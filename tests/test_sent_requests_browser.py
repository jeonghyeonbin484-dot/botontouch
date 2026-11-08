"""Sender cards and actual recipient follow-up workflow, desktop/mobile."""
import os,unittest,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD

class SentRequestsBrowserTests(unittest.TestCase):
 def test_cards_filters_snapshot_chat_and_real_progress(self):
  output=Path('artifacts/sent-requests');output.mkdir(parents=True,exist_ok=True)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
   for width in (1440,390):
    f=Fixture().start()
    try:
     a=f.login('demo.a');b=f.login('demo.b');doc=f.call('/api/documents','월말 업무 원문을 보존합니다.'.encode(),a,{'X-File-Name':'fixture.txt'});requests=[]
     for title in ('월간 점검 인수인계','시설 검토 업무','예산 수락 업무','완료된 서무 업무','보완이 필요한 업무'):
      d=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);d.update(title=title,reviewed=True);d=f.call('/api/drafts/save',d,a)
      rid=f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},a)['id'];requests.append(rid)
     f.call('/api/requests/action',{'id':requests[1],'revision':1,'action':'view'},b)
     for rid in requests[2:4]:f.call('/api/requests/action',{'id':rid,'revision':1,'action':'accept'},b)
     f.call('/api/requests/action',{'id':requests[3],'revision':1,'action':'complete'},a)
     f.call('/api/requests/action',{'id':requests[4],'revision':1,'action':'needs_info','reason':'일정을 구체적으로 알려 주세요.'},b)
     rid=requests[0];page=browser.new_page(viewport={'width':width,'height':1000},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
     page.goto(f.url+'/#sent');page.wait_for_function("document.querySelectorAll('.sent-card').length===5")
     self.assertEqual(page.locator('#page-sent .sent-filters').count(),1);self.assertEqual(page.locator('#page-sent .workbench-filters').count(),0)
     card=page.locator('.sent-card[data-request-id="'+str(rid)+'"]');self.assertIn('가상 인계자',card.inner_text());self.assertIn('가상 인수자',card.inner_text());self.assertIn('열람 확인 전',card.inner_text());self.assertEqual(card.locator('.sent-progress li').count(),4)
     self.assertFalse('done' in (card.locator('.sent-progress li').nth(1).get_attribute('class') or ''));self.assertFalse('done' in (card.locator('.sent-progress li').nth(2).get_attribute('class') or ''));self.assertFalse('done' in (card.locator('.sent-progress li').last.get_attribute('class') or ''))
     page.locator('#sent-status').select_option('accepted');page.wait_for_function("document.querySelectorAll('.sent-card').length===1");self.assertIn('최종 완료 대기',page.locator('.sent-card').inner_text())
     page.get_by_role('button',name='검색 초기화',exact=True).click();page.locator('#sent-query').fill('월간');page.wait_for_function("id=>document.querySelectorAll('.sent-card').length===1&&document.querySelector('.sent-card')?.dataset.requestId===String(id)",arg=rid)
     page.locator('.sent-card').get_by_role('button',name='인수인계서 보기',exact=True).click();page.locator('.report-preview-dialog').wait_for(state='visible');frame=page.frame_locator('.report-preview-dialog iframe');frame.locator('html[data-ready=true]').wait_for();self.assertIn('월간 점검 인수인계',frame.locator('#pages').inner_text());self.assertGreater(frame.locator('.report-brand img').count(),0)
     with page.expect_download() as downloaded:page.locator('.report-preview-dialog').get_by_role('button',name='같은 내용 HWPX 다운로드',exact=True).click()
     with zipfile.ZipFile(downloaded.value.path()) as archive:self.assertIn('월간 점검 인수인계',archive.read('Preview/PrvText.txt').decode())
     page.locator('.report-preview-dialog').get_by_role('button',name='닫기',exact=True).click();self.assertEqual(f.call('/api/requests/'+str(rid),client=b)['state'],'requested')
     page.locator('.sent-card').get_by_role('button',name='대화하기',exact=True).click();chat=page.locator('.handover-chat');chat.get_by_label('대화 메시지').fill('문서 검토를 부탁드립니다.');chat.get_by_role('button',name='보내기',exact=True).click();page.wait_for_function("[...chatMessages.values()].some(m=>m.body==='문서 검토를 부탁드립니다.')");chat.get_by_role('button',name='닫기',exact=True).click()
     self.assertEqual(f.call('/api/requests/'+str(rid),client=b)['state'],'requested')
     f.call('/api/requests/action',{'id':rid,'revision':1,'action':'view'},b);f.call('/api/journey/question',{'request_id':rid,'question':'월말 점검 담당자는 누구인가요?'},b)
     page.locator('#reload-sent-requests').click();page.wait_for_function("document.querySelector('.sent-card').textContent.includes('미답변 추가 질문')&&document.querySelector('.sent-card').textContent.includes('질문 1건')")
     page.locator('.sent-card').get_by_role('button',name='진행 상황 확인',exact=True).click();page.wait_for_function('requestSelection?.question_count===1')
     self.assertEqual(page.locator('.received-overview .sent-progress li').count(),4)
     q=page.locator('#journey-request-questions .journey-question').first;q.get_by_label('질문 답변',exact=False).fill('서무 담당자와 월말에 함께 점검합니다.');q.get_by_role('button',name='답변 저장',exact=True).click();page.wait_for_function('requestSelection?.unanswered_count===0')
     self.assertIn('인수자의 답변 확인',page.locator('.sent-next-action').inner_text())
     row=f.call('/api/requests/'+str(rid),client=b);f.call('/api/requests/answers-reviewed',{'id':rid,'revision':1,'answer_token':row['answer_token']},b);f.call('/api/requests/action',{'id':rid,'revision':1,'action':'accept'},b)
     page.locator('#reload-sent-requests').click();page.wait_for_function("requestSelection?.state==='accepted'")
     self.assertIn('최종 완료',page.locator('.received-detail-guide').inner_text());page.get_by_role('button',name='인수인계 완료',exact=True).click();page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-accept').click();page.wait_for_function("requestSelection?.state==='completed'")
     page.locator('#request-detail-close').click();page.get_by_role('button',name='검색 초기화',exact=True).click();page.wait_for_function("document.querySelectorAll('.sent-card').length===5")
     page.evaluate("window.scrollTo({top:0,behavior:'instant'})");page.screenshot(path=str(output/('sent-'+str(width)+'.png')),full_page=True)
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2);self.assertEqual(errors,[]);page.close()
    finally:f.stop()
   browser.close()
