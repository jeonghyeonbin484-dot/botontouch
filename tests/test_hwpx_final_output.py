import copy,io,zipfile,unittest,xml.etree.ElementTree as E
import export_hwpx,report_document
class FinalOutputTests(unittest.TestCase):
 def test_citations_removed_only_at_export(self):
  d={'title':'가상 검증','items':[{'category':'담당업무','text':'재고 13개 확인\n출처: [1], [2]\n물품 구매 출처: [13], [14]\n구매 후 검수','source_ids':['s']}], 'references':{'s':{'name':'가상.xlsx','location':'1행','text':'원문 비출력'}}}
  original=copy.deepcopy(d)
  with zipfile.ZipFile(io.BytesIO(export_hwpx.build(d))) as z:
   self.assertIsNone(z.testzip())
   for n in z.namelist():
    if n.endswith(('.xml','.hpf','.rdf')):E.fromstring(z.read(n))
   text=''.join(E.fromstring(z.read('Contents/section0.xml')).itertext())
   self.assertNotIn('출처:',text);self.assertNotIn('[13]',text);self.assertIn('재고 13개 확인',text);self.assertIn('구매 후 검수',text)
   self.assertIn('업무 인계·인수 요약서',text)
   with zipfile.ZipFile(export_hwpx.TEMPLATE) as t:self.assertEqual(z.read('Contents/header.xml'),t.read('Contents/header.xml'))
  self.assertEqual(d,original)
  self.assertTrue(any(b['text'].startswith('출처:') for b in report_document.build(d)['blocks']))
if __name__=='__main__':unittest.main()
