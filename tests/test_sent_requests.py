"""Sender list isolation, real state, and latest transmission ordering."""
import io,json,unittest,urllib.error,zipfile
from contextlib import closing
from urllib.parse import quote
import app,cloud_store
from test_cloud import Fixture

class SentRequestsTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c')
  self.doc=self.f.call('/api/documents','전달 당시 보존할 업무 원문'.encode(),self.a,{'X-File-Name':'fictional.txt'})
  self.rid,self.d=self.send('월간 점검 업무')
 def tearDown(self):self.f.stop()
 def send(self,title):
  d=self.f.call('/api/drafts/generate',{'document_ids':[self.doc['id']]},self.a);d.update(title=title,reviewed=True);d=self.f.call('/api/drafts/save',d,self.a)
  r=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},self.a)
  return r['id'],d
 def sent(self,query='',client=None):return self.f.call('/api/requests?box=sent&page=1'+query,client=client or self.a)
 def test_sender_reads_do_not_confirm_receiver_review_and_states_are_real(self):
  initial=self.sent();self.assertEqual(initial['total'],1);row=initial['items'][0];self.assertEqual(row['state'],'requested');self.assertEqual(row['question_count'],0);self.assertFalse(row['answers_reviewed'])
  for suffix in ('','/export.html','/export.hwpx'):
   with self.f.raw('/api/requests/'+str(self.rid)+suffix,client=self.a) as r:self.assertEqual(r.status,200)
  self.assertEqual(self.sent()['items'][0]['state'],'requested');self.assertEqual(self.f.call('/api/requests?box=received',client=self.b)['unread'],1)
  self.f.call('/api/requests/action',{'id':self.rid,'revision':1,'action':'view'},self.b);self.assertEqual(self.sent()['items'][0]['state'],'reviewing')
  self.f.call('/api/journey/question',{'request_id':self.rid,'question':'보고 일정은 언제인가요?'},self.b)
  q=self.f.call('/api/journey/questions?request_id='+str(self.rid),client=self.a)['questions'][-1];self.assertEqual(self.sent()['items'][0]['unanswered_count'],1)
  self.f.call('/api/journey/answer',{'request_id':self.rid,'id':q['id'],'reply':'월말에 확인합니다.','state':'resolved'},self.a)
  row=self.sent()['items'][0];self.assertEqual(row['answered_count'],1);self.assertFalse(row['answers_reviewed'])
  self.f.call('/api/requests/answers-reviewed',{'id':self.rid,'revision':1,'answer_token':row['answer_token']},self.b);self.assertTrue(self.sent()['items'][0]['answers_reviewed'])
  self.f.call('/api/requests/action',{'id':self.rid,'revision':1,'action':'accept'},self.b);self.assertEqual(self.sent()['items'][0]['state'],'accepted');self.assertIsNone(self.sent()['items'][0]['completed_at'])
  self.f.call('/api/requests/action',{'id':self.rid,'revision':1,'action':'complete'},self.a);self.assertEqual(self.sent()['items'][0]['state'],'completed')
 def test_search_status_pagination_and_latest_revision_date(self):
  rid2,d2=self.send('예산 업무')
  with cloud_store.database_request():
   with closing(app.connect()) as db:
    db.execute("UPDATE handover_requests SET created='2026-01-01 00:00:00' WHERE id=?",(self.rid,));db.execute("UPDATE request_snapshots SET created='2026-01-01 00:00:00' WHERE request_id=?",(self.rid,));db.execute("UPDATE request_snapshots SET created='2026-02-01 00:00:00' WHERE request_id=?",(rid2,));db.commit()
  self.assertEqual(self.sent()['items'][0]['id'],rid2)
  self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.d['id'],'fingerprint':self.d['edit_token'],'recipient_employee':'DEMO-B'},self.a)
  rows=self.sent()['items'];self.assertEqual(rows[0]['id'],self.rid);self.assertEqual(rows[0]['revision'],2);self.assertNotEqual(rows[0]['requested_at'],rows[0]['created'])
  self.assertEqual(self.sent('&q='+quote('월간'))['filtered_total'],1);self.assertEqual(self.sent('&q='+quote('가상 인수자'))['filtered_total'],2)
  self.f.call('/api/requests/action',{'id':rid2,'revision':1,'action':'view'},self.b);self.assertEqual(self.sent('&status=reviewing')['filtered_total'],1)
  page=self.sent('&page_size=1');self.assertEqual(len(page['items']),1);self.assertEqual(page['filtered_total'],2)
 def test_list_document_and_files_are_participant_scoped_and_snapshots_immutable(self):
  self.assertEqual(self.sent(client=self.b)['total'],0);self.assertEqual(self.sent(client=self.c)['total'],0)
  self.d['title']='미전달 새 작업 문서';self.d['items'][0]['text']='아직 전달하지 않은 수정';self.f.call('/api/drafts/save',self.d,self.a)
  self.assertEqual(self.sent()['items'][0]['title'],'월간 점검 업무')
  with self.f.raw('/api/requests/'+str(self.rid)+'/export.hwpx',client=self.a) as r:
   with zipfile.ZipFile(io.BytesIO(r.read())) as z:text=z.read('Preview/PrvText.txt').decode();self.assertIn('월간 점검 업무',text);self.assertNotIn('아직 전달하지 않은 수정',text)
  files=self.f.call('/api/requests/'+str(self.rid),client=self.a)['files']
  for suffix in ('','/export.html','/export.hwpx','/files/'+str(files[0]['id'])):
   with self.assertRaises(urllib.error.HTTPError) as e:self.f.raw('/api/requests/'+str(self.rid)+suffix,client=self.c)
   self.assertEqual(e.exception.code,403);e.exception.close()
