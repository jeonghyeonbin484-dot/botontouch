"""Vercel entry point. No local production DB/configuration is deployed."""
import sys,io,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from cloud_store import database_request,StorageUnavailable

class handler(app.Handler):
 def log_message(self,*args):pass
 def do_GET(self):self.dispatch('GET')
 def do_POST(self):self.dispatch('POST')
 def dispatch(self,method):
  if self.path.split('?')[0]=='/api/demo/status':
   return self.simple(200,{'environment':'public-demo','ai_mode':'mock','external_transmission_allowed':False,'real_organization_enabled':False,'storage_configured':bool(os.environ.get('DATABASE_URL')),'notice':'가상 데이터 전용 공개 테스트'})
  try:size=int(self.headers.get('Content-Length','0'))
  except ValueError:return self.simple(400,{'error':'요청 크기가 올바르지 않습니다.'})
  if size<0 or size>4*1024*1024:return self.simple(413,{'error':'공개 테스트 파일은 요청당 4MB까지 등록할 수 있습니다. 기존 입력은 유지됩니다.'})
  output=self.wfile;self.wfile=io.BytesIO();self.capture=True;self.captured_status=200;self.captured_headers=[]
  try:
   with database_request():
    if method=='GET':app.Handler.do_GET(self)
    else:app.Handler.do_POST(self)
    payload=self.wfile.getvalue()
    if len(payload)>4*1024*1024:raise StorageUnavailable('다운로드가 공개 테스트의 응답 한도(4MB)를 초과했습니다.')
  except StorageUnavailable as error:
   self.wfile=output;self.capture=False;return self.simple(503,{'error':str(error)})
  except Exception:
   # Never serialize provider errors, connection strings, bodies, or credentials.
   self.wfile=output;self.capture=False;return self.simple(503,{'error':'테스트 저장소 처리에 실패했습니다. 잠시 후 다시 시도하세요. 기존 입력은 유지됩니다.'})
  self.wfile=output;self.capture=False
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
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
