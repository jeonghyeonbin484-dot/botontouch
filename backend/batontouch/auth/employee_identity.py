"""Verified SAEOLL_ID -> staff identity mapping; never name-based or account provisioning."""
import sqlite3

def ensure_mapping(db,user,required=False,verify_live=False):
 from batontouch.auth.sessions import AccessError
 from batontouch.server import settings as server_settings; from batontouch.organization import directory_client as org_directory
 def fail(message):raise AccessError(409,message)
 username=user['username'].strip().lower()
 link=db.execute('SELECT employee_id FROM employee_accounts WHERE user_id=?',(user['id'],)).fetchone()
 matches=db.execute('SELECT e.*,d.active AS department_active,d.hidden_from_picker FROM org_employees e JOIN org_departments d ON d.id=e.department_id WHERE lower(e.saeoll_id)=? LIMIT 2',(username,)).fetchall()
 if len(matches)>1:fail('동일 SAEOLL_ID에 직원 식별자가 여러 개입니다. 조직도 중복 식별정보 확인이 필요합니다. 이름으로 자동 연결하지 않았습니다.')
 if not matches:
  if link:raise AccessError(403,'기존 직원의 공식 SAEOLL_ID가 확인되지 않아 요청을 차단했습니다. 식별값을 임의로 생성하지 않습니다.')
  if required:fail('로그인 SAEOLL_ID와 일치하는 직원이 동기화된 조직도에 없습니다. 공식 조직도 동기화 후 다시 시도하세요. 수동 계정 연결은 필요하지 않습니다.')
  return None
 staff=dict(matches[0])
 if link and link[0]!=staff['employee_id']:fail('기존 직원 식별자와 SAEOLL_ID가 충돌합니다. 다른 직원의 기록을 연결하지 않았습니다.')
 if not link:
  trusted=staff['source']=='org_api' or staff['source']=='demo' and getattr(server_settings,'public_demo',lambda:False)() or staff['source']=='test' and server_settings.dev_test_accounts()
  if not trusted:
   if required:fail('공식 조직도에서 확인된 SAEOLL_ID 매핑이 필요합니다. 공식 조직도 동기화 후 자동 연결됩니다.')
   return None
 if not staff['active'] or not staff['department_active'] or staff['employment_status']!='active':fail('직원 또는 소속 부서가 비활성/퇴직/전출 상태여서 요청할 수 없습니다.')
 if verify_live and staff['source']=='org_api':
  cfg=org_directory.settings()
  if cfg.get('enabled') is True and cfg.get('approved') is True:
   official=[p for p in org_directory.fetch_employees(staff['department_id'],None) if p.get('employee_id')==staff['employee_id'] and p.get('saeoll_id') and p['saeoll_id'].lower()==username]
   if len(official)!=1:fail('공식 조직도에서 현재 SAEOLL_ID와 직원 식별자 일치를 확인하지 못했습니다. 자료는 유지됩니다.')
   if official[0].get('employment_status','active')!='active':fail('공식 조직도 재직 상태를 확인해야 합니다.')
 if not link:
  owner=db.execute('SELECT user_id FROM employee_accounts WHERE employee_id=?',(staff['employee_id'],)).fetchone()
  if owner and owner[0]!=user['id']:fail('이 직원 식별자가 다른 로그인 계정에 연결되어 있습니다. 자동 병합하지 않았습니다.')
  try:db.execute('INSERT INTO employee_accounts(employee_id,user_id,linked_by) VALUES(?,?,?)',(staff['employee_id'],user['id'],user['id']))
  except sqlite3.IntegrityError:fail('직원 연결이 동시에 변경되었습니다. 다시 로그인해 확인하세요.')
  db.execute("INSERT INTO directory_audit(actor_account,action,target,details) VALUES(?,'SAEOLL_ID 자동 연결',?,'서버 인증 계정과 고유 식별자 일치 검증')",(user['id'],staff['employee_id']))
 return staff
