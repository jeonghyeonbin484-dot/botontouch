"""Messenger privacy, scoped reads, persistence and formal question guards."""
import unittest,uuid,urllib.error,time
from test_cloud import Fixture,PASSWORD
import cloud_store

class MessengerTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c')
  doc=self.f.call('/api/documents','가상 업무 원문'.encode(),self.a,{'X-File-Name':'fixture.txt'});self.d=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a);self.d.update(title='가상 대화 업무',reviewed=True);self.d=self.f.call('/api/drafts/save',self.d,self.a)
  self.rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.d['id'],'fingerprint':self.d['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id'];self.base='/api/chat/'+str(self.rid)
 def tearDown(self):self.f.stop()
 def send(self,text,client=None,base=None):return self.f.call((base or self.base)+'/messages',{'text':text,'nonce':str(uuid.uuid4()),'room_key':str(self.rid)+':DEMO-B'},client or self.a)['id']
 def reject(self,path,body=None,client=None,status=403,headers=None):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(path,body,client or self.c,headers)
  self.assertEqual(e.exception.code,status);e.exception.close()
 def test_own_rooms_metadata_unread_and_persistence_after_relogin(self):
  mid=self.send('월말 보고 일정 확인 부탁드립니다.')
  rooms=self.f.call('/api/chat/rooms',client=self.b)['rooms'];self.assertEqual(rooms[0]['request_id'],self.rid);self.assertEqual(rooms[0]['unread'],1);self.assertEqual(rooms[0]['preview'],'월말 보고 일정 확인 부탁드립니다.');self.assertTrue(rooms[0]['workspace_title']);self.assertTrue(rooms[0]['last_message_at'])
  self.assertEqual(self.f.call('/api/chat/rooms',client=self.c)['rooms'],[])
  self.f.call(self.base+'/read',{'last_id':mid,'room_key':str(self.rid)+':DEMO-B'},self.b);self.f.call('/api/auth/logout',{},self.b);cloud_store.reset_runtime_cache();self.b=self.f.login('demo.b')
  self.assertEqual(self.f.call('/api/chat/rooms',client=self.b)['total'],0);self.assertEqual(self.f.call(self.base+'/messages',client=self.b)['messages'][0]['body'],'월말 보고 일정 확인 부탁드립니다.')
 def test_message_send_read_events_and_files_reject_outsiders(self):
  self.send('당사자 전용 대화');raw=b'%PDF-1.4\nfictional attachment'
  fid=self.f.call(self.base+'/files',raw,self.a,{'Content-Type':'application/octet-stream','X-File-Name':'fixture.pdf','X-Chat-Nonce':str(uuid.uuid4()),'X-Chat-Room-Key':str(self.rid)+':DEMO-B'})['id']
  messages=self.f.call(self.base+'/messages',client=self.a)['messages'];file_id=next(m['file_id'] for m in messages if m['id']==fid)
  for path in (self.base+'/messages',self.base+'/events',self.base+'/files/'+str(file_id)):self.reject(path)
  self.reject(self.base+'/messages',{'text':'forbidden','nonce':str(uuid.uuid4())});self.reject(self.base+'/read',{'last_id':fid})
  self.reject(self.base+'/files',raw,headers={'Content-Type':'application/octet-stream','X-File-Name':'fixture.pdf','X-Chat-Nonce':str(uuid.uuid4())})
  with self.f.raw(self.base+'/files/'+str(file_id),client=self.b) as response:self.assertEqual(response.read(),raw)
 def test_read_cursor_must_belong_to_current_room(self):
  self.send('첫 메시지');d=self.f.call('/api/drafts/generate',{'document_ids':[1]},self.a);d['reviewed']=True;d=self.f.call('/api/drafts/save',d,self.a);other=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id']
  foreign=self.f.call('/api/chat/'+str(other)+'/messages',{'text':'다른 방 메시지','nonce':str(uuid.uuid4())},self.a)['id'];last=self.send('마지막 메시지')
  self.reject(self.base+'/read',{'last_id':foreign},self.b,status=400);self.f.call(self.base+'/read',{'last_id':last},self.b)
 def test_buffered_events_finish_without_holding_shared_write_lock(self):
  self.send('실시간 갱신 확인');start=time.monotonic()
  with self.f.raw(self.base+'/events',client=self.b) as response:body=response.read().decode()
  self.assertIn('event: sync',body);self.assertLess(time.monotonic()-start,5)
 def test_reassignment_blocks_old_recipient_and_stale_sender_target(self):
  self.send('이전 인수자에게 보낸 메시지');self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.d['id'],'fingerprint':self.d['edit_token'],'recipient_employee':'DEMO-C'},self.a)
  self.reject(self.base+'/messages',client=self.b);self.reject(self.base+'/read',{'last_id':0},self.b)
  self.reject(self.base+'/messages',{'text':'old target','nonce':str(uuid.uuid4()),'room_key':str(self.rid)+':DEMO-B'},self.a,status=409)
  self.assertEqual(self.f.call(self.base+'/messages',client=self.c)['messages'],[])
 def test_formal_question_version_and_answer_conflicts_preserve_history(self):
  self.f.call('/api/journey/question',{'request_id':self.rid,'request_revision':1,'question':'보고일은 언제인가요?'},self.b)
  q=self.f.call('/api/journey/questions?request_id='+str(self.rid),client=self.a)['questions'][0]
  body={'request_id':self.rid,'request_revision':1,'id':q['id'],'reply':'월말입니다.','state':'resolved','expected_reply':'','expected_state':'open'}
  self.f.call('/api/journey/answer',body,self.a);body['reply']='덮어쓰면 안 되는 입력';self.reject('/api/journey/answer',body,self.a,status=409)
  latest=self.f.call('/api/journey/questions?request_id='+str(self.rid),client=self.b)['questions'][0];self.assertEqual(latest['reply'],'월말입니다.');self.assertGreaterEqual(len(latest['events']),2)
  self.reject('/api/journey/question',{'request_id':self.rid,'request_revision':0,'question':'stale'},self.b,status=409)
