"""선택 삭제는 권한과 보존 조건을 분리된 가상 DB에서 검사한다."""
import json,sqlite3,unittest,urllib.error
from test_cloud import Fixture

class BulkAndHomeDeleteTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b')
 def tearDown(self):self.f.stop()
 def upload(self,text=b'Fictional source',client=None,headers=None):
  return self.f.call('/api/documents',text,client or self.a,{'X-File-Name':'fictional.txt',**(headers or {})})
 def reject(self,path,body,client=None,status=403):
  with self.assertRaises(urllib.error.HTTPError) as error:self.f.call(path,body,client or self.a)
  self.assertEqual(error.exception.code,status);error.exception.close()
 def draft(self,doc):
  d=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a);d['reviewed']=True
  return self.f.call('/api/drafts/save',d,self.a)
 def test_bulk_delete_preserves_draft_sources_and_recipient_snapshot(self):
  one=self.upload();two=self.upload(b'Another fictional source');d=self.draft(one)
  rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id']
  before=self.f.call('/api/requests/'+str(rid),client=self.b)
  items=[{'id':x['id'],'revision':1} for x in (one,two)]
  preview=self.f.call('/api/library/files/delete-preview',{'items':items},self.a);self.assertEqual(preview['draft_count'],1)
  self.assertEqual(self.f.call('/api/library/files/delete',{'items':items},self.a)['deleted'],2)
  self.assertEqual(self.f.call('/api/library',client=self.a)['total'],0)
  self.assertEqual(self.f.call('/api/requests/'+str(rid),client=self.b)['payload'],before['payload'])
  with self.f.raw('/api/library/file/raw?document_id='+str(one['id'])+'&request_id='+str(rid),client=self.b) as response:self.assertEqual(response.read(),b'Fictional source')
  db=sqlite3.connect(':memory:');db.deserialize(self.f.memory.payload)
  self.assertEqual(db.execute('SELECT count(*) FROM document_files').fetchone()[0],2)
  self.assertEqual(db.execute('SELECT deleted FROM drafts WHERE id=?',(d['id'],)).fetchone()[0],0);db.close()
 def test_stale_revision_is_atomic(self):
  one=self.upload();two=self.upload(b'Second source')
  items=[{'id':one['id'],'revision':1},{'id':two['id'],'revision':999}]
  self.reject('/api/library/files/delete',{'items':items},status=409)
  self.assertEqual(self.f.call('/api/library',client=self.a)['total'],2)
 def test_cross_workspace_and_received_items_are_blocked_atomically(self):
  one=self.upload();session=self.f.call('/api/studio/sessions',{'title':'Recipient private work'},self.b)
  two=self.upload(b'Private second source',self.b,{'X-Workspace-Id':str(session['session']['workspace_id'])})
  self.reject('/api/library/files/delete',{'items':[{'id':one['id'],'revision':1},{'id':two['id'],'revision':1}]})
  self.assertEqual(self.f.call('/api/library',client=self.a)['total'],1)
  self.reject('/api/library/files/delete',{'items':[{'id':one['id'],'revision':1}]},self.b)
  self.reject('/api/library/files/delete',{'items':[{'id':one['id'],'revision':1,'request_id':123}]},status=400)
 def test_home_draft_delete_preserves_records_and_validates_version(self):
  doc=self.upload();d=self.draft(doc);row=self.f.call('/api/workbench',client=self.a)['drafts'][0]
  self.assertTrue(row['can_delete'])
  self.reject('/api/workbench/delete-draft',{'draft_id':d['id'],'expected_fingerprint':'stale'},status=409)
  self.reject('/api/workbench/delete-draft',{'draft_id':d['id'],'expected_fingerprint':row['delete_token']},self.b)
  self.f.call('/api/workbench/delete-draft',{'draft_id':d['id'],'expected_fingerprint':row['delete_token']},self.a)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['drafts'],0)
  db=sqlite3.connect(':memory:');db.deserialize(self.f.memory.payload)
  self.assertEqual(db.execute('SELECT deleted FROM drafts WHERE id=?',(d['id'],)).fetchone()[0],1)
  self.assertGreater(db.execute('SELECT count(*) FROM draft_versions WHERE draft_id=?',(d['id'],)).fetchone()[0],0)
  self.assertEqual(db.execute('SELECT deleted FROM documents WHERE id=?',(doc['id'],)).fetchone()[0],0);db.close()
 def test_sent_draft_cannot_be_deleted(self):
  doc=self.upload();d=self.draft(doc)
  self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},self.a)
  self.reject('/api/workbench/delete-draft',{'draft_id':d['id'],'expected_fingerprint':d['edit_token']},status=409)
  self.assertEqual(self.f.call('/api/requests?box=sent',client=self.a)['pending'],1)

 def test_bulk_home_delete_and_stale_guard_are_atomic(self):
  doc=self.upload();self.draft(doc);self.draft(doc)
  rows=self.f.call('/api/workbench?kind=draft&page_size=200',client=self.a)['items']
  self.assertEqual(len(rows),2)
  selected=[{'draft_id':r['id'],'expected_fingerprint':r['delete_token']} for r in rows]
  self.reject('/api/workbench/delete-drafts',{'items':[selected[0],{**selected[1],'expected_fingerprint':'stale'}]},status=409)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['drafts'],2)
  result=self.f.call('/api/workbench/delete-drafts',{'items':selected},self.a)
  self.assertEqual(result['deleted'],2)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['drafts'],0)
  db=sqlite3.connect(':memory:');db.deserialize(self.f.memory.payload)
  self.assertEqual(db.execute('SELECT count(*) FROM drafts WHERE deleted=1').fetchone()[0],2)
  self.assertEqual(db.execute('SELECT count(*) FROM documents WHERE deleted=0').fetchone()[0],1);db.close()
 def test_bulk_home_delete_denies_outsiders_and_sent_document(self):
  doc=self.upload();one=self.draft(doc);two=self.draft(doc)
  rows=self.f.call('/api/workbench?kind=draft&page_size=200',client=self.a)['items']
  selected=[{'draft_id':r['id'],'expected_fingerprint':r['delete_token']} for r in rows]
  self.reject('/api/workbench/delete-drafts',{'items':selected},self.b)
  self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':one['id'],'fingerprint':one['edit_token'],'recipient_employee':'DEMO-B'},self.a)
  self.reject('/api/workbench/delete-drafts',{'items':selected},status=409)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['drafts'],1)
  self.assertEqual(self.f.call('/api/requests?box=sent',client=self.a)['pending'],1)
 def test_bulk_home_delete_rejects_duplicate_ids(self):
  d=self.draft(self.upload());row=self.f.call('/api/workbench',client=self.a)['drafts'][0]
  item={'draft_id':d['id'],'expected_fingerprint':row['delete_token']}
  self.reject('/api/workbench/delete-drafts',{'items':[item,item]},status=400)
  self.assertEqual(self.f.call('/api/workbench',client=self.a)['counts']['drafts'],1)
