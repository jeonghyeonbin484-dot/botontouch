import unittest,json,sys
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_cloud import Fixture,CloudTests
import app,source_evidence,ai_draft,cloud_store

class EvidenceTests(unittest.TestCase):
 setUp=CloudTests.setUp
 tearDown=CloudTests.tearDown
 reject=CloudTests.reject
 prepare=CloudTests.prepare
 def test_rules_retain_real_locations_and_conflicting_dates(self):
  refs={'D1-S1':{'name':'가상.pdf','location':'2페이지','text':'일정: 가상 교육 / 2027-03-12'},'D2-S15':{'name':'가상.xlsx','location':'일정관리 · 15행','text':'일정: 가상 교육 / 2027-03-19'}}
  result=source_evidence.analysis(refs);self.assertEqual(len(result['conflicts']),1);self.assertEqual(result['conflicts'][0]['source_ids'],['D1-S1','D2-S15']);self.assertEqual({c['month'] for c in result['calendar']},{3});self.assertEqual(result['references'],refs)
 def test_fabricated_reference_and_unfounded_fact_are_rejected(self):
  for item in [{'category':'일정','text':'3월 확정','source_ids':['invented']},{'category':'일정','text':'3월 확정','source_ids':[]}]:
   with self.assertRaises(ValueError):ai_draft.validate_draft({'title':'가상','items':[item]},{})
  value=ai_draft.validate_draft({'title':'가상','items':[{'category':'확인','text':'자료에서 확인되지 않음','source_ids':[]}]},{})
  self.assertEqual(value['items'][0]['source_ids'],[])
 def test_saved_edit_preserves_server_reference_and_marks_recheck(self):
  a,d=self.prepare();refs=d['references'];d['items'][0]['text']='가상 수정 문장';d['references']={'fabricated':{'text':'허위'}};saved=self.f.call('/api/drafts/save',d,a);self.assertEqual(saved['references'],refs);self.assertTrue(saved['items'][0]['source_check_required'])
 def test_request_qa_uses_immutable_sources_and_denies_other_staff(self):
  a=self.f.login('demo.a');doc=self.f.call('/api/documents','가상 3월에는 드론 장비를 점검합니다.'.encode(),a,{'X-File-Name':'demo.txt'});d=self.f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);d['reviewed']=True;d=self.f.call('/api/drafts/save',d,a)
  request=self.f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'recipient_employee':'DEMO-B','fingerprint':d['edit_token']},a)['id'];b=self.f.login('demo.b');c=self.f.login('demo.c')
  self.reject('/api/evidence/analysis?request_id='+str(request),client=c)
  self.reject('/api/evidence/ask',{'request_id':request,'question':'3월 업무는?'},c)
  result=self.f.call('/api/evidence/ask',{'request_id':request,'question':'3월 업무는?'},b);self.assertEqual(result['mode'],'mock');self.assertTrue(result['source_ids']);self.assertIn('드론 장비',result['answer']);self.assertTrue(all(id in result['references'] for id in result['source_ids']))
  self.assertEqual(self.f.call('/api/evidence/analysis?request_id='+str(request),client=b)['references'],d['references'])

if __name__=='__main__':unittest.main()
