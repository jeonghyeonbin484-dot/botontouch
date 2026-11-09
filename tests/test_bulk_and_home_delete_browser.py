"""실제 Chrome에서 전체 선택·취소·삭제와 홈 초안 삭제를 검증한다."""
import unittest,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from test_cloud import Fixture,PASSWORD

class BulkAndHomeDeleteBrowserTests(unittest.TestCase):
 def test_across_pages_select_cancel_delete_and_home_draft_delete(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');documents=[]
   for index in range(23):documents.append(f.call('/api/documents',('Fictional drone task '+str(index)).encode(),a,{'X-File-Name':'fictional-'+str(index)+'.txt'}))
   draft=f.call('/api/drafts/generate',{'document_ids':[documents[0]['id']]},a);draft['title']='삭제 확인용 가상 초안';draft=f.call('/api/drafts/save',draft,a)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files\Google\Chrome\Application\chrome.exe'),headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
    page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
    page.goto(f.url+'/#files');expect(page.locator('.library-file-table tbody tr')).to_have_count(20)
    page.locator('#library-select-all-results').click();expect(page.locator('#library-file-filters')).to_contain_text('23개 선택')
    page.locator('#library-delete-selected').click();page.locator('#confirm-dialog').wait_for(state='visible')
    page.locator('#confirm-cancel').click();self.assertEqual(f.call('/api/library',client=a)['total'],23)
    page.locator('#library-delete-selected').click();page.locator('#confirm-dialog').wait_for(state='visible')
    output=Path('artifacts/bulk-and-home-delete');output.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(output/'bulk-confirm.png'),full_page=True)
    page.locator('#confirm-accept').click();expect(page.locator('.library-file-table')).to_have_count(0)
    self.assertEqual(f.call('/api/library',client=a)['total'],0)
    page.goto(f.url+'/#home');card=page.locator('#journey-dashboard-drafts .workbench-card').filter(has_text='삭제 확인용 가상 초안')
    expect(card).to_have_count(1);card.get_by_role('button',name='삭제 확인용 가상 초안 삭제',exact=True).click()
    page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-cancel').click();expect(card).to_have_count(1)
    card.get_by_role('button',name='삭제 확인용 가상 초안 삭제',exact=True).click();page.locator('#confirm-dialog').wait_for(state='visible');page.screenshot(path=str(output/'home-confirm.png'),full_page=True);page.locator('#confirm-accept').click()
    expect(card).to_have_count(0);self.assertEqual(f.call('/api/workbench',client=a)['counts']['drafts'],0)
    page.reload();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");expect(page.locator('#journey-dashboard-drafts .workbench-card')).to_have_count(0)
    page.set_viewport_size({'width':390,'height':900});page.goto(f.url+'/#files');expect(page.locator('#library-select-all-results')).to_be_visible();self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),392)
    self.assertEqual(errors,[]);browser.close()
  finally:f.stop()

 def test_home_select_all_includes_drafts_beyond_visible_five(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');doc=f.call('/api/documents',b'Fictional drone work',a,{'X-File-Name':'fictional.txt'})
   for index in range(9):
    draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);draft['title']='가상 인수인계 '+str(index);f.call('/api/drafts/save',draft,a)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files\Google\Chrome\Application\chrome.exe'),headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
    page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
    boxes=page.locator('#journey-dashboard-drafts input[type=checkbox]');expect(boxes).to_have_count(5)
    boxes.first.check();expect(page.locator('#workbench-draft-selection')).to_contain_text('1개 선택')
    page.locator('#workbench-select-all-drafts').click();expect(page.locator('#workbench-draft-selection')).to_contain_text('9개 선택')
    page.locator('#workbench-draft-selection').get_by_role('button',name='선택 해제',exact=True).click();expect(page.locator('#workbench-delete-selected-drafts')).to_be_disabled()
    page.set_viewport_size({'width':390,'height':900});page.locator('#workbench-select-all-drafts').click();expect(page.locator('#workbench-draft-selection')).to_contain_text('9개 선택')
    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),392)
    page.locator('#workbench-delete-selected-drafts').click();page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-cancel').click()
    self.assertEqual(f.call('/api/workbench',client=a)['counts']['drafts'],9)
    page.locator('#workbench-delete-selected-drafts').click();page.locator('#confirm-dialog').wait_for(state='visible')
    output=Path('artifacts/bulk-and-home-delete');output.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(output/'home-bulk-confirm-mobile.png'),full_page=True)
    page.locator('#confirm-accept').click();expect(page.locator('#journey-dashboard-drafts .workbench-card')).to_have_count(0)
    self.assertEqual(f.call('/api/workbench',client=a)['counts']['drafts'],0)
    page.reload();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");expect(page.locator('#journey-dashboard-drafts .workbench-card')).to_have_count(0)
    self.assertEqual(errors,[]);browser.close()
  finally:f.stop()
