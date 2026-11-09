"""Recipient-scoped list metadata and explicit, revision-bound answer review."""
import json
from batontouch.auth import sessions as auth_control
from batontouch.handover import workflow as workflow


def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS request_answer_reviews(request_id INTEGER NOT NULL,revision INTEGER NOT NULL,recipient_account INTEGER NOT NULL,answer_token TEXT NOT NULL,confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(request_id,revision,recipient_account))')


def metrics(db,row):
 questions=[dict(q) for q in db.execute("SELECT f.id,f.state,f.reply,f.qa_revision,(SELECT max(e.id) FROM followup_events e WHERE e.followup_id=f.id) AS event_id FROM followups f WHERE f.request_id=? AND f.origin='recipient' AND f.qa_archived=0 ORDER BY f.id",(row['id'],))]
 token=workflow.fingerprint([row['revision'],questions])
 review=db.execute('SELECT answer_token FROM request_answer_reviews WHERE request_id=? AND revision=? AND recipient_account=?',(row['id'],row['revision'],row['recipient_account'])).fetchone()
 return {'question_count':len(questions),'unanswered_count':sum(q['state'] in ('open','deferred') for q in questions),'answered_count':sum(q['state'] in ('resolved','not_applicable') for q in questions),'answers_reviewed':bool(questions and review and review['answer_token']==token),'answer_token':token}


def list_requests(db,user,query,kind):
 from batontouch.handover import requests as requests
 field='recipient_account' if kind=='received' else 'sender_account'
 status=query.get('status',['all'])[0];q=query.get('q',[''])[0].strip();sort=query.get('sort',['created'])[0]
 paged='page' in query;page=int(query.get('page',['1'])[0]);size=int(query.get('page_size',['20' if paged else '200'])[0])
 if len(q)>100 or status not in ('all',*requests.STATES) or sort not in ('created','updated','title') or not 1<=page<=100000 or not 1<=size<=200:raise ValueError('검색 조건을 확인하세요.')
 scope=field+'=?';where=scope;args=[user['id']]
 if status!='all':where+=' AND state=?';args.append(status)
 if q:
  fields=["json_extract(payload,'$.title')","json_extract(payload,'$.workspace.title')",*[f"json_extract({who}_snapshot,'$.{key}')" for who in ('sender','recipient') for key in ('name','department','position')]]
  where+=' AND ('+' OR '.join('instr(lower('+field+'),lower(?))>0' for field in fields)+')';args.extend([q]*len(fields))
 counts=db.execute("SELECT count(*) AS total,sum(state='requested') AS unread,sum(state!='completed') AS active,sum(state IN ('requested','reviewing')) AS pending FROM handover_requests WHERE "+scope,(user['id'],)).fetchone()
 matched=db.execute('SELECT count(*) FROM handover_requests WHERE '+where,args).fetchone()[0]
 page=min(page,max(1,(matched+size-1)//size))
 order="json_extract(payload,'$.title') COLLATE NOCASE ASC,id DESC" if sort=='title' else ('requested_at' if sort=='created' else sort)+' DESC,id DESC'
 rows=db.execute("SELECT id,workspace_id,draft_id,recipient_account,state,reason,revision,created,updated,accepted_at,completed_at,version_id,sender_snapshot,recipient_snapshot,coalesce((SELECT s.created FROM request_snapshots s WHERE s.request_id=handover_requests.id AND s.revision=handover_requests.revision),created) AS requested_at,json_array_length(documents) AS attachment_count,json_object('title',json_extract(payload,'$.title'),'workspace',json_extract(payload,'$.workspace')) AS payload FROM handover_requests WHERE "+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',args+[size,(page-1)*size]).fetchall()
 items=[]
 for row in rows:
  payload=json.loads(row['payload']);workspace=payload.get('workspace');workspace=workspace if isinstance(workspace,dict) else {}
  items.append(requests.summary(row)|metrics(db,row)|{'workspace_title':workspace.get('title') or payload['title'],'requested_at':row['requested_at'],'attachment_count':row['attachment_count']})
 return {'user_id':user['id'],'box':kind,'items':items,'pending':counts['pending'] or 0,'unread':counts['unread'] or 0,'active':counts['active'] or 0,'total':counts['total'],'filtered_total':matched,'page':page,'page_size':size}


def confirm_answers(db,user,body):
 from batontouch.handover import requests as requests
 if type(body.get('id')) is not int:raise ValueError('요청을 선택하세요.')
 row=requests.request_row(db,user,body['id']);requests.assert_recipient(db,user,row)
 if type(body.get('revision')) is not int or body['revision']!=row['revision']:raise auth_control.AccessError(409,'요청이 다시 전달되었습니다. 최신 문서와 답변을 확인하세요.')
 if row['state']=='completed':raise auth_control.AccessError(409,'완료된 요청의 이력은 변경하지 않습니다.')
 info=metrics(db,row)
 if not info['question_count'] or info['unanswered_count']:raise auth_control.AccessError(409,'인계자의 답변을 모두 받은 뒤 확인하세요.')
 if body.get('answer_token')!=info['answer_token']:raise auth_control.AccessError(409,'질문이나 답변이 변경되었습니다. 최신 답변을 다시 확인하세요.')
 db.execute('INSERT INTO request_answer_reviews(request_id,revision,recipient_account,answer_token) VALUES(?,?,?,?) ON CONFLICT(request_id,revision,recipient_account) DO UPDATE SET answer_token=excluded.answer_token,confirmed_at=CURRENT_TIMESTAMP',(row['id'],row['revision'],user['id'],info['answer_token']))
 if not info['answers_reviewed']:requests.history(db,row,user,'추가 질문 답변 확인','최신 질문·답변 확인 완료')
 return {'saved':True}
