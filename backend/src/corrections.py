import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, NonNegativeFloat

from .auth import current_user, require
from .db import query
from .operations import audit, operational_transaction
from .services.replenishment import forecast_replenishment
from .warehouse import picklists

router = APIRouter()
INVENTORY = require('inventory_clerk', 'regional_manager')


class CorrectionIn(BaseModel):
    revision: int = Field(ge=1)
    daily_sales: list[NonNegativeFloat] = Field(min_length=1)
    note: str = Field(default='', max_length=255)


def initialize():
    """Give existing databases the voided order state; fresh installs ship it in schema.sql."""
    rows, _ = query('''SELECT COLUMN_TYPE FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='approval_orders' AND COLUMN_NAME='status' ''')
    if rows and 'voided' not in rows[0]['COLUMN_TYPE']:
        query("""ALTER TABLE approval_orders MODIFY status
                 ENUM('pending','approved','rejected','distributed','voided') NOT NULL DEFAULT 'pending'""", fetch=False)


def _summary(cursor, correction):
    cursor.execute('''SELECT o.approval_id,o.previous_status,o.outcome,a.approved_qty
                      FROM sales_correction_orders o JOIN approval_orders a ON a.id=o.approval_id
                      WHERE o.correction_id=%s ORDER BY o.approval_id''', (correction['id'],))
    orders = cursor.fetchall()
    cursor.execute('''SELECT status FROM replenishment_recommendations
                      WHERE snapshot_id=%s ORDER BY id DESC LIMIT 1''', (correction['snapshot_id'],))
    recommendation = cursor.fetchone()
    return {
        'id': correction['id'],
        'snapshot_id': correction['snapshot_id'],
        'revision': correction['revision'],
        'old_recommended_qty': correction['old_recommended_qty'],
        'new_recommended_qty': correction['new_recommended_qty'],
        'replacement_approval_id': correction['replacement_approval_id'],
        'recommendation_status': recommendation['status'] if recommendation else None,
        'orders': orders,
        'voided': [order['approval_id'] for order in orders if order['outcome'] == 'voided'],
        'kept_dispatched': [order['approval_id'] for order in orders if order['outcome'] == 'kept_dispatched'],
    }


@router.post('/snapshots/{snapshot_id}/sales-corrections', status_code=201)
def apply_correction(snapshot_id: int, data: CorrectionIn, user=Depends(INVENTORY)):
    with operational_transaction() as cursor:
        cursor.execute('SELECT * FROM inventory_snapshots WHERE id=%s FOR UPDATE', (snapshot_id,))
        snapshot = cursor.fetchone()
        if not snapshot:
            raise HTTPException(404, '盘点快照不存在')
        cursor.execute('SELECT * FROM sales_corrections WHERE snapshot_id=%s AND revision=%s',
                       (snapshot_id, data.revision))
        existing = cursor.fetchone()
        if existing:  # 同一修订重试：返回首次办理结果，不重复送审
            return {**_summary(cursor, existing), 'duplicate': True}
        cursor.execute('SELECT COALESCE(MAX(revision),0) AS max_revision FROM sales_corrections WHERE snapshot_id=%s',
                       (snapshot_id,))
        max_revision = cursor.fetchone()['max_revision']
        if data.revision <= max_revision:  # 乱序到达的过期修订不生效
            raise HTTPException(409, f'已应用更高的修订号 {max_revision}，本次修订 {data.revision} 未生效')

        result = forecast_replenishment(
            data.daily_sales, snapshot['on_hand'], snapshot['lead_time_days'], snapshot['safety_days'],
            snapshot['pack_size'], str(snapshot['expiry_date']) if snapshot['expiry_date'] else None,
            snapshot['substitute_sku'])
        cursor.execute("UPDATE inventory_snapshots SET daily_sales=%s,status='forecasted' WHERE id=%s",
                       (json.dumps(data.daily_sales), snapshot_id))

        cursor.execute('''SELECT * FROM replenishment_recommendations WHERE snapshot_id=%s
                          ORDER BY id DESC LIMIT 1 FOR UPDATE''', (snapshot_id,))
        recommendation = cursor.fetchone()
        old_qty = recommendation['recommended_qty'] if recommendation else None
        prior_status = recommendation['status'] if recommendation else None
        recalculated_status = 'blocked' if result['blocked'] else 'draft'
        if recommendation:
            cursor.execute('''UPDATE replenishment_recommendations
                              SET avg_daily=%s,safety_stock=%s,reorder_point=%s,recommended_qty=%s,reason=%s,
                                  status=%s,override_qty=NULL,calculated_at=NOW()
                              WHERE id=%s''',
                           (result['avg_daily'], result['safety_stock'], result['reorder_point'],
                            result['recommended_qty'], result['reason'], recalculated_status, recommendation['id']))
            recommendation_id = recommendation['id']
        else:
            cursor.execute('''INSERT INTO replenishment_recommendations
                              (snapshot_id,avg_daily,safety_stock,reorder_point,recommended_qty,reason,status)
                              VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                           (snapshot_id, result['avg_daily'], result['safety_stock'], result['reorder_point'],
                            result['recommended_qty'], result['reason'], recalculated_status))
            recommendation_id = cursor.lastrowid

        cursor.execute('''INSERT INTO sales_corrections
                          (snapshot_id,revision,daily_sales,old_recommended_qty,new_recommended_qty,note,actor_id)
                          VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                       (snapshot_id, data.revision, json.dumps(data.daily_sales), old_qty,
                        result['recommended_qty'], data.note, user['sub']))
        correction_id = cursor.lastrowid

        # 与发车共用审核单行锁串行：先提交的一方生效，另一方按最新状态判定
        cursor.execute('''SELECT a.id,a.status,a.approved_qty,a.delivery_shift FROM approval_orders a
                          JOIN replenishment_recommendations r ON r.id=a.recommendation_id
                          WHERE r.snapshot_id=%s AND a.status IN ('pending','approved','distributed')
                          ORDER BY a.id FOR UPDATE OF a''', (snapshot_id,))
        voided, kept = [], []
        for order in cursor.fetchall():
            if order['status'] == 'distributed':  # 已发车：原单数量照旧，只重算建议
                outcome = 'kept_dispatched'
                kept.append(order)
            else:  # 未发车：作废待审或已批单，释放拣配预留
                picklists.release_for_correction(cursor, order['id'], user['sub'])
                cursor.execute("UPDATE approval_orders SET status='voided' WHERE id=%s", (order['id'],))
                outcome = 'voided'
                voided.append(order)
            cursor.execute('''INSERT INTO sales_correction_orders
                              (correction_id,approval_id,previous_status,outcome) VALUES(%s,%s,%s,%s)''',
                           (correction_id, order['id'], order['status'], outcome))

        replacement_id = None
        if not result['blocked'] and (voided or prior_status in ('submitted', 'overridden')):
            cursor.execute("UPDATE replenishment_recommendations SET status='submitted' WHERE id=%s",
                           (recommendation_id,))
            shift = voided[-1]['delivery_shift'] if voided else 'morning'
            cursor.execute('''INSERT INTO approval_orders(recommendation_id,store_code,delivery_shift,approved_qty)
                              VALUES(%s,%s,%s,%s)''',
                           (recommendation_id, snapshot['store_code'], shift, result['recommended_qty']))
            replacement_id = cursor.lastrowid
            cursor.execute('UPDATE sales_corrections SET replacement_approval_id=%s WHERE id=%s',
                           (replacement_id, correction_id))

        audit(cursor, user['sub'], 'sales_correction_applied', 'sales_correction', correction_id,
              snapshot_id=snapshot_id, revision=data.revision, old_qty=old_qty,
              new_qty=result['recommended_qty'], voided=[order['id'] for order in voided],
              kept_dispatched=[order['id'] for order in kept], replacement_approval=replacement_id)
        cursor.execute('SELECT * FROM sales_corrections WHERE id=%s', (correction_id,))
        return {**_summary(cursor, cursor.fetchone()), 'duplicate': False}


@router.get('/sales-corrections')
def list_corrections(_user=Depends(current_user)):
    rows, _ = query('''SELECT c.id,c.snapshot_id,c.revision,c.old_recommended_qty,c.new_recommended_qty,
                       c.replacement_approval_id,c.note,c.created_at,
                       s.store_code,s.store_name,s.sku,s.product_name,u.name AS actor_name
                       FROM sales_corrections c
                       JOIN inventory_snapshots s ON s.id=c.snapshot_id
                       JOIN users u ON u.id=c.actor_id ORDER BY c.id DESC LIMIT 100''')
    order_rows, _ = query('''SELECT o.correction_id,o.approval_id,o.previous_status,o.outcome,
                             a.approved_qty,a.status AS current_status
                             FROM sales_correction_orders o JOIN approval_orders a ON a.id=o.approval_id
                             ORDER BY o.approval_id''')
    by_correction = {}
    for row in rows:
        row['orders'] = []
        by_correction[row['id']] = row
    for order in order_rows:
        if order['correction_id'] in by_correction:
            by_correction[order['correction_id']]['orders'].append(order)
    return rows
