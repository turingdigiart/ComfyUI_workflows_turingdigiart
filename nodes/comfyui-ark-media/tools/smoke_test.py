"""Real ComfyUI, fake local Ark endpoint. Uses existing local fixtures, no cloud calls."""
import argparse
import copy
import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen


def http(route, body=None):
    req=Request('http://127.0.0.1:8188'+route,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=20) as r: return json.load(r)


def execute(graph):
    data=http('/prompt',{'prompt':graph}); pid=data['prompt_id']; deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        h=http('/history/'+pid)
        if pid in h:
            result=h[pid]
            if result['status']['status_str']!='success': raise RuntimeError('ComfyUI test failed, history ID '+pid)
            return {'prompt_id':pid,'status':result['status'],'outputs':result['outputs']}
        time.sleep(0.5)
    raise TimeoutError('Local smoke test timed out')


class Handler(BaseHTTPRequestHandler):
    posts=[]; media_headers=[]; image=b''; video=b''
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        # Record only shape, never raw reference bytes.
        Handler.posts.append({'path':self.path,'model':body['model'],'has_image':bool(body.get('image')),'roles':[x.get('role') for x in body.get('content',[])]})
        assert self.headers.get('Authorization')=='Bearer LOCAL-MOCK-ONLY'
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        data={'data':[{'url':f'http://127.0.0.1:{self.server.server_port}/image.png'}]} if self.path.endswith('/images/generations') else {'id':'mock-video-'+str(self.server.server_port)}
        self.wfile.write(json.dumps(data).encode())
    def do_GET(self):
        self.send_response(200); self.end_headers()
        if self.path in ('/image.png','/video.mp4'):
            Handler.media_headers.append(self.headers.get('Authorization'))
            self.wfile.write(Handler.image if self.path=='/image.png' else Handler.video)
        else:
            self.wfile.write(json.dumps({'status':'succeeded','content':{'video_url':f'http://127.0.0.1:{self.server.server_port}/video.mp4'}}).encode())


def main():
    p=argparse.ArgumentParser();p.add_argument('--project-root',type=Path,required=True);a=p.parse_args()
    root=a.project_root.resolve(); app=root/'ComfyUI_windows_portable/ComfyUI'
    q=http('/queue')
    if q['queue_running'] or q['queue_pending']: raise SystemExit('Queue busy; retry when idle')
    config=app/'custom_nodes/comfyui-ark-media/ark.local.json'; original=config.read_bytes()
    Handler.image=(app/'input/3d_evaluation.png').read_bytes()
    fixture=next((app/'output/Expansion').rglob('*LTX23*.mp4'),None)
    if fixture is None: raise SystemExit('Need an existing local LTX23 MP4 fixture')
    Handler.video=fixture.read_bytes()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler); threading.Thread(target=server.serve_forever,daemon=True).start()
    result={'type':'mock Ark only; no cloud requests; fixtures are existing media','tests':{}}
    def graph(number): return json.loads(next((root/'setup/ark_api').glob(number+'_*.json')).read_text(encoding='utf-8'))['prompt']
    try:
        config.write_text(json.dumps({'base_url':f'http://127.0.0.1:{server.server_port}/api/v3','api_key':'LOCAL-MOCK-ONLY','api_key_env':'ARK_SMOKE_UNUSED_KEY','proxy':'direct','allow_local_test':True,'seedream_model':'mock-image','seedance_model':'mock-video'}),encoding='utf-8')
        g=graph('18');g['2']['inputs']['enable_api']=True
        g['3']['inputs']['filename_prefix']='Ark/MockValidation/Seedream_fixture'
        result['tests']['image_reference']=execute(g)
        result['tests']['image_cache']=execute(g)
        assert len(Handler.posts)==1
        g=graph('19');g['2']['inputs']['enable_api']=True
        g['5']['inputs']['filename_prefix']='Ark/MockValidation/Seedance_fixture'
        result['tests']['video_first_frame']=execute(g)
        assert len(Handler.posts)==2
        result['tests']['video_cache']=execute(g)
        assert len(Handler.posts)==2
        task='mock-video-'+str(server.server_port)
        g=graph('20');g['1']['inputs']['task_id']=task
        g['2']['inputs']['filename_prefix']='Ark/MockValidation/Recovered_fixture'
        result['tests']['recover_without_submit']=execute(g)
        assert len(Handler.posts)==2
        g=graph('21');g['1']['inputs']['enable_api']=True
        g['4']['inputs']['filename_prefix']='Ark/MockValidation/TextToVideo_fixture'
        result['tests']['text_to_video']=execute(g)
        assert len(Handler.posts)==3
        assert all(x is None for x in Handler.media_headers)
        result['post_shapes']=Handler.posts;result['media_authorization_absent']=True
    finally:
        config.write_bytes(original);server.shutdown();server.server_close()
    (root/'logs/ark-media-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS:',', '.join(result['tests']))
    print('Local config restored. Paid requests: 0')


if __name__=='__main__':main()
