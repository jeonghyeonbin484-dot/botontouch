"""검토된 저장 데이터에서 HTML/MD/HWPX 공통 문서 모델을 만든다. AI 호출 없음."""
import hashlib
import html
import json
import re
from pathlib import Path

SECTIONS=['인수인계 개요','담당업무 현황','주요 업무계획 및 진행사항','현안사항 및 문제점','주요 미결사항','주요 일정 및 실무 노하우','관련 문서 및 참고자료','인계자·인수자 확인']

def clean(value):
 return ''.join(c for c in str(value or '') if c in '\t\n\r' or 0x20<=ord(c)<=0xD7FF or 0xE000<=ord(c)<=0xFFFD or 0x10000<=ord(c)<=0x10FFFF)

def classify(name):
 if any(k in name for k in ['미결','확인 필요','확인이 필요','확인사항','질문','불확실']):return 4
 if any(k in name for k in ['현안','문제','위험']):return 3
 if any(k in name for k in ['일정','정기','반복','노하우','주의','유의']):return 5
 if any(k in name for k in ['계획','추진','진행','향후','조치','협의']):return 2
 if any(k in name for k in ['참고','자료','근거','문서']):return 6
 return 1

def build(draft):
 blocks=[];groups={i:[] for i in range(8)};refs=[]
 def p(text,style='body'):
  for line in clean(text).splitlines():
   if line.strip():blocks.append({'kind':'p','text':line,'style':style})
 def heading(index):blocks.append({'kind':'heading','number':str(index+1),'text':SECTIONS[index]})
 blocks.append({'kind':'title','text':'업무 인수인계서'})
 blocks.append({'kind':'subtitle','text':clean(draft.get('title'))})
 ws=dict(draft.get('workspace') or {})
 parties=draft.get('handover_parties') or {}
 for field,party,key in [('predecessor','sender','name'),('successor','recipient','name'),('department','sender','department')]:
  if (parties.get(party) or {}).get(key):ws[field]=parties[party][key]
 heading(0)
 for label,key in [('업무명','title'),('부서','department'),('인계자','predecessor'),('인수자','successor'),('인계일(등록 기준일)','reference_date')]:
  if ws.get(key):p(label+': '+clean(ws[key]))
 p('검토 상태: '+('사용자 검토 완료' if draft.get('reviewed') else '미검토 · AI 초안'),'note')
 for item in draft.get('items',[]):
  if clean(item.get('text')).strip():groups[classify(item.get('category',''))].append(item)
 for i in range(1,7):
  heading(i)
  for item in groups[i]:
   category=clean(item.get('category'))
   redundant=re.sub(r'\s','',category)==re.sub(r'\s','',SECTIONS[i]) or i==1 and category in ('담당업무','담당 업무 개요')
   if not redundant:p(category)
   p(item.get('text'))
   marks=[]
   for sid in item.get('source_ids',[]):
    ref=draft.get('references',{}).get(sid)
    if ref:
     key=(clean(ref.get('name')),clean(ref.get('location')))
     if key not in refs:refs.append(key)
     marks.append('['+str(refs.index(key)+1)+']')
   p('출처: '+', '.join(dict.fromkeys(marks)) if marks else '출처 없음 · 전임자 확인 필요','note')
  if not groups[i] and i!=6:p('전임자 확인 필요')
  if i==4:
   for q in (draft.get('recipient_review') or {}).get('followups',[]):
    p('추가 질문: '+clean(q.get('question')))
    p('보완 답변: '+clean(q.get('reply')) if q.get('reply') else '미해결 · 전임자 확인 필요')
  if i==5 and draft.get('tasks'):
   p('후임자 할 일 목록')
   from datetime import datetime,timezone,timedelta
   today=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
   for t in draft['tasks']:
    if t.get('deleted'):continue
    status='완료' if t.get('done') else '기한 지남' if t.get('due_date') and t['due_date']<today else '미완료'
    p('['+status+'] '+clean(t.get('title'))+(' / 기한: '+clean(t['due_date']) if t.get('due_date') else '')+(' / 담당자: '+clean(t['assignee']) if t.get('assignee') else ''))
    if t.get('source'):p('참고: '+clean(t['source']),'note')
  if i==6:
   for n,(name,location) in enumerate(refs,1):p(f'[{n}] {name}'+(' / '+location if location else ''),'note')
   if not refs and not groups[6]:p('등록된 참고자료 없음 · 전임자 확인 필요')
   if draft.get('source_changes'):p('출처 변경 · 재확인 필요: '+', '.join(map(clean,draft['source_changes'])),'note')
 heading(7)
 for label,key in [('인계자','predecessor'),('인수자','successor')]:
  p(label+': '+clean(ws.get(key) or '확인 필요')+'     확인일:                       서명:')
 version=draft.get('version_info') or {}
 if version:p('확정본 v'+str(version.get('revision',''))+' / 확정자: '+clean(version.get('actor'))+' / '+clean(version.get('finalized_kst')),'note')
 review=draft.get('recipient_review') or {}
 for item in review.get('items',[]):
  states={'confirmed':'확인 완료','needs_info':'추가 설명 필요','pending':'미확인','outdated':'재확인 필요'}
  p(clean(item.get('category'))+': '+states.get(item.get('state'),'확인 필요'),'note')
 p('확인란은 직접 확인·서명을 위한 공간이며 전자 승인이나 인수 완료를 대신하지 않습니다.','note')
 blocks.append({'kind':'summary_title','text':'업무 인계·인수 요약서'})
 def excerpt(items):
  lines=[]
  for item in items:
   text=clean(item['text']).strip().splitlines()[0]
   if len(text)>180:text=text[:180]+'… (상세 본문 참조)'
   if text not in lines:lines.append(text)
  return '\n'.join(lines[:3]) if lines else '전임자 확인 필요'
 blocks.append({'kind':'heading','number':'1','text':'업무현황'})
 for label,key in [('가. 담당 업무',1),('나. 주요 업무계획 및 진행사항',2),('다. 현안사항 및 문제점',3),('라. 주요 미결사항',4)]:
  p(label);p(excerpt(groups[key]))
 blocks.append({'kind':'heading','number':'2','text':'관련 문서 현황'})
 p('\n'.join(name+(' / '+loc if loc else '') for name,loc in refs) or '전임자 확인 필요')
 blocks.append({'kind':'heading','number':'3','text':'주요 물품 및 예산 등 인계·인수가 필요한 사항'})
 money=[item for item in draft.get('items',[]) if any(k in clean(item.get('category'))+' '+clean(item.get('text')) for k in ['물품','비품','예산','잔액'])]
 p(excerpt(money))
 blocks.append({'kind':'heading','number':'4','text':'그 밖의 참고사항'})
 p(excerpt(groups[5]));p('이 요약서는 저장된 최종 내용의 발췌입니다. 생략된 세부 내용은 본문을 확인하세요.','note')
 model={'title':clean(draft.get('title')),'blocks':blocks,'reviewed':bool(draft.get('reviewed')),'template':'namyangju-report-v2'}
 model['fingerprint']=hashlib.sha256(json.dumps(model,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 return model

def markdown(model):
 lines=[]
 for b in model['blocks']:
  if b['kind'] in ('title','summary_title'):
   if b['kind']=='summary_title':lines+=['','<!-- 별도 페이지 시작 -->','']
   lines+=['# '+b['text'],'']
  elif b['kind']=='heading':lines+=['## '+b['number']+'. '+b['text'],'']
  else:lines += [b['text'],'']
 return '\n'.join(lines)

def html_document(model):
 # Script/style are fixed program text; all user text is escaped and inserted only as text.
 import base64,zipfile
 with zipfile.ZipFile(Path(__file__).parent/'templates/namyangju-report.hwpx') as z:
  images={n:'data:image/png;base64,'+base64.b64encode(z.read(n)).decode() for n in ['BinData/image1.PNG','BinData/image2.PNG']}
 def esc(s):return html.escape(str(s),quote=True)
 content=[]
 for b in model['blocks']:
  kind=b['kind'];text=esc(b['text'])
  if kind=='title':content.append('<div class="report-brand"><img class="slogan" src="'+images['BinData/image2.PNG']+'"><img class="stripe" src="'+images['BinData/image1.PNG']+'"><h1>'+text+'</h1></div>')
  elif kind=='subtitle':content.append('<div class="report-subtitle">'+text+'</div>')
  elif kind=='summary_title':content.append('<h1 class="summary-title" data-break="1">'+text+'</h1>')
  elif kind=='heading':content.append('<h2><span>'+esc(b['number'])+'</span><strong>'+text+'</strong></h2>')
  else:content.append('<p class="'+('note' if b.get('style')=='note' else 'body')+'">'+text+'</p>')
 css=(Path(__file__).parent/'templates/report.css').read_text(encoding='utf-8')
 font=base64.b64encode((Path(__file__).parent/'templates/fonts/Pretendard-ExtraBold.woff2').read_bytes()).decode()
 css="@font-face{font-family:'Pretendard ExtraBold';src:url(data:font/woff2;base64,"+font+") format('woff2');font-weight:800;font-display:block;}"+css
 script=(Path(__file__).parent/'templates/report-pagination.js').read_text(encoding='utf-8')
 return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(model['title'])+' · 인수인계서 미리보기</title><style>'+css+'</style><body><div class="preview-toolbar">A4 미리보기 · 글꼴과 브라우저에 따라 한글의 페이지 배치와 차이가 날 수 있습니다. <button onclick="window.print()">인쇄</button></div><main id="pages"></main><div id="content" hidden>'+''.join(content)+'</div><script>'+script+'</script></body></html>'


def register_local_fonts():
 """Windows 로컬 실행 중에만 원본 OFL 글꼴을 등록한다. 파일/레지스트리 설치 없음."""
 import os
 if os.name!='nt':return 0
 import ctypes,atexit
 loaded=[]
 for name in ['Pretendard-ExtraBold.ttf','Pretendard-SemiBold.ttf']:
  path=str((Path(__file__).parent/'templates/fonts'/name).resolve())
  if ctypes.windll.gdi32.AddFontResourceExW(path,0,0):loaded.append(path)
 ctypes.windll.user32.SendNotifyMessageW(0xffff,0x001D,0,0)
 def release():
  for path in loaded:ctypes.windll.gdi32.RemoveFontResourceExW(path,0,0)
 atexit.register(release)
 return len(loaded)
