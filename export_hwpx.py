"""Native HWPX export using python-hwpx's clean document template."""
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import export_docx

# Dependencies are installed inside this workspace, leaving global Python alone.
VENDOR = Path(__file__).resolve().parent / '.vendor'
if VENDOR.is_dir() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


def build(draft):
    try:
        from hwpx import HwpxDocument
    except ImportError:
        raise ValueError('한글 문서 생성 구성요소가 없습니다. 실행하기.cmd를 다시 실행해 설치해 주세요.') from None
    # Reuse the Word export's content order, line breaks, status and references.
    # The output itself is a new HWPX package, not a renamed Word file.
    with zipfile.ZipFile(io.BytesIO(export_docx.build(draft))) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    w = '{' + export_docx.W + '}'
    with HwpxDocument.new() as document:
        for paragraph in root.iter(w + 'p'):
            parts = []
            for node in paragraph.iter():
                if node.tag == w + 't':
                    parts.append(node.text or '')
                elif node.tag == w + 'br':
                    parts.append('\n')
            for line in ''.join(parts).split('\n'):
                document.add_paragraph(line)
        return document.to_bytes()
