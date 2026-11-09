"""HWPX 출력 전용 문단·글자 서식. 원본 템플릿의 로고·표·기존 스타일은 변경하지 않는다."""
import copy
import xml.etree.ElementTree as E
H='{http://www.hancom.co.kr/hwpml/2011/head}'
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
C='{http://www.hancom.co.kr/hwpml/2011/core}'

def apply(parts,body,heading):
 header=E.fromstring(parts['Contents/header.xml']);chars=header.find('.//'+H+'charProperties');paras=header.find('.//'+H+'paraProperties')
 def clone(group,key):
  source=next(n for n in group if n.get('id')==str(key));n=copy.deepcopy(source);n.set('id',str(max(int(x.get('id')) for x in group)+1));group.append(n);group.set('itemCnt',str(len(group)));return n
 base_char=body.find(P+'run').get('charPrIDRef');main=clone(chars,base_char);main.set('height','1500');main.set('textColor','#000000')
 for key in main.find(H+'ratio').attrib:main.find(H+'ratio').set(key,'100')
 for key in main.find(H+'spacing').attrib:main.find(H+'spacing').set(key,'-18')
 note=clone(chars,base_char);note.set('height','1400');note.set('textColor','#1B1B1B')
 for key in note.find(H+'spacing').attrib:note.find(H+'spacing').set(key,'0')
 paragraph=clone(paras,body.get('paraPrIDRef'));paragraph.set('condense','0')
 for n in paragraph.iter(H+'lineSpacing'):n.set('type','PERCENT');n.set('value','160')
 # 기준 report.hwpx의 주요 본문 문단 31: 두 호환 분기의 실제 여백을 보존한다.
 for index,n in enumerate(paragraph.iter(H+'margin')):
  n.find(C+'left').set('value','850' if index==0 else '1700');n.find(C+'prev').set('value','0');n.find(C+'next').set('value','567' if index==0 else '1134')
 br=paragraph.find(H+'breakSetting');br.set('widowOrphan','1');br.set('keepWithNext','0');br.set('keepLines','0');br.set('breakNonLatinWord','BREAK_WORD')
 heading_para=clone(paras,heading.get('paraPrIDRef'));br=heading_para.find(H+'breakSetting');br.set('keepWithNext','1');br.set('keepLines','1');br.set('widowOrphan','1')
 parts['Contents/header.xml']=E.tostring(header,encoding='utf-8',xml_declaration=True)
 return {'body_para':paragraph.get('id'),'body_char':main.get('id'),'note_char':note.get('id'),'heading_para':heading_para.get('id')}
