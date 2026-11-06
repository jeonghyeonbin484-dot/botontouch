import os
from urllib.parse import urlsplit

def central():return True
def dev_test_accounts():return False
def host():return '127.0.0.1'
def port():return int(os.environ.get('BATON_PORT','8765'))
def secure_cookie():return os.environ.get('BATON_CLOUD_LOCAL_TEST')!='1'
def public_origin():return os.environ.get('BATON_PUBLIC_ORIGIN','').rstrip('/')
def allowed_origins():
 result={public_origin()} if public_origin() else set()
 for key in ('VERCEL_URL','VERCEL_PROJECT_PRODUCTION_URL','VERCEL_BRANCH_URL'):
  value=os.environ.get(key,'')
  if value and value.endswith('.vercel.app') and '/' not in value:result.add('https://'+value)
 if os.environ.get('BATON_CLOUD_LOCAL_TEST')=='1':result.add('http://127.0.0.1:'+str(port()))
 return result

def validate():
 if public_origin() and (urlsplit(public_origin()).scheme!='https' or urlsplit(public_origin()).path):raise ValueError('공개 주소는 HTTPS 원점으로 설정하세요.')

def public_demo():return False
