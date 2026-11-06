"""Mandatory local authentication, staff provisioning and administrator approvals."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
import ipaddress
from contextlib import closing
from http.cookies import SimpleCookie
import password_security as passwords
import server_settings


class AccessError(Exception):
    def __init__(self,status,message):self.status,self.message=status,message


_backup_lock=threading.Lock()
def backup_before_migration(file):
    if not file.exists():return
    with _backup_lock, closing(sqlite3.connect(file)) as source:
        columns={r[1] for r in source.execute('PRAGMA table_info(users)')}
        if 'must_change_password' in columns:return
        folder=file.parent/'backups';folder.mkdir(exist_ok=True);target=folder/'before-staff-login.sqlite3'
        if not target.exists():
            with closing(sqlite3.connect(target)) as dest:source.backup(dest)


def ensure(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'member');
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS workspace_members(workspace_id INTEGER NOT NULL,user_id INTEGER NOT NULL,permission TEXT NOT NULL,PRIMARY KEY(workspace_id,user_id));
    CREATE TABLE IF NOT EXISTS login_failures(identity TEXT PRIMARY KEY,attempts INTEGER NOT NULL,blocked_until REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS auth_audit(id INTEGER PRIMARY KEY,user_id INTEGER,actor_id INTEGER,action TEXT NOT NULL,ip TEXT NOT NULL,details TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS password_reset_requests(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'pending',requested TEXT DEFAULT CURRENT_TIMESTAMP,approved_by INTEGER,approved TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_reset_pending ON password_reset_requests(user_id) WHERE state='pending';
    ''')
    columns={r['name'] for r in db.execute('PRAGMA table_info(users)')}
    for name,definition in [('active','INTEGER NOT NULL DEFAULT 1'),('must_change_password','INTEGER NOT NULL DEFAULT 0'),('is_test','INTEGER NOT NULL DEFAULT 0'),('password_changed','TEXT'),('initial_shared','INTEGER NOT NULL DEFAULT 0')]:
        if name not in columns:db.execute('ALTER TABLE users ADD COLUMN '+name+' '+definition)


def enabled(db):return bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())
def digest(value):return hashlib.sha256(value.encode()).hexdigest()

# Domain separation retires every pre-fix session without deleting users or history.
# Old cookie tokens can never authenticate against the new session digest.
def session_digest(token):return digest('batontouch-interactive-session-v2:'+token)
def audit(db,handler,action,user_id=None,details=''):
    actor=getattr(handler,'user',None)
    db.execute('INSERT INTO auth_audit(user_id,actor_id,action,ip,details) VALUES(?,?,?,?,?)',(user_id,actor['id'] if actor else None,action,handler.client_address[0],details))


def profile(db,row):
    data={key:row[key] for key in ('id','username','role','active','must_change_password','is_test')}
    staff=db.execute('SELECT e.employee_id,e.saeoll_id,e.name,e.position,e.department_id,e.active,e.employment_status,e.source,d.name AS department,d.active AS department_active FROM employee_accounts a JOIN org_employees e ON e.employee_id=a.employee_id JOIN org_departments d ON d.id=e.department_id WHERE a.user_id=?',(row['id'],)).fetchone()
    data['employee']=dict(staff) if staff else None
    data['identity_pending']=bool(staff and (not staff['saeoll_id'] or staff['saeoll_id']!=row['username']))
    return data


def identity(handler,db):
    handler.user=None
    try:
        cookies=SimpleCookie(handler.headers.get('Cookie',''));token=cookies['baton_session'].value if 'baton_session' in cookies else ''
    except Exception:token=''
    if token:
        row=db.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1',(session_digest(token),time.time())).fetchone()
        if row and (not row['is_test'] or server_settings.dev_test_accounts()) and (not row['initial_shared'] or __import__('staff_account_sync').enabled(db)):
            candidate=profile(db,row);staff=candidate['employee']
            if not staff or staff['active'] and staff['department_active'] and staff['employment_status']=='active' and (not staff['saeoll_id'] or staff['saeoll_id']==row['username']) and (staff['source']!='test' or server_settings.dev_test_accounts()):handler.user=candidate
    if handler.user is None:raise AccessError(401,'로그인이 필요하거나 세션이 만료되었습니다.')
    if handler.user['must_change_password'] and handler.path.split('?')[0] not in ('/api/auth/status','/api/auth/password','/api/auth/logout'):
        raise AccessError(403,'최초 로그인 또는 초기화된 계정입니다. 비밀번호를 먼저 변경하세요.')
    return handler.user


def permission(db,user,workspace_id):
    if not user:return None
    if user['role']=='admin':return 'editor'
    row=db.execute('SELECT permission FROM workspace_members WHERE user_id=? AND workspace_id=?',(user['id'],workspace_id)).fetchone()
    return row['permission'] if row else None


def workspace_access(db,user,workspace_id,write=False,path=''):
    access=permission(db,user,workspace_id)
    if not access:raise AccessError(403,'이 업무 묶음에 접근할 권한이 없습니다.')
    if write and access!='editor' and path not in ('/api/handover/check','/api/handover/followup/create'):raise AccessError(403,'이 작업에는 편집 권한이 필요합니다.')


def actor(handler):return getattr(handler,'user',None)['username'] if getattr(handler,'user',None) else '미인증'
def read_json(handler,limit=32768):
    try:
        size=int(handler.headers.get('Content-Length','0'))
        if not 0<size<=limit:raise ValueError()
        raw=handler.rfile.read(size)
        if len(raw)!=size:raise ValueError()
        body=json.loads(raw)
        if not isinstance(body,dict):raise ValueError()
        return body
    except (ValueError,TypeError,RecursionError):raise ValueError('입력 형식이나 요청 크기를 확인하세요.') from None


def password_hash(password,salt=''):return passwords.hash_password(password)
def validate_username(username):
    if not isinstance(username,str) or not re.fullmatch(r'[a-zA-Z0-9가-힣_.@-]{2,80}',username):raise ValueError('아이디는 2~80자의 조직도 SAEOLL_ID를 입력하세요.')
    return username.lower()

def json_cookie(handler,value,token=None):
    raw=json.dumps(value,ensure_ascii=False).encode();handler.send_response(200);handler.send_header('Content-Type','application/json; charset=utf-8');handler.send_header('Content-Length',str(len(raw)));handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff')
    if token is not None:handler.send_header('Set-Cookie','baton_session='+token+'; HttpOnly; SameSite=Strict; Path=/'+('' if token else '; Max-Age=0')+('; Secure' if server_settings.secure_cookie() else ''))
    handler.end_headers();handler.wfile.write(raw)


def new_session(db,user_id):
    token=secrets.token_urlsafe(32);db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));db.execute('INSERT INTO sessions VALUES(?,?,?)',(session_digest(token),user_id,time.time()+28800));return token


def limits(handler,username,prefix='login'):
    return [prefix+':account:'+digest(username),prefix+':ip:'+digest(handler.client_address[0]+':'+username)]

def check_limits(db,keys):
    if any((r:=db.execute('SELECT blocked_until FROM login_failures WHERE identity=?',(key,)).fetchone()) and r[0]>time.time() for key in keys):raise AccessError(429,'실패가 반복되어 계정이 일시 보호되었습니다. 15분 뒤 다시 시도하세요.')

def record_failure(db,keys):
    for key in keys:
        row=db.execute('SELECT * FROM login_failures WHERE identity=?',(key,)).fetchone();attempts=row['attempts']+1 if row and row['blocked_until']>time.time()-900 else 1
        db.execute('INSERT OR REPLACE INTO login_failures VALUES(?,?,?)',(key,attempts,time.time()+(900 if attempts>=5 else 0)))

def clear_failures(db,keys):
    for key in keys:db.execute('DELETE FROM login_failures WHERE identity=?',(key,))


def staff_for_account(db,employee_id):
    if not isinstance(employee_id,str) or not employee_id:raise ValueError('계정을 발급할 직원을 선택하세요.')
    row=db.execute('SELECT e.*,d.active AS department_active,d.hidden_from_picker FROM org_employees e JOIN org_departments d ON d.id=e.department_id WHERE e.employee_id=?',(employee_id,)).fetchone()
    if not row or not row['active'] or not row['department_active'] or row['employment_status']!='active':raise AccessError(409,'재직 중인 활성 직원을 선택하세요.')
    if not row['saeoll_id']:raise AccessError(409,'직원정보에 SAEOLL_ID가 없습니다. 공식 값을 확인한 뒤 등록하세요. 임의 아이디를 만들지 않습니다.')
    validate_username(row['saeoll_id']);return row


def provision(db,handler,body):
    staff=staff_for_account(db,body.get('employee_id'))
    if body.get('approved') is not True:raise ValueError('관리자가 계정 발급·활성화를 확인해야 합니다.')
    if db.execute('SELECT 1 FROM employee_accounts WHERE employee_id=?',(staff['employee_id'],)).fetchone() or db.execute('SELECT 1 FROM users WHERE username=?',(staff['saeoll_id'],)).fetchone():raise AccessError(409,'이 직원 또는 SAEOLL_ID에 계정이 이미 있습니다. 자동 병합하지 않습니다.')
    test=body.get('test_password') is True
    if test and not(server_settings.dev_test_accounts() and staff['source']=='test' and staff['employee_id'].startswith('TEST-') and staff['saeoll_id'].startswith('test.')):raise AccessError(403,'1234!는 개발 모드의 명시된 가상 직원(TEST-/test.)에게만 허용됩니다.')
    personal=__import__('staff_account_sync').enabled(db) and staff['source']=='org_api' and not staff['hidden_from_picker']
    temporary='1234!' if test or personal else secrets.token_urlsafe(24)
    active=body.get('activate') is True
    cursor=db.execute("INSERT INTO users(username,password_hash,salt,active,must_change_password,is_test,initial_shared) VALUES(?,?,'',?,1,?,?)",(staff['saeoll_id'],passwords.hash_password(temporary),int(active),int(staff['source']=='test'),int(personal)))
    db.execute('INSERT INTO employee_accounts(employee_id,user_id,linked_by) VALUES(?,?,?)',(staff['employee_id'],cursor.lastrowid,handler.user['id']))
    audit(db,handler,'직원 계정 발급 승인',cursor.lastrowid)
    return {'id':cursor.lastrowid,'username':staff['saeoll_id'],'temporary_password':temporary,'must_change_password':True,'active':active,'notice':'임시 비밀번호는 이번 응답에서만 표시됩니다. 안전한 별도 경로로 전달하세요.'}


_hash_slots=threading.BoundedSemaphore(4)
_dummy_hash=None

def verify_limited(password,row):
    global _dummy_hash
    if not _hash_slots.acquire(blocking=False):raise AccessError(429,'로그인 요청이 많습니다. 잠시 후 다시 시도하세요.')
    try:
        if row:return passwords.verify(password,row['password_hash'],row['salt'])
        if _dummy_hash is None:_dummy_hash=passwords.hash_password(secrets.token_urlsafe(24))
        passwords.verify(password,_dummy_hash);return False
    finally:_hash_slots.release()


def handle(handler,factory,method):
    if __import__('staff_self_service').handle(handler,factory,method):return True
    if __import__('account_activation').handle(handler,factory,method):return True
    path=handler.path.split('?')[0]
    if not path.startswith('/api/auth/'):return False
    try:
        with closing(factory()) as db:
            try:user=identity(handler,db)
            except AccessError:
                user=getattr(handler,'user',None)
            if path=='/api/auth/status' and method=='GET':
                json_cookie(handler,{'enabled':enabled(db),'setup_required':not enabled(db),'auth_required':True,'session_policy':'interactive-v2','user':user,'test_accounts_enabled':server_settings.dev_test_accounts(),'bootstrap_token_required':server_settings.central(),'personal_initial_password':__import__('staff_account_sync').enabled(db)});return True
            if path=='/api/auth/reset-request' and method=='POST':
                body=read_json(handler);name=validate_username(body.get('username'));key='reset:'+digest(handler.client_address[0]+':'+name);row=db.execute('SELECT * FROM login_failures WHERE identity=?',(key,)).fetchone()
                if row and row['blocked_until']>time.time():raise AccessError(429,'초기화 요청이 많습니다. 잠시 후 다시 요청하세요.')
                attempts=row['attempts']+1 if row and row['blocked_until']>time.time()-3600 else 1;db.execute('INSERT OR REPLACE INTO login_failures VALUES(?,?,?)',(key,attempts,time.time()+(3600 if attempts>=3 else 0)))
                account=db.execute('SELECT id FROM users WHERE username=?',(name,)).fetchone()
                if account:db.execute("INSERT OR IGNORE INTO password_reset_requests(user_id) VALUES(?)",(account['id'],))
                audit(db,handler,'비밀번호 초기화 요청',account['id'] if account else None);db.commit();json_cookie(handler,{'message':'요청을 접수했습니다. 관리자의 본인 확인·승인 후 임시 비밀번호를 별도로 전달받으세요.'});return True
            if path in ('/api/auth/setup','/api/auth/login') and method=='POST':
                body=read_json(handler);name=validate_username(body.get('username'));password=body.get('password')
                if not isinstance(password,str) or not 1<=len(password)<=200:raise ValueError('아이디와 비밀번호를 확인하세요.')
                if path.endswith('/login') and password=='1234!':
                    handler.respond(409,{'error':'최초 본인확인 후 비밀번호를 설정하세요.','code':'FIRST_PASSWORD_VERIFICATION_REQUIRED'});return True
                db.execute('BEGIN IMMEDIATE')
                if path.endswith('/setup'):
                    if enabled(db):raise AccessError(403,'초기 관리자가 이미 설정되어 있습니다.')
                    if server_settings.central():
                        import os
                        expected=os.environ.get('BATON_BOOTSTRAP_TOKEN','')
                        if len(expected)<32 or not isinstance(body.get('bootstrap_token'),str) or not hmac.compare_digest(expected,body['bootstrap_token']):raise AccessError(403,'공통 서버 초기 관리자 등록 토큰을 확인하세요.')
                    elif not ipaddress.ip_address(handler.client_address[0]).is_loopback:raise AccessError(403,'초기 관리자는 서버 PC에서 등록하세요.')
                    passwords.validate(password);cursor=db.execute("INSERT INTO users(username,password_hash,salt,role) VALUES(?,?,'','admin')",(name,passwords.hash_password(password)));uid=cursor.lastrowid;audit(db,handler,'초기 관리자 등록',uid)
                else:
                    row=db.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
                    if row is None:
                        matches=db.execute('SELECT u.* FROM users u JOIN employee_accounts a ON a.user_id=u.id WHERE lower(u.username)=lower(?) LIMIT 2',(name,)).fetchall()
                        if len(matches)==1:row=matches[0];name=row['username']
                    keys=limits(handler,name);check_limits(db,keys);valid=verify_limited(password,row)
                    if not valid or not row['active'] or row['is_test'] and not server_settings.dev_test_accounts() or row['initial_shared'] and not __import__('staff_account_sync').enabled(db):
                        record_failure(db,keys);audit(db,handler,'로그인 실패',row['id'] if row else None);db.commit();raise AccessError(401,'아이디 또는 비밀번호가 올바르지 않거나 비활성 계정입니다.')
                    __import__('employee_identity').ensure_mapping(db,dict(row))
                    data=profile(db,row);staff=data['employee']
                    if staff and (not staff['active'] or not staff['department_active'] or staff['employment_status']!='active' or staff['saeoll_id'] and staff['saeoll_id']!=name or staff['source']=='test' and not server_settings.dev_test_accounts()):
                        audit(db,handler,'직원 매핑·재직 확인 실패',row['id']);db.commit();raise AccessError(403,'조직도 계정 연결 또는 재직 상태를 관리자에게 확인하세요.')
                    if not row['must_change_password']:
                        try:passwords.validate(password)
                        except ValueError:db.execute('UPDATE users SET must_change_password=1 WHERE id=?',(row['id'],))
                    if passwords.needs_rehash(row['password_hash']):db.execute("UPDATE users SET password_hash=?,salt='' WHERE id=?",(passwords.hash_password(password),row['id']))
                    uid=row['id'];clear_failures(db,keys);audit(db,handler,'로그인 성공',uid)
                token=new_session(db,uid);db.commit();row=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone();json_cookie(handler,{'user':profile(db,row)},token);return True
            if path=='/api/auth/logout' and method=='POST':
                try:cookie=SimpleCookie(handler.headers.get('Cookie',''));token=cookie['baton_session'].value if 'baton_session' in cookie else ''
                except Exception:token=''
                db.execute('DELETE FROM sessions WHERE token_hash=?',(session_digest(token),));audit(db,handler,'로그아웃',user['id'] if user else None);db.commit();json_cookie(handler,{'logged_out':True},'');return True
            if not user:raise AccessError(401,'로그인이 필요합니다.')
            if path=='/api/auth/password' and method=='POST':
                body=read_json(handler);current=body.get('current_password');new=body.get('new_password');passwords.validate(new)
                if new!=body.get('confirmation') or current==new:raise ValueError('새 비밀번호 확인이 다르거나 현재 비밀번호와 같습니다.')
                db.execute('BEGIN IMMEDIATE');keys=limits(handler,user['username'],'password');check_limits(db,keys);row=db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
                if not isinstance(current,str) or len(current)>200 or not verify_limited(current,row):
                    record_failure(db,keys);audit(db,handler,'비밀번호 변경 인증 실패',user['id']);db.commit();raise AccessError(401,'현재 또는 임시 비밀번호를 확인하세요.')
                db.execute("UPDATE users SET password_hash=?,salt='',must_change_password=0,initial_shared=0,password_changed=CURRENT_TIMESTAMP WHERE id=?",(passwords.hash_password(new),user['id']));db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],));clear_failures(db,keys);token=new_session(db,user['id']);audit(db,handler,'비밀번호 변경 완료',user['id']);db.commit();json_cookie(handler,{'changed':True},token);return True
            if user['must_change_password']:raise AccessError(403,'비밀번호를 먼저 변경하세요.')
            if user['role']!='admin':raise AccessError(403,'관리자 권한이 필요합니다.')
            if path=='/api/auth/users' and method=='GET':
                handler.respond(200,[profile(db,r) for r in db.execute('SELECT * FROM users ORDER BY id')]);return True
            if path in ('/api/auth/staff','/api/auth/users') and method=='POST':
                body=read_json(handler);db.execute('BEGIN IMMEDIATE');result=provision(db,handler,body);db.commit();json_cookie(handler,result);return True
            if path=='/api/auth/account' and method=='POST':
                body=read_json(handler);uid=body.get('id');action=body.get('action')
                if type(uid) is not int or body.get('approved') is not True:raise ValueError('대상 계정과 관리자 승인을 확인하세요.')
                db.execute('BEGIN IMMEDIATE');target=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                if not target:raise ValueError('계정이 없습니다.')
                if action in ('activate','deactivate'):
                    if action=='activate':
                        link=db.execute('SELECT employee_id FROM employee_accounts WHERE user_id=?',(uid,)).fetchone()
                        if link:
                            staff=staff_for_account(db,link[0])
                            if staff['saeoll_id']!=target['username']:raise AccessError(409,'SAEOLL_ID와 로그인 아이디가 다릅니다.')
                        if target['is_test'] and not server_settings.dev_test_accounts():raise AccessError(403,'운영 환경에서는 테스트 계정을 활성화할 수 없습니다.')
                    if action=='deactivate' and target['role']=='admin' and db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:raise AccessError(409,'마지막 활성 관리자는 비활성화할 수 없습니다.')
                    db.execute('UPDATE users SET active=? WHERE id=?',(int(action=='activate'),uid));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(db,handler,'계정 '+action,uid);db.commit();json_cookie(handler,{'saved':True});return True
                if action=='role':
                    desired=body.get('role');current=body.get('current_password')
                    if desired not in ('admin','member'):raise ValueError('역할을 확인하세요.')
                    keys=limits(handler,user['username'],'admin-reauth');check_limits(db,keys);administrator=db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
                    if not isinstance(current,str) or len(current)>200 or not verify_limited(current,administrator):
                        record_failure(db,keys);audit(db,handler,'관리자 역할 변경 인증 실패',uid);db.commit();raise AccessError(401,'관리자 본인의 현재 비밀번호를 확인하세요.')
                    if desired=='admin':
                        info=profile(db,target)
                        if not target['active'] or target['must_change_password'] or not info['employee'] or info['identity_pending']:raise AccessError(409,'직원정보 연결·비밀번호 변경을 마친 활성 직원만 관리자로 지정할 수 있습니다.')
                    if desired=='member' and target['role']=='admin' and target['active'] and db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:raise AccessError(409,'마지막 활성 관리자의 권한은 해제할 수 없습니다.')
                    db.execute('UPDATE users SET role=? WHERE id=?',(desired,uid));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));clear_failures(db,keys);audit(db,handler,'관리자 역할 변경 승인',uid,desired);db.commit();json_cookie(handler,{'saved':True});return True
                if action=='reconcile_saeoll':
                    sid=validate_username(body.get('saeoll_id'));note=body.get('note','')
                    if not isinstance(note,str) or not 1<=len(note.strip())<=500:raise ValueError('공식 SAEOLL_ID 확인 메모를 입력하세요.')
                    linked=db.execute('SELECT e.* FROM employee_accounts a JOIN org_employees e ON e.employee_id=a.employee_id WHERE a.user_id=?',(uid,)).fetchone()
                    if not linked:raise AccessError(409,'기존 USER_ID 연결이 먼저 필요합니다.')
                    if linked['saeoll_id'] and linked['saeoll_id']!=sid:raise AccessError(409,'확인된 조직도 SAEOLL_ID와 다릅니다. 임의 변경하지 않습니다.')
                    if db.execute('SELECT 1 FROM users WHERE username=? AND id!=?',(sid,uid)).fetchone():raise AccessError(409,'이미 사용 중인 SAEOLL_ID입니다. 자동 병합하지 않습니다.')
                    db.execute('UPDATE org_employees SET saeoll_id=? WHERE employee_id=?',(sid,linked['employee_id']))
                    db.execute('UPDATE users SET username=?,must_change_password=1 WHERE id=?',(sid,uid));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
                    audit(db,handler,'기존 계정 SAEOLL_ID 반영 승인',uid,target['username']+' -> '+sid+' / '+note.strip());db.commit();json_cookie(handler,{'saved':True,'username':sid,'notice':'계정 번호와 USER_ID 연결은 유지했습니다. 새 아이디·기존 비밀번호로 로그인한 뒤 비밀번호를 변경하세요.'});return True
                if action=='reset':
                    if uid==user['id']:raise AccessError(409,'본인 계정은 비밀번호 변경을 사용하세요. 초기화는 다른 관리자의 확인이 필요합니다.')
                    note=body.get('note','')
                    if not isinstance(note,str) or not 1<=len(note.strip())<=500:raise ValueError('관리자 본인 확인·초기화 승인 메모를 입력하세요.')
                    temporary=secrets.token_urlsafe(24);db.execute("UPDATE users SET password_hash=?,salt='',must_change_password=1,initial_shared=0 WHERE id=?",(passwords.hash_password(temporary),uid));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));db.execute("UPDATE password_reset_requests SET state='approved',approved_by=?,approved=CURRENT_TIMESTAMP WHERE user_id=? AND state='pending'",(user['id'],uid));audit(db,handler,'비밀번호 초기화 승인',uid,note.strip());db.commit();json_cookie(handler,{'temporary_password':temporary,'notice':'이번 응답에서만 표시됩니다. 기존 세션은 폐기되었고 다음 로그인에서 변경해야 합니다.'});return True
                raise ValueError('처리 작업을 확인하세요.')
            if path=='/api/auth/audit' and method=='GET':
                handler.respond(200,[dict(r) for r in db.execute('SELECT a.id,a.action,a.details,a.ip,a.created,u.username,actor.username AS actor FROM auth_audit a LEFT JOIN users u ON u.id=a.user_id LEFT JOIN users actor ON actor.id=a.actor_id ORDER BY a.id DESC LIMIT 200')]);return True
            if path=='/api/auth/reset-requests' and method=='GET':
                handler.respond(200,[dict(r) for r in db.execute("SELECT r.id,r.user_id,u.username,r.requested FROM password_reset_requests r JOIN users u ON u.id=r.user_id WHERE r.state='pending' ORDER BY r.id")]);return True
            if path=='/api/auth/access' and method=='GET':
                workspace=int(handler.headers.get('X-Workspace-Id','1'));handler.respond(200,[dict(r) for r in db.execute('SELECT m.user_id,m.permission,u.username FROM workspace_members m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=?',(workspace,))]);return True
            if path=='/api/auth/access' and method=='POST':
                body=read_json(handler);workspace,uid,access=body.get('workspace_id'),body.get('user_id'),body.get('permission')
                if type(workspace) is not int or type(uid) is not int or access not in ('editor','viewer','none'):raise ValueError('권한 설정을 확인하세요.')
                if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone() or not db.execute('SELECT 1 FROM workspaces WHERE id=?',(workspace,)).fetchone():raise ValueError('사용자 또는 업무 묶음이 없습니다.')
                if access=='none':db.execute('DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?',(workspace,uid))
                else:db.execute('INSERT OR REPLACE INTO workspace_members VALUES(?,?,?)',(workspace,uid,access))
                audit(db,handler,'업무 묶음 권한 변경',uid,access);db.commit();handler.respond(200,{'saved':True});return True
            handler.respond(404,{'error':'인증 경로가 없습니다.'})
    except AccessError as e:handler.respond(e.status,{'error':e.message})
    except sqlite3.IntegrityError:handler.respond(409,{'error':'아이디·직원 연결이 중복됩니다. 기존 계정을 확인하세요.'})
    except sqlite3.Error:handler.respond(503,{'error':'계정 저장소가 일시적으로 사용 중입니다. 잠시 후 다시 시도하세요.'})
    except (ValueError,TypeError,RecursionError) as e:handler.respond(400,{'error':str(e) if isinstance(e,ValueError) else '입력 형식을 확인하세요.'})
    return True
