"""승인된 내부 연계 서버의 서명된 조직도 동기화 요청만 처리한다."""
import hashlib,hmac,json,os,re,secrets,time,sqlite3
from contextlib import closing
import auth_control as auth

def signature(secret,stamp,nonce,raw):return hmac.new(secret.encode(),(stamp+'\n'+nonce+'\n').encode()+raw,hashlib.sha256).hexdigest()
def handle(handler,factory):
 if handler.path.split('?')[0]!='/api/organization-sync':return False
 try:
  secret=os.environ.get('BATON_ORG_SYNC_SECRET','')
  if os.environ.get('BATON_ORG_SYNC_ALLOWED')!='true' or len(secret)<32:raise auth.AccessError(403,'조직도 동기화 승인과 서버 연계 설정이 필요합니다.')
  if handler.headers.get('Origin'):raise auth.AccessError(403,'조직도 동기화는 서버 간 요청만 허용합니다.')
  size=int(handler.headers.get('Content-Length','0'))
  if not 0<size<=2*1024*1024:raise ValueError('조직정보 요청 크기를 확인하세요.')
  stamp=handler.headers.get('X-Org-Time','');nonce=handler.headers.get('X-Org-Nonce','');sign=handler.headers.get('X-Org-Signature','')
  if not re.fullmatch(r'[0-9]{10,12}',stamp) or abs(time.time()-int(stamp))>300 or not re.fullmatch('[a-f0-9]{32}',nonce):raise auth.AccessError(401,'조직도 요청 유효시간을 확인하세요.')
  raw=handler.rfile.read(size)
  if not hmac.compare_digest(sign,signature(secret,stamp,nonce,raw)):raise auth.AccessError(401,'조직도 요청 서명이 올바르지 않습니다.')
  body=json.loads(raw);kind=body.get('kind');rows=body.get('items')
  if kind not in ('departments','employees') or not isinstance(rows,list) or len(rows)>(10000 if kind=='departments' else 100):raise ValueError('조직정보 묶음 형식을 확인하세요.')
  clean=[];seen=set();logins=set()
  for item in rows:
   if not isinstance(item,dict):raise ValueError('조직정보 항목 형식을 확인하세요.')
   keys=('id','name','parent_id','sort_order','mode','team_flag') if kind=='departments' else ('employee_id','name','department_id','position','saeoll_id','employment_status')
   row={k:item.get(k,'') for k in keys}
   for key,value in row.items():
    if value is None and key=='saeoll_id':continue
    if not isinstance(value,str) or len(value)>200:raise ValueError('조직정보 필드 형식을 확인하세요.')
   identifier=row['id' if kind=='departments' else 'employee_id']
   if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',identifier) or identifier in seen or not row['name'].strip():raise ValueError('직원·부서 식별값이 중복되거나 형식이 올바르지 않습니다.')
   seen.add(identifier)
   if kind=='employees':
    row['saeoll_id']=auth.validate_username(row['saeoll_id']) if row['saeoll_id'] else None
    if row['saeoll_id']:
     if row['saeoll_id'] in logins:raise ValueError('SAEOLL_ID가 중복됩니다. 자동 병합하지 않습니다.')
     logins.add(row['saeoll_id'])
    if row['employment_status'] not in ('active','inactive','retired','transferred'):raise ValueError('공식 재직 상태를 확인하세요.')
   clean.append(row)
  with closing(factory()) as db:
   db.execute('CREATE TABLE IF NOT EXISTS organization_sync_receipts(nonce TEXT PRIMARY KEY,created REAL NOT NULL)');db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM organization_sync_receipts WHERE nonce=?',(nonce,)).fetchone():raise auth.AccessError(409,'이미 처리한 조직도 요청입니다.')
   counts={'received':len(clean),'created_accounts':0,'missing_login':0}
   for row in clean:
    if kind=='departments':
     db.execute("INSERT INTO org_departments(id,name,parent_id,sort_order,mode,team_flag,source,synced_at) VALUES(?,?,?,?,?,?,'org_api',CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET name=excluded.name,parent_id=excluded.parent_id,sort_order=excluded.sort_order,mode=excluded.mode,team_flag=excluded.team_flag,source='org_api',synced_at=CURRENT_TIMESTAMP",tuple(row[k] for k in ('id','name','parent_id','sort_order','mode','team_flag')))
    else:
     dept=db.execute('SELECT * FROM org_departments WHERE id=?',(row['department_id'],)).fetchone()
     if not dept:raise ValueError('직원의 소속 부서가 없습니다. 부서를 먼저 동기화하세요.')
     prior=db.execute('SELECT * FROM org_employees WHERE employee_id=?',(row['employee_id'],)).fetchone()
     linked=db.execute('SELECT u.* FROM employee_accounts a JOIN users u ON u.id=a.user_id WHERE a.employee_id=?',(row['employee_id'],)).fetchone()
     if linked and linked['username']!=row['saeoll_id']:raise ValueError('기존 직원 계정과 SAEOLL_ID 연결이 충돌합니다. 기존 계정을 변경하지 않았습니다.')
     if prior and (prior['department_id']!=row['department_id'] or prior['position']!=row['position']):db.execute('INSERT INTO org_changes(employee_id,old_department,new_department,old_position,new_position) VALUES(?,?,?,?,?)',(row['employee_id'],prior['department_id'],row['department_id'],prior['position'],row['position']))
     active=int(row['employment_status']=='active')
     db.execute("INSERT INTO org_employees(employee_id,name,department_id,position,source,saeoll_id,active,employment_status) VALUES(?,?,?,?,'org_api',?,?,?) ON CONFLICT(employee_id) DO UPDATE SET name=excluded.name,department_id=excluded.department_id,position=excluded.position,source='org_api',saeoll_id=excluded.saeoll_id,employment_status=excluded.employment_status,active=min(org_employees.active,excluded.active),updated=CURRENT_TIMESTAMP",(row['employee_id'],row['name'],row['department_id'],row['position'],row['saeoll_id'],active,row['employment_status']))
     if not active and linked:
      db.execute('UPDATE users SET active=0 WHERE id=?',(linked['id'],));db.execute('DELETE FROM sessions WHERE user_id=?',(linked['id'],))
     if not row['saeoll_id']:counts['missing_login']+=1
     elif not linked and active:
      if db.execute('SELECT 1 FROM users WHERE username=?',(row['saeoll_id'],)).fetchone():raise ValueError('로그인 ID 충돌입니다. 다른 계정에 자동 연결하지 않습니다.')
      encoded=__import__('password_security').hash_password(secrets.token_urlsafe(32))
      uid=db.execute("INSERT INTO users(username,password_hash,salt,active,must_change_password,initial_shared) VALUES(?,?,'',0,1,0)",(row['saeoll_id'],encoded)).lastrowid
      db.execute('INSERT INTO employee_accounts(employee_id,user_id,linked_by) VALUES(?,?,0)',(row['employee_id'],uid));counts['created_accounts']+=1
   if kind=='departments':
    db.execute("WITH RECURSIVE abolished(id) AS (SELECT id FROM org_departments WHERE id='64100000001' UNION SELECT d.id FROM org_departments d JOIN abolished a ON d.parent_id=a.id) UPDATE org_departments SET hidden_from_picker=1 WHERE id IN (SELECT id FROM abolished)")
   db.execute('INSERT INTO organization_sync_receipts VALUES(?,?)',(nonce,time.time()));db.execute('DELETE FROM organization_sync_receipts WHERE created<?',(time.time()-86400,))
   db.execute("INSERT INTO auth_audit(action,ip,details) VALUES('서명된 조직도 동기화','server',?)",(json.dumps({'kind':kind,**counts}),));db.commit();handler.respond(200,counts)
 except auth.AccessError as e:handler.respond(e.status,{'error':e.message})
 except (ValueError,TypeError,KeyError) as e:handler.respond(400,{'error':str(e) if isinstance(e,ValueError) else '조직정보 필드를 확인하세요.'})
 except sqlite3.Error:handler.respond(409,{'error':'조직정보 저장 충돌입니다. 기존 데이터는 유지됩니다.'})
 return True
