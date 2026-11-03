"""Draft-aware missing information checks and request-scoped conversation. No automatic approval."""
import copy,json,re,sqlite3
from contextlib import closing
from urllib.parse import urlsplit,parse_qs
import auth_control,ai_draft,handover_workflow as workflow

def ensure(db):
 cols={r['name'] for r in db.execute('pragma table_info(followups)')}
 for name,definition in [('request_id','INTEGER'),('origin',"TEXT NOT NULL DEFAULT 'manual'"),('reason',"TEXT NOT NULL DEFAULT ''"),('source_ids',"TEXT NOT NULL DEFAULT '[]'"),('baseline',"TEXT NOT NULL DEFAULT ''"),('application',"TEXT NOT NULL DEFAULT 'none'"),('proposal','TEXT')]:
  if name not in cols:db.execute('ALTER TABLE followups ADD COLUMN '+name+' '+definition)
 db.executescript('''CREATE TABLE IF NOT EXISTS journey_checks(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,draft_id INTEGER NOT NULL,baseline TEXT NOT NULL,payload TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS followup_events(id INTEGER PRIMARY KEY,followup_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS journey_progress(workspace_id INTEGER PRIMARY KEY,step INTEGER NOT NULL DEFAULT 1,draft_id INTEGER,updated TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS journey_user_state(user_id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,updated TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS journey_library_imports(workspace_id INTEGER NOT NULL,source_document INTEGER NOT NULL,source_revision INTEGER NOT NULL,new_document INTEGER NOT NULL,PRIMARY KEY(workspace_id,source_document,source_revision));
 CREATE INDEX IF NOT EXISTS idx_followups_request ON followups(request_id,id);''')

def question_rows(db,draft_id=None,request_id=None):
 column,value=('request_id',request_id) if request_id is not None else ('draft_id',draft_id)
 result=[]
 for row in db.execute('SELECT * FROM followups WHERE '+column+'=? ORDER BY id',(value,)):
  item=dict(row);item['source_ids']=json.loads(item['source_ids']);item['proposal']=json.loads(item['proposal']) if item['proposal'] else None
  item['request_completed']=bool(item['request_id'] and db.execute("SELECT 1 FROM handover_requests WHERE id=? AND state='completed'",(item['request_id'],)).fetchone())
  item['events']=[dict(e)|{'payload':json.loads(e['payload'])} for e in db.execute('SELECT actor_id,action,payload,created FROM followup_events WHERE followup_id=? ORDER BY id',(item['id'],))];result.append(item)
 return result

def snapshot(db,draft_id):
 questions=question_rows(db,draft_id=draft_id)
 return {'questions':questions,'unresolved':sum(q['state'] in ('open','deferred') for q in questions)}

def event(db,q,user,action,payload):db.execute('INSERT INTO followup_events(followup_id,actor_id,action,payload) VALUES(?,?,?,?)',(q,user['id'],action,json.dumps(payload,ensure_ascii=False)))

def documents(db,draft,workspace):
 ids={r['document_id'] for r in draft.get('references',{}).values() if isinstance(r,dict) and type(r.get('document_id')) is int}
 docs=db.execute('SELECT * FROM documents WHERE workspace_id=? AND deleted=0 ORDER BY id',(workspace,)).fetchall();return [d for d in docs if d['id'] in ids]

def handle(handler,factory,method):
 path=urlsplit(handler.path).path
 if not path.startswith('/api/journey/'):return False
 try:
  with closing(factory()) as db:
   user=auth_control.identity(handler,db);body=auth_control.read_json(handler,2*1024*1024) if method=='POST' else {k:v[0] for k,v in parse_qs(urlsplit(handler.path).query).items()}
   if path=='/api/journey/active' and method=='GET':
    row=db.execute('SELECT workspace_id FROM journey_user_state WHERE user_id=?',(user['id'],)).fetchone();handler.respond(200,{'workspace_id':row[0] if row and auth_control.permission(db,user,row[0]) else None});return True
   if path=='/api/journey/dashboard' and method=='GET':
    from handover_requests import bind_pending_requests
    bind_pending_requests(db,user);db.commit();workspaces=[dict(w) for w in db.execute('SELECT * FROM workspaces ORDER BY id DESC') if auth_control.permission(db,user,w['id'])]
    draft_rows=[]
    for w in workspaces:
     for d in db.execute('SELECT id,payload,created FROM drafts WHERE workspace_id=? AND deleted=0 ORDER BY id DESC',(w['id'],)):
      p=json.loads(d['payload']);latest=db.execute('SELECT state,draft_fingerprint FROM handover_requests WHERE draft_id=? AND sender_account=? ORDER BY id DESC LIMIT 1',(d['id'],user['id'])).fetchone()
      if latest and latest['state']!='needs_info' and latest['draft_fingerprint']==workflow.fingerprint(p):continue
      draft_rows.append(dict(id=d['id'],workspace_id=w['id'],workspace_title=w['title'],title=p['title'],created=d['created'],reviewed=p.get('reviewed',False)))
    counts={}
    for label,sql in [('received',"recipient_account=? AND state IN ('requested','reviewing','needs_info')"),('sent',"sender_account=? AND state!='completed'"),('completed',"(sender_account=? OR recipient_account=?) AND state='completed'")]:counts[label]=db.execute('SELECT count(*) FROM handover_requests WHERE '+sql,(user['id'],user['id']) if label=='completed' else (user['id'],)).fetchone()[0]
    handler.respond(200,dict(counts=dict(drafts=len(draft_rows),**counts),drafts=draft_rows[:30],workspaces=workspaces));return True
   req=None
   if body.get('request_id'):
    import handover_requests
    req=handover_requests.request_row(db,user,int(body['request_id']));workspace=req['workspace_id'];draft_id=req['draft_id']
   else:
    workspace=int(body.get('workspace_id') or handler.headers.get('X-Workspace-Id','1'));auth_control.workspace_access(db,user,workspace,method=='POST');draft_id=int(body.get('draft_id') or 0)
   if req and path not in ('/api/journey/questions','/api/journey/question','/api/journey/answer','/api/journey/propose','/api/journey/apply'):raise auth_control.AccessError(403,'요청 상세에서는 해당 요청의 질문·답변만 처리할 수 있습니다.')
   if path=='/api/journey/library' and method=='GET':
    rows=[dict(r) for r in db.execute('SELECT d.id,d.name,d.workspace_id,w.title AS workspace_title,d.revision FROM documents d JOIN workspaces w ON w.id=d.workspace_id WHERE d.deleted=0 AND d.workspace_id!=? AND instr(lower(d.name),lower(?))>0 ORDER BY d.id DESC',(workspace,str(body.get('q',''))[:100])) if auth_control.permission(db,user,r['workspace_id'])];handler.respond(200,{'items':rows[:200],'total':len(rows)});return True
   if path=='/api/journey/import' and method=='POST':
    ids=body.get('document_ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(type(i) is not int for i in ids):raise ValueError('가져올 자료를 1~20개 선택하세요.')
    db.execute('BEGIN IMMEDIATE');added=[]
    for key in set(ids):
     doc=db.execute('SELECT * FROM documents WHERE id=? AND deleted=0',(key,)).fetchone()
     if not doc:raise ValueError('삭제되었거나 없는 자료입니다.')
     auth_control.workspace_access(db,user,doc['workspace_id'])
     imported=db.execute('SELECT j.new_document FROM journey_library_imports j JOIN documents d ON d.id=j.new_document WHERE j.workspace_id=? AND j.source_document=? AND j.source_revision=? AND d.deleted=0',(workspace,key,doc['revision'])).fetchone()
     if imported:added.append(imported[0]);continue
     cursor=db.execute('INSERT INTO documents(name,content,sources,workspace_id) VALUES(?,?,?,?)',(doc['name'],doc['content'],doc['sources'],workspace));newid=cursor.lastrowid
     db.execute('INSERT INTO document_files(document_id,workspace_id,revision,name,raw) SELECT ?,?,1,name,raw FROM document_files WHERE document_id=? AND revision=?',(newid,workspace,key,doc['revision']));db.execute('INSERT INTO journey_library_imports VALUES(?,?,?,?) ON CONFLICT(workspace_id,source_document,source_revision) DO UPDATE SET new_document=excluded.new_document',(workspace,key,doc['revision'],newid));added.append(newid)
    db.commit();handler.respond(201,{'document_ids':added});return True
   if path=='/api/journey/progress':
    if method=='POST':
     step=int(body.get('step',1))
     if not 1<=step<=5:raise ValueError('단계를 확인하세요.')
     if draft_id:workflow.load_draft(db,draft_id,workspace)
     db.execute('INSERT INTO journey_user_state(user_id,workspace_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET workspace_id=excluded.workspace_id,updated=CURRENT_TIMESTAMP',(user['id'],workspace))
     db.execute('INSERT INTO journey_progress(workspace_id,step,draft_id) VALUES(?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET step=excluded.step,draft_id=excluded.draft_id,updated=CURRENT_TIMESTAMP',(workspace,step,draft_id or None));db.commit()
    row=db.execute('SELECT * FROM journey_progress WHERE workspace_id=?',(workspace,)).fetchone();handler.respond(200,dict(row) if row else {'step':1});return True
   if path=='/api/journey/questions' and method=='GET':
    if not req:workflow.load_draft(db,draft_id,workspace)
    rows=question_rows(db,request_id=req['id']) if req else question_rows(db,draft_id=draft_id);handler.respond(200,{'questions':rows});return True
   if method!='POST':raise ValueError('지원하지 않는 요청입니다.')
   if req and req['state']=='completed':raise ValueError('완료된 인수인계는 이력을 보존하며 수정하지 않습니다.')
   if path=='/api/journey/question':
    if not req:raise ValueError('받은 인수인계에서 추가 질문을 작성하세요.')
    if user['id']!=req['recipient_account']:raise auth_control.AccessError(403,'지정된 인수자만 추가 질문을 작성할 수 있습니다.')
    question=body.get('question','')
    if not isinstance(question,str):raise ValueError('질문은 글로 입력하세요.')
    question=question.strip()
    if not 1<=len(question)<=2000:raise ValueError('질문을 입력하세요.')
    cursor=db.execute('INSERT INTO followups(workspace_id,draft_id,item_index,question,actor,request_id,origin) VALUES(?,?,-1,?,?,?,\'recipient\')',(workspace,draft_id,question,user['username'],req['id']));event(db,cursor.lastrowid,user,'질문 작성',{'question':question});db.commit();handler.respond(201,{'saved':True});return True
   if req and user['id']!=req['sender_account']:raise auth_control.AccessError(403,'인계자만 답변·문서 반영을 할 수 있습니다.')
   auth_control.workspace_access(db,user,workspace,True);draft=workflow.load_draft(db,draft_id,workspace)
   if path=='/api/journey/check':
    if workflow.fingerprint(draft)!=body.get('fingerprint'):raise ValueError('작성 내용을 먼저 저장한 뒤 점검하세요.')
    docs=documents(db,draft,workspace)
    if not docs:raise ValueError('출처가 연결된 업무자료를 먼저 등록하세요.')
    existing=question_rows(db,draft_id=draft_id);baseline=workflow.fingerprint(draft)
    result=ai_draft.generate(docs,gap_context={'draft':{'title':draft['title'],'items':draft['items']},'existing_questions':[{'question':q['question'],'answer':q['reply'],'state':q['state']} for q in existing]})
    db.execute('BEGIN IMMEDIATE')
    if workflow.fingerprint(workflow.load_draft(db,draft_id,workspace))!=baseline:raise ValueError('점검 중 문서가 변경됐습니다. 기존 작성 내용은 유지되며 다시 점검하세요.')
    known={re.sub(r'\s+','',q['question']).casefold() for q in existing};added=0
    for q in result['questions']:
     key=re.sub(r'\s+','',q['question']).casefold()
     if key in known:continue
     known.add(key);cur=db.execute('INSERT INTO followups(workspace_id,draft_id,item_index,question,actor,origin,reason,source_ids,baseline) VALUES(?,?,?,?,?,\'ai\',?,?,?)',(workspace,draft_id,q['target_index'],q['question'],user['username'],q['reason'],json.dumps(q['source_ids']),baseline));event(db,cur.lastrowid,user,'AI 질문 제안',q);added+=1
    db.execute('INSERT INTO journey_checks(workspace_id,draft_id,baseline,payload) VALUES(?,?,?,?)',(workspace,draft_id,baseline,json.dumps(result,ensure_ascii=False)));db.commit();handler.respond(201,{'added':added,'summary':result['summary'],'questions':question_rows(db,draft_id=draft_id)});return True
   q=db.execute('SELECT * FROM followups WHERE id=? AND workspace_id=? AND draft_id=?',(body.get('id'),workspace,draft_id)).fetchone()
   if not q or req and q['request_id']!=req['id']:raise auth_control.AccessError(403,'해당 인수인계의 질문만 처리할 수 있습니다.')
   if q['request_id'] and db.execute("SELECT 1 FROM handover_requests WHERE id=? AND state='completed'",(q['request_id'],)).fetchone():raise ValueError('완료된 인수인계의 질문·답변은 변경하지 않습니다.')
   if path=='/api/journey/answer':
    answer=body.get('reply','');status=body.get('state','resolved')
    if status not in ('open','resolved','deferred','not_applicable') or not isinstance(answer,str) or len(answer)>8000 or status=='resolved' and not answer.strip():raise ValueError('답변과 처리 상태를 확인하세요.')
    db.execute('BEGIN IMMEDIATE');q=db.execute('SELECT * FROM followups WHERE id=?',(q['id'],)).fetchone()
    event(db,q['id'],user,'답변·상태 변경',{'before':{'reply':q['reply'],'state':q['state']},'after':{'reply':answer,'state':status}})
    db.execute("UPDATE followups SET reply=?,state=?,reply_actor=?,proposal=NULL,application='none',updated=CURRENT_TIMESTAMP WHERE id=?",(answer,status,user['username'],q['id']));db.commit();handler.respond(200,{'saved':True});return True
   if path=='/api/journey/propose':
    if q['state']!='resolved' or not q['reply']:raise ValueError('답변을 먼저 저장하세요.')
    baseline=workflow.fingerprint(draft);answer_hash=workflow.fingerprint(q['reply']);result=ai_draft.generate(documents(db,draft,workspace),gap_apply_context={'draft':{'title':draft['title'],'items':draft['items']},'question':q['question'],'answer':q['reply']})
    db.execute('BEGIN IMMEDIATE');current=db.execute('SELECT reply FROM followups WHERE id=?',(q['id'],)).fetchone()[0]
    if workflow.fingerprint(workflow.load_draft(db,draft_id,workspace))!=baseline or workflow.fingerprint(current)!=answer_hash:raise ValueError('생성 중 문서나 답변이 변경됐습니다. 다시 확인하세요.')
    result.update(baseline=baseline,answer_hash=answer_hash);db.execute("UPDATE followups SET proposal=?,application='proposed' WHERE id=?",(json.dumps(result,ensure_ascii=False),q['id']));event(db,q['id'],user,'반영안 제안',result);db.commit();handler.respond(200,result);return True
   if path=='/api/journey/apply':
    proposal=json.loads(q['proposal'] or '{}');text=body.get('text')
    if not proposal or not isinstance(text,str) or not 1<=len(text)<=20000 or workflow.fingerprint(draft)!=proposal['baseline'] or workflow.fingerprint(q['reply'])!=proposal['answer_hash']:raise ValueError('문서·답변이 변경되었거나 반영안이 없습니다. 다시 확인하세요.')
    db.execute('BEGIN IMMEDIATE')
    if workflow.fingerprint(workflow.load_draft(db,draft_id,workspace))!=proposal['baseline']:raise ValueError('문서가 변경됐습니다. 다시 확인하세요.')
    latest=db.execute('SELECT reply,proposal FROM followups WHERE id=?',(q['id'],)).fetchone()
    if not latest['proposal'] or workflow.fingerprint(latest['reply'])!=proposal['answer_hash']:raise ValueError('답변이나 반영안이 변경됐습니다. 다시 확인하세요.')
    workflow.baseline(db,draft_id,workspace,draft)
    draft.setdefault('original',{'title':draft['title'],'items':copy.deepcopy(draft['items'])})
    draft['items'][proposal['target_index']]['text']=text;draft['reviewed']=False;db.execute('UPDATE drafts SET payload=? WHERE id=?',(json.dumps(draft,ensure_ascii=False),draft_id));workflow.record_version(db,draft_id,workspace,draft,user['username'],'answer_applied');db.execute("UPDATE followups SET application='applied' WHERE id=?",(q['id'],));event(db,q['id'],user,'반영 승인',{'target_index':proposal['target_index'],'text':text});db.commit();handler.respond(200,{'id':draft_id,**draft,'edit_token':workflow.fingerprint(draft)});return True
   raise ValueError('지원하지 않는 작업입니다.')
 except auth_control.AccessError as e:handler.respond(e.status,{'error':e.message})
 except sqlite3.Error:handler.respond(409,{'error':'저장 충돌이 발생했습니다. 입력 내용은 유지되며 다시 시도할 수 있습니다.'})
 except (ValueError,TypeError,KeyError,IndexError,OverflowError) as e:handler.respond(400,{'error':str(e) if isinstance(e,ValueError) else '요청 또는 AI 응답 형식을 확인하세요.'})
 return True

def backup_extension(db,workspace):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='followup_events'").fetchone():return None
 questions=[dict(r) for r in db.execute('SELECT id,origin,reason,source_ids,application FROM followups WHERE workspace_id=?',(workspace,))]
 events=[dict(r) for r in db.execute('SELECT e.followup_id,e.action,e.payload,e.created FROM followup_events e JOIN followups q ON q.id=e.followup_id WHERE q.workspace_id=? ORDER BY e.id',(workspace,))]
 return {'version':1,'questions':questions,'events':events}

def restore_extension(db,extension,question_map,document_map,user):
 if extension is None:return
 if not isinstance(extension,dict) or extension.get('version')!=1 or not isinstance(extension.get('questions'),list) or not isinstance(extension.get('events'),list) or len(extension['questions'])>5000 or len(extension['events'])>20000:raise ValueError('질문 이력 백업 형식이 올바르지 않습니다.')
 def remap(key):
  match=re.fullmatch(r'D(\d+)-S(\d+)',key) if isinstance(key,str) else None
  return 'D'+str(document_map[int(match[1])])+'-S'+match[2] if match and int(match[1]) in document_map else None
 for q in extension['questions']:
  if not isinstance(q,dict) or q.get('id') not in question_map or q.get('origin') not in ('manual','ai','recipient') or not isinstance(q.get('reason'),str) or len(q['reason'])>4000:raise ValueError('질문 백업 항목을 확인하세요.')
  ids=json.loads(q['source_ids'])
  if not isinstance(ids,list):raise ValueError('질문 출처 백업 형식을 확인하세요.')
  ids=[mapped for source in ids if (mapped:=remap(source))]
  db.execute("UPDATE followups SET origin=?,reason=?,source_ids=?,application='restored',proposal=NULL,request_id=NULL WHERE id=?",(q['origin'],q['reason'],json.dumps(ids),question_map[q['id']]))
 for e in extension['events']:
  if not isinstance(e,dict) or e.get('followup_id') not in question_map or not isinstance(e.get('action'),str) or len(e['action'])>200 or not isinstance(e.get('payload'),str) or len(e['payload'])>100000 or not isinstance(e.get('created'),str) or len(e['created'])>100:raise ValueError('질문 변경 이력 백업을 확인하세요.')
  payload=json.loads(e['payload'])
  if not isinstance(payload,dict):raise ValueError('질문 변경 이력 형식을 확인하세요.')
  db.execute('INSERT INTO followup_events(followup_id,actor_id,action,payload,created) VALUES(?,?,?,?,?)',(question_map[e['followup_id']],user['id'],e['action']+' (복원된 기록)',e['payload'],e['created']))
