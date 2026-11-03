"""Actual deployed browser audit. Credentials are environment-only; no application changes.
Run: TEST_PASSWORD=... python tools/browser-audit/run_browser_tests.py
Optional RECEIVER_USERNAME / RECEIVER_TEST_PASSWORD allow receiver verification.
"""
import os,sys,json,re,time,zipfile,hashlib,traceback,importlib.metadata
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit,urlunsplit
ROOT=Path(__file__).resolve().parents[2] if Path(__file__).parent.name=='browser-audit' else Path.cwd()
if (ROOT/'.ui-tools').exists():sys.path.insert(0,str(ROOT/'.ui-tools'))
from playwright.sync_api import sync_playwright
BASE=os.environ.get('TEST_BASE_URL','https://botontouch-test.vercel.app').rstrip('/')
PASSWORD=os.environ.get('TEST_PASSWORD','')
RECEIVER=os.environ.get('RECEIVER_USERNAME','')
RECEIVER_PASSWORD=os.environ.get('RECEIVER_TEST_PASSWORD','')
OUT=Path(os.environ.get('TEST_REPORT_DIR',str(ROOT/'artifacts'/'botontouch-browser-audit')))
STAMP=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')
TITLE='[가상 브라우저 검증] 사무용품 관리 '+datetime.now().strftime('%Y%m%d-%H%M%S')
results=[];issues=[];console_errors=[];api_errors=[];request_failures=[];network=[];layouts=[];notes=[]
step_name='준비';contexts=[];pages=[];secret_values=[x for x in (PASSWORD,RECEIVER_PASSWORD,os.environ.get('OTHER_TEST_PASSWORD','')) if x]
MOCK='MOCK';workspace_id=None;draft_id=None;request_id=None

def redact(value):
 s=str(value)
 for secret in secret_values:s=s.replace(secret,'[비밀값 삭제]')
 s=re.sub(r'(?i)(authorization|cookie|set-cookie|api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s,;]+',r'\1=[삭제]',s)
 s=re.sub(r'AIza[\w-]{20,}|sk-[\w-]{20,}|eyJ[\w-]+\.[\w-]+\.[\w-]+','[인증값 삭제]',s)
 s=re.sub(r'https?://[^\s\)\]"<>]+',lambda m:safe_url(m.group(0)),s)
 return s[:3500]

def safe_url(value):
 try:
  p=urlsplit(value);return urlunsplit((p.scheme,p.hostname or '',p.path,'',p.fragment if p.fragment in ('home','journey','inbox','sent','files','guide','settings','accounts','password') else ''))
 except Exception:return '[URL 확인 불가]'

def shot(page,name):
 path=OUT/'screenshots'/name
 try:
  page.screenshot(path=str(path),full_page=True,mask=[page.locator('input[type=password],input[name*=token i],#bootstrap-token,#staff-admin-reauth')],timeout=20000,animations='disabled')
  return 'screenshots/'+name
 except Exception as e:
  issues.append({'severity':'보통','category':'증거 수집','step':step_name,'url':safe_url(page.url),'expected':'화면 캡처 저장','actual':redact(e),'reproduction':[step_name],'screenshot':None});return None

def layout(page,name):
 try:
  data=page.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,height:innerHeight,text:document.body.innerText.trim().length,loading:[...document.querySelectorAll('[role=status]')].filter(e=>e.offsetParent!==null).map(e=>e.textContent).filter(t=>/불러오|처리 중|저장 중/.test(t)).slice(0,8)})")
  layouts.append({'step':name,'url':safe_url(page.url),**data})
  if data['scroll']>data['width']+2:issues.append({'severity':'보통','category':'화면 가로 넘침','step':name,'url':safe_url(page.url),'expected':'가로 스크롤 없이 주요 기능 사용','actual':f"화면 {data['width']}px / 문서 {data['scroll']}px",'reproduction':[name],'screenshot':None})
  if data['text']<30:raise RuntimeError('본문이 거의 없는 빈 화면입니다.')
 except Exception as e:notes.append(redact(e))

def run_step(key,name,page,action,expected,steps,filename=None,dependencies=True,mock=False):
 global step_name
 step_name=name;start=time.monotonic();entry={'id':key,'name':name,'status':'BLOCKED','url':safe_url(page.url) if page else BASE,'steps':steps,'expected':expected,'actual':'','screenshots':[],'duration_seconds':0}
 if not dependencies:entry['actual']='선행 기능 실패 또는 필요한 가상 계정/자료 미제공으로 실행하지 않았습니다.'
 else:
  try:
   detail=action() or '화면과 동작 확인 완료'
   entry.update(status='MOCK' if mock else 'PASS',actual=redact(detail),url=safe_url(page.url))
  except Exception as e:
   entry.update(status='FAIL',actual=redact(str(e) or type(e).__name__),url=safe_url(page.url));error_shot=shot(page,'error-'+key+'.png') if page else None
   if error_shot:entry['screenshots'].append(error_shot)
   issues.append({'severity':'높음' if key in ('01','04','05','07','10','14') else '보통','category':'기능 실행 실패','step':name,'url':entry['url'],'expected':expected,'actual':entry['actual'],'reproduction':steps,'screenshot':error_shot})
  if page:
   if filename:
    captured=shot(page,filename)
    if captured:entry['screenshots'].append(captured)
   layout(page,name)
 entry['duration_seconds']=round(time.monotonic()-start,2);results.append(entry)
 print(json.dumps({'id':key,'status':entry['status']},ensure_ascii=False),flush=True)
 return entry['status'] in ('PASS','MOCK')

def wait_idle(page):page.wait_for_function("typeof state!=='undefined' && !state.busy.size && !journeyCreating",timeout=60000)

def attach(page,actor):
 pages.append(page)
 def response(r):
  if not r.url.startswith(BASE):return
  row={'time':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),'step':step_name,'actor':actor,'method':r.request.method,'url':safe_url(r.url),'status':r.status}
  network.append(row)
  if r.status>=400:api_errors.append({**row,'expected':(r.status==401 and ('/favicon.ico' in r.url or step_name.startswith('로그아웃'))) or (r.status==403 and '권한' in step_name)})
 def failed(r):request_failures.append({'step':step_name,'actor':actor,'method':r.method,'url':safe_url(r.url),'reason':redact(r.failure or '원인 확인 불가')})
 page.on('response',response);page.on('requestfailed',failed)
 page.on('console',lambda m:console_errors.append({'step':step_name,'actor':actor,'type':m.type,'message':redact(m.text),'url':safe_url(page.url)}) if m.type in ('error','warning') else None)
 page.on('pageerror',lambda e:console_errors.append({'step':step_name,'actor':actor,'type':'javascript-exception','message':redact(e),'url':safe_url(page.url)}))
 page.set_default_timeout(45000);page.set_default_navigation_timeout(60000)

def login(page,username,password):
 page.goto(BASE+'/login',wait_until='load');page.locator('#auth-username').fill(username);page.locator('#auth-password').fill(password)
 # Password inputs are masked even when capturing a failure.
 page.locator('#auth-submit').click();page.wait_for_function("!!document.querySelector('#staff-profile')?.textContent",timeout=60000)
 page.locator('#journey-start').wait_for(state='visible');page.wait_for_function("!document.querySelector('#journey-start').disabled",timeout=60000)
 assert page.evaluate('account.user.username')==username,'서버에서 확인한 로그인 계정 불일치';return '가상 직원 로그인 성공. 서버 검증 후 홈과 직원정보 표시.'

def ready_draft(page):page.locator('#editor').wait_for(state='visible');wait_idle(page)

def make_report(environment):
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'screenshots').mkdir(exist_ok=True);(OUT/'errors').mkdir(exist_ok=True)
 # Visible contradictory language is a finding even when the mock backend works.
 counts={s:sum(r['status']==s for r in results) for s in ('PASS','FAIL','BLOCKED','MOCK')}
 data={'tested_at':STAMP,'finished_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),'base_url':BASE,'environment':environment,'summary':counts,'tests':results,'issues':issues,'layout_checks':layouts,'console_errors':console_errors,'api_errors':api_errors,'request_failures':request_failures,'network_metadata':network,'notes':notes,'privacy':{'password_source':'TEST_PASSWORD 환경변수','request_response_bodies_recorded':False,'cookies_tokens_recorded':False,'har_trace_video_created':False,'password_inputs_masked':True,'data':'새 가상 업무만 생성. 기존 문서 수정·삭제 없음. 실제 AI 호출 없음.'},'created_test_data':{'title':TITLE,'workspace_id':workspace_id,'draft_id':draft_id,'request_id':request_id}}
 (OUT/'test-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 for file,items in [('console-errors.txt',console_errors),('api-errors.txt',api_errors),('request-failures.txt',request_failures)]:
  (OUT/'errors'/file).write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in items) if items else '기록된 오류 없음\n',encoding='utf-8')
 lines=['# 바통터치 실제 배포 브라우저 테스트 보고서','',f'- 시작: {STAMP}',f'- 종료: {data["finished_at"]}',f'- 배포 URL: {BASE}/login',f'- 환경: {json.dumps(environment,ensure_ascii=False)}','- 브라우저 창을 화면에 띄우지 않는 headless 방식이며 실제 렌더링·클릭·입력·파일 업로드를 수행했습니다.','- MOCK은 화면 흐름만 검증한 모의 응답입니다. 실제 Gemini 분석 성공을 의미하지 않습니다.','- 스크린샷의 비밀번호 입력란을 가렸고 요청 본문·응답 원문·쿠키·인증 토큰·HAR·추적 파일을 저장하지 않았습니다.','- 테스트 DB에 새 가상 문서·요청을 추가했습니다. 기존 문서 및 로컬 운영 DB는 변경하지 않았습니다.','',f'## 결과: {counts}','', '| 번호 | 실제 실행한 항목 | 결과 | 관찰 | 증거 |','|---|---|---|---|---|']
 for r in results:
  clean=lambda x:str(x).replace('|',' / ').replace('\n',' ')[:550]
  lines.append('| '+' | '.join([r['id'],r['name'],r['status'],clean(r['actual']),', '.join(r['screenshots']) or '없음'])+' |')
 lines+=['','## 오류 상세와 재현 방법','']
 if not issues:lines.append('기능 테스트에서 재현된 오류 없음. 네트워크·콘솔 기록은 errors 폴더와 JSON에서 별도로 확인하세요.')
 for i,issue in enumerate(issues,1):
  lines += [f'### {i}. [{issue["severity"]}] {issue["category"]}: {issue["step"]}','',f'- URL: {issue["url"]}',f'- 재현: {" → ".join(issue["reproduction"])}',f'- 예상: {issue["expected"]}',f'- 실제: {issue["actual"]}',f'- 증거: {issue.get("screenshot") or "관련 단계 스크린샷/오류 로그 참조"}','']
 lines += ['','## 수정이 필요한 부분 및 UX 개선 의견','']
 for issue in issues:lines.append(f'- [{issue["severity"]}] {issue["category"]}: {issue["step"]}에서 확인된 현상을 우선 검토하세요. 이번 작업에서는 수정하지 않았습니다.')
 lines += ['- 모의 모드의 안내와 실제 전송 여부를 모든 AI 설명·버튼·결과 영역에서 일치시키는지 확인하세요.','- 일반 직원이 로그아웃 버튼을 쉽게 찾을 수 있는지 확인하세요.','- 자료 선택, 생성 중 상태, 저장 완료와 요청 완료의 구분을 스크린샷으로 검토하세요.','- 자동 레이아웃 검사는 가로 넘침·빈 본문을 중심으로 수행했습니다. 색상 대비·화면 읽기 도구·모든 모바일 기기의 사용성까지 보장하지 않습니다.','','## 실행 절차 및 한계','']
 for r in results:lines += [f'### {r["id"]}. {r["name"]}',*['- '+x for x in r['steps']],f'- 기대 결과: {r["expected"]}',f'- 실제: {r["actual"]}','']
 lines += ['## 참고','',*['- '+x for x in notes],'- errors/api-errors.txt에는 HTTP 오류 상태만, errors/console-errors.txt에는 비밀값을 지운 브라우저 오류·경고만 기록했습니다. 일반 네트워크 메타데이터는 JSON에 있습니다.','- 실제 한컴오피스 문서 열기는 이번 검증 범위에 포함하지 않았습니다.','- 실제 기관 조직도·실제 직원 계정·실제 AI·운영 부하는 검증하지 않았습니다.']
 (OUT/'test-report.md').write_text('\n'.join(lines),encoding='utf-8')
 # Include a reusable runner, with no secrets or browser storage state.
 (OUT/'run_browser_tests.py').write_text(Path(__file__).read_text(encoding='utf-8-sig'),encoding='utf-8')
 (OUT/'실행방법.md').write_text('''# 재실행 방법\n\nPython과 Playwright가 필요합니다.\n\n```powershell\npython -m pip install playwright\npython -m playwright install chromium\n$env:TEST_BASE_URL="https://botontouch-test.vercel.app"\n# 아래 입력은 화면에 비밀번호를 표시하지 않습니다.\n$secret=Read-Host "테스트 계정 비밀번호" -AsSecureString\n$env:TEST_PASSWORD=[System.Net.NetworkCredential]::new("",$secret).Password\npython run_browser_tests.py\nRemove-Item Env:TEST_PASSWORD\n```\n\n인수자 계정은 RECEIVER_USERNAME 및 RECEIVER_TEST_PASSWORD 환경변수가 모두 있을 때만 테스트합니다. 비밀번호를 코드나 보고서에 기록하지 마세요.\nTEST_BROWSER_EXECUTABLE 환경변수로 설치된 Chrome/Edge 실행 파일을 지정할 수 있습니다.\n기본 Chromium 설치가 안 될 경우 설치된 Chrome을 사용하며 실제 브라우저 종류를 보고서에 기록합니다.\nTEST_REPORT_DIR로 결과 폴더를 지정할 수 있습니다.\n''',encoding='utf-8')
 # Verify textual artifacts contain none of the credential values before creating ZIP.
 for file in OUT.rglob('*'):
  if file.is_file() and file.suffix in ('.md','.txt','.json','.py'):
   content=file.read_text(encoding='utf-8-sig')
   if any(secret in content for secret in secret_values):raise RuntimeError('비밀값 검출: ZIP 생성을 중단했습니다.')
 target=OUT.parent/'botontouch-recipient-regression.zip'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
  for file in OUT.rglob('*'):
   if file.is_file() and '__pycache__' not in file.parts:archive.write(file,file.relative_to(OUT).as_posix())
 with zipfile.ZipFile(target) as archive:
  assert archive.testzip() is None
 print(json.dumps({'zip':str(target),'summary':counts,'screenshots':len(list((OUT/'screenshots').glob('*.png'))),'issues':len(issues)},ensure_ascii=False),flush=True)


def main():
 global workspace_id,draft_id,request_id,step_name
 for name in ('screenshots','errors'):(OUT/name).mkdir(parents=True,exist_ok=True)
 environment={'playwright':importlib.metadata.version('playwright'),'os':sys.platform,'viewport':'1440x1050','browser':'미실행','credentials':'환경변수만 사용'}
 if not PASSWORD:
  run_step('01','로그인',None,lambda:None,'로그인 성공',['TEST_PASSWORD 환경변수 설정'],dependencies=False);notes.append('TEST_PASSWORD가 설정되지 않아 브라우저를 실행하지 않았습니다.');make_report(environment);return
 os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'.ui-tools/browsers'))
 try:
  with sync_playwright() as p:
   chromium=Path(p.chromium.executable_path);exe=os.environ.get('TEST_BROWSER_EXECUTABLE')
   if not exe and not chromium.exists():
    exe='C:/Program Files/Google/Chrome/Application/chrome.exe';notes.append('Playwright 전용 Chromium 다운로드가 ECONNRESET으로 실패하여 설치된 Google Chrome(Chromium 엔진)을 사용했습니다. 인증서 검증 또는 네트워크 정책은 변경하지 않았습니다.')
   browser=p.chromium.launch(**({'executable_path':exe} if exe else {}),headless=True)
   environment.update(browser=('Google Chrome (Chromium 엔진)' if exe and 'chrome' in exe.lower() else 'Chromium'),browser_version=browser.version)
   context=browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True);contexts.append(context);a=context.new_page();attach(a,'인계자')
   def login_page():a.goto(BASE+'/login',wait_until='load');a.locator('#auth-form').wait_for(state='visible');return '로그인 입력란과 버튼 표시'
   reached=run_step('00','로그인 페이지 접속',a,login_page,'로그인 폼 표시',['배포 URL /login 접속'],'01-login.png')
   logged=run_step('01','로그인',a,lambda:login(a,'demo.a',PASSWORD),'demo.a 로그인 후 메인 이동',['아이디 demo.a 입력','환경변수 비밀번호 입력','로그인 클릭'],'02-dashboard.png',reached)
   def dashboard():
    assert a.locator('#journey-start').is_visible();assert a.locator('#journey-dashboard-counts').inner_text();
    body=a.locator('body').inner_text()
    if '이 PC에' in body and '별도 테스트 DB' in body:issues.append({'severity':'보통','category':'저장 위치 안내 불일치','step':'대시보드 안내','url':safe_url(a.url),'expected':'실제 배포본의 공유 테스트 DB 저장을 일관되게 안내','actual':'별도 테스트 DB 저장 안내와 로컬·이 PC 저장 안내가 함께 표시됨','reproduction':['로그인 후 대시보드','왼쪽 하단과 본문 하단의 저장 위치 안내 비교'],'screenshot':'screenshots/02-dashboard-main.png'})
    return '시작 버튼·현황 카드 표시'
   run_step('02','메인 화면 확인',a,dashboard,'업무 중심 대시보드 표시',['로그인 후 대시보드 카드 확인'],'02-dashboard-main.png',logged)
   if logged:
    menu_data=[]
    for link in a.locator('#sidebar a[href^="#"]').all():
     if link.is_visible():menu_data.append((link.get_attribute('href'),link.inner_text().strip()))
    for index,(href,label) in enumerate(dict(menu_data).items(),1):
     def menu(href=href,label=label):
      a.locator('#sidebar a[href="'+href+'"]').first.click();a.wait_for_function('(hash)=>location.hash===hash',arg=href);wait_idle(a);return label+' 메뉴 이동 및 본문 확인'
     run_step('03-'+str(index),'사이드바: '+label,a,menu,'선택한 메뉴에 맞는 화면 표시',['사이드바 '+label+' 클릭','이동 경로 및 본문 확인'],'03-sidebar-'+str(index)+'.png')
    a.locator('#sidebar a[href="#home"]').first.click()
   else:run_step('03','사이드바 전체 메뉴',a,lambda:None,'각 메뉴 이동',['사이드바 메뉴 클릭'],dependencies=False)
   def start():
    a.locator('#journey-start').click();a.locator('#journey-title').fill(TITLE);a.locator('#journey-prepare').click();a.wait_for_function("!state.busy.size&&!journeyCreating&&!document.querySelector('#journey-files').hidden");return '새 가상 업무 생성 후 자료 등록 단계 표시'
   created=run_step('04','인수인계 시작하기',a,start,'새 가상 업무와 자료 등록 화면',['홈 → 인수인계 시작하기','고유한 가상 업무명 입력','업무 저장하고 자료 등록 클릭'],'04-handover-start.png',logged)
   if created:workspace_id=a.evaluate('state.workspace')
   def upload():
    a.locator('#upload').set_input_files({'name':'가상-사무용품-업무자료.txt','mimeType':'text/plain','buffer':'[가상 테스트 문서] 사무용품은 매월 첫째 주에 수량을 확인합니다. 부족한 품목을 목록으로 정리합니다. 구매 전 가상 담당팀과 예산을 확인합니다. 다음 담당자는 구매 기록을 확인해야 합니다.'.encode()});a.locator('#submit').click();a.wait_for_function("state.docs.length===1&&!state.busy.size");assert a.locator('#files').inner_text();return '새 업무에 가상 TXT 1건 등록, 추출 결과 표시'
   uploaded=run_step('05','가상 파일 업로드·텍스트 확인',a,upload,'가상 자료 1건과 추출 본문 표시',['가상 TXT 파일 선택','선택한 자료 등록 클릭','자료함 목록과 추출 결과 확인'],'05-file-upload.png',created)
   def generate():
    a.locator('#journey-next').click();a.locator('#draft-choices input').first.check();a.locator('#generate').click();ready_draft(a)
    value=a.evaluate('({model:state.draft.model,mode:state.draft.mode,items:state.draft.items.length})');assert value['mode']=='mock';assert value['items']>0;return '모의 초안 표시. 실제 AI 미호출. '+value['model']
   ai_status=a.request.get(BASE+'/api/demo/status').json()
   mock_allowed=ai_status.get('ai_mode')=='mock' and ai_status.get('external_transmission_allowed') is False
   environment['ai_mode']=ai_status.get('ai_mode');environment['external_transmission_allowed']=ai_status.get('external_transmission_allowed')
   generated=run_step('06','AI 초안 생성',a,generate,'실제 AI와 구분된 모의 초안 표시',['2단계로 이동','가상 자료 선택','AI 초안 작성 클릭','결과 확인'],'05-ai-draft.png',uploaded and mock_allowed,mock=True)
   if generated:draft_id=a.evaluate('state.draft.id')
   def folded():
    assert not a.locator('#journey-optional-tools').evaluate('e=>e.open')
    original=a.locator('#draft-items textarea').first.input_value()
    a.locator('#journey-optional-tools > summary').click();a.locator('#journey-optional-tools > summary').click()
    assert a.locator('#draft-items textarea').first.input_value()==original
    assert a.locator('#editor').is_visible();assert '모의 AI 응답' in a.locator('body').inner_text();assert 'Gemini' not in a.locator('body').inner_text()
    return '문서 편집과 선택 기능 분리, 기본 접힘 및 접기·펼치기 후 입력 보존'
   run_step('06b','편집·질문 분리 및 접기·펼치기',a,folded,'편집 유지 및 선택 기능만 펼침',['편집 화면과 선택 기능 구분 확인','선택 기능 펼치고 다시 접기','기존 입력 보존 확인'],'05-progressive-editor.png',generated)
   edited_text='[가상 검증] 매주 사무용품 수량을 확인하고 부족한 품목을 구매 목록에 기록합니다.'
   def edit():
    a.locator('#draft-title').fill(TITLE);a.locator('#draft-items textarea').first.fill(edited_text);a.wait_for_function("!state.draftDirty&&document.querySelector('#journey-save-state').textContent.startsWith('마지막 저장')");a.locator('#journey-save').click();wait_idle(a);a.reload();ready_draft(a);assert a.locator('#draft-items textarea').first.input_value()==edited_text,'수정 본문이 새로고침 후 일치하지 않음';assert a.locator('#draft-title').input_value()==TITLE,'수정 제목이 새로고침 후 일치하지 않음';return '가상 문장·제목 수정 후 자동/임시 저장 및 새로고침 복원 확인'
   edited=run_step('07','작성 내용 수정·저장',a,edit,'수정 내용과 마지막 저장 시각 유지',['초안 첫 항목 직접 수정','자동 저장 완료 대기','임시저장 클릭'],'06-ai-review.png',generated)
   def suggested():
    details=a.locator('#journey-source-questions').locator('..');details.locator(':scope > summary').click();a.locator('#expected-questions-panel > summary').click();a.locator('#question-choices input').first.check();a.locator('#suggest-questions').click();a.wait_for_function("state.suggestions?.questions?.length>=10&&!state.busy.size");
    if 'Gemini로 전송' in a.locator('#journey-source-questions').inner_text():issues.append({'severity':'보통','category':'안내 문구 불일치','step':'모의 AI 예상질문 화면','url':safe_url(a.url),'expected':'모의 모드에서는 실제 외부 전송이 없다는 설명을 일관되게 표시','actual':'모의 AI 안내와 선택 원문이 Gemini로 전송된다는 안내가 함께 표시됨','reproduction':['AI 초안 단계에서 자료에 질문하기 펼치기','AI 예상질문 생성','전송 안내와 테스트 모드 안내 비교'],'screenshot':'screenshots/06-ai-questions.png'})
    return '모의 예상질문 '+str(a.evaluate('state.suggestions.questions.length'))+'건 표시'
   run_step('08a','AI 예상 질문 생성',a,suggested,'모의 예상질문 목록 표시',['자료에 질문하기 펼치기','가상 자료 선택','AI 예상질문 생성 클릭'],'06-ai-questions.png',generated,mock=True)
   def gap():
    a.locator('#journey-next').click();a.locator('#journey-gap-check').click();a.locator('#journey-gap-list .journey-question').first.wait_for();wait_idle(a);return '모의 누락 확인 질문 표시. 실제 AI 분석 아님.'
   gaps=run_step('08b','AI 누락사항 점검',a,gap,'모의 누락 확인 질문 표시',['3단계 이동','AI 누락사항 점검 클릭'],'06-ai-gap-check.png',generated,mock=True)
   def answer():
    card=a.locator('#journey-gap-list .journey-question').first;card.locator('textarea').fill('가상 다음 구매 일정은 다음 달 첫째 주입니다.');card.get_by_role('button',name='답변 저장',exact=True).click();a.locator('#journey-gap-list').get_by_role('button',name='AI 반영안 미리보기',exact=True).first.click();a.locator('#journey-proposal-dialog').wait_for(state='visible');assert a.evaluate('state.draft.items[0].text')==edited_text;shot(a,'06-ai-answer-preview.png');a.locator('#journey-proposal-after').fill(edited_text+' 가상 다음 구매는 다음 달 첫째 주입니다.');a.locator('#journey-proposal-apply').click();a.locator('#journey-proposal-dialog').wait_for(state='hidden');wait_idle(a);return '사용자 적용 전 원본 유지, 모의 반영안을 직접 수정·승인 후 적용'
   run_step('08c','답변·미리보기·사용자 선택 적용',a,answer,'미리보기 전 원본 유지 및 승인 후 반영',['질문에 가상 답변 입력','답변 저장','반영안 미리보기','직접 수정 후 적용'],'06-ai-answer-applied.png',gaps and edited,mock=True)
   def recipient():
    a.locator('#journey-next').click();a.locator('#recipient-department').select_option('DEMO-AI')
    a.locator('#recipient-employee option[value="DEMO-SAME-A"]').wait_for(state='attached')
    assert a.locator('#recipient-employee option[value="DEMO-GLOBAL"]').count()==0
    a.locator('#recipient-search').fill('가상 빅데이터 직원')
    a.locator('#recipient-employee option[value="DEMO-GLOBAL"]').wait_for(state='attached')
    assert '빅데이터팀' in a.locator('#recipient-employee option[value="DEMO-GLOBAL"]').inner_text()
    a.locator('#recipient-employee').select_option('DEMO-GLOBAL')
    assert a.locator('#recipient-department').input_value()=='DEMO-BIGDATA'
    shot(a,'07-global-search-auto-department.png')
    a.locator('#recipient-search').fill('')
    a.wait_for_function("!document.querySelector('#recipient-employee').disabled && !!document.querySelector('#recipient-employee option[value=\"DEMO-SAME-B\"]')")
    assert a.locator('#recipient-employee option[value="DEMO-SAME-A"]').count()==0
    shot(a,'07-search-cleared-department-list.png')
    a.locator('#recipient-search').fill('동명이인')
    a.locator('#recipient-employee option[value="DEMO-SAME-A"]').wait_for(state='attached')
    a.locator('#recipient-employee option[value="DEMO-SAME-B"]').wait_for(state='attached')
    assert 'AI전략팀' in a.locator('#recipient-employee option[value="DEMO-SAME-A"]').inner_text()
    assert '빅데이터팀' in a.locator('#recipient-employee option[value="DEMO-SAME-B"]').inner_text()
    shot(a,'07-duplicate-names.png')
    a.locator('#recipient-search').fill('가상 빅데이터 직원');a.locator('#recipient-employee option[value="DEMO-GLOBAL"]').wait_for(state='attached');a.locator('#recipient-employee').select_option('DEMO-GLOBAL')
    assert a.locator('#recipient-department').input_value()=='DEMO-BIGDATA'
    return 'AI전략팀 선택 → 전체 검색 API로 빅데이터팀 직원 조회 → 실제 소속 자동 변경 → 검색 초기화 시 해당 부서 복원 → 동명이인 구분 확인'
   selected=run_step('09','인수받을 부서·직원 선택',a,recipient,'전체 검색과 실제 소속 자동 변경',['4단계 이동','가상 업무지원팀 선택','가상 인수자 선택'],'07-recipient-select.png',gaps)
   def send():
    a.locator('#journey-next').click();a.locator('#journey-final-reviewed').check();a.locator('#send-handover').click();shot(a,'08-send-confirmation.png');a.locator('#confirm-accept').click();a.locator('#request-detail-panel').wait_for(state='visible');a.wait_for_function("requestSelection?.state==='requested'");environment['recipient_pending_at_send']=a.evaluate('requestSelection.recipient_account_pending');return '요청 발송 후 인수 요청 상태와 상세 화면 표시'
   sent=run_step('10','인수인계 요청 발송',a,send,'새 요청 생성 및 인수 요청 상태 표시',['5단계 최종 문서 검토','직접 확인 체크','인수인계 요청하기','확인창 승인'],'08-request-sent.png',selected)
   if sent:request_id=a.evaluate('requestSelection.id')
   def sent_list():
    a.locator('#navigation a[href="#sent"]').click();a.locator('#reload-sent-requests').click();a.wait_for_function('(title)=>document.querySelector("#sent-requests").textContent.includes(title)',arg=TITLE);return '내가 생성한 가상 업무가 보낸 목록에 표시'
   run_step('11','보낸 목록·처리 상태 확인',a,sent_list,'새 가상 요청이 보낸 목록에 표시',['보낸 인수인계 메뉴 클릭','목록 새로고침','이번 가상 업무 제목 확인'],'09-sent-list.png',sent)
   def received_a():
    a.locator('#navigation a[href="#inbox"]').click();a.locator('#received-requests').wait_for(state='visible');wait_idle(a);return '인계자 계정의 받은 요청함 표시(수신 내역 없음도 정상). 인수자 수신 확인은 별도 테스트.'
   run_step('12a','demo.a 받은 목록 확인',a,received_a,'본인 받은 요청함만 표시',['받은 인수인계 클릭'],'10-received-list.png',logged)
   b=None
   if RECEIVER and RECEIVER_PASSWORD:
    bc=browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True);contexts.append(bc);b=bc.new_page();attach(b,'인수자')
   def received_b():
    login(b,RECEIVER,RECEIVER_PASSWORD);b.locator('#navigation a[href="#inbox"]').click();b.wait_for_function('(title)=>document.querySelector("#received-requests").textContent.includes(title)',arg=TITLE);b.locator('#received-requests').get_by_role('button').filter(has_text=TITLE).first.click();b.locator('#request-detail-panel').wait_for(state='visible');assert b.evaluate('account.user.employee.employee_id')=='DEMO-GLOBAL';assert b.evaluate('account.user.username')=='demo.global';environment['recipient_auto_mapped']=True;return '별도 가상 인수자 계정에서 이번 요청의 수신·상세 확인'
   receiver_ready=run_step('12b','별도 가상 인수자 수신 확인',b,received_b,'demo.b 받은 요청함에 이번 문서 표시',['제공된 별도 가상 계정으로 새 브라우저 로그인','받은 목록에서 이번 제목 선택'],'10-receiver-account.png',sent and bool(RECEIVER and RECEIVER_PASSWORD))
   if receiver_ready and b:shot(b,'10-receiver-detail.png')
   def menu_and_labels():
    a.locator('#navigation a[href="#home"]').click();wait_idle(a)
    body=a.locator('body').inner_text();assert '이 PC에' not in body;assert '공유 테스트 DB' in body
    assert a.locator('#user-menu > summary').is_visible()
    return '상단 사용자 메뉴와 공유 테스트 DB 안내 일치'
   run_step('16','사용자 메뉴·저장 위치 안내',a,menu_and_labels,'상단 메뉴 및 공유 DB 안내',['홈으로 이동','상단 사용자 메뉴·하단 안내 확인'],'15-user-menu-storage.png',logged)
   def accept():
    b.get_by_role('button',name='인수 수락',exact=True).click();b.locator('#confirm-accept').click();b.wait_for_function("requestSelection?.state==='accepted'")
    return '지정 인수자의 실제 UI 클릭으로 인수 수락 상태 전환'
   accepted=run_step('17','인수자 인수 수락',b,accept,'지정된 인수자가 요청 수락',['demo.b 이번 요청 상세','인수 수락 클릭','확인창 승인'],'16-accepted.png',receiver_ready)
   def complete():
    a.locator('#navigation a[href="#sent"]').click();a.locator('#reload-sent-requests').click();a.locator('#sent-requests').get_by_role('button',name=TITLE,exact=True).click();a.wait_for_function("requestSelection?.state==='accepted'")
    a.get_by_role('button',name='인수인계 완료',exact=True).click();a.locator('#confirm-accept').click();a.wait_for_function("requestSelection?.state==='completed'")
    return '인계자의 최종 완료와 확정본 생성 확인'
   completed=run_step('18','인계자 최종 완료',a,complete,'수락 후 인계자가 최종 완료',['보낸 목록 이번 요청 열기','인수인계 완료','확인창 승인'],'17-completed.png',accepted)
   def hwpx():
    import io,xml.etree.ElementTree as ET
    with a.expect_download() as dl:a.get_by_role('button',name='요청 문서 한글 내려받기',exact=True).click()
    destination=OUT/'downloads'/'fictional-handover.hwpx';destination.parent.mkdir(exist_ok=True);dl.value.save_as(destination)
    with zipfile.ZipFile(destination) as z:
     assert z.testzip() is None
     names=z.namelist();assert 'Contents/content.hpf' in names
     xmls=[n for n in names if n.endswith('.xml')]
     for name in xmls:ET.fromstring(z.read(name))
     assert any('매주 사무용품' in z.read(n).decode('utf-8','ignore') for n in xmls)
    return '실제 UI 다운로드, ZIP·XML 유효성 및 직접 수정한 가상 본문 확인. 한컴오피스 열기는 미검증.'
   run_step('19','완료 문서 HWPX 다운로드',a,hwpx,'한글 파일 다운로드 및 내용/구조 확인',['최종 완료 상세','요청 문서 한글 내려받기','ZIP·XML 검사'],'18-hwpx-download.png',completed)
   def permissions():
    user=os.environ.get('OTHER_USERNAME');password=os.environ.get('OTHER_TEST_PASSWORD')
    if not user or not password:raise RuntimeError('별도 가상 직원 C 계정 미제공')
    context_c=browser.new_context(viewport={'width':1440,'height':1050});contexts.append(context_c);c=context_c.new_page();attach(c,'다른 직원');login(c,user,password)
    paths=['/api/requests/'+str(request_id),'/api/requests/'+str(request_id)+'/export.hwpx','/api/documents']
    statuses=[]
    for path in paths:
     status=c.evaluate("async data=>{const r=await fetch(data.path,{headers:{'X-Workspace-Id':String(data.workspace)}});return r.status}",{'path':path,'workspace':workspace_id});statuses.append(status);assert status==403,'권한 없는 조회 허용: '+path
    status=c.evaluate("async id=>(await fetch('/api/requests/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,revision:1,action:'accept'})})).status",request_id);statuses.append(status);assert status==403
    shot(c,'19-other-user.png');return '직원 C의 문서 상세·HWPX·업무자료 조회·처리 요청 모두 HTTP 403 차단: '+str(statuses)
   run_step('20','직원별 접근 권한 차단',a,permissions,'관계없는 직원은 읽기·출력·처리 불가',['별도 가상 직원 demo.c 로그인','새 요청 상세·HWPX·자료 API 조회','수락 API 호출 시도'],'19-permission-check.png',sent and bool(os.environ.get('OTHER_TEST_PASSWORD')))
   def persist():
    a.locator('#navigation a[href="#sent"]').click();a.reload();a.locator('#sent-requests').wait_for(state='visible');a.wait_for_function('(title)=>document.querySelector("#sent-requests").textContent.includes(title)',arg=TITLE);return '새로고침 후 보낸 요청 제목과 상태 유지'
   run_step('13','새로고침 후 데이터 유지',a,persist,'서버 저장된 요청이 새로고침 후에도 표시',['보낸 인수인계로 이동','브라우저 새로고침','이번 요청 확인'],'11-refresh.png',sent)
   def logout():
    # Use actual UI logout only. Never substitute a direct API call silently.
    a.locator('#user-menu > summary').click()
    found=None
    for candidate in a.get_by_role('button',name='로그아웃',exact=True).all():
     if candidate.is_visible():found=candidate;break
    if found is None:
     # Existing settings page remains accessible by the actual guide/footer links if present.
     links=a.locator('a[href="#settings"]')
     visible=[x for x in links.all() if x.is_visible()]
     if visible:visible[0].click()
     else:
      password_link=a.get_by_role('link',name='비밀번호 변경',exact=True)
      if password_link.is_visible():
       captured=shot(a,'12-logout-entry.png')
       issues.append({'severity':'보통','category':'로그아웃 동선','step':'로그아웃 버튼 찾기','url':safe_url(a.url),'expected':'일반 직원 메인 또는 메뉴에서 로그아웃을 바로 발견','actual':'메인에 로그아웃이 보이지 않아 비밀번호 변경 화면을 거쳐야 함','reproduction':['일반 직원으로 로그인','메인·사이드바에서 로그아웃 찾기','상단 비밀번호 변경 → 로그아웃'],'screenshot':captured})
       password_link.click();a.locator('#password-view').wait_for(state='visible');shot(a,'12-password-page-logout.png');found=a.locator('#password-logout')
      else:raise RuntimeError('일반 직원 화면에서 로그아웃 진입 경로를 찾지 못했습니다. 직접 API 호출로 대체하지 않았습니다.')
     if found is None:found=a.get_by_role('button',name='로그아웃',exact=True)
     found.wait_for(state='visible')
    found.click();a.wait_for_url('**/login?reason=logout');assert '#password' not in a.url;a.goto(BASE+'/');a.wait_for_url('**/login');return 'UI 로그아웃 후 보호된 홈 접근 시 로그인으로 이동'
   out=run_step('14a','로그아웃·보호 화면 차단',a,logout,'로그아웃 후 로그인 화면 및 보호 화면 차단',['보이는 로그아웃 버튼 찾기·클릭','홈 다시 접속'],'12-logout.png',logged)
   run_step('14b','재로그인',a,lambda:login(a,'demo.a',PASSWORD),'재로그인 후 메인 진입',['로그아웃 이후 demo.a 재로그인'],'13-relogin.png',out)
   # Observe visible guidance without treating source inspection as evidence.
   if generated:
    for pg in pages:
     if not pg.is_closed():
      text=pg.locator('body').inner_text()
      if 'Gemini로 전송' in text and '모의' in text:
       issues.append({'severity':'보통','category':'안내 문구 불일치','step':'모의 AI 화면 안내','url':safe_url(pg.url),'expected':'모의 모드에서는 실제 외부 전송이 없다고 일관되게 안내','actual':'모의 응답 안내와 Gemini 전송 안내가 한 화면에 함께 표시됨','reproduction':['AI 예상질문/자료에 질문하기 펼치기','모의 응답 안내와 전송 안내 비교'],'screenshot':'screenshots/06-ai-questions.png'});break
   # Independent small-screen visual check; no extra data writes.
   def small():
    a.set_viewport_size({'width':390,'height':844});layout(a,'작은 화면');assert a.evaluate('document.documentElement.scrollWidth<=innerWidth+2');return '390px 화면에서 문서 가로 넘침 없음. 상세 접근성은 미검증.'
   run_step('15','작은 화면 가로 넘침',a,small,'가로 넘침 없음',['브라우저 너비 390px로 변경'],'14-mobile.png',logged)
   for c in contexts:c.close()
   browser.close()
 except Exception as e:
  notes.append('테스트 실행기 예외: '+redact(e))
  if not results:run_step('00','브라우저 실행',None,lambda:(_ for _ in ()).throw(e),'브라우저 실행',['Playwright 브라우저 시작'])
 finally:make_report(environment)

if __name__=='__main__':main()
