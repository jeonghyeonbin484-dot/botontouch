"""기존 스키마와 연결 절차를 유지하는 데이터베이스 연결."""
import sqlite3
from pathlib import Path
from batontouch.auth import sessions as auth_control; from batontouch.handover import requests as handover_requests; from batontouch.handover import workflow as handover_workflow; from batontouch.handover import journey as handover_journey
def open_application_database(data_directory):
    DATA = __import__('cloud_context').current_data.get() or data_directory
    DATA.mkdir(parents=True,exist_ok=True)
    auth_control.backup_before_migration(DATA / 'library.sqlite3')
    handover_requests.backup_before_migration(DATA / 'library.sqlite3')
    db = sqlite3.connect(DATA / 'library.sqlite3',timeout=30)
    db.row_factory = sqlite3.Row
    db.create_function('staff_rank',1,__import__('staff_order').rank,deterministic=True)
    db.execute('CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, name TEXT, content TEXT, sources TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute('CREATE TABLE IF NOT EXISTS drafts (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute("CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY, title TEXT NOT NULL, department TEXT NOT NULL DEFAULT '', predecessor TEXT NOT NULL DEFAULT '', successor TEXT NOT NULL DEFAULT '', reference_date TEXT NOT NULL DEFAULT '')")
    db.execute("INSERT OR IGNORE INTO workspaces(id,title) VALUES(1,'기존 인수인계')")
    db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, title TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '', assignee TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '', deleted INTEGER NOT NULL DEFAULT 0)")
    db.execute('CREATE TABLE IF NOT EXISTS suggestions (id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    auth_control.ensure(db)
    handover_workflow.ensure(db)
    handover_requests.ensure(db)
    __import__('handover_chat').ensure(db)
    handover_journey.ensure(db)
    __import__('ai_studio').ensure(db)
    __import__('workbench').ensure(db)
    __import__('journey_authoring').ensure(db)
    __import__('request_inbox').ensure(db)
    for table in ('documents', 'drafts', 'questions'):
        if 'workspace_id' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN workspace_id INTEGER NOT NULL DEFAULT 1')
        db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_workspace ON {table}(workspace_id)')
        if 'deleted' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
    if 'revision' not in {r['name'] for r in db.execute('PRAGMA table_info(documents)')}:
        db.execute('ALTER TABLE documents ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
    db.commit()
    return db
