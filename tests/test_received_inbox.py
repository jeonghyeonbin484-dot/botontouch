"""Recipient inbox contracts on isolated shared storage; never production data."""
import io,json,unittest,urllib.error,zipfile
from contextlib import closing
from urllib.parse import quote
import app,cloud_store
from test_cloud import Fixture

class ReceivedInboxTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c')
  doc=self.f.call('/api/documents','전달 당시 원문입니다.'.encode(),self.a,{'X-File-Name':'fictional.txt'})
  self.doc=doc;self.d=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a);self.d.update(title='전달한 월간 업무',reviewed=True);self.d=self.f.call('/api/drafts/save',self.d,self.a)
  self.rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.d['id'],'fingerprint':self.d['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id']
 def tearDown(self):self.f.stop()
 def inbox(self,query='',client=None):return self.f.call('/api/requests?box=received'+query,client=client or self.b)
 def detail(self):return self.f.call('/api/requests/'+str(self.rid),client=self.b)
 def reject(self,path,body=None,client=None,status=403):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(path,body,client or self.c)
  self.assertEqual(e.exception.code,status);e.exception.close()
 def test_count_semantics_and_search_do_not_change_reads(self):
  first=self.inbox('&page=1');self.assertEqual((first['unread'],first['active'],first['total'],first['pending']),(1,1,1,1))
  row=first['items'][0];self.assertEqual(row['attachment_count'],1);self.assertEqual(row['unanswered_count'],0)
  self.assertNotIn('전달 당시 원문입니다.',json.dumps(first,ensure_ascii=False));self.assertNotIn('payload',row)
  self.assertEqual(self.inbox('&q='+quote('월간'))['filtered_total'],1);self.assertEqual(self.inbox('&q=absent')['filtered_total'],0);self.assertEqual(self.inbox('&q=absent')['total'],1)
  self.assertEqual(self.inbox('&q='+quote('가상 인계자'))['filtered_total'],1)
  self.detail();self.assertEqual(self.inbox()['unread'],1)
  self.f.call('/api/requests/action',{'id':self.rid,'revision':1,'action':'view'},self.b)
  self.assertEqual((self.inbox()['unread'],self.inbox()['pending'],self.inbox()['active']),(0,1,1))
  self.assertEqual(self.inbox('&status=requested')['filtered_total'],0)
  self.f.call('/api/requests/action',{'id':self.rid,'revision':1,'action':'accept'},self.b);self.assertEqual(self.inbox()['active'],1)
  self.reject('/api/requests/action',{'id':self.rid,'revision':1,'action':'complete'},self.b)
  self.f.call('/api/requests/action',{'id':self.rid,'revision':1,'action':'complete'},self.a)
  self.assertEqual((self.inbox()['active'],self.inbox()['total']),(0,1));self.assertEqual(self.inbox('&status=completed')['filtered_total'],1)
 def test_answers_are_revision_bound_and_require_actual_recipient(self):
  self.f.call('/api/journey/question',{'request_id':self.rid,'question':'담당 일정은 언제인가요?'},self.b)
  q=self.f.call('/api/journey/questions?request_id='+str(self.rid),client=self.a)['questions'][-1]
  r=self.detail();self.assertEqual(r['unanswered_count'],1)
  body={'id':self.rid,'revision':1,'answer_token':r['answer_token']}
  self.reject('/api/requests/answers-reviewed',body,self.b,status=409);self.reject('/api/requests/answers-reviewed',body,self.a)
  self.f.call('/api/journey/answer',{'request_id':self.rid,'id':q['id'],'reply':'매월 마지막 날입니다.','state':'resolved'},self.a)
  r=self.detail();self.assertEqual(r['unanswered_count'],0);body['answer_token']=r['answer_token']
  self.f.call('/api/requests/answers-reviewed',body,self.b);self.assertTrue(self.detail()['answers_reviewed'])
  cloud_store.reset_runtime_cache();self.assertTrue(self.detail()['answers_reviewed'])
  self.f.call('/api/journey/answer',{'request_id':self.rid,'id':q['id'],'reply':'매월 마지막 근무일입니다.','state':'resolved'},self.a)
  self.assertFalse(self.detail()['answers_reviewed']);self.reject('/api/requests/answers-reviewed',body,self.b,status=409)
  self.reject('/api/requests/answers-reviewed',dict(body,revision=0),self.b,status=409)
 def test_outsider_cannot_read_document_files_questions_or_acknowledge(self):
  self.assertEqual(self.inbox(client=self.c)['total'],0)
  base='/api/requests/'+str(self.rid)
  for suffix in ('','/export.html','/export.hwpx','/export.md','/export.docx'):self.reject(base+suffix)
  file=self.detail()['files'][0];self.reject(base+'/files/'+str(file['id']))
  self.reject('/api/journey/questions?request_id='+str(self.rid))
  self.reject('/api/requests/answers-reviewed',{'id':self.rid,'revision':1,'answer_token':self.detail()['answer_token']})
  with self.f.raw(base+'/export.hwpx',client=self.b) as response:
   with zipfile.ZipFile(io.BytesIO(response.read())) as archive:self.assertIsNone(archive.testzip());self.assertIn('전달한 월간 업무',archive.read('Preview/PrvText.txt').decode())
 def test_preview_and_download_use_sent_snapshot_after_working_draft_changes(self):
  self.d['title']='나중에 변경한 작성 문서';self.d['items'][0]['text']='아직 보내지 않은 수정 내용';self.f.call('/api/drafts/save',self.d,self.a)
  with self.f.raw('/api/requests/'+str(self.rid)+'/export.html',client=self.b) as r:html=r.read().decode()
  self.assertIn('전달한 월간 업무',html);self.assertNotIn('아직 보내지 않은 수정 내용',html)
  self.assertEqual(self.inbox()['items'][0]['title'],'전달한 월간 업무')
 def test_reassignment_revokes_former_recipient_and_resets_new_receipt(self):
  old=self.detail()
  self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.d['id'],'fingerprint':self.d['edit_token'],'recipient_employee':'DEMO-C'},self.a)
  self.assertEqual(self.inbox()['total'],0);self.assertEqual(self.inbox(client=self.c)['unread'],1)
  base='/api/requests/'+str(self.rid)
  self.reject(base,client=self.b);self.reject(base+'/export.html',client=self.b);self.reject(base+'/export.hwpx',client=self.b)
  self.reject('/api/journey/questions?request_id='+str(self.rid),client=self.b)
  self.reject('/api/requests/answers-reviewed',{'id':self.rid,'revision':old['revision'],'answer_token':old['answer_token']},self.b)
  self.assertEqual(self.f.call(base,client=self.c)['revision'],2)
 def test_server_pagination_includes_requests_beyond_200(self):
  with cloud_store.database_request():
   with closing(app.connect()) as db:
    row=dict(db.execute('SELECT * FROM handover_requests WHERE id=?',(self.rid,)).fetchone());row.pop('id');row['state']='completed';columns=list(row)
    for i in range(204):
     payload=json.loads(row['payload']);payload['title']='Historical %03d'%i;row['payload']=json.dumps(payload,ensure_ascii=False)
     db.execute('INSERT INTO handover_requests('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
    db.commit()
  result=self.inbox('&page=11&page_size=20');self.assertEqual(result['total'],205);self.assertEqual(len(result['items']),5);self.assertEqual(result['unread'],1)
  result=self.inbox('&page=1&q=Historical%20000');self.assertEqual(result['filtered_total'],1);self.assertEqual(result['items'][0]['title'],'Historical 000')
  self.assertEqual(self.inbox(client=self.c)['total'],0)
  self.reject('/api/requests?box=received&page=0',client=self.b,status=400)
