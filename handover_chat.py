"""인수인계 당사자 전용 채팅. 외부 AI나 조직도 호출을 하지 않는다."""
import io
import json
import os
import re
import sqlite3
import time
import zipfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote, quote
import auth_control

SCHEMA='''
CREATE TABLE IF NOT EXISTS request_chat_messages(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL REFERENCES handover_requests(id),sender_id INTEGER NOT NULL REFERENCES users(id),recipient_employee TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',nonce TEXT NOT NULL,created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),UNIQUE(request_id,sender_id,nonce));
CREATE INDEX IF NOT EXISTS idx_chat_request ON request_chat_messages(request_id,id);
CREATE TABLE IF NOT EXISTS request_chat_reads(request_id INTEGER NOT NULL,user_id INTEGER NOT NULL,last_id INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(request_id,user_id));
CREATE TABLE IF NOT EXISTS request_chat_files(id INTEGER PRIMARY KEY,message_id INTEGER UNIQUE NOT NULL REFERENCES request_chat_messages(id),name TEXT NOT NULL,raw BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS request_chat_knowledge(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL,message_id INTEGER UNIQUE NOT NULL,saved_by INTEGER NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
'''
def ensure(db): db.executescript(SCHEMA)

def access(db,user,rid):
    import handover_requests as requests
    # Pending requests bind only through the existing verified identity mapping.
    requests.bind_pending_requests(db,user)
    row=requests.request_row(db,user,rid)
    return row

def positive(value):
    if not isinstance(value,int) or isinstance(value,bool) or value<0: raise ValueError('메시지 번호를 확인하세요.')
    return value

def data(db,user,row,before=0):
    rid=row['id'];peer=row['recipient_account'] if user['id']==row['sender_account'] else row['sender_account']
    read=db.execute('SELECT last_id FROM request_chat_reads WHERE request_id=? AND user_id=?',(rid,peer)).fetchone()
    peer_read=read[0] if read else 0
    rows=db.execute('SELECT m.id,m.sender_id,m.body,m.created,f.id AS file_id,f.name,length(f.raw) AS bytes,k.id AS knowledge_id FROM request_chat_messages m LEFT JOIN request_chat_files f ON f.message_id=m.id LEFT JOIN request_chat_knowledge k ON k.message_id=m.id WHERE m.request_id=? AND m.recipient_employee=? AND (?=0 OR m.id<?) ORDER BY m.id DESC LIMIT 60',(rid,row['recipient_employee'],before,before)).fetchall()
    messages=[dict(m)|{'mine':m['sender_id']==user['id'],'read':m['id']<=peer_read if m['sender_id']==user['id'] else True} for m in reversed(rows)]
    return {'request_id':rid,'room_key':str(rid)+':'+row['recipient_employee'],'messages':messages,'peer_read':peer_read,'has_more':bool(rows) and db.execute('SELECT 1 FROM request_chat_messages WHERE request_id=? AND recipient_employee=? AND id<? LIMIT 1',(rid,row['recipient_employee'],rows[-1]['id'])).fetchone() is not None,'completed':row['state']=='completed','can_send':row['state']!='completed','my_id':user['id'],'recipient_pending':peer is None,'file_limit_mb':2 if os.environ.get('VERCEL') else 10,'total_limit_mb':8 if os.environ.get('VERCEL') else 50}

def validate_file(name,raw,limit):
    if not name or len(name)>180 or name!=Path(name).name or any(c in name for c in '/\\:\x00') or any(ord(c)<32 for c in name): raise ValueError('안전한 파일 이름을 사용하세요.')
    ext=Path(name).suffix.lower()
    if ext not in ('.hwpx','.pdf','.xlsx','.docx'): raise ValueError('HWPX, PDF, XLSX, DOCX 파일만 첨부할 수 있습니다.')
    if not raw or len(raw)>limit: raise ValueError('파일 크기 제한을 확인하세요.')
    if ext=='.pdf':
        if not raw.startswith(b'%PDF-'): raise ValueError('PDF 파일 내용과 확장자가 일치하지 않습니다.')
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos=z.infolist()
                if len(infos)>3000 or sum(i.file_size for i in infos)>50*1024*1024: raise ValueError('압축 해제 크기가 너무 큰 파일입니다.')
                if any(i.flag_bits&1 or '..' in i.filename.split('/') or i.filename.startswith('/') or 'vbaproject' in i.filename.lower() for i in infos): raise ValueError('암호화·매크로 또는 위험한 파일은 첨부할 수 없습니다.')
                expected={'.hwpx':'Contents/section0.xml','.xlsx':'xl/workbook.xml','.docx':'word/document.xml'}[ext]
                if expected not in z.namelist(): raise ValueError('파일 내용과 확장자가 일치하지 않습니다.')
        except zipfile.BadZipFile: raise ValueError('문서 압축 구조가 손상되었습니다.') from None

def notification_snapshot(db,user,after=-1):
    import handover_requests
    handover_requests.bind_pending_requests(db,user)
    uid=user['id']
    scope="(? IN (r.sender_account,r.recipient_account)) AND m.recipient_employee=r.recipient_employee"
    high=db.execute('SELECT coalesce(max(m.id),0) FROM request_chat_messages m JOIN handover_requests r ON r.id=m.request_id WHERE '+scope,(uid,)).fetchone()[0]
    rows=db.execute("SELECT m.request_id,count(*) AS count,max(m.id) AS last_id,json_extract(CASE WHEN r.sender_account=? THEN r.recipient_snapshot ELSE r.sender_snapshot END,'$.name') AS peer_name,json_extract(r.payload,'$.title') AS title FROM request_chat_messages m JOIN handover_requests r ON r.id=m.request_id LEFT JOIN request_chat_reads s ON s.request_id=r.id AND s.user_id=? WHERE "+scope+" AND m.sender_id!=? AND m.id>coalesce(s.last_id,0) GROUP BY m.request_id ORDER BY max(m.id) DESC",(uid,uid,uid,uid)).fetchall()
    notes=[]
    if after>=0:
        notes=[dict(row) for row in db.execute("SELECT m.id,m.request_id,m.created,CASE WHEN m.body='' THEN '첨부파일' ELSE substr(m.body,1,120) END AS preview,json_extract(r.payload,'$.title') AS title,json_extract(CASE WHEN m.sender_id=r.sender_account THEN r.sender_snapshot ELSE r.recipient_snapshot END,'$.name') AS sender_name FROM request_chat_messages m JOIN handover_requests r ON r.id=m.request_id LEFT JOIN request_chat_reads s ON s.request_id=r.id AND s.user_id=? WHERE "+scope+" AND m.sender_id!=? AND m.id>? AND m.id<=? AND m.id>coalesce(s.last_id,0) ORDER BY m.id LIMIT 50",(uid,uid,uid,after,high)).fetchall()]
    cursor=notes[-1]['id'] if len(notes)==50 else max(high,after)
    return {'user_id':uid,'cursor':cursor,'notifications':notes,'total':sum(row['count'] for row in rows),'rooms':[dict(row) for row in rows]}


def notification_feed(handler,factory,method):
    path=urlsplit(handler.path).path
    if path not in ('/api/chat/notifications','/api/chat/notifications/events'):return False
    started=False
    try:
        if method!='GET':raise auth_control.AccessError(405,'알림 조회는 GET 요청만 허용됩니다.')
        q=parse_qs(urlsplit(handler.path).query);raw=handler.headers.get('Last-Event-ID') or q.get('after',['-1'])[0]
        try:after=int(raw)
        except (ValueError,TypeError):raise ValueError('알림 확인 번호를 확인하세요.')
        if not -1<=after<=9007199254740991:raise ValueError('알림 확인 번호를 확인하세요.')
        buffered=bool(os.environ.get('VERCEL') or getattr(handler,'capture',False));deadline=time.monotonic()+(0 if buffered else 20);db_path=None
        while True:
            connection=factory() if db_path is None else sqlite3.connect('file:'+quote(db_path.replace(chr(92),'/'),safe='/:')+'?mode=rw',uri=True,timeout=5)
            with closing(connection) as db:
                db.row_factory=sqlite3.Row
                if db_path is None:db_path=db.execute('PRAGMA database_list').fetchone()[2]
                user=auth_control.identity(handler,db)
                expected=q.get('user_id',[None])[0]
                if expected is not None and expected!=str(user['id']):raise auth_control.AccessError(403,'로그인 계정이 변경되어 이전 알림 연결을 종료했습니다.')
                result=notification_snapshot(db,user,after);db.commit()
            if path=='/api/chat/notifications':handler.respond(200,result);return True
            if not started:
                handler.send_response(200);handler.send_header('Content-Type','text/event-stream; charset=utf-8');handler.send_header('Cache-Control','no-store');handler.send_header('X-Accel-Buffering','no');handler.send_header('Connection','close');handler.end_headers();started=True
            handler.wfile.write(('retry: 5000\nid: '+str(result['cursor'])+'\nevent: notifications\ndata: '+json.dumps(result,ensure_ascii=False)+'\n\n').encode());handler.wfile.flush();after=result['cursor']
            if time.monotonic()>=deadline:break
            time.sleep(1)
        handler.close_connection=True
    except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    except auth_control.AccessError as error:
        if started:handler.wfile.write(b'event: denied\ndata: {}\n\n');handler.wfile.flush()
        else:handler.respond(error.status,{'error':error.message})
    except ValueError as error:
        if not started:handler.respond(400,{'error':str(error)})
    except sqlite3.Error:
        if not started:handler.respond(503,{'error':'대화 알림 저장소를 확인하지 못했습니다. 잠시 후 다시 연결합니다.'})
        handler.close_connection=True
    return True


def handle(handler,factory,method):
    if notification_feed(handler,factory,method):return True
    path=urlsplit(handler.path).path
    if not path.startswith('/api/chat/'): return False
    started=False
    try:
        q=parse_qs(urlsplit(handler.path).query)
        match=re.fullmatch(r'/api/chat/(\d+)/(messages|events|read|files|knowledge)(?:/(\d+))?',path)
        with closing(factory()) as db:
            user=auth_control.identity(handler,db)
            if path=='/api/chat/rooms' and method=='GET':
                import handover_requests
                handover_requests.bind_pending_requests(db,user)
                rows=db.execute('SELECT * FROM handover_requests WHERE sender_account=? OR recipient_account=?',(user['id'],user['id'])).fetchall()
                rooms=[]
                for row in rows:
                    last=db.execute('SELECT body,created,id FROM request_chat_messages WHERE request_id=? AND recipient_employee=? ORDER BY id DESC LIMIT 1',(row['id'],row['recipient_employee'])).fetchone()
                    unread=db.execute('SELECT count(*) FROM request_chat_messages m LEFT JOIN request_chat_reads s ON s.request_id=m.request_id AND s.user_id=? WHERE m.request_id=? AND m.recipient_employee=? AND m.sender_id!=? AND m.id>coalesce(s.last_id,0)',(user['id'],row['id'],row['recipient_employee'],user['id'])).fetchone()[0]
                    sender=user['id']==row['sender_account']
                    payload=json.loads(row['payload']);workspace=payload.get('workspace');workspace=workspace if isinstance(workspace,dict) else {}
                    rooms.append({'request_id':row['id'],'title':payload.get('title',''),'workspace_title':workspace.get('title') or payload.get('title',''),'peer':json.loads(row['recipient_snapshot'] if sender else row['sender_snapshot']),'sender':sender,'unread':unread,'last_id':last['id'] if last else 0,'preview':(last['body'][:120] or '첨부파일') if last else '첫 대화를 시작하세요.','last_time':last['created'] if last else row['created'],'last_message_at':last['created'] if last else None,'revision':row['revision'],'state':row['state'],**__import__('request_inbox').metrics(db,row)})
                rooms.sort(key=lambda r:(bool(r['last_id']),r['last_time'].replace('T',' ').removesuffix('Z'),r['last_id'],r['request_id']),reverse=True)
                db.commit();handler.respond(200,{'rooms':rooms,'total':sum(r['unread'] for r in rooms)});return True
            if path=='/api/chat/unread' and method=='GET':
                import handover_requests
                handover_requests.bind_pending_requests(db,user)
                rows=db.execute("SELECT m.request_id,count(*) AS count,max(m.id) AS last_id,json_extract(CASE WHEN r.sender_account=? THEN r.recipient_snapshot ELSE r.sender_snapshot END,'$.name') AS peer_name FROM request_chat_messages m JOIN handover_requests r ON r.id=m.request_id LEFT JOIN request_chat_reads s ON s.request_id=r.id AND s.user_id=? WHERE (? IN (r.sender_account,r.recipient_account)) AND m.recipient_employee=r.recipient_employee AND m.sender_id!=? AND m.id>coalesce(s.last_id,0) GROUP BY m.request_id ORDER BY max(m.id) DESC",(user['id'],user['id'],user['id'],user['id'])).fetchall();db.commit()
                handler.respond(200,{'total':sum(r['count'] for r in rows),'rooms':[dict(r) for r in rows]});return True
            if not match: raise ValueError('대화방 경로를 확인하세요.')
            rid=int(match[1]);kind=match[2];fid=match[3];row=access(db,user,rid);db.commit()
            if method=='GET' and kind in ('messages','events'):
                before=positive(int(q.get('before',['0'])[0]));result=data(db,user,row,before)
                db_path=db.execute('PRAGMA database_list').fetchone()[2]
                if kind=='messages':handler.respond(200,result);return True
            elif method=='GET' and kind=='files' and fid:
                f=db.execute('SELECT f.name,f.raw FROM request_chat_files f JOIN request_chat_messages m ON m.id=f.message_id WHERE f.id=? AND m.request_id=? AND m.recipient_employee=?',(int(fid),rid,row['recipient_employee'])).fetchone()
                if not f:raise auth_control.AccessError(404,'대화방 첨부파일을 찾을 수 없습니다.')
                raw=f['raw'];handler.send_response(200);handler.send_header('Content-Type','application/octet-stream');handler.send_header('Content-Disposition',"attachment; filename=chat-file; filename*=UTF-8''"+quote(f['name'],safe=''));handler.send_header('Content-Length',str(len(raw)));handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Cache-Control','no-store');handler.end_headers();handler.wfile.write(raw);return True
            elif method=='POST':
                if kind=='files':
                    limit=(2 if os.environ.get('VERCEL') else 10)*1024*1024
                    size=int(handler.headers.get('Content-Length','0'))
                    if size<=0 or size>limit:raise ValueError('첨부파일은 '+str(limit//1024//1024)+'MB 이하로 선택하세요.')
                    name=unquote(handler.headers.get('X-File-Name',''));raw=handler.rfile.read(size)
                    if len(raw)!=size:raise ValueError('파일 전송이 완료되지 않았습니다.')
                    validate_file(name,raw,limit);body={'nonce':handler.headers.get('X-Chat-Nonce','')}
                else:body=auth_control.read_json(handler,20000)
                db.execute('BEGIN IMMEDIATE');row=access(db,user,rid)
                expected=body.get('room_key',handler.headers.get('X-Chat-Room-Key'))
                if expected is not None and expected!=str(rid)+':'+row['recipient_employee']:raise auth_control.AccessError(409,'인수자가 변경되었습니다. 최신 대화방을 다시 선택하세요. 입력 내용은 유지됩니다.')
                if kind=='read':
                    upto=positive(body.get('last_id'))
                    maximum=db.execute('SELECT coalesce(max(id),0) FROM request_chat_messages WHERE request_id=? AND recipient_employee=?',(rid,row['recipient_employee'])).fetchone()[0]
                    if upto>maximum:raise ValueError('실제로 확인한 메시지만 읽음 처리할 수 있습니다.')
                    if upto and not db.execute('SELECT 1 FROM request_chat_messages WHERE id=? AND request_id=? AND recipient_employee=?',(upto,rid,row['recipient_employee'])).fetchone():raise ValueError('이 대화방에서 확인한 메시지만 읽음 처리할 수 있습니다.')
                    db.execute('INSERT INTO request_chat_reads VALUES(?,?,?) ON CONFLICT(request_id,user_id) DO UPDATE SET last_id=max(last_id,excluded.last_id)',(rid,user['id'],upto));result={'saved':True}
                elif kind=='knowledge':
                    mid=positive(body.get('message_id'));m=db.execute('SELECT id FROM request_chat_messages WHERE request_id=? AND recipient_employee=? AND id=?',(rid,row['recipient_employee'],mid)).fetchone()
                    if not m:raise ValueError('대화방 메시지를 찾을 수 없습니다.')
                    db.execute('INSERT OR IGNORE INTO request_chat_knowledge(request_id,message_id,saved_by) VALUES(?,?,?)',(rid,mid,user['id']));result={'saved':True}
                elif kind in ('messages','files'):
                    if row['state']=='completed':raise auth_control.AccessError(409,'완료된 인수인계 대화방은 열람만 가능합니다.')
                    nonce=body.get('nonce','');text=body.get('text','')
                    if not isinstance(nonce,str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}',nonce): raise ValueError('전송 식별값을 확인하세요.')
                    if not isinstance(text,str) or len(text)>4000 or (kind=='messages' and not text.strip()): raise ValueError('메시지는 1~4,000자로 입력하세요.')
                    existing=db.execute('SELECT id FROM request_chat_messages WHERE request_id=? AND sender_id=? AND nonce=?',(rid,user['id'],nonce)).fetchone()
                    if existing: result={'id':existing[0]}
                    else:
                        count=db.execute("SELECT count(*) FROM request_chat_messages WHERE sender_id=? AND created>strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 minute')",(user['id'],)).fetchone()[0]
                        if count>=30:raise auth_control.AccessError(429,'메시지를 너무 빠르게 전송하고 있습니다. 잠시 후 다시 시도하세요.')
                        if kind=='files':
                            total=db.execute('SELECT coalesce(sum(length(f.raw)),0) FROM request_chat_files f JOIN request_chat_messages m ON m.id=f.message_id WHERE m.request_id=?',(rid,)).fetchone()[0]
                            total_limit=(8 if os.environ.get('VERCEL') else 50)*1024*1024
                            if total+size>total_limit:raise ValueError('대화방 첨부파일 합계 '+str(total_limit//1024//1024)+'MB를 초과했습니다.')
                        mid=db.execute('INSERT INTO request_chat_messages(request_id,sender_id,recipient_employee,body,nonce) VALUES(?,?,?,?,?)',(rid,user['id'],row['recipient_employee'],text.strip(),nonce)).lastrowid
                        if kind=='files':db.execute('INSERT INTO request_chat_files(message_id,name,raw) VALUES(?,?,?)',(mid,name,raw))
                        result={'id':mid}
                else:raise ValueError('지원하지 않는 대화방 작업입니다.')
                db.commit();handler.respond(200,result);return True
            else:raise ValueError('대화방 요청 방식을 확인하세요.')
        # No open transaction while waiting. Re-check the session and participant on each tick.
        handler.send_response(200);handler.send_header('Content-Type','text/event-stream; charset=utf-8');handler.send_header('Cache-Control','no-store');handler.send_header('X-Accel-Buffering','no');handler.send_header('Connection','close');handler.end_headers();started=True
        previous=None;end=time.monotonic()+(0 if os.environ.get('VERCEL') or getattr(handler,'capture',False) else 20)
        while True:
            with closing(sqlite3.connect('file:'+quote(db_path.replace('\\','/'),safe='/:')+'?mode=rw',uri=True,timeout=5)) as db:
                db.row_factory=sqlite3.Row
                user=auth_control.identity(handler,db)
                row=__import__('handover_requests').request_row(db,user,rid)
                result=data(db,user,row)
            encoded=json.dumps(result,ensure_ascii=False)
            if encoded!=previous:
                handler.wfile.write(('retry: '+('5000' if os.environ.get('VERCEL') else '1500')+'\nevent: sync\ndata: '+encoded+'\n\n').encode());previous=encoded
            else:handler.wfile.write(b': heartbeat\n\n')
            handler.wfile.flush()
            if time.monotonic()>=end:break
            time.sleep(1)
        handler.close_connection=True
    except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    except auth_control.AccessError as e:
        if started:
            handler.wfile.write(('event: denied\ndata: '+json.dumps({'error':e.message},ensure_ascii=False)+'\n\n').encode());handler.wfile.flush()
        else:handler.respond(e.status,{'error':e.message})
    except (ValueError,TypeError,OverflowError) as error:
        if not started:handler.respond(400,{'error':str(error) if isinstance(error,ValueError) and not isinstance(error, __import__('json').JSONDecodeError) else '메시지·파일 형식 또는 크기를 확인하세요.'})
    except sqlite3.Error:
        if not started:handler.respond(409,{'error':'대화를 저장하지 못했습니다. 입력 내용은 유지됩니다. 다시 시도하세요.'})
    return True
