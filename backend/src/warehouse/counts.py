from fastapi import HTTPException
from mysql.connector import IntegrityError

from ..db import query
from ..operations import audit, operational_transaction
from .lots import lock_lot


def count_queue():
    counts, _ = query('''SELECT c.*,l.sku,l.lot_code,
                         CAST(c.counted_units AS SIGNED)-CAST(c.system_units AS SIGNED) delta
                         FROM warehouse_cycle_counts c JOIN warehouse_lots l ON l.id=c.lot_id ORDER BY c.id DESC''')
    return counts


def submit(data, actor):
    try:
        with operational_transaction() as cursor:
            lot = lock_lot(cursor, data.lot_id)
            if lot['state'] != 'available':
                raise HTTPException(409, '召回批号的数量由召回流程核销')
            cursor.execute("SELECT id FROM warehouse_cycle_counts WHERE lot_id=%s AND state='pending' LIMIT 1", (data.lot_id,))
            if cursor.fetchone():
                raise HTTPException(409, '该批号已有待复核盘差')
            cursor.execute('''INSERT INTO warehouse_cycle_counts
                              (lot_id,count_ref,system_units,counted_units,discrepancy_reason,counted_by)
                              VALUES(%s,%s,%s,%s,%s,%s)''',
                           (data.lot_id, data.count_ref, lot['on_hand'], data.counted_units, data.reason, actor))
            count_id = cursor.lastrowid
            audit(cursor, actor, 'warehouse.count_submitted', 'warehouse_count', count_id,
                  system_units=lot['on_hand'], counted_units=data.counted_units)
    except IntegrityError as error:
        if error.errno == 1062:
            raise HTTPException(409, '盘点凭证已使用') from error
        raise
    return {'id': count_id, 'state': 'pending'}


def review(count_id, data, actor):
    with operational_transaction() as cursor:
        cursor.execute('SELECT * FROM warehouse_cycle_counts WHERE id=%s FOR UPDATE', (count_id,))
        count = cursor.fetchone()
        if not count:
            raise HTTPException(404, '盘差单不存在')
        if count['state'] != 'pending':
            raise HTTPException(409, '盘差单已复核')
        if str(count['counted_by']) == str(actor):
            raise HTTPException(409, '盘点与复核须由不同人员执行')
        if data.decision == 'posted':
            lot = lock_lot(cursor, count['lot_id'])
            if lot['state'] != 'available' or lot['on_hand'] != count['system_units']:
                raise HTTPException(409, '盘点后库存状态已发生变化，请退回重盘')
            if count['counted_units'] < lot['reserved']:
                raise HTTPException(409, '实盘数量小于拣货预留，请处理预留后再过账')
            cursor.execute('UPDATE warehouse_lots SET on_hand=%s WHERE id=%s', (count['counted_units'], lot['id']))
        cursor.execute('''UPDATE warehouse_cycle_counts SET state=%s,reviewer_note=%s,reviewed_by=%s,
                          reviewed_at=NOW() WHERE id=%s''', (data.decision, data.note, actor, count_id))
        audit(cursor, actor, 'warehouse.count_reviewed', 'warehouse_count', count_id, decision=data.decision)
    return {'id': count_id, 'state': data.decision}
