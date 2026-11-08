import json
import unittest
import urllib.error

import cloud_store
from test_cloud import Fixture


class WorkbenchTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a');self.b=self.f.login('demo.b');self.c=self.f.login('demo.c')
  d=self.f.call('/api/documents','목록에 노출하지 않을 가상 원문'.encode(),self.a,{'X-File-Name':'private.txt'})
  self.one=self.f.call('/api/drafts/generate',{'document_ids':[d['id']]},self.a);self.one.update(title='가. 월간 점검',reviewed=True);self.one=self.f.call('/api/drafts/save',self.one,self.a)
  self.two=self.f.call('/api/drafts/generate',{'document_ids':[d['id']]},self.a);self.two.update(title='나. 예산 인계');self.two=self.f.call('/api/drafts/save',self.two,self.a)
 def tearDown(self):self.f.stop()
 def reject(self,path,body=None,client=None,status=403):
  with self.assertRaises(urllib.error.HTTPError) as e:self.f.call(path,body,client or self.c)
  self.assertEqual(e.exception.code,status);e.exception.close()
 def test_search_status_revision_sort_metadata_and_no_leak(self):
  first=self.f.call('/api/workbench',client=self.a)
  self.assertEqual(first['counts']['drafts'],2);self.assertEqual(first['items'][0]['id'],self.two['id'])
  self.one['title']='가. 월간 점검 수정';self.one=self.f.call('/api/drafts/save',self.one,self.a)
  latest=self.f.call('/api/workbench?sort=updated',client=self.a)
  self.assertEqual(latest['items'][0]['id'],self.one['id'])
  self.assertEqual(self.f.call('/api/workbench?status=reviewed',client=self.a)['total'],1)
  from urllib.parse import quote
  self.assertEqual(self.f.call('/api/workbench?q='+quote('예산'),client=self.a)['total'],1)
  self.assertEqual(self.f.call('/api/workbench?sort=title',client=self.a)['items'][0]['title'],self.one['title'])
  self.assertEqual(self.f.call('/api/workbench',client=self.c)['total'],0)
  self.assertNotIn('목록에 노출하지 않을 가상 원문',json.dumps(first,ensure_ascii=False));self.assertNotIn('password_hash',str(first));self.assertNotIn('payload',str(first))
  library=self.f.call('/api/library?kind=drafts&status=saved&sort=updated',client=self.a)
  self.assertEqual(library['total'],1);self.assertEqual(library['items'][0]['id'],self.one['id'])
  self.assertEqual(self.f.call('/api/library?kind=drafts&status=draft',client=self.a)['total'],1)
  self.reject('/api/workbench?sort=invalid',client=self.a,status=400)
 def test_requests_notifications_shared_persistence_and_individual_reads(self):
  rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.one['id'],'fingerprint':self.one['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id']
  received=self.f.call('/api/workbench?kind=inbox',client=self.b)
  self.assertEqual(received['counts']['received'],1);self.assertEqual(received['items'][0]['id'],rid)
  self.assertEqual(received['items'][0]['stage'],5);self.assertGreater(received['unread'],0)
  event=received['notifications'][0]['key']
  self.f.call('/api/workbench/read',{'keys':[event]},self.b)
  cloud_store.reset_runtime_cache()
  b2=self.f.login('demo.b');again=self.f.call('/api/workbench',client=b2)
  self.assertTrue(next(e for e in again['notifications'] if e['key']==event)['read'])
  self.assertFalse(next(e for e in self.f.call('/api/workbench',client=self.a)['notifications'] if e['key']==event)['read'])
  self.reject('/api/workbench/read',{'keys':[event]})
  self.f.call('/api/workbench/read',{'all':True},self.b)
  self.assertEqual(self.f.call('/api/workbench',client=self.b)['unread'],0)
  self.assertEqual(self.f.call('/api/auth/status',client=self.a)['user']['username'],'demo.a')
 def test_question_and_review_events_are_visible_only_to_participants(self):
  rid=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':self.one['id'],'fingerprint':self.one['edit_token'],'recipient_employee':'DEMO-B'},self.a)['id']
  self.f.call('/api/journey/question',{'request_id':rid,'draft_id':self.one['id'],'question':'가상 추가 질문'},self.b)
  from handover_workflow import fingerprint
  self.f.call('/api/handover/check',{'draft_id':self.one['id'],'item_index':0,'fingerprint':fingerprint(self.one['items'][0]),'state':'confirmed','note':''},self.a)
  events=self.f.call('/api/workbench',client=self.a)['notifications']
  self.assertTrue(any('질문' in e['label'] for e in events));self.assertTrue(any(e['label']=='항목 검토 완료' for e in events))
  self.assertEqual(self.f.call('/api/workbench',client=self.c)['notifications'],[])


if __name__=='__main__':unittest.main()
