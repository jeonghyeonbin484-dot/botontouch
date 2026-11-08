from pathlib import Path
import hashlib,json,shutil
import win32com.client
root=Path.cwd(); folder=root/'public/media';folder.mkdir(parents=True,exist_ok=True)
source=root/'templates/namyangju-report.hwpx';target=folder/'namyangju-template.pdf'
app=win32com.client.DispatchEx('HWPFrame.HwpObject')
try:
 app.XHwpWindows.Item(0).Visible=False
 assert app.Open(str(source.resolve()),'HWPX','')
 pages=app.PageCount
 assert app.SaveAs(str(target.resolve()),'PDF','')
finally:app.Clear(1);app.Quit()
shutil.copy2(source,folder/'namyangju-template.hwpx')
manifest={'source':'templates/namyangju-report.hwpx','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pdf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'pages':pages,'converter':'한컴오피스 HWPFrame.HwpObject PDF 저장','notice':'저장소에 포함된 보고서 서식 참고용 원본입니다. 저장된 인수인계서 본문 미리보기와 다릅니다.'}
(folder/'namyangju-template-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('원본 HWPX 한컴 PDF 변환 완료',pages,'쪽',target.stat().st_size,'bytes')
