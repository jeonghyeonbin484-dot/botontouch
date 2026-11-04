import unittest,json
from unittest.mock import patch
from test_cloud import Fixture
import gemini_engine,source_evidence
SECTIONS=('담당 업무 개요','주요 업무 및 추진 현황','월별·정기 업무 일정','진행 중인 현안 및 향후 조치사항','협의 부서 및 담당자','후임자 유의사항','전임자 확인이 필요한 사항')
class ReadableAITests(unittest.TestCase):
 def generate(self,items):
  docs=[{'id':3,'name':'가상.pdf','sources':json.dumps([{'location':'1페이지','text':'가상 드론 업무'}]),'revision':1}]
  value={'title':'업무 인수인계서','items':items};response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}
  with patch('gemini_transport.generate_content',return_value=(response,{'http_status':200})) as call:
   result=gemini_engine.generate(docs,config={'key':'fictional-key','model':'gemini-3.1-flash-lite'});payload=call.call_args.args[2];self.assertIn('파일별 요약이나 문단별 발췌 목록은 최종 결과로 내지 마라',payload['systemInstruction']['parts'][0]['text']);return result
 def test_exact_seven_sections_no_legacy_append(self):
  items=[{'category':s,'text':'자료에서 확인되지 않음 · 전임자 확인 필요','source_ids':[]} for s in reversed(SECTIONS)];result=self.generate(items);self.assertEqual(tuple(x['category'] for x in result['items']),SECTIONS);self.assertEqual(result['references']['D3-S1']['location'],'1페이지')
 def test_duplicate_sections_fail_without_saving(self):
  items=[{'category':SECTIONS[0],'text':'자료에서 확인되지 않음','source_ids':[]} for _ in range(7)]
  with self.assertRaises(ValueError):self.generate(items)
 def test_old_categories_remain_valid_for_saved_documents(self):
  value={'title':'기존 문서','items':[{'category':'정기적으로 해야 할 업무','text':'자료에서 확인되지 않음','source_ids':[]}]};self.assertEqual(gemini_engine.validate_draft(value,{})['items'][0]['category'],'정기적으로 해야 할 업무')
