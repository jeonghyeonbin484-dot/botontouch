"""Demo-only persistence: serialize existing SQLite under a Postgres row lock.

The Postgres transaction is held until the handler completes. Never send a successful
HTTP response before durable commit. Fresh /tmp files per request prevent sharing
mutable SQLite state across concurrent Fluid Compute invocations.
This preserves the existing SQLite SQL without migrating/copying local business data.
"""
import os,tempfile
from contextlib import contextmanager,closing
from pathlib import Path
import cloud_context

MAX_DATABASE_BYTES=20*1024*1024

class StorageUnavailable(Exception):pass


def seed():
 import app,auth_control
 with closing(app.connect()) as db:
  if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():return
  password=os.environ.get('BATON_DEMO_PASSWORD','')
  if len(password)<16:raise StorageUnavailable('테스트 계정 비밀번호 설정이 필요합니다.')
  db.execute("UPDATE workspaces SET title='[가상 예시] 사무용품 구매 및 관리',department='가상 행정지원팀' WHERE id=1")
  for key,name in [('DEMO-ADMIN','가상 관리팀'),('DEMO-SUPPORT','가상 행정지원팀'),('DEMO-RECEIVE','가상 업무지원팀')]:
   db.execute("INSERT INTO org_departments(id,name,source) VALUES(?,?,'demo')",(key,name))
  for username,name,dept,role,identifier in [('demo.admin','가상 관리자','DEMO-ADMIN','admin','DEMO-ADMIN-1'),('demo.a','가상 인계자','DEMO-SUPPORT','member','DEMO-A'),('demo.b','가상 인수자','DEMO-RECEIVE','member','DEMO-B'),('demo.c','가상 다른 직원','DEMO-RECEIVE','member','DEMO-C')]:
   cur=db.execute("INSERT INTO users(username,password_hash,salt,role,active,must_change_password,is_test) VALUES(?,?,'',?,1,0,0)",(username,auth_control.password_hash(password),role));uid=cur.lastrowid
   db.execute("INSERT INTO org_employees(employee_id,name,department_id,position,saeoll_id,source) VALUES(?,?,?,'가상 주무관',?,'demo')",(identifier,name,dept,username))
   db.execute('INSERT INTO employee_accounts(employee_id,user_id,linked_by) VALUES(?,?,1)',(identifier,uid))
   if username in ('demo.admin','demo.a'):db.execute("INSERT INTO workspace_members VALUES(1,?,'editor')",(uid,))
  db.commit()


@contextmanager
def database_request():
 """Never fall back to nonpersistent SQLite when shared storage is missing."""
 url=os.environ.get('DATABASE_URL','')
 if not url:raise StorageUnavailable('공유 테스트 데이터베이스가 연결되지 않았습니다.')
 import psycopg
 # Credentials must never appear in exception responses or logs.
 with psycopg.connect(url,connect_timeout=10,autocommit=False) as pg:
  pg.execute("SET LOCAL lock_timeout='15s'")
  pg.execute("SET LOCAL statement_timeout='50s'")
  pg.execute('CREATE TABLE IF NOT EXISTS baton_demo_state (id integer PRIMARY KEY CHECK(id=1), payload bytea, updated timestamptz DEFAULT now())')
  pg.execute('INSERT INTO baton_demo_state(id) VALUES(1) ON CONFLICT DO NOTHING')
  row=pg.execute('SELECT payload FROM baton_demo_state WHERE id=1 FOR UPDATE').fetchone()
  before=bytes(row[0]) if row[0] is not None else None
  with tempfile.TemporaryDirectory(prefix='baton-demo-') as folder:
   root=Path(folder);file=root/'library.sqlite3'
   if before:
    if len(before)>MAX_DATABASE_BYTES:raise StorageUnavailable('테스트 저장공간 한도를 초과했습니다.')
    file.write_bytes(before)
   token=cloud_context.current_data.set(root)
   try:
    if not before:seed()
    yield
    after=file.read_bytes()
    if len(after)>MAX_DATABASE_BYTES:raise StorageUnavailable('공개 테스트의 합계 저장 한도(20MB)를 초과했습니다. 입력은 화면에 유지됩니다.')
    if after!=before:pg.execute('UPDATE baton_demo_state SET payload=%s,updated=now() WHERE id=1',(after,))
   finally:cloud_context.current_data.reset(token)
 # Commit occurs here, before HTTP response emission in api/index.py.
