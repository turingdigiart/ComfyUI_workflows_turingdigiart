import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("ark_core", Path(__file__).resolve().parents[1]/"core.py")
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)


class Handler(BaseHTTPRequestHandler):
    posts = []
    gets = []
    status = 200
    task_status = "succeeded"
    redirect = False
    def log_message(self, *args):
        pass
    def do_POST(self):
        Handler.posts.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length']))), self.headers.get('Authorization')))
        self.send_response(Handler.status)
        if Handler.redirect:
            self.send_header('Location', 'https://other.example/steal')
        self.end_headers()
        self.wfile.write(json.dumps({'id':'test-task-1'} if Handler.status == 200 else {'error':'SECRET sensitive server message'}).encode())
    def do_GET(self):
        Handler.gets.append((self.path, self.headers.get('Authorization')))
        self.send_response(200); self.end_headers()
        if self.path == '/media':
            self.wfile.write(b'mock-media')
        else:
            self.wfile.write(json.dumps({'id':'test-task-1','status':Handler.task_status,'content':{'video_url':f'http://127.0.0.1:{self.server.server_port}/media'}}).encode())


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0), Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config={'base_url':f'http://127.0.0.1:{self.server.server_port}/v3','api_key':'SECRET','api_key_env':'ARK_TEST_UNUSED_ENV','allow_local_test':True,'proxy':'direct'}
        self.c=core.Client(self.config, self.temp.name)
        Handler.posts=[]; Handler.gets=[]; Handler.status=200; Handler.task_status='succeeded'; Handler.redirect=False
    def tearDown(self):
        self.temp.cleanup()
    def test_auth_and_create(self):
        self.assertEqual(self.c.submit_once('video',{'model':'test'},0,'1')['id'],'test-task-1')
        self.assertEqual(Handler.posts[0][0],'/v3/contents/generations/tasks')
        self.assertEqual(Handler.posts[0][2],'Bearer SECRET')
    def test_durable_deduplication_and_refresh(self):
        self.c.submit_once('video',{'model':'test'},0,'1')
        core.Client(self.config,self.temp.name).submit_once('video',{'model':'test'},0,'1')
        self.assertEqual(len(Handler.posts),1)
        self.c.submit_once('video',{'model':'test'},1,'1')
        self.assertEqual(len(Handler.posts),2)
    def test_failure_no_retry_redaction(self):
        Handler.status=401
        for _ in range(2):
            with self.assertRaises(core.ArkError) as e:
                self.c.submit_once('video',{'model':'test'},0,'1')
            self.assertNotIn('SECRET',str(e.exception))
        self.assertEqual(len(Handler.posts),1)
    def test_receipts_no_key_or_prompt(self):
        self.c.submit_once('video',{'prompt':'PRIVATE-PROMPT'},0,'1')
        raw=''.join(p.read_text() for p in Path(self.temp.name).glob('*.json'))
        self.assertNotIn('SECRET',raw); self.assertNotIn('PRIVATE-PROMPT',raw)
    def test_missing_key(self):
        self.config['api_key']=''
        with self.assertRaises(core.ArkError): core.Client(self.config,self.temp.name)
    def test_api_redirect_rejected(self):
        Handler.status=307; Handler.redirect=True
        with self.assertRaises(core.ArkError): self.c.call('/test',{})
        self.assertEqual(len(Handler.posts),1)
    def test_media_no_auth(self):
        path=Path(self.temp.name)/'video.mp4'
        self.c.download(f'http://127.0.0.1:{self.server.server_port}/media',path,100)
        self.assertEqual(path.read_bytes(),b'mock-media')
        self.assertIsNone(Handler.gets[0][1])
    def test_size_limit_cleanup(self):
        path=Path(self.temp.name)/'too-big.mp4'
        with self.assertRaises(core.ArkError): self.c.download(f'http://127.0.0.1:{self.server.server_port}/media',path,1)
        self.assertFalse(path.exists()); self.assertFalse(list(Path(self.temp.name).glob('*.part')))
    def test_poll_success(self):
        self.assertEqual(self.c.poll('test-task-1',1)['status'],'succeeded')
        self.assertEqual(len(Handler.posts),0)
    def test_poll_timeout_keeps_id(self):
        Handler.task_status='running'
        with self.assertRaisesRegex(core.ArkError,'test-task-1'): self.c.poll('test-task-1',0)
        self.assertFalse(Handler.posts)
    def test_failed_and_canceled(self):
        for s in ('failed','cancelled','expired'):
            Handler.task_status=s
            with self.assertRaises(core.ArkError): self.c.poll('test-task-1',0)
    def test_interrupt(self):
        def stop(): raise InterruptedError('user cancelled')
        with self.assertRaises(InterruptedError): self.c.poll('test-task-1',1,stop)
        self.assertFalse(Handler.gets)
    def test_invalid_id_and_url(self):
        for task in ('../secret','id?key=a',''):
            with self.assertRaises(core.ArkError): core.safe_id(task)
        for url in ('http://remote.example/x','file:///tmp/test','https://secret@host/v3'):
            with self.assertRaises(core.ArkError): core.validate_url(url)
    def test_seedream_shape(self):
        b=core.image_body('model','prompt','2K',True,['data:image/png;base64,abc'])
        self.assertEqual(b['image'],'data:image/png;base64,abc'); self.assertNotIn('messages',b)
        self.assertEqual(b['response_format'],'url')
    def test_seedance_first_last(self):
        b=core.video_body('doubao-seedance-2-5-260628','wave','first_frame','720p','16:9',5,True,True,['a'],['b'])
        self.assertEqual(b['ratio'],'adaptive')
        self.assertEqual([x.get('role') for x in b['content']],[None,'first_frame','last_frame'])
    def test_bad_video_combinations(self):
        for mode, refs, last in [('text',['a'],[]),('first_frame',[],[]),('reference_images',['a'],['b'])]:
            with self.assertRaises(core.ArkError): core.video_body('model','prompt',mode,'720p','adaptive',5,True,True,refs,last)
        with self.assertRaises(core.ArkError): core.video_body('doubao-seedance-2-0','prompt','text','720p','16:9',30,True,True,[],[])


if __name__ == '__main__': unittest.main()
