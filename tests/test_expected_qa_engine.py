import unittest,io,json
from unittest.mock import patch
import gemini_engine as ai_draft
class ExpectedQAEngineTests(unittest.TestCase):
 def invoke(self,question):
  docs=[dict(id=1,name='fictional.txt',revision=1,sources=json.dumps([dict(location='1행',text='매월 가상 비품 점검')]))]
  context=dict(mode='expected_qa',draft=dict(title='가상',items=[dict(category='업무',text='가상 점검')]),existing_questions=[])
  response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(dict(summary='가상',questions=[question]))}]}}]}
  with patch.object(ai_draft,'settings',return_value={'key':'fictional-key','model':'fictional-model'}),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
   return ai_draft.generate(docs,gap_context=context)
 def question(self):return dict(question='언제 점검하나요?',reason='후임자 확인',target_index=0,source_ids=['D1-S1'],recommended_answer='매월 점검합니다.',answer_source_ids=['D1-S1'],supported=True)
 def test_supported_answer(self):self.assertTrue(self.invoke(self.question())['questions'][0]['supported'])
 def test_unknown_source_rejected(self):
  q=self.question();q['answer_source_ids']=['D99-S1']
  with self.assertRaises(ValueError):self.invoke(q)
 def test_unsupported_answer_not_invented(self):
  q=self.question();q.update(supported=False,answer_source_ids=[],recommended_answer='추측한 답변')
  self.assertIn('추가 확인 필요',self.invoke(q)['questions'][0]['recommended_answer'])
 def test_supported_requires_source(self):
  q=self.question();q['answer_source_ids']=[]
  with self.assertRaises(ValueError):self.invoke(q)
if __name__=='__main__':unittest.main()
