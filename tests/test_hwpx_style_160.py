"""문서 스타일의 실제 적용과 템플릿 전체 보존을 검사한다."""
import unittest,io,zipfile,copy,xml.etree.ElementTree as E
import export_hwpx
H='{http://www.hancom.co.kr/hwpml/2011/head}';P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
def assert_header_extensions_only(test,generated,original):
 original=E.fromstring(original);generated=E.fromstring(generated)
 for name in ['charProperties','paraProperties']:
  before=original.find('.//'+H+name);after=generated.find('.//'+H+name);ids={n.get('id') for n in before}
  for child in list(after):
   if child.get('id') not in ids:after.remove(child)
  after.set('itemCnt',before.get('itemCnt'))
 test.assertEqual(E.tostring(generated),E.tostring(original),'기존 헤더 전체·글꼴·기존 스타일은 그대로 유지되어야 합니다.')
class Style160Tests(unittest.TestCase):
 def test_actual_body_styles_and_template_preservation(self):
  draft={'title':'가상 업무','items':[{'category':'담당 업무','text':'가상 비품을 확인합니다.','source_ids':[]}],'references':{}};before=copy.deepcopy(draft)
  with zipfile.ZipFile(io.BytesIO(export_hwpx.build(draft))) as z,zipfile.ZipFile(export_hwpx.TEMPLATE) as t:
   assert_header_extensions_only(self,z.read('Contents/header.xml'),t.read('Contents/header.xml'));header=E.fromstring(z.read('Contents/header.xml'));section=E.fromstring(z.read('Contents/section0.xml'));body=next(p for p in section if '가상 비품을 확인합니다.' in ''.join(p.itertext()))
   para=header.find('.//'+H+'paraPr[@id="'+body.get('paraPrIDRef')+'"]');char=header.find('.//'+H+'charPr[@id="'+body.find(P+'run').get('charPrIDRef')+'"]')
   self.assertEqual(char.get('height'),'1500');self.assertEqual(char.find(H+'ratio').get('hangul'),'100');self.assertEqual(char.find(H+'spacing').get('hangul'),'-18');self.assertTrue(all(n.get('value')=='160' and n.get('type')=='PERCENT' for n in para.iter(H+'lineSpacing')))
   for name in z.namelist():
    if name.startswith('BinData/'):self.assertEqual(z.read(name),t.read(name))
   original=E.fromstring(t.read('Contents/section0.xml'));self.assertEqual(E.tostring(section.find('.//'+P+'pagePr')),E.tostring(original.find('.//'+P+'pagePr')));self.assertIsNotNone(section.find('.//'+P+'pageNum'))
   headings=[p for p in section if len(p.findall('.//'+P+'tc'))==2]
   self.assertTrue(headings)
   for p in headings:
    pr=header.find('.//'+H+'paraPr[@id="'+p.get('paraPrIDRef')+'"]');self.assertEqual(pr.find(H+'breakSetting').get('keepWithNext'),'1')
  self.assertEqual(draft,before)
if __name__=='__main__':unittest.main()
