import os,json,unittest
from unittest.mock import patch
import ai_draft,material_transmission_policy
class MaterialPolicyTests(unittest.TestCase):
 def docs(self,text):return [{'id':1,'name':'가상업무.hwpx','sources':json.dumps([{'text':text,'location':'1문단'}])}]
 def test_normal_business_text_allowed(self):material_transmission_policy.check(self.docs('3월 드론 교육계획을 검토합니다. 담당 부서 확인 필요.'))
 def test_identifier_and_secret_blocked(self):
  for text in ['가상 900101-1234567','가상 010-1234-5678','example@example.test','password: fictional-secret']:
   with self.assertRaises(ai_draft.AIServiceError):material_transmission_policy.check(self.docs(text))
 def test_approval_required_before_transport(self):
  with patch.dict(os.environ,{'AI_MODE':'live','BATON_AI_DATA_SCOPE':'approved-materials','GEMINI_API_KEY':'fictional','GEMINI_MODEL':'gemini-3.1-flash-lite','AI_EXTERNAL_TRANSMISSION_ALLOWED':'true','AI_APPROVED_WRITING_ALLOWED':'true','BATON_AI_APPROVED_MATERIALS':'true','AI_APPROVAL_REFERENCE':''}),patch('gemini_engine.generate') as call:
   with self.assertRaises(ai_draft.AIServiceError):ai_draft.generate(self.docs('가상 업무'),actor={'id':2,'username':'fictional.staff'})
   call.assert_not_called()
 def test_sensitive_content_not_sent_even_with_approval(self):
  with patch.dict(os.environ,{'AI_MODE':'live','BATON_AI_DATA_SCOPE':'approved-materials','GEMINI_API_KEY':'fictional','GEMINI_MODEL':'gemini-3.1-flash-lite','AI_EXTERNAL_TRANSMISSION_ALLOWED':'true','AI_APPROVED_WRITING_ALLOWED':'true','BATON_AI_APPROVED_MATERIALS':'true','AI_APPROVAL_REFERENCE':'fictional-unit-only'}),patch('gemini_engine.generate') as call:
   with self.assertRaises(ai_draft.AIServiceError):ai_draft.generate(self.docs('가상 010-1234-5678'),actor={'id':2,'username':'fictional.staff'})
   call.assert_not_called()
if __name__=='__main__':unittest.main()
