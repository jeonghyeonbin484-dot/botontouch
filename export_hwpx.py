"""원본 남양주시 보고서의 실제 XML·이미지·스타일을 재사용한 HWPX 생성."""
import copy
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import report_document

HP='http://www.hancom.co.kr/hwpml/2011/paragraph'
HH='http://www.hancom.co.kr/hwpml/2011/head'
SECTIONS=report_document.SECTIONS
TEMPLATE=Path(__file__).parent/'templates/namyangju-report.hwpx'

def output_model(draft,editable=False):
 # 출력용 복사본: 저장된 출처 데이터와 일반 미리보기는 변경하지 않는다.
 output_draft=copy.deepcopy(draft)
 def without_citations(value):
  value=report_document.clean(value)
  value=re.sub(r'출처\s*[:：]\s*(?:\[\d+\]\s*(?:[,，]\s*)?)+','',value)
  value=re.sub(r'(?m)^\s*출처 없음\s*[·:：]?\s*전임자 확인 필요\s*$','',value)
  return '\n'.join(line.rstrip() for line in value.splitlines() if line.strip())
 model=report_document.build(output_draft,editable)
 filtered=[]
 for block in model['blocks']:
  text=block['text']
  if block.get('style')=='note' and (text.startswith(('출처:','출처 없음','출처 변경')) or re.match(r'^\[\d+\] ',text)):
   continue
  block['text']=without_citations(text)
  if block['text'].strip():filtered.append(block)
 model['blocks']=filtered
 return model

def build(draft):
 model=output_model(draft)
 with zipfile.ZipFile(TEMPLATE) as z:parts={n:z.read(n) for n in z.namelist()}
 for _,pair in ET.iterparse(io.BytesIO(parts['Contents/section0.xml']),events=['start-ns']):
  if pair[0] and not re.fullmatch(r'ns\d+',pair[0]):ET.register_namespace(*pair)
 source=ET.fromstring(parts['Contents/section0.xml']);nodes=list(source)
 section=ET.Element(source.tag,source.attrib)
 title=copy.deepcopy(nodes[0]);subtitle=nodes[1];heading=nodes[2];body=nodes[3]
 style=__import__('hwpx_report_style').apply(parts,body,heading)
 def text(p,value):
  run=p.find('{%s}run'%HP)
  attrs=dict(run.attrib) if run is not None else {'charPrIDRef':'21'}
  for child in list(p):p.remove(child)
  run=ET.SubElement(p,'{%s}run'%HP,attrs);ET.SubElement(run,'{%s}t'%HP).text=report_document.clean(value)
 def cells(p):return p.findall('.//{%s}tc'%HP)
 title_cell=cells(title)[-1];text(title_cell.find('.//{%s}p'%HP),'업무 인수인계서')
 for block in model['blocks']:
  kind=block['kind'];value=block['text']
  if kind=='title':section.append(title)
  elif kind=='subtitle':
   p=copy.deepcopy(subtitle);text(p.find('.//{%s}tc//{%s}p'%(HP,HP)),value);section.append(p)
  elif kind in ('summary_title','appendix_title'):
   p=copy.deepcopy(title_cell.find('.//{%s}p'%HP));p.set('pageBreak','1');text(p,value);section.append(p)
  elif kind=='heading':
   p=copy.deepcopy(heading);p.set('paraPrIDRef',style['heading_para']);cs=cells(p)
   text(cs[0].find('.//{%s}p'%HP),block['number']);text(cs[1].find('.//{%s}p'%HP),value)
   section.append(p)
  else:
   p=copy.deepcopy(body);text(p,value);p.set('paraPrIDRef',style['body_para']);p.set('styleIDRef','0');p.find('{%s}run'%HP).set('charPrIDRef',style['body_char'])
   if block.get('style')=='note':
    p.find('{%s}run'%HP).set('charPrIDRef',style['note_char'])
   section.append(p)
 # Repeated templates must have new instance IDs; style and binary references remain intact.
 ident=100000
 for node in section.iter():
  if node.tag in ('{%s}p'%HP,'{%s}tbl'%HP,'{%s}pic'%HP):
   node.set('id',str(ident));ident+=1
  for stale in list(node.findall('{%s}linesegarray'%HP)):node.remove(stale)
 # Keep original fonts, spacing, border fills, image resources and section properties.
 if 'settings.xml' in parts:
  settings=ET.fromstring(parts['settings.xml'])
  for item in settings.iter():
   if item.get('name')=='PrintMethod':item.text='0'
  parts['settings.xml']=ET.tostring(settings,encoding='utf-8',xml_declaration=True)
 parts['Contents/section0.xml']=ET.tostring(section,encoding='utf-8',xml_declaration=True)
 parts['Preview/PrvText.txt']='\n'.join(b['text'] for b in model['blocks']).encode('utf-8')
 # A stale blank-template thumbnail must not represent the newly generated document.
 # The package thumbnail is optional; remove its manifest entry together with the file.
 parts.pop('Preview/PrvImage.png',None)
 for name in ['META-INF/manifest.xml','Contents/content.hpf']:
  if name not in parts:continue
  root=ET.fromstring(parts[name])
  if name=='Contents/content.hpf':
   opf='http://www.idpf.org/2007/opf/'
   manifest=root.find('{%s}manifest'%opf)
   for meta in root.iter():
    if meta.get('name') in ('creator','lastsaveby'):meta.text=''

  for parent in root.iter():
   for child in list(parent):
    if any('PrvImage.png' in str(v) for v in child.attrib.values()):parent.remove(child)
   if root.tag.endswith('package'):
    for el in root.iter():
     if el.tag.endswith('title'):el.text=model['title']
  parts[name]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  z.writestr('mimetype',b'application/hwp+zip',compress_type=zipfile.ZIP_STORED)
  for name,value in parts.items():
   if name!='mimetype':z.writestr(name,value,compress_type=zipfile.ZIP_DEFLATED)
 raw=out.getvalue()
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip():raise ValueError('한글 문서 압축 검증에 실패했습니다.')
  for name in z.namelist():
   if name.endswith(('.xml','.hpf','.rdf')):ET.fromstring(z.read(name))
 return raw
