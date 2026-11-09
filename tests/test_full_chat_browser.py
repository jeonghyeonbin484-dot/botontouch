import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT.parents[1]/'.ui-tools'))
from playwright.sync_api import sync_playwright,expect
from test_cloud import Fixture,PASSWORD
import os
os.environ['VERCEL']='1'
f=Fixture().start();checks=[];errors=[];out=ROOT.parents[1]/'artifacts/final-release/chat-cloud';out.mkdir(parents=True,exist_ok=True)
try:
 aclient=f.login('demo.a');doc=f.call('/api/documents','가상 업무 점검'.encode(),aclient,{'X-File-Name':'fictional.txt'});draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},aclient);draft['reviewed']=True;draft=f.call('/api/drafts/save',draft,aclient);rid=f.call('/api/requests/send',{'draft_id':draft['id'],'workspace_id':1,'fingerprint':draft['edit_token'],'recipient_employee':'DEMO-B'},aclient)['id']
 with sync_playwright() as p:
  expect.set_options(timeout=12000)
  browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
  contexts=[];pages=[]
  for username in ['demo.a','demo.b']:
   ctx=browser.new_context(viewport={'width':1400,'height':1000});contexts.append(ctx)
   ctx.route('**/*',lambda r:r.continue_() if r.request.url.startswith(f.url) else r.abort())
   page=ctx.new_page();pages.append(page);page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f.url);page.locator('#auth-username').fill(username);page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("location.pathname==='/'&&getComputedStyle(document.body).visibility==='visible'")
   page.locator('#navigation a[href="#chats"]').click();expect(page.locator('.chat-room-row')).to_have_count(1)
  a,b=pages;checks.append('두 계정 로그인 및 사이드바 대화방 진입')
  a.locator('.chat-room-row button').last.click();a.locator('.chat-compose textarea').fill('가상 업무 확인 질문입니다.');a.locator('.chat-compose button[type="submit"]').click();expect(a.locator('.chat-bubble')).to_contain_text('가상 업무 확인 질문입니다.')
  b.evaluate('checkChatUnread()');expect(b.locator('#nav-chat-count')).to_have_text('1');expect(b.locator('.chat-message-toast')).to_be_visible();expect(b.locator('.chat-room-row.unread')).to_have_count(1);checks.append('새 메시지 상단 알림 및 읽지 않음 배지')
  b.locator('.chat-message-toast-open').click();expect(b.locator('.chat-bubble')).to_contain_text('가상 업무 확인 질문입니다.');b.wait_for_function('chatLastRead>0');b.evaluate('checkChatUnread()');expect(b.locator('#nav-chat-count')).to_be_hidden();checks.append('알림 클릭 이동 및 읽음 처리')
  b.locator('.chat-compose textarea').fill('가상 답변을 전달합니다.');b.locator('.chat-compose button[type="submit"]').click();expect(a.locator('.chat-bubble').last).to_contain_text('가상 답변을 전달합니다.');checks.append('실시간 양방향 송수신')
  a.locator('.handover-chat').screenshot(path=str(out/'sender-chat.png'));b.locator('.handover-chat').screenshot(path=str(out/'recipient-chat.png'))
  b.locator('.chat-head button').filter(has_text='인수인계서 보기').click();expect(b.locator('#request-detail .chat-entry')).to_have_text('인계자에게 질문하기');b.locator('#request-detail .chat-entry').click();expect(b.locator('.chat-bubble')).to_have_count(2);checks.append('상세 화면 진입 및 기존 기록 재조회')
  print('단계: 목록 촬영',flush=True);a.locator('.chat-head button').filter(has_text='닫기').click();a.locator('#chat-refresh').click();a.screenshot(path=str(out/'room-list.png'))
  b.locator('.chat-head button').filter(has_text='닫기').click();print('단계: 모바일 검사',flush=True);b.set_viewport_size({'width':390,'height':844});b.evaluate("location.hash='chats'");b.wait_for_function("state.route==='chats'");b.locator('#chat-refresh').click();b.screenshot(path=str(out/'mobile-list.png'));assert b.evaluate('document.documentElement.scrollWidth<=innerWidth');checks.append('모바일 목록 너비')
  assert not errors,errors
  print('단계: 브라우저 종료',flush=True);browser.close()
 result={'checks':checks,'result':'PASS','javascript_errors':errors,'actual_ai_calls':0};(out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
finally:f.stop()
