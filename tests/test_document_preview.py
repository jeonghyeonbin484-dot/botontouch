import io
import unittest
import zipfile

import auth_control
import report_export


class Response:
 def __init__(self,path):self.path=path;self.wfile=io.BytesIO();self.headers={}
 def send_response(self,status):self.status=status
 def send_header(self,key,value):self.headers[key]=value
 def end_headers(self):pass


class OfficialDocumentPreviewTests(unittest.TestCase):
 def test_full_preview_and_hwpx_share_content_and_reject_stale_download(self):
  draft={'title':'현재 실제 문서','items':[{'category':'담당 업무','text':'실제 저장 내용\n출처: [1]','source_ids':[]}],'references':{}}
  preview=Response('/api/drafts/1/export.html?view=hwpx')
  report_export.respond(preview,draft,'html','문서')
  html=preview.wfile.getvalue().decode()
  self.assertIn('실제 저장 내용',html)
  self.assertNotIn('출처: [1]',html)
  self.assertIn('업무 인계·인수 요약서',html)
  self.assertIn('data:image/png;base64,',html)
  fingerprint=preview.headers['X-Report-Fingerprint']
  download=Response('/api/drafts/1/export.hwpx?view=hwpx&report_hash='+fingerprint)
  report_export.respond(download,draft,'hwpx','문서')
  self.assertEqual(download.headers['X-Report-Fingerprint'],fingerprint)
  with zipfile.ZipFile(io.BytesIO(download.wfile.getvalue())) as z:
   self.assertIn('실제 저장 내용',z.read('Preview/PrvText.txt').decode())
   self.assertNotIn('출처: [1]',z.read('Preview/PrvText.txt').decode())
  draft['items'][0]['text']='변경된 내용'
  with self.assertRaises(auth_control.AccessError) as error:
   report_export.respond(Response(download.path),draft,'hwpx','문서')
  self.assertEqual(error.exception.status,409)
