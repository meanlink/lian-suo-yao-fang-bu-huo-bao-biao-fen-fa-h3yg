from fastapi import HTTPException

from ..db import query
from ..operations import audit, operational_transaction
from .lots import local_day


def lock_picklist(cursor, pick_id):
    cursor.execute('SELECT * FROM warehouse_picklists WHERE id=%s FOR UPDATE', (pick_id,))
    pick = cursor.fetchone()
    if pick is None:
        raise HTTPException(404, '拣货单不存在')
    return pick


def lock_lines(cursor, pick_id):
    cursor.execute('''SELECT i.lot_id,i.units,l.lot_code,l.state,l.expires_on,l.temperature_band
                      FROM warehouse_pick_lines i JOIN warehouse_lots l ON i.lot_id=l.id
                      WHERE i.picklist_id=%s ORDER BY l.id FOR UPDATE''', (pick_id,))
    return cursor.fetchall()


def list_board():
    picks, _ = query('''SELECT p.id,p.approval_id,p.status,a.store_code,s.sku,a.approved_qty,
                        p.packed_at FROM warehouse_picklists p JOIN approval_orders a ON a.id=p.approval_id
                        JOIN replenishment_recommendations r ON r.id=a.recommendation_id
                        JOIN inventory_snapshots s ON s.id=r.snapshot_id ORDER BY p.id DESC''')
    lines, _ = query('''SELECT i.*,l.lot_code,l.expires_on,l.temperature_band,l.state FROM warehouse_pick_lines i
                        JOIN warehouse_lots l ON l.id=i.lot_id ORDER BY l.expires_on,l.id''')
    orders, _ = query('''SELECT a.id,a.store_code,s.sku,a.approved_qty FROM approval_orders a
                         JOIN replenishment_recommendations r ON r.id=a.recommendation_id
                         JOIN inventory_snapshots s ON s.id=r.snapshot_id WHERE a.status='approved' AND a.approved_qty>0
                         AND NOT EXISTS (SELECT 1 FROM warehouse_picklists p WHERE p.approval_id=a.id AND p.active_slot=1)
                         ORDER BY a.id DESC''')
    by_pick = {p['id']: p for p in picks}
    for pick in picks:
        pick['lines'] = []
    for line in lines:
        if line['picklist_id'] in by_pick:
            by_pick[line['picklist_id']]['lines'].append(line)
    return {'eligible_orders': orders, 'picklists': picks}


def reserve(approval_id, actor):
    with operational_transaction() as cursor:
        cursor.execute('''SELECT a.status,a.approved_qty,s.sku FROM approval_orders a
                          JOIN replenishment_recommendations r ON r.id=a.recommendation_id
                          JOIN inventory_snapshots s ON s.id=r.snapshot_id WHERE a.id=%s FOR UPDATE OF a''', (approval_id,))
        order = cursor.fetchone()
        if not order or order['status'] != 'approved' or not order['approved_qty']:
            raise HTTPException(409, '仅可拣配已审批且数量为正的订单')
        cursor.execute('SELECT id FROM warehouse_picklists WHERE approval_id=%s AND active_slot=1', (approval_id,))
        if cursor.fetchone():
            raise HTTPException(409, '该订单已有有效拣货单')
        cursor.execute('''SELECT id,on_hand-reserved free_units,expires_on FROM warehouse_lots
                          WHERE sku=%s AND state='available' AND expires_on>%s ORDER BY id FOR UPDATE''',
                       (order['sku'], local_day()))
        lots = sorted(cursor.fetchall(), key=lambda item: (item['expires_on'], item['id']))
        if sum(lot['free_units'] for lot in lots) < order['approved_qty']:
            raise HTTPException(409, '未召回且未过期的可用库存不足，未占用任何批号')
        cursor.execute('INSERT INTO warehouse_picklists (approval_id,reserved_by) VALUES(%s,%s)', (approval_id, actor))
        pick_id = cursor.lastrowid
        remaining = order['approved_qty']
        for lot in lots:
            units = min(lot['free_units'], remaining)
            if not units:
                continue
            cursor.execute('UPDATE warehouse_lots SET reserved=reserved+%s WHERE id=%s', (units, lot['id']))
            cursor.execute('INSERT INTO warehouse_pick_lines (picklist_id,lot_id,units) VALUES(%s,%s,%s)',
                           (pick_id, lot['id'], units))
            remaining -= units
        audit(cursor, actor, 'warehouse.pick_reserved', 'warehouse_picklist', pick_id, quantity=order['approved_qty'])
    return {'id': pick_id, 'status': 'reserved'}


def assert_shippable(lines):
    if any(line['state'] != 'available' or line['expires_on'] <= local_day() for line in lines):
        raise HTTPException(409, '拣货单含召回或已过期批号，请撤销并重新拣配')


def pack(pick_id, actor):
    with operational_transaction() as cursor:
        pick = lock_picklist(cursor, pick_id)
        if pick['status'] != 'reserved':
            raise HTTPException(409, '只有待打包的拣货单可以确认')
        lines = lock_lines(cursor, pick_id)
        assert_shippable(lines)
        if any(line['temperature_band'] == 'chilled' for line in lines):
            from .temperatures import require_passing_measurement

            require_passing_measurement(cursor, pick_id)
        cursor.execute("UPDATE warehouse_picklists SET status='packed',packed_by=%s,packed_at=NOW() WHERE id=%s",
                       (actor, pick_id))
        audit(cursor, actor, 'warehouse.pick_packed', 'warehouse_picklist', pick_id)
    return {'id': pick_id, 'status': 'packed'}


def cancel(pick_id, actor):
    with operational_transaction() as cursor:
        pick = lock_picklist(cursor, pick_id)
        if pick['status'] not in {'reserved', 'packed'}:
            raise HTTPException(409, '只有发车前的拣货单可撤销')
        for line in lock_lines(cursor, pick_id):
            cursor.execute('UPDATE warehouse_lots SET reserved=reserved-%s WHERE id=%s', (line['units'], line['lot_id']))
        cursor.execute("UPDATE warehouse_picklists SET status='cancelled' WHERE id=%s", (pick_id,))
        audit(cursor, actor, 'warehouse.pick_cancelled', 'warehouse_picklist', pick_id)
    return {'id': pick_id, 'status': 'cancelled'}


def consume_for_dispatch(cursor, approval_id, actor):
    """Convert an approved warehouse reservation into stock movement inside dispatch's transaction."""
    cursor.execute('SELECT * FROM warehouse_picklists WHERE approval_id=%s AND active_slot=1 FOR UPDATE', (approval_id,))
    pick = cursor.fetchone()
    if not pick:
        cursor.execute('''SELECT l.id FROM approval_orders a
            JOIN replenishment_recommendations r ON r.id=a.recommendation_id
            JOIN inventory_snapshots s ON s.id=r.snapshot_id
            JOIN warehouse_lots l ON l.sku=s.sku WHERE a.id=%s LIMIT 1''', (approval_id,))
        if cursor.fetchone():
            raise HTTPException(409, '仓配 SKU 发车前须建立并确认拣货单')
        return
    if pick['status'] != 'packed':
        raise HTTPException(409, '仓配订单必须先确认打包')
    lines = lock_lines(cursor, pick['id'])
    assert_shippable(lines)
    if any(line['temperature_band'] == 'chilled' for line in lines):
        from .temperatures import require_passing_measurement

        require_passing_measurement(cursor, pick['id'])
    for line in lines:
        cursor.execute('UPDATE warehouse_lots SET on_hand=on_hand-%s,reserved=reserved-%s WHERE id=%s',
                       (line['units'], line['units'], line['lot_id']))
    cursor.execute("UPDATE warehouse_picklists SET status='dispatched' WHERE id=%s", (pick['id'],))
    audit(cursor, actor, 'warehouse.pick_dispatched', 'warehouse_picklist', pick['id'], approval_id=approval_id)
