"""Vercel entry point. No local production DB/configuration is deployed."""
import sys,io,json,os,gzip
from pathlib import Path
from batontouch.common.paths import PROJECT_ROOT
from batontouch.server import application as app
from batontouch.storage.shared_store import database_request, StorageUnavailable

class handler(app.Handler):
 def log_message(self,*args):pass
 def do_GET(self):
  route=self.path.split('?')[0]
  if any(part.startswith('.') for part in route.split('/') if part) or route.endswith(('.py','.sqlite3','.json','.env')):return self.simple(404,{'error':'페이지가 없습니다.'})
  if route=='/login':
   raw=(PROJECT_ROOT/'frontend/login.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw);return
  if not route.startswith('/api/') and 'baton_session=' not in self.headers.get('Cookie',''):
   self.send_response(303);self.send_header('Location','/login');self.send_header('Cache-Control','no-store');self.end_headers();return
  self.dispatch('GET')
 def do_POST(self):self.dispatch('POST')
 def dispatch(self,method):
  if self.path.split('?')[0]=='/api/system/storage-status':
   if method!='GET':return self.simple(405,{'error':'상태 확인에는 GET 요청을 사용하세요.'})
   try:return self.simple(200,__import__('cloud_store').readiness())
   except Exception as error:return self.simple(503,__import__('storage_diagnostics').payload(error,self.path))
  if self.path.split('?')[0] in ('/api/system/capabilities','/api/demo/status'):
   cfg=__import__('ai_draft').settings()
   return self.simple(200,{'environment':'cloud','ai_mode':cfg['mode'],'ai_scope':cfg['scope'],'model':cfg['model'],'ai_transmission_ready':cfg['scope']=='approved-materials' and all(os.environ.get(k)=='true' for k in ('AI_EXTERNAL_TRANSMISSION_ALLOWED','AI_APPROVED_WRITING_ALLOWED','BATON_AI_APPROVED_MATERIALS')) and bool(os.environ.get('AI_APPROVAL_REFERENCE','')),'organization_sync_enabled':os.environ.get('BATON_ORG_SYNC_ALLOWED')=='true','storage_configured':bool(os.environ.get('DATABASE_URL')),'release':'full-20261107-storage','authentication_required':True,'external_transmission_allowed':cfg['mode']=='live' and (cfg['scope']=='approved-materials' and all(os.environ.get(k)=='true' for k in ('AI_EXTERNAL_TRANSMISSION_ALLOWED','AI_APPROVED_WRITING_ALLOWED','BATON_AI_APPROVED_MATERIALS')) and bool(os.environ.get('AI_APPROVAL_REFERENCE','')) or cfg['scope']=='verified-fictional-only' and os.environ.get('BATON_STAFF_FICTIONAL_ALLOWED')=='true')})
  try:size=int(self.headers.get('Content-Length','0'))
  except ValueError:return self.simple(400,{'error':'요청 크기가 올바르지 않습니다.'})
  if size<0 or size>4*1024*1024:return self.simple(413,{'error':'현재 Vercel 함수 경로는 요청당 4MB까지 등록할 수 있습니다. 대용량 자료는 별도 저장소 연결이 필요합니다. 기존 입력은 유지됩니다.'})
  output=self.wfile;self.wfile=io.BytesIO();self.capture=True;self.captured_status=200;self.captured_headers=[]
  try:
   with database_request():
    if method=='GET':app.Handler.do_GET(self)
    else:app.Handler.do_POST(self)
    payload=self.wfile.getvalue()
    if len(payload)>4*1024*1024:raise StorageUnavailable('다운로드가 Vercel 함수의 응답 한도(4MB)를 초과했습니다.')
  except StorageUnavailable as error:
   self.wfile=output;self.capture=False;return self.simple(503,__import__('storage_diagnostics').payload(error,self.path))
  except Exception as error:
   # Never serialize provider errors, connection strings, bodies, or credentials.
   self.wfile=output;self.capture=False;return self.simple(503,__import__('storage_diagnostics').payload(error,self.path))
  self.wfile=output;self.capture=False
  if len(payload)>1024 and 'gzip' in self.headers.get('Accept-Encoding','') and any(k.lower()=='content-type' and ('text/' in v or 'application/json' in v) for k,v in self.captured_headers):
   payload=gzip.compress(payload,compresslevel=5)
   self.captured_headers=[(k,v) for k,v in self.captured_headers if k.lower()!='content-length']+ [('Content-Encoding','gzip'),('Vary','Accept-Encoding'),('Content-Length',str(len(payload)))]
  super().send_response(self.captured_status)
  for key,value in self.captured_headers:super().send_header(key,value)
  super().end_headers();self.wfile.write(payload)
 def send_response(self,code,message=None):
  if getattr(self,'capture',False):self.captured_status=code
  else:super().send_response(code,message)
 def send_header(self,key,value):
  if getattr(self,'capture',False):self.captured_headers.append((key,value))
  else:super().send_header(key,value)
 def end_headers(self):
  if not getattr(self,'capture',False):super().end_headers()
 def simple(self,status,data):
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);
  if status==503:self.send_header('Retry-After',str(data.get('retry_after',60)))
  self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
