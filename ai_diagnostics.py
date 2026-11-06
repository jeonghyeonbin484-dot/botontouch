"""AI 장애의 발생 계층을 기록하되 원문·키·응답 본문은 기록하지 않는다."""
import json,sys,uuid,re

def payload(error,feature='',user=None):
 from gemini_transport import GeminiTransportError
 from gemini_engine import DraftSourceError
 if isinstance(error,DraftSourceError):
  trace=uuid.uuid4().hex[:16]
  record={'event':'ai_response_validation_failed','trace_id':trace,'feature':feature,'origin':'ai_validation','http_status':error.http_status,'upstream_status':200,'code':error.error_code,'reason':error.reason,'item_index':error.item_index}
  print(json.dumps(record),file=sys.stderr,flush=True)
  return {'error':str(error),'code':error.error_code,'origin':'ai_validation','trace_id':trace,'upstream_status':200}
 if not isinstance(error,GeminiTransportError):return {'error':str(error)}
 trace=uuid.uuid4().hex[:16]
 provider=error.provider_error.get('status','UNKNOWN')
 if not isinstance(provider,str) or not re.fullmatch(r'[A-Z_]{1,60}',provider):provider='UNKNOWN'
 origin='gemini' if provider!='NON_JSON_UPSTREAM_ERROR' and error.upstream_status else 'upstream_gateway' if error.upstream_status else 'network'
 code=getattr(error,'error_code',None) or ('AI_UPSTREAM_UNAVAILABLE' if error.upstream_status==503 else 'AI_UPSTREAM_ERROR')
 record={'event':'ai_request_failed','trace_id':trace,'feature':feature,'origin':origin,'http_status':error.http_status,'upstream_status':error.upstream_status,'provider_status':provider,'attempts':len(error.attempts)}
 print(json.dumps(record,ensure_ascii=False),file=sys.stderr,flush=True)
 return {'error':str(error),'code':code,'origin':origin,'trace_id':trace,'upstream_status':error.upstream_status,'provider_status':provider,'attempts':len(error.attempts)}
