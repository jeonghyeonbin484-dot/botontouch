import unittest,urllib.error
from test_cloud import Fixture
class ResourceLibraryCloudTests(unittest.TestCase):
 def setUp(self):self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b')
 def tearDown(self):self.f.stop()
 def test_metadata_authentication_and_scope(self):
  self.f.call('/api/documents','가상 업무 본문은 목록에 보내지 않습니다.'.encode(),self.a,{'X-File-Name':'library-test.txt'});value=self.f.call('/api/library',client=self.a);self.assertEqual(value['total'],1);self.assertEqual(value['items'][0]['name'],'library-test.txt');self.assertFalse({'content','sources','raw'}&set(value['items'][0]));self.assertEqual(self.f.call('/api/library',client=self.b)['total'],0)
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call('/api/library')
  self.assertEqual(e.exception.code,401);e.exception.close()
 def test_owner_conversations_and_empty_library(self):
  self.f.call('/api/studio/sessions',{'workspace_id':1,'title':'가상 자료함 대화'},self.a);a=self.f.call('/api/library?kind=conversations',client=self.a);self.assertEqual(a['total'],1);self.assertEqual(a['items'][0]['title'],'가상 자료함 대화');self.assertNotIn('messages',a['items'][0]);self.assertEqual(self.f.call('/api/library?kind=conversations',client=self.b)['total'],0)
if __name__=='__main__':unittest.main()
