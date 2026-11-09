import os
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright
import export_hwpx
import report_content
import report_document
from test_hwpx_revised_format import example_draft, LONG_BODY, LONG_PLAN


class RevisedPreviewBrowserTests(unittest.TestCase):
 def test_revised_preview_pages_bullets_and_two_line_body(self):
  draft=example_draft();model=export_hwpx.output_model(draft)
  output=Path('artifacts/revised-hwpx');output.mkdir(parents=True,exist_ok=True)
  html=report_document.html_document(model)
  (output/'revised-preview.html').write_text(html,encoding='utf-8')
  (output/'revised-handover.hwpx').write_bytes(export_hwpx.build(draft))
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
   page=browser.new_page(viewport={'width':1150,'height':1000})
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.set_content(html);page.locator('html[data-ready=true]').wait_for()
   self.assertEqual(page.locator('h2 span').all_text_contents(),list(map(str,range(1,7))))
   for original in (LONG_BODY,LONG_PLAN):
    for brief in report_content.concise_bullets(original):
     paragraph=page.get_by_text('○ '+brief,exact=True)
     lines=paragraph.evaluate("e=>e.getBoundingClientRect().height/parseFloat(getComputedStyle(e).lineHeight)")
     self.assertLessEqual(lines,2.05,brief)
   text=page.locator('body').inner_text()
   for removed in ('관련 문서 및 참고자료','인계자·인수자 확인','업무 인계·인수 요약서'):
    self.assertNotIn(removed,text)
   question=page.get_by_text('1. 매월 초 해야 할 업무는?',exact=True)
   self.assertEqual(question.evaluate('e=>e.nextElementSibling.textContent'),'- 확인 필요: 전월분 초과근무 내역을 취합·점검합니다.')
   page.screenshot(path=str(output/'revised-body.png'))
   page.locator('.report-page').last.scroll_into_view_if_needed()
   page.screenshot(path=str(output/'revised-questions.png'))
   self.assertEqual(errors,[])
   browser.close()


if __name__=='__main__':unittest.main()
