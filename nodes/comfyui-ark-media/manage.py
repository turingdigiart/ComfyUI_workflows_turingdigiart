"""Install/update preserves local config. Release is explicitly allowlisted."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = ['__init__.py','core.py','nodes.py','ark.example.json','.gitignore','manage.py','README.md','CHANGELOG.md','tests/test_core.py','tools/create_workflows.py','tools/smoke_test.py']


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('install').add_argument('--comfy',type=Path,required=True)
    sub.add_parser('package').add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    for f in FILES:
        if not (ROOT/f).is_file(): raise SystemExit('Missing release file: '+f)
    if a.action=='install':
        app=a.comfy.resolve()
        if not (app/'main.py').exists() or not (app/'custom_nodes').is_dir(): raise SystemExit('Not a ComfyUI app directory')
        dst=app/'custom_nodes'/ROOT.name
        if dst.resolve()==ROOT: raise SystemExit('Already installed here')
        for f in FILES:
            (dst/f).parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/f,dst/f)
        if not (dst/'ark.local.json').exists(): shutil.copy2(ROOT/'ark.example.json',dst/'ark.local.json')
        print('Installed:',dst,'\nLocal config preserved. Restart ComfyUI.')
    else:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if a.output.exists(): raise SystemExit('Output already exists')
        hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}
        with zipfile.ZipFile(a.output,'x',zipfile.ZIP_DEFLATED) as z:
            for f in FILES: z.write(ROOT/f,ROOT.name+'/'+f)
            z.writestr(ROOT.name+'/SHA256SUMS.json',json.dumps(hashes,indent=2))
        print('Packaged:',a.output)


if __name__=='__main__': main()
