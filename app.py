"""Shared handover library server with required staff authentication."""
import io
from contextlib import closing
import json
import sqlite3
import socket
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ai_draft
import export_docx
import export_hwpx
import extract_office
import re
import auth_control
import server_settings
import os
import handover_workflow
import handover_requests
import handover_journey
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('BATON_DATA_DIR',str(ROOT/'data'))).resolve()
MAX_FILE = 4 * 1024 * 1024


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def connect():
    DATA = __import__('cloud_context').current_data.get() or globals()['DATA']
    DATA.mkdir(parents=True,exist_ok=True)
    auth_control.backup_before_migration(DATA / 'library.sqlite3')
    handover_requests.backup_before_migration(DATA / 'library.sqlite3')
    db = sqlite3.connect(DATA / 'library.sqlite3',timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, name TEXT, content TEXT, sources TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute('CREATE TABLE IF NOT EXISTS drafts (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    db.execute("CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY, title TEXT NOT NULL, department TEXT NOT NULL DEFAULT '', predecessor TEXT NOT NULL DEFAULT '', successor TEXT NOT NULL DEFAULT '', reference_date TEXT NOT NULL DEFAULT '')")
    db.execute("INSERT OR IGNORE INTO workspaces(id,title) VALUES(1,'기존 인수인계')")
    db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, title TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '', assignee TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '', deleted INTEGER NOT NULL DEFAULT 0)")
    db.execute('CREATE TABLE IF NOT EXISTS suggestions (id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    auth_control.ensure(db)
    handover_workflow.ensure(db)
    handover_requests.ensure(db)
    __import__('handover_chat').ensure(db)
    handover_journey.ensure(db)
    for table in ('documents', 'drafts', 'questions'):
        if 'workspace_id' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN workspace_id INTEGER NOT NULL DEFAULT 1')
        db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_workspace ON {table}(workspace_id)')
        if 'deleted' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
    if 'revision' not in {r['name'] for r in db.execute('PRAGMA table_info(documents)')}:
        db.execute('ALTER TABLE documents ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
    db.commit()
    return db


def source_changes(db, payload, workspace_id):
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


def extract(name, raw):
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


class Handler(BaseHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        # No query strings, usernames, headers, request bodies or credentials in logs.
        path=urlsplit(self.path).path
        category=path.split('/')[2] if path.startswith('/api/') and len(path.split('/'))>2 else ''
        known={'auth','directory','requests','documents','drafts','questions','tasks','workspaces','handover','versions','checks','backup','manage'}
        route='/api/'+category if category in known else path if path in ('/','/login') else '/unknown'
        method=self.command if self.command in ('GET','POST','HEAD','OPTIONS') else 'UNKNOWN'
        self.log_message('%s %s %s',method,route,str(code))

    def workspace(self):
        try:
            workspace_id = int(self.headers.get('X-Workspace-Id', '1'))
        except ValueError:
            raise ValueError('인수인계 묶음을 선택해 주세요.')
        with closing(connect()) as db:
            if not db.execute('SELECT id FROM workspaces WHERE id=?', (workspace_id,)).fetchone():
                raise ValueError('인수인계 묶음이 없습니다.')
            auth_control.workspace_access(db, getattr(self, 'user', None), workspace_id, self.command == 'POST', self.path)
        return workspace_id

    def respond(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        route=self.path.split('?')[0]
        if any(part.startswith('.') for part in route.split('/') if part) or route.endswith(('.py','.sqlite3','.json','.env')):
            return self.respond(404,{'error':'페이지가 없습니다.'})
        if not self.path.split('?')[0].startswith('/api/'):
            page='login.html' if self.path.split('?')[0]=='/login' else 'index.html'
            if page=='index.html':
                try:
                    with closing(connect()) as db:auth_control.identity(self,db)
                except auth_control.AccessError as error:
                    self.send_response(303);self.send_header('Location','/login#password' if error.status==403 else '/login');self.send_header('Cache-Control','no-store');self.end_headers();return
            raw=(ROOT/'web'/page).read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        if auth_control.handle(self, connect, 'GET'):
            return
        if __import__('handover_chat').handle(self, connect, 'GET'):
            return
        if handover_requests.handle(self, connect, 'GET', source_changes):
            return
        if handover_journey.handle(self, connect, 'GET'):
            return
        if __import__('gemini_verification').handle(self,connect,'GET'):
            return
        if __import__('evidence_api').handle(self,connect,'GET'):
            return
        try:
            with closing(connect()) as db:
                auth_control.identity(self, db)
                if self.path == '/api/workspaces':
                    rows = db.execute('SELECT * FROM workspaces ORDER BY id').fetchall()
                    result = [{**dict(row), 'permission': auth_control.permission(db, self.user, row['id'])} for row in rows if auth_control.permission(db, self.user, row['id'])]
                    return self.respond(200, result)
        except auth_control.AccessError as error:
            return self.respond(error.status, {'error': error.message})
        try:
            workspace_id = self.workspace()
        except auth_control.AccessError as error:
            return self.respond(error.status, {'error': error.message})
        except ValueError as error:
            return self.respond(getattr(error,'http_status',400), {'error': str(error)})
        if handover_workflow.handle(self, connect, 'GET', workspace_id, source_changes):
            return
        export_match = re.fullmatch(r'/api/drafts/(\d+)/export(?:\.(hwpx|html|md))?', urlsplit(self.path).path)
        if export_match:
            with closing(connect()) as db:
                row = db.execute('SELECT payload FROM drafts WHERE id=? AND workspace_id=? AND deleted=0', (int(export_match[1]), workspace_id)).fetchone()
            if row is None:
                return self.respond(404, {'error': '내려받을 초안이 없습니다.'})
            draft = json.loads(row['payload'])
            with closing(connect()) as db:
                draft['workspace'] = dict(db.execute('SELECT * FROM workspaces WHERE id=?', (workspace_id,)).fetchone())
                draft['source_changes'] = source_changes(db, draft, workspace_id)
                draft['tasks'] = [dict(task) for task in db.execute("SELECT * FROM tasks WHERE workspace_id=? AND deleted=0 ORDER BY done, CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date, id DESC", (workspace_id,))]
            extension = export_match[2] or 'docx'
            if extension in ('hwpx','html','md'):
                try:
                    return __import__('report_export').respond(self,draft,extension,draft.get('title') or '인수인계서')
                except auth_control.AccessError as error:
                    return self.respond(error.status,{'error':error.message})
            try:
                raw = export_hwpx.build(draft) if extension == 'hwpx' else export_docx.build(draft)
            except ValueError as error:
                return self.respond(getattr(error,'http_status',400), {'error': str(error)})
            title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', draft['title'])[:80] or '인수인계서'
            self.send_response(200)
            self.send_header('Content-Type', 'application/hwp+zip' if extension == 'hwpx' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            self.send_header('Content-Disposition', f"attachment; filename=handover.{extension}; filename*=UTF-8''" + quote(title + '.' + extension))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == '/':
            raw = (ROOT / 'web' / 'index.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == '/api/tasks':
            with closing(connect()) as db:
                rows = db.execute('SELECT * FROM tasks WHERE workspace_id=? AND deleted=0 ORDER BY done, CASE WHEN due_date=\'\' THEN 1 ELSE 0 END, due_date, id DESC', (workspace_id,)).fetchall()
            self.respond(200, [dict(row) for row in rows])
        elif self.path == '/api/workspaces':
            with closing(connect()) as db:
                rows = db.execute('SELECT * FROM workspaces ORDER BY id').fetchall()
            self.respond(200, [dict(row) for row in rows])
        elif self.path == '/api/documents':
            with closing(connect()) as db:
                rows = db.execute('SELECT id,name,length(content) AS characters,created,substr(content,1,160) AS summary,CASE WHEN instr(content,char(10))>0 THEN substr(content,1,instr(content,char(10))-1) ELSE substr(content,1,80) END AS title FROM documents WHERE workspace_id=? AND deleted=0 ORDER BY id DESC', (workspace_id,)).fetchall()
            self.respond(200, [dict(r) for r in rows])
        elif self.path == '/api/drafts':
            with closing(connect()) as db:
                rows = db.execute('SELECT * FROM drafts WHERE workspace_id=? AND deleted=0 ORDER BY id DESC', (workspace_id,)).fetchall()
                results = []
                for row in rows:
                    payload = json.loads(row['payload'])
                    results.append({'id': row['id'], 'created': row['created'], **payload, 'edit_token': handover_workflow.fingerprint(payload), 'source_changes': source_changes(db, payload, workspace_id)})
            self.respond(200, results)
        elif self.path == '/api/questions/suggestions':
            with closing(connect()) as db:
                row = db.execute('SELECT * FROM suggestions WHERE workspace_id=? ORDER BY id DESC LIMIT 1', (workspace_id,)).fetchone()
                if row:
                    payload = json.loads(row['payload'])
                    result = {'id': row['id'], 'created': row['created'], **payload, 'source_changes': source_changes(db, payload, workspace_id)}
                else:
                    result = None
            self.respond(200, result)
        elif self.path == '/api/questions':
            with closing(connect()) as db:
                rows = db.execute('SELECT * FROM questions WHERE workspace_id=? AND deleted=0 ORDER BY id DESC LIMIT 50', (workspace_id,)).fetchall()
                results = []
                for row in rows:
                    payload = json.loads(row['payload'])
                    results.append({'id': row['id'], 'created': row['created'], **payload, 'source_changes': source_changes(db, payload, workspace_id)})
            self.respond(200, results)
        elif self.path.startswith('/api/documents/'):
            try:
                document_id = int(self.path.rsplit('/', 1)[1])
            except ValueError:
                return self.respond(404, {'error': '자료가 없습니다.'})
            with closing(connect()) as db:
                row = db.execute('SELECT * FROM documents WHERE id=? AND workspace_id=? AND deleted=0', (document_id, workspace_id)).fetchone()
            if not row:
                return self.respond(404, {'error': '자료가 없습니다.'})
            result = dict(row)
            result['sources'] = json.loads(result['sources'])
            self.respond(200, result)
        else:
            self.respond(404, {'error': '페이지가 없습니다.'})

    def do_POST(self):
        # No cross-origin uploads: this server is intended for this PC only.
        origin = self.headers.get('Origin')
        if origin and origin not in server_settings.allowed_origins():
            return self.respond(403, {'error': '허용되지 않은 요청입니다.'})
        if __import__('organization_ingest').handle(self,connect):
            return
        if auth_control.handle(self, connect, 'POST'):
            return
        if __import__('handover_chat').handle(self, connect, 'POST'):
            return
        if handover_requests.handle(self, connect, 'POST', source_changes):
            return
        if handover_journey.handle(self, connect, 'POST'):
            return
        if __import__('gemini_verification').handle(self,connect,'POST'):
            return
        if __import__('evidence_api').handle(self,connect,'POST'):
            return
        try:
            with closing(connect()) as db:
                auth_control.identity(self, db)
            workspace_id = 0 if self.path in ('/api/workspaces/create', '/api/backup/restore') else self.workspace()
        except auth_control.AccessError as error:
            return self.respond(error.status, {'error': error.message})
        except ValueError as error:
            return self.respond(getattr(error,'http_status',400), {'error': str(error)})
        if handover_workflow.handle(self, connect, 'POST', workspace_id, source_changes):
            return
        if self.path == '/api/manage/delete':
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 10000:
                    raise ValueError('요청 크기를 확인해 주세요.')
                body = json.loads(self.rfile.read(size))
                table = body.get('type') if isinstance(body, dict) else None
                if table not in ('documents', 'drafts', 'questions', 'tasks') or type(body.get('id')) is not int:
                    raise ValueError('삭제할 항목을 확인해 주세요.')
                with closing(connect()) as db:
                    cursor = db.execute(f'UPDATE {table} SET deleted=1 WHERE id=? AND workspace_id=? AND deleted=0', (body['id'], workspace_id))
                    if not cursor.rowcount:
                        raise ValueError('삭제할 항목이 없거나 다른 묶음에 속해 있습니다.')
                    db.commit()
                return self.respond(200, {'deleted': True})
            except (ValueError, TypeError) as error:
                return self.respond(getattr(error,'http_status',400), {'error': str(error)})
        if self.path in ('/api/tasks/create', '/api/tasks/save'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 20000:
                    raise ValueError('입력 크기를 확인해 주세요.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('입력 형식을 확인해 주세요.')
                fields = ('title', 'due_date', 'assignee', 'source')
                values = [body.get(key, '') for key in fields]
                if any(not isinstance(v, str) for v in values) or not values[0].strip() or len(values[0]) > 2000 or len(values[2]) > 200 or len(values[3]) > 5000:
                    raise ValueError('할 일은 1~2000자, 담당자는 200자, 출처 메모는 5000자 이내로 입력해 주세요.')
                values = [v.strip() for v in values]
                if values[1]:
                    from datetime import date
                    date.fromisoformat(values[1])
                if type(body.get('done', False)) is not bool:
                    raise ValueError('완료 상태를 확인해 주세요.')
                done = int(body.get('done', False))
                with closing(connect()) as db:
                    if self.path.endswith('/create'):
                        cursor = db.execute('INSERT INTO tasks(title,due_date,assignee,source,done,workspace_id) VALUES(?,?,?,?,?,?)', (*values, done, workspace_id))
                        task_id = cursor.lastrowid
                    else:
                        if type(body.get('id')) is not int:
                            raise ValueError('할 일 ID를 확인해 주세요.')
                        cursor = db.execute('UPDATE tasks SET title=?,due_date=?,assignee=?,source=?,done=? WHERE id=? AND workspace_id=? AND deleted=0', (*values, done, body['id'], workspace_id))
                        if not cursor.rowcount:
                            raise ValueError('할 일이 없거나 다른 묶음에 속해 있습니다.')
                        task_id = body['id']
                    db.commit()
                return self.respond(200, {'id': task_id})
            except (ValueError, TypeError) as error:
                return self.respond(getattr(error,'http_status',400), {'error': str(error)})
        if self.path in ('/api/workspaces/create', '/api/workspaces/save'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 10000:
                    raise ValueError('입력 크기를 확인해 주세요.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('입력 형식을 확인해 주세요.')
                fields = ('title', 'department', 'predecessor', 'successor', 'reference_date')
                values = [body.get(field, '') for field in fields]
                if any(not isinstance(v, str) or len(v) > 200 for v in values) or not values[0].strip():
                    raise ValueError('업무명은 필수이며 각 항목은 200자 이내입니다.')
                values = [v.strip() for v in values]
                if values[4]:
                    from datetime import date
                    date.fromisoformat(values[4])
                with closing(connect()) as db:
                    if self.path.endswith('/create'):
                        cursor = db.execute('INSERT INTO workspaces(title,department,predecessor,successor,reference_date) VALUES(?,?,?,?,?)', values)
                        result_id = cursor.lastrowid
                        if self.user:
                            db.execute('INSERT INTO workspace_members VALUES(?,?,?)', (result_id, self.user['id'], 'editor'))
                    else:
                        db.execute('UPDATE workspaces SET title=?,department=?,predecessor=?,successor=?,reference_date=? WHERE id=?', (*values, workspace_id))
                        result_id = workspace_id
                    db.commit()
                return self.respond(200, {'id': result_id})
            except (ValueError, TypeError) as error:
                return self.respond(getattr(error,'http_status',400), {'error': str(error)})
        if self.path in ('/api/drafts/generate', '/api/drafts/save', '/api/questions/ask', '/api/questions/suggest'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2 * 1024 * 1024:
                    raise ValueError('요청 크기를 확인해 주세요.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('요청 형식을 확인해 주세요.')
                if self.path.endswith('/generate') or self.path.endswith('/ask') or self.path.endswith('/suggest'):
                    ids = body.get('document_ids')
                    if not isinstance(ids, list) or not 1 <= len(ids) <= 20 or any(type(i) is not int for i in ids):
                        raise ValueError('자료를 1~20개 선택해 주세요.')
                    with closing(connect()) as db:
                        docs = db.execute('SELECT * FROM documents WHERE workspace_id=? AND deleted=0 AND id IN (' + ','.join('?' for _ in ids) + ')', [workspace_id, *ids]).fetchall()
                    if len(docs) != len(set(ids)):
                        raise ValueError('선택한 자료를 찾지 못했습니다.')
                    if self.path.endswith('/suggest'):
                        result = ai_draft.generate(docs, expected_questions=True,actor=self.user)
                        result['documents'] = [{'id': doc['id'], 'name': doc['name']} for doc in docs]
                        with closing(connect()) as db:
                            cursor = db.execute('INSERT INTO suggestions(workspace_id,payload) VALUES(?,?)', (workspace_id, json.dumps(result, ensure_ascii=False)))
                            result_id = cursor.lastrowid
                            db.commit()
                        return self.respond(201, {'id': result_id, **result})
                    if self.path.endswith('/ask'):
                        question = body.get('question')
                        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
                            raise ValueError('질문을 1~2000자로 입력해 주세요.')
                        answer = ai_draft.generate(docs, question=question.strip(),actor=self.user)
                        answer.update(question=question.strip(), documents=[{'id': d['id'], 'name': d['name']} for d in docs])
                        with closing(connect()) as db:
                            cursor = db.execute('INSERT INTO questions(payload,workspace_id) VALUES(?,?)', (json.dumps(answer, ensure_ascii=False), workspace_id))
                            db.commit()
                            answer_id = cursor.lastrowid
                        return self.respond(201, {'id': answer_id, **answer})
                    draft = ai_draft.generate(docs,actor=self.user)
                    with closing(connect()) as db:
                        cursor = db.execute('INSERT INTO drafts(payload,workspace_id) VALUES(?,?)', (json.dumps(draft, ensure_ascii=False), workspace_id))
                        draft_id = cursor.lastrowid
                        handover_workflow.record_version(db, draft_id, workspace_id, draft, auth_control.actor(self), 'generated')
                        db.commit()
                    return self.respond(201, {'id': draft_id, **draft, 'edit_token': handover_workflow.fingerprint(draft)})
                with closing(connect()) as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT payload FROM drafts WHERE id=? AND workspace_id=? AND deleted=0', (body.get('id'), workspace_id)).fetchone()
                    if not row:
                        raise ValueError('저장할 초안이 없습니다.')
                    previous = json.loads(row['payload'])
                    if body.get('edit_token') and body['edit_token'] != handover_workflow.fingerprint(previous):
                        raise ValueError('다른 사용자가 문서를 수정했습니다. 현재 입력을 복사해 보관한 뒤 최신 문서를 다시 열어 주세요.')
                    handover_workflow.baseline(db, body['id'], workspace_id, previous)
                    edited = ai_draft.validate_draft(body, previous['references'])
                    # Immutable source text and original generated content remain on the server.
                    previous.setdefault('original', {'title': previous['title'], 'items': previous['items']})
                    edited['items']=__import__('source_evidence').preserve_review(previous,edited['items'])
                    previous.update(title=edited['title'], items=edited['items'], reviewed=body.get('reviewed') is True)
                    db.execute('UPDATE drafts SET payload=? WHERE id=?', (json.dumps(previous, ensure_ascii=False), body.get('id')))
                    handover_workflow.record_version(db, body['id'], workspace_id, previous, auth_control.actor(self), 'saved')
                    db.commit()
                with closing(connect()) as db:
                    changes = source_changes(db, previous, workspace_id)
                return self.respond(200, {'id': body['id'], **previous, 'edit_token': handover_workflow.fingerprint(previous), 'source_changes': changes})
            except (ValueError, TypeError) as error:
                return self.respond(getattr(error,'http_status',400), __import__('ai_diagnostics').payload(error, self.path.rsplit('/',1)[-1], getattr(self,'user',None)))
        if self.path != '/api/documents':
            return self.respond(404, {'error': '페이지가 없습니다.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_FILE:
                raise ValueError('파일은 0바이트 초과, 10MB 이하여야 합니다.')
            name = self.headers.get('X-File-Name', '')
            from urllib.parse import unquote
            name = Path(unquote(name)).name
            if not name or len(name)>200 or any(ord(c)<32 for c in name):raise ValueError('파일 이름을 확인해 주세요.')
            original_bytes = self.rfile.read(size)
            if len(original_bytes)!=size:raise ValueError('파일 전송이 완료되지 않았습니다.')
            content, sources = extract(name, original_bytes)
            with closing(connect()) as db:
                replace_id = self.headers.get('X-Replace-Id')
                if replace_id:
                    document_id = int(replace_id)
                    cursor = db.execute('UPDATE documents SET name=?,content=?,sources=?,revision=revision+1 WHERE id=? AND workspace_id=? AND deleted=0', (name, content, json.dumps(sources, ensure_ascii=False), document_id, workspace_id))
                    if not cursor.rowcount:
                        raise ValueError('교체할 자료가 없거나 다른 묶음에 속해 있습니다.')
                else:
                    cursor = db.execute('INSERT INTO documents(name,content,sources,workspace_id) VALUES(?,?,?,?)', (name, content, json.dumps(sources, ensure_ascii=False), workspace_id))
                    document_id = cursor.lastrowid
                revision=db.execute('SELECT revision FROM documents WHERE id=?',(document_id,)).fetchone()[0]
                db.execute('INSERT INTO document_files(document_id,workspace_id,revision,name,raw) VALUES(?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET revision=excluded.revision,name=excluded.name,raw=excluded.raw',(document_id,workspace_id,revision,name,original_bytes))
                db.commit()
            self.respond(201, {'id': document_id, 'name': name})
        except ValueError as error:
            self.respond(getattr(error,'http_status',400), {'error': str(error)})


if __name__ == '__main__':
    server_settings.validate()
    __import__('report_document').register_local_fonts()
    connect().close()
    print('바통터치 서버 시작: '+(server_settings.public_origin() or 'http://'+server_settings.host()+':'+str(server_settings.port())),flush=True)
    try:
        LocalServer((server_settings.host(),server_settings.port()), Handler).serve_forever()
    except OSError:
        print('이미 실행 중인 서버가 있습니다. 기존 바통터치 실행 창을 종료한 뒤 다시 실행해 주세요.', flush=True)
