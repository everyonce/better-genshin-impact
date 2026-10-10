"""Bounded marker steering pilot. All capture and input goes through BetterGI.
This is not a route planner: a supervisor must approve each short corridor.
"""
import argparse, json, os, time, uuid, subprocess, importlib.util
from pathlib import Path

BASE=Path(__file__).resolve().parent
REPO=BASE.parents[1]
APP=Path(os.environ.get('BETTERGI_PILOT_APP_DIR', REPO/'artifacts'/'release-r8'/'BetterGI-English-win-x64')).expanduser().resolve()
ROOT=APP/'User/JsScript/OpeningQuestPilot'
DOTNET=Path(os.environ.get('DOTNET_HOST_PATH', Path.home()/'.codex/tools/dotnet8/dotnet.exe')).expanduser()
spec=importlib.util.spec_from_file_location('vision',BASE/'birds-eye-vision.py')
vision=importlib.util.module_from_spec(spec); spec.loader.exec_module(vision)

def read(): return json.loads((ROOT/'observation.json').read_text(encoding='utf-8-sig'))
def send(o,action,**kw):
    current=read()
    assert current['session']==o['session'] and current['frameId']==o['frameId'], 'Session or frame changed'
    nav=json.loads((ROOT/'navigation.json').read_text(encoding='utf-8-sig'))
    assert nav['rdp'] is True and nav['windowsSessionId']==5, 'Wrong Windows session'
    assert time.time()*1000-o['timestamp'] < 60000, 'Observation too old'
    c=dict(id='steer-'+uuid.uuid4().hex,session=o['session'],expectedFrameId=o['frameId'],createdAt=int(time.time()*1000),action=action,**kw)
    tmp=ROOT/'command.pending.json'; tmp.write_text(json.dumps(c),encoding='utf-8'); os.replace(tmp,ROOT/'command.json')
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        time.sleep(.1)
        try: r=json.loads((ROOT/'receipt.json').read_text(encoding='utf-8-sig'))
        except (FileNotFoundError,json.JSONDecodeError): continue
        if r['id']==c['id'] and r['status']!='started':
            assert r['status']=='completed', r
            n=read(); assert n['session']==o['session'] and n['frameId']==o['frameId']+1
            return n
    raise RuntimeError('No terminal receipt; no retry is permitted')

def world_hud(o):
    rows=o['ocr']
    pixels=vision.np.asarray(vision.Image.open(ROOT/o['screenshotPath']).convert('RGB'))
    hp=pixels[1005:1016,810:1110].astype(float)
    arrow=pixels[110:140,153:183].astype(float)
    hp_pixels=((hp[:,:,1]>150)&(hp[:,:,0]>90)&(hp[:,:,2]<130)&(hp[:,:,1]>hp[:,:,0]*1.1)).sum()
    cyan_pixels=((arrow[:,:,2]>220)&(arrow[:,:,1]>120)&(arrow[:,:,0]<100)).sum()
    assert hp_pixels>500 and cyan_pixels>25, 'World HUD missing; stop for screen review'
    if any('Unexpected Power' in r['text'] or 'Quest Completed' in r['text'] for r in rows): raise RuntimeError('Quest transition; stop')
    for r in rows:
        if r['y']>980 and '/' in r['text']:
            hp=r['text'].replace(' ','').split('/')
            if len(hp)==2 and hp[0].isdigit() and hp[1]=='912': assert int(hp[0])>=660, 'HP decreased'

def analyze(o):
    world_hud(o)
    path=ROOT/o['screenshotPath']
    v=vision.analyze(path)
    p=json.loads(subprocess.check_output([str(DOTNET),'exec','--runtimeconfig',str(APP/'BetterGI.runtimeconfig.json'),'--depsfile',str(APP/'BetterGI.deps.json'),str(APP/'VisionProbe.dll'),str(path)],text=True))[0]
    assert p['confidence']>=.7 and p['angle'] is not None, 'Camera angle uncertain'
    assert v['quest_confidence']>=.9 and v['quest_bearing_screen_deg'] is not None, 'Quest marker uncertain'
    err=(v['quest_bearing_screen_deg']-p['angle']+180)%360-180
    return dict(frame=o['frameId'],angle=p['angle'],confidence=p['confidence'],target=v['quest_bearing_screen_deg'],error=err)

def run(steps):
    o=send(read(),'observe')
    moves=0
    for _ in range(steps*3):
        v=analyze(o); print(json.dumps(v),flush=True)
        if abs(v['error'])>8:
            dx=max(-300,min(300,round(v['error']*9)))
            o=send(o,'moveMouseBy',dx=dx,dy=0)
        else:
            o=send(o,'hold',key='VK_W',ms=1000); moves+=1
            if moves>=steps: break
    print(json.dumps({'movements':moves,'frame':o['frameId'],'screenshot':str(ROOT/o['screenshotPath'])}),flush=True)

def straight(steps):
    assert steps<=4, 'Only a short visually approved corridor is allowed'
    o=send(read(),'observe')
    for _ in range(steps):
        world_hud(o)
        o=send(o,'hold',key='VK_W',ms=1000)
        print(json.dumps({'frame':o['frameId'],'ocr':[r['text'] for r in o['ocr']]}),flush=True)
    print(str(ROOT/o['screenshotPath']))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--steps',type=int,default=4); p.add_argument('--straight',action='store_true'); args=p.parse_args()
    assert 1<=args.steps<=8
    (straight if args.straight else run)(args.steps)
