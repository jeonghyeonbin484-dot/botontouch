"""공식 조직도 이메일 소유 확인에 의한 최초 비밀번호 설정. 기존 계정 재설정에는 사용하지 않는다."""
import os,re,secrets,time,hmac,hashlib,smtplib,ssl,csv,io
from email.message import EmailMessage
from email.utils import parseaddr
from contextlib import closing
import auth_control as auth
import password_security as passwords

REQUEST_MESSAGE='입력 정보가 최초 설정 대상과 일치하면 등록된 본인확인 메일로 인증번호가 전송됩니다.'
def ensure(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS staff_identity_channels(employee_id TEXT PRIMARY KEY,saeoll_id TEXT NOT NULL,email TEXT NOT NULL,source TEXT NOT NULL,verified_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS staff_first_password_codes(user_id INTEGER PRIMARY KEY,nonce TEXT NOT NULL,code_hash TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS staff_first_password_sends(user_id INTEGER PRIMARY KEY,count INTEGER NOT NULL,period REAL NOT NULL);''')

def configuration():
 domains={v.strip().lower() for v in os.environ.get('BATON_STAFF_EMAIL_DOMAINS','').split(',') if v.strip()}
 values={k:os.environ.get('BATON_SMTP_'+k,'') for k in ('HOST','USER','PASSWORD','FROM')}
 ready=all(values.values()) and len(os.environ.get('BATON_OTP_SIGNING_SECRET',''))>=32 and bool(domains)
 return values,domains,bool(ready)

def valid_email(value,domains):
 if not isinstance(value,str) or len(value)>254 or any(c in value for c in '\r\n'):return False
 name,address=parseaddr(value)
 return not name and address==value and bool(re.fullmatch(r'[^\s@]+@[^\s@]+',value)) and value.rsplit('@',1)[-1].lower() in domains

def _send_code(email,code):
 cfg,_,ready=configuration()
 if not ready:raise ValueError('본인확인 메일 발송 설정이 완료되지 않았습니다.')
 sender=cfg['FROM']
 if any(c in sender for c in '\r\n') or not parseaddr(sender)[1]:raise ValueError('본인확인 메일 발신자 설정을 확인하세요.')
 msg=EmailMessage();msg['From']=sender;msg['To']=email;msg['Subject']='바통터치 최초 비밀번호 설정 인증번호'
 msg.set_content('본인확인 인증번호: '+code+'\n10분 안에 입력하세요. 본인이 요청하지 않았다면 입력하지 마세요.')
 port=int(os.environ.get('BATON_SMTP_PORT','465'));context=ssl.create_default_context()
 if port==465:
  with smtplib.SMTP_SSL(cfg['HOST'],port,timeout=10,context=context) as mail:mail.login(cfg['USER'],cfg['PASSWORD']);mail.send_message(msg)
 elif port==587:
  with smtplib.SMTP(cfg['HOST'],port,timeout=10) as mail:mail.ehlo();mail.starttls(context=context);mail.ehlo();mail.login(cfg['USER'],cfg['PASSWORD']);mail.send_message(msg)
 else:raise ValueError('본인확인 메일은 검증된 TLS 연결(465/587)만 사용합니다.')

def eligible(db,name):
 row=db.execute('SELECT u.* FROM users u JOIN employee_accounts a ON a.user_id=u.id JOIN org_employees e ON e.employee_id=a.employee_id JOIN org_departments d ON d.id=e.department_id WHERE u.username=? AND e.saeoll_id=u.username AND e.source=\'org_api\' AND e.active=1 AND d.active=1 AND e.employment_status=\'active\' AND d.hidden_from_picker=0',(name,)).fetchone()
 if not row or not row['must_change_password'] or row['password_changed']:return None
 return row

def code_hash(user_id,nonce,code):
 secret=os.environ.get('BATON_OTP_SIGNING_SECRET','')
 if len(secret)<32:raise ValueError('본인확인 서명 설정이 완료되지 않았습니다.')
 return hmac.new(secret.encode(),f'{user_id}:{nonce}:{code}'.encode(),hashlib.sha256).hexdigest()

def handle(handler,factory,method):
 path=handler.path.split('?')[0];prefix='/api/auth/first-password/'
 if not path.startswith(prefix):return False
 try:
  _,domains,ready=configuration()
  if path==prefix+'options' and method=='GET':
   handler.respond(200,{'enabled':ready,'method':'official_email','notice':'' if ready else '공식 본인확인 메일·발송 서버 연결이 준비되지 않았습니다. 관리자 코드는 계속 사용할 수 있습니다.'});return True
  if method!='POST':raise auth.AccessError(405,'지원하지 않는 요청 방식입니다.')
  with closing(factory()) as db:
   ensure(db);body=auth.read_json(handler,1024*1024)
   if path==prefix+'channels':
    admin=auth.identity(handler,db)
    if admin['role']!='admin':raise auth.AccessError(403,'관리자 권한이 필요합니다.')
    if body.get('official_source_confirmed') is not True:raise ValueError('공식 조직도에서 확인한 이메일인지 확인하세요.')
    rows=body.get('items')
    if not domains:raise auth.AccessError(503,'허용할 공식 개인 이메일 도메인을 서버에 먼저 설정하세요.')
    if isinstance(body.get('csv'),str):
     rows=[{'employee_id':r.get('employee_id'),'saeoll_id':r.get('saeoll_id'),'email':r.get('email')} for r in csv.DictReader(io.StringIO(body['csv'].lstrip('\ufeff')))]
    if not isinstance(rows,list) or not 1<=len(rows)<=5000:raise ValueError('공식 직원 이메일 목록 형식을 확인하세요.')
    clean=[];seen=set();emails=set()
    for item in rows:
     if not isinstance(item,dict):raise ValueError('직원 이메일 항목 형식을 확인하세요.')
     sid=auth.validate_username(item.get('saeoll_id'));eid=item.get('employee_id');email=item.get('email')
     if not isinstance(eid,str) or sid in seen or not valid_email(email,domains):raise ValueError('중복 ID 또는 허용되지 않은 공식 이메일입니다.')
     seen.add(sid)
     if email.casefold() in emails or db.execute('SELECT 1 FROM staff_identity_channels WHERE lower(email)=? AND employee_id!=?',(email.casefold(),eid)).fetchone():raise ValueError('여러 직원이 공유하는 이메일은 본인확인 수단으로 등록할 수 없습니다.')
     emails.add(email.casefold());staff=db.execute("SELECT 1 FROM org_employees WHERE employee_id=? AND saeoll_id=? AND source='org_api'",(eid,sid)).fetchone()
     if not staff:raise ValueError('공식 직원 식별값과 새올 ID가 일치하지 않습니다.')
     clean.append((eid,sid,email))
    db.executemany("INSERT INTO staff_identity_channels(employee_id,saeoll_id,email,source) VALUES(?,?,?,'org_api') ON CONFLICT(employee_id) DO UPDATE SET saeoll_id=excluded.saeoll_id,email=excluded.email,source='org_api',verified_at=CURRENT_TIMESTAMP",clean)
    db.executemany('UPDATE staff_first_password_codes SET used=1 WHERE user_id IN (SELECT user_id FROM employee_accounts WHERE employee_id=?)',[(item[0],) for item in clean])
    auth.audit(db,handler,'공식 직원 본인확인 이메일 일괄 등록',details='건수: '+str(len(clean)));db.commit();handler.respond(200,{'registered':len(clean)});return True
   if not ready:raise auth.AccessError(503,'공식 본인확인 메일 연결 설정이 완료되지 않았습니다. 현재 계정의 보안 설정은 유지됩니다.')
   name=auth.validate_username(body.get('username'));row=eligible(db,name);keys=auth.limits(handler,name,'first-password');auth.check_limits(db,keys)
   if path==prefix+'request':
    # 미등록/기존 계정의 상태나 이메일은 공개하지 않는다. 신규 계정을 임의 생성하지 않는다.
    if not row:handler.respond(202,{'message':REQUEST_MESSAGE});return True
    channel=db.execute("SELECT c.email FROM staff_identity_channels c JOIN employee_accounts a ON a.employee_id=c.employee_id WHERE a.user_id=? AND c.saeoll_id=? AND c.source='org_api'",(row['id'],name)).fetchone()
    if not channel or not valid_email(channel['email'],domains):handler.respond(202,{'message':REQUEST_MESSAGE});return True
    sends=db.execute('SELECT * FROM staff_first_password_sends WHERE user_id=?',(row['id'],)).fetchone();now=time.time()
    count=sends['count'] if sends and sends['period']>now-3600 else 0
    if count>=3:raise auth.AccessError(429,'인증번호 요청이 많습니다. 잠시 후 다시 시도하세요.')
    nonce=secrets.token_hex(16);code=str(secrets.randbelow(1000000)).zfill(6)
    db.execute('INSERT OR REPLACE INTO staff_first_password_codes VALUES(?,?,?,?,0,0)',(row['id'],nonce,code_hash(row['id'],nonce,code),now+600))
    try:_send_code(channel['email'],code)
    except (OSError,smtplib.SMTPException,ValueError):raise auth.AccessError(503,'본인확인 메일을 발송하지 못했습니다. 관리자에게 발송 연결 상태를 확인해 주세요.') from None
    db.execute('INSERT OR REPLACE INTO staff_first_password_sends VALUES(?,?,?)',(row['id'],count+1,sends['period'] if sends and count else now));auth.audit(db,handler,'최초 비밀번호 본인확인 번호 발송',row['id']);db.commit();handler.respond(202,{'message':REQUEST_MESSAGE});return True
   if path==prefix+'confirm':
    code=body.get('code','');challenge=db.execute('SELECT * FROM staff_first_password_codes WHERE user_id=?',(row['id'],)).fetchone() if row else None
    valid=row and isinstance(code,str) and re.fullmatch(r'\d{6}',code) and challenge and not challenge['used'] and challenge['expires']>time.time() and challenge['attempts']<5 and hmac.compare_digest(challenge['code_hash'],code_hash(row['id'],challenge['nonce'],code))
    if not valid:
     if challenge:db.execute('UPDATE staff_first_password_codes SET attempts=attempts+1 WHERE user_id=?',(row['id'],))
     auth.record_failure(db,keys);db.commit();raise auth.AccessError(401,'인증번호가 올바르지 않거나 만료되었습니다.')
    new=body.get('new_password');passwords.validate(new)
    if new!=body.get('confirmation'):raise ValueError('새 비밀번호 확인이 일치하지 않습니다.')
    changed=db.execute('UPDATE staff_first_password_codes SET used=1 WHERE user_id=? AND used=0 AND expires>?',(row['id'],time.time())).rowcount
    if changed!=1:raise auth.AccessError(409,'이미 사용했거나 만료된 인증번호입니다.')
    db.execute("UPDATE users SET password_hash=?,salt='',active=1,must_change_password=0,initial_shared=0,password_changed=CURRENT_TIMESTAMP WHERE id=?",(passwords.hash_password(new),row['id']))
    db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],));db.execute('UPDATE account_activations SET used=1 WHERE user_id=?',(row['id'],)) if db.execute("SELECT 1 FROM sqlite_master WHERE name='account_activations'").fetchone() else None
    auth.clear_failures(db,keys);auth.audit(db,handler,'공식 이메일 본인확인·최초 비밀번호 설정',row['id']);db.commit();auth.json_cookie(handler,{'activated':True},'');return True
   raise auth.AccessError(404,'요청한 본인확인 기능이 없습니다.')
 except auth.AccessError as e:handler.respond(e.status,{'error':e.message})
 except ValueError as e:handler.respond(400,{'error':str(e)})
 except (TypeError,KeyError):handler.respond(400,{'error':'아이디·인증번호·비밀번호 입력값을 확인하세요.'})
 return True
