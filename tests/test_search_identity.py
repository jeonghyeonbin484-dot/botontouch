import sys,json,unittest
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_cloud import Fixture,CloudTests,PASSWORD
import app,cloud_store,auth_control

class SearchIdentityTests(unittest.TestCase):
 setUp=CloudTests.setUp
 tearDown=CloudTests.tearDown
 reject=CloudTests.reject
 prepare=CloudTests.prepare
 def modify(self,sql,args=()):
  with cloud_store.database_request(),closing(app.connect()) as db:db.execute(sql,args);db.commit()
 def send(self,a,draft,recipient):return self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':draft['id'],'recipient_employee':recipient,'fingerprint':draft['edit_token']},a)
 def test_global_search_is_independent_of_selected_department(self):
  a=self.f.login('demo.a');self.assertEqual(self.f.call('/api/directory/employees?department_id=DEMO-AI',client=a)['total'],1)
  result=self.f.call('/api/directory/employees/search?q='+__import__('urllib.parse',fromlist=['quote']).quote('가상 빅데이터 직원')+'&department_id=DEMO-AI',client=a)
  self.assertEqual(result['scope'],'all_departments');self.assertEqual(result['items'][0]['department_id'],'DEMO-BIGDATA');self.assertEqual(result['items'][0]['employee_id'],'DEMO-GLOBAL')
  duplicate=self.f.call('/api/directory/employees/search?q='+__import__('urllib.parse',fromlist=['quote']).quote('동명이인'),client=a)['items'];self.assertEqual(len(duplicate),2);self.assertEqual(len({x['department_id'] for x in duplicate}),2)
  self.assertEqual(self.f.call('/api/directory/employees/search?q=%25',client=a)['total'],0)
  self.reject('/api/directory/employees/search?q=a',status=401)
 def test_sender_missing_mapping_repaired_without_manual_link(self):
  self.modify("DELETE FROM employee_accounts WHERE employee_id='DEMO-A'")
  a,draft=self.prepare();id=self.send(a,draft,'DEMO-B')['id'];self.assertTrue(id)
  with cloud_store.database_request(),closing(app.connect()) as db:
   row=db.execute("SELECT e.employee_id,e.saeoll_id FROM employee_accounts a JOIN org_employees e ON e.employee_id=a.employee_id JOIN users u ON u.id=a.user_id WHERE u.username='demo.a'").fetchone();self.assertEqual(tuple(row),('DEMO-A','demo.a'))
 def test_pending_request_claimed_on_first_login_and_other_user_blocked(self):
  a,draft=self.prepare();id=self.send(a,draft,'DEMO-GLOBAL')['id'];self.assertTrue(self.f.call('/api/requests/'+str(id),client=a)['recipient_account_pending'])
  b=self.f.login('demo.global');items=self.f.call('/api/requests?box=received',client=b)['items'];self.assertEqual(items[0]['id'],id);self.assertFalse(items[0]['recipient_account_pending'])
  self.reject('/api/requests/'+str(id),client=self.f.login('demo.c'));self.reject('/api/requests/action',{'id':id,'revision':1,'action':'accept'},self.f.login('demo.c'))
 def test_no_account_recipient_later_issued_and_automatically_claimed(self):
  a,draft=self.prepare();id=self.send(a,draft,'DEMO-SAME-B')['id']
  self.modify("INSERT INTO users(username,password_hash,salt,role,active) VALUES(?,?,'','member',1)",('demo.same.b',auth_control.password_hash(PASSWORD)))
  b=self.f.login('demo.same.b');self.assertEqual(self.f.call('/api/requests?box=received',client=b)['items'][0]['id'],id)
 def test_conflicting_identity_is_not_silently_reassigned(self):
  self.modify("DELETE FROM employee_accounts WHERE employee_id IN ('DEMO-A','DEMO-C')")
  self.modify("INSERT INTO employee_accounts(employee_id,user_id,linked_by) SELECT 'DEMO-A',id,id FROM users WHERE username='demo.c'")
  self.reject('/api/auth/login',{'username':'demo.a','password':PASSWORD},status=409)
 def test_missing_official_identity_cannot_send(self):
  self.modify("DELETE FROM employee_accounts WHERE employee_id='DEMO-A'")
  self.modify("UPDATE org_employees SET saeoll_id=NULL WHERE employee_id='DEMO-A'")
  a,draft=self.prepare();self.reject('/api/requests/send',{'workspace_id':1,'draft_id':draft['id'],'recipient_employee':'DEMO-B','fingerprint':draft['edit_token']},a,status=409)

if __name__=='__main__':unittest.main()
