import sys,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
sys.path.insert(0,str(ROOT.parents[1]/'.ui-tools'))
from test_cloud import Fixture,PASSWORD
from playwright.sync_api import sync_playwright

def run(base=None,password=PASSWORD):
 f=Fixture().start() if base is None else None
 base=f.url if f else base
 checks=[];errors=[];external=[];folder=ROOT.parents[1]/'artifacts'/'vercel-browser';folder.mkdir(exist_ok=True)
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
   def login(name):
    context=browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True)
    context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else (external.append(route.request.resource_type),route.abort())[1])
    page=context.new_page();page.set_default_timeout(60000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base);page.locator('#auth-username').fill(name);page.locator('#auth-password').fill(password);page.locator('#auth-submit').click();page.wait_for_function("!!document.querySelector('#staff-profile')?.textContent");return page
   a=login('demo.a');checks.append('가상 직원 로그인 및 보호된 홈 진입')
   a.locator('#journey-start').click();a.locator('#journey-title').fill('가상 사무용품 구매 및 관리');a.locator('#journey-prepare').click()
   a.wait_for_function("!state.busy.size && !journeyCreating && !document.querySelector('#journey-files').hidden")
   a.locator('#upload').set_input_files(dict(name='demo.txt',mimeType='text/plain',buffer='가상 사무용품을 매월 점검합니다. 부족한 수량을 확인합니다.'.encode()));a.locator('#submit').click();a.wait_for_function("document.querySelector('#file-count').textContent==='1개'");checks.append('새 인수인계 작성 및 가상 파일 등록')
   a.locator('#journey-next').click();a.locator('#draft-choices input').first.check();a.locator('#generate').click();a.locator('#editor').wait_for(state='visible');assert '실제 AI 아님' in a.evaluate('state.draft.model');checks.append('AI 모의 초안 생성 및 실제 AI와 구분')
   a.locator('#draft-items textarea').first.fill('가상 사무용품을 매주 확인합니다.');a.wait_for_function("!state.draftDirty && document.querySelector('#journey-save-state').textContent.startsWith('마지막 저장')");a.reload();a.locator('#editor').wait_for(state='visible');assert a.locator('#draft-items textarea').first.input_value()=='가상 사무용품을 매주 확인합니다.';checks.append('직접 수정·자동 저장·새로고침 후 복원')
   a.locator('#journey-next').click();a.locator('#journey-gap-check').click();a.locator('#journey-gap-list .journey-question').first.wait_for();a.locator('#journey-gap-list').get_by_role('button',name='나중에 답변',exact=True).first.click();a.wait_for_function("!state.busy.size");checks.append('모의 누락 점검 및 미해결 상태 저장')
   a.locator('#journey-next').click();a.locator('#recipient-department').select_option('DEMO-RECEIVE');a.locator('#recipient-employee option[value="DEMO-B"]').wait_for(state='attached');a.locator('#recipient-employee').select_option('DEMO-B');a.locator('#journey-next').click();a.locator('#journey-final-reviewed').check();a.locator('#send-handover').click();a.locator('#confirm-accept').click();a.locator('#request-detail-panel').wait_for(state='visible');checks.append('가상 부서·인수자 선택 및 요청 발송')
   b=login('demo.b');b.locator('#navigation a[href="#inbox"]').click();b.locator('#received-requests .text-button').first.click();b.locator('#request-detail-panel').wait_for(state='visible');b.get_by_role('button',name='인수 수락',exact=True).click();b.locator('#confirm-accept').click();b.wait_for_function("requestSelection?.state==='accepted'");checks.append('다른 브라우저 세션의 수신·인수 수락')
   with b.expect_download() as dl:b.get_by_role('button',name='요청 문서 한글 내려받기',exact=True).click()
   target=folder/'가상인수인계.hwpx';dl.value.save_as(target)
   with zipfile.ZipFile(target) as z:assert z.testzip() is None
   checks.append('HWPX 다운로드 및 ZIP 구조 확인');b.screenshot(path=str(folder/'수신상세.png'),full_page=True)
   assert not errors,errors;assert not external,external;browser.close()
 finally:
  if f:f.stop()
  (folder/'report.json').write_text(json.dumps(dict(checks=checks,page_errors=errors,external_requests=external,environment='deployed' if not f else 'local transaction double',ai='mock'),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(passed=len(checks),page_errors=len(errors),external_requests=len(external))))
if __name__=='__main__':run()
