"""가상 원본만 허용하는 직원 화면 실제 AI 정책. 운영 자료 전송 승인은 별도."""
import os,json,hashlib,time
from functools import lru_cache
from contextlib import closing
class PolicyError(ValueError):
 http_status=403
QUESTIONS={'3월에 해야 할 일은?','교육 일정에 충돌이 있나요?','현재 진행 중인 현안은 무엇인가요?','협의가 필요한 부서는 어디인가요?','예산 잔액은 얼마인가요?'}
def settings():
 live=os.environ.get('BATON_STAFF_AI_MODE','mock')=='live'
 return {'mode':'live' if live else 'mock','scope':'verified-fictional-only','model':os.environ.get('GEMINI_MODEL',''),'key':os.environ.get('GEMINI_API_KEY','')}
def active():return settings()['mode']=='live' and os.environ.get('BATON_STAFF_FICTIONAL_ALLOWED')=='true'
@lru_cache(maxsize=1)
def approved_sources():
 import gemini_verification
 return {d['name']:json.loads(d['sources']) for d in gemini_verification.documents()}
def authorize(documents,actor,question):
 if not active():raise PolicyError('실제 AI 외부 전송이 비활성화되어 있습니다. 운영 자료 전송 승인을 별도로 확인하세요.')
 if not isinstance(actor,dict) or type(actor.get('id')) is not int or actor['id']<=0 or not isinstance(actor.get('username'),str) or not actor['username'].strip() or actor.get('active',True) is False or actor.get('active',True)==0 or actor.get('must_change_password',False):raise PolicyError('AI 사용을 위해 정상 로그인과 최초 비밀번호 변경이 필요합니다.')
 # 사용자 이름 허용목록 대신 서버의 인증 신원을 사용한다. 자료의 승인 범위 검사는 아래에서 그대로 수행한다.
 cfg=settings()
 if not cfg['key'] or cfg['model']!='gemini-3.1-flash-lite':raise PolicyError('서버의 Gemini 키 또는 검증 모델 설정이 준비되지 않았습니다.')
 if question is not None and question not in QUESTIONS:raise PolicyError('개인정보 전송 방지를 위해 승인된 가상 질문만 허용합니다: '+ ' / '.join(sorted(QUESTIONS)))
 approved=approved_sources();clean=[]
 if not 1<=len(documents)<=3:raise PolicyError('검증된 가상 PDF·XLSX·HWPX 원본을 1~3개 선택하세요.')
 for doc in documents:
  name=doc['name'];sources=json.loads(doc['sources'])
  if name not in approved or sources!=approved[name]:raise PolicyError('승인되지 않은 원본입니다. 공개 테스트에서는 제공된 가상 드론 자료만 Gemini에 전송할 수 있습니다. 일반 업무자료는 차단했습니다.')
  clean.append({'id':doc['id'],'name':name,'revision':doc['revision'] if 'revision' in doc.keys() else 1,'sources':json.dumps(sources,ensure_ascii=False)})
 return clean,cfg

def generate(documents,actor,question=None):
 import app,gemini_engine
 clean,cfg=authorize(documents,actor,question);feature='qa' if question is not None else 'draft'
 with closing(app.connect()) as db:
  db.execute('CREATE TABLE IF NOT EXISTS staff_ai_usage(id INTEGER PRIMARY KEY,user_id INTEGER,feature TEXT,day TEXT DEFAULT CURRENT_DATE,state TEXT,model TEXT,tokens INTEGER DEFAULT 0)')
  count=db.execute('SELECT COUNT(*) FROM staff_ai_usage WHERE user_id=? AND day=CURRENT_DATE',(actor['id'],)).fetchone()[0]
  if count>=10:raise PolicyError('가상자료 실제 AI의 하루 10회 요청 한도에 도달했습니다. 실패도 한도에 포함됩니다.')
  run=db.execute('INSERT INTO staff_ai_usage(user_id,feature,state,model) VALUES(?,?,?,?)',(actor['id'],feature,'started',cfg['model'])).lastrowid;db.commit()
 try:
  result=gemini_engine.generate(clean,question=question,config=cfg)
 except Exception:
  with closing(app.connect()) as db:db.execute("UPDATE staff_ai_usage SET state='failed' WHERE id=?",(run,));db.commit()
  raise
 with closing(app.connect()) as db:
  db.execute("UPDATE staff_ai_usage SET state='success',tokens=? WHERE id=?",(result.get('usage',{}).get('totalTokenCount',0),run));db.commit()
 result['transmission_scope']='verified-fictional-only';result['source_policy']='업로드한 가상 원본만 전송. 직접 수정한 검토본문·자유 입력은 외부 전송에서 제외.'
 return result
