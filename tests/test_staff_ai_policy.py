import unittest,os,json
from unittest.mock import patch
from test_cloud import Fixture
import staff_ai_policy,ai_draft,gemini_verification
class StaffPolicyTests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'BATON_STAFF_AI_MODE':'live','BATON_STAFF_FICTIONAL_ALLOWED':'true','BATON_STAFF_AI_TEST_USERS':'demo.a,demo.global','GEMINI_API_KEY':'fictional-unit-key','GEMINI_MODEL':'gemini-3.1-flash-lite'});self.env.start();self.docs=gemini_verification.documents();self.user={'id':1,'username':'demo.a'}
 def tearDown(self):self.env.stop()
 def test_normal_staff_not_in_legacy_test_allowlist(self):
  actor={'id':2832,'username':'fictional.normal.staff','role':'member','active':True,'must_change_password':False}
  docs,_=staff_ai_policy.authorize(self.docs,actor,None);self.assertEqual(len(docs),3)
 def test_incomplete_or_disabled_identity_still_blocked(self):
  for extra in [{'active':False},{'must_change_password':True},{'id':True},{'id':0}]:
   with self.assertRaises(staff_ai_policy.PolicyError):staff_ai_policy.authorize(self.docs,{**self.user,**extra},None)
 def test_originals_keep_uploaded_ids(self):
  self.docs[0]['id']=314;docs,_=staff_ai_policy.authorize(self.docs,self.user,None);self.assertEqual(docs[0]['id'],314)
 def test_changed_sources_block_before_network(self):
  sources=json.loads(self.docs[0]['sources']);sources[0]['text']='not approved';self.docs[0]['sources']=json.dumps(sources)
  with patch('gemini_engine.generate') as call:
   with self.assertRaises(staff_ai_policy.PolicyError):ai_draft.generate(self.docs,actor=self.user)
   call.assert_not_called()
 def test_identity_question_and_environment(self):
  for user,q in [(None,None),({'username':'demo.c'},None),(self.user,'private question')]:
   with self.assertRaises(staff_ai_policy.PolicyError):staff_ai_policy.authorize(self.docs,user,q)
  with patch.dict(os.environ,{'BATON_STAFF_FICTIONAL_ALLOWED':'false'}):
   with self.assertRaises(staff_ai_policy.PolicyError):staff_ai_policy.authorize(self.docs,self.user,None)
 def test_no_fallback_on_live_failure(self):
  with patch('staff_ai_policy.generate',side_effect=ValueError('failed')),patch('mock_ai.generate') as mock:
   with self.assertRaises(ValueError):ai_draft.generate(self.docs,actor=self.user)
   mock.assert_not_called()
 def test_mock_preserved(self):
  with patch.dict(os.environ,{'BATON_STAFF_AI_MODE':'mock'}),patch('gemini_engine.generate') as call:
   self.assertEqual(ai_draft.generate(self.docs)['mode'],'mock');call.assert_not_called()
