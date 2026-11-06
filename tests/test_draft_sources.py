import json,unittest,io
from unittest.mock import patch
import gemini_engine,ai_diagnostics
SECTIONS=('담당 업무 개요','주요 업무 및 추진 현황','월별·정기 업무 일정','진행 중인 현안 및 향후 조치사항','협의 부서 및 담당자','후임자 유의사항','전임자 확인이 필요한 사항')
class DraftSourceTests(unittest.TestCase):
 def generate(self,source_ids,text='가상 교육을 준비합니다.'):
  docs=[{'id':527,'name':'가상.hwpx','sources':json.dumps([{'location':'1문단','text':'3월 가상 교육 준비'}]),'revision':1}]
  items=[{'category':s,'text':text,'source_ids':list(source_ids)} for s in SECTIONS]
  response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'title':'가상 업무','items':items})}]}}]}
  with patch('gemini_transport.generate_content',return_value=(response,{'http_status':200})) as call:
   result=gemini_engine.generate(docs,config={'key':'fictional-only','model':'gemini-3.1-flash-lite'})
   self.assertEqual(call.call_args.args[2]['generationConfig']['responseJsonSchema']['properties']['items']['items']['properties']['source_ids']['items']['enum'],['D527-S1'])
   return result
 def test_non_contiguous_database_ids_are_preserved(self):
  result=self.generate(['D527-S1']);self.assertEqual(result['items'][0]['source_ids'],['D527-S1']);self.assertEqual(result['references']['D527-S1']['document_id'],527)
 def test_safe_display_wrappers_only(self):self.assertEqual(self.generate([' [D527-S1] ','D527-S1'])['items'][0]['source_ids'],['D527-S1'])
 def test_no_citation_is_review_required_not_unknown_source_error(self):
  item=self.generate([],'자료에 없습니다.')['items'][0];self.assertTrue(item['source_check_required']);self.assertIn('전임자 확인 필요',item['text']);self.assertEqual(item['source_ids'],[])
 def test_fabricated_ids_not_reassigned_or_dropped(self):
  with self.assertRaises(gemini_engine.DraftSourceError) as raised:self.generate(['D1-S1'])
  self.assertEqual(raised.exception.http_status,502);self.assertEqual(raised.exception.reason,'unknown_id')
 def test_model_validation_error_diagnostics_are_safe(self):
  err=gemini_engine.DraftSourceError('AI_SOURCE_ID_MISMATCH','안전한 안내','unknown_id',2)
  with patch('sys.stderr',new=io.StringIO()) as log:result=ai_diagnostics.payload(err,'generate')
  self.assertEqual(result['origin'],'ai_validation');self.assertEqual(result['upstream_status'],200);self.assertNotIn('references',log.getvalue());self.assertNotIn('text',log.getvalue())
 def test_saved_document_validation_is_not_relaxed(self):
  with self.assertRaises(ValueError):gemini_engine.validate_draft({'title':'기존','items':[{'category':'개요','text':'검토하지 않은 문장','source_ids':[]}]},{})
if __name__=='__main__':unittest.main()
