import json,re
QUESTION_TYPES=('업무절차', '처리방법', '주의사항', '일정·기한', '예외상황', '실무팁')
def validate_draft(value, references):
    if not isinstance(value, dict) or not isinstance(value.get('title'), str) or not isinstance(value.get('items'), list):
        raise ValueError('초안 형식이 올바르지 않습니다. 다시 생성해 주세요.')
    if not value['title'].strip() or not 1 <= len(value['items']) <= 100:
        raise ValueError('초안 제목과 항목을 확인해 주세요.')
    for item in value['items']:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ('category', 'text')):
            raise ValueError('초안 항목 형식이 올바르지 않습니다.')
        ids = item.get('source_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in references for i in ids):
            raise ValueError('원문에 없는 출처가 포함되어 결과를 저장하지 않았습니다. 다시 생성해 주세요.')
    return value

def validate_document_check(value,refs):
    if not isinstance(value,dict) or not isinstance(value.get('summary'),str) or not isinstance(value.get('findings'),list) or len(value['findings'])>20:
        raise ValueError('자료 점검 응답 형식이 올바르지 않습니다.')
    for item in value['findings']:
        if not isinstance(item,dict) or item.get('category') not in ('상충','누락') or item.get('severity') not in ('높음','보통','낮음') or not isinstance(item.get('issue'),str) or not 1<=len(item['issue'])<=4000:
            raise ValueError('자료 점검 항목이 올바르지 않습니다.')
        ids=item.get('source_ids')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in refs for i in ids) or item['category']=='상충' and len(set(ids))<2:
            raise ValueError('자료 점검의 비교 출처를 확인할 수 없습니다. 다시 시도해 주세요.')
    return value

def validate_questions(value, refs):
    if not isinstance(value, dict) or not isinstance(value.get('questions'), list) or not 10 <= len(value['questions']) <= 15:
        raise ValueError('예상질문은 10~15개여야 합니다. 다시 생성해 주세요.')
    seen, categories = set(), set()
    for item in value['questions']:
        if not isinstance(item, dict) or item.get('category') not in QUESTION_TYPES:
            raise ValueError('예상질문 유형이 올바르지 않습니다. 다시 생성해 주세요.')
        question = item.get('question')
        if not isinstance(question, str) or not 5 <= len(question.strip()) <= 500:
            raise ValueError('예상질문 내용이 올바르지 않습니다. 다시 생성해 주세요.')
        key = re.sub(r'\s+', '', question).rstrip('?.!？')
        if key in seen:
            raise ValueError('중복된 예상질문이 있어 저장하지 않았습니다. 다시 생성해 주세요.')
        seen.add(key)
        categories.add(item['category'])
        ids = item.get('source_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in refs for i in ids):
            raise ValueError('예상질문에 실제 자료의 출처가 없습니다. 다시 생성해 주세요.')
        item['question'] = question.strip()
    if categories != set(QUESTION_TYPES):
        raise ValueError('예상질문의 여섯 유형이 모두 포함되지 않았습니다. 다시 생성해 주세요.')
    return value

def validate_answer(value, refs):
    if not isinstance(value, dict) or type(value.get('supported')) is not bool or not isinstance(value.get('answer'), str) or not isinstance(value.get('source_ids'), list):
        raise ValueError('답변 형식이 올바르지 않습니다. 다시 질문해 주세요.')
    if any(not isinstance(i, str) or i not in refs for i in value['source_ids']):
        raise ValueError('답변에 원문에 없는 출처가 포함되어 표시하지 않았습니다.')
    if not value['supported']:
        return {'answer': '선택한 자료만으로는 확인할 수 없습니다. 관련 자료를 추가하거나 전임자에게 확인해 주세요.', 'supported': False, 'source_ids': []}
    if not value['source_ids'] or not value['answer'].strip():
        raise ValueError('답변의 근거가 없습니다. 자료를 확인하고 다시 질문해 주세요.')
    return value

MODEL='테스트 응답 — 실제 AI 아님 · 외부 API 호출 없음'
def settings():return {'key':'','model':MODEL,'mode':'mock'}
def generate(documents,question=None,expected_questions=False,document_check=False,gap_context=None,gap_apply_context=None):
 refs={}
 for doc in documents:
  for i,source in enumerate(json.loads(doc['sources']),1):
   refs[f"D{doc['id']}-S{i}"]={'document_id':doc['id'],'revision':doc['revision'] if 'revision' in doc.keys() else 1,'name':doc['name'],**source}
 if not refs:raise ValueError('먼저 가상 업무자료를 등록하세요.')
 ids=list(refs);first=ids[0]
 common={'model':MODEL,'mode':'mock','references':refs}
 if gap_apply_context is not None:
  draft=gap_apply_context['draft'];return {**common,'target_index':0,'text':draft['items'][0]['text']+'\n[사용자 답변 · 테스트 반영안] '+gap_apply_context['answer']}
 if gap_context is not None:
  return {**common,'summary':'테스트 화면 예시입니다. 실제 AI가 누락을 판단한 결과가 아닙니다.','questions':[{'question':'가상 업무의 다음 처리 일정은 언제인가요?','reason':'테스트 질문 예시이며 실제 의미 분석이 아닙니다.','target_index':0,'source_ids':[first]}]}
 if document_check:return {**common,'summary':'테스트 응답입니다. 실제 자료의 누락·충돌을 판단하지 않았습니다.','findings':[]}
 if expected_questions:
  return {**common,'questions':[{'category':QUESTION_TYPES[i%6],'question':f'[테스트 질문 {i+1}] 이 가상 업무의 확인할 {QUESTION_TYPES[i%6]}은 무엇인가요?','source_ids':[first]} for i in range(12)]}
 if question is not None:return {**common,'answer':'[테스트 응답] 실제 AI 답변이 아닙니다. 선택한 가상 자료의 출처를 확인하는 예시입니다.','supported':False,'source_ids':[]}
 items=[{'category':'담당업무','text':'[테스트 초안 · 실제 AI 아님] 선택한 자료를 읽고 아래 내용을 직접 확인·수정하세요.','source_ids':[first]}]
 for key,source in list(refs.items())[:15]:items.append({'category':'자료 내용','text':source['text'][:2000],'source_ids':[key]})
 items.append({'category':'확인 필요','text':'실제 AI 분석이 없는 테스트 초안입니다. 일정·연락처·미결사항은 작성자가 직접 확인하세요.','source_ids':[first]})
 return {**common,'title':'[가상 예시] 사무용품 구매 및 관리','items':items,'reviewed':False}
