"""Source-bound verification tools. Calendar/conflict extraction is explicitly rule-based."""
import re,json,copy
SECTIONS=('담당 업무 개요','정기적으로 해야 할 업무','월별·시기별 주요 일정','현재 진행 중인 현안','협의가 필요한 부서 및 담당자','향후 조치사항','후임자가 알아야 할 유의사항')
def refs_for(documents):
 refs={}
 for d in documents:
  for i,s in enumerate(json.loads(d['sources']),1):refs[f"D{d['id']}-S{i}"]={'document_id':d['id'],'revision':d['revision'] if 'revision' in d.keys() else 1,'name':d['name'],**s}
 return refs

def analysis(refs):
 calendar=[];groups={}
 for key,ref in refs.items():
  for line in ref['text'].splitlines():
   if re.match(r'\s*(내보낸 시각|생성 시각|검토 상태|저장된 내용 기준)\s*[:：]',line):continue
   dates=re.findall(r'(20\d{2})[-./](\d{1,2})[-./](\d{1,2})',line)
   months={int(m) for m in re.findall(r'(?<!\d)(1[0-2]|[1-9])월',line)}|{int(m) for _,m,_ in dates}
   for month in sorted(months):calendar.append({'month':month,'text':line,'source_ids':[key],'method':'규칙 기반 원문 추출 · AI 의미 분석 아님'})
   event=re.search(r'일정\s*[:：]\s*(.+?)\s*[/|]',line)
   if event:
    for y,m,d in dates:groups.setdefault(event[1].strip(),{}).setdefault(f'{y}-{int(m):02}-{int(d):02}',[]).append(key)
 conflicts=[]
 for event,values in groups.items():
  if len(values)>1:conflicts.append({'event':event,'dates':values,'source_ids':list(dict.fromkeys(k for keys in values.values() for k in keys)),'question':event+'의 일정이 '+', '.join(values)+'로 다릅니다. 어느 일정이 최종인가요?','method':'규칙 기반 동일 일정명·서로 다른 날짜 후보 · 사람 확인 필요'})
 return {'calendar':calendar,'conflicts':conflicts,'references':refs,'method':'규칙 기반 보조 점검. AI 분석과 구분합니다.'}

def preserve_review(previous,items):
 result=copy.deepcopy(items)
 for i,item in enumerate(result):
  old=previous.get('items',[])[i] if i<len(previous.get('items',[])) else None
  if old and (old['text']!=item['text'] or old.get('source_check_required')):item['source_check_required']=True
  if not item.get('source_ids'):item['source_check_required']=True
 return result

def complete_sections(value,sections=None):
 value=copy.deepcopy(value);present={i['category'] for i in value['items']}
 for section in (SECTIONS if sections is None else sections):
  if section not in present:value['items'].append({'category':section,'text':'자료에서 확인되지 않음 · 전임자 확인 필요','source_ids':[],'source_check_required':True})
 return value
