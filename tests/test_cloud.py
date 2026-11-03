"""HTTP contract tests using a transactional in-memory Postgres double.
No Neon/Vercel/OpenAI/Gemini/organization requests are performed.
"""
import sys,os,io,json,threading,types,http.cookiejar,urllib.request,urllib.error,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
# Local test dependency location only; excluded from the published package.
local_vendor=ROOT.parents[1]/'.vendor'
if local_vendor.exists():sys.path.insert(0,str(local_vendor))
from api.index import handler
import app,cloud_store,handover_workflow
PASSWORD='Fictional-Test-Password-1947!'

class MemoryDatabase:
 def __init__(self):self.payload=None;self.lock=threading.Lock();self.fail_commit=False;self.commits=0
 def connect(self,*args,**kwargs):return Transaction(self)
class Transaction:
 def __init__(self,owner):self.owner=owner;self.payload=None;self.changed=False
 def __enter__(self):self.owner.lock.acquire();self.payload=self.owner.payload;return self
 def __exit__(self,kind,value,trace):
  try:
   if kind is None:
    if self.owner.fail_commit:raise RuntimeError('FAKE DATABASE PASSWORD MUST NEVER LEAK')
    self.owner.payload=self.payload;self.owner.commits+=1
  finally:self.owner.lock.release()
 def execute(self,sql,args=None):
  if sql.startswith('UPDATE baton_demo_state'):self.payload=bytes(args[0]);self.changed=True
  return self
 def fetchone(self):return (self.payload,)

class Fixture:
 def start(self):
  self.memory=MemoryDatabase();self.driver=patch.dict(sys.modules,{'psycopg':types.SimpleNamespace(connect=self.memory.connect)});self.driver.start()
  self.env=patch.dict(os.environ,{'DATABASE_URL':'postgresql://fictional.invalid/test','BATON_DEMO_PASSWORD':PASSWORD,'BATON_CLOUD_LOCAL_TEST':'1'});self.env.start()
  self.server=app.LocalServer(('127.0.0.1',0),handler);self.portenv=patch.dict(os.environ,{'BATON_PORT':str(self.server.server_port)});self.portenv.start()
  threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.server.server_port);return self
 def stop(self):self.server.shutdown();self.server.server_close();self.portenv.stop();self.env.stop();self.driver.stop()
 def client(self):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def raw(self,path,body=None,client=None,headers=None):
  data=body if isinstance(body,bytes) else json.dumps(body).encode() if body is not None else None
  return (client or self.client()).open(urllib.request.Request(self.url+path,data=data,headers=headers or {}))
 def call(self,path,body=None,client=None,headers=None):
  with self.raw(path,body,client,headers) as r:return json.load(r)
 def login(self,name):
  client=self.client();self.call('/api/auth/login',{'username':name,'password':PASSWORD},client);return client

class CloudTests(unittest.TestCase):
 def setUp(self):self.f=Fixture().start()
 def tearDown(self):self.f.stop()
 def reject(self,path,body=None,client=None,status=403,headers=None):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(path,body,client,headers)
  self.assertEqual(e.exception.code,status);return e.exception.read().decode()
 def prepare(self):
  a=self.f.login('demo.a');doc=self.f.call('/api/documents','가상 사무용품을 매월 점검합니다.'.encode(),a,{'X-File-Name':'demo.txt'})
  draft=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a)
  draft['reviewed']=True;draft=self.f.call('/api/drafts/save',draft,a)
  return a,draft
 def test_login_gate_shared_sessions_and_logout(self):
  self.reject('/api/documents',status=401)
  a=self.f.login('demo.a');self.assertEqual(self.f.call('/api/auth/status',client=a)['user']['username'],'demo.a')
  self.assertGreater(self.f.memory.commits,1)
  self.f.call('/api/auth/logout',{},a);self.reject('/api/documents',client=a,status=401)
 def test_fictional_roster_only_and_no_internal_sync(self):
  a=self.f.login('demo.a');depts=self.f.call('/api/directory/departments',client=a);self.assertEqual(len(depts),3)
  staff=self.f.call('/api/directory/employees?department_id=DEMO-RECEIVE',client=a);self.assertEqual(staff['total'],2)
  self.assertTrue(all(e['employee_id'].startswith('DEMO-') for e in staff['items']))
  self.reject('/api/directory/sync',{'employees':True},a)
 def test_upload_mock_draft_save_send_receive_accept_complete_hwpx(self):
  a,draft=self.prepare();self.assertIn('실제 AI 아님',draft['model']);self.assertEqual(draft['mode'],'mock')
  id=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':draft['id'],'recipient_employee':'DEMO-B','fingerprint':draft['edit_token']},a)['id']
  b=self.f.login('demo.b');c=self.f.login('demo.c');self.assertEqual(self.f.call('/api/requests?box=received',client=b)['pending'],1)
  self.reject('/api/requests/'+str(id),client=c)
  self.f.call('/api/requests/action',{'id':id,'revision':1,'action':'accept'},b)
  self.assertEqual(self.f.call('/api/requests/'+str(id),client=a)['state'],'accepted')
  self.f.call('/api/requests/action',{'id':id,'revision':1,'action':'complete'},a)
  with self.f.raw('/api/requests/'+str(id)+'/export.hwpx',client=b) as r:
   with zipfile.ZipFile(io.BytesIO(r.read())) as archive:self.assertIsNone(archive.testzip())
 def test_durable_commit_failure_never_returns_success_or_cookie(self):
  self.f.login('demo.a');before=self.f.memory.payload;self.f.memory.fail_commit=True
  body=self.reject('/api/auth/login',{'username':'demo.b','password':PASSWORD},status=503)
  self.assertNotIn('PASSWORD',body);self.assertNotIn('postgresql',body);self.assertEqual(self.f.memory.payload,before)
 def test_absent_storage_fails_closed(self):
  with patch.dict(os.environ,{'DATABASE_URL':''}):self.reject('/api/auth/status',status=503)
 def test_request_size_limit(self):self.reject('/api/documents',b'x'*(4*1024*1024+1),status=413)
 def test_cross_origin_request_blocked(self):
  a=self.f.login('demo.a');self.reject('/api/workspaces/create',{'title':'가상'},a,headers={'Origin':'https://untrusted.example'})
 def test_private_files_not_web_accessible(self):
  a=self.f.login('demo.admin')
  for path in ('/.env','/cloud_store.py','/data/library.sqlite3','/organization.local.json'):self.reject(path,client=a,status=404)
 def test_demo_status_no_secrets(self):
  s=self.f.call('/api/demo/status');self.assertEqual(s['ai_mode'],'mock');self.assertFalse(s['external_transmission_allowed']);self.assertNotIn('password',json.dumps(s).lower())

if __name__=='__main__':unittest.main()

