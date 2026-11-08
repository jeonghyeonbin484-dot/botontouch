"""기존 followups에 예상 Q&A를 보존한다. 기존 질문과 이력을 삭제하지 않는다."""
import json,sqlite3,re
from contextlib import closing
import auth_control,ai_draft,handover_workflow as workflow
from urllib.parse import urlsplit

def handle(handler,factory,method):
 from handover_journey import question_rows,event,documents
 path=urlsplit(handler.path).path
 try:
  if method!='POST':raise auth_control.AccessError(405,'질문·답변 처리는 POST 요청을 사용하세요.')
  body=auth_control.read_json(handler,2*1024*1024)
  with closing(factory()) as db:
   user=auth_control.identity(handler,db);workspace=int(body.get('workspace_id') or handler.headers.get('X-Workspace-Id','1'));auth_control.workspace_access(db,user,workspace,True);draft_id=int(body.get('draft_id') or 0);draft=workflow.load_draft(db,draft_id,workspace)
   if path.endswith('/generate'):
    if body.get('fingerprint')!=workflow.fingerprint(draft):raise auth_control.AccessError(409,'문서를 먼저 저장한 뒤 예상 질문을 만드세요.')
    docs=documents(db,draft,workspace)
    if not docs:raise ValueError('등록한 업무자료와 저장된 AI 초안이 필요합니다.')
    existing=question_rows(db,draft_id=draft_id);baseline=workflow.fingerprint(draft)
    context={'mode':'expected_qa','draft':{'title':draft['title'],'items':draft['items']},'existing_questions':[{'question':q['question'],'answer':q['reply']} for q in existing]}
    result=ai_draft.generate(docs,gap_context=context,actor=user)
    db.execute('BEGIN IMMEDIATE')
    if workflow.fingerprint(workflow.load_draft(db,draft_id,workspace))!=baseline:raise auth_control.AccessError(409,'생성 중 문서가 변경됐습니다. 입력은 유지되며 최신 문서로 다시 시도하세요.')
    added=store_suggestions(db,workspace,draft_id,user,baseline,result)
    db.execute('INSERT INTO journey_checks(workspace_id,draft_id,baseline,payload) VALUES(?,?,?,?)',(workspace,draft_id,baseline,json.dumps(result,ensure_ascii=False)));db.commit();handler.respond(201,{'added':added,'summary':result['summary'],'model':result.get('model'),'mode':result.get('mode'),'questions':question_rows(db,draft_id=draft_id)});return True
   if path.endswith('/save') or path.endswith('/archive'):
    key=body.get('id');q=db.execute("SELECT * FROM followups WHERE id=? AND workspace_id=? AND draft_id=? AND qa_kind='expected' AND qa_archived=0",(key,workspace,draft_id)).fetchone() if key else None
    if key and not q:raise auth_control.AccessError(403,'해당 문서의 예상 질문만 수정할 수 있습니다.')
    if q and q['request_id'] and db.execute("SELECT 1 FROM handover_requests WHERE id=? AND state='completed'",(q['request_id'],)).fetchone():raise auth_control.AccessError(409,'완료된 요청의 질문·답변은 이력을 유지하며 수정하지 않습니다.')
    if path.endswith('/archive'):
     if not q:raise ValueError('질문을 선택하세요.')
     db.execute('UPDATE followups SET qa_archived=1,qa_revision=qa_revision+1 WHERE id=?',(q['id'],));event(db,q['id'],user,'예상 질문 숨김(원문·이력 보존)',{'question':q['question']});db.commit();handler.respond(200,{'saved':True,'questions':question_rows(db,draft_id=draft_id)});return True
    question=body.get('question','');reply=body.get('reply','');included=body.get('included',True);attachments=body.get('document_ids',[]);index=body.get('target_index',q['item_index'] if q else 0)
    if not isinstance(question,str) or not 1<=len(question.strip())<=2000 or not isinstance(reply,str) or len(reply)>8000 or type(included) is not bool or type(index) is not int or not 0<=index<len(draft['items']):raise ValueError('질문·답변과 반영할 문서 항목을 확인하세요.')
    if not isinstance(attachments,list) or len(attachments)>10 or any(type(i) is not int for i in attachments):raise ValueError('관련 자료를 최대 10개까지 선택하세요.')
    for doc_id in attachments:
     if not db.execute('SELECT 1 FROM documents WHERE id=? AND workspace_id=? AND deleted=0',(doc_id,workspace)).fetchone():raise auth_control.AccessError(403,'이 문서의 업무자료만 첨부할 수 있습니다.')
    state=body.get('state') or ('resolved' if reply.strip() else 'open')
    if state not in ('open','resolved','not_applicable','deferred') or state=='resolved' and not reply.strip():raise ValueError('답변과 처리 상태를 확인하세요.')
    if state=='not_applicable':included=False
    db.execute('BEGIN IMMEDIATE')
    if q:
     expected=body.get('revision',q['qa_revision'])
     if type(expected) is not int or expected!=q['qa_revision']:raise auth_control.AccessError(409,'다른 화면에서 수정한 질문입니다. 현재 입력을 보관하고 다시 불러오세요.')
     changed=db.execute("UPDATE followups SET question=?,reply=?,state=?,qa_included=?,qa_documents=?,item_index=?,qa_revision=qa_revision+1,updated=CURRENT_TIMESTAMP,application='none',proposal=NULL WHERE id=? AND qa_revision=?",(question.strip(),reply,state,int(included),json.dumps(attachments),index,q['id'],expected)).rowcount
     if changed!=1:raise auth_control.AccessError(409,'다른 화면에서 질문이 변경됐습니다.')
     event(db,q['id'],user,'예상 Q&A 수정',{'before':{'question':q['question'],'reply':q['reply'],'state':q['state'],'included':bool(q['qa_included'])},'after':{'question':question.strip(),'reply':reply,'state':state,'included':included,'document_ids':attachments}})
    else:
     key=db.execute("INSERT INTO followups(workspace_id,draft_id,item_index,question,reply,state,actor,origin,qa_kind,qa_included,qa_documents) VALUES(?,?,?,?,?,?,?,'manual','expected',?,?)",(workspace,draft_id,index,question.strip(),reply,state,user['username'],int(included),json.dumps(attachments))).lastrowid;event(db,key,user,'직접 예상 질문 작성',{'question':question.strip(),'reply':reply,'included':included})
    db.commit();handler.respond(200,{'saved':True,'questions':question_rows(db,draft_id=draft_id)});return True
   raise auth_control.AccessError(404,'요청한 예상 질문 기능이 없습니다.')
 except auth_control.AccessError as error:handler.respond(error.status,{'error':error.message})
 except (ValueError,TypeError,KeyError) as error:handler.respond(getattr(error,'http_status',400),{'error':str(error) if isinstance(error,ValueError) else '질문·답변 입력 형식을 확인하세요.'})
 except sqlite3.Error:handler.respond(409,{'error':'질문 저장 중 충돌했습니다. 입력은 유지되며 다시 시도할 수 있습니다.'})
 return True

def store_suggestions(db,workspace,draft_id,user,baseline,result,selected=True):
 from handover_journey import question_rows,event
 existing=question_rows(db,draft_id=draft_id);before_ids={q['id'] for q in existing}
 known={re.sub(r'\s+','',q['question']).casefold() for q in existing};added=0
 for q in result['questions']:
  key=re.sub(r'\s+','',q['question']).casefold()
  if key in known:continue
  known.add(key);cur=db.execute("INSERT INTO followups(workspace_id,draft_id,item_index,question,actor,origin,reason,source_ids,baseline,qa_kind,recommended_answer,answer_source_ids,answer_supported,qa_references,qa_mode,qa_model) VALUES(?,?,?,?,?,'ai',?,?,?,'expected',?,?,?,?,?,?)",(workspace,draft_id,q['target_index'],q['question'],user['username'],q['reason'],json.dumps(q['source_ids']),baseline,q['recommended_answer'],json.dumps(q['answer_source_ids']),int(q['supported']),json.dumps(result.get('references',{}),ensure_ascii=False),result.get('mode','unknown'),result.get('model','')));event(db,cur.lastrowid,user,'AI 예상 질문·추천 답변 생성',{'question':q['question'],'model':result.get('model'),'mode':result.get('mode')});added+=1
 if not selected:
  for row in question_rows(db,draft_id=draft_id):
   if row['id'] not in before_ids:db.execute('UPDATE followups SET qa_included=0 WHERE id=?',(row['id'],))
 return added
