"""Generate UI + API samples, all paid submissions disabled by default."""
import argparse
import copy
import json
from pathlib import Path
from urllib.request import urlopen
import uuid


def main():
    p=argparse.ArgumentParser(); p.add_argument('--project-root',type=Path,required=True); a=p.parse_args()
    root=a.project_root.resolve(); app=root/'ComfyUI_windows_portable/ComfyUI'
    with urlopen('http://127.0.0.1:8188/object_info') as response: schema=json.load(response)
    image=dict(enable_api=False,prompt='参考图片重新设计机器人：保持可爱的大头短身比例和完整全身，使用钴蓝色装甲、橙色配件、发光眼睛及胸口能量核心，干净的浅灰背景，精致3D角色设定图。',model='',size='2K',watermark=True,refresh_id=0)
    video=dict(enable_api=False,prompt='可爱机器人缓慢抬起右手向镜头挥手，眼睛轻轻闪烁，固定镜头，保持角色造型一致，轻微机械运转音，无对白。',model='',mode='first_frame',resolution='720p',ratio='adaptive',duration=5,generate_audio=True,watermark=True,refresh_id=0)
    def node(kind, **inputs): return dict(class_type=kind,inputs=inputs)
    def save(name,g,note):
        nodes=[]; links=[]; rows={}; depths={}
        for key,item in g.items():
            spec=schema[item['class_type']]; sockets=[]; widgets=[]
            for field,definition in {**spec['input'].get('required',{}),**spec['input'].get('optional',{})}.items():
                typ=definition[0]; opts=definition[1] if len(definition)>1 else {}; val=item['inputs'].get(field)
                if field=='codec' and item['class_type']=='SaveVideo': continue
                if typ=='COMFY_DYNAMICCOMBO_V3':
                    widgets += ['mp4','auto']; continue
                primitive=isinstance(typ,list) or typ in ('STRING','INT','FLOAT','BOOLEAN','COMBO')
                connected=isinstance(val,list) and len(val)==2 and str(val[0]) in g
                if primitive and not connected:
                    default=(typ[0] if isinstance(typ,list) else opts.get('default',''))
                    widgets.append(default if val is None else val)
                    if opts.get('image_upload'): widgets.append('image')
                else:
                    socket={'name':field,'type':typ if isinstance(typ,str) else 'COMBO','link':None}
                    if primitive:
                        socket['widget']={'name':field}; widgets.append(opts.get('default',''))
                    sockets.append(socket)
            depth=max([depths[str(v[0])]+1 for v in item['inputs'].values() if isinstance(v,list) and str(v[0]) in depths] or [0]); depths[key]=depth
            row=rows.get(depth,0); rows[depth]=row+1
            outs=[{'name':label,'type':typ,'links':[],'slot_index':i} for i,(label,typ) in enumerate(zip(spec['output_name'],spec['output']))]
            nodes.append(dict(id=int(key),type=item['class_type'],title=spec.get('display_name',item['class_type']),pos=[depth*520,row*620],size=[450,540],flags={},order=len(nodes),mode=0,inputs=sockets,outputs=outs,properties={'Node name for S&R':item['class_type']},widgets_values=widgets))
        lookup={str(n['id']):n for n in nodes}
        for key,item in g.items():
            for field,val in item['inputs'].items():
                if not isinstance(val,list): continue
                src,slot=val; dst=lookup[key]; source=lookup[src]; idx=next(i for i,x in enumerate(dst['inputs']) if x['name']==field)
                lid=len(links)+1; typ=source['outputs'][slot]['type']; links.append([lid,int(src),slot,int(key),idx,typ]); dst['inputs'][idx]['link']=lid; source['outputs'][slot]['links'].append(lid)
        nid=max(int(x) for x in g)+1
        nodes.append(dict(id=nid,type='MarkdownNote',title='开始前先读 / 云端付费接口',pos=[0,-430],size=[950,380],flags={},order=len(nodes),mode=0,properties={},widgets_values=[note]))
        w=dict(id=str(uuid.uuid4()),revision=0,last_node_id=nid,last_link_id=len(links),nodes=nodes,links=links,groups=[],config={},extra={'ds':{'scale':0.65,'offset':[30,460]}},version=0.4)
        for folder in (root/'workflows', app/'user/default/workflows'):
            (folder/(name+'.json')).write_text(json.dumps(w,ensure_ascii=False,indent=2),encoding='utf-8')
        folder=root/'setup/ark_api'; folder.mkdir(exist_ok=True)
        (folder/(name+'.json')).write_text(json.dumps({'prompt':g,'workflow':w},ensure_ascii=False,indent=2),encoding='utf-8')
        print('Created:',name)
    common='配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。'
    save('18_方舟Seedream_机器人改图',{'1':node('LoadImage',image='3d_evaluation.png'),'2':node('ArkSeedream',**image,reference_images=['1',0]),'3':node('SaveImage',images=['2',0],filename_prefix='Ark/Seedream'),'4':node('PreviewAny',source=['2',1])},common+'\n\n默认单图2K。移除参考图连接可文生图。相同请求复用本地记录；需要新结果才增加refresh_id。结果在output/Ark。')
    save('19_方舟Seedance_机器人图生视频',{'1':node('LoadImage',image='3d_evaluation.png'),'2':node('ArkSeedanceSubmit',**video,reference_images=['1',0]),'3':node('PreviewAny',source=['2',0]),'4':node('ArkSeedanceFetch',task_id=['2',0],wait_seconds=600),'5':node('SaveVideo',video=['4',0],filename_prefix='Ark/Seedance',format='mp4',codec='auto')},common+'\n\n默认5秒720p有声。首帧模式自动使用adaptive比例。提交任务后保留ID；超时重跑会查询原任务。不要随意增加refresh_id，否则会创建新付费任务。停止本地等待不等于取消云端。')
    save('20_方舟Seedance_已有任务取回',{'1':node('ArkSeedanceFetch',task_id='',wait_seconds=600),'2':node('SaveVideo',video=['1',0],filename_prefix='Ark/Recovered',format='mp4',codec='auto'),'3':node('PreviewAny',source=['1',1])},'填写已有任务ID，使用同一方舟账户的配置。此工作流只查询和下载，不创建新生成任务。可用于恢复超时任务；任务和下载地址存在有效期，完成后尽快保存。')
    v=copy.deepcopy(video); v.update(mode='text',ratio='16:9')
    save('21_方舟Seedance_文生视频',{'1':node('ArkSeedanceSubmit',**v),'2':node('PreviewAny',source=['1',0]),'3':node('ArkSeedanceFetch',task_id=['1',0],wait_seconds=600),'4':node('SaveVideo',video=['3',0],filename_prefix='Ark/TextToVideo',format='mp4',codec='auto')},common+'\n\n纯文字生成5秒720p有声视频。任务取回、超时恢复规则与19相同。')


if __name__=='__main__': main()
