import time
import mysql.connector
from .config import DB

def conn():
    last = None
    for _ in range(20):
        try:
            return mysql.connector.connect(**DB)
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise last

def query(sql, params=(), fetch=True, many=False):
    c=conn(); cur=c.cursor(dictionary=True)
    try:
        if many: cur.executemany(sql, params)
        else: cur.execute(sql, params)
        rows=cur.fetchall() if fetch else []
        c.commit()
        return rows, cur.lastrowid
    finally:
        cur.close(); c.close()
