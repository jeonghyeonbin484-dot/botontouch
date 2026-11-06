import os,secrets,unittest,tempfile,sqlite3
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from test_cloud import Fixture
class CloudFirstPasswordTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.admin=self.f.login('demo.admin');self.env=patch.dict(os.environ,{'BATON_SMTP_HOST':'smtp.example.test','BATON_SMTP_USER':'fictional','BATON_SMTP_PASSWORD':'fictional-only','BATON_SMTP_FROM':'noreply@agency.test','BATON_STAFF_EMAIL_DOMAINS':'agency.test','BATON_OTP_SIGNING_SECRET':secrets.token_urlsafe(32)});self.env.start()
  self.modify("UPDATE org_employees SET source='org_api' WHERE employee_id='DEMO-B'");self.modify("UPDATE users SET active=0,must_change_password=1,password_changed=NULL WHERE username='demo.b'")
  self.f.call('/api/auth/first-password/channels',{'official_source_confirmed':True,'items':[{'employee_id':'DEMO-B','saeoll_id':'demo.b','email':'staff@agency.test'}]},self.admin)
 def tearDown(self):self.env.stop();self.f.stop()
 def modify(self,sql):
  with tempfile.TemporaryDirectory() as folder:
   file=Path(folder)/'state.sqlite3';file.write_bytes(self.f.memory.payload)
   with closing(sqlite3.connect(file)) as db:db.execute(sql);db.commit()
   with self.f.memory.lock:self.f.memory.payload=file.read_bytes();self.f.memory.version+=1
 def test_real_route_self_password_once_and_normal_login(self):
  client=self.f.client()
  with patch('staff_self_service._send_code') as send:self.f.call('/api/auth/first-password/request',{'username':'DEMO.B'},client);code=send.call_args.args[1]
  new='Fictional-Personal-Password-25!';body={'username':'DEMO.B','code':code,'new_password':new,'confirmation':new}
  self.assertTrue(self.f.call('/api/auth/first-password/confirm',body,client)['activated']);self.f.call('/api/auth/logout',{},client);self.f.call('/api/auth/login',{'username':'DEMO.B','password':new},client)
  self.assertEqual(self.f.call('/api/auth/status',client=client)['user']['username'],'demo.b')
 def test_requested_shared_initial_password_forces_change(self):
  import password_security
  encoded=password_security.hash_password('1234!')
  self.modify("UPDATE users SET active=1,must_change_password=1,password_changed=NULL,initial_shared=1,password_hash='"+encoded+"' WHERE username='demo.b'")
  with patch.dict(os.environ,{'BATON_STAFF_SHARED_INITIAL_ALLOWED':'true'}):
   client=self.f.client();self.f.call('/api/auth/login',{'username':'DEMO.B','password':'1234!'},client)
   self.assertTrue(self.f.call('/api/auth/status',client=client)['user']['must_change_password'])
   with self.assertRaises(__import__('urllib.error',fromlist=['HTTPError']).HTTPError) as error:self.f.call('/api/workspaces',client=client)
   self.assertEqual(error.exception.code,403);error.exception.close()
   new='Fictional-New-Password-26!';self.f.call('/api/auth/session-password',{'username':'demo.b','new_password':new,'confirmation':new},client)
   with self.assertRaises(__import__('urllib.error',fromlist=['HTTPError']).HTTPError) as error:self.f.call('/api/auth/login',{'username':'demo.b','password':'1234!'})
   self.assertEqual(error.exception.code,401);error.exception.close()
   self.f.call('/api/auth/login',{'username':'demo.b','password':new},client);self.assertFalse(self.f.call('/api/auth/status',client=client)['user']['must_change_password'])
 def test_shared_initial_disabled_by_default(self):
  with patch.dict(os.environ,{'BATON_STAFF_SHARED_INITIAL_ALLOWED':'false'}):
   with self.assertRaises(__import__('urllib.error',fromlist=['HTTPError']).HTTPError) as error:self.f.call('/api/auth/login',{'username':'demo.b','password':'1234!'})
   self.assertEqual(error.exception.code,409);error.exception.close()
 def test_unconfigured_does_not_send_or_activate(self):
  with patch.dict(os.environ,{'BATON_OTP_SIGNING_SECRET':''}),patch('staff_self_service._send_code') as send:
   self.assertFalse(self.f.call('/api/auth/first-password/options')['enabled'])
   with self.assertRaises(__import__('urllib.error',fromlist=['HTTPError']).HTTPError) as error:self.f.call('/api/auth/first-password/request',{'username':'demo.b'})
   self.assertEqual(error.exception.code,503);error.exception.close();send.assert_not_called()
if __name__=='__main__':unittest.main()
