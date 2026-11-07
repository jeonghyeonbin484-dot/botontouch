"""공용 저장소 장애를 접속 문자열·비밀번호·요청 원문 없이 기록한다."""
import json,sys,uuid,os,re

def payload(error,path=''):
 text=str(error).lower();known=getattr(error,'code','');sqlstate=str(getattr(error,'sqlstate','') or '')
 if sqlstate.startswith('28'):
  code='STORAGE_AUTH_FAILED';message='공용 DB 인증 설정을 확인해야 합니다. 관리자가 서버 연결 정보를 점검하세요. 직원 비밀번호 문제와는 다릅니다.'
 elif sqlstate=='42P01' or known=='STORAGE_NOT_INITIALIZED':
  code='STORAGE_NOT_INITIALIZED';message='설정된 공용 DB에서 기존 데이터를 확인하지 못했습니다. 연결 대상을 확인하세요. 새 DB로 초기화하지 않았습니다.'
 elif known=='STORAGE_NOT_CONFIGURED':
  code=known;message='공용 DB 서버 설정이 누락되었거나 올바르지 않습니다. 관리자가 Vercel의 DATABASE_URL과 Production 배포를 확인해야 합니다. 기존 데이터는 유지됩니다.'
 elif known=='STORAGE_QUOTA_EXCEEDED' or 'quota' in text and 'exceeded' in text:
  code='STORAGE_QUOTA_EXCEEDED';message='공용 DB 제공업체의 사용 한도로 연결이 차단되었습니다. 관리자가 현재 DB의 사용량을 확인해야 합니다. 기존 데이터는 유지됩니다.'
 else:code=known if known=='STORAGE_UNAVAILABLE' else 'STORAGE_UNAVAILABLE';message='공용 DB에 일시적으로 연결하지 못했습니다. 잠시 후 연결 상태를 다시 확인하세요. 기존 입력과 데이터는 유지됩니다.'
 trace=uuid.uuid4().hex[:16];state=str(getattr(error,'sqlstate','') or '')
 log={'event':'storage_request_failed','code':code,'trace_id':trace,'failure_kind':getattr(error,'failure_kind',type(error).__name__),'environment':os.environ.get('VERCEL_ENV','unknown') if os.environ.get('VERCEL_ENV','unknown') in ('production','preview','development','unknown') else 'unknown','database_configured':bool(os.environ.get('DATABASE_URL','').strip())}
 if re.fullmatch('[A-Z0-9]{5}',state):log['sqlstate']=state
 # 플랫폼이 제공하는 배포 식별자만 기록한다. URL·호스트·사용자 입력은 기록하지 않는다.
 deployment=os.environ.get('VERCEL_DEPLOYMENT_ID','')
 if re.fullmatch(r'dpl_[A-Za-z0-9]+',deployment):log['deployment_id']=deployment
 if path.split('?',1)[0] in ('/api/auth/status','/api/auth/login','/api/system/storage-status'):log['route']=path.split('?',1)[0]
 print(json.dumps(log),file=sys.stderr,flush=True)
 return {'error':message,'code':code,'origin':'shared_database','trace_id':trace,'retry_after':getattr(error,'retry_after',15)}
