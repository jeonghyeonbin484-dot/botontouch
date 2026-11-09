"""PDF and XLSX extraction with stable page/sheet/row citations."""
import io
import zipfile


def pdf_sources(raw):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError('PDF 구성요소가 없습니다. 실행하기.cmd를 다시 실행해 주세요.') from None
    try:
        # Some parser warnings include raw file prefixes; do not write document bytes to logs.
        import logging
        logging.getLogger('pypdf').setLevel(logging.CRITICAL)
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('암호화 PDF는 지원하지 않습니다. 암호를 해제한 파일을 등록해 주세요.')
        if len(reader.pages) > 300:
            raise ValueError('PDF는 300페이지 이내로 나누어 등록해 주세요.')
        sources = []
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or '').strip()
            if text:
                sources.append({'location': f'{number}페이지', 'text': text})
        if not sources:
            raise ValueError('PDF에서 글자를 읽지 못했습니다. 스캔·이미지 PDF의 문자 인식(OCR)은 아직 지원하지 않습니다.')
        empty = len(reader.pages) - len(sources)
        if empty:
            sources.append({'location': '추출 안내', 'text': f'[시스템 안내] 총 {len(reader.pages)}페이지 중 {empty}페이지에서 글자를 추출하지 못했습니다. 해당 페이지에 필요한 내용이 없는지 원본을 확인하세요.'})
        return sources
    except ValueError:
        raise
    except Exception:
        raise ValueError('PDF를 읽지 못했습니다. 파일 손상과 형식을 확인해 주세요.') from None


def xlsx_sources(raw):
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ValueError('엑셀 구성요소가 없습니다. 실행하기.cmd를 다시 실행해 주세요.') from None
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 40 * 1024 * 1024:
                raise ValueError('엑셀 압축 해제 크기가 40MB를 초과합니다.')
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
        try:
            sources, cells = [], 0
            for sheet in workbook.worksheets:
                if sheet.sheet_state != 'visible':
                    continue
                if sheet.max_row and sheet.max_row > 20000 or sheet.max_column and sheet.max_column > 500:
                    raise ValueError('엑셀은 시트당 2만 행·500열 이내로 나누어 등록해 주세요.')
                for row_number, row in enumerate(sheet.iter_rows(), 1):
                    cells += len(row)
                    if cells > 200000:
                        raise ValueError('엑셀은 전체 20만 셀 이내로 나누어 등록해 주세요.')
                    values = []
                    for cell in row:
                        if cell.value is None:
                            continue
                        value = str(cell.value)
                        if cell.data_type == 'f':
                            value = '[수식·계산 안 함] ' + value
                        values.append(f'{cell.column_letter}: {value}')
                    if values:
                        sources.append({'location': f'{sheet.title} · {row_number}행', 'text': ' | '.join(values)})
            if not sources:
                raise ValueError('엑셀의 표시된 시트에서 읽을 수 있는 셀이 없습니다.')
            return sources
        finally:
            workbook.close()
    except ValueError:
        raise
    except Exception:
        raise ValueError('XLSX를 읽지 못했습니다. 암호·파일 손상·형식을 확인해 주세요. 구형 XLS는 지원하지 않습니다.') from None
