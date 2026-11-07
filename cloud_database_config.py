"""공용 PostgreSQL 설정 확인. 비밀값은 반환 응답이나 오류에 포함하지 않는다."""
import os
from urllib.parse import urlsplit,parse_qs
class DatabaseConfigurationError(ValueError):pass

def connection_url():
 value=os.environ.get('DATABASE_URL','').strip()
 if not value:raise DatabaseConfigurationError('Vercel 서버의 DATABASE_URL 설정이 없습니다. 관리자가 Production 환경변수와 배포를 확인해야 합니다.')
 try:
  url=urlsplit(value)
  if url.scheme not in ('postgresql','postgres') or not url.hostname:raise ValueError()
  port=url.port
 except ValueError:raise DatabaseConfigurationError('DATABASE_URL 형식이 올바르지 않습니다. 공용 PostgreSQL 연결 설정을 확인하세요.') from None
 if os.environ.get('BATON_CLOUD_LOCAL_TEST')!='1' and url.hostname.lower() in ('localhost','127.0.0.1','::1'):
  raise DatabaseConfigurationError('공개 서버에는 PC 로컬 DB 주소를 사용할 수 없습니다. 공용 PostgreSQL 주소를 설정하세요.')
 return value

def safe_metadata():
 value=connection_url();url=urlsplit(value);host=url.hostname.lower();provider='supabase' if host.endswith(('.supabase.com','.supabase.co')) else 'neon' if host.endswith('.neon.tech') else 'postgresql'
 return {'configured':True,'provider':provider,'transaction_pooler':host.endswith('pooler.supabase.com') and url.port==6543}
