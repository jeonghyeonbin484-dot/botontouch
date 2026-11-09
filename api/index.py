from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
"""Vercel 공개 진입점. 처리 로직은 서버 패키지에서 관리한다."""
from batontouch.server.vercel_handler import handler as ApplicationHandler

class handler(ApplicationHandler):
    """Vercel이 직접 탐지할 수 있는 기존 요청 처리기의 진입점."""
    pass
