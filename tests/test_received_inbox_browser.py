"""PC/mobile recipient workflow against fictional isolated shared data."""
import os,unittest,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD

class ReceivedInboxBrowserTests(unittest.TestCase):
 def test_counts_snapshot_preview_chat_questions_and_completion(self):
  output=Path('artifacts/received-inbox');output.mkdir(parents=True,exist_ok=True)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
   for width in (1440,390):
    f=Fixture().start()
    try:
     a=f.login('demo.a');b=f.login('demo.b');doc=f.call('/api/documents','전달 당시 월간 점검 원문'.encode(),a,{'X-File-Name':'fictional.txt'});requests=[]
     for title in ('월간 사업 인수인계','완료된 예산 업무','검토 중 시설 업무'):
      d=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);d.update(title=title,reviewed=True);d=f.call('/api/drafts/save',d,a)
      rid=f.call('/api/requests/send',{'workspace_id':1,'draft_id':d['id'],'fingerprint':d['edit_token'],'recipient_employee':'DEMO-B'},a)['id'];requests.append((rid,d))
     rid,d=requests[0]
     f.call('/api/requests/action',{'id':requests[1][0],'revision':1,'action':'accept'},b);f.call('/api/requests/action',{'id':requests[1][0],'revision':1,'action':'complete'},a)
     f.call('/api/requests/action',{'id':requests[2][0],'revision':1,'action':'view'},b)
     f.call('/api/journey/question',{'request_id':rid,'question':'월간 보고일은 언제인가요?'},b)
     page=browser.new_page(viewport={'width':width,'height':1000},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.b');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
     page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
     page.goto(f.url+'/#inbox');page.locator('.received-card').first.wait_for();page.wait_for_function("document.querySelector('.received-summary').textContent.includes('전체 3건')")
     self.assertEqual(page.locator('#nav-inbox-count').inner_text(),'1');self.assertEqual(page.locator('.received-count strong').all_inner_texts(),['1','2','3'])
     self.assertEqual(page.locator('.received-card').count(),3)
     page.locator('#inbox-query').fill('월간');page.wait_for_function("document.querySelectorAll('.received-card').length===1")
     card=page.locator('.received-card');self.assertIn('인계자',card.inner_text());self.assertIn('가상 인계자',card.inner_text());self.assertIn('가상 인수자',card.inner_text());self.assertIn('미답변 추가 질문',card.inner_text());self.assertEqual(card.locator('.received-progress li').count(),5)
     card.get_by_role('button',name='대화하기',exact=True).click();page.locator('.handover-chat').wait_for(state='visible')
     page.locator('.handover-chat').get_by_label('대화 메시지').fill('문서를 검토하겠습니다.');page.locator('.handover-chat').get_by_role('button',name='보내기',exact=True).click()
     page.wait_for_function("[...chatMessages.values()].some(m=>m.body==='문서를 검토하겠습니다.')")
     page.locator('.handover-chat').get_by_role('button',name='닫기',exact=True).click();self.assertEqual(page.locator('#nav-inbox-count').inner_text(),'1')
     card.get_by_role('button',name='인수인계서 확인',exact=True).click();page.locator('.report-preview-dialog').wait_for(state='visible')
     frame=page.frame_locator('.report-preview-dialog iframe');frame.locator('html[data-ready=true]').wait_for();self.assertIn('월간 사업 인수인계',frame.locator('#pages').inner_text());self.assertGreater(frame.locator('.report-brand img').count(),0)
     with page.expect_download() as result:page.locator('.report-preview-dialog').get_by_role('button',name='같은 내용 HWPX 다운로드',exact=True).click()
     with zipfile.ZipFile(result.value.path()) as archive:self.assertIn('월간 사업 인수인계',archive.read('Preview/PrvText.txt').decode())
     page.locator('.report-preview-dialog').get_by_role('button',name='닫기',exact=True).click();page.wait_for_function("document.getElementById('nav-inbox-count').textContent==='0'")
     self.assertTrue(page.locator('.received-overview').get_by_role('button',name='답변 확인 완료',exact=True).is_disabled())
     page.get_by_label('인계자에게 추가 질문').fill('월말에 확인할 담당자는 누구인가요?');page.get_by_role('button',name='추가 질문 보내기',exact=True).click()
     page.wait_for_function('requestSelection.question_count===2')
     for q in f.call('/api/journey/questions?request_id='+str(rid),client=a)['questions']:
      f.call('/api/journey/answer',{'request_id':rid,'id':q['id'],'reply':'월말 담당자와 일정표를 확인하세요.','state':'resolved'},a)
     page.locator('#reload-requests').click();page.wait_for_function('requestSelection?.unanswered_count===0&&receiptDisplayedTokens.get(requestSelection.id)?.token===requestSelection.answer_token')
     page.locator('.received-overview').get_by_role('button',name='답변 확인 완료',exact=True).click();page.wait_for_function('requestSelection.answers_reviewed')
     page.get_by_role('button',name='인수 수락',exact=True).click();page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-accept').click();page.wait_for_function("requestSelection.state==='accepted'")
     self.assertIn('인계자가 최종 완료',page.locator('.received-detail-guide').inner_text())
     f.call('/api/requests/action',{'id':rid,'revision':1,'action':'complete'},a);page.locator('#reload-requests').click();page.wait_for_function("requestSelection.state==='completed'")
     page.locator('#request-detail-close').click();page.locator('#inbox-query').fill('');page.locator('#inbox-status').select_option('completed');page.wait_for_function("document.querySelectorAll('.received-card').length===2")
     self.assertEqual(page.locator('#nav-inbox-count').inner_text(),'0');self.assertIn('전체 3건',page.locator('.received-summary').inner_text())
     page.evaluate("window.scrollTo({top:0,behavior:'instant'})");page.screenshot(path=str(output/('inbox-'+str(width)+'.png')),full_page=True)
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2);self.assertEqual(errors,[]);page.close()
    finally:f.stop()
   browser.close()
