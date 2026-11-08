import unittest,sys,json,sqlite3,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from test_cloud import Fixture
import cloud_store

class TransferTests(unittest.TestCase):
 def setUp(self):self.f=Fixture().start();self.a=self.f.login('demo.a')
 def tearDown(self):self.f.stop()
 def test_unchanged_reads_do_not_transfer_database(self):
  downloads=self.f.memory.downloads
  for _ in range(30):self.assertIsNotNone(self.f.call('/api/auth/status',client=self.a)['user'])
  self.assertEqual(self.f.memory.downloads,downloads)
 def test_external_session_revocation_invalidates_cache(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'state.sqlite3';path.write_bytes(self.f.memory.payload)
   with closing(sqlite3.connect(path)) as db:db.execute('DELETE FROM sessions');db.commit()
   with self.f.memory.lock:self.f.memory.payload=path.read_bytes();self.f.memory.version+=1
  self.assertIsNone(self.f.call('/api/auth/status',client=self.a)['user'])
 def test_database_failure_never_authenticates_cached_user(self):
  class OperationalError(Exception):pass
  with patch.object(sys.modules['psycopg'],'connect',side_effect=OperationalError('account quota exceeded')) as connect:
   for _ in range(2):
    with self.assertRaises(__import__('urllib.error',fromlist=['HTTPError']).HTTPError) as error:self.f.call('/api/auth/status',client=self.a)
    self.assertEqual(error.exception.code,503);self.assertEqual(json.load(error.exception)['code'],'STORAGE_QUOTA_EXCEEDED')
   self.assertEqual(connect.call_count,1)
 def test_measure_warm_and_cold_payload_bytes(self):
  start=self.f.memory.downloaded_bytes
  for _ in range(20):self.f.call('/api/chat/unread',client=self.a)
  warm=self.f.memory.downloaded_bytes-start
  start=self.f.memory.downloaded_bytes
  for _ in range(20):
   cloud_store.reset_runtime_cache();self.f.call('/api/chat/unread',client=self.a)
  cold=self.f.memory.downloaded_bytes-start
  self.assertEqual(warm,0);self.assertGreater(cold,0)
  out=Path(__file__).resolve().parents[1]/'artifacts/final-release/storage-transfer-measurement.json';out.parent.mkdir(parents=True,exist_ok=True)
  out.write_text(json.dumps({'requests':20,'warm_payload_bytes':warm,'cold_payload_bytes':cold,'scope':'가상 DB의 스냅샷 전송량만 측정. SQL 메타데이터·실제 서비스 트래픽은 별도.'},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':unittest.main()
