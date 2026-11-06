import unittest,json
from test_cloud import Fixture
class ExpectedQACloudTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c')
  d=self.f.call('/api/documents','매월 가상 비품 점검'.encode(),self.a,{'X-File-Name':'fictional.txt'});self.draft=self.f.call('/api/drafts/generate',{'document_ids':[d['id']]},self.a)
 def tearDown(self):self.f.stop()
 def generate(self):return self.f.call('/api/journey/qa/generate',{'draft_id':self.draft['id'],'fingerprint':self.draft['edit_token']},self.a)
 def test_mock_recommendation_and_no_overwrite(self):
  result=self.generate();self.assertEqual(result['mode'],'mock');self.assertTrue(result['questions']);self.assertEqual(result['questions'][0]['reply'],'');self.assertEqual(self.f.call('/api/drafts',client=self.a)[0]['items'],self.draft['items'])
 def test_save_and_request_delivers_qa(self):
  q=self.generate()['questions'][0];self.f.call('/api/journey/qa/save',dict(draft_id=self.draft['id'],id=q['id'],revision=q['qa_revision'],question=q['question'],reply='가상 확인 답변',included=True,target_index=0),self.a);self.draft['reviewed']=True;d=self.f.call('/api/drafts/save',self.draft,self.a);rid=self.f.call('/api/requests/send',dict(workspace_id=1,draft_id=d['id'],recipient_employee='DEMO-B',fingerprint=d['edit_token']),self.a)['id'];questions=self.f.call('/api/journey/questions?request_id='+str(rid),client=self.b)['questions'];self.assertTrue(any(q['reply']=='가상 확인 답변' for q in questions))
 def test_other_staff_cannot_generate(self):
  import urllib.error
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call('/api/journey/qa/generate',dict(draft_id=self.draft['id'],fingerprint=self.draft['edit_token']),self.c)
  self.assertIn(e.exception.code,[403,404]);e.exception.close()
if __name__=='__main__':unittest.main()
