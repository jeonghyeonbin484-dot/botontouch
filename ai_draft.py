"""기존 직원 API가 공통 Gemini 엔진 또는 명시적 MOCK을 선택한다."""
from mock_ai import validate_draft,validate_answer,validate_questions,validate_document_check,QUESTION_TYPES
import mock_ai,staff_ai_policy

def settings():return staff_ai_policy.settings()
def generate(documents,question=None,expected_questions=False,document_check=False,gap_context=None,gap_apply_context=None,actor=None):
 if expected_questions or document_check or gap_context is not None or gap_apply_context is not None:
  return mock_ai.generate(documents,question,expected_questions,document_check,gap_context,gap_apply_context)
 if settings()['mode']=='mock':return mock_ai.generate(documents,question)
 return staff_ai_policy.generate(documents,actor,question)
