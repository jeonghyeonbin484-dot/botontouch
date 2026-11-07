"""공용 PostgreSQL에 기존 SQLite 스냅샷을 보관하는 서버 저장소.

PC 파일을 읽지 않고 요청별 임시 복제본을 사용한다. PostgreSQL 커밋이
성공한 뒤에만 응답하며, 운영 환경에서는 빈 DB나 가상 계정을 생성하지 않는다.
"""
import os,tempfile,hashlib,threading,time
from contextlib import contextmanager,closing
from pathlib import Path
import cloud_context

MAX_DATABASE_BYTES=20*1024*1024

class StorageUnavailable(Exception):
 def __init__(self,message,code='STORAGE_UNAVAILABLE',retry_after=15):
  super().__init__(message);self.code=code;self.retry_after=retry_after

# 캐시 사용 전에도 PostgreSQL의 최신 버전을 매 요청 검증한다. 인증 결과는 캐시하지 않는다.
_cache_lock=threading.Lock()
_snapshot_cache={}
_failure_backoff={}

def reset_runtime_cache():
 with _cache_lock:_snapshot_cache.clear();_failure_backoff.clear()

def _cached(key,version):
 with _cache_lock:
  item=_snapshot_cache.get(key)
  return item[1] if item and item[0]==version else None

def _publish(key,version,raw):
 with _cache_lock:
  _snapshot_cache.clear();_snapshot_cache[key]=(version,raw)
  _failure_backoff.pop(key,None)



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


def demo_search_fixtures():
 """Add fictional test staff without editing existing departments/users/documents."""
 import app,auth_control
 with closing(app.connect()) as db:
  if db.execute("SELECT 1 FROM org_employees WHERE employee_id='DEMO-GLOBAL'").fetchone():return
  for code,name in [('DEMO-AI','AI전략팀 (가상)'),('DEMO-BIGDATA','빅데이터팀 (가상)')]:
   db.execute("INSERT OR IGNORE INTO org_departments(id,name,source) VALUES(?,?,'demo')",(code,name))
  for identifier,name,dept,login,position in [('DEMO-GLOBAL','가상 빅데이터 직원','DEMO-BIGDATA','demo.global','가상 주무관'),('DEMO-SAME-A','가상 동명이인','DEMO-AI','demo.same.a','가상 팀장'),('DEMO-SAME-B','가상 동명이인','DEMO-BIGDATA','demo.same.b','가상 주무관')]:
   db.execute("INSERT OR IGNORE INTO org_employees(employee_id,name,department_id,position,saeoll_id,source) VALUES(?,?,?,?,?,'demo')",(identifier,name,dept,position,login))
  # This additional fictional login intentionally starts without a staff link.
  # It is issued explicitly by the demo fixture, not by an organization lookup.
  if not db.execute("SELECT 1 FROM users WHERE username='demo.global'").fetchone():
   password=os.environ.get('BATON_DEMO_PASSWORD','')
   if len(password)<16:raise StorageUnavailable('테스트 계정 비밀번호 설정을 확인하세요.')
   db.execute("INSERT INTO users(username,password_hash,salt,role,active,must_change_password,is_test) VALUES(?,?,'','member',1,0,0)",('demo.global',auth_control.password_hash(password)))
  db.commit()


@contextmanager
def database_request():
 """최신 버전 확인 → 개인 요청별 복사 → 원자적 저장. DB 장애 시 캐시로 인증하지 않는다."""
 try:url=__import__('cloud_database_config').connection_url()
 except __import__('cloud_database_config').DatabaseConfigurationError as error:raise StorageUnavailable(str(error),'STORAGE_NOT_CONFIGURED',60) from None
 key=hashlib.sha256(url.encode()).digest()
 with _cache_lock:failure=_failure_backoff.get(key)
 if failure and failure[0]>time.monotonic():raise StorageUnavailable(failure[1],failure[2],max(1,int(failure[0]-time.monotonic())))
 import psycopg
 pending=None
 try:
  with psycopg.connect(url,connect_timeout=10,autocommit=False,prepare_threshold=None) as pg:
   pg.execute("SET LOCAL lock_timeout='15s'")
   pg.execute("SET LOCAL statement_timeout='85s'")
   if os.environ.get('BATON_CLOUD_LOCAL_TEST')=='1':
    pg.execute('CREATE TABLE IF NOT EXISTS baton_demo_state (id integer PRIMARY KEY CHECK(id=1), payload bytea, updated timestamptz DEFAULT now())')
    pg.execute('INSERT INTO baton_demo_state(id) VALUES(1) ON CONFLICT DO NOTHING')
   # 큰 payload 대신 작은 버전값만 받는다. 다른 인스턴스의 수정·세션 폐기도 즉시 감지한다.
   current=pg.execute('SELECT updated FROM baton_demo_state WHERE id=1 FOR UPDATE').fetchone()
   if not current:raise StorageUnavailable('공용 DB에 기존 상태 행이 없어 초기화하지 않았습니다. 연결 대상을 확인하세요.','STORAGE_NOT_INITIALIZED',60)
   version=current[0]
   before=_cached(key,version)
   if before is None:
    row=pg.execute('SELECT payload FROM baton_demo_state WHERE id=1').fetchone()
    before=bytes(row[0]) if row[0] is not None else None
   with tempfile.TemporaryDirectory(prefix='baton-request-') as folder:
    root=Path(folder);file=root/'library.sqlite3'
    if before:
     if len(before)>MAX_DATABASE_BYTES:raise StorageUnavailable('저장공간 한도를 초과했습니다.')
     file.write_bytes(before)
    token=cloud_context.current_data.set(root)
    try:
     if os.environ.get('BATON_CLOUD_LOCAL_TEST')=='1':
      if not before:seed()
      demo_search_fixtures()
     elif not before:
      raise StorageUnavailable('공용 DB에 기존 데이터가 없어 초기화하지 않았습니다. 연결 대상을 확인하세요.','STORAGE_NOT_INITIALIZED',60)
     yield
     after=file.read_bytes()
     if len(after)>MAX_DATABASE_BYTES:raise StorageUnavailable('공유 저장공간 한도(20MB)를 초과했습니다. 입력은 화면에 유지됩니다.')
     if after!=before:
      version=pg.execute('UPDATE baton_demo_state SET payload=%s,updated=clock_timestamp() WHERE id=1 RETURNING updated',(after,)).fetchone()[0]
     pending=(version,after)
    finally:cloud_context.current_data.reset(token)
  # PostgreSQL 커밋 성공 뒤에만 캐시를 공개한다. 커밋 실패 시 세션/데이터 성공 응답도 나가지 않는다.
  if pending:_publish(key,*pending)
 except StorageUnavailable:raise
 except Exception as error:
  quota='quota' in str(error).lower() and 'exceeded' in str(error).lower()
  if quota or type(error).__name__ in ('OperationalError','InterfaceError','ConnectionTimeout'):
   delay=60 if quota else 15
   code='STORAGE_QUOTA_EXCEEDED' if quota else 'STORAGE_UNAVAILABLE'
   notice='DB 사용 한도 초과로 연결이 차단되었습니다. 기존 데이터는 유지됩니다.' if quota else 'DB 연결을 확인할 수 없습니다. 잠시 후 다시 시도하세요.'
   with _cache_lock:_failure_backoff[key]=(time.monotonic()+delay,notice,code)
   failure=StorageUnavailable(notice,code,delay);failure.failure_kind=type(error).__name__;failure.sqlstate=getattr(error,'sqlstate',None)
   raise failure from None
  raise


def readiness():
 """공개 상태 확인용 읽기 전용 쿼리. 계정/자료/스냅샷 본문은 읽거나 생성하지 않는다."""
 import cloud_database_config as config,psycopg
 try:url=config.connection_url()
 except config.DatabaseConfigurationError as error:raise StorageUnavailable(str(error),'STORAGE_NOT_CONFIGURED',60) from None
 with psycopg.connect(url,connect_timeout=10,autocommit=False,prepare_threshold=None) as pg:
  pg.execute('SET TRANSACTION READ ONLY')
  pg.execute("SET LOCAL statement_timeout='8s'")
  pg.execute('SELECT 1')
  initialized=pg.execute('SELECT payload IS NOT NULL FROM public.baton_demo_state WHERE id=1').fetchone()
  if not initialized or not initialized[0]:raise StorageUnavailable('공용 DB에 기존 데이터가 확인되지 않아 처리를 중단했습니다. DB 연결 대상을 확인하세요.','STORAGE_NOT_INITIALIZED',60)
 return {'status':'ready','release':'full-20261107-storage',**config.safe_metadata(),'checked':True,'mode':'postgresql_sqlite_snapshot','authentication_required':True}
