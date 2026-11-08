"""Revised export layout never mutates stored handover data."""
import copy
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET

import export_hwpx
import report_content
import report_document
import report_export
from test_document_preview import Response


LONG_BODY='시민지원과 행정지원팀 서무 담당자로서 복무 및 초과근무 관리, 예산 지출 보조, 공문 배부, 회의 지원, 물품 관리 업무를 수행합니다.'
LONG_PLAN='내부 시스템을 활용하여 휴가 및 출장 등 복무 내역을 점검하고, 매일 오전 접수문서 분류·배부와 미처리 공문을 관리합니다. 또한, 매월 초 전월분 초과근무 내역을 취합·점검하고 매월 말 소모품 재고 및 예산 집행 현황을 확인하는 업무를 지속적으로 수행하고 있습니다.'


def example_draft():
 return {'title':'2026년 서무 인수인계서','reviewed':True,'workspace':{'department':'가상 행정지원팀','predecessor':'가상 인계자','successor':'가상 인수자'},'items':[
  {'category':'담당업무 현황','text':LONG_BODY,'source_ids':[]},
  {'category':'주요 업무계획 및 진행사항','text':LONG_PLAN,'source_ids':[]},
  {'category':'주요 미결사항','text':'납품 확인 전 지급 요청을 해서는 안 됩니다.','source_ids':[]},
  {'category':'주요 일정 및 실무 노하우','text':'매월 20일까지 1,500,000원 집행 현황 점검.','source_ids':[]},
  {'category':'관련 문서 및 참고자료','text':'삭제할 참고자료 목록','source_ids':[]},
  {'category':'인계자·인수자 확인','text':'삭제할 확인란','source_ids':[]},
  {'category':'업무 인계·인수 요약서','text':'삭제할 요약 내용','source_ids':[]}],
  'report_documents':[{'id':1,'name':'삭제할 첨부 목록.hwpx'}],'references':{},
  'gap_review':{'questions':[{'qa_kind':'expected','qa_included':True,'question':'매월 초 해야 할 업무는?','recommended_answer':'전월분 초과근무 내역을 취합·점검합니다.'},
   {'qa_kind':'expected','qa_included':False,'question':'제외된 질문','recommended_answer':'제외된 답변'}]}}


class RevisedFormatTests(unittest.TestCase):
 def test_six_sections_overview_bullets_and_question_answer_order(self):
  draft=example_draft();before=copy.deepcopy(draft);model=export_hwpx.output_model(draft)
  headings=[b for b in model['blocks'] if b['kind']=='heading']
  self.assertEqual([b['number'] for b in headings],list(map(str,range(1,7))))
  self.assertEqual([b['text'] for b in headings],report_document.SECTIONS)
  blocks=model['blocks'];start=blocks.index(headings[0])+1;end=blocks.index(headings[1])
  self.assertTrue(all(b['text'].startswith('○ ') for b in blocks[start:end]))
  question=next(i for i,b in enumerate(blocks) if b['text']=='1. 매월 초 해야 할 업무는?')
  self.assertEqual(blocks[question+1]['text'],'- AI 추천 답변 · 확인 필요: 전월분 초과근무 내역을 취합·점검합니다.')
  self.assertEqual(draft,before)

 def test_hwpx_xml_text_and_every_preview_use_same_revised_content(self):
  draft=example_draft();before=copy.deepcopy(draft)
  model=export_hwpx.output_model(draft)
  with zipfile.ZipFile(io.BytesIO(export_hwpx.build(draft))) as z:
   text=z.read('Preview/PrvText.txt').decode()
   section=ET.fromstring(z.read('Contents/section0.xml'))
   xml_text=''.join(section.itertext())
   self.assertIsNone(z.testzip())
   for block in model['blocks']:self.assertIn(block['text'],xml_text)
  for view in ('','?view=first-page','?view=hwpx'):
   response=Response('/api/drafts/1/export.html'+view);report_export.respond(response,draft,'html','문서')
   html=response.wfile.getvalue().decode()
   self.assertEqual(response.headers['X-Report-Fingerprint'],model['fingerprint'])
   for removed in ('관련 문서 및 참고자료','인계자·인수자 확인','업무 인계·인수 요약서','삭제할','제외된 질문'):
    self.assertNotIn(removed,html);self.assertNotIn(removed,text);self.assertNotIn(removed,xml_text)
  self.assertIn('○ 업무명: 2026년 서무',text)
  self.assertIn('\n- AI 추천 답변 · 확인 필요:',text)
  self.assertEqual(draft,before)

 def test_concise_bullets_keep_tasks_numbers_conditions_and_negation(self):
  import unicodedata
  for text in (LONG_BODY,LONG_PLAN):
   bullets=report_content.concise_bullets(text)
   self.assertGreater(len(bullets),0)
   for bullet in bullets:
    units=sum(1 if unicodedata.east_asian_width(c) in ('W','F') else .5 for c in bullet)
    self.assertLessEqual(units,64)
  combined=' '.join(report_content.concise_bullets(LONG_PLAN))
  for fact in ('휴가','출장','매일 오전','접수문서','미처리 공문','매월 초','전월분','매월 말','소모품','예산 집행'):
   self.assertIn(fact,combined)
  protected='납품이 확인되지 않은 경우에는 지급 요청을 해서는 안 됩니다. 매월 20일까지 1,500,000원 집행 현황을 확인해야 합니다.'
  result=' '.join(report_content.concise_bullets(protected))
  for fact in ('확인되지 않은 경우','해서는 안 됩니다','매월 20일까지','1,500,000원','확인해야 합니다'):
   self.assertIn(fact,result)

 def test_removed_nested_sections_and_confirmed_budget(self):
  d=example_draft();d['items']=[{'category':'담당업무 현황','text':'보존할 담당 업무\n8. 인계자·인수자 확인\n삭제할 서명란\n2. 담당업무 현황\n보존할 두 번째 업무','source_ids':[]},
   {'category':'예산','text':'확정 예산: 500만원','source_ids':[]}]
  text='\n'.join(b['text'] for b in report_document.build(d)['blocks'])
  self.assertNotIn('삭제할 서명란',text)
  self.assertIn('보존할 담당 업무',text);self.assertIn('보존할 두 번째 업무',text)
  self.assertIn('확정 예산: 500만원',text)


if __name__=='__main__':unittest.main()
