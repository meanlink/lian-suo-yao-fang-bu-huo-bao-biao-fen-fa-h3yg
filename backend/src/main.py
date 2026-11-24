from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from datetime import date
import json, os
from .db import query
from .auth import token_for, current_user, require
from .services.replenishment import forecast_replenishment
from .middlewares.controls import RequestGuard

from . import operations
from .warehouse import count_routes, lot_routes, migrations, pick_routes, picklists, recall_routes, temperature_routes


@asynccontextmanager
async def lifespan(app):
    operations.initialize()
    migrations.initialize()
    yield


app=FastAPI(title='连锁药房补货报表分发', version='3.0.0', lifespan=lifespan)
app.include_router(operations.router)
for feature in (lot_routes, pick_routes, temperature_routes, recall_routes, count_routes):
    app.include_router(feature.router)
app.add_middleware(RequestGuard)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

class Login(BaseModel): email:str; password:str
class SnapshotIn(BaseModel): store_code:str; store_name:str; sku:str; product_name:str; category:str; on_hand:float; daily_sales:list[float]; lead_time_days:int=2; safety_days:float=2; pack_size:int=10; expiry_date:str|None=None; substitute_sku:str|None=None; substitute_name:str|None=None; snapshot_date:str='2026-11-21'
class OverrideIn(BaseModel): qty:int=Field(ge=0); note:str=Field(min_length=3)
class ReviewIn(BaseModel): decision:str; note:str=''
class DispatchIn(BaseModel): recipient_name:str; shift:str

@app.get('/health')
def health(): return {'status':'ok','service':'pharmacy-replenishment'}
@app.post('/auth/login')
def login(payload:Login):
    rows,_=query('SELECT id,email,name,role FROM users WHERE email=%s AND password=%s',(payload.email,payload.password))
    if not rows: raise HTTPException(401,'邮箱或密码错误')
    return {'access_token':token_for(rows[0]),'user':rows[0]}
@app.get('/auth/me')
def me(user=Depends(current_user)): return user
@app.get('/dashboard')
def dashboard(user=Depends(current_user)):
    rows,_=query('SELECT status,COUNT(*) count FROM replenishment_recommendations GROUP BY status')
    stores,_=query('SELECT store_code,store_name,COUNT(*) sku_count,SUM(on_hand) units FROM inventory_snapshots GROUP BY store_code,store_name ORDER BY store_code')
    return {'summary':rows,'stores':stores,'user':user}
@app.get('/snapshots')
def snapshots(user=Depends(current_user)):
    rows,_=query('SELECT * FROM inventory_snapshots ORDER BY snapshot_date DESC,store_code,sku')
    for r in rows: r['daily_sales']=json.loads(r['daily_sales']); r['expiry_date']=str(r['expiry_date']) if r['expiry_date'] else None
    return rows
@app.post('/snapshots')
def create_snapshot(payload:SnapshotIn,user=Depends(require('inventory_clerk','regional_manager'))):
    try:
        _,rid=query('INSERT INTO inventory_snapshots(store_code,store_name,sku,product_name,category,on_hand,daily_sales,lead_time_days,safety_days,pack_size,expiry_date,substitute_sku,substitute_name,snapshot_date) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(payload.store_code,payload.store_name,payload.sku,payload.product_name,payload.category,payload.on_hand,json.dumps(payload.daily_sales),payload.lead_time_days,payload.safety_days,payload.pack_size,payload.expiry_date,payload.substitute_sku,payload.substitute_name,payload.snapshot_date),fetch=False)
    except Exception as e: raise HTTPException(409,'同门店同 SKU 同盘点日已存在')
    query('INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,detail) VALUES(%s,%s,%s,%s,%s)',(user['sub'],'create_snapshot','inventory_snapshot',rid,json.dumps({'sku':payload.sku})),fetch=False)
    return {'id':rid,'status':'counted'}
@app.post('/snapshots/{sid}/forecast')
def forecast(sid:int,user=Depends(require('inventory_clerk','regional_manager'))):
    rows,_=query('SELECT * FROM inventory_snapshots WHERE id=%s',(sid,))
    if not rows: raise HTTPException(404,'盘点快照不存在')
    s=rows[0]; result=forecast_replenishment(json.loads(s['daily_sales']),s['on_hand'],s['lead_time_days'],s['safety_days'],s['pack_size'],str(s['expiry_date']) if s['expiry_date'] else None,s['substitute_sku'])
    old,_=query('SELECT id FROM replenishment_recommendations WHERE snapshot_id=%s',(sid,))
    if old: query('UPDATE replenishment_recommendations SET avg_daily=%s,safety_stock=%s,reorder_point=%s,recommended_qty=%s,reason=%s,status=%s WHERE id=%s',(result['avg_daily'],result['safety_stock'],result['reorder_point'],result['recommended_qty'],result['reason'],'blocked' if result['blocked'] else 'draft',old[0]['id']),fetch=False); rid=old[0]['id']
    else: _,rid=query('INSERT INTO replenishment_recommendations(snapshot_id,avg_daily,safety_stock,reorder_point,recommended_qty,reason,status) VALUES(%s,%s,%s,%s,%s,%s,%s)',(sid,result['avg_daily'],result['safety_stock'],result['reorder_point'],result['recommended_qty'],result['reason'],'blocked' if result['blocked'] else 'draft'),fetch=False)
    query('UPDATE inventory_snapshots SET status=%s WHERE id=%s',('forecasted',sid),fetch=False)
    return {'id':rid,**result,'status':'blocked' if result['blocked'] else 'draft'}
@app.get('/recommendations')
def recommendations(user=Depends(current_user)):
    rows,_=query('SELECT r.*,s.store_code,s.store_name,s.sku,s.product_name,s.on_hand,s.expiry_date,s.substitute_name FROM replenishment_recommendations r JOIN inventory_snapshots s ON s.id=r.snapshot_id ORDER BY r.id DESC')
    return rows
@app.post('/recommendations/{rid}/override')
def override(rid:int,payload:OverrideIn,user=Depends(require('regional_manager'))):
    rows,_=query('SELECT * FROM replenishment_recommendations WHERE id=%s',(rid,))
    if not rows: raise HTTPException(404,'补货建议不存在')
    query('UPDATE replenishment_recommendations SET override_qty=%s,recommended_qty=%s,status=%s,reason=%s WHERE id=%s',(payload.qty,payload.qty,'overridden',payload.note,rid),fetch=False)
    return {'id':rid,'status':'overridden','recommended_qty':payload.qty}
@app.post('/recommendations/{rid}/submit')
def submit(rid:int,user=Depends(require('inventory_clerk','regional_manager'))):
    rows,_=query('SELECT status FROM replenishment_recommendations WHERE id=%s',(rid,))
    if not rows: raise HTTPException(404,'补货建议不存在')
    if rows[0]['status']=='blocked': raise HTTPException(409,'临期药品与可替代品冲突，必须先人工改写')
    query('UPDATE replenishment_recommendations SET status=%s WHERE id=%s',('submitted',rid),fetch=False); return {'status':'submitted'}
@app.get('/approvals')
def approvals(user=Depends(current_user)):
    rows,_=query('SELECT a.*,r.recommended_qty,r.status recommendation_status,s.product_name,s.store_name FROM approval_orders a JOIN replenishment_recommendations r ON r.id=a.recommendation_id JOIN inventory_snapshots s ON s.id=r.snapshot_id ORDER BY a.id DESC')
    return rows
@app.post('/approvals/{rid}')
def create_approval(rid:int,user=Depends(require('inventory_clerk','regional_manager'))):
    rows,_=query('SELECT r.*,s.store_code FROM replenishment_recommendations r JOIN inventory_snapshots s ON s.id=r.snapshot_id WHERE r.id=%s',(rid,))
    if not rows or rows[0]['status'] not in ('submitted','overridden'): raise HTTPException(409,'只有已提交或已改写的建议可以送审')
    _,aid=query('INSERT INTO approval_orders(recommendation_id,store_code,delivery_shift,approved_qty) VALUES(%s,%s,%s,%s)',(rid,rows[0]['store_code'],'morning',rows[0]['recommended_qty']),fetch=False)
    return {'id':aid,'status':'pending'}
@app.put('/approvals/{aid}')
def review(aid:int,payload:ReviewIn,user=Depends(require('regional_manager'))):
    if payload.decision not in ('approved','rejected'): raise HTTPException(422,'decision 必须为 approved 或 rejected')
    rows,_=query('SELECT * FROM approval_orders WHERE id=%s',(aid,))
    if not rows or rows[0]['status']!='pending': raise HTTPException(409,'审核单当前不可操作')
    query('UPDATE approval_orders SET status=%s,reviewer_id=%s,review_note=%s,reviewed_at=NOW() WHERE id=%s',(payload.decision,user['sub'],payload.note,aid),fetch=False)
    if payload.decision=='approved': query('UPDATE replenishment_recommendations SET status=%s WHERE id=%s',('approved',rows[0]['recommendation_id']),fetch=False)
    return {'status':payload.decision}
@app.get('/dispatches')
def dispatches(user=Depends(current_user)):
    rows,_=query('SELECT d.*,a.store_code,a.approved_qty,s.product_name,s.store_name FROM dispatch_records d JOIN approval_orders a ON a.id=d.approval_id JOIN replenishment_recommendations r ON r.id=a.recommendation_id JOIN inventory_snapshots s ON s.id=r.snapshot_id ORDER BY d.id DESC')
    return rows
@app.post('/dispatches/{aid}')
def dispatch(aid:int,payload:DispatchIn,user=Depends(require('shift_coordinator','regional_manager'))):
    if payload.shift not in ('morning','afternoon','night'): raise HTTPException(422,'班次不合法')
    with operations.operational_transaction() as cursor:
        cursor.execute('SELECT status FROM approval_orders WHERE id=%s FOR UPDATE', (aid,))
        row = cursor.fetchone()
        if not row or row['status'] != 'approved':
            raise HTTPException(409, '只有已批准审核单可以分发')
        picklists.consume_for_dispatch(cursor, aid, user['sub'])
        cursor.execute("""INSERT INTO dispatch_records(approval_id,recipient_name,shift,status,dispatched_at)
                          VALUES(%s,%s,%s,'sent',NOW())""", (aid, payload.recipient_name, payload.shift))
        dispatch_id = cursor.lastrowid
        cursor.execute("UPDATE approval_orders SET status='distributed' WHERE id=%s", (aid,))
    return {'id': dispatch_id, 'status': 'sent'}
@app.put('/dispatches/{did}/receive')
def receive(did:int,user=Depends(require('shift_coordinator'))):
    rows,_=query('SELECT status FROM dispatch_records WHERE id=%s',(did,))
    if not rows or rows[0]['status']!='sent': raise HTTPException(409,'该分发单当前不可收件确认')
    query('UPDATE dispatch_records SET status=%s,received_at=NOW() WHERE id=%s',('received',did),fetch=False); return {'status':'received'}
