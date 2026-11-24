import time
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestGuard(BaseHTTPMiddleware):
    def __init__(self, app): super().__init__(app); self.hits=defaultdict(list)
    async def dispatch(self, request: Request, call_next):
        key=request.client.host if request.client else 'unknown'; now=time.time(); recent=[x for x in self.hits[key] if now-x<60]
        if len(recent)>=120: from fastapi.responses import JSONResponse; return JSONResponse({'detail':'请求过于频繁'},status_code=429)
        recent.append(now); self.hits[key]=recent
        response=await call_next(request); response.headers['X-Request-Guard']='active'; return response
