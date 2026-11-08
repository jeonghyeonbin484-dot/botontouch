import os
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD


class WorkbenchBrowserTests(unittest.TestCase):
 def test_daily_work_desktop_mobile_sidebar_search_notifications(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');doc=f.call('/api/documents','가상 원문 보존'.encode(),a,{'X-File-Name':'fictional.txt'})
   drafts=[]
   for title in ('가. 월간 점검','나. 인수 요청 문서'):
    d=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);d.update(title=title,reviewed=True);drafts.append(f.call('/api/drafts/save',d,a))
   f.call('/api/requests/send',{'workspace_id':1,'draft_id':drafts[1]['id'],'fingerprint':drafts[1]['edit_token'],'recipient_employee':'DEMO-B'},a)
   output=Path('artifacts/workbench');output.mkdir(parents=True,exist_ok=True)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
    for width in (1440,390):
     page=browser.new_page(viewport={'width':width,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
     page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
     page.locator('#workbench-results .workbench-card').first.wait_for()
     self.assertLess(page.locator('.workbench-intro').bounding_box()['height'],260)
     self.assertGreater(page.locator('#journey-dashboard-drafts .workbench-card').count(),0)
     self.assertEqual(page.locator('#workbench-results .workbench-progress').first.locator('li').count(),7)
     if width>800:
      page.get_by_role('button',name='사이드바 접기',exact=True).click()
      self.assertAlmostEqual(page.locator('#sidebar').bounding_box()['width'],76,delta=1)
      page.reload();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
      page.get_by_role('button',name='사이드바 펼치기',exact=True).click()
      page.set_viewport_size({'width':1440,'height':440})
      self.assertTrue(page.locator('.sidebar-scroll').evaluate('e=>e.scrollHeight>e.clientHeight'))
      page.locator('.sidebar-guide-link').last.scroll_into_view_if_needed()
      self.assertTrue(page.locator('.sidebar-guide-link').last.is_visible())
      page.set_viewport_size({'width':1440,'height':900})
     else:
      page.locator('#menu-toggle').click()
      page.screenshot(path=str(output/'mobile-menu.png'))
      page.locator('.sidebar-mobile-close').click()
      self.assertFalse(page.locator('#sidebar').evaluate('e=>e.classList.contains("open")'))
     page.locator('#workbench-query').fill('월간');page.locator('#workbench-search-form').get_by_role('button',name='검색',exact=True).click()
     page.wait_for_function("document.getElementById('workbench-summary').textContent.includes('1건')")
     self.assertEqual(page.locator('#workbench-results .workbench-card').count(),1)
     page.locator('#workbench-status').select_option('completed')
     page.wait_for_function("document.getElementById('workbench-summary').textContent.includes('0건')")
     page.locator('#workbench-reset').click()
     page.locator('#workbench-bell').click();page.locator('.workbench-notification-row').first.wait_for()
     page.get_by_role('button',name='모두 읽음',exact=True).click()
     page.wait_for_function("document.querySelector('#workbench-bell .badge').hidden")
     page.locator('#workbench-notifications').get_by_role('button',name='닫기',exact=True).click()
     self.assertNotIn('로컬 서버 연결됨',page.locator('body').inner_text())
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2)
     page.screenshot(path=str(output/('home-'+str(width)+'.png')))
     page.evaluate("location.hash='files'")
     page.locator('#library-tab-drafts').click();page.locator('#library-status-field').wait_for()
     page.locator('#library-status').select_option('draft')
     page.wait_for_function("document.getElementById('library-result-count').textContent.includes('총 0건')")
     page.locator('#library-reset').click()
     page.wait_for_function("document.getElementById('library-result-count').textContent.includes('총 2건')")
     self.assertEqual(errors,[])
     page.close()
    # Another user receives the request and keeps their own unread state.
    page=browser.new_page(viewport={'width':390,'height':844})
    page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.b');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
    page.locator('#workbench-received .workbench-card').first.wait_for()
    page.locator('#workbench-bell').click();page.locator('.workbench-notification-row').first.click()
    page.locator('#request-detail-panel').wait_for()
    self.assertIn('나. 인수 요청 문서',page.locator('#request-detail-panel').inner_text())
    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),392)
    browser.close()
  finally:f.stop()


if __name__=='__main__':unittest.main()
