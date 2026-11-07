import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT.parents[1]/'.ui-tools'))
from test_cloud import Fixture
from playwright.sync_api import sync_playwright,expect
f=Fixture().start();out=ROOT.parents[1]/'artifacts/external-db-recovery';out.mkdir(parents=True,exist_ok=True)
try:
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True);page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(type(e).__name__))
  def unavailable(route):route.fulfill(status=503,json={'error':'공용 DB 서버 설정을 확인하세요.','code':'STORAGE_NOT_CONFIGURED','trace_id':'fictional-trace-only'})
  page.route('**/api/auth/status',unavailable);page.goto(f.url+'/login');expect(page.locator('#connection-retry')).to_be_visible();expect(page.locator('#auth-message')).to_contain_text('fictional-trace-only');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill('Fictional-not-submitted!');page.unroute('**/api/auth/status',unavailable);page.locator('#connection-retry').click();expect(page.locator('#connection-retry')).to_be_hidden(timeout=20000);expect(page.locator('#auth-username')).to_have_value('demo.a');expect(page.locator('#auth-password')).to_have_value('Fictional-not-submitted!');assert not errors;page.locator('#auth-password').fill('');page.screenshot(path=str(out/'configuration-error-recovered.png'));b.close()
 (out/'browser-error-recovery.json').write_text(json.dumps({'result':'PASS','checks':['DB 장애와 인증 실패 구분','오류 조회번호 표시','자동 재시도 없이 사용자 재확인','복구 뒤 아이디·입력 보존'],'javascript_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
finally:f.stop()
