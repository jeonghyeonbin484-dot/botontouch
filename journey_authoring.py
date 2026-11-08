"""Additive per-user resume state; existing drafts, accounts and requests remain intact."""
import json
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit,parse_qs
import auth_control
import handover_workflow as workflow

def ensure(db):
 db.execute("CREATE TABLE IF NOT EXISTS journey_authoring(user_id INTEGER NOT NULL,workspace_id INTEGER NOT NULL,draft_id INTEGER NOT NULL,recipient TEXT NOT NULL DEFAULT '{}',qa_token TEXT NOT NULL DEFAULT '',updated TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,workspace_id,draft_id))")

def qa_signature(db,did):
 return [[r['id'],r['qa_revision'],r['state'],r['qa_included']] for r in db.execute("SELECT id,qa_revision,state,qa_included FROM followups WHERE draft_id=? AND qa_kind='expected' AND qa_archived=0 ORDER BY id",(did,))]

def handle(handler,factory,method):
 if urlsplit(handler.path).path!='/api/journey/authoring':return False
 try:
  body=auth_control.read_json(handler,32768) if method=='POST' else {};params=parse_qs(urlsplit(handler.path).query)
  with closing(factory()) as db:
   user=auth_control.identity(handler,db);wid=int(body.get('workspace_id') or handler.headers.get('X-Workspace-Id','1'));auth_control.workspace_access(db,user,wid,True)
   if method=='POST' and body.get('action')=='title':
    title=body.get('title','');previous=body.get('previous_title')
    if not isinstance(title,str) or not 1<=len(title.strip())<=500 or not isinstance(previous,str):raise ValueError('업무명을 입력하세요.')
    if db.execute('UPDATE workspaces SET title=? WHERE id=? AND title=?',(title.strip(),wid,previous)).rowcount!=1:raise auth_control.AccessError(409,'다른 화면에서 업무명이 변경되었습니다. 입력한 업무명은 유지됩니다. 최신 업무를 확인한 뒤 저장하세요.')
    db.commit();handler.respond(200,{'saved':True,'title':title.strip()});return True
   did=int(body.get('draft_id') or params.get('draft_id',['0'])[0]);draft=workflow.load_draft(db,did,wid);baseline=workflow.fingerprint(draft);signature=qa_signature(db,did);token=workflow.fingerprint([draft['title'],draft['items'],draft.get('references',{}),signature])
   if method=='POST':
    if body.get('baseline')!=baseline:raise auth_control.AccessError(409,'문서가 변경됐습니다. 최신 문서를 저장한 뒤 확인하세요.')
    db.execute('INSERT OR IGNORE INTO journey_authoring(user_id,workspace_id,draft_id) VALUES(?,?,?)',(user['id'],wid,did))
    if body.get('action')=='review':
     if body.get('reviewed') is True and body.get('questions')!=signature:raise auth_control.AccessError(409,'질문·답변이 변경됐습니다. 다시 확인하세요.')
     db.execute('UPDATE journey_authoring SET qa_token=?,updated=CURRENT_TIMESTAMP WHERE user_id=? AND workspace_id=? AND draft_id=?',(token if body.get('reviewed') is True else '',user['id'],wid,did))
    elif body.get('action')=='recipient-clear':
     db.execute("UPDATE journey_authoring SET recipient=?,updated=CURRENT_TIMESTAMP WHERE user_id=? AND workspace_id=? AND draft_id=?",(json.dumps({'department_id':str(body.get('department_id') or ''),'confirmed':False}),user['id'],wid,did))
    elif body.get('action')=='recipient':
     import org_directory,handover_requests
     target=body.get('employee_id');dept=body.get('department_id');person=None
     if not isinstance(target,str) or not isinstance(dept,str):raise ValueError('부서와 직원을 선택하세요.')
     if db.execute('SELECT 1 FROM org_employees WHERE employee_id=?',(target,)).fetchone():person=handover_requests.employee(db,target)
     cfg=org_directory.settings()
     if cfg.get('enabled') and cfg.get('approved'):
      official=next((p for p in org_directory.fetch_employees(dept,None) if p['employee_id']==target),None)
      person={**(person or {}),**official,'department':official.get('department_name','')} if official else None
     if not person or person.get('department_id')!=dept or not person.get('saeoll_id') or person.get('employment_status','active')!='active':raise ValueError('현재 부서의 재직 직원과 유효한 SAEOLL_ID를 확인하세요.')
     department=db.execute('SELECT active,hidden_from_picker FROM org_departments WHERE id=?',(dept,)).fetchone()
     if not department or not department['active'] or department['hidden_from_picker']:raise ValueError('신규 요청이 가능한 부서를 선택하세요.')
     if person.get('user_id')==user['id'] or person['saeoll_id']==user['username']:raise ValueError('본인에게 인수인계를 요청할 수 없습니다.')
     snapshot={k:person.get(k,'') for k in ('employee_id','saeoll_id','name','position','department_id','department')};snapshot['account_linked']=bool(person.get('user_id') and person.get('account_username')==person['saeoll_id']);snapshot['account_eligible']=True;snapshot['confirmed']=body.get('confirm') is True
     db.execute('UPDATE journey_authoring SET recipient=?,updated=CURRENT_TIMESTAMP WHERE user_id=? AND workspace_id=? AND draft_id=?',(json.dumps(snapshot,ensure_ascii=False),user['id'],wid,did))
    else:raise ValueError('저장할 작성 상태를 확인하세요.')
    db.commit()
   elif method!='GET':raise auth_control.AccessError(405,'지원하지 않는 요청입니다.')
   row=db.execute('SELECT * FROM journey_authoring WHERE user_id=? AND workspace_id=? AND draft_id=?',(user['id'],wid,did)).fetchone()
   handler.respond(200,{'draft_id':did,'baseline':baseline,'questions':signature,'qa_reviewed':bool(row and row['qa_token']==token),'recipient':json.loads(row['recipient']) if row else None})
 except auth_control.AccessError as e:handler.respond(e.status,{'error':e.message})
 except ValueError as e:handler.respond(400,{'error':str(e)})
 except (TypeError,KeyError):handler.respond(400,{'error':'작성 상태를 확인하세요. 입력한 내용은 유지됩니다.'})
 except sqlite3.Error:handler.respond(409,{'error':'저장 중 충돌했습니다. 입력은 유지되며 다시 저장할 수 있습니다.'})
 return True
