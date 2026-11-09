"""관리자 발급과 최초 변경 화면의 PC·모바일 회귀 검사."""
import os, unittest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from test_cloud import Fixture, PASSWORD

class AdminAccountCreationBrowserTests(unittest.TestCase):
    def test_admin_creates_member_and_member_changes_password(self):
        fixture=Fixture().start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files\Google\Chrome\Application\chrome.exe'),headless=True)
                for width in (1440,390):
                    context=browser.new_context(viewport={'width':width,'height':1000})
                    page=context.new_page(); errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(fixture.url+'/login')
                    page.locator('#auth-username').fill('demo.admin');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
                    page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
                    page.goto(fixture.url+'/#accounts')
                    username='judge.browser'+str(width)
                    page.locator('#staff-create-username').fill(username.upper())
                    page.locator('#staff-create-password').fill(PASSWORD)
                    page.locator('#staff-create-form').get_by_role('button',name='새 계정 생성',exact=True).click()
                    expect(page.locator('#staff-account-message')).to_contain_text(username+' 계정을 생성했습니다.')
                    expect(page.locator('#staff-create-password')).to_have_value('')
                    expect(page.locator('#staff-account-list')).to_contain_text(username)
                    output=Path('artifacts/admin-account-creation');output.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(output/('admin-'+str(width)+'.png')),full_page=True)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2)
                    context.close()
                    context=browser.new_context(viewport={'width':width,'height':1000});page=context.new_page()
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(fixture.url+'/login');page.locator('#auth-username').fill(username);page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
                    expect(page.locator('#self-password')).to_be_visible()
                    new='Fictional-Browser-Changed-2026!'
                    page.locator('#self-password').fill(new);page.locator('#self-confirmation').fill(new);page.locator('#self-password-submit').click()
                    expect(page.locator('#auth-username')).to_be_visible()
                    page.locator('#auth-username').fill(username);page.locator('#auth-password').fill(new);page.locator('#auth-submit').click()
                    page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
                    expect(page.locator('#accounts-menu')).to_be_hidden()
                    self.assertEqual(errors,[]);context.close()
                browser.close()
        finally:
            fixture.stop()
