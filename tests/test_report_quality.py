from test_hwpx_style_160 import assert_header_extensions_only
import unittest,copy,io,zipfile,xml.etree.ElementTree as E
import report_content,report_document,export_hwpx
class ReportQualityTests(unittest.TestCase):
 def draft(self):return dict(title='가상 드론 교육 업무 인수인계서',reviewed=True,workspace={'title':'서무업무'},items=[],references={})
 def test_title_and_nested_headings_not_repeated(self):
  d=self.draft();d['items']=[dict(category='담당 업무 개요',text='# 가상 드론 교육 업무 인수인계서\n## 1.담당 업무\n교육 접수와 현장 운영을 담당합니다.\n교육 접수와 현장 운영을 담당합니다.',source_ids=[])];m=report_document.build(d);texts=[b['text'] for b in m['blocks']];self.assertEqual(texts.count('○ 교육 접수와 현장 운영을 담당합니다.'),1);self.assertIn('업무명: 가상 드론 교육',texts);self.assertNotIn('업무명: 서무업무',texts)
 def test_no_budget_keyword_false_positive_and_no_qa_in_pending(self):
  d=self.draft();d['items']=[dict(category='진행 중인 현안 및 향후 조치사항',text='예산 확보 여건에 따라 시범 운영을 추진할 예정입니다.',source_ids=[])];d['gap_review']={'questions':[dict(qa_kind='expected',qa_included=1,question='가상 선정 질문',reply='',recommended_answer='추가 확인 필요'),dict(qa_kind='expected',qa_included=0,question='제외된 질문',reply='제외된 답변'),dict(qa_kind='expected',qa_included=1,qa_archived=1,question='숨긴 질문',reply='숨긴 답변')]};p=report_content.prepare(d);self.assertEqual(len(p['groups'][2]),1);self.assertEqual(p['budget'],[]);m=report_document.build(d);kinds=[b['kind'] for b in m['blocks']];self.assertLess(kinds.index('appendix_title'),kinds.index('summary_title'));s='\n'.join(b['text'] for b in m['blocks']);self.assertIn('AI 추천 답변 · 확인 필요: 추가 확인 필요',s);self.assertNotIn('제외된 질문',s);self.assertNotIn('숨긴 질문',s)
 def test_decimals_and_negation_are_not_duplicates(self):
  d=self.draft();d['items']=[dict(category='담당 업무',text='처리량은 1.5건입니다.\n처리량은 15건입니다.\n교육을 진행하지 않습니다.\n교육을 진행합니다.',source_ids=[])];self.assertEqual(sum(len(x) for x in report_content.prepare(d)['groups'].values()),4)
 def test_finance_only_checked_fact(self):
  d=self.draft();d['items']=[dict(category='예산',text='확정 예산: 500만원\n구축 예상 예산: 800만원\n예산 절감 효과를 검토합니다.',source_ids=[])];p=report_content.prepare(d);self.assertEqual([e['text'] for e in p['budget']],['확정 예산: 500만원'])
 def test_references_match_real_attachment_name_and_group_pages(self):
  d=self.draft();d['references']={'A':dict(document_id=1,revision=1,name='틀린파일.pdf',location='1쪽'),'B':dict(document_id=1,revision=1,name='실제파일.pdf',location='2쪽'),'C':dict(document_id=99,name='없는파일.pdf',location='1쪽')};d['report_documents']=[dict(id=1,name='실제파일.pdf',revision=1)];docs=report_content.related_documents(d);self.assertEqual(len(docs),1);self.assertEqual(docs[0]['name'],'실제파일.pdf');self.assertTrue(docs[0]['needs_check']);self.assertEqual(docs[0]['locations'],['1쪽','2쪽'])
 def test_styles_summary_page_and_input_preserved(self):
  d=self.draft();d['items']=[dict(category='담당 업무',text='가상 교육 자료를 정리합니다.',source_ids=[])];before=copy.deepcopy(d)
  with zipfile.ZipFile(io.BytesIO(export_hwpx.build(d))) as z,zipfile.ZipFile(export_hwpx.TEMPLATE) as t:
   assert_header_extensions_only(self,z.read('Contents/header.xml'),t.read('Contents/header.xml'));self.assertEqual(z.read('BinData/image1.PNG'),t.read('BinData/image1.PNG'));self.assertEqual(z.read('BinData/image2.PNG'),t.read('BinData/image2.PNG'));section=E.fromstring(z.read('Contents/section0.xml'));summary=next(p for p in section if '업무 인계·인수 요약서' in ''.join(p.itertext()));self.assertEqual(summary.get('pageBreak'),'1');self.assertIsNotNone(section.find('.//{%s}pageNum'%export_hwpx.HP))
  self.assertEqual(d,before)
 def test_summary_not_a_second_copy_of_body(self):
  d=self.draft();sentence='가상 교육의 현장 참석을 확인하고 준비한 자료를 배부하여 후임자가 업무 절차를 익힐 수 있도록 운영합니다.';d['items']=[dict(category='담당 업무',text=sentence,source_ids=[])];m=report_document.build(d);self.assertEqual(sum(sentence in b['text'] for b in m['blocks']),1)
 def test_work_scope_and_pending_not_reclassified_by_problem_keyword(self):
  self.assertEqual(report_content.section_for('시스템 장애 대응 업무를 담당합니다.',1),1)
  self.assertEqual(report_content.section_for('지연된 계약 조건을 수정해야 합니다.',4),4)
if __name__=='__main__':unittest.main()
