"""등록 자료의 텍스트와 출처 위치를 추출한다."""
import io,zipfile,re
import xml.etree.ElementTree as ET
from pathlib import Path
from batontouch.materials import office_extraction as extract_office
def extract_document_text(name, raw):
    suffix = Path(name).suffix.lower()
    if not raw:
        raise ValueError('빈 파일입니다.')
    if suffix == '.txt':
        for encoding in ('utf-8-sig', 'cp949'):
            try:
                content = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        else:
            raise ValueError('텍스트 인코딩을 읽을 수 없습니다. UTF-8로 저장해 주세요.')
        if '\x00' in content:
            raise ValueError('일반 텍스트 파일이 아닙니다.')
        sources = [{'location': f'{i}행', 'text': line} for i, line in enumerate(content.splitlines(), 1) if line.strip()]
    elif suffix == '.hwpx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                    raise ValueError('압축 해제 크기가 40MB를 초과합니다.')
                sections = sorted(n for n in archive.namelist() if n.startswith('Contents/section') and n.endswith('.xml'))
                sources = []
                for section in sections:
                    root = ET.fromstring(archive.read(section))
                    count = 0
                    for paragraph in root.iter():
                        if paragraph.tag.rsplit('}', 1)[-1] != 'p':
                            continue
                        # Nested table paragraphs are extracted separately, without duplication.
                        if any(child is not paragraph and child.tag.rsplit('}', 1)[-1] == 'p' for child in paragraph.iter()):
                            continue
                        text = ''.join(t.text or '' for t in paragraph.iter() if t.tag.rsplit('}', 1)[-1] == 't').strip()
                        if text:
                            count += 1
                            sources.append({'location': f'{Path(section).stem} · {count}문단', 'text': text})
        except (zipfile.BadZipFile, ET.ParseError, RuntimeError, KeyError):
            raise ValueError('HWPX를 읽지 못했습니다. 암호화 여부와 파일 형식을 확인해 주세요.')
    elif suffix == '.pdf':
        sources = extract_office.pdf_sources(raw)
    elif suffix == '.xlsx':
        sources = extract_office.xlsx_sources(raw)
    else:
        raise ValueError('TXT·HWPX·텍스트 PDF·XLSX를 지원합니다. HWP·XLS·XLSM은 지원하지 않습니다.')
    if not sources:
        raise ValueError('추출 가능한 본문이 없습니다. 이미지 안의 글자는 지원하지 않습니다.')
    return '\n'.join(s['text'] for s in sources), sources
