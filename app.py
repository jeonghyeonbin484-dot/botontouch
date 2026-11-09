"""로컬 실행 및 기존 app 모듈 호환 진입점."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'backend'))
for parent in Path(__file__).resolve().parents:
    vendor=parent/'.vendor'
    if vendor.is_dir():
        sys.path.append(str(vendor))
        break
from batontouch.server import application
if __name__ == '__main__':
    application.start_local_server()
else:
    sys.modules[__name__] = application
