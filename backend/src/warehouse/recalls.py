from fastapi import HTTPException
from mysql.connector import IntegrityError

from ..db import query
from ..operations import audit, operational_transaction
from .lots import lock_lot


def list_recalls():
    notices, _ = query('''SELECT w.*,l.sku,l.lot_code,l.on_hand FROM warehouse_recalls w
                         JOIN warehouse_lots l ON l.id=w.lot_id ORDER BY w.id DESC''')
    actions, _ = query('''SELECT i.*,p.status pick_status,a.store_code FROM warehouse_recall_actions i
                         JOIN warehouse_picklists p ON p.id=i.picklist_id
                         JOIN approval_orders a ON a.id=p.approval_id ORDER BY a.store_code,p.id''')
    by_notice = {notice['id']: notice for notice in notices}
    for notice in notices:
        notice['exposures'] = []
    for action in actions:
        if action['recall_id'] in by_notice:
            by_notice[action['recall_id']]['exposures'].append(action)
    return notices


def open_notice(data, actor):
    try:
        with operational_transaction() as cursor:
            lot = lock_lot(cursor, data.lot_id)
            if lot['state'] != 'available':
                raise HTTPException(409, '该批号已有召回通知')
            cursor.execute("UPDATE warehouse_lots SET state='recalled' WHERE id=%s", (data.lot_id,))
            cursor.execute('INSERT INTO warehouse_recalls (lot_id,notice_ref,reason,opened_by) VALUES(%s,%s,%s,%s)',
                           (data.lot_id, data.notice_ref, data.reason, actor))
            recall_id = cursor.lastrowid
            cursor.execute('''SELECT p.id,p.status,i.units FROM warehouse_pick_lines i
                            JOIN warehouse_picklists p ON p.id=i.picklist_id
                            WHERE i.lot_id=%s AND p.status IN ('reserved','packed','dispatched')''', (data.lot_id,))
            exposures = cursor.fetchall()
            if exposures:
                cursor.executemany('''INSERT INTO warehouse_recall_actions
                    (recall_id,picklist_id,status_at_notice,exposed_units) VALUES(%s,%s,%s,%s)''',
                    [(recall_id, pick['id'], pick['status'], pick['units']) for pick in exposures])
            audit(cursor, actor, 'warehouse.recall_opened', 'warehouse_recall', recall_id,
                  lot_code=lot['lot_code'], affected_picklists=len(exposures))
    except IntegrityError as error:
        if error.errno == 1062:
            raise HTTPException(409, '召回编号已使用') from error
        raise
    return {'id': recall_id, 'affected_picklists': len(exposures)}


def lock_notice(cursor, recall_id):
    cursor.execute('SELECT * FROM warehouse_recalls WHERE id=%s FOR UPDATE', (recall_id,))
    notice = cursor.fetchone()
    if not notice:
        raise HTTPException(404, '找不到召回通知')
    if notice['closed_at']:
        raise HTTPException(409, '召回已结案')
    return notice


def confirm(recall_id, pick_id, data, actor):
    with operational_transaction() as cursor:
        lock_notice(cursor, recall_id)
        cursor.execute('''SELECT i.*,p.status pick_status FROM warehouse_recall_actions i
                        JOIN warehouse_picklists p ON p.id=i.picklist_id WHERE i.recall_id=%s AND i.picklist_id=%s''',
                       (recall_id, pick_id))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, '该拣货单不在召回范围内')
        if row['handled_at']:
            raise HTTPException(409, '该召回行动已登记')
        if row['status_at_notice'] == 'dispatched':
            if data.isolated_units != row['exposed_units']:
                raise HTTPException(409, '门店隔离数量须与该批实际发车数量一致')
        elif row['pick_status'] != 'cancelled' or data.isolated_units != 0:
            raise HTTPException(409, '先撤销未发车拣货单，再登记零件发出')
        cursor.execute('''UPDATE warehouse_recall_actions SET outlet_ref=%s,isolated_units=%s,handled_by=%s,
                          handled_at=NOW() WHERE recall_id=%s AND picklist_id=%s''',
                       (data.outlet_ref, data.isolated_units, actor, recall_id, pick_id))
        audit(cursor, actor, 'warehouse.recall_action_confirmed', 'warehouse_recall', recall_id,
              picklist=pick_id, isolated_units=data.isolated_units)
    return {'id': recall_id, 'picklist_id': pick_id, 'handled': True}


def close(recall_id, actor):
    with operational_transaction() as cursor:
        lock_notice(cursor, recall_id)
        cursor.execute('SELECT 1 FROM warehouse_recall_actions WHERE recall_id=%s AND handled_at IS NULL LIMIT 1', (recall_id,))
        if cursor.fetchone():
            raise HTTPException(409, '仍有未回执的召回行动')
        cursor.execute('UPDATE warehouse_recalls SET closed_at=NOW() WHERE id=%s', (recall_id,))
        audit(cursor, actor, 'warehouse.recall_closed', 'warehouse_recall', recall_id)
    return {'id': recall_id, 'closed': True}
