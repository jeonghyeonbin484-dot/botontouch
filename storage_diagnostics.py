"""공개 저장소 오류를 원문/접속 문자열 없이 분류한다."""
import json,sys,uuid

def payload(error):
 text=str(error).lower()
 if 'quota' in text and 'exceeded' in text:
  code='STORAGE_QUOTA_EXCEEDED';message='공유 테스트 DB 제공업체의 사용 한도를 초과해 연결할 수 없습니다. 관리자가 Neon 콘솔의 프로젝트 제한을 확인해야 합니다. 기존 데이터는 삭제하지 않았습니다.'
 else:
  code='STORAGE_UNAVAILABLE';message='공유 테스트 DB에 연결하지 못했습니다. 관리자에게 오류 조회번호를 전달해 주세요. 기존 입력과 데이터는 유지됩니다.'
 trace=uuid.uuid4().hex[:16]
 print(json.dumps({'event':'storage_request_failed','code':code,'trace_id':trace}),file=sys.stderr,flush=True)
 return {'error':message,'code':code,'origin':'shared_database','trace_id':trace}
