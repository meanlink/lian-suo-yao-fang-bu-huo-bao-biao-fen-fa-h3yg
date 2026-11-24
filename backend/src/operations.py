import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from mysql.connector import IntegrityError
from pydantic import BaseModel, ConfigDict, Field

from .auth import current_user, require
from .db import conn, query

router = APIRouter()
MANAGER = require('regional_manager')
INVENTORY = require('inventory_clerk', 'regional_manager')
SHIFT = require('shift_coordinator', 'regional_manager')
LOCAL_ZONE = ZoneInfo('Asia/Shanghai')
LATEST = '''NOT EXISTS (SELECT 1 FROM inventory_snapshots newer WHERE newer.store_code=s.store_code
            AND newer.sku=s.sku AND newer.snapshot_date>s.snapshot_date)'''
RECEIPT_GAP = '''d.status='sent' AND (d.dispatched_at IS NULL OR d.dispatched_at <= NOW() - INTERVAL 2 HOUR)'''


class Note(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=255)


class ExpiryAction(Note):
    action: Literal['quarantined', 'returned']


class Subscription(BaseModel):
    store_code: str = Field(min_length=1, max_length=40)
    recipient_id: int = Field(gt=0)
    delivery_hour: int = Field(ge=0, le=23)


class Enabled(BaseModel):
    enabled: bool


def initialize():
    schema = Path(__file__).resolve().parents[1] / 'operations.sql'
    for statement in schema.read_text().split(';'):
        if statement.strip():
            query(statement, fetch=False)


@contextmanager
def operational_transaction():
    db = conn()
    cur = db.cursor(dictionary=True, buffered=True)
    try:
        yield cur
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        cur.close()
        db.close()


def audit(cur, actor, event, kind, entity_id, **detail):
    cur.execute('''INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,detail) VALUES(%s,%s,%s,%s,%s)''',
                (actor, event, kind, entity_id, json.dumps(detail, ensure_ascii=False)))


@router.get('/expiry-board')
def expiry_board(_user=Depends(current_user)):
    cutoff = datetime.now(LOCAL_ZONE).date() + timedelta(days=30)
    rows, _ = query(f'''SELECT s.id,s.store_code,s.product_name,s.expiry_date,s.on_hand,s.substitute_name,
                       a.action,a.note FROM inventory_snapshots s LEFT JOIN expiry_actions a ON a.snapshot_id=s.id
                       WHERE {LATEST} AND s.expiry_date<=%s AND s.on_hand>0 ORDER BY s.expiry_date,s.id''', (cutoff,))
    return rows


@router.post('/expiry-board/{snapshot_id}', status_code=201)
def expiry_action(snapshot_id: int, data: ExpiryAction, user=Depends(INVENTORY)):
    cutoff = datetime.now(LOCAL_ZONE).date() + timedelta(days=30)
    with operational_transaction() as cur:
        cur.execute(f'SELECT s.id FROM inventory_snapshots s WHERE s.id=%s AND {LATEST} AND s.expiry_date<=%s AND s.on_hand>0 FOR UPDATE',
                    (snapshot_id, cutoff))
        if not cur.fetchone():
            raise HTTPException(409, '仅可处理最新在库且 30 天内到期或已过期的盘点')
        try:
            cur.execute('INSERT INTO expiry_actions(snapshot_id,action,note,actor_id) VALUES(%s,%s,%s,%s)',
                        (snapshot_id, data.action, data.note, user['sub']))
        except IntegrityError as error:
            if error.errno != 1062:
                raise
            raise HTTPException(409, '该临期快照已有处置记录') from error
        audit(cur, user['sub'], 'expiry_action', 'inventory_snapshot', snapshot_id, action=data.action, note=data.note)
    return {'action': data.action}


@router.get('/shortage-board')
def shortages(_user=Depends(current_user)):
    rows, _ = query(f'''SELECT s.id,s.store_code,s.sku,s.product_name,s.on_hand,r.reorder_point,
                       c.status,c.note,c.resolution FROM inventory_snapshots s
                       JOIN replenishment_recommendations r ON r.id=(SELECT MAX(id) FROM replenishment_recommendations WHERE snapshot_id=s.id)
                       LEFT JOIN shortage_cases c ON c.snapshot_id=s.id
                       WHERE ({LATEST} AND s.on_hand<r.reorder_point) OR c.snapshot_id IS NOT NULL
                       ORDER BY COALESCE(c.status='open',FALSE) DESC,s.id''')
    return rows


@router.post('/shortage-board/{snapshot_id}', status_code=201)
def escalate(snapshot_id: int, data: Note, user=Depends(INVENTORY)):
    with operational_transaction() as cur:
        cur.execute(f'''SELECT s.id FROM inventory_snapshots s JOIN replenishment_recommendations r
                     ON r.id=(SELECT MAX(id) FROM replenishment_recommendations WHERE snapshot_id=s.id)
                     WHERE s.id=%s AND {LATEST} AND s.on_hand<r.reorder_point FOR UPDATE''', (snapshot_id,))
        if not cur.fetchone():
            raise HTTPException(409, '请对库存不足的最新快照先运行预测')
        try:
            cur.execute('INSERT INTO shortage_cases(snapshot_id,note,opened_by) VALUES(%s,%s,%s)',
                        (snapshot_id, data.note, user['sub']))
        except IntegrityError as error:
            if error.errno != 1062:
                raise
            raise HTTPException(409, '该快照已登记缺货升级') from error
        audit(cur, user['sub'], 'shortage_escalated', 'inventory_snapshot', snapshot_id, note=data.note)
    return {'status': 'open'}


@router.put('/shortage-board/{snapshot_id}')
def resolve_shortage(snapshot_id: int, data: Note, user=Depends(MANAGER)):
    with operational_transaction() as cur:
        cur.execute('''UPDATE shortage_cases SET status='resolved',resolution=%s,resolved_by=%s,resolved_at=NOW()
                       WHERE snapshot_id=%s AND status='open' ''', (data.note, user['sub'], snapshot_id))
        if cur.rowcount != 1:
            raise HTTPException(409, '没有待关闭的缺货升级记录')
        audit(cur, user['sub'], 'shortage_resolved', 'inventory_snapshot', snapshot_id, resolution=data.note)
    return {'status': 'resolved'}


@router.get('/report-subscriptions')
def subscriptions(user=Depends(current_user)):
    manager = user['role'] == 'regional_manager'
    subscriptions, _ = query('''SELECT rp.*,u.name AS recipient FROM report_subscriptions rp JOIN users u ON u.id=rp.recipient_id
                               WHERE %s OR u.id=%s ORDER BY rp.id''', (manager, user['sub']))
    deliveries, _ = query('''SELECT d.id,d.report_date,d.delivered_at,d.payload,rp.store_code,u.name AS recipient
                             FROM report_deliveries d JOIN report_subscriptions rp ON rp.id=d.subscription_id
                             JOIN users u ON u.id=rp.recipient_id WHERE %s OR u.id=%s
                             ORDER BY d.id DESC LIMIT 60''', (manager, user['sub']))
    for row in deliveries:
        row['payload'] = json.loads(row['payload'])
    stores, _ = query('SELECT DISTINCT store_code,store_name FROM inventory_snapshots ORDER BY store_code') if manager else ([], 0)
    recipients, _ = query('SELECT id,name FROM users ORDER BY id') if manager else ([], 0)
    return {'subscriptions': subscriptions, 'deliveries': deliveries, 'stores': stores, 'recipients': recipients}


@router.post('/report-subscriptions', status_code=201)
def create_subscription(data: Subscription, user=Depends(MANAGER)):
    with operational_transaction() as cur:
        cur.execute('SELECT id FROM inventory_snapshots WHERE store_code=%s LIMIT 1', (data.store_code,))
        if not cur.fetchone():
            raise HTTPException(404, '门店不存在')
        cur.execute('SELECT id FROM users WHERE id=%s', (data.recipient_id,))
        if not cur.fetchone():
            raise HTTPException(404, '收件人不存在')
        try:
            cur.execute('''INSERT INTO report_subscriptions(store_code,recipient_id,delivery_hour,created_on)
                           VALUES(%s,%s,%s,%s)''', (data.store_code, data.recipient_id, data.delivery_hour,
                                                  datetime.now(LOCAL_ZONE).date()))
        except IntegrityError as error:
            if error.errno != 1062:
                raise
            raise HTTPException(409, '该门店、收件人和时间已有订阅') from error
        identifier = cur.lastrowid
        audit(cur, user['sub'], 'report_subscribed', 'report_subscription', identifier, store=data.store_code)
    return {'id': identifier}


@router.put('/report-subscriptions/{subscription_id}')
def toggle_subscription(subscription_id: int, data: Enabled, user=Depends(MANAGER)):
    with operational_transaction() as cur:
        cur.execute('SELECT id,enabled FROM report_subscriptions WHERE id=%s FOR UPDATE', (subscription_id,))
        current = cur.fetchone()
        if not current:
            raise HTTPException(404, '订阅不存在')
        if bool(current['enabled']) != data.enabled:
            cur.execute('UPDATE report_subscriptions SET enabled=%s WHERE id=%s', (data.enabled, subscription_id))
            audit(cur, user['sub'], 'report_schedule_updated', 'report_subscription', subscription_id, enabled=data.enabled)
    return {'enabled': data.enabled}


def deliver_due_reports(now=None):
    now = now or datetime.now(LOCAL_ZONE)
    with operational_transaction() as cur:
        cur.execute('''SELECT s.* FROM report_subscriptions s WHERE s.enabled AND s.created_on<=%s AND s.delivery_hour<=%s
                       AND NOT EXISTS (SELECT 1 FROM report_deliveries d WHERE d.subscription_id=s.id AND d.report_date=%s)
                       ORDER BY s.id LIMIT 50 FOR UPDATE SKIP LOCKED''', (now.date(), now.hour, now.date()))
        for subscription in cur.fetchall():
            cur.execute('''SELECT s.sku,s.product_name,s.snapshot_date,s.on_hand,r.reorder_point,r.recommended_qty,r.status
                          FROM inventory_snapshots s LEFT JOIN replenishment_recommendations r
                          ON r.id=(SELECT MAX(id) FROM replenishment_recommendations WHERE snapshot_id=s.id)
                          WHERE s.store_code=%s AND s.snapshot_date<=%s
                          AND NOT EXISTS (SELECT 1 FROM inventory_snapshots newer WHERE newer.store_code=s.store_code
                          AND newer.sku=s.sku AND newer.snapshot_date>s.snapshot_date AND newer.snapshot_date<=%s) ORDER BY s.sku''',
                        (subscription['store_code'], now.date(), now.date()))
            payload = json.dumps(cur.fetchall(), ensure_ascii=False, default=str)
            cur.execute('INSERT INTO report_deliveries(subscription_id,report_date,payload) VALUES(%s,%s,%s)',
                        (subscription['id'], now.date(), payload))


@router.get('/receipt-audit')
def receipt_audit(_user=Depends(current_user)):
    rows, _ = query(f'''SELECT d.id,d.recipient_name,d.shift,d.status,d.dispatched_at,d.received_at,
                       a.store_code,a.approved_qty,e.reason,e.closed_at,({RECEIPT_GAP}) AS overdue
                       FROM dispatch_records d JOIN approval_orders a ON a.id=d.approval_id
                       LEFT JOIN receipt_exceptions e ON e.dispatch_id=d.id
                       WHERE d.status IN ('sent','received') ORDER BY overdue DESC,d.id DESC LIMIT 120''')
    return rows


@router.post('/receipt-audit/{dispatch_id}', status_code=201)
def flag_receipt(dispatch_id: int, data: Note, user=Depends(SHIFT)):
    with operational_transaction() as cur:
        cur.execute(f'SELECT d.id FROM dispatch_records d WHERE d.id=%s AND {RECEIPT_GAP} FOR UPDATE', (dispatch_id,))
        if not cur.fetchone():
            raise HTTPException(409, '只有超过 2 小时未签收或缺失发送时间的分发可以登记异常')
        try:
            cur.execute('INSERT INTO receipt_exceptions(dispatch_id,reason,opened_by) VALUES(%s,%s,%s)',
                        (dispatch_id, data.note, user['sub']))
        except IntegrityError as error:
            if error.errno != 1062:
                raise
            raise HTTPException(409, '该分发已有异常记录') from error
        audit(cur, user['sub'], 'receipt_flagged', 'dispatch', dispatch_id, reason=data.note)
    return {'status': 'open'}


@router.put('/receipt-audit/{dispatch_id}')
def close_receipt(dispatch_id: int, user=Depends(SHIFT)):
    with operational_transaction() as cur:
        cur.execute('''UPDATE receipt_exceptions e JOIN dispatch_records d ON d.id=e.dispatch_id
                       SET e.closed_at=NOW(),e.closed_by=%s WHERE d.id=%s AND d.status='received'
                       AND d.received_at IS NOT NULL AND e.closed_at IS NULL''', (user['sub'], dispatch_id))
        if cur.rowcount != 1:
            raise HTTPException(409, '需先确认收件，再结清待跟进异常')
        audit(cur, user['sub'], 'receipt_reconciled', 'dispatch', dispatch_id)
    return {'status': 'closed'}
