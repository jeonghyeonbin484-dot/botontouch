import copy,io,unittest
import report_export,export_hwpx
class OutputPreviewTests(unittest.TestCase):
 def test_shared_output_preserves_input_and_removes_print_citations(self):
  draft={'title':'가상 실제 저장 문서','items':[{'category':'담당 업무','text':'매월 가상 비품 확인.\n출처: [1]','source_ids':[]}],'references':{}};original=copy.deepcopy(draft);model=export_hwpx.output_model(draft);self.assertEqual(draft,original);self.assertIn('매월 가상 비품 확인.',str(model['blocks']));self.assertNotIn('출처: [1]',str(model['blocks']))
 def test_first_page_response_uses_saved_title_and_real_template_logo(self):
  class Handler:
   path='/api/drafts/1/export.html?view=first-page'
   wfile=io.BytesIO()
   def send_response(self,status):self.status=status
   def send_header(self,*args):pass
   def end_headers(self):pass
  h=Handler();report_export.respond(h,{'title':'가상 일정 전용 문서','items':[{'category':'담당 업무','text':'가상 사업 일정 확인','source_ids':[]}],'references':{}},'html','문서');body=h.wfile.getvalue().decode();self.assertEqual(h.status,200);self.assertIn('가상 일정 전용 문서',body);self.assertIn('data:image/png;base64,',body);self.assertIn('가상 사업 일정 확인',body)
