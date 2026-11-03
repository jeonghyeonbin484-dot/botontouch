"""Authenticated immutable-source analysis and request-scoped successor Q&A."""
import json,os,sqlite3
from contextlib import closing
from urllib.parse import urlsplit,parse_qs
import auth_control,ai_draft,source_evidence

def handle(handler,factory,method):
 path=urlsplit(handler.path).path
 if not path.startswith('/api/evidence/'):return False
 try:
  with closing(factory()) as db:
   user=auth_control.identity(handler,db)
   body=auth_control.read_json(handler,32768) if method=='POST' else {k:v[0] for k,v in parse_qs(urlsplit(handler.path).query).items()}
   request=None
   if body.get('request_id'):
    import handover_requests
    handover_requests.bind_pending_requests(db,user);db.commit();request=handover_requests.request_row(db,user,int(body['request_id']));draft=json.loads(request['payload']);workspace=request['workspace_id']
   else:
    if method=='POST':raise auth_control.AccessError(400,'후임자 질문은 인수인계 요청에서 실행하세요.')
    row=db.execute('SELECT * FROM drafts WHERE id=? AND deleted=0',(int(body.get('draft_id',0)),)).fetchone()
    if not row:raise ValueError('저장된 초안을 선택하세요.')
    workspace=row['workspace_id'];auth_control.workspace_access(db,user,workspace);draft=json.loads(row['payload'])
   if method=='GET' and path=='/api/evidence/analysis':
    handler.respond(200,source_evidence.analysis(draft.get('references',{})));return True
   if method=='POST' and path=='/api/evidence/ask':
    question=body.get('question','')
    if not isinstance(question,str) or not 1<=len(question.strip())<=2000:raise ValueError('질문은 1~2000자로 입력하세요.')
    mode=ai_draft.settings().get('mode','live')
    if mode!='mock' and os.environ.get('BATON_SOURCE_QA_LIVE_ALLOWED')!='true':raise auth_control.AccessError(403,'실제 자료 질의응답은 서버의 승인된 실행환경에서만 사용할 수 있습니다. 공개 테스트는 모의 응답을 사용합니다.')
    docs=json.loads(request['documents'])
    docs=[dict(d) for d in docs]
    for d in docs:
     if not isinstance(d.get('sources'),str):d['sources']=json.dumps(d.get('sources',[]),ensure_ascii=False)
    confirmed=[{'location':f'확인된 인수인계서 항목 {i+1}','text':item['category']+': '+item['text'],'kind':'검토된 인수인계서'} for i,item in enumerate(draft['items'])]
    docs.append({'id':-request['id'],'name':'검토된 인수인계서 #'+str(request['id']),'revision':request['revision'],'sources':json.dumps(confirmed,ensure_ascii=False)})
    result=ai_draft.generate(docs,question=question.strip());result.update(question=question.strip(),request_id=request['id'],documents=[{'id':d['id'],'name':d['name']} for d in docs])
    cur=db.execute('INSERT INTO questions(payload,workspace_id) VALUES(?,?)',(json.dumps(result,ensure_ascii=False),workspace));auth_control.audit(db,handler,'자료 기반 질의응답',user['id'],details='모델: '+str(result.get('model','')));db.commit()
    handler.respond(201,dict(id=cur.lastrowid,**result));return True
   raise ValueError('지원하지 않는 자료 분석 경로입니다.')
 except auth_control.AccessError as e:handler.respond(e.status,{'error':e.message})
 except ValueError as e:handler.respond(getattr(e,'http_status',400),{'error':str(e)})
 except (TypeError,KeyError,sqlite3.Error):handler.respond(400,{'error':'자료 분석·질의응답을 처리하지 못했습니다. 자료와 권한, 서버 모델 설정을 확인하세요. 입력은 유지됩니다.'})
 return True
