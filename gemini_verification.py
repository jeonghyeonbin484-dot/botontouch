"""Admin-only, fixed fictional fixture verification. No arbitrary user text/files."""
import os,json,base64,hashlib,time
from pathlib import Path
from contextlib import closing
import auth_control,gemini_engine,gemini_transport
FIXTURE_SHA256='77167c18d408d72e236c7a58630f45e2aae7c19715504b30be39e086175bf252'

def documents():
 import app
 raw=Path(__file__).with_name('gemini_verification_fixtures.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=FIXTURE_SHA256:raise ValueError('가상 원본 검증값이 일치하지 않습니다.')
 result=[]
 for index,item in enumerate(json.loads(raw),1):
  data=base64.b64decode(item['base64'],validate=True)
  if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('가상 파일 무결성 검사 실패')
  content,sources=app.extract(item['name'],data)
  result.append({'id':index,'name':item['name'],'revision':1,'sources':json.dumps(sources,ensure_ascii=False),'content':content})
 return result

def handle(handler,factory,method):
 path=handler.path.split('?')[0]
 if path!='/api/demo/gemini-verify':return False
 try:
  with closing(factory()) as db:
   user=auth_control.identity(handler,db)
   if user['role']!='admin':raise auth_control.AccessError(403,'관리자만 고정 가상 자료 연결 검증을 실행할 수 있습니다.')
   db.execute("CREATE TABLE IF NOT EXISTS gemini_verification_runs(run_id TEXT,action TEXT,user_id INTEGER,payload TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(run_id,action))")
   run=os.environ.get('GEMINI_VERIFY_RUN_ID','disabled');enabled=os.environ.get('GEMINI_VERIFY_ENABLED')=='true'
   if method=='GET':
    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM gemini_verification_runs WHERE run_id=? ORDER BY created,action',(run,))]
    # Latest completed virtual results remain viewable after external transmission is disabled.
    if not rows:rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM gemini_verification_runs ORDER BY created DESC LIMIT 3')]
    db.commit();handler.respond(200,{'enabled':enabled,'results':rows,'scope':'서버에 고정된 가상 원본 3개 전용. 일반 작성 자료 전송은 비활성화.'});return True
   body=auth_control.read_json(handler,1024)
   if set(body)-{'action','reviewed'}:raise ValueError('임의 입력·파일·질문 전송을 허용하지 않습니다.')
   action=body.get('action')
   if action not in ('minimal','draft','qa'):raise ValueError('검증 종류가 올바르지 않습니다.')
   if not enabled or run=='disabled':raise auth_control.AccessError(403,'실제 연결 검증이 종료되었거나 비활성화 상태입니다. 일반 AI는 모의 모드를 유지합니다.')
   existing=db.execute('SELECT payload FROM gemini_verification_runs WHERE run_id=? AND action=?',(run,action)).fetchone()
   if existing:handler.respond(200,{**json.loads(existing[0]),'cached':True});return True
   key=os.environ.get('GEMINI_VERIFY_API_KEY','');model=os.environ.get('GEMINI_VERIFY_MODEL','')
   if not key or not model:raise ValueError('서버 검증 전용 키·모델이 설정되지 않았습니다.')
   config={'key':key,'model':model};start=time.monotonic()
   try:
    if action=='minimal':
     value,transport=gemini_transport.generate_content(key,model,{'contents':[{'parts':[{'text':'가상 연결 테스트입니다. 연결 확인 이라고만 답하세요.'}]}],'generationConfig':{'maxOutputTokens':512}})
     result={'mode':'live','model':model,'text':''.join(p.get('text','') for c in value.get('candidates',[]) for p in c.get('content',{}).get('parts',[]) if not p.get('thought')),'transport':transport,'usage':value.get('usageMetadata',{})}
    elif action=='draft':result=gemini_engine.generate(documents(),config=config)
    else:
     prior=db.execute("SELECT payload FROM gemini_verification_runs WHERE run_id=? AND action='draft'",(run,)).fetchone()
     if not prior or body.get('reviewed') is not True:raise ValueError('실제 초안과 원문을 확인한 뒤 검토 체크를 선택하세요.')
     draft=json.loads(prior[0])
     if draft.get('status')!='PASS':raise ValueError('성공한 실제 초안이 필요합니다.')
     docs=documents();docs.append({'id':-1,'name':'가상 인수인계 검토본','revision':1,'sources':json.dumps([{'location':f'검토본 항목 {i+1}','text':item['category']+': '+item['text']} for i,item in enumerate(draft['result']['items'])],ensure_ascii=False)})
     result=gemini_engine.generate(docs,question='3월에 해야 할 일과 드론 안전교육의 최종 일정 확인 사항은 무엇인가요? 원본 자료의 출처도 표시해 주세요.',config=config)
    record={'action':action,'status':'PASS','result':result,'seconds':round(time.monotonic()-start,3),'data_scope':'고정 가상 원본만 사용','http_status':200}
   except gemini_transport.GeminiTransportError as e:record={'action':action,'status':'FAIL','error':str(e),'provider_error':e.provider_error,'attempts':e.attempts,'http_status':e.http_status,'upstream_status':e.upstream_status,'seconds':round(time.monotonic()-start,3)}
   db.execute('INSERT INTO gemini_verification_runs(run_id,action,user_id,payload) VALUES(?,?,?,?)',(run,action,user['id'],json.dumps(record,ensure_ascii=False)))
   auth_control.audit(db,handler,'고정 가상자료 Gemini 검증',user['id'],details=action+' / '+record['status']);db.commit();handler.respond(record['http_status'],record);return True
 except auth_control.AccessError as e:handler.respond(e.status,{'error':e.message})
 except ValueError as e:handler.respond(400,{'error':str(e)})
 return True
