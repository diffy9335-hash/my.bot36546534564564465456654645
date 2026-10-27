"""Durable sync diagnostics and consistent SQLite backups (virtual-currency only)."""
import os, sqlite3, json, time, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from .core import DB_PATH, connect, LOCK, iso, utcnow

log=logging.getLogger(__name__)

def init_operations():
    with LOCK,connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
          finished_at TEXT NOT NULL, ok INTEGER NOT NULL, mode TEXT,
          updated INTEGER NOT NULL DEFAULT 0, settled INTEGER NOT NULL DEFAULT 0,
          error TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON sync_runs(started_at DESC)')

def record_sync(started, result=None, error=None):
    with LOCK,connect() as c:
        c.execute('INSERT INTO sync_runs(started_at,finished_at,ok,mode,updated,settled,error) VALUES (?,?,?,?,?,?,?)',
                  (started, iso(utcnow()), 0 if error else 1,
                   (result or {}).get('mode'), (result or {}).get('updated',0),
                   (result or {}).get('settled',0), str(error)[:500] if error else None))
        c.execute('DELETE FROM sync_runs WHERE id NOT IN (SELECT id FROM sync_runs ORDER BY id DESC LIMIT 500)')

def operations_overview():
    with connect() as c:
        runs=[dict(r) for r in c.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 20')]
        counts=dict(c.execute('SELECT (SELECT COUNT(*) FROM matches) AS matches, (SELECT COUNT(*) FROM slips WHERE status="pending") AS pending_slips').fetchone())
    latest=runs[0] if runs else None
    last_good=next((x for x in runs if x['ok']),None)
    age=None
    if last_good:
        age=int((utcnow()-datetime.fromisoformat(last_good['finished_at'])).total_seconds())
    max_age=max(300,int(os.getenv('SYNC_MINUTES','2'))*60*3)
    return {'latest':latest,'last_success_at':last_good['finished_at'] if last_good else None,
            'last_success_age_seconds':age, 'stale':age is None or age>max_age,
            'max_success_age_seconds':max_age,'recent_runs':runs,**counts}

def create_backup(directory=None, keep=None):
    """sqlite3.backup creates a consistent copy while main DB uses WAL."""
    src=Path(DB_PATH)
    if not src.exists(): raise FileNotFoundError('Database does not exist')
    dest_dir=Path(directory or os.getenv('BACKUP_DIR','./backups'))
    dest_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    keep=int(keep if keep is not None else os.getenv('BACKUP_KEEP','14'))
    if keep<1: raise ValueError('BACKUP_KEEP must be >= 1')
    stamp=utcnow().strftime('%Y%m%dT%H%M%S%fZ')
    target=dest_dir/f'football-{stamp}.sqlite3'
    try:
        with sqlite3.connect(str(src),timeout=30) as source:
            with sqlite3.connect(str(target),timeout=30) as dest:
                source.backup(dest)
                res=dest.execute('PRAGMA integrity_check').fetchone()[0]
                if res!='ok': raise RuntimeError('Backup integrity check failed')
        target.chmod(0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    files=sorted(dest_dir.glob('football-*.sqlite3'),key=lambda f:f.name,reverse=True)
    for old in files[keep:]: old.unlink()
    return {'file':str(target),'bytes':target.stat().st_size,'verified':True}

def backup_loop():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.once:
        print(json.dumps(create_backup(),ensure_ascii=False)); return
    interval=max(1,int(os.getenv('BACKUP_HOURS','24')))*3600
    while True:
        try: log.info('Backup: %s',create_backup())
        except Exception: log.exception('Backup failed')
        time.sleep(interval)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    backup_loop()
