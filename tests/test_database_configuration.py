import unittest,os,io,json
from unittest.mock import patch
import cloud_database_config as config,storage_diagnostics,cloud_store
from test_cloud import Fixture
class DatabaseConfigurationTests(unittest.TestCase):
 def test_missing_setting_has_no_local_or_other_provider_fallback(self):
  with patch.dict(os.environ,{'DATABASE_URL':'','POSTGRES_URL':'postgresql://wrong-provider.invalid/db'}):
   with self.assertRaises(config.DatabaseConfigurationError):config.connection_url()
 def test_production_local_url_is_rejected(self):
  with patch.dict(os.environ,{'DATABASE_URL':'postgresql://localhost/database','BATON_CLOUD_LOCAL_TEST':''}):
   with self.assertRaises(config.DatabaseConfigurationError):config.connection_url()
 def test_metadata_does_not_expose_url(self):
  secret='not-real-private-secret'
  with patch.dict(os.environ,{'DATABASE_URL':'postgresql://postgres.fake:'+secret+'@aws-0-test.pooler.supabase.com:6543/postgres?sslmode=require'}):
   m=config.safe_metadata();self.assertEqual(m['provider'],'supabase');self.assertTrue(m['transaction_pooler']);self.assertNotIn(secret,json.dumps(m))
 def test_bad_port_redacted(self):
  with patch.dict(os.environ,{'DATABASE_URL':'postgresql://user:secret@host:broken/database'}):
   with self.assertRaises(config.DatabaseConfigurationError) as e:config.connection_url()
   self.assertNotIn('secret',str(e.exception))
 def test_missing_setting_stops_deployment_before_build(self):
  import subprocess,sys
  from pathlib import Path
  environment=dict(os.environ,DATABASE_URL='')
  result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'tools/validate_cloud_environment.py')],env=environment,capture_output=True)
  self.assertEqual(result.returncode,1);self.assertIn('DATABASE_URL',result.stderr.decode('utf-8','replace'))
 def test_error_log_omits_secrets(self):
  error=Exception('postgresql://user:very-private-password@host/db');stream=io.StringIO()
  with patch('sys.stderr',stream):r=storage_diagnostics.payload(error,'/api/auth/login?password=hidden')
  self.assertTrue(r['trace_id']);self.assertNotIn('very-private-password',stream.getvalue()+json.dumps(r));self.assertNotIn('password=hidden',stream.getvalue())
 def test_sqlstate_distinguishes_database_auth(self):
  class OperationalError(Exception):sqlstate='28P01'
  with patch('sys.stderr',io.StringIO()):r=storage_diagnostics.payload(OperationalError('private-password'))
  self.assertEqual(r['code'],'STORAGE_AUTH_FAILED');self.assertNotIn('private-password',str(r))
class DatabaseEndpointTests(unittest.TestCase):
 def setUp(self):self.f=Fixture().start()
 def tearDown(self):self.f.stop()
 def test_missing_configuration_is_503_not_login_401(self):
  import urllib.error
  with patch.dict(os.environ,{'DATABASE_URL':''}),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(urllib.error.HTTPError) as e:self.f.call('/api/auth/status')
   body=json.load(e.exception);e.exception.close();self.assertEqual(e.exception.code,503);self.assertEqual(body['code'],'STORAGE_NOT_CONFIGURED');self.assertTrue(body['trace_id'])
 def test_failure_does_not_clear_existing_authentication_cookie(self):
  import urllib.error
  a=self.f.login('demo.a')
  with patch.dict(os.environ,{'DATABASE_URL':''}),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(urllib.error.HTTPError) as e:self.f.raw('/api/auth/status',client=a)
   self.assertEqual(e.exception.code,503);self.assertIsNone(e.exception.headers.get('Set-Cookie'));e.exception.close()
 def test_missing_production_state_is_not_initialized(self):
  import sys,types
  queries=[]
  class EmptyDatabase:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def execute(self,sql,*args):queries.append(sql);return self
   def fetchone(self):return None
  with patch.dict(os.environ,{'DATABASE_URL':'postgresql://fictional.invalid/empty','BATON_CLOUD_LOCAL_TEST':''}),patch.dict(sys.modules,{'psycopg':types.SimpleNamespace(connect=lambda *args,**kwargs:EmptyDatabase())}):
   with self.assertRaises(cloud_store.StorageUnavailable) as error:
    with cloud_store.database_request():self.fail('빈 운영 DB에서 요청을 실행하면 안 됩니다.')
   self.assertEqual(error.exception.code,'STORAGE_NOT_INITIALIZED');self.assertFalse(any(q.startswith(('CREATE','INSERT','UPDATE','DELETE')) for q in queries))
 def test_health_endpoint_has_no_accounts_or_secrets(self):
  with patch.object(cloud_store,'readiness',return_value={'status':'ready','provider':'supabase','checked':True,'authentication_required':True}):r=self.f.call('/api/system/storage-status')
  self.assertEqual(r['status'],'ready');self.assertNotIn('users',r);self.assertNotIn('DATABASE_URL',r)
 def test_health_failure_logs_trace(self):
  import urllib.error
  with patch.object(cloud_store,'readiness',side_effect=cloud_store.StorageUnavailable('missing','STORAGE_NOT_INITIALIZED')),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(urllib.error.HTTPError) as e:self.f.call('/api/system/storage-status')
   body=json.load(e.exception);e.exception.close();self.assertEqual(body['code'],'STORAGE_NOT_INITIALIZED');self.assertTrue(body['trace_id'])
if __name__=='__main__':unittest.main()
