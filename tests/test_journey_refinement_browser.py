"""Five-step browser journey on isolated storage, desktop and mobile."""
import os,unittest,zipfile,io
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD

class JourneyBrowserTests(unittest.TestCase):
 def test_five_steps_save_resume_errors_preview_and_send(self):
  f=Fixture().start()
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
    for width in (1440,390):
     page=browser.new_page(viewport={'width':width,'height':950},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
     page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
     Path('artifacts/journey-refinement').mkdir(parents=True,exist_ok=True)
     def shot(step):
      page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
      page.screenshot(path='artifacts/journey-refinement/step-'+str(step)+'-'+str(width)+'.png',full_page=True)
     page.locator('#journey-start').click();page.locator('#journey-title').fill('Fictional daily task '+str(width))
     page.wait_for_function("!journeyNew&&!titleSaveActive&&!journeyTitleDirty")
     # A failed title save retains the user's input and can be retried.
     page.route('**/api/journey/authoring',lambda r:r.fulfill(status=503,json={'error':'Fixture storage unavailable'}) if r.request.method=='POST' else r.continue_())
     page.locator('#journey-title').fill('Retained fictional task '+str(width))
     page.wait_for_function("document.getElementById('journey-title-status').textContent.includes('실패')")
     self.assertEqual(page.locator('#journey-title').input_value(),'Retained fictional task '+str(width))
     page.unroute('**/api/journey/authoring');page.locator('#journey-prepare').click();page.wait_for_function('!journeyTitleDirty&&!titleSaveActive')
     page.locator('#upload').set_input_files({'name':'fictional.txt','mimeType':'text/plain','buffer':'매월 사무용품 재고와 예산을 점검합니다. 담당자와 일정 확인이 필요합니다.'.encode()})
     page.locator('#submit').click();page.wait_for_function('state.docs.length===1&&!state.busy.size&&stageReady(1)')
     shot(1)
     page.locator('#journey-next').click();page.wait_for_function('journeyStep===2')
     page.locator('#generate').click();page.wait_for_function('!!state.draft&&!state.busy.size')
     self.assertGreater(page.locator('.journey-draft-fold').count(),0)
     page.get_by_role('button',name='모두 펼치기',exact=True).click()
     page.route('**/api/drafts/save',lambda r:r.fulfill(status=503,json={'error':'Fixture save unavailable'}))
     page.locator('#draft-item-0').fill('직접 수정한 인수인계 업무입니다. 월말 재고를 확인합니다.')
     page.wait_for_function("document.getElementById('journey-save-state').textContent.includes('실패')")
     self.assertIn('직접 수정한',page.locator('#draft-item-0').input_value())
     page.unroute('**/api/drafts/save');page.locator('#journey-save').click()
     page.wait_for_function('!state.draftDirty&&!journeySaving')
     shot(2)
     page.locator('#journey-next').click();page.wait_for_function('journeyStep===3')
     page.locator('#journey-gap-check').click();page.wait_for_function('journeyQuestions.some(q=>q.qa_kind==="expected")&&!state.busy.size')
     card=page.locator('.qa-card').first
     card.locator('textarea[aria-label^="예상 답변"]').fill('매월 말일 재고와 잔여 예산을 담당자와 확인합니다.')
     before=page.evaluate('state.draft.items.map(i=>i.text)')
     card.get_by_role('button',name='답변을 문서에 반영',exact=True).click()
     page.locator('#journey-proposal-dialog').wait_for(state='visible')
     target=page.evaluate('journeyProposal.target_index')
     page.locator('#journey-proposal-apply').click();page.locator('#journey-proposal-dialog').wait_for(state='hidden')
     after=page.evaluate('state.draft.items.map(i=>i.text)')
     for i,value in enumerate(before):
      if i!=target:self.assertEqual(after[i],value)
     # Keep an identifiable saved paragraph for the actual HWPX download assertion.
     if target==0:
      page.evaluate("journeyStep=2;paintJourney()")
      page.locator('#draft-item-0').fill('직접 수정한 인수인계 업무입니다. 월말 재고를 확인합니다.')
      page.wait_for_function('!state.draftDirty&&!journeySaving');page.evaluate('journeyStep=3;paintJourney()')
     card=page.locator('.qa-card').first
     card.get_by_role('button',name='해당 없음',exact=True).click();page.wait_for_function('!qaSaving&&journeyQuestions.some(q=>q.state==="not_applicable")')
     page.locator('#qa-review-check').check();page.wait_for_function('stageReady(3)')
     shot(3)
     page.locator('#journey-next').click();page.wait_for_function('journeyStep===4')
     page.route('**/api/directory/employees?*',lambda r:r.fulfill(status=503,json={'error':'Fixture organization temporarily unavailable'}))
     page.locator('#recipient-department').select_option('DEMO-RECEIVE')
     page.wait_for_function("document.getElementById('recipient-summary').textContent.includes('Fixture organization')")
     self.assertEqual(page.locator('#recipient-department').input_value(),'DEMO-RECEIVE')
     page.unroute('**/api/directory/employees?*');page.locator('#recipient-retry').click();page.wait_for_function('recipientOptions.some(p=>p.employee_id==="DEMO-B")')
     page.locator('#recipient-employee').select_option('DEMO-B');self.assertTrue(page.locator('#journey-next').is_disabled())
     page.locator('#journey-confirm-recipient').click();page.wait_for_function('stageReady(4)&&!authoringSaving')
     shot(4)
     page.locator('#journey-save').click();page.wait_for_function('!authoringSaving')
     page.reload();page.wait_for_function('typeof authoringState!=="undefined"&&authoringState?.recipient?.confirmed&&journeyStep===4&&stageReady(4)')
     page.locator('#journey-next').click();page.wait_for_function('journeyStep===5')
     page.locator('#journey-final-reviewed').check();page.wait_for_function('!state.draftDirty&&!journeySaving')
     self.assertFalse(page.locator('#send-handover').is_disabled())
     page.locator('#journey-final').get_by_role('button',name='문서 미리보기',exact=True).click()
     page.locator('.report-preview-dialog').wait_for(state='visible')
     page.wait_for_function('!!reportHash')
     with page.expect_download() as download:page.locator('.report-preview-dialog').get_by_role('button',name='같은 내용 HWPX 다운로드',exact=True).click()
     with zipfile.ZipFile(download.value.path()) as archive:
      self.assertIsNone(archive.testzip());self.assertIn('직접 수정한',archive.read('Contents/section0.xml').decode())
     page.locator('.report-preview-dialog').get_by_role('button',name='닫기',exact=True).click()
     shot(5)
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2)
     page.locator('#send-handover').click();page.locator('#confirm-dialog').wait_for(state='visible')
     page.locator('#confirm-cancel').click();self.assertEqual(page.evaluate('journeyStep'),5)
     page.locator('#send-handover').click();page.locator('#confirm-accept').click()
     page.wait_for_function('location.hash==="#sent"')
     self.assertEqual(errors,[]);page.close()
    browser.close()
  finally:f.stop()
