"""Library UI verification with fictional accounts and isolated shared storage."""
import io,os,unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
import export_hwpx
from test_cloud import Fixture,PASSWORD

class LibraryBrowserTests(unittest.TestCase):
 def test_received_file_reuse_into_existing_conversation_and_duplicate_upload(self):
  f=Fixture().start()
  try:
   a=f.login('demo.a');b=f.login('demo.b');doc=f.call('/api/documents',b'Fictional received attachment',a,{'X-File-Name':'received.txt'});draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a);draft['reviewed']=True;draft=f.call('/api/drafts/save',draft,a);rid=f.call('/api/requests/send',{'workspace_id':1,'draft_id':draft['id'],'recipient_employee':'DEMO-B','fingerprint':draft['edit_token']},a)['id'];session=f.call('/api/studio/sessions',{'title':'Recipient separate workspace'},b)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True);page=browser.new_page(viewport={'width':390,'height':950});page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.b');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");page.goto(f.url+'/#files');page.locator('.library-file-table tbody tr').wait_for();row=page.locator('.library-file-table tbody tr');self.assertIn('전달받은 자료',row.inner_text());self.assertEqual(row.get_by_role('button',name='삭제',exact=True).count(),0)
    page.get_by_label('현재 페이지 자료 전체 선택').check();self.assertIn('1개 선택',page.locator('.library-file-filters').inner_text());page.get_by_role('button',name='선택한 자료 연결',exact=True).click();reuse=page.locator('.library-reuse-dialog');reuse.get_by_label('연결 방식',exact=True).select_option('conversation');reuse.get_by_label('연결할 기록',exact=True).select_option(str(session['session']['id']));reuse.get_by_role('button',name='연결하기',exact=True).click();page.wait_for_function("location.hash==='#studio'&&studioData?.documents.some(d=>d.name==='received.txt')");self.assertEqual(page.evaluate('studioData.session.id'),session['session']['id'])
    page.goto(f.url+'/#files');page.locator('.library-file-table').wait_for();page.evaluate('libraryManage.open=true');page.locator('#upload').set_input_files({'name':'renamed.txt','mimeType':'text/plain','buffer':b'Fictional received attachment'});page.locator('#submit').click();page.wait_for_function("state.staged.some(i=>i.reused&&i.status==='success')");self.assertIn('기존 자료 재사용',page.locator('#staged-files').inner_text());self.assertEqual(f.call('/api/requests/'+str(rid),client=b)['state'],'requested');browser.close()
  finally:f.stop()

 def test_table_preview_reuse_tabs_duplicate_delete_and_responsive(self):
  output=Path('artifacts/library-files');output.mkdir(parents=True,exist_ok=True)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path=os.environ.get('TEST_BROWSER',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),headless=True)
   for width in [1440,390]:
    f=Fixture().start()
    try:
     a=f.login('demo.a');doc=f.call('/api/documents',b'Fictional library test text',a,{'X-File-Name':'library.txt'});draft=f.call('/api/drafts/generate',{'document_ids':[doc['id']]},a)
     data=io.BytesIO();pdf=PdfWriter();sheet=pdf.add_blank_page(width=595,height=842);font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')});sheet[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):pdf._add_object(font)})});stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 40 750 Td (Fictional PDF task) Tj ET');sheet[NameObject('/Contents')]=pdf._add_object(stream);pdf.write(data);f.call('/api/documents',data.getvalue(),a,{'X-File-Name':'guide.pdf'})
     book=Workbook();book.active.append(['Monthly task','Owner']);book.active.append(['Supplies','Fictional employee']);data=io.BytesIO();book.save(data);f.call('/api/documents',data.getvalue(),a,{'X-File-Name':'tasks.xlsx'})
     f.call('/api/documents',export_hwpx.build(draft),a,{'X-File-Name':'handover.hwpx'})
     page=browser.new_page(viewport={'width':width,'height':1000},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(f.url+'/login');page.locator('#auth-username').fill('demo.a');page.locator('#auth-password').fill(PASSWORD);page.locator('#auth-submit').click();page.wait_for_function("typeof studioBootReady!=='undefined'&&studioBootReady");page.goto(f.url+'/#files');page.locator('.library-file-table tbody tr').first.wait_for();self.assertEqual(page.locator('.library-file-table tbody tr').count(),4)
     page.locator('#library-format').select_option('pdf');page.wait_for_function("document.querySelectorAll('.library-file-table tbody tr').length===1");page.get_by_role('button',name='미리보기',exact=True).click();preview=page.locator('.library-preview-dialog');preview.wait_for();self.assertEqual(preview.locator('iframe').count(),1)
     with page.expect_download() as download:preview.get_by_role('button',name='원본 다운로드',exact=True).click()
     self.assertTrue(Path(download.value.path()).read_bytes().startswith(b'%PDF'));preview.get_by_role('button',name='추출 본문 보기',exact=True).click();self.assertIn('Fictional PDF task',preview.locator('.source-document').inner_text());preview.get_by_role('button',name='닫기',exact=True).click()
     for fmt,text in [('xlsx','Supplies'),('hwpx',draft['title'])]:
      page.locator('#library-format').select_option(fmt);page.wait_for_function("fmt=>libraryState.data.items.length===1&&libraryState.data.items[0].format===fmt",arg=fmt);page.get_by_role('button',name='미리보기',exact=True).click();preview.wait_for();self.assertIn(text,preview.locator('.source-document').inner_text());preview.get_by_role('button',name='닫기',exact=True).click()
     page.locator('#library-format').select_option('txt');page.wait_for_function("libraryState.data.items.length===1&&libraryState.data.items[0].format==='txt'");page.get_by_role('button',name='연결',exact=True).click();reuse=page.locator('.library-reuse-dialog');reuse.wait_for();reuse.get_by_role('button',name='연결하기',exact=True).click();page.wait_for_function("location.hash==='#studio'&&studioData?.documents.some(d=>d.name==='library.txt')");self.assertEqual(page.evaluate('studioData.draft.id'),draft['id']);self.assertEqual(page.evaluate('studioData.draft.items[0].text'),draft['items'][0]['text'])
     page.goto(f.url+'/#files');page.locator('.library-file-table').wait_for();page.get_by_role('tab',name='AI 작성 대화',exact=True).click();page.locator('.library-card').first.wait_for();page.get_by_role('tab',name='인수인계 문서',exact=True).click();page.locator('.library-card').first.wait_for();page.get_by_role('tab',name='업무자료',exact=True).click();page.locator('.library-file-table').wait_for();page.locator('#library-format').select_option('txt');page.wait_for_function("libraryState.data.items.length===1&&libraryState.data.items[0].format==='txt'");page.get_by_role('button',name='삭제',exact=True).click();confirm=page.locator('#confirm-dialog');confirm.wait_for();self.assertIn('AI 대화 1건',confirm.inner_text());page.locator('#confirm-cancel').click();self.assertEqual(page.locator('.library-file-table tbody tr').count(),1)
     page.locator('#library-format').select_option('all');page.wait_for_function("document.querySelectorAll('.library-file-table tbody tr').length===4");page.screenshot(path=str(output/f'library-{width}.png'),full_page=True);self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+2);self.assertEqual(errors,[]);page.close()
    finally:f.stop()
   browser.close()
