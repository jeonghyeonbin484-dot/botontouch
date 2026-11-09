"""업무별 비공개 AI 작성 대화. 기존 로그인·자료·문서·Q&A·출력 API를 재사용한다."""
import copy,json,re,sqlite3,zlib,uuid
from contextlib import closing
from urllib.parse import urlsplit,parse_qs
from batontouch.auth import sessions as auth_control; from batontouch.ai import drafts as ai_draft; from batontouch.handover import workflow as workflow; from batontouch.handover import journey as handover_journey; from batontouch.ai import conversation_generation as studio_ai

def ensure_conversation_schema(db):
 db.executescript('''
 CREATE TABLE IF NOT EXISTS ai_studio_sessions(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL,workspace_id INTEGER NOT NULL,draft_id INTEGER,title TEXT NOT NULL DEFAULT '새 인수인계 대화',created_workspace INTEGER NOT NULL DEFAULT 0,created TEXT DEFAULT CURRENT_TIMESTAMP,updated TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS ai_studio_documents(session_id INTEGER NOT NULL,document_id INTEGER NOT NULL,PRIMARY KEY(session_id,document_id));
 CREATE TABLE IF NOT EXISTS ai_studio_messages(id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL,nonce TEXT NOT NULL,role TEXT NOT NULL,mode TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,result BLOB,baseline TEXT,proposal_state TEXT NOT NULL DEFAULT 'pending',attempt INTEGER NOT NULL DEFAULT 0,created TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(session_id,nonce,role,attempt));
 CREATE TABLE IF NOT EXISTS ai_studio_events(id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL,message_id INTEGER,actor_id INTEGER NOT NULL,action TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS idx_ai_studio_owner ON ai_studio_sessions(owner_id,updated);
 CREATE INDEX IF NOT EXISTS idx_ai_studio_history ON ai_studio_messages(session_id,id);
 ''')

def pack(value):return zlib.compress(json.dumps(value,ensure_ascii=False).encode('utf-8'))
def unpack(raw):return json.loads(zlib.decompress(raw)) if raw else None

def access(db,user,sid):
 row=db.execute('SELECT * FROM ai_studio_sessions WHERE id=? AND owner_id=?',(sid,user['id'])).fetchone()
 if not row:raise auth_control.AccessError(404,'본인의 AI 작성 대화만 열 수 있습니다.')
 auth_control.workspace_access(db,user,row['workspace_id'],True);return dict(row)

def draft_for(db,s):
 if not s['draft_id']:return None
 return workflow.load_draft(db,s['draft_id'],s['workspace_id'])

def documents(db,s):
 return db.execute('SELECT d.* FROM documents d JOIN ai_studio_documents a ON a.document_id=d.id WHERE a.session_id=? AND d.workspace_id=? AND d.deleted=0 ORDER BY d.id',(s['id'],s['workspace_id'])).fetchall()

def enriched(db,s,draft):
 if not draft:return None,None
 draft=copy.deepcopy(draft);draft['workspace']=dict(db.execute('SELECT * FROM workspaces WHERE id=?',(s['workspace_id'],)).fetchone());draft['gap_review']=handover_journey.snapshot(db,s['draft_id']);draft['report_documents']=[dict(r) for r in db.execute('SELECT id,name,revision FROM documents WHERE workspace_id=? AND deleted=0',(s['workspace_id'],))]
 preview=__import__('report_document').build(draft);return {'id':s['draft_id'],**draft,'edit_token':workflow.fingerprint(draft_for(db,s))},preview

def quota(db,user):
 import os
 limit=max(1,min(1000,int(os.environ.get('AI_DAILY_REQUEST_LIMIT','10'))));exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='staff_ai_usage'").fetchone();used=db.execute('SELECT count(*) FROM staff_ai_usage WHERE user_id=? AND day=CURRENT_DATE',(user['id'],)).fetchone()[0] if exists else 0
 return {'used':used,'limit':limit,'reset_timezone':'UTC','failed_attempts_included':True}

def view(db,s,user,before=None):
 draft,preview=enriched(db,s,draft_for(db,s));args=[s['id']];where='session_id=?'
 if before:where+=' AND id<?';args.append(int(before))
 rows=db.execute('SELECT * FROM ai_studio_messages WHERE '+where+' ORDER BY id DESC LIMIT 51',args).fetchall();more=len(rows)>50;messages=[]
 for row in reversed(rows[:50]):
  message=dict(row);message['result']=unpack(row['result']);messages.append(message)
 cfg=ai_draft.settings();return {'session':s,'messages':messages,'has_more':more,'draft':draft,'preview':preview,'documents':[{'id':d['id'],'name':d['name'],'characters':len(d['content'] or ''),'revision':d['revision']} for d in documents(db,s)],'questions':handover_journey.question_rows(db,draft_id=s['draft_id']) if s['draft_id'] else [],'ai':{'mode':cfg.get('mode','live'),'model':cfg.get('model',''),'quota':quota(db,user)}}

def save_questions(db,s,user,result):
 from batontouch.handover.questions import store_suggestions
 if not s['draft_id']:raise ValueError('먼저 인수인계서 초안을 문서에 반영하세요.')
 return store_suggestions(db,s['workspace_id'],s['draft_id'],user,workflow.fingerprint(draft_for(db,s)),{'questions':result['qa'],'references':result.get('references',{}),'model':result.get('model',''),'mode':result.get('mode','unknown')},selected=False)

def handle_conversation_request(handler,factory,method):
 path=urlsplit(handler.path).path
 if not path.startswith('/api/studio/'):return False
 try:
  body=auth_control.read_json(handler,128*1024) if method=='POST' else {};params=parse_qs(urlsplit(handler.path).query)
  with closing(factory()) as db:
   user=auth_control.identity(handler,db)
   if path=='/api/studio/sessions':
    if method=='GET':
     rows=[dict(r) for r in db.execute('SELECT * FROM ai_studio_sessions WHERE owner_id=? ORDER BY updated DESC,id DESC LIMIT 100',(user['id'],))];rows=[r for r in rows if auth_control.permission(db,user,r['workspace_id'])];handler.respond(200,{'sessions':rows});return True
    if method!='POST':raise auth_control.AccessError(405,'지원하지 않는 요청입니다.')
    workspace=body.get('workspace_id');title=body.get('title','새 인수인계 대화')
    if not isinstance(title,str) or not 1<=len(title.strip())<=200:raise ValueError('업무명을 200자 이내로 입력하세요.')
    created=not workspace
    if created:
     workspace=db.execute('INSERT INTO workspaces(title) VALUES(?)',(title.strip(),)).lastrowid;db.execute("INSERT INTO workspace_members(workspace_id,user_id,permission) VALUES(?,?,'editor')",(workspace,user['id']))
    else:auth_control.workspace_access(db,user,int(workspace),True)
    did=body.get('draft_id');draft=workflow.load_draft(db,int(did),int(workspace)) if did else None
    sid=db.execute('INSERT INTO ai_studio_sessions(owner_id,workspace_id,draft_id,title,created_workspace) VALUES(?,?,?,?,?)',(user['id'],workspace,did,title.strip(),int(created))).lastrowid
    if draft:
     for d in handover_journey.documents(db,draft,workspace):db.execute('INSERT OR IGNORE INTO ai_studio_documents VALUES(?,?)',(sid,d['id']))
    db.commit();handler.respond(201,view(db,access(db,user,sid),user));return True
   match=re.fullmatch(r'/api/studio/sessions/(\d+)(?:/(documents|messages|apply|reject|paper|paragraphs|paragraph-apply|paragraph-reject|paragraph-undo))?',path)
   if not match:raise auth_control.AccessError(404,'AI 작성 대화 기능을 찾을 수 없습니다.')
   sid=int(match[1]);s=access(db,user,sid);action=match[2]
   if action in __import__('studio_paragraphs').ACTIONS:
    __import__('studio_paragraphs').handle(handler,db,s,user,action,method,body);return True
   if method=='GET' and not action:handler.respond(200,view(db,s,user,params.get('before',[None])[0]));return True
   if method!='POST':raise auth_control.AccessError(405,'이 작업은 POST 요청을 사용하세요.')
   if action=='documents':
    ids=body.get('document_ids')
    if not isinstance(ids,list) or len(ids)>20 or any(type(i) is not int for i in ids):raise ValueError('이 대화에서 참고할 자료를 최대20개 선택하세요.')
    for i in ids:
     if not db.execute('SELECT 1 FROM documents WHERE id=? AND workspace_id=? AND deleted=0',(i,s['workspace_id'])).fetchone():raise auth_control.AccessError(403,'이 업무에 접근 가능한 등록 자료만 첨부할 수 있습니다.')
    db.execute('DELETE FROM ai_studio_documents WHERE session_id=?',(sid,))
    for i in dict.fromkeys(ids):db.execute('INSERT INTO ai_studio_documents VALUES(?,?)',(sid,i))
    db.commit();handler.respond(200,view(db,s,user));return True
   if action=='messages':
    text=body.get('text','');mode=body.get('mode','draft');nonce=body.get('nonce','');focus=body.get('focus_index')
    if not isinstance(text,str) or not 1<=len(text.strip())<=8000 or mode not in studio_ai.MODES or not isinstance(nonce,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',nonce):raise ValueError('메시지와 작성 모드를 확인하세요. 메시지는 8,000자 이내입니다.')
    current=draft_for(db,s);pending=db.execute("SELECT result,baseline FROM ai_studio_messages WHERE session_id=? AND role='assistant' AND mode IN ('draft','review') AND status='done' AND proposal_state='pending' ORDER BY id DESC LIMIT 1",(sid,)).fetchone();candidate=unpack(pending[0]).get('proposed_draft') if pending and pending['baseline']==(workflow.fingerprint(current) if current else None) else None
    if mode in ('review','qa') and not current and not candidate:raise ValueError('인수인계서 작성 모드에서 초안을 먼저 제안받으세요.')
    if mode=='qa' and not current:raise ValueError('초안을 문서에 반영한 뒤 예상 Q&A를 만드세요.')
    if focus is not None and (type(focus) is not int or not current or not 0<=focus<len(current['items'])):raise ValueError('수정할 문서 항목을 다시 선택하세요.')
    db.execute('BEGIN IMMEDIATE');existing=db.execute("SELECT * FROM ai_studio_messages WHERE session_id=? AND nonce=? AND role='user'",(sid,nonce)).fetchone()
    if existing:
     if existing['content']!=text or existing['mode']!=mode:raise auth_control.AccessError(409,'이미 사용된 요청번호입니다. 새 메시지로 전송하세요.')
     if existing['status']=='done':db.commit();handler.respond(200,view(db,s,user));return True
     if existing['status']=='pending' or not body.get('retry'):raise auth_control.AccessError(409,'처리 중이거나 실패한 요청입니다. 결과를 확인하고 직접 다시 시도하세요.')
     db.execute("UPDATE ai_studio_messages SET status='pending' WHERE id=?",(existing['id'],));mid=existing['id']
    else:
     if db.execute("SELECT 1 FROM ai_studio_messages WHERE session_id=? AND role='user' AND status='pending'",(sid,)).fetchone():raise auth_control.AccessError(409,'이 대화의 AI 요청이 처리 중입니다. 중복 호출하지 않았습니다.')
     mid=db.execute("INSERT INTO ai_studio_messages(session_id,nonce,role,mode,content,status) VALUES(?,?,'user',?,?,'pending')",(sid,nonce,mode,text)).lastrowid
    db.commit();baseline=workflow.fingerprint(current) if current else None;docs=documents(db,s)
    history=[{'role':r['role'],'text':r['content'][:1800]} for r in reversed(db.execute("SELECT role,content FROM ai_studio_messages WHERE session_id=? AND status='done' ORDER BY id DESC LIMIT 12",(sid,)).fetchall())]
    context={'previous_proposal':candidate if current else None,'mode':mode,'message':text,'focus_index':focus,'history':history,'draft':{k:(current or candidate)[k] for k in ('title','items')} if current or candidate else None,'existing_questions':[{'question':q['question'],'answer':q['reply']} for q in handover_journey.question_rows(db,draft_id=s['draft_id'])] if s['draft_id'] else []}
    try:
     if len(json.dumps(context,ensure_ascii=False))>90000:raise ValueError('대화와 문서가 너무 깁니다. 새 업무로 나누거나 특정 항목을 선택해 주세요.')
     result=ai_draft.generate(docs,actor=user,chat_context=context)
    except Exception as error:
     status=getattr(error,'http_status',400 if isinstance(error,ValueError) else 502);notice=str(error) if isinstance(error,ValueError) else 'AI 응답 처리 중 오류가 발생했습니다. 입력과 문서는 유지됩니다.'
     db.execute("UPDATE ai_studio_messages SET status='failed' WHERE id=?",(mid,));attempt=db.execute("SELECT count(*) FROM ai_studio_messages WHERE session_id=? AND nonce=? AND role='error'",(sid,nonce)).fetchone()[0]+1;db.execute("INSERT INTO ai_studio_messages(session_id,nonce,role,mode,content,status,attempt) VALUES(?,?,'error',?,?,'failed',?)",(sid,nonce,mode,notice,attempt));db.execute('UPDATE ai_studio_sessions SET updated=CURRENT_TIMESTAMP WHERE id=?',(sid,));db.commit();handler.respond(status,{'error':notice,'code':getattr(error,'error_code',None) or ('AI_APP_DAILY_LIMIT' if status==429 else 'AI_REQUEST_FAILED'),'upstream_status':getattr(error,'upstream_status',None),'nonce':nonce,'saved':True});return True
    # 공유 DB 연결의 오류를 모의 성공으로 대체하지 않는다. 전체 결과를 저장한 뒤 응답한다.
    attempt=db.execute("SELECT count(*) FROM ai_studio_messages WHERE session_id=? AND nonce=? AND role='assistant'",(sid,nonce)).fetchone()[0]+1;db.execute("UPDATE ai_studio_messages SET status='done' WHERE id=?",(mid,));result['document_revisions']={str(d['id']):d['revision'] for d in docs};db.execute("INSERT INTO ai_studio_messages(session_id,nonce,role,mode,content,status,result,baseline,attempt) VALUES(?,?,'assistant',?,?,'done',?,?,?)",(sid,nonce,mode,result['reply'],pack(result),baseline,attempt));db.execute('UPDATE ai_studio_sessions SET updated=CURRENT_TIMESTAMP WHERE id=?',(sid,));db.commit();handler.respond(201,view(db,access(db,user,sid),user));return True
   if action in ('apply','reject'):
    message=db.execute("SELECT * FROM ai_studio_messages WHERE id=? AND session_id=? AND role='assistant' AND status='done'",(body.get('message_id'),sid)).fetchone()
    if not message:raise auth_control.AccessError(404,'이 대화의 AI 제안만 반영할 수 있습니다.')
    if message['mode']=='paragraph':raise auth_control.AccessError(405,'문단 수정안의 전용 반영·취소 기능을 사용하세요.')
    result=unpack(message['result']);kind=body.get('kind','draft');event_action='문서 수정안 반영' if kind=='draft' else '예상 Q&A 추가'
    state_key=message['proposal_state']
    applied=(state_key=='applied' or state_key==kind+'_applied')
    if action=='reject':
     if applied:raise auth_control.AccessError(409,'이미 반영한 제안입니다. 새 수정안을 요청하세요.')
     db.execute("UPDATE ai_studio_messages SET proposal_state='rejected' WHERE id=?",(message['id'],));db.execute('INSERT INTO ai_studio_events(session_id,message_id,actor_id,action) VALUES(?,?,?,?)',(sid,message['id'],user['id'],'제안 취소'));db.commit();handler.respond(200,view(db,s,user));return True
    if applied:handler.respond(200,view(db,s,user));return True
    if state_key=='rejected':raise auth_control.AccessError(409,'취소한 제안입니다. 새 수정안을 요청하세요.')
    current=draft_for(db,s)
    if (workflow.fingerprint(current) if current else None)!=message['baseline']:raise auth_control.AccessError(409,'다른 화면에서 문서가 변경됐습니다. 현재 문서를 확인하고 새 수정안을 요청하세요. 기존 내용은 덮어쓰지 않았습니다.')
    for did,revision in result.get('document_revisions',{}).items():
     if not db.execute('SELECT 1 FROM documents WHERE id=? AND workspace_id=? AND revision=? AND deleted=0',(int(did),s['workspace_id'],revision)).fetchone():raise auth_control.AccessError(409,'근거 자료가 변경됐습니다. 다시 분석한 제안을 확인하세요.')
    db.execute('BEGIN IMMEDIATE')
    if kind=='qa':
     if not result.get('qa'):raise ValueError('추가할 예상 Q&A가 없습니다.')
     save_questions(db,s,user,result)
    elif kind=='draft':
     proposal=copy.deepcopy(result.get('proposed_draft'))
     if not proposal:raise ValueError('이 응답에는 문서 수정안이 없습니다.')
     indices=body.get('selected_indices',list(range(len(proposal['items']))));edits=body.get('edited_items',{});title=body.get('title',proposal['title'])
     if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(proposal['items']) for i in indices) or not indices:raise ValueError('반영할 항목을 하나 이상 선택하세요.')
     if not isinstance(edits,dict) or not isinstance(title,str) or not 1<=len(title)<=200:raise ValueError('문서 제목과 수정안을 확인하세요.')
     target=copy.deepcopy(current or proposal);target['title']=title;target['references']={**(current or {}).get('references',{}),**result.get('references',{})}
     if not current:target['items']=[{'category':i['category'],'text':'확인 필요','source_ids':[]} for i in proposal['items']]
     for i in indices:
      item=copy.deepcopy(proposal['items'][i]);text=edits.get(str(i),item['text'])
      if not isinstance(text,str) or not 1<=len(text)<=12000:raise ValueError('반영할 내용을 12,000자 이내로 입력하세요.')
      if text!=item['text']:
       item['text']=text if any(t in text for t in ('확인 필요','확인되지 않음','확인필요')) else text+'\n[직접 수정 · 원문 근거 확인 필요]';item['source_ids']=[]
      target['items'][i]=item
     ai_draft.validate_draft(target,target['references']);target['reviewed']=False;target['mode']=result.get('mode','unknown');target['model']=result.get('model','');target['studio_session_id']=sid
     if current:
      workflow.baseline(db,s['draft_id'],s['workspace_id'],current);target.setdefault('original',{'title':current['title'],'items':current['items']});db.execute('UPDATE drafts SET payload=? WHERE id=? AND workspace_id=?',(json.dumps(target,ensure_ascii=False),s['draft_id'],s['workspace_id']))
     else:s['draft_id']=db.execute('INSERT INTO drafts(workspace_id,payload) VALUES(?,?)',(s['workspace_id'],json.dumps(target,ensure_ascii=False))).lastrowid;db.execute('UPDATE ai_studio_sessions SET draft_id=? WHERE id=?',(s['draft_id'],sid))
     workflow.record_version(db,s['draft_id'],s['workspace_id'],target,user['username'],'studio_applied');db.execute('UPDATE ai_studio_sessions SET title=? WHERE id=?',(title,sid))
     if s['created_workspace']:db.execute('UPDATE workspaces SET title=? WHERE id=?',(title,s['workspace_id']))
    else:raise ValueError('반영할 제안 종류를 확인하세요.')
    db.execute('UPDATE ai_studio_messages SET proposal_state=? WHERE id=?',(kind+'_applied',message['id']));db.execute('INSERT INTO ai_studio_events(session_id,message_id,actor_id,action) VALUES(?,?,?,?)',(sid,message['id'],user['id'],event_action));db.execute('UPDATE ai_studio_sessions SET updated=CURRENT_TIMESTAMP WHERE id=?',(sid,));db.commit();handler.respond(200,view(db,access(db,user,sid),user));return True
   raise auth_control.AccessError(404,'지원하지 않는 AI 작성 대화 작업입니다.')
 except auth_control.AccessError as error:handler.respond(error.status,{'error':error.message})
 except (ValueError,TypeError,KeyError) as error:handler.respond(getattr(error,'http_status',400),{'error':str(error) if isinstance(error,ValueError) else '요청 항목을 확인하세요.'})
 except sqlite3.Error:handler.respond(409,{'error':'다른 요청과 저장이 충돌했습니다. 입력은 유지됩니다. 직접 다시 시도하세요.'})
 return True

# 이전 확장 모듈·도구와의 호출 호환성.
handle = handle_conversation_request
ensure = ensure_conversation_schema
