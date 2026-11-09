"""Authorized work lists and event notifications; no document bodies or AI calls."""
import json
import sqlite3
from contextlib import closing
from urllib.parse import parse_qs,urlsplit

from batontouch.auth import sessions as auth_control
from batontouch.handover import workflow as workflow

STATES={'all','draft','reviewed','requested','reviewing','needs_info','accepted','completed'}
LABELS={'draft':'작성 중','reviewed':'검토 완료','requested':'인수 요청','reviewing':'인수자 확인 중','needs_info':'보완 요청','accepted':'인수 수락','completed':'완료'}


def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS user_event_reads(user_id INTEGER NOT NULL,event_key TEXT NOT NULL,read_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,event_key))')


def stamp(value):return str(value or '').replace('T',' ').removesuffix('Z')


def data(db,user):
 from batontouch.handover import requests as handover_requests
 handover_requests.bind_pending_requests(db,user);db.commit()
 allowed={r['id']:dict(r) for r in db.execute('SELECT id,title FROM workspaces') if auth_control.permission(db,user,r['id'])}
 requests=[dict(r) for r in db.execute('SELECT id,workspace_id,draft_id,sender_account,recipient_account,state,created,updated,draft_fingerprint,sender_snapshot,recipient_snapshot,json_extract(payload,\'$.title\') AS title FROM handover_requests WHERE sender_account=? OR recipient_account=? ORDER BY id DESC',(user['id'],user['id']))]
 latest={};items=[];drafts=[]
 for r in requests:
  latest.setdefault(r['draft_id'],r)
  peer=json.loads(r['sender_snapshot'] if r['recipient_account']==user['id'] else r['recipient_snapshot'])
  items.append({k:r[k] for k in ('id','workspace_id','draft_id','state','created','updated','title')}|{'kind':'request','box':'inbox' if r['recipient_account']==user['id'] else 'sent','workspace_title':allowed.get(r['workspace_id'],{}).get('title',''),'person':str(peer.get('name','')),'stage':7 if r['state']=='completed' else 6 if r['state']=='accepted' else 3 if r['state']=='needs_info' else 5})
 progress={r['workspace_id']:dict(r) for r in db.execute('SELECT * FROM journey_progress')}
 for r in db.execute('SELECT d.id,d.workspace_id,d.payload,d.created,(SELECT max(created) FROM draft_versions v WHERE v.draft_id=d.id) AS modified,(SELECT max(id) FROM draft_versions v WHERE v.draft_id=d.id) AS version_order FROM drafts d WHERE d.deleted=0'):
  if r['workspace_id'] not in allowed:continue
  payload=json.loads(r['payload']);req=latest.get(r['id'])
  if req and req['state']!='needs_info' and req['draft_fingerprint']==workflow.fingerprint(payload):continue
  p=progress.get(r['workspace_id'],{})
  row={'kind':'draft','id':r['id'],'draft_id':r['id'],'workspace_id':r['workspace_id'],'workspace_title':allowed[r['workspace_id']]['title'],'title':payload['title'],'state':'reviewed' if payload.get('reviewed') else 'draft','stage':max(2,min(4,p.get('step',2))) if p.get('draft_id')==r['id'] else 3 if payload.get('reviewed') else 2,'created':r['created'],'updated':r['modified'] or r['created'],'version_order':r['version_order'] or 0}
  row['can_delete']=auth_control.permission(db,user,r['workspace_id'])=='editor' and not db.execute('SELECT 1 FROM handover_requests WHERE draft_id=? LIMIT 1',(r['id'],)).fetchone()
  if row['can_delete']:row['delete_token']=workflow.fingerprint(payload)
  drafts.append(row);items.append(row)
 counts={'drafts':len(drafts),'received':sum(r['recipient_account']==user['id'] and r['state'] in ('requested','reviewing','needs_info') for r in requests),'sent':sum(r['sender_account']==user['id'] and r['state']!='completed' for r in requests),'completed':sum(r['state']=='completed' for r in requests)}
 events=[];by_id={r['id']:r for r in requests}
 def add(key,rid,label,created):
  r=by_id.get(rid)
  if r:events.append({'key':key,'request_id':rid,'label':label,'title':r['title'],'created':created,'box':'inbox' if r['recipient_account']==user['id'] else 'sent'})
 for r in db.execute('SELECT h.* FROM request_history h JOIN handover_requests r ON r.id=h.request_id WHERE r.sender_account=? OR r.recipient_account=? ORDER BY h.id DESC LIMIT 200',(user['id'],user['id'])):
  add('request:'+str(r['id']),r['request_id'],r['action'],r['created'])
 for r in db.execute('SELECT e.id,e.action,e.created,f.request_id FROM followup_events e JOIN followups f ON f.id=e.followup_id JOIN handover_requests r ON r.id=f.request_id WHERE r.sender_account=? OR r.recipient_account=? ORDER BY e.id DESC LIMIT 200',(user['id'],user['id'])):
  add('question:'+str(r['id']),r['request_id'],'질문·답변 · '+r['action'],r['created'])
 for r in db.execute("SELECT a.id,a.updated,r.id AS request_id FROM acknowledgments a JOIN handover_requests r ON r.draft_id=a.draft_id WHERE a.state='confirmed' AND r.id=(SELECT max(x.id) FROM handover_requests x WHERE x.draft_id=a.draft_id AND x.created<=a.updated) AND (r.sender_account=? OR r.recipient_account=?) ORDER BY a.updated DESC LIMIT 100",(user['id'],user['id'])):
  add('review:'+str(r['id'])+':'+r['updated']+':'+str(r['request_id']),r['request_id'],'항목 검토 완료',r['updated'])
 reads={r[0] for r in db.execute('SELECT event_key FROM user_event_reads WHERE user_id=?',(user['id'],))}
 for e in events:e['read']=e['key'] in reads
 events.sort(key=lambda e:(stamp(e['created']),e['key']),reverse=True)
 items.sort(key=lambda r:(stamp(r['updated']),r.get('version_order',0),r['id']),reverse=True)
 return items,counts,events


def checked_deletion(db,user,item):
 key=item.get('draft_id') if isinstance(item,dict) else None
 if type(key) is not int:raise ValueError()
 draft=db.execute('SELECT id,workspace_id,payload FROM drafts WHERE id=? AND deleted=0',(key,)).fetchone()
 if not draft:raise auth_control.AccessError(409,'이미 삭제된 문서입니다. 목록을 새로 불러오세요.')
 auth_control.workspace_access(db,user,draft['workspace_id'],True)
 if db.execute('SELECT 1 FROM handover_requests WHERE draft_id=? LIMIT 1',(key,)).fetchone():
  raise auth_control.AccessError(409,'요청을 발송한 문서는 삭제할 수 없습니다. 보낸 인수인계에서 확인하세요.')
 if item.get('expected_fingerprint')!=workflow.fingerprint(json.loads(draft['payload'])):
  raise auth_control.AccessError(409,'문서가 변경되었습니다. 목록을 새로 불러온 뒤 삭제하세요.')
 return key


def handle_dashboard_request(handler,factory,method):
 path=urlsplit(handler.path).path
 if path not in ('/api/workbench','/api/workbench/read','/api/workbench/delete-draft','/api/workbench/delete-drafts'):return False
 try:
  params=parse_qs(urlsplit(handler.path).query);q=params.get('q',[''])[0].strip().casefold();status=params.get('status',['all'])[0];sort=params.get('sort',['updated'])[0];page=int(params.get('page',['1'])[0]);kind=params.get('kind',['all'])[0];size=int(params.get('page_size',['20'])[0])
  if not 20<=size<=200 or len(q)>100 or status not in STATES or sort not in ('updated','created','title') or kind not in ('all','draft','inbox','sent') or not 1<=page<=100000:raise ValueError()
  with closing(factory()) as db:
   user=auth_control.identity(handler,db)
   if path in ('/api/workbench/delete-draft','/api/workbench/delete-drafts'):
    if method!='POST':raise auth_control.AccessError(405,'POST 요청을 사용하세요.')
    body=auth_control.read_json(handler,32768)
    selected=[body] if path.endswith('/delete-draft') else body.get('items')
    if not isinstance(selected,list) or not 1<=len(selected)<=200:raise ValueError('문서를 1~200개 선택하세요.')
    db.execute('BEGIN IMMEDIATE')
    keys=[checked_deletion(db,user,item) for item in selected]
    if len(set(keys))!=len(keys):raise ValueError('중복된 문서가 있습니다.')
    for key in keys:db.execute('UPDATE drafts SET deleted=1 WHERE id=?',(key,))
    auth_control.audit(db,handler,'작성 중 인수인계서 논리 삭제',details=json.dumps(keys))
    db.commit();handler.respond(200,{'deleted':True} if path.endswith('/delete-draft') else {'deleted':len(keys)});return True
   items,counts,events=data(db,user)
   if path.endswith('/read'):
    if method!='POST':raise auth_control.AccessError(405,'읽음 처리는 POST 요청을 사용하세요.')
    body=auth_control.read_json(handler,32768);keys={e['key'] for e in events}
    requested=keys if body.get('all') is True else body.get('keys',[])
    if not isinstance(requested,(list,set)) or any(not isinstance(k,str) or k not in keys for k in requested):raise auth_control.AccessError(403,'본인의 알림만 읽음 처리할 수 있습니다.')
    for key in requested:db.execute('INSERT OR IGNORE INTO user_event_reads(user_id,event_key) VALUES(?,?)',(user['id'],key))
    db.commit();handler.respond(200,{'read':len(requested)});return True
   if method!='GET':raise auth_control.AccessError(405,'목록 조회는 GET 요청을 사용하세요.')
   filtered=[r for r in items if (kind=='all' or (r['kind']=='draft' if kind=='draft' else r.get('box')==kind)) and (status=='all' or r['state']==status) and (not q or q in (r['title']+' '+r['workspace_title']+' '+r.get('person','')).casefold())]
   if sort=='created':filtered.sort(key=lambda r:(stamp(r['created']),r['id']),reverse=True)
   elif sort=='title':filtered.sort(key=lambda r:(r['title'].casefold(),-r['id']))
   handler.respond(200,{'user_id':user['id'],'counts':counts,'items':filtered[(page-1)*size:page*size],'total':len(filtered),'page':page,'page_size':size,'drafts':[r for r in items if r['kind']=='draft'][:5],'received':[r for r in items if r['kind']=='request' and r['box']=='inbox' and r['state'] in ('requested','reviewing','needs_info')][:5],'notifications':events[:60],'unread':sum(not e['read'] for e in events),'notification_total':len(events)})
 except auth_control.AccessError as error:handler.respond(error.status,{'error':error.message})
 except (ValueError,TypeError,KeyError):handler.respond(400,{'error':'검색 조건을 확인하세요.'})
 except sqlite3.Error:handler.respond(503,{'error':'업무 목록을 불러오지 못했습니다. 저장된 데이터는 유지됩니다.'})
 return True

# 이전 확장 모듈·도구와의 호출 호환성.
handle = handle_dashboard_request
