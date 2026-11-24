import os
DB = dict(host=os.getenv('MYSQL_HOST','db'), user=os.getenv('MYSQL_USER','pharmacy'), password=os.getenv('MYSQL_PASSWORD','pharmacy-local'), database=os.getenv('MYSQL_DATABASE','pharmacy_replenishment'), port=3306)
JWT_SECRET = os.getenv('JWT_SECRET','pharmacy-replenishment-demo-secret')
SHARED_DIR = os.getenv('SHARED_DIR','/shared')
