import unittest,sys,io,json,os,urllib.error
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_cloud import Fixture,CloudTests
import gemini_transport,gemini_engine

def error(code,status):return urllib.error.HTTPError('https://generativelanguage.googleapis.com/test',code,'error',{},io.BytesIO(json.dumps({'error':{'code':code,'status':status,'message':'가상 오류'}}).encode()))
class TransportTests(unittest.TestCase):
 def test_only_503_unavailable_retried_twice(self):
  with patch('urllib.request.urlopen',side_effect=[error(503,'UNAVAILABLE'),error(503,'UNAVAILABLE'),io.BytesIO(b'{"candidates":[]}')]) as call,patch('time.sleep') as sleep:
   _,meta=gemini_transport.generate_content('fictional-key','gemini-fictional',{});self.assertEqual(call.call_count,3);self.assertEqual(sleep.call_count,2);self.assertEqual(meta['retries'],2)
 def test_auth_quota_and_syntax_errors_never_retried(self):
  for code in (400,401,403,404,429,500):
   with self.subTest(code=code),patch('urllib.request.urlopen',side_effect=error(code,'TEST_ERROR')) as call,patch('time.sleep') as sleep:
    with self.assertRaises(gemini_transport.GeminiTransportError):gemini_transport.generate_content('fictional-key','gemini-fictional',{})
    self.assertEqual(call.call_count,1);sleep.assert_not_called()
 def test_unknown_html_503_is_not_retried(self):
  e=urllib.error.HTTPError('https://generativelanguage.googleapis.com/test',503,'error',{},io.BytesIO(b'<html>proxy error</html>'))
  with patch('urllib.request.urlopen',side_effect=e) as call:
   with self.assertRaises(gemini_transport.GeminiTransportError):gemini_transport.generate_content('fictional-key','gemini-fictional',{})
   self.assertEqual(call.call_count,1)
 def test_provider_message_does_not_leak_key(self):
  e=urllib.error.HTTPError('https://generativelanguage.googleapis.com/test',403,'error',{},io.BytesIO(b'{"error":{"status":"DENIED","message":"fictional-key"}}'))
  with patch('urllib.request.urlopen',side_effect=e):
   try:gemini_transport.generate_content('fictional-key','gemini-fictional',{})
   except gemini_transport.GeminiTransportError as e:self.assertNotIn('fictional-key',json.dumps(e.provider_error))

class RestrictedVerificationTests(unittest.TestCase):
 setUp=CloudTests.setUp
 tearDown=CloudTests.tearDown
 reject=CloudTests.reject
 def test_member_and_anonymous_cannot_trigger_live(self):
  self.reject('/api/demo/gemini-verify',{'action':'draft'},self.f.login('demo.a'))
  self.reject('/api/demo/gemini-verify',{'action':'draft'},status=401)
 def test_disabled_and_arbitrary_input_blocked(self):
  admin=self.f.login('demo.admin');self.reject('/api/demo/gemini-verify',{'action':'draft'},admin)
  with patch.dict(os.environ,{'GEMINI_VERIFY_ENABLED':'true','GEMINI_VERIFY_RUN_ID':'fictional'}),patch.object(gemini_engine,'generate') as call:
   self.reject('/api/demo/gemini-verify',{'action':'draft','text':'not allowed'},admin,status=400);call.assert_not_called()
 def test_completed_action_is_cached_without_second_model_call(self):
  admin=self.f.login('demo.admin')
  with patch.dict(os.environ,{'GEMINI_VERIFY_ENABLED':'true','GEMINI_VERIFY_RUN_ID':'fictional','GEMINI_VERIFY_API_KEY':'fictional-key','GEMINI_VERIFY_MODEL':'gemini-fictional'}),patch.object(gemini_engine,'generate',return_value={'mode':'live','model':'gemini-fictional','items':[],'references':{}}) as call:
   first=self.f.call('/api/demo/gemini-verify',{'action':'draft'},admin);second=self.f.call('/api/demo/gemini-verify',{'action':'draft'},admin);self.assertEqual(first['status'],'PASS');self.assertTrue(second['cached']);self.assertEqual(call.call_count,1)

if __name__=='__main__':unittest.main()
