import copy
import io
import uuid
import unittest
import urllib.error
import zipfile
from unittest.mock import patch

from test_cloud import Fixture


class ParagraphTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b')
  doc=self.f.call('/api/documents','가상 업무 근거'.encode(),self.a,{'X-File-Name':'fictional.txt'})
  self.draft=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a)
  self.draft['items'][0]['text']='수정 대상 문단입니다.\n그대로 보존할 다음 문단입니다.\n수정 대상 문단입니다.'
  self.draft['reviewed']=True;self.draft=self.f.call('/api/drafts/save',self.draft,self.a)
  self.s=self.f.call('/api/studio/sessions',{'workspace_id':1,'draft_id':self.draft['id'],'title':'가상 문단 수정'},self.a)
  self.base='/api/studio/sessions/'+str(self.s['session']['id'])
 def tearDown(self):self.f.stop()
 def current(self):return self.f.call(self.base,client=self.a)['draft']
 def request(self):
  paper=self.f.call(self.base+'/paper',client=self.a)
  target=next(t for t in paper['targets'].values() if t['before']=='수정 대상 문단입니다.')
  return {'draft_id':self.draft['id'],'baseline':paper['baseline'],'target_id':target['id'],'text':'더 간결하게','nonce':uuid.uuid4().hex}
 def propose(self):
  body=self.request();result=self.f.call(self.base+'/paragraphs',body,self.a)
  message=next(m for m in reversed(result['messages']) if m['role']=='assistant')
  return body,message
 def reject(self,path,body,client=None,status=409):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(path,body,client or self.a)
  self.assertEqual(e.exception.code,status);e.exception.close()
 def test_approval_changes_one_span_download_and_undo_preserve_other_data(self):
  before=self.current();session_before=self.f.call(self.base,client=self.a)
  rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.draft['id'],'fingerprint':self.draft['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id']
  request_before=self.f.call('/api/requests/'+str(rid),client=self.a)
  body,message=self.propose();self.assertEqual(self.current(),before)
  # Idempotent requests cannot create a second proposal.
  same=self.f.call(self.base+'/paragraphs',body,self.a)
  self.assertEqual(len(same['messages']),2)
  result=self.f.call(self.base+'/paragraph-apply',{'message_id':message['id']},self.a)
  edit=message['result']['paragraph_edit'];after=self.current()
  self.assertEqual(after['items'][0]['text'],edit['after']+'\n그대로 보존할 다음 문단입니다.\n수정 대상 문단입니다.')
  self.assertEqual(after['items'][1:],before['items'][1:]);self.assertEqual(after['title'],before['title']);self.assertEqual(after['references'],before['references'])
  self.assertEqual(after['items'][0]['source_ids'],before['items'][0]['source_ids'])
  self.assertEqual(result['documents'],session_before['documents'])
  self.assertEqual(self.f.call('/api/requests/'+str(rid),client=self.a),request_before)
  self.f.call(self.base+'/paragraph-apply',{'message_id':message['id']},self.a)
  with self.f.raw('/api/drafts/'+str(self.draft['id'])+'/export.hwpx',client=self.a) as response:
   with zipfile.ZipFile(io.BytesIO(response.read())) as z:self.assertIn('[모의 수정]',z.read('Preview/PrvText.txt').decode())
  undone=self.f.call(self.base+'/paragraph-undo',{'message_id':message['id']},self.a)
  self.assertEqual(undone['draft']['items'],before['items'])
  self.assertEqual(undone['messages'][-1]['proposal_state'],'paragraph_reverted')
  versions=self.f.call('/api/handover/versions?draft_id='+str(self.draft['id']),client=self.a)
  self.assertIn('paragraph_applied',str(versions));self.assertIn('paragraph_undo',str(versions))
 def test_cancel_unauthorized_target_tamper_and_stale_proposal(self):
  before=self.current();body,message=self.propose()
  self.reject(self.base+'/paragraph-apply',{'message_id':message['id']},self.b,404)
  self.reject(self.base+'/apply',{'message_id':message['id']},status=405)
  self.f.call(self.base+'/paragraph-reject',{'message_id':message['id']},self.a)
  self.reject(self.base+'/paragraph-apply',{'message_id':message['id']})
  self.assertEqual(self.current(),before)
  tamper=self.request();tamper['target_id']='0'*64;self.reject(self.base+'/paragraphs',tamper)
  tamper=self.request();tamper['draft_id']+=1;self.reject(self.base+'/paragraphs',tamper)
  body,message=self.propose();changed=copy.deepcopy(self.current());changed['items'][1]['text']='다른 화면에서 새로 저장한 내용';self.f.call('/api/drafts/save',changed,self.a)
  self.reject(self.base+'/paragraph-apply',{'message_id':message['id']})
  self.assertEqual(self.current()['items'][1]['text'],'다른 화면에서 새로 저장한 내용')
 def test_failure_and_retry_keep_location_and_do_not_overwrite(self):
  body=self.request();before=self.current()
  with patch('ai_draft.generate',side_effect=ValueError('가상 AI 오류')):self.reject(self.base+'/paragraphs',body,status=400)
  self.assertEqual(self.current(),before)
  body['retry']=True;result=self.f.call(self.base+'/paragraphs',body,self.a)
  self.assertEqual(result['messages'][-1]['result']['paragraph_edit']['before'],'수정 대상 문단입니다.')
  self.assertEqual(self.current(),before)
 def test_stale_undo_refuses_to_erase_newer_changes(self):
  _,message=self.propose();self.f.call(self.base+'/paragraph-apply',{'message_id':message['id']},self.a)
  changed=self.current();changed['items'][1]['text']='되돌리기 후에도 보존할 새 변경';self.f.call('/api/drafts/save',changed,self.a)
  self.reject(self.base+'/paragraph-undo',{'message_id':message['id']})
  self.assertEqual(self.current()['items'][1]['text'],'되돌리기 후에도 보존할 새 변경')


if __name__=='__main__':unittest.main()
