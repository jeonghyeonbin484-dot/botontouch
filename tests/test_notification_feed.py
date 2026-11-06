import unittest,uuid,time
from test_cloud import Fixture,PASSWORD
class CloudNotificationTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c');doc=self.f.call('/api/documents','가상 사무용품 점검'.encode(),self.a,{'X-File-Name':'fictional.txt'});draft=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a);draft['reviewed']=True;draft=self.f.call('/api/drafts/save',draft,self.a);self.rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':draft['id'],'recipient_employee':'DEMO-B','fingerprint':draft['edit_token']},self.a)['id']
 def tearDown(self):self.f.stop()
 def send(self):return self.f.call('/api/chat/'+str(self.rid)+'/messages',{'text':'가상 새 알림','nonce':str(uuid.uuid4())},self.a)['id']
 def test_feed_is_private_and_own_messages_excluded(self):
  cursor=self.f.call('/api/chat/notifications',client=self.b)['cursor'];mid=self.send();r=self.f.call('/api/chat/notifications?after='+str(cursor),client=self.b);self.assertEqual(r['total'],1);self.assertEqual(r['notifications'][0]['id'],mid);self.assertEqual(self.f.call('/api/chat/notifications?after=0',client=self.a)['notifications'],[]);self.assertEqual(self.f.call('/api/chat/notifications?after=0',client=self.c)['notifications'],[])
 def test_vercel_style_sse_completes_without_holding_transaction(self):
  self.send();start=time.monotonic()
  with self.f.raw('/api/chat/notifications/events?after=0',client=self.b) as response:raw=response.read().decode()
  self.assertIn('event: notifications',raw);self.assertIn('retry: 5000',raw);self.assertLess(time.monotonic()-start,5)
 def test_server_read_status_survives_relogin_and_cache_reset(self):
  mid=self.send();self.f.call('/api/chat/'+str(self.rid)+'/read',{'last_id':mid},self.b);self.f.call('/api/auth/logout',{},self.b);__import__('cloud_store').reset_runtime_cache();b=self.f.login('demo.b');self.assertEqual(self.f.call('/api/chat/notifications?after=0',client=b)['total'],0)
if __name__=='__main__':unittest.main()
