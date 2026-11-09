"""자료함용 메타데이터 조회. 원문·첨부 바이너리·대화 본문을 재전송하지 않는다."""
import sqlite3,json
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit,parse_qs
from batontouch.auth import sessions as auth_control

def handle_library_request(handler,factory,method):
 if urlsplit(handler.path).path!='/api/library':return False
 try:
  if method!='GET':raise auth_control.AccessError(405,'자료함 목록은 조회 요청을 사용하세요.')
  params=parse_qs(urlsplit(handler.path).query);kind=params.get('kind',['documents'])[0];query=params.get('q',[''])[0].strip().casefold();wid=int(params.get('workspace_id',['0'])[0]);page=int(params.get('page',['1'])[0]);status=params.get('status',['all'])[0];sort=params.get('sort',['updated'])[0];size=int(params.get('page_size',['20'])[0])
  if not 20<=size<=200 or status not in ('all','draft','saved','requested','reviewing','needs_info','accepted','completed') or sort not in ('updated','created','title') or kind not in ('documents','drafts','conversations') or len(query)>100 or wid<0 or not 1<=page<=100000:raise ValueError('자료함 검색 조건을 확인하세요.')
  with closing(factory()) as db:
   user=auth_control.identity(handler,db);workspaces=[{**dict(r),'permission':auth_control.permission(db,user,r['id'])} for r in db.execute('SELECT id,title FROM workspaces ORDER BY id DESC') if auth_control.permission(db,user,r['id'])];allowed={w['id']:w for w in workspaces}
   received=list(db.execute('SELECT id,workspace_id,payload,documents,created,revision FROM handover_requests WHERE recipient_account=? ORDER BY id DESC',(user['id'],)))
   received_workspaces={r['workspace_id']:json.loads(r['payload']).get('title','전달받은 업무') for r in received}
   if wid and wid not in allowed and (kind!='documents' or wid not in received_workspaces):raise auth_control.AccessError(403,'이 업무의 자료함을 조회할 권한이 없습니다.')
   if kind=='documents':workspaces.extend({'id':key,'title':title+' · 전달받음','permission':'received'} for key,title in received_workspaces.items() if key not in allowed)
   items=[]
   if kind=='documents':
    for r in db.execute('SELECT id,name,workspace_id,created,length(content) AS characters,revision FROM documents WHERE deleted=0 ORDER BY id DESC'):
     if r['workspace_id'] in allowed:items.append({**dict(r),'type':'document','title':r['name'],'workspace_title':allowed[r['workspace_id']]['title'],'origin':'managed','editable':allowed[r['workspace_id']]['permission']=='editor'})
    for req in received:
     for d in json.loads(req['documents']):items.append({'id':d['id'],'name':d['name'],'title':d['name'],'type':'document','workspace_id':req['workspace_id'],'workspace_title':json.loads(req['payload']).get('title','전달받은 업무'),'created':req['created'],'revision':req['revision'],'request_id':req['id'],'origin':'received','editable':False})
    for item in items:item['format']=Path(item['name']).suffix.lower().lstrip('.')
    fmt=params.get('format',['all'])[0];origin=params.get('origin',['all'])[0]
    if fmt not in ('all','pdf','hwpx','xlsx','txt') or origin not in ('all','managed','received'):raise ValueError()
    items=[r for r in items if (fmt=='all' or r['format']==fmt) and (origin=='all' or r['origin']==origin)]
   elif kind=='drafts':
    requests=[dict(r) for r in db.execute("SELECT id,workspace_id,draft_id,state,created,updated,completed_at,sender_account,json_extract(payload,'$.title') AS title FROM handover_requests WHERE sender_account=? OR recipient_account=? ORDER BY id DESC",(user['id'],user['id']))];latest={}
    for r in requests:latest.setdefault(r['draft_id'],r)
    for r in db.execute("SELECT d.id,d.workspace_id,d.created,coalesce((SELECT max(v.created) FROM draft_versions v WHERE v.draft_id=d.id),d.created) AS updated,coalesce((SELECT max(v.id) FROM draft_versions v WHERE v.draft_id=d.id),0) AS version_order,json_extract(d.payload,'$.title') AS title,json_extract(d.payload,'$.reviewed') AS reviewed FROM drafts d WHERE d.deleted=0 ORDER BY d.id DESC"):
     if r['workspace_id'] not in allowed:continue
     request=latest.get(r['id']);row_state=request['state'] if request and request['state']!='completed' else 'saved' if r['reviewed'] else 'draft'
     items.append({**dict(r),'type':'draft','state':row_state,'editable':allowed[r['workspace_id']]['permission']=='editor','workspace_title':allowed[r['workspace_id']]['title']})
    for r in requests:
     if r['state']=='completed':items.append({**{k:v for k,v in r.items() if k!='sender_account'},'type':'completed','workspace_title':allowed.get(r['workspace_id'],{}).get('title',r['title']),'box':'sent' if r['sender_account']==user['id'] else 'inbox','created':r['completed_at'] or r['updated']})
   else:
    for r in db.execute('SELECT s.id,s.workspace_id,s.draft_id,s.title,s.created,s.updated,json_extract(d.payload,\'$.title\') AS draft_title FROM ai_studio_sessions s LEFT JOIN drafts d ON d.id=s.draft_id AND d.workspace_id=s.workspace_id AND d.deleted=0 WHERE s.owner_id=? ORDER BY s.updated DESC,s.id DESC',(user['id'],)):
     if r['workspace_id'] in allowed:items.append({**dict(r),'type':'conversation','editable':allowed[r['workspace_id']]['permission']=='editor','workspace_title':allowed[r['workspace_id']]['title']})
   items=[r for r in items if (kind!='drafts' or status=='all' or r.get('state',r.get('type'))==status) and (not wid or r['workspace_id']==wid) and (not query or query in str(r.get('title','')).casefold() or query in str(r.get('workspace_title','')).casefold() or query in str(r.get('draft_title') or '').casefold())];items.sort(key=lambda r:(r.get('updated') or r.get('created') or '',r.get('version_order',0),r['id']),reverse=True);total=len(items)
   if sort=='created':items.sort(key=lambda r:(r.get('created') or '',r['id']),reverse=True)
   elif sort=='title':items.sort(key=lambda r:(r.get('title','').casefold(),-r['id']))
   document_count=sum(r['n'] for r in db.execute('SELECT workspace_id,count(*) AS n FROM documents WHERE deleted=0 GROUP BY workspace_id') if r['workspace_id'] in allowed)+sum(len(json.loads(r['documents'])) for r in received)
   handler.respond(200,{'document_count':document_count,'kind':kind,'items':items[(page-1)*size:page*size],'total':total,'page':page,'page_size':size,'workspaces':workspaces})
 except auth_control.AccessError as error:handler.respond(error.status,{'error':error.message})
 except (ValueError,TypeError):handler.respond(400,{'error':'자료함 검색 조건을 확인하세요.'})
 except sqlite3.Error:handler.respond(503,{'error':'자료함을 불러오지 못했습니다. 잠시 후 다시 불러오세요. 기존 자료는 유지됩니다.'})
 return True

# 이전 확장 모듈·도구와의 호출 호환성.
handle = handle_library_request
