"""Version-bound, approval-only edits to one exact paragraph in a studio draft."""
import copy
import hashlib
import json
import re

import ai_draft
import auth_control
import export_hwpx
import handover_workflow as workflow
import report_document

ACTIONS={'paper','paragraphs','paragraph-apply','paragraph-reject','paragraph-undo'}


def paper(draft,draft_id):
 baseline=workflow.fingerprint(draft)
 model=export_hwpx.output_model(draft,editable=True);targets={}
 for block in model['blocks']:
  origin=block.pop('origin',None)
  if not origin:continue
  identifier=hashlib.sha256(workflow.canonical([draft_id,baseline,origin]).encode()).hexdigest()
  targets[identifier]={'id':identifier,'draft_id':draft_id,'baseline':baseline,**origin}
  block['edit_id']=identifier
 return {'html':report_document.html_document(model),'targets':targets,'baseline':baseline,'draft_id':draft_id}


def current_draft(db,s):
 import ai_studio
 draft=ai_studio.draft_for(db,s)
 if not draft:raise auth_control.AccessError(409,'저장된 문서를 먼저 선택하세요.')
 return draft


def editable(db,s):
 # Sent snapshots are immutable. Editing this working copy never edits requests.
 if db.execute("SELECT 1 FROM handover_requests WHERE draft_id=? AND state='completed'",(s['draft_id'],)).fetchone():
  raise auth_control.AccessError(409,'완료된 인수인계 문서는 변경하지 않습니다. 새 업무에서 작성하세요.')


def event(db,s,message,user,label):
 db.execute('INSERT INTO ai_studio_events(session_id,message_id,actor_id,action) VALUES(?,?,?,?)',(s['id'],message,user['id'],label))
 db.execute('UPDATE ai_studio_sessions SET updated=CURRENT_TIMESTAMP WHERE id=?',(s['id'],))


def handle(handler,db,s,user,action,method,body):
 import ai_studio
 sid=s['id']
 if action=='paper':
  if method!='GET':raise auth_control.AccessError(405,'미리보기는 GET 요청을 사용하세요.')
  draft=current_draft(db,s);enriched,_=ai_studio.enriched(db,s,draft)
  result=paper(enriched,s['draft_id'])
  # Enrichment changes only output metadata; edit baselines always bind raw storage.
  baseline=workflow.fingerprint(draft)
  for target in result['targets'].values():target['baseline']=baseline
  result['baseline']=baseline
  handler.respond(200,result);return
 if method!='POST':raise auth_control.AccessError(405,'문단 수정은 POST 요청을 사용하세요.')
 editable(db,s)
 if action=='paragraphs':
  current=current_draft(db,s);baseline=workflow.fingerprint(current)
  if body.get('draft_id')!=s['draft_id'] or body.get('baseline')!=baseline:
   raise auth_control.AccessError(409,'문서가 변경되었습니다. 최신 미리보기에서 문단을 다시 선택하세요.')
  enriched,_=ai_studio.enriched(db,s,current)
  target=paper(enriched,s['draft_id'])['targets'].get(body.get('target_id'))
  if not target:raise auth_control.AccessError(409,'문단 위치가 달라졌습니다. 미리보기에서 다시 선택하세요.')
  target['baseline']=baseline
  text=body.get('text','');nonce=body.get('nonce','')
  if not isinstance(text,str) or not 1<=len(text.strip())<=8000 or not isinstance(nonce,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',nonce):
   raise ValueError('수정 지시와 요청번호를 확인하세요.')
  db.execute('BEGIN IMMEDIATE')
  existing=db.execute("SELECT * FROM ai_studio_messages WHERE session_id=? AND nonce=? AND role='user'",(sid,nonce)).fetchone()
  if existing:
   meta=ai_studio.unpack(existing['result']) or {}
   if existing['content']!=text or meta.get('paragraph_request')!=target:raise auth_control.AccessError(409,'다른 문단에 사용된 요청번호입니다.')
   if existing['status']=='done':db.commit();handler.respond(200,ai_studio.view(db,s,user));return
   if existing['status']=='pending' or not body.get('retry'):raise auth_control.AccessError(409,'진행 중인 요청이거나 실패한 요청입니다. 직접 다시 시도하세요.')
   mid=existing['id'];db.execute("UPDATE ai_studio_messages SET status='pending' WHERE id=?",(mid,))
  else:
   if db.execute("SELECT 1 FROM ai_studio_messages WHERE session_id=? AND role='user' AND status='pending'",(sid,)).fetchone():raise auth_control.AccessError(409,'이 대화에서 AI가 처리 중입니다.')
   mid=db.execute("INSERT INTO ai_studio_messages(session_id,nonce,role,mode,content,status,result,baseline) VALUES(?,?,'user','paragraph',?,'pending',?,?)",(sid,nonce,text,ai_studio.pack({'paragraph_request':target}),baseline)).lastrowid
  db.commit()
  item=current['items'][target['item_index']]
  context={'mode':'review','message':text,'focus_index':0,'history':[],
   'selection_only':True,'selected_paragraph':target['before'],
   'draft':{'title':current['title'],'items':[{'category':item['category'],'text':target['before'],'source_ids':item.get('source_ids',[])}]}}
  try:
   result=ai_draft.generate(ai_studio.documents(db,s),actor=user,chat_context=context)
   proposal=result.get('proposed_draft')
   if not proposal or len(proposal.get('items',[]))!=1 or proposal['items'][0]['category']!=item['category']:raise ValueError('선택 문단의 수정안을 확인할 수 없습니다. 문서는 유지됩니다.')
   after=proposal['items'][0]['text']
   if not isinstance(after,str) or not 1<=len(after)<=12000:raise ValueError('문단 수정안의 길이를 확인하세요.')
  except Exception as error:
   db.execute("UPDATE ai_studio_messages SET status='failed' WHERE id=?",(mid,));db.commit()
   status=getattr(error,'http_status',400 if isinstance(error,ValueError) else 502)
   handler.respond(status,{'error':str(error) if isinstance(error,ValueError) else 'AI 수정 요청에 실패했습니다. 저장된 문서는 유지됩니다.'});return
  result={'reply':result['reply'],'mode':result.get('mode'),'model':result.get('model'),
   'paragraph_edit':{**target,'after':after,'instruction':text},'references':result.get('references',{}),
   'document_revisions':{str(d['id']):d['revision'] for d in ai_studio.documents(db,s)}}
  attempt=db.execute("SELECT count(*) FROM ai_studio_messages WHERE session_id=? AND nonce=? AND role='assistant'",(sid,nonce)).fetchone()[0]+1
  db.execute("UPDATE ai_studio_messages SET status='done' WHERE id=?",(mid,))
  db.execute("INSERT INTO ai_studio_messages(session_id,nonce,role,mode,content,status,result,baseline,attempt) VALUES(?,?,'assistant','paragraph',?,'done',?,?,?)",(sid,nonce,result['reply'],ai_studio.pack(result),baseline,attempt))
  db.commit();handler.respond(201,ai_studio.view(db,s,user));return
 db.execute('BEGIN IMMEDIATE')
 editable(db,s)
 message=db.execute("SELECT * FROM ai_studio_messages WHERE id=? AND session_id=? AND role='assistant' AND mode='paragraph' AND status='done'",(body.get('message_id'),sid)).fetchone()
 if not message:raise auth_control.AccessError(404,'이 대화의 문단 수정안만 처리할 수 있습니다.')
 result=ai_studio.unpack(message['result']);target=result['paragraph_edit']
 if target['draft_id']!=s['draft_id']:raise auth_control.AccessError(409,'선택한 문서와 수정안의 문서가 다릅니다.')
 state=message['proposal_state']
 if action=='paragraph-reject':
  if state!='pending':raise auth_control.AccessError(409,'이미 처리한 수정안입니다.')
  db.execute("UPDATE ai_studio_messages SET proposal_state='rejected' WHERE id=?",(message['id'],));event(db,s,message['id'],user,'문단 수정안 취소')
 else:
  undo=action=='paragraph-undo'
  if action not in ('paragraph-apply','paragraph-undo'):raise ValueError('지원하지 않는 문단 작업입니다.')
  if not undo and state=='paragraph_applied':db.commit();handler.respond(200,ai_studio.view(db,s,user));return
  if state!=('paragraph_applied' if undo else 'pending'):raise auth_control.AccessError(409,'이미 처리된 문단 수정안입니다.')
  current=current_draft(db,s)
  expected=result.get('applied_fingerprint') if undo else target['baseline']
  if workflow.fingerprint(current)!=expected:raise auth_control.AccessError(409,'문서가 이후에 변경되었습니다. 최신 내용을 확인하세요. 다른 내용은 덮어쓰지 않았습니다.')
  if not undo:
   for did,revision in result.get('document_revisions',{}).items():
    if not db.execute('SELECT 1 FROM documents WHERE id=? AND workspace_id=? AND revision=? AND deleted=0',(int(did),s['workspace_id'],revision)).fetchone():raise auth_control.AccessError(409,'첨부자료가 변경되었습니다. 새 수정안을 요청하세요.')
  before,after=(target['after'],target['before']) if undo else (target['before'],target['after'])
  index,start=target['item_index'],target['start'];text=current['items'][index]['text']
  if text[start:start+len(before)]!=before:raise auth_control.AccessError(409,'선택 문단이 달라졌습니다. 최신 미리보기에서 다시 선택하세요.')
  updated=copy.deepcopy(current);updated['items'][index]['text']=text[:start]+after+text[start+len(before):];updated['reviewed']=False
  if len(updated['items'][index]['text'])>12000:raise ValueError('수정 후 항목은 12,000자 이내여야 합니다.')
  workflow.baseline(db,s['draft_id'],s['workspace_id'],current)
  db.execute('UPDATE drafts SET payload=? WHERE id=? AND workspace_id=?',(json.dumps(updated,ensure_ascii=False),s['draft_id'],s['workspace_id']))
  workflow.record_version(db,s['draft_id'],s['workspace_id'],updated,user['username'],'paragraph_undo' if undo else 'paragraph_applied')
  if not undo:result['applied_fingerprint']=workflow.fingerprint(updated)
  db.execute('UPDATE ai_studio_messages SET proposal_state=?,result=? WHERE id=?',('paragraph_reverted' if undo else 'paragraph_applied',ai_studio.pack(result),message['id']))
  event(db,s,message['id'],user,'문단 수정 되돌리기' if undo else '선택 문단 수정 반영')
 db.commit();handler.respond(200,ai_studio.view(db,s,user))
