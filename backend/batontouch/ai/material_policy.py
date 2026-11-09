"""승인된 업무자료 전송 전 기본 식별정보 차단. 완전한 개인정보 판별을 보장하지 않는다."""
import json,re
from batontouch.ai.gemini_engine import AIServiceError
RULES=(
 ('주민등록번호',re.compile(r'(?<!\d)\d{6}[\s-]*[1-8]\d{6}(?!\d)')),
 ('휴대전화번호',re.compile(r'(?<!\d)01[016789][\s.-]*\d{3,4}[\s.-]*\d{4}(?!\d)')),
 ('이메일 주소',re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')),
 ('민감한 인증정보',re.compile(r'(?i)(?:api[_ -]?key|비밀번호|password|access[_ -]?token)\s*[:=]\s*[^\s,;]{4,}')),
)
def check(documents,question=None,contexts=None):
 values=[]
 for doc in documents:
  sources=doc['sources']
  if isinstance(sources,str):
   try:sources=json.loads(sources)
   except ValueError:raise AIServiceError('자료의 추출 정보 형식이 올바르지 않습니다. 자료는 전송하지 않았습니다.',400) from None
  if not isinstance(sources,list):raise AIServiceError('자료의 추출 정보 형식이 올바르지 않습니다.',400)
  values.append(str(doc['name']));values.extend(str(s.get('text','')) for s in sources if isinstance(s,dict))
 if question is not None:values.append(question)
 if contexts is not None:values.append(json.dumps(contexts,ensure_ascii=False))
 text='\n'.join(values)
 for label,pattern in RULES:
  if pattern.search(text):raise AIServiceError('외부 전송을 차단했습니다: '+label+' 포함 가능성이 있습니다. 개인정보와 인증정보를 제거한 승인 자료로 다시 시도하세요. 원문은 전송하지 않았습니다.',403)
