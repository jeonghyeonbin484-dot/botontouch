"""Isolated desktop/mobile preview editing and approval contracts."""
import os,unittest,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_cloud import Fixture,PASSWORD

class StudioEditingUXTests(unittest.TestCase):
 def test_splitter_fullscreen_approval_and_document_switch(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');doc=f.call('/api/documents','가상 월간 재고 확인 자료'.encode(),a,{'X-File-Name':'fixture.txt'})
   draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a)
   draft['items'][0]['text']='선택할 첫 문장입니다.\n변경하지 않을 다음 문단입니다.';draft=f.call('/api/drafts/save',draft,a)
   s=f.call('/api/studio/sessions',{'workspace_id':1,'draft_id':draft['id'],'title':'첫 번째 문서'},a)
   other=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a)
   second=f.call('/api/studio/sessions',{'workspace_id':1,'draft_id':other['id'],'title':'다른 문서'},a)
   empty=f.call('/api/studio/sessions',{'title':'자료 없는 새 업무'},a)
   output=Path('artifacts/studio-editing-ux');output.mkdir(parents=True,exist_ok=True)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
    for width in (1440,390):
     page=browser.new_page(viewport={'width':width,'height':950},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click()
     page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady")
     page.goto(f.url+'/#studio');page.wait_for_function('!!studioData&&!studioBusy')
     page.locator('#studio-sessions').select_option(str(empty['session']['id']));page.wait_for_function('(sid)=>studioData?.session.id===sid&&!studioBusy',arg=empty['session']['id'])
     self.assertIn('업무자료를 첨부하거나',page.locator('.studio-greeting').inner_text())
     self.assertLess(page.locator('.studio-chat').bounding_box()['height'],620)
     page.locator('#studio-sessions').select_option(str(s['session']['id']));page.wait_for_function('(sid)=>studioData?.session.id===sid&&!studioBusy',arg=s['session']['id'])
     self.assertTrue(page.locator('.studio-paragraph-selection').is_hidden())
     if width>1000:self.assertIn('자료 1개가 연결되어 있습니다.',page.locator('.studio-greeting').inner_text())
     if width>1000:
      splitter=page.get_by_role('separator',name='AI 대화와 문서 너비 조절');box=splitter.bounding_box();old=page.locator('.studio-chat').bounding_box()['width']
      page.mouse.move(box['x']+box['width']/2,box['y']+80);page.mouse.down();page.mouse.move(box['x']+90,box['y']+80,steps=8);page.mouse.up()
      self.assertGreater(page.locator('.studio-chat').bounding_box()['width'],old+40)
      splitter.focus();page.keyboard.press('ArrowLeft');ratio=page.evaluate('studioSplitRatio')
      page.reload();page.wait_for_function('(value)=>!!studioData&&!studioBusy&&studioSplitOwner===studioSplitKey()&&Math.abs(studioSplitRatio-value)<.1',arg=ratio);self.assertAlmostEqual(page.evaluate('studioSplitRatio'),ratio,delta=.1)
      page.locator('#studio-sessions').select_option(str(s['session']['id']));page.wait_for_function('(sid)=>studioData?.session.id===sid&&!studioBusy',arg=s['session']['id'])
     else:
      self.assertTrue(page.get_by_role('separator',name='AI 대화와 문서 너비 조절').is_hidden())
      page.get_by_role('button',name='저장된 문서',exact=True).click()
     page.locator('.studio-paper-viewer[data-ready=true]').wait_for()
     page.get_by_role('button',name='전체 화면',exact=True).click()
     frame=page.frame_locator('.studio-paper-frame');frame.locator('[data-edit-id]').first.click()
     action=frame.get_by_role('button',name='AI 수정 요청',exact=True);self.assertTrue(action.is_visible());action.click()
     panel=page.locator('.studio-expanded-editor');panel.get_by_label('전체 화면 AI 수정 지시').wait_for()
     self.assertTrue(page.locator('.studio-paper-expanded').is_visible())
     before=f.call('/api/studio/sessions/'+str(s['session']['id']),client=a)['draft']['items'][0]['text']
     panel.get_by_label('전체 화면 AI 수정 지시').fill('더 간결하게');panel.get_by_role('button',name='AI 수정 요청',exact=True).click()
     panel.get_by_role('button',name='수정 반영',exact=True).wait_for()
     self.assertEqual(f.call('/api/studio/sessions/'+str(s['session']['id']),client=a)['draft']['items'][0]['text'],before)
     panel.get_by_role('button',name='취소',exact=True).click();page.wait_for_function('!studioBusy')
     panel.get_by_label('전체 화면 AI 수정 지시').fill('공문서 문체로');panel.get_by_role('button',name='AI 수정 요청',exact=True).click()
     panel.get_by_role('button',name='수정 반영',exact=True).wait_for()
     page.screenshot(path=str(output/('compare-'+str(width)+'.png')))
     panel.get_by_role('button',name='수정 반영',exact=True).click();page.wait_for_function('!studioBusy&&studioData.draft.items[0].text.startsWith("[모의 수정]")')
     self.assertTrue(page.locator('.studio-paper-expanded').is_visible());page.locator('.studio-paper-viewer[data-ready=true]').wait_for()
     self.assertIn('[모의 수정]',frame.locator('#pages').inner_text())
     after=f.call('/api/studio/sessions/'+str(s['session']['id']),client=a)['draft']['items'][0]['text'];self.assertEqual(after.split('\n',1)[1],before.split('\n',1)[1])
     page.get_by_role('button',name='전체 화면 종료',exact=True).click()
     self.assertTrue(page.locator('.studio-paragraph-selection').is_hidden())
     with page.expect_download() as result:page.locator('#studio-export').click()
     with zipfile.ZipFile(result.value.path()) as archive:self.assertIn('[모의 수정]',archive.read('Preview/PrvText.txt').decode())
     frame.locator('[data-edit-id]').first.click();frame.get_by_role('button',name='AI 수정 요청',exact=True).click()
     self.assertFalse(page.locator('.studio-paragraph-selection').is_hidden())
     page.locator('#studio-input').fill('선택한 문장에만 적용할 지시')
     page.locator('#studio-sessions').select_option(str(second['session']['id']));page.wait_for_function('(sid)=>studioData?.session.id===sid&&!studioBusy',arg=second['session']['id'])
     self.assertIsNone(page.evaluate('studioParagraphSelection'));self.assertTrue(page.locator('.studio-paragraph-selection').is_hidden())
     self.assertEqual(page.locator('#studio-input').input_value(),'')
     self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2);self.assertEqual(errors,[])
     # Restore the fixture before the second viewport run.
     page.locator('#studio-sessions').select_option(str(s['session']['id']));page.wait_for_function('(sid)=>studioData?.session.id===sid&&!studioBusy',arg=s['session']['id'])
     if width<1000:page.get_by_role('button',name='AI 대화',exact=True).click()
     page.locator('.studio-paragraph-comparison').last.get_by_role('button',name='이 수정 되돌리기',exact=True).click();page.wait_for_function('!studioBusy&&!studioData.draft.items[0].text.startsWith("[모의 수정]")')
     page.close()
    browser.close()
  finally:f.stop()
