import unittest,io,tempfile
from pathlib import Path
from unittest.mock import patch
import guide_media
class Handler:
 def __init__(self,path,range_header=None):self.path=path;self.headers={'Range':range_header} if range_header else {};self.wfile=io.BytesIO();self.response_headers={}
 def send_response(self,status):self.status=status
 def send_header(self,key,value):self.response_headers[key]=value
 def end_headers(self):pass
 def respond(self,status,payload):self.status=status
class GuideMediaTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);folder=self.root/'public/media';folder.mkdir(parents=True);(folder/'botontouch-guide-v1.mp4').write_bytes(bytes(range(256)))
 def tearDown(self):self.temp.cleanup()
 def test_complete_video(self):
  h=Handler('/media/botontouch-guide-v1.mp4');self.assertTrue(guide_media.serve(h,self.root));self.assertEqual(h.status,200);self.assertEqual(len(h.wfile.getvalue()),256);self.assertEqual(h.response_headers['Content-Type'],'video/mp4')
 def test_range(self):
  h=Handler('/media/botontouch-guide-v1.mp4','bytes=50-99');guide_media.serve(h,self.root);self.assertEqual(h.status,206);self.assertEqual(h.wfile.getvalue(),bytes(range(50,100)));self.assertEqual(h.response_headers['Content-Range'],'bytes 50-99/256')
 def test_suffix_range(self):
  h=Handler('/media/botontouch-guide-v1.mp4','bytes=-8');guide_media.serve(h,self.root);self.assertEqual(h.wfile.getvalue(),bytes(range(248,256)))
 def test_outside_range(self):
  h=Handler('/media/botontouch-guide-v1.mp4','bytes=900-');guide_media.serve(h,self.root);self.assertEqual(h.status,416)
 def test_no_private_file_access(self):
  for name in ['../settings.local.json','secret.mp4','botontouch-guide-v1.py']:
   h=Handler('/media/'+name);guide_media.serve(h,self.root);self.assertEqual(h.status,404)
 def test_missing_preparation(self):
  h=Handler('/media/botontouch-guide-v2.mp4');guide_media.serve(h,self.root);self.assertEqual(h.status,404)
 def test_other_routes_unchanged(self):self.assertFalse(guide_media.serve(Handler('/api/documents'),self.root))
if __name__=='__main__':unittest.main()
