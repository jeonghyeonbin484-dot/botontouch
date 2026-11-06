"""Recipient review, immutable draft versions, AI checks and workspace backups."""
import copy
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qs, quote
import ai_draft
import auth_control
import export_docx
import export_hwpx


def ensure(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS draft_versions(id INTEGER PRIMARY KEY,draft_id INTEGER NOT NULL,workspace_id INTEGER NOT NULL,revision INTEGER NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,actor TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(draft_id,revision));
    CREATE TABLE IF NOT EXISTS acknowledgments(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,draft_id INTEGER NOT NULL,item_index INTEGER NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,note TEXT NOT NULL,actor TEXT NOT NULL,updated TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(draft_id,item_index));
    CREATE TABLE IF NOT EXISTS followups(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,draft_id INTEGER NOT NULL,item_index INTEGER NOT NULL,question TEXT NOT NULL,reply TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'open',actor TEXT NOT NULL,reply_actor TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP,updated TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS document_checks(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,payload TEXT NOT NULL,actor TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def record_version(db, draft_id, workspace_id, payload, actor, kind):
    revision = db.execute('SELECT coalesce(max(revision),0)+1 FROM draft_versions WHERE draft_id=?', (draft_id,)).fetchone()[0]
    if kind == 'final':
        payload=copy.deepcopy(payload)
        payload['version_info']={'revision':revision,'actor':actor,'finalized_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')}
    cursor = db.execute('INSERT INTO draft_versions(draft_id,workspace_id,revision,kind,payload,actor) VALUES(?,?,?,?,?,?)', (draft_id, workspace_id, revision, kind, json.dumps(payload, ensure_ascii=False), actor))
    return cursor.lastrowid


def baseline(db, draft_id, workspace_id, payload):
    if not db.execute('SELECT 1 FROM draft_versions WHERE draft_id=?', (draft_id,)).fetchone():
        record_version(db, draft_id, workspace_id, payload, '이력 도입 전 문서', 'baseline')


def load_draft(db, draft_id, workspace):
    if type(draft_id) is not int:
        raise ValueError('인수인계서를 선택해 주세요.')
    row = db.execute('SELECT payload FROM drafts WHERE id=? AND workspace_id=? AND deleted=0', (draft_id, workspace)).fetchone()
    if not row:
        raise ValueError('인수인계서가 없거나 이 묶음에 속하지 않습니다.')
    return json.loads(row['payload'])


def review_status(db, draft_id, workspace):
    draft = load_draft(db, draft_id, workspace)
    rows = {row['item_index']: dict(row) for row in db.execute('SELECT * FROM acknowledgments WHERE draft_id=? AND workspace_id=?', (draft_id, workspace))}
    items = []
    for index, item in enumerate(draft['items']):
        stored = rows.get(index)
        current = fingerprint(item)
        state = stored['state'] if stored and stored['fingerprint'] == current else 'outdated' if stored else 'pending'
        items.append({'index': index, 'category': item['category'], 'text': item['text'], 'fingerprint': current, 'state': state, 'record': stored})
    followups = [dict(row) for row in db.execute('SELECT * FROM followups WHERE workspace_id=? AND draft_id=? ORDER BY id DESC', (workspace, draft_id))]
    return {'draft_id': draft_id, 'title': draft['title'], 'fingerprint': fingerprint(draft), 'items': items, 'followups': followups, 'confirmed': sum(item['state'] == 'confirmed' for item in items)}


def export_response(handler, payload, extension, filename):
    if extension in ('hwpx','html','md'):
        return __import__('report_export').respond(handler,payload,extension,filename)
    raw = export_hwpx.build(payload) if extension == 'hwpx' else export_docx.build(payload)
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/hwp+zip' if extension == 'hwpx' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    handler.send_header('Content-Disposition', f"attachment; filename=handover.{extension}; filename*=UTF-8''" + quote(filename + '.' + extension))
    handler.send_header('Content-Length', str(len(raw)))
    handler.send_header('Cache-Control','no-store')
    handler.send_header('X-Content-Type-Options','nosniff')
    handler.end_headers()
    handler.wfile.write(raw)


BACKUP_TABLES = {'documents': ('id','name','content','sources','created','revision'), 'drafts': ('id','payload','created'), 'questions': ('id','payload','created'), 'suggestions': ('id','payload','created'), 'tasks': ('id','title','due_date','assignee','done','source'), 'draft_versions': ('id','draft_id','revision','kind','payload','actor','created'), 'acknowledgments': ('id','draft_id','item_index','fingerprint','state','note','actor','updated'), 'followups': ('id','draft_id','item_index','question','reply','state','actor','reply_actor','created','updated'), 'document_checks': ('id','payload','actor','created')}


def backup(db, workspace):
    row = db.execute('SELECT * FROM workspaces WHERE id=?', (workspace,)).fetchone()
    data = {'format': 'batontouch.workspace', 'version': 1, 'exported_kst': datetime.now(timezone(timedelta(hours=9))).isoformat(), 'workspace': dict(row), 'tables': {}}
    for table, fields in BACKUP_TABLES.items():
        condition = ' AND deleted=0' if table in ('documents','drafts','questions','tasks') else ''
        data['tables'][table] = [{field: r[field] for field in fields} for r in db.execute(f'SELECT * FROM {table} WHERE workspace_id=?{condition}', (workspace,))]
    extension=__import__('handover_journey').backup_extension(db,workspace)
    if extension is not None:data['extensions']={'journey':extension}
    return {'data': data, 'sha256': fingerprint(data)}


def restore(db, bundle, user):
    data = bundle.get('data')
    if not isinstance(data, dict) or data.get('format') != 'batontouch.workspace' or data.get('version') != 1 or bundle.get('sha256') != fingerprint(data):
        raise ValueError('지원하는 백업 파일이 아니거나 무결성 검사에 실패했습니다.')
    tables, meta = data.get('tables'), data.get('workspace')
    if not isinstance(tables, dict) or set(tables) != set(BACKUP_TABLES) or not isinstance(meta, dict):
        raise ValueError('백업 구조를 확인해 주세요.')
    for key in ('title','department','predecessor','successor','reference_date'):
        if not isinstance(meta.get(key), str) or len(meta[key]) > 200:
            raise ValueError('백업의 기본 정보 형식이 잘못되었습니다.')
    if not meta['title'].strip():
        raise ValueError('백업에 업무명이 없습니다.')
    for table, rows in tables.items():
        if not isinstance(rows, list) or len(rows) > 5000 or any(not isinstance(row, dict) or set(row) != set(BACKUP_TABLES[table]) or type(row.get('id')) is not int for row in rows):
            raise ValueError('백업 항목 형식이나 개수를 확인해 주세요.')
        if len({row['id'] for row in rows}) != len(rows):
            raise ValueError('백업의 항목 ID가 중복됩니다.')
    db.execute('BEGIN IMMEDIATE')
    cursor = db.execute('INSERT INTO workspaces(title,department,predecessor,successor,reference_date) VALUES(?,?,?,?,?)', (meta['title'][:190]+' (복원)', meta['department'], meta['predecessor'], meta['successor'], meta['reference_date']))
    workspace = cursor.lastrowid
    if user:
        db.execute('INSERT INTO workspace_members VALUES(?,?,?)', (workspace, user['id'], 'editor'))
    document_map, draft_map = {}, {}
    for row in tables['documents']:
        if not all(isinstance(row.get(key), str) for key in ('name','content','sources','created')) or len(row['content']) > 2000000 or type(row['revision']) is not int or row['revision'] < 1:
            raise ValueError('백업 자료 형식이 올바르지 않습니다.')
        sources = json.loads(row['sources'])
        if not isinstance(sources, list) or any(not isinstance(source,dict) or not isinstance(source.get('text'),str) or not isinstance(source.get('location'),str) for source in sources):
            raise ValueError('백업 자료의 출처 형식이 잘못되었습니다.')
        cursor = db.execute('INSERT INTO documents(name,content,sources,created,revision,workspace_id) VALUES(?,?,?,?,?,?)', (row['name'],row['content'],row['sources'],row['created'],row['revision'],workspace))
        document_map[row['id']] = cursor.lastrowid

    def remap_payload(raw, draft=False):
        payload = json.loads(raw)
        if not isinstance(payload,dict):
            raise ValueError('백업 결과 형식이 잘못되었습니다.')
        refs = payload.get('references',{})
        if not isinstance(refs,dict):
            raise ValueError('백업 출처 형식이 잘못되었습니다.')
        for key,ref in refs.items():
            if not isinstance(ref,dict) or not all(isinstance(ref.get(k),str) for k in ('name','location','text')):
                raise ValueError('백업 인용 정보가 잘못되었습니다.')
            old_id=ref.get('document_id')
            if old_id is None:
                match=re.match(r'D(\d+)-S',key);old_id=int(match[1]) if match else None
            if type(old_id) is int:
                ref['document_id']=document_map.get(old_id,-abs(old_id)-1)
        if isinstance(payload.get('documents'),list):
            for doc in payload['documents']:
                if not isinstance(doc,dict) or type(doc.get('id')) is not int:
                    raise ValueError('백업 선택 자료가 잘못되었습니다.')
                doc['id']=document_map.get(doc['id'],-abs(doc['id'])-1)
        if draft:
            ai_draft.validate_draft(payload,refs)
        return json.dumps(payload,ensure_ascii=False)

    for table in ('drafts','questions','suggestions','document_checks'):
        for row in tables[table]:
            payload=remap_payload(row['payload'],table=='drafts')
            if table=='document_checks':
                cursor=db.execute('INSERT INTO document_checks(workspace_id,payload,actor,created) VALUES(?,?,?,?)',(workspace,payload,'복원된 기록',row['created']))
            else:
                cursor=db.execute(f'INSERT INTO {table}(workspace_id,payload,created) VALUES(?,?,?)',(workspace,payload,row['created']))
            if table=='drafts':
                draft_map[row['id']]=cursor.lastrowid
    for row in tables['tasks']:
        if not all(isinstance(row.get(k),str) for k in ('title','due_date','assignee','source')) or row['done'] not in (0,1):
            raise ValueError('할 일 백업 형식이 잘못되었습니다.')
        if row['due_date']:
            from datetime import date
            date.fromisoformat(row['due_date'])
        db.execute('INSERT INTO tasks(workspace_id,title,due_date,assignee,done,source) VALUES(?,?,?,?,?,?)',(workspace,row['title'],row['due_date'],row['assignee'],row['done'],row['source']))
    for row in tables['draft_versions']:
        if row['draft_id'] not in draft_map:
            continue
        payload=json.loads(remap_payload(row['payload'],True))
        payload['restored_record']=True
        db.execute('INSERT INTO draft_versions(workspace_id,draft_id,revision,kind,payload,actor,created) VALUES(?,?,?,?,?,?,?)',(workspace,draft_map[row['draft_id']],row['revision'],row['kind'],json.dumps(payload,ensure_ascii=False),'복원된 기록',row['created']))
    question_map={}
    for table in ('acknowledgments','followups'):
        for row in tables[table]:
            if row['draft_id'] not in draft_map:
                continue
            fields=[key for key in BACKUP_TABLES[table] if key not in ('id','draft_id')]
            values=[row[key] for key in fields]
            values[fields.index('actor')]='복원된 기록'
            if 'reply_actor' in fields: values[fields.index('reply_actor')]='복원된 기록' if row['reply_actor'] else ''
            cursor=db.execute(f'INSERT INTO {table}(workspace_id,draft_id,{",".join(fields)}) VALUES({",".join("?" for _ in range(len(fields)+2))})',[workspace,draft_map[row['draft_id']],*values])
            if table=='followups':question_map[row['id']]=cursor.lastrowid
    extension=data.get('extensions',{})
    if not isinstance(extension,dict):raise ValueError('추가 백업 형식을 확인하세요.')
    if user:__import__('handover_journey').restore_extension(db,extension.get('journey'),question_map,document_map,user)
    return workspace


def handle(handler,factory,method,workspace,source_changes):
    path=urlsplit(handler.path).path
    if not (path.startswith('/api/handover/') or path.startswith('/api/versions/') or path.startswith('/api/checks/') or path.startswith('/api/backup/')):
        return False
    try:
        actor=auth_control.actor(handler)
        if method=='GET':
            with closing(factory()) as db:
                if path=='/api/handover/status':
                    draft_id=int(parse_qs(urlsplit(handler.path).query).get('draft_id',['0'])[0])
                    handler.respond(200,review_status(db,draft_id,workspace));return True
                if path=='/api/handover/versions':
                    draft_id=int(parse_qs(urlsplit(handler.path).query).get('draft_id',['0'])[0]);draft=load_draft(db,draft_id,workspace)
                    rows=db.execute('SELECT * FROM draft_versions WHERE workspace_id=? AND draft_id=? ORDER BY revision DESC',(workspace,draft_id)).fetchall()
                    handler.respond(200,[{'id':row['id'],'revision':row['revision'],'kind':row['kind'],'actor':row['actor'],'created':row['created'],'title':json.loads(row['payload'])['title']} for row in rows]);return True
                match=re.fullmatch(r'/api/versions/(\d+)(?:/export\.(hwpx|docx))?',path)
                if match:
                    row=db.execute('SELECT * FROM draft_versions WHERE id=? AND workspace_id=?',(int(match[1]),workspace)).fetchone()
                    if not row: raise ValueError('문서 버전이 없습니다.')
                    payload=json.loads(row['payload'])
                    if match[2]:
                        export_response(handler,payload,match[2],f"인수인계서_v{row['revision']}")
                    else: handler.respond(200,{'id':row['id'],'revision':row['revision'],'kind':row['kind'],'actor':row['actor'],'created':row['created'],'payload':payload})
                    return True
                if path=='/api/checks/latest':
                    row=db.execute('SELECT * FROM document_checks WHERE workspace_id=? ORDER BY id DESC LIMIT 1',(workspace,)).fetchone()
                    payload=json.loads(row['payload']) if row else None
                    handler.respond(200,{'id':row['id'],'created':row['created'],**payload,'source_changes':source_changes(db,payload,workspace)} if row else None);return True
                if path=='/api/backup/export':
                    db.execute('BEGIN')
                    bundle=backup(db,workspace)
                    raw=json.dumps(bundle,ensure_ascii=False,indent=2).encode()
                    handler.send_response(200);handler.send_header('Content-Type','application/json; charset=utf-8');handler.send_header('Content-Disposition',f'attachment; filename=batontouch-workspace-{workspace}.json');handler.send_header('Content-Length',str(len(raw)));handler.end_headers();handler.wfile.write(raw);return True
        else:
            body=auth_control.read_json(handler,25*1024*1024 if path=='/api/backup/restore' else 2*1024*1024)
            with closing(factory()) as db:
                if path=='/api/backup/restore':
                    try:
                        new_workspace=restore(db,body,getattr(handler,'user',None));db.commit()
                    except Exception:
                        db.rollback();raise
                    handler.respond(201,{'workspace_id':new_workspace});return True
                if path=='/api/checks/run':
                    ids=body.get('document_ids')
                    if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(type(i) is not int for i in ids):raise ValueError('점검할 자료를 1~20개 선택해 주세요.')
                    docs=db.execute('SELECT * FROM documents WHERE workspace_id=? AND deleted=0 AND id IN ('+','.join('?' for _ in ids)+')',[workspace,*ids]).fetchall()
                    if len(docs)!=len(set(ids)):raise ValueError('점검할 자료가 없거나 다른 묶음에 속해 있습니다.')
                    result=ai_draft.generate(docs,document_check=True,actor=handler.user)
                    result['documents']=[{'id':d['id'],'name':d['name']} for d in docs]
                    cursor=db.execute('INSERT INTO document_checks(workspace_id,payload,actor) VALUES(?,?,?)',(workspace,json.dumps(result,ensure_ascii=False),actor));db.commit()
                    handler.respond(201,{'id':cursor.lastrowid,**result});return True
                db.execute('BEGIN IMMEDIATE')
                draft_id=body.get('draft_id');draft=load_draft(db,draft_id,workspace)
                if path=='/api/handover/check':
                    index=body.get('item_index');state=body.get('state');note=body.get('note','')
                    if type(index) is not int or not 0<=index<len(draft['items']) or state not in ('confirmed','needs_info') or not isinstance(note,str) or len(note)>2000:raise ValueError('확인할 항목과 상태·메모를 확인해 주세요.')
                    current=fingerprint(draft['items'][index])
                    if body.get('fingerprint')!=current:raise ValueError('문서가 변경되었습니다. 최신 내용을 불러온 뒤 다시 확인해 주세요.')
                    db.execute("INSERT INTO acknowledgments(workspace_id,draft_id,item_index,fingerprint,state,note,actor) VALUES(?,?,?,?,?,?,?) ON CONFLICT(draft_id,item_index) DO UPDATE SET fingerprint=excluded.fingerprint,state=excluded.state,note=excluded.note,actor=excluded.actor,updated=CURRENT_TIMESTAMP",(workspace,draft_id,index,current,state,note,actor));db.commit()
                    handler.respond(200,review_status(db,draft_id,workspace));return True
                if path=='/api/handover/followup/create':
                    index=body.get('item_index',-1);question=body.get('question')
                    if type(index) is not int or not -1<=index<len(draft['items']) or not isinstance(question,str) or not 1<=len(question.strip())<=2000:raise ValueError('추가 질문과 관련 항목을 확인해 주세요.')
                    db.execute('INSERT INTO followups(workspace_id,draft_id,item_index,question,actor) VALUES(?,?,?,?,?)',(workspace,draft_id,index,question.strip(),actor));db.commit();handler.respond(201,review_status(db,draft_id,workspace));return True
                if path=='/api/handover/followup/reply':
                    reply=body.get('reply');status=body.get('state')
                    if not isinstance(reply,str) or len(reply)>4000 or status not in ('open','resolved') or status=='resolved' and not reply.strip():raise ValueError('답변과 해결 상태를 확인해 주세요.')
                    locked=db.execute("SELECT 1 FROM followups q JOIN handover_requests r ON r.id=q.request_id WHERE q.id=? AND q.workspace_id=? AND q.draft_id=? AND r.state='completed'",(body.get('id'),workspace,draft_id)).fetchone()
                    if locked:raise ValueError('완료된 인수인계의 질문·답변은 변경하지 않습니다.')
                    cursor=db.execute('UPDATE followups SET reply=?,state=?,reply_actor=?,updated=CURRENT_TIMESTAMP WHERE id=? AND workspace_id=? AND draft_id=?',(reply,status,actor,body.get('id'),workspace,draft_id))
                    if not cursor.rowcount:raise ValueError('추가 질문을 찾지 못했습니다.')
                    db.commit();handler.respond(200,review_status(db,draft_id,workspace));return True
                if path=='/api/handover/finalize':
                    if body.get('fingerprint')!=fingerprint(draft):raise ValueError('문서가 변경되었습니다. 최신 내용을 불러온 뒤 확정해 주세요.')
                    if not draft.get('reviewed'):raise ValueError('전임자 검토를 저장한 뒤 확정해 주세요.')
                    if source_changes(db,draft,workspace):raise ValueError('삭제·교체된 출처가 있습니다. 현재 자료로 다시 검토해 주세요.')
                    snapshot=copy.deepcopy(draft)
                    snapshot['workspace']=dict(db.execute('SELECT * FROM workspaces WHERE id=?',(workspace,)).fetchone())
                    snapshot['tasks']=[dict(row) for row in db.execute('SELECT * FROM tasks WHERE workspace_id=? AND deleted=0 ORDER BY id',(workspace,))]
                    snapshot['recipient_review']=review_status(db,draft_id,workspace)
                    baseline(db,draft_id,workspace,draft)
                    version_id=record_version(db,draft_id,workspace,snapshot,actor,'final');db.commit()
                    handler.respond(201,{'version_id':version_id});return True
        handler.respond(404,{'error':'요청한 관리 기능이 없습니다.'})
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,IndexError) as error:
        handler.respond(400,{'error':str(error) if isinstance(error,ValueError) else '입력 또는 백업 파일 형식을 확인해 주세요.'})
    except sqlite3.Error:
        handler.respond(400,{'error':'저장 충돌 또는 백업 구조 오류가 발생했습니다. 기존 데이터는 유지됩니다.'})
    return True
