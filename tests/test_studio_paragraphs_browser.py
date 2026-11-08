import os
import unittest
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD


class ParagraphBrowserTests(unittest.TestCase):
 def test_desktop_mobile_full_pages_selection_approval_cancel_undo_and_download(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');doc=f.call('/api/documents','가상 업무 원문'.encode(),a,{'X-File-Name':'fictional.txt'})
   draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a)
   draft['items'][0]['text']='선택할 첫 문단입니다.\n'+'\n'.join('보존할 문단 %03d: 매월 업무 처리 내역을 확인합니다.'%i for i in range(100))
   draft=f.call('/api/drafts/save',draft,a)
   s=f.call('/api/studio/sessions',{'workspace_id':1,'draft_id':draft['id'],'title':'전체 문서 수정 검증'},a)
   output=Path('artifacts/studio-paragraphs');output.mkdir(parents=True,exist_ok=True)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
    for width in (1440,390):
     page=browser.new_page(viewport={'width':width,'height':1000},accept_downloads=True)
     errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
     page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
     page.goto(f.url+'/#studio');page.wait_for_function("studioData?.draft?.id>0")
     if width<1000:page.get_by_role('button',name='저장된 문서',exact=True).click()
     page.locator('.studio-paper-viewer[data-ready=true]').wait_for()
     frame=page.frame_locator('.studio-paper-frame')
     self.assertGreater(frame.locator('.report-page').count(),2)
     self.assertIn('보존할 문단 099',frame.locator('#pages').inner_text())
     self.assertTrue(page.locator('.studio-paper-scroll').evaluate('e=>e.scrollHeight>e.clientHeight'))
     page.get_by_label('문서 확대 비율').select_option('1.5')
     page.wait_for_function("document.querySelector('.studio-paper-frame').style.width.includes('1215')")
     self.assertEqual(frame.locator('#pages').evaluate('e=>getComputedStyle(e).zoom'),'1.5')
     page.get_by_label('문서 확대 비율').select_option('fit')
     page.get_by_role('button',name='전체 화면',exact=True).click()
     page.wait_for_function("!!document.fullscreenElement||!!document.querySelector('.studio-paper-expanded')")
     page.locator('.studio-paper-toolbar button').last.click()
     page.wait_for_function("!document.fullscreenElement&&!document.querySelector('.studio-paper-expanded')")
     # Click a rendered paragraph, then its explicit action inside the sandboxed frame.
     frame.locator('[data-edit-id]').first.click()
     frame.get_by_role('button',name='AI 수정 요청',exact=True).click()
     page.get_by_role('button',name='더 간결하게',exact=True).click();page.locator('#studio-send').click()
     compare=page.locator('.studio-paragraph-comparison').last
     compare.get_by_role('button',name='수정 반영',exact=True).wait_for()
     self.assertIn('선택할 첫 문단입니다.',compare.inner_text())
     self.assertIn('[모의 수정]',compare.inner_text())
     before=f.call('/api/studio/sessions/'+str(s['session']['id']),client=a)['draft']['items'][0]['text']
     self.assertTrue(before.startswith('선택할 첫 문단입니다.\n'))
     # Cancel first, then request again and explicitly approve.
     compare.get_by_role('button',name='취소',exact=True).click()
     page.get_by_role('button',name='공문서 문체로',exact=True).click();page.locator('#studio-send').click()
     compare=page.locator('.studio-paragraph-comparison').last
     compare.get_by_role('button',name='수정 반영',exact=True).click()
     page.wait_for_function("studioData.draft.items[0].text.startsWith('[모의 수정]')&&!studioBusy")
     after=f.call('/api/studio/sessions/'+str(s['session']['id']),client=a)['draft']['items'][0]['text']
     self.assertEqual(after.split('\n',1)[1],before.split('\n',1)[1])
     if width<1000:page.get_by_role('button',name='저장된 문서',exact=True).click()
     page.locator('.studio-paper-viewer[data-ready=true]').wait_for()
     self.assertIn('[모의 수정]',page.frame_locator('.studio-paper-frame').locator('#pages').inner_text())
     self.assertGreater(page.frame_locator('.studio-paper-frame').locator('.report-page').count(),2)
     page.screenshot(path=str(output/('preview-'+str(width)+'.png')))
     self.assertGreater(page.locator('.studio-paper-frame').bounding_box()['height'],600)
     with page.expect_download() as download:page.locator('#studio-export').click()
     with zipfile.ZipFile(download.value.path()) as z:
      text=z.read('Preview/PrvText.txt').decode();self.assertIn('[모의 수정]',text);self.assertIn('보존할 문단 099',text)
     if width<1000:page.get_by_role('button',name='AI 대화',exact=True).click()
     page.locator('.studio-paragraph-comparison').last.get_by_role('button',name='이 수정 되돌리기',exact=True).click()
     page.wait_for_function("studioData.draft.items[0].text.startsWith('선택할 첫 문단입니다.')&&!studioBusy")
     self.assertEqual(f.call('/api/studio/sessions/'+str(s['session']['id']),client=a)['draft']['items'][0]['text'],before)
     self.assertEqual(errors,[])
     page.close()
    browser.close()
  finally:f.stop()


if __name__=='__main__':unittest.main()
