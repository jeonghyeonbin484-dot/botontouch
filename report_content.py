"""출력 전용 정리. 저장된 문장·출처를 보존하고 외부 AI를 호출하지 않는다."""
import re
ALIASES={1:['담당업무 현황','담당 업무','담당 업무 개요','업무 개요'],2:['주요 업무계획 및 진행사항','주요 업무 및 추진 현황','추진현황','추진 상황','업무계획','진행사항','협의 부서 및 담당자','협의사항'],3:['현안사항 및 문제점','현안사항','문제점','진행 중인 현안 및 향후 조치사항','진행 중인 업무 및 현안'],4:['주요 미결사항','미결사항','전임자 확인이 필요한 사항','확인 필요사항','향후 조치사항'],5:['주요 일정 및 실무 노하우','월별·정기 업무 일정','주요 일정','처리절차','업무 주기','실무 노하우','후임자 유의사항','유의사항','주의사항'],6:['관련 문서 및 참고자료','관련 문서','참고자료'],8:['예산·물품','예산','물품','계약 현황']}
def key(value):return re.sub(r'[\s\W_]+','',str(value)).casefold()
def paragraph_key(value):return re.sub(r'\s+',' ',str(value)).strip().rstrip('.。')
def work_name(draft):
 title=str(draft.get('title') or (draft.get('workspace') or {}).get('title') or '업무명 확인 필요').strip()
 return re.sub(r'\s*(?:업무\s*)?인수인계서\s*$','',title).strip() or title

def classification(name):
 k=key(name)
 for section,aliases in ALIASES.items():
  if k in {key(a) for a in aliases}:return section
 if any(w in name for w in ['미결','확인 필요','확인이 필요','확인사항','질문','불확실']):return 4
 if any(w in name for w in ['현안','문제','위험']):return 3
 if any(w in name for w in ['일정','정기','반복','노하우','주의','유의','절차','주기']):return 5
 if any(w in name for w in ['계획','추진','진행','향후','조치','협의']):return 2
 if any(w in name for w in ['참고','자료','근거','문서']):return 6
 return 1

def strip_marker(line):
 line=re.sub(r'^\s*#{1,6}\s*','',line).strip()
 line=re.sub(r'^(?:[○●•▪□■▶▷]|[-*](?=\s+\D))\s*','',line)
 line=re.sub(r'^(?:\d+[.)]|[가-하][.)]|[①-⑳])\s+','',line)
 return line.strip().strip('*').strip()

def unknown(text):
 return bool(re.fullmatch(r'(?:자료에서\s*)?(?:(?:확인되지\s*않음|확인할\s*수\s*없(?:음|습니다))\s*[.·—-]?\s*)?(?:전임자\s*)?(?:확인\s*필요|미확인)(?:\s*[.·—-]\s*(?:전임자\s*)?확인\s*필요)?[.!\s]*',text))

def section_for(text,default):
 if default==5 and re.search(r'효과|비용 회수|탄소중립|효율성',text) and not re.search(r'매월|\d+월|반드시|주의|준수|점검|마감|기한|절차|전날',text):return 1
 if default in (1,4,5,6,8):return default
 # 현재 문제를 기술한 문장은 계획/완료 이력으로 잘못 옮기지 않는다.
 problem=bool(re.search(r'부족|미흡|지연|장애|오류|불일치|위험|문제',text))
 historic=bool(re.search(r'분석하였|분석했|해결하였|해결했|해소하였|개선.*(?:완료|수립|보고)',text))
 if problem and not historic:return 3
 if re.search(r'확인(?:이|을)?\s*필요|확인해야|확보해야|협의해야|처리해야|미확정|미정|미결|답변\s*필요',text):return 4
 if default==3 and not problem and re.search(r'예정|추진|계획|검토\s*중|구축|확대|수립|보고',text):return 2
 return default

def money_fact(text,draft,ids):
 # 예산이라는 단어, 회수기간, 추천 답변을 확정된 예산으로 취급하지 않는다.
 amount=re.findall(r'\d[\d,.]*(?:\s*억|\s*천|\s*백만|\s*만)?\s*원|\d[\d,.]*\s*(?:대|개|세트)(?![가-힣])',text)
 if not amount or not re.search(r'예산|집행|잔액|계약|구매|물품|비품|장비|명패|구축비',text):return False
 if re.search(r'예상|추정|검토|문제|낭비|부족|미정|확인\s*필요|확인되지|계획\s*중|가능|회수|절감\s*효과',text):return False
 references=draft.get('references') or {}
 supported=any(all(re.sub(r'\s','',a) in re.sub(r'\s','',str(references[s].get('text',''))) for a in amount) for s in ids if s in references)
 return bool(supported or draft.get('reviewed'))

def prepare(draft):
 groups={i:[] for i in range(1,7)};budget=[];seen={};removed=0;known={key(a):i for i,ls in ALIASES.items() for a in ls}
 ignored={key(work_name(draft)),key(draft.get('title','')),key('업무 인수인계서'),key('인수인계 개요'),key('인계자·인수자 확인'),key('업무 인계·인수 요약서')}
 for item in draft.get('items',[]):
  category=str(item.get('category',''));target=classification(category)
  for raw in str(item.get('text','')).splitlines():
   text=strip_marker(raw)
   if not text or re.match(r'^출처\s*[:：]',text):continue
   if key(text) in ignored:removed+=1;continue
   named=re.match(r'^(?:업무명|문서 제목|제목)[:：]\s*(.+)$',text)
   if named and key(named[1]) in ignored:removed+=1;continue
   candidate=re.sub(r'^(?:\d+[.)]|[가-하][.)])\s*','',text)
   if key(candidate.rstrip(':：')) in known:text=candidate
   if key(text.rstrip(':：')) in known:target=known[key(text.rstrip(':：'))];continue
   colon=re.match(r'^([^:：]{1,45})[:：]\s*(.+)$',text)
   if colon and key(colon[1]) in known:target=known[key(colon[1])];text=colon[2].strip()
   if unknown(text):continue
   normalized=paragraph_key(text)
   if normalized in seen:
    seen[normalized]['source_ids']=list(dict.fromkeys(seen[normalized]['source_ids']+item.get('source_ids',[])));removed+=1;continue
   section=section_for(text,target);entry={'text':text,'category':category,'source_ids':list(item.get('source_ids',[])),'section':section};seen[normalized]=entry
   if money_fact(text,draft,entry['source_ids']):budget.append(entry)
   elif section==8:groups[4].append(entry|{'text':'확인 필요: '+text,'section':4})
   else:groups[section].append(entry)
 return {'groups':groups,'budget':budget,'duplicates_removed':removed}

def related_documents(draft):
 actual=draft.get('report_documents');by_id={d['id']:d for d in actual or [] if 'id' in d};result={}
 for ref in (draft.get('references') or {}).values():
  name=str(ref.get('name') or '').strip();location=str(ref.get('location') or '').strip();did=ref.get('document_id');mismatch=False
  if actual is not None:
   doc=by_id.get(did) or next((d for d in actual if d.get('name')==name),None)
   if not doc:continue
   mismatch=doc.get('name')!=name or (ref.get('revision') is not None and doc.get('revision') is not None and ref['revision']!=doc['revision']);name=doc['name']
  if not name:continue
  row=result.setdefault(name,{'name':name,'locations':[],'needs_check':False});row['needs_check']|=mismatch
  if location not in row['locations'] and location:row['locations'].append(location)
 for doc in actual or []:
  name=doc.get('name')
  if name:result.setdefault(name,{'name':name,'locations':[],'needs_check':False})
 return list(result.values())

def compact_summary(entries,section):
 if not entries:return '확인 필요'
 lines=[]
 for entry in entries[:2]:
  text=entry['text'];parts=re.split(r'(?<=하였으며),\s*|(?<=했으며),\s*|(?<=예정이며),\s*|(?<=임)\.\s+',text)
  chosen=parts[-1] if len(parts)>1 else text
  if section==5 and re.search(r'에 대하여|에 대해',text):chosen='확인 필요: '+re.split(r'에 대하여|에 대해',text)[0].removeprefix('사업 추진을 위한 ').strip()
  chosen=re.sub(r'^이를 개선하기 위한\s*','',chosen).strip()
  if len(chosen)>86:
   lines.append(str(len(entries))+'건 · 상세 내용은 본문 '+str(section)+'항 참조');break
  if chosen==text:
   lines.append(str(len(entries))+'건 · 상세 내용은 본문 '+str(section)+'항 참조');break
  lines.append(chosen+' (본문 '+str(section)+'항 참조)')
 return '\n'.join(dict.fromkeys(lines))
