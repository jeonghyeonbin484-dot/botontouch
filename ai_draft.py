"""모든 작성 기능이 공통 Gemini 엔진을 사용하며 실패 시 모의 응답으로 대체하지 않는다."""
import os
import gemini_engine
from gemini_engine import validate_draft,validate_answer,validate_questions,validate_document_check,QUESTION_TYPES,CONFIG,AIServiceError

def settings():
 cfg=gemini_engine.settings();cfg['mode']=os.environ.get('AI_MODE',os.environ.get('BATON_STAFF_AI_MODE','live'));cfg['scope']=os.environ.get('BATON_AI_DATA_SCOPE','verified-fictional-only');return cfg

def generate(documents,question=None,expected_questions=False,document_check=False,gap_context=None,gap_apply_context=None,actor=None):
 cfg=settings()
 if cfg['mode']=='mock':
  import mock_ai
  return mock_ai.generate(documents,question,expected_questions,document_check,gap_context,gap_apply_context)
 if cfg['mode']!='live':raise AIServiceError('AI_MODE는 mock 또는 live로 설정하세요.',503)
 if not actor:raise AIServiceError('AI 요청자의 로그인 신원을 확인할 수 없습니다.',403)
 if not cfg['key'] or not cfg['model']:raise AIServiceError('서버의 Gemini API 키 또는 모델명이 설정되지 않았습니다.',503)
 if cfg['scope']=='verified-fictional-only':
  import staff_ai_policy
  if gap_context is not None or gap_apply_context is not None:raise AIServiceError('현재 외부 전송 범위는 검증된 가상 원문뿐입니다. 수정 문서와 답변 전송은 별도 승인 설정이 필요합니다.',403)
  if not expected_questions and not document_check:return staff_ai_policy.generate(documents,actor,question)
  documents,cfg=staff_ai_policy.authorize(documents,actor,question)
 elif cfg['scope']=='approved-materials':
  required=('AI_EXTERNAL_TRANSMISSION_ALLOWED','AI_APPROVED_WRITING_ALLOWED','BATON_AI_APPROVED_MATERIALS')
  if any(os.environ.get(k)!='true' for k in required) or not os.environ.get('AI_APPROVAL_REFERENCE','').strip():raise AIServiceError('업무자료 외부 AI 전송 승인 및 서버 자료 허용 설정이 완료되지 않았습니다. 자료는 전송하지 않았습니다.',403)
  __import__('material_transmission_policy').check(documents,question,{'gap_context':gap_context,'gap_apply_context':gap_apply_context})
 else:raise AIServiceError('허용된 AI 자료 범위가 설정되지 않았습니다.',403)
 # 기존 공통 전송 모듈의 60초 제한·503 제한 재시도·응답 검증을 그대로 사용한다.
 from contextlib import closing
 import app
 with closing(app.connect()) as db:
  db.execute('CREATE TABLE IF NOT EXISTS staff_ai_usage(id INTEGER PRIMARY KEY,user_id INTEGER,feature TEXT,day TEXT DEFAULT CURRENT_DATE,state TEXT,model TEXT,tokens INTEGER DEFAULT 0)')
  limit=max(1,min(1000,int(os.environ.get('AI_DAILY_REQUEST_LIMIT','10'))))
  if db.execute('SELECT count(*) FROM staff_ai_usage WHERE user_id=? AND day=CURRENT_DATE',(actor['id'],)).fetchone()[0]>=limit:raise AIServiceError('하루 AI 요청 한도에 도달했습니다.',429)
  run=db.execute('INSERT INTO staff_ai_usage(user_id,feature,state,model) VALUES(?,?,?,?)',(actor['id'],'qa' if question is not None else 'writing','started',cfg['model'])).lastrowid;db.commit()
 try:
  result=gemini_engine.generate(documents,question=question,expected_questions=expected_questions,document_check=document_check,gap_context=gap_context,gap_apply_context=gap_apply_context,config=cfg)
 except Exception:
  with closing(app.connect()) as db:db.execute("UPDATE staff_ai_usage SET state='failed' WHERE id=?",(run,));db.commit()
  raise
 with closing(app.connect()) as db:db.execute("UPDATE staff_ai_usage SET state='success',tokens=? WHERE id=?",(result.get('usage',{}).get('totalTokenCount',0),run));db.commit()
 return result
