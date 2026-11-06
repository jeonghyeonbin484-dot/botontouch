"""가상자료 사용 안내 영상만 제공. DB·사용자 자료를 읽지 않는다."""
from pathlib import Path
import re
TYPES={'.mp4':'video/mp4','.jpg':'image/jpeg','.vtt':'text/vtt; charset=utf-8'}
def serve(handler,root):
 path=handler.path.split('?',1)[0]
 if not path.startswith('/media/'):return False
 name=path.removeprefix('/media/')
 if not re.fullmatch(r'botontouch-guide-v[0-9]+\.(mp4|jpg|vtt)',name):handler.respond(404,{'error':'안내 영상 파일이 없습니다.'});return True
 file=Path(root)/'public/media'/name
 if not file.is_file():handler.respond(404,{'error':'안내 영상을 준비 중입니다.'});return True
 size=file.stat().st_size;start=0;end=size-1;status=200;requested=handler.headers.get('Range')
 if requested:
  match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
  try:
   if not match or not any(match.groups()):raise ValueError()
   first,last=match.groups()
   if first:start=int(first);end=min(int(last),size-1) if last else size-1
   else:start=max(0,size-int(last))
   if start>end or start>=size:raise ValueError()
   status=206
  except ValueError:
   handler.send_response(416);handler.send_header('Content-Range','bytes */'+str(size));handler.send_header('Content-Length','0');handler.end_headers();return True
 handler.send_response(status);handler.send_header('Content-Type',TYPES[file.suffix]);handler.send_header('Accept-Ranges','bytes');handler.send_header('Content-Length',str(end-start+1));handler.send_header('Cache-Control','public,max-age=86400');handler.send_header('X-Content-Type-Options','nosniff')
 if status==206:handler.send_header('Content-Range',f'bytes {start}-{end}/{size}')
 handler.end_headers()
 try:
  with file.open('rb') as stream:
   stream.seek(start);remaining=end-start+1
   while remaining:
    chunk=stream.read(min(256*1024,remaining))
    if not chunk:break
    handler.wfile.write(chunk);remaining-=len(chunk)
 except (BrokenPipeError,ConnectionAbortedError,ConnectionResetError):pass
 return True
