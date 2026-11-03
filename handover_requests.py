"""Authenticated, employee-addressed handover requests with immutable snapshots."""
import copy
import json
import re
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
import auth_control
import handover_workflow as workflow
import org_directory
import server_settings

STATES = {'requested': '인수 요청', 'reviewing': '인수자 확인 중', 'needs_info': '보완 요청', 'accepted': '인수 수락', 'completed': '인수인계 완료'}
_backup_lock = threading.Lock()


def backup_before_migration(file):
    if not file.exists():
        return
    with _backup_lock:
        with closing(sqlite3.connect(file)) as source:
            if source.execute("SELECT 1 FROM sqlite_master WHERE name='handover_requests'").fetchone():
                return
            folder = file.parent / 'backups'
            folder.mkdir(exist_ok=True)
            target = folder / 'before-org-requests.sqlite3'
            if not target.exists():
                with closing(sqlite3.connect(target)) as dest:
                    source.backup(dest)


def ensure(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS org_departments(id TEXT PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS org_employees(employee_id TEXT PRIMARY KEY,name TEXT NOT NULL,department_id TEXT NOT NULL,position TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,source TEXT NOT NULL DEFAULT 'manual',updated TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS idx_org_employee_department ON org_employees(department_id,active,name);
    CREATE TABLE IF NOT EXISTS employee_accounts(employee_id TEXT PRIMARY KEY,user_id INTEGER UNIQUE NOT NULL,linked_by INTEGER NOT NULL,linked_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS handover_requests(id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,draft_id INTEGER NOT NULL,sender_account INTEGER NOT NULL,recipient_account INTEGER NOT NULL,sender_employee TEXT NOT NULL,recipient_employee TEXT NOT NULL,sender_snapshot TEXT NOT NULL,recipient_snapshot TEXT NOT NULL,payload TEXT NOT NULL,documents TEXT NOT NULL,draft_fingerprint TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 1,created TEXT DEFAULT CURRENT_TIMESTAMP,updated TEXT DEFAULT CURRENT_TIMESTAMP,accepted_at TEXT,completed_at TEXT,version_id INTEGER);
    CREATE INDEX IF NOT EXISTS idx_requests_recipient ON handover_requests(recipient_account,state,id);
    CREATE INDEX IF NOT EXISTS idx_requests_sender ON handover_requests(sender_account,id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_active_draft ON handover_requests(draft_id) WHERE state!='completed';
    CREATE TABLE IF NOT EXISTS request_history(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL,actor_account INTEGER NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS request_snapshots(request_id INTEGER NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,documents TEXT NOT NULL,sender_snapshot TEXT NOT NULL,recipient_snapshot TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(request_id,revision));
    CREATE TABLE IF NOT EXISTS document_files(document_id INTEGER PRIMARY KEY,workspace_id INTEGER NOT NULL,revision INTEGER NOT NULL,name TEXT NOT NULL,raw BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS request_files(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL,revision INTEGER NOT NULL,document_id INTEGER NOT NULL,name TEXT NOT NULL,raw BLOB NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_request_files ON request_files(request_id,revision);
    CREATE TABLE IF NOT EXISTS directory_audit(id INTEGER PRIMARY KEY,actor_account INTEGER NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,details TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    request_columns={r['name']:r for r in db.execute('PRAGMA table_info(handover_requests)')}
    if request_columns['recipient_account']['notnull']:
        sql=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='handover_requests'").fetchone()[0]
        indexes=[r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='handover_requests' AND sql IS NOT NULL")]
        columns=','.join('"'+c+'"' for c in request_columns)
        db.execute('SAVEPOINT nullable_recipient')
        try:
            db.execute(sql.replace('handover_requests','handover_requests_nullable',1).replace('recipient_account INTEGER NOT NULL','recipient_account INTEGER'))
            db.execute('INSERT INTO handover_requests_nullable('+columns+') SELECT '+columns+' FROM handover_requests')
            db.execute('DROP TABLE handover_requests')
            db.execute('ALTER TABLE handover_requests_nullable RENAME TO handover_requests')
            for statement in indexes:db.execute(statement)
            db.execute('RELEASE nullable_recipient')
        except Exception:
            db.execute('ROLLBACK TO nullable_recipient');db.execute('RELEASE nullable_recipient');raise
    if 'recipient_saeoll_id' not in request_columns:
        db.execute('ALTER TABLE handover_requests ADD COLUMN recipient_saeoll_id TEXT')
        db.execute("UPDATE handover_requests SET recipient_saeoll_id=lower(json_extract(recipient_snapshot,'$.saeoll_id'))")
    db.execute('CREATE INDEX IF NOT EXISTS idx_requests_pending_identity ON handover_requests(recipient_employee,recipient_saeoll_id) WHERE recipient_account IS NULL')
    dept_columns={r['name'] for r in db.execute('PRAGMA table_info(org_departments)')}
    for column,definition in [('parent_id',"TEXT NOT NULL DEFAULT ''"),('sort_order',"TEXT NOT NULL DEFAULT ''"),('source',"TEXT NOT NULL DEFAULT 'manual'"),('synced_at','TEXT'),('mode',"TEXT NOT NULL DEFAULT ''"),('team_flag',"TEXT NOT NULL DEFAULT ''"),('hidden_from_picker','INTEGER NOT NULL DEFAULT 0')]:
        if column not in dept_columns:db.execute('ALTER TABLE org_departments ADD COLUMN '+column+' '+definition)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS org_sync_runs(id INTEGER PRIMARY KEY,started TEXT DEFAULT CURRENT_TIMESTAMP,finished TEXT,state TEXT NOT NULL,actor INTEGER NOT NULL,report TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS org_changes(id INTEGER PRIMARY KEY,employee_id TEXT NOT NULL,old_department TEXT,new_department TEXT,old_position TEXT,new_position TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    columns={r['name'] for r in db.execute('PRAGMA table_info(org_employees)')}
    if 'saeoll_id' not in columns:db.execute('ALTER TABLE org_employees ADD COLUMN saeoll_id TEXT')
    if 'employment_status' not in columns:db.execute("ALTER TABLE org_employees ADD COLUMN employment_status TEXT NOT NULL DEFAULT 'active'")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_saeoll ON org_employees(saeoll_id) WHERE saeoll_id IS NOT NULL AND saeoll_id!=''")


def fail(status, text):
    raise auth_control.AccessError(status, text)


def text(body, key, limit=200, required=True):
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > limit or required and not value.strip():
        raise ValueError(key + ' 입력을 확인하세요.')
    return value.strip()


def audit(db, user, action, target='', details=''):
    db.execute('INSERT INTO directory_audit(actor_account,action,target,details) VALUES(?,?,?,?)', (user['id'], action, target, details))


def employee(db, employee_id):
    row = db.execute('SELECT e.employee_id,e.name,e.position,e.department_id,d.name AS department,e.active,e.saeoll_id,e.employment_status,e.source,d.active AS department_active,a.user_id,u.active AS account_active,u.username AS account_username FROM org_employees e JOIN org_departments d ON d.id=e.department_id LEFT JOIN employee_accounts a ON a.employee_id=e.employee_id LEFT JOIN users u ON u.id=a.user_id WHERE e.employee_id=?', (employee_id,)).fetchone()
    if not row or not row['active'] or not row['department_active'] or row['employment_status']!='active':
        fail(409, '재직 중인 등록 직원과 부서를 선택하세요.')
    if row['source']=='test' and not server_settings.dev_test_accounts():fail(403,'개발 전용 가상 직원입니다.')
    return dict(row)


def linked_employee(db, user):
    row = db.execute('SELECT employee_id FROM employee_accounts WHERE user_id=?', (user['id'],)).fetchone()
    if not row:
        fail(409, '관리자가 로그인 계정과 조직도 USER_ID를 먼저 연결해야 합니다.')
    staff=employee(db,row['employee_id'])
    if not staff['saeoll_id'] or staff['saeoll_id']!=user['username']:fail(409,'기존 계정의 공식 SAEOLL_ID를 관리자가 확인·반영한 뒤 요청을 처리하세요.')
    return staff


def history(db, row, user, action, details=''):
    db.execute('INSERT INTO request_history(request_id,actor_account,action,details) VALUES(?,?,?,?)', (row['id'], user['id'], action, details))


def bind_pending_requests(db,user):
    staff=db.execute('SELECT e.employee_id,e.saeoll_id FROM employee_accounts a JOIN org_employees e ON e.employee_id=a.employee_id JOIN users u ON u.id=a.user_id WHERE a.user_id=? AND u.active=1 AND e.active=1 AND e.saeoll_id=u.username',(user['id'],)).fetchone()
    if not staff or not staff['saeoll_id']:return
    rows=db.execute('SELECT id FROM handover_requests WHERE recipient_account IS NULL AND recipient_employee=? AND recipient_saeoll_id=?',(staff['employee_id'],staff['saeoll_id'])).fetchall()
    for row in rows:
        cursor=db.execute('UPDATE handover_requests SET recipient_account=? WHERE id=? AND recipient_account IS NULL AND recipient_employee=? AND recipient_saeoll_id=? AND EXISTS(SELECT 1 FROM employee_accounts a JOIN org_employees e ON e.employee_id=a.employee_id JOIN users u ON u.id=a.user_id WHERE a.user_id=? AND e.employee_id=handover_requests.recipient_employee AND e.saeoll_id=handover_requests.recipient_saeoll_id AND u.username=e.saeoll_id)',(user['id'],row['id'],staff['employee_id'],staff['saeoll_id'],user['id']))
        if cursor.rowcount:db.execute("INSERT INTO request_history(request_id,actor_account,action,details) VALUES(?,?,'수신 계정 연결','직원 식별값과 SAEOLL_ID 일치 확인')",(row['id'],user['id']))


def request_row(db, user, request_id):
    row = db.execute('SELECT * FROM handover_requests WHERE id=?', (request_id,)).fetchone()
    if not row:
        fail(404, '인수인계 요청을 찾을 수 없습니다.')
    if user['id'] not in (row['sender_account'], row['recipient_account']):
        fail(403, '본인이 보내거나 받은 요청만 확인할 수 있습니다.')
    return row


def assert_sender(db, user, row):
    if user['id'] != row['sender_account'] or linked_employee(db, user)['employee_id'] != row['sender_employee']:
        fail(403, '요청을 보낸 본인만 처리할 수 있습니다.')
    auth_control.workspace_access(db, user, row['workspace_id'], True)


def assert_recipient(db, user, row):
    if user['id'] != row['recipient_account'] or linked_employee(db, user)['employee_id'] != row['recipient_employee']:
        fail(403, '지정된 인수자 본인만 처리할 수 있습니다.')


def summary(row):
    return {key: row[key] for key in ('id','workspace_id','draft_id','state','reason','revision','created','updated','accepted_at','completed_at','version_id')} | {'recipient_account_pending':row['recipient_account'] is None, 'state_label': STATES[row['state']], 'title': json.loads(row['payload'])['title'], 'sender': json.loads(row['sender_snapshot']), 'recipient': json.loads(row['recipient_snapshot'])}


def detail(db, user, request_id):
    row = request_row(db, user, request_id)
    return summary(row) | {'payload': json.loads(row['payload']), 'documents': json.loads(row['documents']), 'fingerprint': row['draft_fingerprint'], 'files': [dict(f) for f in db.execute('SELECT id,document_id,name,length(raw) AS bytes FROM request_files WHERE request_id=? AND revision=?',(request_id,row['revision']))], 'can_receive': user['id']==row['recipient_account'], 'can_send': user['id']==row['sender_account'], 'history': [dict(r) for r in db.execute('SELECT h.id,h.action,h.details,h.created,u.username AS actor FROM request_history h JOIN users u ON u.id=h.actor_account WHERE request_id=? ORDER BY h.id', (request_id,))]}


def send(db, user, body, source_changes=None):
    workspace, draft_id = body.get('workspace_id'), body.get('draft_id')
    if type(workspace) is not int or type(draft_id) is not int:
        raise ValueError('업무 묶음과 저장된 인수인계서를 선택하세요.')
    auth_control.workspace_access(db, user, workspace, True)
    sender = linked_employee(db, user)
    target_id=text(body,'recipient_employee')
    cached=db.execute('SELECT 1 FROM org_employees WHERE employee_id=?',(target_id,)).fetchone()
    recipient=employee(db,target_id) if cached else None
    cfg=org_directory.settings()
    if cfg.get('enabled') is True and cfg.get('approved') is True:
        dept=body.get('recipient_department') or (recipient['department_id'] if recipient else '')
        department=db.execute('SELECT * FROM org_departments WHERE id=? AND active=1',(dept,)).fetchone()
        if not department or department['hidden_from_picker']:fail(409,'신규 요청이 가능한 부서를 선택하세요.')
        official=next((item for item in org_directory.fetch_employees(dept,None) if item['employee_id']==target_id),None)
        if not official:fail(409,'선택한 직원이 현재 부서 조직도에 없습니다. 다시 조회하세요.')
        if official.get('employment_status','active')!='active':fail(409,'재직 상태 확인이 필요한 직원입니다.')
        if recipient is None:recipient={'user_id':None,'account_username':None,'account_active':0,'employee_id':target_id}
        recipient.update(saeoll_id=official['saeoll_id'],name=official['name'],position=official['position'],department_id=dept,department=official.get('department_name',department['name']))
    if recipient is None:fail(409,'직원을 조직도에서 다시 선택하세요.')
    if not recipient['saeoll_id']:fail(409,'이 직원은 SAEOLL_ID 누락으로 인수인계 수신 대상이 아닙니다.')
    if db.execute('SELECT hidden_from_picker FROM org_departments WHERE id=?',(recipient['department_id'],)).fetchone()[0]:fail(409,'폐지부서 하위 조직에는 신규 인수인계를 요청할 수 없습니다.')
    recipient_account=recipient['user_id'] if recipient['account_username']==recipient['saeoll_id'] else None
    if recipient['employee_id']==sender['employee_id'] or recipient['saeoll_id']==sender['saeoll_id'] or recipient_account == user['id']:
        raise ValueError('본인에게 인수인계를 요청할 수 없습니다.')
    draft = workflow.load_draft(db, draft_id, workspace)
    if body.get('fingerprint') != workflow.fingerprint(draft):
        fail(409, '문서가 변경되었습니다. 저장된 최신 문서를 다시 불러오세요.')
    if not draft.get('reviewed'):
        fail(409, '전임자 검토 완료를 저장한 뒤 인수인계를 요청하세요.')
    if source_changes and source_changes(db,draft,workspace):fail(409,'삭제·교체된 출처가 있습니다. 최신 자료로 검토한 뒤 요청하세요.')
    old = db.execute("SELECT * FROM handover_requests WHERE draft_id=? AND state!='completed'", (draft_id,)).fetchone()
    if old:
        assert_sender(db, user, old)
        recipient_question=db.execute("SELECT 1 FROM followups WHERE request_id=? AND origin='recipient' LIMIT 1",(old['id'],)).fetchone()
        same_target_update=recipient['employee_id']==old['recipient_employee'] and workflow.fingerprint(draft)!=old['draft_fingerprint']
        if old['state'] not in ('requested','needs_info') and not (same_target_update and (old['state']=='accepted' or old['state']=='reviewing' and recipient_question)):
            fail(409, '인수자 확인 중이거나 수락한 요청은 대상 변경·재요청할 수 없습니다.')
    import handover_journey
    snapshot = copy.deepcopy(draft)
    snapshot['gap_review']=handover_journey.snapshot(db,draft_id)
    snapshot['workspace'] = dict(db.execute('SELECT * FROM workspaces WHERE id=?', (workspace,)).fetchone())
    snapshot['tasks'] = [dict(r) for r in db.execute('SELECT * FROM tasks WHERE workspace_id=? AND deleted=0 ORDER BY id', (workspace,))]
    ids = {r.get('document_id') for r in draft.get('references',{}).values() if type(r.get('document_id')) is int}
    for key in draft.get('references', {}):
        match = re.match(r'D(\d+)-S', key)
        if match: ids.add(int(match[1]))
    docs = []
    for doc_id in sorted(ids):
        row = db.execute('SELECT id,name,content,sources,revision FROM documents WHERE id=? AND workspace_id=? AND deleted=0', (doc_id,workspace)).fetchone()
        if not row: fail(409,'삭제된 근거 자료가 있습니다. 현재 자료로 검토한 뒤 요청하세요.')
        for ref in draft.get('references',{}).values():
            if ref.get('document_id')==doc_id and ref.get('revision',1)!=row['revision']:fail(409,'교체된 출처가 있습니다. 현재 자료로 다시 검토하세요.')
        docs.append(dict(row) | {'sources': json.loads(row['sources'])})
    if len(workflow.canonical(snapshot).encode())+len(workflow.canonical(docs).encode())>20*1024*1024:
        fail(413,'요청 자료가 20MB를 초과합니다. 업무 묶음을 나눠 주세요.')
    values = (recipient_account,recipient['employee_id'],workflow.canonical(sender),workflow.canonical(recipient),workflow.canonical(snapshot),workflow.canonical(docs),workflow.fingerprint(draft))
    if old:
        request_id=old['id'];revision=old['revision']+1
        db.execute("UPDATE handover_requests SET recipient_account=?,recipient_employee=?,sender_snapshot=?,recipient_snapshot=?,payload=?,documents=?,draft_fingerprint=?,state='requested',reason='',revision=?,accepted_at=NULL,updated=CURRENT_TIMESTAMP WHERE id=?", (*values,revision,request_id))
    else:
        cursor=db.execute("INSERT INTO handover_requests(workspace_id,draft_id,sender_account,sender_employee,recipient_account,recipient_employee,sender_snapshot,recipient_snapshot,payload,documents,draft_fingerprint,state) VALUES(?,?,?,?,?,?,?,?,?,?,?,'requested')", (workspace,draft_id,user['id'],sender['employee_id'],*values))
        request_id=cursor.lastrowid;revision=1
    db.execute('UPDATE handover_requests SET recipient_saeoll_id=? WHERE id=?',(recipient['saeoll_id'],request_id))
    db.execute('UPDATE followups SET request_id=? WHERE draft_id=? AND workspace_id=? AND request_id IS NULL',(request_id,draft_id,workspace))
    total=0
    for doc in docs:
        binary=db.execute('SELECT length(raw) FROM document_files WHERE document_id=? AND workspace_id=? AND revision=?',(doc['id'],workspace,doc['revision'])).fetchone()
        total+=binary[0] if binary else 0
    if total>100*1024*1024:fail(413,'요청 원본 파일 합계가 100MB를 초과합니다. 문서를 나누어 주세요.')
    for doc in docs:
        db.execute('INSERT INTO request_files(request_id,revision,document_id,name,raw) SELECT ?,?,document_id,name,raw FROM document_files WHERE document_id=? AND workspace_id=? AND revision=?',(request_id,revision,doc['id'],workspace,doc['revision']))
    db.execute('INSERT INTO request_snapshots(request_id,revision,payload,documents,sender_snapshot,recipient_snapshot) VALUES(?,?,?,?,?,?)',(request_id,revision,values[4],values[5],values[2],values[3]))
    row=request_row(db,user,request_id)
    change='요청 버전 '+str(revision)
    if old and old['recipient_employee']!=recipient['employee_id']:
        previous=json.loads(old['recipient_snapshot'])
        change+=' | '+previous['department']+' · '+previous['name']+' ('+old['recipient_employee']+') → '+recipient['department']+' · '+recipient['name']+' ('+recipient['employee_id']+')'
    history(db,row,user,('인수자 변경·재요청' if old['recipient_employee']!=recipient['employee_id'] else '보완·수정 재요청') if old else '인수인계 요청',change)
    return request_id


def act(db,user,body,source_changes):
    
    if type(body.get('id')) is not int:raise ValueError('요청 ID를 확인하세요.')
    row=request_row(db,user,body.get('id'));action=body.get('action')
    if type(body.get('revision')) is not int or body['revision']!=row['revision']:
        fail(409,'요청이 변경되었습니다. 다시 불러오세요.')
    if action in ('view','accept','needs_info'):
        assert_recipient(db,user,row)
        if row['state'] not in ('requested','reviewing'):
            fail(409,'현재 상태에서는 인수 처리할 수 없습니다.')
        new={'view':'reviewing','accept':'accepted','needs_info':'needs_info'}[action]
        reason=text(body,'reason',2000) if action=='needs_info' else ''
        db.execute("UPDATE handover_requests SET state=?,reason=?,accepted_at=CASE WHEN ?='accepted' THEN CURRENT_TIMESTAMP ELSE accepted_at END,updated=CURRENT_TIMESTAMP WHERE id=?",(new,reason,new,row['id']))
        history(db,row,user,STATES[new],reason)
    elif action=='complete':
        assert_sender(db,user,row)
        if row['state']!='accepted':fail(409,'인수자가 수락한 요청만 완료할 수 있습니다.')
        draft=workflow.load_draft(db,row['draft_id'],row['workspace_id'])
        if workflow.fingerprint(draft)!=row['draft_fingerprint'] or not draft.get('reviewed') or source_changes(db,draft,row['workspace_id']):
            fail(409,'수락한 문서와 현재 문서·출처가 다릅니다. 원문과 요청 이력을 확인하세요.')
        snapshot=json.loads(row['payload']);snapshot['gap_review']=__import__('handover_journey').snapshot(db,row['draft_id']);snapshot['recipient_review']={'confirmed':len(snapshot.get('items',[])), 'request_id':row['id'], 'accepted_at':row['accepted_at'], 'followups':__import__('handover_journey').question_rows(db,request_id=row['id']), 'items':[{'category':item['category'],'state':'confirmed','record':{'actor':json.loads(row['recipient_snapshot'])['name'],'note':'문서 전체 인수 수락'}} for item in snapshot.get('items',[])]}
        version=workflow.record_version(db,row['draft_id'],row['workspace_id'],snapshot,user['username'],'final')
        db.execute("UPDATE handover_requests SET state='completed',version_id=?,completed_at=CURRENT_TIMESTAMP,updated=CURRENT_TIMESTAMP WHERE id=?",(version,row['id']))
        history(db,row,user,STATES['completed'])
    else:raise ValueError('지원하지 않는 처리 작업입니다.')


def disable_staff_accounts(db,user,ids):
    targets=[]
    for identifier in ids:
        row=db.execute('SELECT u.id,u.role,u.active FROM employee_accounts a JOIN users u ON u.id=a.user_id WHERE a.employee_id=?',(identifier,)).fetchone()
        if row:targets.append(row)
    affected=sum(r['role']=='admin' and r['active'] for r in targets)
    total=db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
    if affected and total<=affected:fail(409,'마지막 활성 관리자의 부서·재직 상태를 비활성화할 수 없습니다.')
    for row in targets:
        db.execute('UPDATE users SET active=0 WHERE id=?',(row['id'],));db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
        db.execute("INSERT INTO auth_audit(user_id,actor_id,action,ip,details) VALUES(?,?,'재직 상태에 따른 계정 비활성화','','')",(row['id'],user['id']))


def admin(db,user,body,path):
    if 'active' in body and type(body['active']) is not bool:raise ValueError('활성 상태는 체크 여부로 지정하세요.')
    if user['role']!='admin':fail(403,'조직정보 등록·계정 연결은 관리자만 가능합니다.')
    if path=='/api/directory/departments':
        key,name=text(body,'id',100),text(body,'name')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',key):raise ValueError('부서 ID 형식을 확인하세요.')
        if body.get('active',True) is False:disable_staff_accounts(db,user,[r[0] for r in db.execute('SELECT employee_id FROM org_employees WHERE department_id=?',(key,))])
        db.execute('INSERT INTO org_departments(id,name,active) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,active=excluded.active',(key,name,int(body.get('active',True) is True)));audit(db,user,'부서 등록·수정',key)
    elif path=='/api/directory/employees':
        item={'employee_id':text(body,'employee_id',100),'name':text(body,'name'),'department_id':text(body,'department_id',100),'position':text(body,'position',200,False)}
        if not db.execute('SELECT 1 FROM org_departments WHERE id=? AND active=1',(item['department_id'],)).fetchone():raise ValueError('등록된 부서를 먼저 선택하세요.')
        saeoll=body.get('saeoll_id')
        if saeoll is not None:saeoll=auth_control.validate_username(saeoll)
        previous=db.execute('SELECT * FROM org_employees WHERE employee_id=?',(item['employee_id'],)).fetchone()
        if saeoll is None and previous:saeoll=previous['saeoll_id']
        mapping=db.execute('SELECT u.username FROM employee_accounts a JOIN users u ON u.id=a.user_id WHERE a.employee_id=?',(item['employee_id'],)).fetchone()
        if mapping and mapping['username']!=saeoll:fail(409,'연결된 계정과 SAEOLL_ID가 다릅니다. 관리자 계정 이전 검토가 필요합니다.')
        test=body.get('is_test') is True
        if test and not(server_settings.dev_test_accounts() and item['employee_id'].startswith('TEST-') and (saeoll or '').startswith('test.') and (not previous or previous['source']=='test')):fail(403,'가상 직원은 개발 테스트 모드와 TEST-/test. 식별값이 필요합니다.')
        status=body.get('employment_status','active' if body.get('active',True) else 'inactive')
        if status not in ('active','inactive','retired','transferred'):raise ValueError('재직 상태를 확인하세요.')
        enabled=body.get('active',True) is True and status=='active'
        if not enabled:disable_staff_accounts(db,user,[item['employee_id']])
        db.execute("INSERT INTO org_employees(employee_id,name,department_id,position,active) VALUES(?,?,?,?,?) ON CONFLICT(employee_id) DO UPDATE SET name=excluded.name,department_id=excluded.department_id,position=excluded.position,active=excluded.active,updated=CURRENT_TIMESTAMP",(*item.values(),int(enabled)));db.execute('UPDATE org_employees SET saeoll_id=?,employment_status=?,source=? WHERE employee_id=?',(saeoll,status,'test' if test or previous and previous['source']=='test' else previous['source'] if previous else 'manual',item['employee_id']));audit(db,user,'직원 등록·수정',item['employee_id'])
    elif path=='/api/directory/link':
        employee_id=text(body,'employee_id',100);user_id=body.get('user_id');staff=employee(db,employee_id)
        if type(user_id) is not int or not db.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone():raise ValueError('로그인 계정을 선택하세요.')
        account=db.execute('SELECT username FROM users WHERE id=?',(user_id,)).fetchone()
        if not staff['saeoll_id'] or account['username']!=staff['saeoll_id']:fail(409,'계정 아이디가 공식 SAEOLL_ID와 같아야 합니다. 누락된 값을 임의 생성하지 않습니다.')
        previous=db.execute('SELECT * FROM employee_accounts WHERE employee_id=? OR user_id=?',(employee_id,user_id)).fetchall()
        if any(r['user_id']!=user_id or r['employee_id']!=employee_id for r in previous):fail(409,'직원 또는 계정이 이미 다른 대상과 연결되어 있습니다. 자동 병합하지 않습니다.')
        db.execute('INSERT INTO employee_accounts(employee_id,user_id,linked_by) VALUES(?,?,?) ON CONFLICT(employee_id) DO UPDATE SET linked_by=excluded.linked_by,linked_at=CURRENT_TIMESTAMP',(employee_id,user_id,user['id']));audit(db,user,'계정 USER_ID 연결',employee_id,str(user_id))
    else:raise ValueError('등록 경로가 없습니다.')


def sync_directory(db, user, dept, items):
    if not items:raise ValueError('조직도 응답 직원이 0명입니다. 부서를 임의로 생성하지 않았습니다.')
    names={item.get('department_name') for item in items if item.get('department_name')}
    if len(names)>1:raise ValueError('단일 부서 조회에 여러 부서명이 반환되었습니다.')
    db.execute('BEGIN IMMEDIATE')
    if names:
        db.execute('INSERT INTO org_departments(id,name,active) VALUES(?,?,1) ON CONFLICT(id) DO UPDATE SET name=excluded.name',(dept,next(iter(names))))
    if not db.execute('SELECT 1 FROM org_departments WHERE id=? AND active=1',(dept,)).fetchone():raise ValueError('활성 부서 정보가 필요합니다.')
    for item in items:
        if item['department_id']!=dept:raise ValueError('직원 부서 코드가 다릅니다.')
        existing=db.execute('SELECT source FROM org_employees WHERE employee_id=?',(item['employee_id'],)).fetchone()
        if existing and existing[0]=='test':fail(409,'가상 직원 식별값 충돌입니다. 자동 병합하지 않습니다.')
        linked=db.execute('SELECT u.username FROM employee_accounts a JOIN users u ON u.id=a.user_id WHERE a.employee_id=?',(item['employee_id'],)).fetchone()
        if linked and item['saeoll_id'] is not None and linked['username']!=item['saeoll_id']:fail(409,'SAEOLL_ID 변경 충돌입니다. 관리자 확인이 필요합니다.')
        prior=db.execute('SELECT department_id,position FROM org_employees WHERE employee_id=?',(item['employee_id'],)).fetchone()
        if prior and (prior['department_id']!=dept or prior['position']!=item['position']):db.execute('INSERT INTO org_changes(employee_id,old_department,new_department,old_position,new_position) VALUES(?,?,?,?,?)',(item['employee_id'],prior['department_id'],dept,prior['position'],item['position']))
        db.execute("INSERT INTO org_employees(employee_id,name,department_id,position,source,saeoll_id) VALUES(?,?,?,?,'org_api',?) ON CONFLICT(employee_id) DO UPDATE SET name=excluded.name,department_id=excluded.department_id,position=excluded.position,source='org_api',saeoll_id=excluded.saeoll_id,updated=CURRENT_TIMESTAMP",(item['employee_id'],item['name'],dept,item['position'],item['saeoll_id']))
        status=item.get('employment_status')
        if status in ('inactive','retired','transferred'):
            disable_staff_accounts(db,user,[item['employee_id']])
            db.execute('UPDATE org_employees SET active=0,employment_status=? WHERE employee_id=?',(status,item['employee_id']))
        # Returning personnel are not automatically reactivated; administrator approval stays required.
    audit(db,user,'조직도 갱신',dept,str(len(items)))
    db.commit()


def handle(handler,factory,method,source_changes=None):
    path=urlsplit(handler.path).path
    if not(path.startswith('/api/directory/') or path.startswith('/api/requests')):return False
    try:
        with closing(factory()) as db:
            user=auth_control.identity(handler,db)
            if not user:fail(401,'직원 간 인수인계 요청은 로그인 활성화와 계정 연결이 필요합니다. 기본 정보에서 관리자를 먼저 등록하세요.')
            bind_pending_requests(db,user);db.commit()
            query=parse_qs(urlsplit(handler.path).query)
            if method=='GET':
                if path=='/api/directory/status':
                    cfg=org_directory.settings();link=db.execute('SELECT employee_id FROM employee_accounts WHERE user_id=?',(user['id'],)).fetchone()
                    handler.respond(200,{'linked_employee':employee(db,link[0]) if link else None,'live_enabled':cfg.get('enabled') is True and cfg.get('approved') is True,'notice':'부서는 공식 전체 부서 API 동기화 목록입니다. 부서 선택 시 직원 API를 실시간 조회하며, 계정 발급과 활성화는 관리자 승인이 필요합니다.'});return True
                if path=='/api/directory/departments':
                    import org_sync
                    handler.respond(200,org_sync.department_tree(db));return True
                if path=='/api/directory/employees':
                    dept=query.get('department_id',[''])[0]
                    if query.get('live',[''])[0]=='1':
                        import org_sync
                        handler.respond(200,org_sync.live_lookup(db,user,dept,query));return True
                    keyword=query.get('q',[''])[0][:100];page=max(1,int(query.get('page',['1'])[0]));term='%'+keyword.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                    args=(dept,term,term);where="e.department_id=? AND e.active=1 AND d.active=1 AND (e.name LIKE ? ESCAPE '\\' OR e.position LIKE ? ESCAPE '\\')"
                    rows=db.execute('SELECT e.employee_id,e.name,e.position,d.name AS department,e.department_id,(a.user_id IS NOT NULL AND u.active=1 AND e.saeoll_id IS NOT NULL AND e.saeoll_id=u.username) AS account_linked,(e.saeoll_id IS NOT NULL AND length(e.saeoll_id)>0) AS account_eligible,COUNT(*) OVER(PARTITION BY e.department_id,e.name,e.position) AS duplicate_count' + (',e.saeoll_id,e.source' if user['role']=='admin' else '') + ' FROM org_employees e JOIN org_departments d ON d.id=e.department_id LEFT JOIN employee_accounts a ON a.employee_id=e.employee_id LEFT JOIN users u ON u.id=a.user_id WHERE '+where+' ORDER BY e.name,e.position,e.employee_id LIMIT 50 OFFSET ?',(*args,(page-1)*50)).fetchall()
                    total=db.execute('SELECT count(*) FROM org_employees e JOIN org_departments d ON d.id=e.department_id WHERE '+where,args).fetchone()[0]
                    audit(db,user,'직원 검색',dept);db.commit();handler.respond(200,{'items':[dict(r) for r in rows],'total':total,'page':page,'page_size':50});return True
                if path in ('/api/directory/inspection','/api/directory/inspection.csv'):
                    if user['role']!='admin':fail(403,'관리자만 조직도 점검 결과를 조회할 수 있습니다.')
                    folder=Path(db.execute('PRAGMA database_list').fetchone()[2]).parent/'org-inspection'
                    if not (folder/'summary.json').exists():fail(404,'아직 실제 조직도 점검 결과가 없습니다.')
                    if path.endswith('.csv'):
                        filename={'failures':'직원조회_실패부서.csv','all':'전체부서_조회결과.csv','suspects':'폐지의심_명칭확인필요.csv'}.get(query.get('kind',['failures'])[0])
                        if not filename:raise ValueError('다운로드 종류를 확인하세요.')
                        raw=(folder/filename).read_bytes();handler.send_response(200);handler.send_header('Content-Type','text/csv; charset=utf-8');handler.send_header('Content-Disposition',"attachment; filename=departments.csv; filename*=UTF-8''"+quote(filename));handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(raw)));handler.end_headers();handler.wfile.write(raw);return True
                    results=json.loads((folder/'results.json').read_text(encoding='utf-8'))
                    handler.respond(200,{'summary':json.loads((folder/'summary.json').read_text(encoding='utf-8')),'failures':[r for r in results if r['result'] not in ('success','empty')]});return True
                if path=='/api/directory/sync-status':
                    if user['role']!='admin':fail(403,'관리자만 동기화 결과를 볼 수 있습니다.')
                    import org_sync
                    handler.respond(200,org_sync.latest(db));return True
                if path=='/api/directory/audit':
                    if user['role']!='admin':fail(403,'관리자만 조회할 수 있습니다.')
                    handler.respond(200,[dict(r) for r in db.execute('SELECT * FROM directory_audit ORDER BY id DESC LIMIT 100')]);return True
                if path=='/api/requests':
                    kind=query.get('box',['received'])[0]
                    if kind not in ('received','sent'):raise ValueError('요청함을 선택하세요.')
                    field='recipient_account' if kind=='received' else 'sender_account'
                    rows=db.execute("SELECT id,workspace_id,draft_id,recipient_account,state,reason,revision,created,updated,accepted_at,completed_at,version_id,sender_snapshot,recipient_snapshot,json_object('title',json_extract(payload,'$.title')) AS payload FROM handover_requests WHERE "+field+'=? ORDER BY id DESC LIMIT 200',(user['id'],)).fetchall()
                    handler.respond(200,{'items':[summary(r) for r in rows],'pending':db.execute('SELECT count(*) FROM handover_requests WHERE '+field+"=? AND state IN ('requested','reviewing')",(user['id'],)).fetchone()[0]});return True
                file_match=re.fullmatch(r'/api/requests/(\d+)/files/(\d+)',path)
                if file_match:
                    row=request_row(db,user,int(file_match[1]))
                    f=db.execute('SELECT name,raw FROM request_files WHERE id=? AND request_id=? AND revision=?',(int(file_match[2]),row['id'],row['revision'])).fetchone()
                    if not f:fail(404,'요청에 연결된 원본 파일이 없습니다.')
                    handler.send_response(200);handler.send_header('Content-Type','application/octet-stream');handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Cache-Control','no-store');handler.send_header('Content-Disposition',"attachment; filename=handover-source; filename*=UTF-8''"+quote(f['name'],safe=''));handler.send_header('Content-Length',str(len(f['raw'])));handler.end_headers();handler.wfile.write(f['raw']);return True
                match=re.fullmatch(r'/api/requests/(\d+)(?:/export\.(hwpx|docx))?',path)
                if match:
                    row=request_row(db,user,int(match[1]))
                    if match[2]:
                        payload=json.loads(row['payload'])
                        if row['version_id']:
                            version=db.execute('SELECT payload FROM draft_versions WHERE id=?',(row['version_id'],)).fetchone();payload=json.loads(version[0])
                        workflow.export_response(handler,payload,match[2],'인수인계요청_'+str(row['id']))
                    else:handler.respond(200,detail(db,user,row['id']))
                    return True
            if method=='POST':
                body=auth_control.read_json(handler,32768)
                if path=='/api/directory/sync':
                    if user['role']!='admin':fail(403,'전체 조직도 동기화는 관리자만 가능합니다.')
                    import org_sync
                    handler.respond(202,org_sync.start(factory,user,body.get('employees') is True));return True
                if path=='/api/directory/refresh':
                    if user['role']!='admin':fail(403,'조직도 새로고침은 관리자만 가능합니다.')
                    dept=text(body,'department_id',100)
                    try:
                        items=org_directory.fetch_employees(dept,None)
                        sync_directory(db,user,dept,items)
                    except org_directory.DirectoryError as error:
                        db.rollback();audit(db,user,'조직도 조회 실패',dept,str(error));db.commit();raise
                    handler.respond(200,{'updated':len(items),'source':'org_api','notice':'실제 응답 부서와 직원만 반영했습니다. 계정 발급은 관리자 승인이 필요합니다.'});return True
                db.execute('BEGIN IMMEDIATE')
                if path in ('/api/directory/departments','/api/directory/employees','/api/directory/link'):
                    admin(db,user,body,path);result={'saved':True}
                elif path=='/api/requests/send':
                    result={'id':send(db,user,body,source_changes)}
                elif path=='/api/requests/action':
                    act(db,user,body,source_changes);result={'saved':True}
                else:fail(404,'요청 경로가 없습니다.')
                db.commit();handler.respond(200,result);return True
            handler.respond(404,{'error':'요청 경로가 없습니다.'})
    except auth_control.AccessError as e:handler.respond(e.status,{'error':e.message})
    except (ValueError,TypeError,KeyError,OverflowError) as e:handler.respond(400,{'error':str(e) if isinstance(e,ValueError) else '요청 형식을 확인하세요.'})
    except sqlite3.Error:handler.respond(409,{'error':'저장 충돌이 발생했습니다. 최신 상태를 불러오세요. 기존 데이터는 유지됩니다.'})
    return True
