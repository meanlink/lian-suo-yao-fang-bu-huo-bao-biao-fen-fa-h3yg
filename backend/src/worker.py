import logging
import time
from pathlib import Path

from .config import SHARED_DIR
from .operations import deliver_due_reports

logging.basicConfig(level=logging.INFO)
heartbeat = Path(SHARED_DIR, 'worker-heartbeat')
heartbeat.parent.mkdir(parents=True, exist_ok=True)
while True:
    try:
        deliver_due_reports()
        heartbeat.touch()
    except Exception:
        logging.exception('Scheduled report delivery failed')
    time.sleep(5)
