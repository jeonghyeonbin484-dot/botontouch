"""DB 설정 없는 운영 배포를 중단한다. DB 변경/접속이나 비밀값 출력 없음."""
from pathlib import Path
import sys,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cloud_database_config

def main():
 try:
  import template_preview_assets
  template_preview_assets.validate(Path(__file__).resolve().parents[1])
 except (ValueError,OSError) as error:
  print(str(error),file=sys.stderr);return 1
 try:meta=cloud_database_config.safe_metadata()
 except cloud_database_config.DatabaseConfigurationError:
  print('배포 중단: 공용 PostgreSQL의 DATABASE_URL 설정을 확인하세요. 기존 운영 배포와 데이터는 변경하지 않습니다.',file=sys.stderr);return 1
 print('공용 DB 설정 검증 완료 · provider='+meta['provider']+' · 서버 설정값 원문은 출력하지 않습니다.')
 return subprocess.call([sys.executable,str(Path(__file__).resolve().parents[1]/'web/build.py')])
if __name__=='__main__':raise SystemExit(main())
