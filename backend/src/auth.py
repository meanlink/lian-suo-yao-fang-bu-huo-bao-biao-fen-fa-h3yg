from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Header, HTTPException, Depends
from .config import JWT_SECRET

def token_for(user):
    return jwt.encode({'sub':str(user['id']),'email':user['email'],'name':user['name'],'role':user['role'],'exp':datetime.now(timezone.utc)+timedelta(hours=8)}, JWT_SECRET, algorithm='HS256')

def current_user(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'请先登录')
    try: return jwt.decode(authorization.split(' ',1)[1], JWT_SECRET, algorithms=['HS256'])
    except Exception: raise HTTPException(401,'登录已过期')

def require(*roles):
    def dep(user=Depends(current_user)):
        if user['role'] not in roles: raise HTTPException(403,'当前角色无权执行此动作')
        return user
    return dep
