from pathlib import Path

from ..db import query


def initialize():
    """Install additive warehouse tables in dependency order on an existing database."""
    directory = Path(__file__).resolve().parents[2] / 'warehousing'
    migrations = sorted(directory.glob('*.sql'))
    if not migrations:
        raise RuntimeError('仓配数据表迁移文件未随镜像安装')
    for migration in migrations:
        for statement in migration.read_text(encoding='utf-8').split(';'):
            if statement.strip():
                query(statement, fetch=False)
