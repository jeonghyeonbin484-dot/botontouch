"""공통 출력 응답: 동일 데이터 지문을 HTML·MD·HWPX에 적용한다."""
from urllib.parse import quote,urlsplit,parse_qs
from batontouch.reports import document_model as report_document
from batontouch.reports import hwpx_generator as export_hwpx
from batontouch.auth import sessions as auth_control

def respond(handler,payload,extension,filename):
 model=export_hwpx.output_model(payload)
 expected=parse_qs(urlsplit(handler.path).query).get('report_hash',[''])[0]
 if expected and expected!=model['fingerprint']:raise auth_control.AccessError(409,'미리보기 이후 저장 내용이 바뀌었습니다. 미리보기를 다시 열고 내려받으세요.')
 if extension=='hwpx':raw=export_hwpx.build(payload);mime='application/hwp+zip'
 elif extension=='html':raw=report_document.html_document(model).encode('utf-8');mime='text/html; charset=utf-8'
 else:raw=report_document.markdown(model).encode('utf-8');mime='text/markdown; charset=utf-8'
 handler.send_response(200);handler.send_header('Content-Type',mime)
 handler.send_header('Content-Disposition',('inline' if extension=='html' else 'attachment')+f"; filename=handover.{extension}; filename*=UTF-8''"+quote(filename+'.'+extension))
 handler.send_header('X-Report-Fingerprint',model['fingerprint']);handler.send_header('Content-Length',str(len(raw)));handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff')
 if extension=='html':handler.send_header('Content-Security-Policy',"default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
 handler.end_headers();handler.wfile.write(raw)
