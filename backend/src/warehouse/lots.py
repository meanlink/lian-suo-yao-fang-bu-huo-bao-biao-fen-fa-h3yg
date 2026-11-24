from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from mysql.connector import IntegrityError

from ..db import query
from ..operations import audit, operational_transaction


def local_day():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


def lock_lot(cursor, lot_id):
    cursor.execute('SELECT * FROM warehouse_lots WHERE id=%s FOR UPDATE', (lot_id,))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, '仓库批号不存在')
    return row


def list_stock():
    rows, _ = query('''SELECT *, on_hand-reserved free_units FROM warehouse_lots
                       ORDER BY sku,expires_on,id''')
    return {'lots': rows, 'warehousing_day': local_day()}


def register(data, actor):
    if not isinstance(data.expires_on, date) or data.expires_on <= local_day():
        raise HTTPException(422, '只可登记有效期晚于今天的入库批号')
    try:
        with operational_transaction() as cursor:
            cursor.execute('SELECT id FROM inventory_snapshots WHERE sku=%s LIMIT 1', (data.sku,))
            if not cursor.fetchone():
                raise HTTPException(422, '请先建立该 SKU 的门店库存档案')
            cursor.execute('''INSERT INTO warehouse_lots
                (sku,lot_code,supplier_ref,expires_on,temperature_band,initial_units,on_hand,registered_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                (data.sku, data.lot_code, data.supplier_ref, data.expires_on,
                 data.temperature_band, data.units, data.units, actor))
            lot_id = cursor.lastrowid
            audit(cursor, actor, 'warehouse.lot_received', 'warehouse_lot', lot_id,
                  supplier_ref=data.supplier_ref, units=data.units)
    except IntegrityError as error:
        if error.errno == 1062:
            raise HTTPException(409, '该 SKU 的供货批号已登记') from error
        raise
    return {'id': lot_id, 'on_hand': data.units}
