import unittest,urllib.error,sqlite3
from test_cloud import Fixture
class SentDeleteTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.rows=[]
  doc=self.f.call('/api/documents',b'Fictional source',self.a,{'X-File-Name':'fictional.txt'})
  for index in range(3):
   d=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a);d.update(title='Fictional '+str(index),reviewed=True);d=self.f.call('/api/drafts/save',d,self.a)
   rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id'];self.rows.append({'id':rid,'revision':1})
 def tearDown(self):self.f.stop()
 def reject(self,items,client,status):
  with self.assertRaises(urllib.error.HTTPError) as error:self.f.call('/api/requests/delete-sent',{'items':items},client)
  self.assertEqual(error.exception.code,status);error.exception.close()
 def test_only_sender_list_hidden_and_recipient_can_still_process(self):
  self.reject(self.rows,self.b,403)
  self.f.call('/api/requests/delete-sent',{'items':self.rows[:1]},self.a)
  self.assertEqual(self.f.call('/api/requests?box=sent',client=self.a)['total'],2)
  self.assertEqual(self.f.call('/api/requests?box=received',client=self.b)['total'],3)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['drafts'],0)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['sent'],2)
  self.f.call('/api/requests/action',{**self.rows[0],'action':'accept'},self.b)
  self.f.call('/api/requests/action',{**self.rows[0],'action':'complete'},self.a)
  self.f.call('/api/requests/delete-sent',{'items':self.rows[1:]},self.a)
  self.assertEqual(self.f.call('/api/requests?box=sent',client=self.f.login('demo.a'))['total'],0)
  db=sqlite3.connect(':memory:');db.deserialize(self.f.memory.payload)
  self.assertEqual(db.execute('SELECT count(*) FROM handover_requests').fetchone()[0],3)
  self.assertEqual(db.execute('SELECT count(*) FROM request_files').fetchone()[0],3)
  self.assertGreater(db.execute('SELECT count(*) FROM request_history').fetchone()[0],3);db.close()
 def test_entire_selection_validated_before_hiding(self):
  self.reject([self.rows[0],{**self.rows[1],'revision':99}],self.a,409)
  self.reject([self.rows[0],{'id':999999,'revision':1}],self.a,403)
  self.reject([self.rows[0],self.rows[0]],self.a,400)
  self.assertEqual(self.f.call('/api/requests?box=sent',client=self.a)['total'],3)
