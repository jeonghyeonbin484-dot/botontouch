"""Create a minimal, genuine Office Open XML Word document."""
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ET.register_namespace('w', W)


def build(draft):
    root = ET.Element(f'{{{W}}}document')
    body = ET.SubElement(root, f'{{{W}}}body')

    def paragraph(text, bold=False, size=22):
        # PDF/HWPX text may contain control characters forbidden by XML 1.0.
        text = ''.join(c for c in str(text) if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
        p = ET.SubElement(body, f'{{{W}}}p')
        run = ET.SubElement(p, f'{{{W}}}r')
        props = ET.SubElement(run, f'{{{W}}}rPr')
        ET.SubElement(props, f'{{{W}}}rFonts', {f'{{{W}}}ascii': 'Malgun Gothic', f'{{{W}}}eastAsia': '맑은 고딕'})
        ET.SubElement(props, f'{{{W}}}sz', {f'{{{W}}}val': str(size)})
        if bold:
            ET.SubElement(props, f'{{{W}}}b')
        for index, line in enumerate(str(text).split('\n')):
            if index:
                ET.SubElement(run, f'{{{W}}}br')
            ET.SubElement(run, f'{{{W}}}t', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'}).text = line

    paragraph(draft['title'], True, 34)
    if draft.get('workspace'):
        workspace = draft['workspace']
        for label, key in [('업무명', 'title'), ('부서', 'department'), ('전임자', 'predecessor'), ('후임자', 'successor'), ('인수인계 기준일', 'reference_date')]:
            paragraph(label + ': ' + (workspace.get(key) or '미입력'))
    paragraph('검토 상태: ' + ('사용자 검토 완료' if draft.get('reviewed') else '미검토 · AI 초안'))
    if draft.get('recipient_review'):
        review=draft['recipient_review']
        info=draft.get('version_info',{})
        if info:paragraph(f"확정본 v{info['revision']} / 확정자: {info['actor']} / 한국 시간: {info['finalized_kst']}")
        paragraph(f"확정 당시 후임자 확인: {review['confirmed']}/{len(review['items'])}항목 완료")
        paragraph('이 문서는 확정 당시의 내용·업무 정보·할 일·인수 확인을 보관한 스냅샷입니다.')
        statuses={'confirmed':'확인 완료','needs_info':'추가 설명 필요','pending':'미확인','outdated':'내용 변경 · 재확인 필요'}
        for item in review['items']:
            paragraph(item['category']+': '+statuses.get(item['state'],item['state']))
            if item.get('record'):
                paragraph('확인자: '+item['record']['actor']+' / 메모: '+item['record'].get('note',''))
        for question in review['followups']:
            paragraph('추가 질문 ('+('답변 완료' if question['state']=='resolved' else '미해결')+'): '+question['question'])
            if question.get('reply'):paragraph('보완 답변: '+question['reply'])
    if draft.get('source_changes'):
        paragraph('주의: 생성 후 삭제·교체된 출처가 있습니다. 현재 자료로 다시 검토하세요. ' + ', '.join(draft['source_changes']))
    # Fixed UTC offset avoids requiring the optional tzdata package on Windows.
    from datetime import timezone, timedelta
    paragraph('내보낸 시각: ' + datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M (한국 시간)'))
    paragraph('저장된 내용 기준입니다. 원문 출처는 편집한 문장 전체의 정확성을 보증하지 않습니다.')
    used = []
    for item in draft['items']:
        paragraph(item['category'], True, 26)
        paragraph(item['text'])
        numbers = []
        for source_id in item['source_ids']:
            if source_id not in used:
                used.append(source_id)
            numbers.append(str(used.index(source_id) + 1))
        paragraph('출처: ' + ', '.join('[' + n + ']' for n in numbers))
    paragraph('출처 목록', True, 28)
    for index, source_id in enumerate(used, 1):
        ref = draft['references'][source_id]
        paragraph(f"[{index}] {ref['name']} / {ref['location']}", True)
        paragraph(ref['text'])
    if 'tasks' in draft:
        paragraph('후임자 할 일 목록', True, 28)
        paragraph('내려받는 시점에 해당 업무 묶음에 저장된 할 일입니다. 초안 작성 시점과 다를 수 있습니다. 완료 여부와 기한은 사용자가 입력한 값입니다.')
        tasks = draft['tasks']
        unfinished = [task for task in tasks if not task['done']]
        today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        overdue = sum(bool(task['due_date']) and task['due_date'] < today for task in unfinished)
        paragraph(f'미완료 {len(unfinished)}건 / 완료 {len(tasks) - len(unfinished)}건 / 기한 지남 {overdue}건')
        if not tasks:
            paragraph('등록된 할 일이 없습니다.')
        for index, task in enumerate(tasks, 1):
            status = '완료' if task['done'] else '기한 지남' if task['due_date'] and task['due_date'] < today else '미완료'
            paragraph(f"{index}. [{status}] {task['title']}", True)
            paragraph('기한: ' + (task['due_date'] or '미지정') + ' / 담당자: ' + (task['assignee'] or '미지정'))
            if task.get('source'):
                paragraph('등록 당시 출처·참고 메모: ' + task['source'])
    section = ET.SubElement(body, f'{{{W}}}sectPr')
    ET.SubElement(section, f'{{{W}}}pgSz', {f'{{{W}}}w': '11906', f'{{{W}}}h': '16838'})
    ET.SubElement(section, f'{{{W}}}pgMar', {f'{{{W}}}top': '1134', f'{{{W}}}bottom': '1134', f'{{{W}}}left': '1134', f'{{{W}}}right': '1134'})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', ET.tostring(root, encoding='utf-8', xml_declaration=True))
    return output.getvalue()
