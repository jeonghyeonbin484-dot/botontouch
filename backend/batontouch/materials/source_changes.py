"""초안이 참조한 원본의 변경 여부를 확인한다."""
import re
def find_changed_document_sources(db, payload, workspace_id):
    changes = []
    for key, ref in payload.get('references', {}).items():
        doc_id = ref.get('document_id')
        if doc_id is None:
            match = re.match(r'D(\d+)-S', key)
            doc_id = int(match[1]) if match else None
        if doc_id is None:
            continue
        row = db.execute('SELECT deleted,revision FROM documents WHERE id=? AND workspace_id=?', (doc_id, workspace_id)).fetchone()
        if row is None or row['deleted'] or row['revision'] != ref.get('revision', 1):
            label = ref.get('name', str(doc_id))
            if label not in changes:
                changes.append(label)
    return changes
