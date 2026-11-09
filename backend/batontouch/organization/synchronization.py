"""Official directory synchronization. No automatic account creation or retirement guessing."""
import json,sqlite3,threading,time
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor,as_completed
from batontouch.organization import directory_client as org_directory

_lock=threading.Lock()

def department_tree(db):
    rows=[dict(r) for r in db.execute('SELECT * FROM org_departments WHERE active=1')]
    byid={r['id']:r for r in rows};children={}
    for row in rows:children.setdefault(row['parent_id'] if row['parent_id'] in byid else '',[]).append(row)
    def order(row):
        try:return (0,float(row['sort_order']),row['name'],row['id'])
        except (ValueError,TypeError):return (1,0,row['name'],row['id'])
    result=[];seen=set()
    def visit(row,path,depth):
        if row['id'] in seen:return
        seen.add(row['id']);item=dict(row);item.update(depth=depth,path=' / '.join(path+[row['name']]),parent_missing=bool(row['parent_id'] and row['parent_id'] not in byid));
        if not row.get('hidden_from_picker'):result.append(item)
        for child in sorted(children.get(row['id'],[]),key=order):visit(child,path+[row['name']],depth+1)
    for row in sorted(children.get('',[]),key=order):visit(row,[],0)
    for row in rows:
        if row['id'] not in seen:visit(row,[],0)
    return result

def sync_departments(db,items):
    policy=org_directory.settings().get('department_mode_policy',{})
    if not isinstance(policy,dict):raise ValueError('부서 상태 정책 형식을 확인하세요.')
    excluded=policy.get('excluded_modes',[])
    if not isinstance(excluded,list) or any(not isinstance(x,str) or not x for x in excluded):raise ValueError('확인된 제외 상태값만 목록으로 지정하세요.')
    roots=org_directory.settings().get('excluded_department_roots',[])
    if not isinstance(roots,list) or any(not isinstance(r,str) or not r for r in roots):raise ValueError('제외 부서 코드 설정을 확인하세요.')
    byid={r['id']:r for r in items}
    def excluded_branch(key):
        seen=set()
        while key in byid and key not in seen:
            if key in roots:return True
            seen.add(key);key=byid[key]['parent_id']
        return False
    confirmed=policy.get('confirmed') is True
    db.execute('BEGIN IMMEDIATE')
    for row in items:
        mode=row.get('mode','');hide=int(excluded_branch(row['id']) or confirmed and mode in excluded)
        db.execute("INSERT INTO org_departments(id,name,parent_id,sort_order,source,synced_at,mode,team_flag,hidden_from_picker) VALUES(?,?,?,?,'org_api',CURRENT_TIMESTAMP,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,parent_id=excluded.parent_id,sort_order=excluded.sort_order,source='org_api',synced_at=CURRENT_TIMESTAMP,mode=excluded.mode,team_flag=excluded.team_flag,hidden_from_picker=excluded.hidden_from_picker",(row['id'],row['name'],row['parent_id'],row['sort_order'],mode,row.get('team_flag',''),hide))
    db.commit()

def live_lookup(db,user,dept,query):
    from batontouch.handover.requests import audit
    row=db.execute('SELECT * FROM org_departments WHERE id=? AND active=1',(dept,)).fetchone()
    if not row:raise ValueError('등록된 부서를 선택하세요.')
    try:items=org_directory.fetch_employees(dept,None)
    except org_directory.DirectoryError as error:
        audit(db,user,'실시간 직원 조회 실패',dept,str(error));db.commit();raise
    q=query.get('q',[''])[0][:100].casefold();page=max(1,int(query.get('page',['1'])[0]));output=[]
    for item in items:
        if q and q not in (item['name']+' '+item['position']).casefold():continue
        linked=db.execute('SELECT u.active,u.username,e.active AS staff_active,e.department_id,e.saeoll_id,e.employment_status FROM employee_accounts a JOIN users u ON u.id=a.user_id JOIN org_employees e ON e.employee_id=a.employee_id WHERE a.employee_id=?',(item['employee_id'],)).fetchone()
        ready=bool(item['saeoll_id'] and linked and linked['username']==item['saeoll_id'] and linked['active'] and linked['staff_active'] and linked['department_id']==dept and linked['saeoll_id']==item['saeoll_id'] and linked['employment_status']=='active' and item.get('employment_status','active')=='active')
        result={k:item[k] for k in ('employee_id','name','position','department_id')};result.update(department=item.get('department_name',row['name']),account_linked=int(ready),account_eligible=bool(item['saeoll_id']),account_issue='' if item['saeoll_id'] else 'SAEOLL_ID 누락 — 계정 발급·수신 불가',source='org_api')
        if user['role']=='admin':result['saeoll_id']=item['saeoll_id']
        output.append(result)
    from collections import Counter
    duplicates=Counter((i['name'],i['position']) for i in output)
    for item in output:item['duplicate_count']=duplicates[(item['name'],item['position'])]
    output.sort(key=lambda i:(__import__('staff_order').rank(i['position']),i['name'],i['position'],i['employee_id']))
    audit(db,user,'실시간 직원 조회',dept,str(len(items)));db.commit()
    return dict(items=output[(page-1)*50:page*50],total=len(output),page=page,page_size=50,source='org_api')

def latest(db):
    row=db.execute('SELECT * FROM org_sync_runs ORDER BY id DESC LIMIT 1').fetchone()
    if not row:return {'state':'not_started'}
    value=dict(row);value['report']=json.loads(value['report']);return value

def synchronize_staff_directory(factory,user,employees=False):
    from batontouch.handover.requests import sync_directory, audit
    with closing(factory()) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM org_sync_runs WHERE state='running'").fetchone():raise ValueError('기존 동기화가 진행 중입니다. 이전 작업 종료 후 다시 실행하세요.')
        cursor=db.execute("INSERT INTO org_sync_runs(state,actor) VALUES('running',?)",(user['id'],));runid=cursor.lastrowid;db.commit()
    report={'departments':0,'department_success':0,'department_failure':0,'empty_departments':0,'employee_rows':0,'unique_employees':0,'duplicate_rows':0,'identity_conflicts':0,'imported_employees':0,'failures':[],'missing_staff_review':0}
    def save(state='running'):
        with closing(factory()) as db:
            db.execute('UPDATE org_sync_runs SET state=?,report=?,finished=CASE WHEN ?=\'running\' THEN NULL ELSE CURRENT_TIMESTAMP END WHERE id=?',(state,json.dumps(report,ensure_ascii=False),state,runid));db.commit()
    try:
        depts=org_directory.fetch_departments()
        with closing(factory()) as db:sync_departments(db,depts)
        report['departments']=len(depts);save()
        if employees:
            collected={};collisions=set();logins={};successful=set()
            # Only two concurrent requests; no retry, no broad network scan.
            def fetch(dept):return dept,org_directory.fetch_employees(dept['id'],None)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={pool.submit(fetch,dept):dept for dept in depts}
                for future in as_completed(futures):
                    dept=futures[future]
                    try:
                        _,items=future.result();successful.add(dept['id']);report['department_success']+=1
                        if not items:report['empty_departments']+=1
                        for item in items:
                            report['employee_rows']+=1;key=item['employee_id'];login=item['saeoll_id']
                            if key in collected:
                                report['duplicate_rows']+=1
                                if collected[key]!=item:collisions.add(key)
                            if login and login in logins and logins[login]!=key:collisions.update((key,logins[login]))
                            collected.setdefault(key,item)
                            if login:logins.setdefault(login,key)
                    except Exception as error:
                        report['department_failure']+=1;report['failures'].append({'department_id':dept['id'],'department_name':dept['name'],'parent_department':next((d['name'] for d in depts if d['id']==dept['parent_id']),''),'error':str(error) if isinstance(error,org_directory.DirectoryError) else type(error).__name__})
                    if (report['department_success']+report['department_failure'])%25==0:save()
            report['unique_employees']=len(collected);report['identity_conflicts']=len(collisions)
            bydept={}
            for key,item in collected.items():
                if key not in collisions:bydept.setdefault(item['department_id'],[]).append(item)
            for dept,items in bydept.items():
                try:
                    with closing(factory()) as db:sync_directory(db,user,dept,items)
                    report['imported_employees']+=len(items)
                except Exception as error:
                    report['failures'].append({'department_id':dept,'error':str(error) if isinstance(error,ValueError) else type(error).__name__})
            # Absence does NOT prove retirement. Preserve accounts/documents and flag review only.
            with closing(factory()) as db:
                for row in db.execute("SELECT employee_id,department_id FROM org_employees WHERE source='org_api' AND active=1"):
                    if row['department_id'] in successful and row['employee_id'] not in collected:report['missing_staff_review']+=1
        state='partial' if report['failures'] or report['identity_conflicts'] else 'completed';save(state)
        with closing(factory()) as db:audit(db,user,'전체 조직도 동기화',str(runid),json.dumps({k:v for k,v in report.items() if k!='failures'}));db.commit()
    except Exception as error:
        report['error']=str(error) if isinstance(error,(org_directory.DirectoryError,ValueError)) else type(error).__name__;save('failed')
    return dict(run_id=runid,report=report)

def start_directory_synchronization(factory,user,employees=False):
    if __import__('os').environ.get('VERCEL'):
        raise ValueError('전체 조직도 정기 동기화는 승인된 내부 서버에서 tools/sync_internal_organization.py로 실행하세요. Vercel 요청 종료 뒤 백그라운드 작업을 성공한 것처럼 표시하지 않습니다. 부서별 직원 조회와 동기화된 전체 직원 검색은 그대로 사용할 수 있습니다.')
    with closing(factory()) as db:
        if db.execute("SELECT 1 FROM org_sync_runs WHERE state='running'").fetchone():raise ValueError('이미 조직도 동기화가 진행 중입니다.')
    if not _lock.acquire(blocking=False):raise ValueError('이미 조직도 동기화가 진행 중입니다.')
    def worker():
        try:run(factory,user,employees)
        finally:_lock.release()
    threading.Thread(target=worker,daemon=True).start()
    return {'state':'started','notice':'진행 결과는 동기화 상태에서 확인하세요.'}

if __name__=='__main__':
    import argparse; from batontouch.server import application as app
    parser=argparse.ArgumentParser(description='승인된 조직정보 정기 동기화. 작업 스케줄러에서 실행합니다.')
    parser.add_argument('--employees',action='store_true');args=parser.parse_args()
    print(json.dumps(run(app.connect,{'id':0},args.employees),ensure_ascii=True))

# 이전 확장 모듈·도구와의 호출 호환성.
run = synchronize_staff_directory
start = start_directory_synchronization
