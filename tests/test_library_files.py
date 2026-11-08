import unittest,urllib.error
from test_cloud import Fixture

class LibraryFilesTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c')
 def tearDown(self):self.f.stop()
 def upload(self,text=b'Fictional monthly task',name='task.txt',client=None):return self.f.call('/api/documents',text,client or self.a,{'X-File-Name':name})
 def reject(self,path,client,body=None,status=403):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(path,body,client)
  self.assertEqual(e.exception.code,status);e.exception.close()
 def prepare(self):
  doc=self.upload();draft=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a);draft['reviewed']=True;draft=self.f.call('/api/drafts/save',draft,self.a)
  rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':draft['id'],'recipient_employee':'DEMO-B','fingerprint':draft['edit_token']},self.a)['id'];return doc,draft,rid
 def test_original_privacy_duplicate_and_revision(self):
  doc=self.upload();duplicate=self.upload(name='same-content.txt');self.assertEqual(duplicate['id'],doc['id']);self.assertTrue(duplicate['duplicate']);self.assertEqual(self.f.call('/api/library',client=self.a)['total'],1)
  query='?document_id='+str(doc['id'])
  for endpoint in ['file','file/raw','file/impact']:self.reject('/api/library/'+endpoint+query,self.b)
  with self.f.raw('/api/library/file/raw'+query,client=self.a) as r:self.assertEqual(r.read(),b'Fictional monthly task')
  self.f.call('/api/documents',b'New revision',self.a,{'X-File-Name':'task.txt','X-Replace-Id':str(doc['id'])})
  self.reject('/api/manage/delete',self.a,{'type':'documents','id':doc['id'],'expected_revision':1},409)
  self.assertEqual(self.f.call('/api/library/file'+query,client=self.a)['revision'],2)
 def test_received_snapshot_reuse_and_soft_delete_preserve_history(self):
  doc,draft,rid=self.prepare();key='?document_id='+str(doc['id'])+'&request_id='+str(rid);snapshot=self.f.call('/api/requests/'+str(rid),client=self.b)['payload']
  items=self.f.call('/api/library?origin=received',client=self.b)['items'];self.assertEqual(len(items),1);self.assertEqual(items[0]['request_id'],rid)
  self.reject('/api/library/file'+key,self.c);self.reject('/api/library/file/impact'+key,self.b)
  impact=self.f.call('/api/library/file/impact?document_id='+str(doc['id']),client=self.a);self.assertEqual(len(impact['drafts']),1);self.assertEqual(impact['requests'],1)
  self.f.call('/api/manage/delete',{'type':'documents','id':doc['id'],'expected_revision':1},self.a)
  with self.f.raw('/api/library/file/raw'+key,client=self.b) as r:self.assertEqual(r.read(),b'Fictional monthly task')
  created=self.f.call('/api/studio/sessions',{'title':'Recipient work'},self.b);wid=created['session']['workspace_id'];body={'workspace_id':wid,'items':[{'document_id':doc['id'],'request_id':rid}]}
  reused=self.f.call('/api/library/reuse',body,self.b);self.assertEqual(self.f.call('/api/library/reuse',body,self.b),reused)
  self.f.call('/api/studio/sessions/'+str(created['session']['id'])+'/documents',reused,self.b)
  self.assertEqual(self.f.call('/api/requests/'+str(rid),client=self.b)['payload'],snapshot)
  self.f.call('/api/auth/logout',{},self.b);self.b=self.f.login('demo.b');self.assertEqual(len(self.f.call('/api/studio/sessions/'+str(created['session']['id']),client=self.b)['documents']),1)
 def test_reuse_targets_and_filters_enforce_workspace_access(self):
  doc=self.upload();self.reject('/api/library/reuse',self.b,{'workspace_id':1,'items':[{'document_id':doc['id']}]});self.reject('/api/library/targets?workspace_id=1',self.b)
  self.assertEqual(self.f.call('/api/library?format=pdf',client=self.a)['total'],0);self.assertEqual(self.f.call('/api/library?format=txt&q=task',client=self.a)['total'],1)
  self.reject('/api/library?format=exe',self.a,status=400)
  self.reject('/api/library/file?document_id='+str(doc['id']),self.f.client(),status=401)
