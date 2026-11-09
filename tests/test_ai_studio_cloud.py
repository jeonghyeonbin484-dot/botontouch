import unittest,uuid,urllib.error
from test_cloud import Fixture
class StudioCloudTests(unittest.TestCase):
 def setUp(self):self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.s=self.f.call('/api/studio/sessions',{'title':'가상 대화형 작성'},self.a);self.base='/api/studio/sessions/'+str(self.s['session']['id'])
 def tearDown(self):self.f.stop()
 def test_cloud_roundtrip_nonce_approval_qa_and_acl(self):
  payload={'mode':'draft','text':'가상 비품 업무를 작성해 주세요.','nonce':uuid.uuid4().hex};result=self.f.call(self.base+'/messages',payload,self.a);self.assertIsNone(result['draft']);self.assertEqual(result['messages'][-1]['result']['mode'],'mock');same=self.f.call(self.base+'/messages',payload,self.a);self.assertEqual(len(result['messages']),len(same['messages']));saved=self.f.call(self.base+'/apply',{'message_id':result['messages'][-1]['id']},self.a);self.assertIsNotNone(saved['draft']);self.assertFalse(saved['draft']['reviewed']);self.assertEqual(self.f.call(self.base,client=self.a)['draft']['id'],saved['draft']['id'])
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(self.base,client=self.b)
  self.assertEqual(e.exception.code,404);e.exception.close()
 def test_bad_format_never_calls_or_changes_document(self):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(self.base+'/messages',{'mode':'other','text':'가상','nonce':uuid.uuid4().hex},self.a)
  self.assertEqual(e.exception.code,400);e.exception.close();self.assertEqual(self.f.call(self.base,client=self.a)['messages'],[])
if __name__=='__main__':unittest.main()
