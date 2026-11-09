"""실행 위치와 무관한 공통 자원 경로. 데이터 저장 정책은 변경하지 않는다."""
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = PROJECT_ROOT / 'frontend'
TEMPLATE_ROOT = PROJECT_ROOT / 'templates'
