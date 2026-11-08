"""Isolated shared-store contracts. No production data or external APIs."""
import unittest,urllib.error
from test_cloud import Fixture

class AuthoringTests(unittest.TestCase):
 def setUp(self):
  self.f=Fixture().start();self.a=self.f.login('demo.a')
  doc=self.f.call('/api/documents',b'Fictional monthly supplies checklist',self.a,{'X-File-Name':'fixture.txt'})
  self.d=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},self.a)
 def tearDown(self):self.f.stop()
 def prefs(self,action,**extra):
  return self.f.call('/api/journey/authoring',{'action':action,'workspace_id':1,'draft_id':self.d['id'],'baseline':self.d['edit_token'],**extra},self.a)
 def test_title_compare_and_swap_preserves_draft_and_metadata(self):
  ws=self.f.call('/api/workspaces',client=self.a)[0]
  self.f.call('/api/journey/authoring',{'action':'title','workspace_id':1,'previous_title':ws['title'],'title':'New fictional task'},self.a)
  with self.assertRaises(urllib.error.HTTPError) as err:self.f.call('/api/journey/authoring',{'action':'title','workspace_id':1,'previous_title':ws['title'],'title':'Stale title'},self.a)
  self.assertEqual(err.exception.code,409);err.exception.close()
  after=self.f.call('/api/workspaces',client=self.a)[0]
  for key in ('department','predecessor','successor','reference_date'):self.assertEqual(after[key],ws[key])
  self.assertEqual(self.f.call('/api/drafts',client=self.a)[0]['items'],self.d['items'])
 def test_review_is_durable_scoped_and_invalidated_by_content(self):
  result=self.prefs('review',reviewed=True,questions=[]);self.assertTrue(result['qa_reviewed'])
  other=self.f.login('demo.a');self.assertTrue(self.f.call('/api/journey/authoring?draft_id='+str(self.d['id']),client=other)['qa_reviewed'])
  self.d['reviewed']=True;self.d=self.f.call('/api/drafts/save',self.d,self.a)
  self.assertTrue(self.f.call('/api/journey/authoring?draft_id='+str(self.d['id']),client=self.a)['qa_reviewed'])
  self.d['items'][0]['text']='Edited isolated text';self.d=self.f.call('/api/drafts/save',self.d,self.a)
  self.assertFalse(self.f.call('/api/journey/authoring?draft_id='+str(self.d['id']),client=self.a)['qa_reviewed'])
 def test_recipient_explicit_confirmation_and_self_rejection(self):
  p=self.prefs('recipient',employee_id='DEMO-B',department_id='DEMO-RECEIVE',confirm=False);self.assertFalse(p['recipient']['confirmed'])
  p=self.prefs('recipient',employee_id='DEMO-B',department_id='DEMO-RECEIVE',confirm=True);self.assertTrue(p['recipient']['confirmed'])
  with self.assertRaises(urllib.error.HTTPError) as err:self.prefs('recipient',employee_id='DEMO-A',department_id='DEMO-SEND',confirm=True)
  self.assertIn(err.exception.code,(400,409));err.exception.close()
  self.assertEqual(self.f.call('/api/drafts',client=self.a)[0]['items'],self.d['items'])
 def test_qa_dispositions_preserve_question_and_history(self):
  result=self.f.call('/api/journey/qa/save',{'draft_id':self.d['id'],'question':'Fictional question?','reply':'','state':'not_applicable','included':True,'target_index':0},self.a)
  q=next(q for q in result['questions'] if q['qa_kind']=='expected');self.assertEqual(q['state'],'not_applicable');self.assertFalse(q['qa_included'])
  result=self.f.call('/api/journey/qa/save',{'draft_id':self.d['id'],'id':q['id'],'revision':q['qa_revision'],'question':q['question'],'reply':'Later','state':'deferred','included':True,'target_index':0},self.a)
  q=result['questions'][0];self.assertEqual(q['state'],'deferred');self.assertGreaterEqual(len(q['events']),2)
  with self.assertRaises(urllib.error.HTTPError) as err:self.prefs('review',reviewed=True,questions=[])
  self.assertEqual(err.exception.code,409);err.exception.close()
 def test_authoring_access_and_stale_document_are_rejected(self):
  outsider=self.f.login('demo.c')
  with self.assertRaises(urllib.error.HTTPError) as err:self.f.call('/api/journey/authoring?draft_id='+str(self.d['id']),client=outsider)
  self.assertEqual(err.exception.code,403);err.exception.close()
  stale=self.d['edit_token'];self.d['items'][0]['text']='New content';self.d=self.f.call('/api/drafts/save',self.d,self.a)
  with self.assertRaises(urllib.error.HTTPError) as err:self.prefs('recipient',baseline=stale,employee_id='DEMO-B',department_id='DEMO-RECEIVE',confirm=True)
  self.assertEqual(err.exception.code,409);err.exception.close()
