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
 return __import__('report_content').classification(name)

def build(draft):
 import report_content as content
 blocks=[];prepared=content.prepare(draft);groups=prepared['groups'];references=draft.get('references',{});refs=[];documents=content.related_documents(draft);work=content.work_name(draft)
 def p(text,style='body'):
  for line in clean(text).splitlines():
   if line.strip():blocks.append({'kind':'p','text':line.strip(),'style':style})
 def heading(index):blocks.append({'kind':'heading','number':str(index+1),'text':SECTIONS[index]})
 def source(entry):
  marks=[]
  for sid in entry['source_ids']:
   ref=references.get(sid)
   if ref:
    key=(clean(ref.get('name')),clean(ref.get('location')))
    if key not in refs:refs.append(key)
    marks.append('['+str(refs.index(key)+1)+']')
  if marks:p('출처: '+', '.join(dict.fromkeys(marks)),'note')
 blocks.append({'kind':'title','text':'업무 인수인계서'});blocks.append({'kind':'subtitle','text':work})
 ws=dict(draft.get('workspace') or {});parties=draft.get('handover_parties') or {}
 for field,party,key in [('predecessor','sender','name'),('successor','recipient','name'),('department','sender','department')]:
  if (parties.get(party) or {}).get(key):ws[field]=parties[party][key]
 heading(0);p('업무명: '+work)
 for label,key in [('부서','department'),('인계자','predecessor'),('인수자','successor'),('인계일(등록 기준일)','reference_date')]:p(label+': '+clean(ws.get(key) or '확인 필요'))
 p('검토 상태: '+('사용자 검토 완료' if draft.get('reviewed') else '미검토 · AI 초안'),'note')
 for i in range(1,7):
  heading(i)
  for entry in groups[i]:
   p('○ '+entry['text']);source(entry)
  if not groups[i] and i!=6:p('확인 필요')
  if i==5:
   tasks=[t for t in draft.get('tasks',[]) if not t.get('deleted')]
   if tasks:
    p('후임자 할 일 목록')
    from datetime import datetime,timezone,timedelta
    today=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    for t in tasks:
     status='완료' if t.get('done') else '기한 지남' if t.get('due_date') and t['due_date']<today else '미완료'
     p('○ ['+status+'] '+clean(t.get('title'))+(' / 기한: '+clean(t['due_date']) if t.get('due_date') else '')+(' / 담당자: '+clean(t['assignee']) if t.get('assignee') else ''))
  if i==6:
   for doc in documents:p('○ '+clean(doc['name'])+(' / '+', '.join(map(clean,doc['locations'])) if doc['locations'] else '')+(' · 원본 변경 확인 필요' if doc['needs_check'] else ''))
   if not documents and not groups[6]:p('확인 필요')
 heading(7)
 for label,key in [('인계자','predecessor'),('인수자','successor')]:p(label+': '+clean(ws.get(key) or '확인 필요')+'     확인일:                       서명:')
 version=draft.get('version_info') or {}
 if version:p('확정본 v'+str(version.get('revision',''))+' / 확정자: '+clean(version.get('actor'))+' / '+clean(version.get('finalized_kst')),'note')
 p('확인란은 직접 확인·서명을 위한 공간이며 전자 승인이나 인수 완료를 대신하지 않습니다.','note')
 review_items=(draft.get('recipient_review') or {}).get('items',[])
 if review_items:
  confirmed=sum(i.get('state')=='confirmed' for i in review_items);p('인수자 항목 확인: '+str(confirmed)+' / '+str(len(review_items))+'개 확인 완료','note')
 expected=[q for q in (draft.get('gap_review') or {}).get('questions',[]) if q.get('qa_kind')=='expected' and q.get('qa_included',True) and not q.get('qa_archived')]
 extra=[q for q in (draft.get('recipient_review') or {}).get('followups',[]) if q.get('qa_kind')!='expected' and not q.get('qa_archived')]
 questions=[];seen=set()
 for q in expected+extra:
  key=content.paragraph_key(q.get('question',''))
  if key and key not in seen:questions.append(q);seen.add(key)
 if questions:
  blocks.append({'kind':'appendix_title','text':'부록 · 후임자 예상 질문·답변'})
  for n,q in enumerate(questions,1):
   p(str(n)+'. '+clean(q.get('question')))
   p(('인계자 확인 답변: ' if q.get('reply') else 'AI 추천 답변 · 확인 필요: ')+clean(q.get('reply') or q.get('recommended_answer') or '추가 확인 필요'))
 blocks.append({'kind':'summary_title','text':'업무 인계·인수 요약서'});blocks.append({'kind':'heading','number':'1','text':'업무현황'})
 for label,idx in [('가. 담당 업무',1),('나. 주요 업무계획 및 진행사항',2),('다. 현안사항 및 문제점',3),('라. 주요 미결사항',4)]:
  p(label);p(('업무: '+work+' · 본문 2항 참조') if idx==1 and groups[1] else content.compact_summary(groups[idx],idx+1))
 blocks.append({'kind':'heading','number':'2','text':'관련 문서 현황'});p('관련 문서 '+str(len(documents))+'건 · 파일명과 위치는 본문 7항 참조' if documents else '확인 필요')
 blocks.append({'kind':'heading','number':'3','text':'주요 물품 및 예산 등 인계·인수가 필요한 사항'})
 for entry in prepared['budget']:p('○ '+entry['text']);source(entry)
 if not prepared['budget']:p('확인 필요')
 blocks.append({'kind':'heading','number':'4','text':'그 밖의 참고사항'});p(content.compact_summary(groups[5],6))
 model={'title':clean(draft.get('title')),'blocks':blocks,'reviewed':bool(draft.get('reviewed')),'template':'namyangju-report-v2'}
 model['fingerprint']=hashlib.sha256(json.dumps(model,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 return model

def markdown(model):
 lines=[]
 for b in model['blocks']:
  if b['kind'] in ('title','summary_title','appendix_title'):
   if b['kind'] in ('summary_title','appendix_title'):lines+=['','<!-- 별도 페이지 시작 -->','']
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
  elif kind in ('summary_title','appendix_title'):content.append('<h1 class="summary-title" data-break="1">'+text+'</h1>')
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
