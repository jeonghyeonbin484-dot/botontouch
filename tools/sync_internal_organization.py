"""승인된 내부망 서버에서만 실행하는 조직도 외부 동기화 프로그램."""
import os,sys,json,secrets,time,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import org_directory
from organization_ingest import signature

def main():
 if os.environ.get('BATON_ORG_EXPORT_APPROVED')!='true':raise SystemExit('직원정보 외부 저장·동기화 승인이 확인되지 않아 전송하지 않았습니다.')
 target=os.environ.get('BATON_SYNC_TARGET','').rstrip('/')
 from urllib.parse import urlsplit
 u=urlsplit(target)
 if u.scheme!='https' or not u.netloc or u.username or u.path or u.query or u.fragment:raise SystemExit('승인된 HTTPS 서버 원점을 설정하세요.')
 secret=os.environ.get('BATON_ORG_SYNC_SECRET','')
 if len(secret)<32:raise SystemExit('서버 간 전용 동기화 비밀값이 필요합니다.')
 def send(kind,items):
  raw=json.dumps({'kind':kind,'items':items},ensure_ascii=False).encode();stamp=str(int(time.time()));nonce=secrets.token_hex(16)
  req=urllib.request.Request(target+'/api/organization-sync',data=raw,method='POST',headers={'Content-Type':'application/json','X-Org-Time':stamp,'X-Org-Nonce':nonce,'X-Org-Signature':signature(secret,stamp,nonce,raw)})
  opener=urllib.request.build_opener(org_directory.NoRedirect())
  with opener.open(req,timeout=80) as r:return json.load(r)
 departments=org_directory.fetch_departments();print(json.dumps({'departments':send('departments',departments)},ensure_ascii=False),flush=True)
 total={'departments_ok':0,'departments_failed':0,'employees':0,'missing_login':0}
 for dept in departments:
  try:
   employees=org_directory.fetch_employees(dept['id']);total['employees']+=len(employees);total['missing_login']+=sum(not e.get('saeoll_id') for e in employees)
   for start in range(0,len(employees),50):send('employees',employees[start:start+50])
   total['departments_ok']+=1
  except (ValueError,urllib.error.URLError):total['departments_failed']+=1
 print(json.dumps(total,ensure_ascii=False))
if __name__=='__main__':main()
