from pathlib import Path
import hashlib,json
def validate(root):
 root=Path(root);folder=root/'public/media';m=json.loads((folder/'namyangju-template-manifest.json').read_text(encoding='utf-8'))
 for path,key in [(root/'templates/namyangju-report.hwpx','source_sha256'),(folder/'namyangju-template.pdf','pdf_sha256')]:
  if hashlib.sha256(path.read_bytes()).hexdigest()!=m[key]:raise ValueError('서식 원본과 미리보기 PDF가 일치하지 않습니다. 원본 기준 PDF를 다시 생성하세요.')
 if (root/'templates/namyangju-report.hwpx').read_bytes()!=(folder/'namyangju-template.hwpx').read_bytes():raise ValueError('원본 다운로드 파일을 함께 갱신하세요.')
 return m
