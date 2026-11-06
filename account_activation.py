"""별도 본인확인 후 발급된 일회용 코드로만 직원 계정을 활성화한다."""
import secrets,time,hmac
from contextlib import closing
import auth_control as auth
import password_security as passwords

def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS account_activations(user_id INTEGER PRIMARY KEY,token_hash TEXT NOT NULL,expires REAL NOT NULL,issued_by INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0)')

def handle(handler,factory,method):
 path=handler.path.split('?')[0]
 if path not in ('/api/auth/activation-issue','/api/auth/activate') or method!='POST':return False
 try:
  with closing(factory()) as db:
   ensure(db);body=auth.read_json(handler)
   if path.endswith('activation-issue'):
    admin=auth.identity(handler,db)
    if admin['role']!='admin' or admin['must_change_password']:raise auth.AccessError(403,'관리자 본인 인증과 비밀번호 변경이 필요합니다.')
    name=auth.validate_username(body.get('username'));note=body.get('verification_note','')
    if body.get('identity_verified') is not True or not isinstance(note,str) or not 5<=len(note.strip())<=500:raise ValueError('승인된 별도 경로에서 본인확인을 마치고 확인 기록을 입력하세요.')
    row=db.execute('SELECT u.* FROM users u JOIN employee_accounts a ON a.user_id=u.id WHERE u.username=?',(name,)).fetchone()
    if not row or row['role']=='admin':raise auth.AccessError(409,'조직도에 연결된 일반 직원 계정만 활성화할 수 있습니다.')
    if row['password_changed'] or not row['must_change_password']:raise auth.AccessError(409,'이미 사용 중인 계정입니다. 기존 비밀번호를 변경하지 않았습니다.')
    token=secrets.token_urlsafe(32)
    db.execute('INSERT OR REPLACE INTO account_activations VALUES(?,?,?,?,0)',(row['id'],auth.digest(token),time.time()+86400,admin['id']))
    db.execute('UPDATE users SET active=0 WHERE id=?',(row['id'],));db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
    auth.audit(db,handler,'직원 본인확인·활성화 코드 발급',row['id'],note.strip());db.commit()
    auth.json_cookie(handler,{'activation_code':token,'expires_hours':24,'notice':'코드는 한 번만 표시됩니다. 본인확인한 직원에게 별도 안전한 경로로 전달하세요.'});return True
   name=auth.validate_username(body.get('username'));keys=auth.limits(handler,name,'activation');auth.check_limits(db,keys)
   code=body.get('activation_code','');row=db.execute('SELECT u.*,a.token_hash,a.expires,a.used FROM users u JOIN account_activations a ON a.user_id=u.id WHERE u.username=?',(name,)).fetchone()
   if not isinstance(code,str) or len(code)>200 or not row or row['used'] or row['expires']<time.time() or not hmac.compare_digest(row['token_hash'],auth.digest(code)):
    auth.record_failure(db,keys);db.commit();raise auth.AccessError(401,'활성화 정보가 올바르지 않거나 만료되었습니다. 발급 담당자에게 확인하세요.')
   new=body.get('new_password');passwords.validate(new)
   if new!=body.get('confirmation'):raise ValueError('새 비밀번호 확인이 일치하지 않습니다.')
   staff=auth.profile(db,row).get('employee')
   if not staff or not staff['active'] or not staff['department_active'] or staff['employment_status']!='active' or staff['saeoll_id']!=name:raise auth.AccessError(403,'조직도 직원 연결 및 재직 상태 확인이 필요합니다.')
   db.execute('BEGIN IMMEDIATE')
   changed=db.execute('UPDATE account_activations SET used=1 WHERE user_id=? AND used=0 AND expires>?',(row['id'],time.time())).rowcount
   if changed!=1:raise auth.AccessError(409,'이미 사용한 활성화 코드입니다.')
   db.execute("UPDATE users SET password_hash=?,salt='',active=1,must_change_password=0,initial_shared=0,password_changed=CURRENT_TIMESTAMP WHERE id=?",(passwords.hash_password(new),row['id']))
   db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],));auth.clear_failures(db,keys);token=auth.new_session(db,row['id']);auth.audit(db,handler,'직원 계정 활성화·최초 비밀번호 설정',row['id']);db.commit();auth.json_cookie(handler,{'activated':True},token)
 except auth.AccessError as e:handler.respond(e.status,{'error':e.message})
 except (ValueError,TypeError) as e:handler.respond(400,{'error':str(e) if isinstance(e,ValueError) else '계정 활성화 입력을 확인하세요.'})
 return True
