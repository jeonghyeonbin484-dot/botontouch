import unittest,os
from playwright.sync_api import sync_playwright,expect
from test_cloud import PASSWORD
from test_sent_delete import SentDeleteTests
class SentDeleteBrowserTests(unittest.TestCase):
 def test_select_cancel_single_and_bulk_hide(self):
  fixture=SentDeleteTests();fixture.setUp();f=fixture.f
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files\Google\Chrome\Application\chrome.exe'),headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");page.goto(f.url+'/#sent')
    expect(page.locator('.sent-card')).to_have_count(3);page.locator('#sent-select-all').click();expect(page.locator('#sent-delete-tools')).to_contain_text('3개 선택')
    page.locator('#sent-delete-selected').click();page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-cancel').click();expect(page.locator('.sent-card')).to_have_count(3)
    page.locator('.sent-card').first.get_by_role('button',name='삭제',exact=True).click();page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-accept').click();expect(page.locator('.sent-card')).to_have_count(2)
    page.set_viewport_size({'width':390,'height':900});page.locator('#sent-select-all').click();expect(page.locator('#sent-delete-tools')).to_contain_text('2개 선택');page.locator('#sent-delete-selected').click();page.locator('#confirm-dialog').wait_for(state='visible');page.locator('#confirm-accept').click();expect(page.locator('.sent-card')).to_have_count(0)
    page.reload();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");expect(page.locator('.sent-card')).to_have_count(0)
    self.assertEqual(f.call('/api/requests?box=received',client=fixture.b)['total'],3);self.assertEqual(errors,[]);browser.close()
  finally:fixture.tearDown()
