"""Gemini REST transport: bounded 503-only retries, redacted diagnostics, no fallback."""
import json,time,random,re,urllib.request,urllib.error
class GeminiTransportError(ValueError):
 def __init__(self,message,upstream_status=None,provider_error=None,attempts=None):
  super().__init__(message);self.upstream_status=upstream_status;self.http_status=503 if upstream_status==503 else 502;self.provider_error=provider_error or {};self.attempts=attempts or []

def generate_content(key,model,payload,timeout=60,max_retries=2):
 if not key or not re.fullmatch(r'[a-zA-Z0-9._-]+',model or ''):raise ValueError('Gemini 키 또는 모델 설정을 확인하세요.')
 deadline=time.monotonic()+timeout;attempts=[]
 for index in range(max(0,min(int(max_retries),2))+1):
  remaining=deadline-time.monotonic()
  if remaining<=0:raise GeminiTransportError('AI 요청 제한시간(60초)을 초과했습니다. 입력은 유지됩니다.',attempts=attempts)
  start=time.monotonic();request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
  try:
   with urllib.request.urlopen(request,timeout=remaining) as response:
    value=json.load(response);attempts.append({'attempt':index+1,'http_status':getattr(response,'status',200),'seconds':round(time.monotonic()-start,3)})
    return value,{'model':model,'http_status':200,'attempts':attempts,'retries':index,'elapsed_seconds':round(timeout-(deadline-time.monotonic()),3)}
  except urllib.error.HTTPError as error:
   raw=error.read(16384);error.close()
   try:body=json.loads(raw);details=body.get('error',{});safe={k:details[k] for k in ('code','status','message') if k in details};safe=json.loads(json.dumps(safe).replace(key,'[키 삭제]'))
   except (ValueError,TypeError):safe={'status':'NON_JSON_UPSTREAM_ERROR','message':'상위 서버가 JSON이 아닌 오류 응답을 반환했습니다.'}
   attempts.append({'attempt':index+1,'http_status':error.code,'seconds':round(time.monotonic()-start,3),'provider_error':safe})
   transient=error.code==503 and safe.get('status')=='UNAVAILABLE'
   if transient and index<max_retries and index<2:
    delay=2**index+random.uniform(0,0.2)
    if deadline-time.monotonic()>delay+1:time.sleep(delay);continue
   message='AI 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요.' if error.code==503 else 'Gemini 요청 실패: HTTP '+str(error.code)+' / '+str(safe.get('status','오류'))
   raise GeminiTransportError(message,error.code,safe,attempts) from None
  except (TimeoutError,urllib.error.URLError):raise GeminiTransportError('Gemini 연결 또는 응답 제한시간을 확인하세요. 자동으로 재시도하지 않았습니다.',attempts=attempts) from None
