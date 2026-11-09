"""Authorized library file views and non-destructive reuse of request snapshots."""
import json,sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,quote
from batontouch.auth import sessions as auth_control; from batontouch.handover import requests as handover_requests

def source(db,user,document_id,request_id=0):
 if request_id:
  req=handover_requests.request_row(db,user,request_id)
  docs=json.loads(req['documents']);doc=next((d for d in docs if d['id']==document_id),None)
  if not doc:raise auth_control.AccessError(404,'전달된 자료를 찾을 수 없습니다.')
  binary=db.execute('SELECT raw FROM request_files WHERE request_id=? AND revision=? AND document_id=?',(request_id,req['revision'],document_id)).fetchone()
  doc={**doc,'workspace_id':req['workspace_id']}
 else:
  row=db.execute('SELECT * FROM documents WHERE id=? AND deleted=0',(document_id,)).fetchone()
  if not row:raise auth_control.AccessError(404,'등록 자료를 찾을 수 없습니다.')
  doc=dict(row);auth_control.workspace_access(db,user,doc['workspace_id'])
  binary=db.execute('SELECT raw FROM document_files WHERE document_id=? AND revision=?',(document_id,doc['revision'])).fetchone()
 if isinstance(doc.get('sources'),str):doc['sources']=json.loads(doc['sources'])
 return doc,bytes(binary['raw']) if binary else None

def impact(db,doc):
 key=doc['id'];drafts=[]
 for r in db.execute('SELECT id,payload FROM drafts WHERE workspace_id=? AND deleted=0',(doc['workspace_id'],)):
  p=json.loads(r['payload'])
  if any(x.get('document_id')==key for x in p.get('references',{}).values()) or any(x.get('id')==key for x in p.get('documents',[])):drafts.append({'id':r['id'],'title':p.get('title','인수인계서')})
 sessions=db.execute('SELECT count(*) FROM ai_studio_documents WHERE document_id=?',(key,)).fetchone()[0]
 requests=sum(any(x.get('id')==key for x in json.loads(r['documents'])) for r in db.execute('SELECT documents FROM handover_requests WHERE workspace_id=?',(doc['workspace_id'],)))
 return {'drafts':drafts,'conversations':sessions,'requests':requests,'revision':doc['revision']}

def selected_documents(db, user, items):
 """선택 전체의 권한과 버전을 검사한 뒤에만 변경을 허용한다."""
 if not isinstance(items, list) or not 1 <= len(items) <= 200:
  raise ValueError('삭제할 자료를 1~200개 선택하세요.')
 documents=[];seen=set()
 for item in items:
  if not isinstance(item,dict) or type(item.get('id')) is not int or type(item.get('revision')) is not int:
   raise ValueError('삭제할 자료와 버전을 다시 확인하세요.')
  if item.get('request_id') or item['id'] in seen:
   raise ValueError('전달받은 자료 또는 중복된 항목은 삭제할 수 없습니다.')
  seen.add(item['id'])
  doc=db.execute('SELECT id,name,workspace_id,revision FROM documents WHERE id=? AND deleted=0',(item['id'],)).fetchone()
  if not doc:raise auth_control.AccessError(409,'일부 자료가 이미 삭제되었습니다. 목록을 새로 불러오세요.')
  auth_control.workspace_access(db,user,doc['workspace_id'],True)
  if doc['revision']!=item['revision']:
   raise auth_control.AccessError(409,'일부 자료가 변경되었습니다. 삭제 영향을 다시 확인하세요.')
  documents.append(dict(doc))
 return documents


def handle_file_request(handler,factory,method):
 path=urlsplit(handler.path).path
 if not path.startswith('/api/library/file') and path not in ('/api/library/reuse','/api/library/targets'):return False
 try:
  body=auth_control.read_json(handler) if method=='POST' else {k:v[0] for k,v in parse_qs(urlsplit(handler.path).query).items()}
  with closing(factory()) as db:
   user=auth_control.identity(handler,db)
   if path in ('/api/library/files/delete-preview','/api/library/files/delete'):
    if method!='POST':raise auth_control.AccessError(405,'POST 요청을 사용하세요.')
    db.execute('BEGIN IMMEDIATE')
    documents=selected_documents(db,user,body.get('items'))
    if path.endswith('delete-preview'):
     affected={d['id'] for doc in documents for d in impact(db,doc)['drafts']}
     handler.respond(200,{'items':documents,'draft_count':len(affected)});return True
    for doc in documents:db.execute('UPDATE documents SET deleted=1 WHERE id=?',(doc['id'],))
    auth_control.audit(db,handler,'자료 일괄 논리 삭제',details=json.dumps([doc['id'] for doc in documents]))
    db.commit();handler.respond(200,{'deleted':len(documents)});return True
   if path=='/api/library/targets':
    if method!='GET':raise auth_control.AccessError(405,'조회 요청을 사용하세요.')
    wid=int(body.get('workspace_id',0));auth_control.workspace_access(db,user,wid,True)
    handler.respond(200,{'drafts':[dict(r) for r in db.execute("SELECT id,json_extract(payload,'$.title') AS title FROM drafts WHERE workspace_id=? AND deleted=0 ORDER BY id DESC",(wid,))],'conversations':[dict(r) for r in db.execute('SELECT id,title FROM ai_studio_sessions WHERE workspace_id=? AND owner_id=? ORDER BY updated DESC,id DESC',(wid,user['id']))]});return True
   if path=='/api/library/reuse':
    if method!='POST':raise auth_control.AccessError(405,'POST 요청을 사용하세요.')
    target=int(body.get('workspace_id',0));auth_control.workspace_access(db,user,target,True)
    ids=body.get('items');result=[]
    if not isinstance(ids,list) or not 1<=len(ids)<=20:raise ValueError()
    db.execute('BEGIN IMMEDIATE')
    for item in ids:
     doc,raw=source(db,user,int(item['document_id']),int(item.get('request_id',0)))
     if not item.get('request_id') and doc['workspace_id']==target:result.append(doc['id']);continue
     existing= db.execute('SELECT d.id FROM documents d JOIN document_files f ON f.document_id=d.id AND f.revision=d.revision WHERE d.workspace_id=? AND d.deleted=0 AND f.raw=?',(target,raw)).fetchone() if raw is not None else None
     if existing:result.append(existing['id']);continue
     content=doc.get('content') or '\n'.join(s['text'] for s in doc.get('sources',[]))
     key=db.execute('INSERT INTO documents(name,content,sources,workspace_id) VALUES(?,?,?,?)',(doc['name'],content,json.dumps(doc.get('sources',[]),ensure_ascii=False),target)).lastrowid
     if raw is not None:db.execute('INSERT INTO document_files(document_id,workspace_id,revision,name,raw) VALUES(?,?,1,?,?)',(key,target,doc['name'],raw))
     result.append(key)
    db.commit();handler.respond(201,{'document_ids':list(dict.fromkeys(result))});return True
   if method!='GET':raise auth_control.AccessError(405,'조회 요청을 사용하세요.')
   doc,raw=source(db,user,int(body.get('document_id',0)),int(body.get('request_id',0)))
   if path=='/api/library/file/impact':
    if body.get('request_id'):raise auth_control.AccessError(403,'전달받은 원본은 삭제할 수 없습니다.')
    auth_control.workspace_access(db,user,doc['workspace_id'],True);handler.respond(200,impact(db,doc));return True
   if path=='/api/library/file':handler.respond(200,{k:v for k,v in doc.items() if k!='raw'}|{'has_original':raw is not None});return True
   if path!='/api/library/file/raw':raise auth_control.AccessError(404,'자료 기능이 없습니다.')
   if raw is None:raise auth_control.AccessError(404,'이전 자료의 원본 파일은 보관되어 있지 않습니다. 추출 본문은 확인할 수 있습니다.')
   pdf=Path(doc['name']).suffix.lower()=='.pdf' and body.get('inline')=='1'
   handler.send_response(200);handler.send_header('Content-Type','application/pdf' if pdf else 'application/octet-stream');handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Content-Disposition',('inline' if pdf else 'attachment')+"; filename=source; filename*=UTF-8''"+quote(doc['name'],safe=''));handler.send_header('Content-Length',str(len(raw)));handler.end_headers();handler.wfile.write(raw)
 except auth_control.AccessError as e:handler.respond(e.status,{'error':e.message})
 except (ValueError,TypeError,KeyError):handler.respond(400,{'error':'자료 선택과 연결할 업무를 확인하세요.'})
 except sqlite3.Error:handler.respond(503,{'error':'자료 저장소를 확인하지 못했습니다. 기존 자료는 유지됩니다.'})
 return True

# 이전 확장 모듈·도구와의 호출 호환성.
handle = handle_file_request
