"""Real browser messenger flow on fictional, isolated shared storage."""
import os,unittest,uuid,json
from contextlib import closing
import app,cloud_store
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD

class MessengerBrowserTests(unittest.TestCase):
 def test_delayed_older_messages_do_not_mix_rooms_and_drafts_are_scoped(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');b=f.login('demo.b');doc=f.call('/api/documents',b'fictional',a,{'X-File-Name':'fixture.txt'});rooms=[]
   for title in ('이전 대화 업무','두 번째 업무'):
    d=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);d.update(title=title,reviewed=True);d=f.call('/api/drafts/save',d,a);rooms.append(f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},a)['id'])
   with cloud_store.database_request():
    with closing(app.connect()) as db:
     actor=db.execute('SELECT sender_account FROM handover_requests WHERE id=?',(rooms[0],)).fetchone()[0]
     for i in range(65):db.execute("INSERT INTO request_chat_messages(request_id,sender_id,recipient_employee,body,nonce,created) VALUES(?,?,?,?,?,'2026-01-01T00:00:00.000Z')",(rooms[0],actor,'DEMO-B','역사 대화 %03d'%i,str(uuid.uuid4())))
     db.commit()
   f.call('/api/chat/'+str(rooms[1])+'/messages',{'text':'두 번째 방 메시지','nonce':str(uuid.uuid4())},a)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
    page=browser.new_page(viewport={'width':1440,'height':950});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.b');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");page.goto(f.url+'/#chats');page.locator('.messenger-room[data-request-id="'+str(rooms[0])+'"]').click();page.wait_for_function('(id)=>chatRoom?.request_id===id',arg=rooms[0])
    page.get_by_label('대화 메시지',exact=True).fill('첫 방의 보관할 초안');pending=[];page.route('**/api/chat/'+str(rooms[0])+'/messages?before=*',lambda route:pending.append(route));page.get_by_role('button',name='이전 대화 불러오기',exact=True).click();page.wait_for_timeout(100);self.assertEqual(len(pending),1)
    older=f.call('/api/chat/'+str(rooms[0])+'/messages?before=6',client=b)
    page.locator('.messenger-room[data-request-id="'+str(rooms[1])+'"]').click();page.wait_for_function('(id)=>chatRoom?.request_id===id',arg=rooms[1]);pending[0].fulfill(status=200,content_type='application/json',body=json.dumps(older));page.wait_for_timeout(100)
    self.assertEqual(page.locator('.chat-messages').inner_text().count('두 번째 방 메시지'),1);self.assertNotIn('역사 대화',page.locator('.chat-messages').inner_text());self.assertEqual(page.get_by_label('대화 메시지',exact=True).input_value(),'')
    page.locator('.messenger-room[data-request-id="'+str(rooms[0])+'"]').click();page.wait_for_function('(id)=>chatRoom?.request_id===id',arg=rooms[0]);self.assertEqual(page.get_by_label('대화 메시지',exact=True).input_value(),'첫 방의 보관할 초안');self.assertEqual(errors,[]);browser.close()
  finally:f.stop()
 def test_desktop_mobile_messages_questions_files_reads_and_relogin(self):
  out=Path('artifacts/chat-messenger');out.mkdir(parents=True,exist_ok=True)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
   for width in (1440,390):
    f=Fixture().start()
    try:
     a=f.login('demo.a');b=f.login('demo.b');doc=f.call('/api/documents','가상 월간 업무 원문'.encode(),a,{'X-File-Name':'fixture.txt'});rooms=[]
     for title in ('월간 점검 대화','시설 관리 대화'):
      d=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);d.update(title=title,reviewed=True);d=f.call('/api/drafts/save',d,a);rooms.append(f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},a)['id'])
     def send(rid,text):return f.call('/api/chat/'+str(rid)+'/messages',{'text':text,'nonce':str(uuid.uuid4())},a)
     send(rooms[0],'월말 점검을 부탁드립니다.');send(rooms[1],'시설 일정을 확인해 주세요.')
     errors=[]
     def login(user):
      p=browser.new_page(viewport={'width':width,'height':1000},accept_downloads=True);p.on('pageerror',lambda e:errors.append(str(e)))
      p.goto(f.url+'/login');p.locator('#auth-username').fill(user);p.locator('#auth-password').fill(PASSWORD);p.locator('#auth-submit').click();p.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
      p.goto(f.url+'/#chats');p.locator('.messenger-room').first.wait_for();return p
     page=login('demo.b');self.assertEqual(page.locator('.messenger-room').count(),2);self.assertEqual(page.locator('.messenger-room').first.get_attribute('data-request-id'),str(rooms[1]))
     page.get_by_label('대화방 검색',exact=True).fill('월간');self.assertEqual(page.locator('.messenger-room').count(),1);page.locator('.messenger-room').click();page.wait_for_function('(id)=>chatId===id&&!!chatRoom',arg=rooms[0])
     page.wait_for_function("chatLastRead>0");self.assertTrue(page.locator('.handover-chat.messenger-inline').is_visible());self.assertIn('월말 점검',page.locator('.chat-messages').inner_text())
     if width>800:self.assertTrue(page.locator('.messenger-list').is_visible())
     else:self.assertFalse(page.locator('.messenger-list').is_visible())
     page.get_by_label('대화 메시지',exact=True).fill('일정을 확인했습니다.');page.locator('.chat-compose').get_by_role('button',name='보내기',exact=True).click();page.wait_for_function("[...chatMessages.values()].some(m=>m.mine&&m.body==='일정을 확인했습니다.')")
     self.assertGreater(page.locator('.chat-line.mine').count(),0);self.assertGreater(page.locator('.chat-line.theirs').count(),0)
     self.assertEqual(f.call('/api/requests/'+str(rooms[0]),client=b)['state'],'requested')
     page.get_by_label('대화 메시지',exact=True).fill('작성 중인 메시지');send(rooms[1],'다른 업무의 새 메시지입니다.')
     if width<800:page.get_by_role('button',name='대화 목록으로',exact=True).click()
     page.get_by_label('대화방 검색',exact=True).fill('');page.wait_for_function('(id)=>chatRooms.find(r=>r.request_id===id)?.unread===2',arg=rooms[1])
     if width<800:page.locator('.messenger-room[data-request-id="'+str(rooms[0])+'"]').click();page.wait_for_function('(id)=>chatId===id&&!!chatRoom',arg=rooms[0])
     self.assertEqual(page.get_by_label('대화 메시지',exact=True).input_value(),'작성 중인 메시지')
     self.assertEqual(f.call('/api/chat/rooms',client=b)['rooms'][0]['unread'],2)
     page.get_by_role('button',name='질문·답변',exact=True).click();page.get_by_label('대화방 추가 질문').fill('월말 점검 담당자는 누구인가요?');page.get_by_role('button',name='질문 등록',exact=True).click()
     try:page.wait_for_function('messengerQuestionState?.questions.length===1&&!messengerQuestionBusy')
     except Exception:
      page.screenshot(path=str(out/'question-error.png'));print(page.evaluate('({room:chatId,busy:messengerQuestionBusy,count:messengerQuestionState?.questions.length,revision:messengerQuestionState?.revision,notice:messengerQuestionNotice.textContent})'));print(errors);raise
     sender=login('demo.a');sender.locator('.messenger-room[data-request-id="'+str(rooms[0])+'"]').click();sender.wait_for_function('(id)=>chatId===id&&!!chatRoom',arg=rooms[0]);sender.get_by_role('button',name='질문·답변',exact=True).click()
     sender.get_by_label('대화방 질문 답변',exact=False).fill('서무 담당자와 함께 점검합니다.');sender.get_by_role('button',name='답변 저장',exact=True).click();sender.wait_for_function('messengerQuestionState?.questions[0]?.reply.includes("서무 담당자")&&!messengerQuestionBusy')
     page.bring_to_front();page.get_by_role('button',name='질문·답변',exact=True).click();page.get_by_role('button',name='질문·답변',exact=True).click();page.wait_for_function('messengerQuestionState?.questions[0]?.reply.includes("서무 담당자")')
     page.get_by_role('button',name='답변 확인 완료',exact=True).click();page.wait_for_function('messengerQuestionState?.details.answers_reviewed&&!messengerQuestionBusy')
     self.assertEqual(page.locator('.messenger-question-progress li.done').count(),4)
     page.get_by_role('button',name='질문·답변',exact=True).click()
     raw=b'%PDF-1.4\nfictional messenger attachment';page.get_by_label('대화 파일 첨부',exact=True).set_input_files({'name':'messenger.pdf','mimeType':'application/pdf','buffer':raw});page.get_by_role('button',name='파일 보내기',exact=True).click();page.wait_for_function('[...chatMessages.values()].some(m=>m.name==="messenger.pdf")&&!chatBusy')
     sender.bring_to_front();sender.locator('.chat-file').filter(has_text='messenger.pdf').wait_for()
     with sender.expect_download() as downloaded:sender.locator('.chat-file').filter(has_text='messenger.pdf').click()
     self.assertEqual(Path(downloaded.value.path()).read_bytes(),raw)
     page.bring_to_front();page.get_by_role('button',name='인수인계서 보기',exact=True).click();page.locator('.report-preview-dialog').wait_for(state='visible');page.frame_locator('.report-preview-dialog iframe').locator('html[data-ready=true]').wait_for()
     self.assertIn('월간 점검 대화',page.frame_locator('.report-preview-dialog iframe').locator('#pages').inner_text())
     send(rooms[0],'미리보기 중 도착한 메시지');page.wait_for_function("[...chatMessages.values()].some(m=>m.body==='미리보기 중 도착한 메시지')")
     self.assertGreater(next((r['count'] for r in f.call('/api/chat/unread',client=b)['rooms'] if r['request_id']==rooms[0]),0),0)
     page.locator('.report-preview-dialog').get_by_role('button',name='닫기',exact=True).click();page.wait_for_function("chatLastRead===Math.max(...chatMessages.keys())")
     self.assertEqual(f.call('/api/requests/'+str(rooms[0]),client=b)['state'],'reviewing')
     page.screenshot(path=str(out/('conversation-'+str(width)+'.png')))
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2)
     page.reload();page.wait_for_function('(id)=>chatId===id&&!!chatRoom',arg=rooms[0]);self.assertIn('일정을 확인했습니다.',page.locator('.chat-messages').inner_text())
     page.request.post(f.url+'/api/auth/logout',data='{}',headers={'Content-Type':'application/json'});page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.b');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");page.goto(f.url+'/#chats');page.wait_for_function('(id)=>chatId===id&&!!chatRoom',arg=rooms[0]);self.assertIn('일정을 확인했습니다.',page.locator('.chat-messages').inner_text())
     if width<800:page.get_by_role('button',name='대화 목록으로',exact=True).click();self.assertTrue(page.locator('.messenger-list').is_visible());self.assertFalse(page.locator('.messenger-detail').is_visible())
     self.assertEqual(errors,[]);sender.close();page.close()
    finally:f.stop()
   browser.close()
