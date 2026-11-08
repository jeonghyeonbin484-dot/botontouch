"""Browser regression on isolated in-memory storage; never uses production data."""
import io
import os
import unittest
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_cloud import Fixture, PASSWORD


class DocumentPreviewBrowserTests(unittest.TestCase):
 def test_saved_document_full_preview_refresh_download_and_responsive_toolbar(self):
  f=Fixture().start()
  try:
   client=f.login('demo.a')
   doc=f.call('/api/documents','가상 업무 점검'.encode(),client,{'X-File-Name':'fictional.txt'})
   draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},client)
   draft['items'][0]['text']='\n'.join('가상 실제 작성 내용 %03d: 업무 처리 절차와 확인 사항을 인계합니다.'%i for i in range(90))
   draft=f.call('/api/drafts/save',draft,client)
   f.call('/api/journey/progress',{'step':5,'draft_id':draft['id']},client)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.goto(f.url+'/login')
    page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
    page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
    page.goto(f.url+'/#journey')
    page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
    page.wait_for_function("state.route==='journey'&&journeyStep===5&&!state.busy.size")
    page.evaluate("id=>{openDraft(state.drafts.find(d=>d.id===id));journeyStep=5;paintJourney();}",draft['id'])
    page.get_by_role('button',name='문서 미리보기',exact=True).last.click()
    frame=page.frame_locator('.report-preview-dialog iframe')
    frame.locator('html[data-ready=true]').wait_for()
    self.assertGreater(frame.locator('.report-page').count(),2)
    self.assertIn('가상 실제 작성 내용 089',frame.locator('body').inner_text())
    self.assertEqual(frame.locator('.report-brand img').count(),2)
    artifacts=Path('artifacts/document-preview');artifacts.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(artifacts/'desktop-preview.png'))
    with page.expect_download() as download:
     page.get_by_role('button',name='같은 내용 HWPX 다운로드').click()
    with zipfile.ZipFile(download.value.path()) as z:
     self.assertIn('가상 실제 작성 내용 089',z.read('Preview/PrvText.txt').decode())
    page.get_by_role('button',name='닫기',exact=True).click()
    page.evaluate("()=>{state.draft.items[0].text='저장 전 최신 수정 내용';state.draftDirty=true;}")
    page.get_by_role('button',name='문서 미리보기',exact=True).last.click()
    frame.locator('html[data-ready=true]').wait_for()
    self.assertIn('저장 전 최신 수정 내용',frame.locator('body').inner_text())
    self.assertNotIn('가상 실제 작성 내용 089',frame.locator('body').inner_text())
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(artifacts/'mobile-preview.png'))
    self.assertIn('저장 전 최신 수정 내용',next(d for d in f.call('/api/drafts',client=client) if d['id']==draft['id'])['items'][0]['text'])
    page.get_by_role('button',name='닫기',exact=True).click()
    page.evaluate("()=>{location.hash='studio';}")
    page.locator('#studio-reset').wait_for(state='visible')
    self.assertEqual(page.locator('.topbar-right #studio-reset').count(),0)
    for width in (1440,712,390):
     page.set_viewport_size({'width':width,'height':900})
     page.wait_for_timeout(150)
     preview=page.locator('#studio-preview-toggle').bounding_box();reset=page.locator('#studio-reset').bounding_box()
     self.assertAlmostEqual(preview['y'],reset['y'],delta=2)
     self.assertGreater(reset['x'],preview['x'])
     self.assertAlmostEqual(preview['height'],reset['height'],delta=1)
     self.assertTrue(page.locator('.sidebar-footer').is_hidden())
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2)
    self.assertEqual(errors,[])
    browser.close()
  finally:f.stop()


if __name__=='__main__':unittest.main()
