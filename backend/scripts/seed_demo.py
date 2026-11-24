import json,sys,time
sys.path.insert(0,'/app')
from src.db import query
users=[('clerk@huimin.local','demo123','林晓','inventory_clerk'),('manager@huimin.local','demo123','周岚','regional_manager'),('shift@huimin.local','demo123','赵凯','shift_coordinator')]
for u in users: query('INSERT INTO users(email,password,name,role) VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name),role=VALUES(role)',u,fetch=False)
items=[('S001','惠民人民路店','RX-1001','阿莫西林胶囊 0.25g','抗感染',18,[12,14,11,16,13,15,14],2,2,10,None,None,None),('S001','惠民人民路店','OTC-2003','复方感冒灵颗粒','感冒用药',46,[5,7,6,8,6,5,7],2,3,10,'2026-11-28','OTC-2010','复方氨酚烷胺片'),('S002','惠民湖滨店','DM-3010','二甲双胍片 0.5g','慢病用药',30,[9,10,8,11,12,10,9],3,2,10,None,None,None),('S002','惠民湖滨店','BP-4012','电子血压计袖带','健康器械',8,[1,2,1,2,1,1,2],4,2,5,None,None,None)]
for item in items:
    try:
        query('INSERT INTO inventory_snapshots(store_code,store_name,sku,product_name,category,on_hand,daily_sales,lead_time_days,safety_days,pack_size,expiry_date,substitute_sku,substitute_name,snapshot_date) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(*item[:6],json.dumps(item[6]),*item[7:],'2026-11-21'),fetch=False)
    except Exception: pass
print('seed ok',query('SELECT COUNT(*) count FROM users')[0][0]['count'],query('SELECT COUNT(*) count FROM inventory_snapshots')[0][0]['count'])
