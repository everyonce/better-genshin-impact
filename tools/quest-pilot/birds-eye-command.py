import argparse, json, os, time, uuid
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--session', required=True)
p.add_argument('--frame', type=int, required=True)
p.add_argument('action', choices=['observe','stop','hold','keyPress','moveMouseBy','click'])
p.add_argument('--key'); p.add_argument('--ms', type=int)
p.add_argument('--dx', type=int); p.add_argument('--dy', type=int)
p.add_argument('--x', type=int); p.add_argument('--y', type=int)
a = p.parse_args()
base = Path(__file__).resolve().parent
repo = base.parents[1]
app = Path(os.environ.get('BETTERGI_PILOT_APP_DIR', repo / 'artifacts' / 'release-r8' / 'BetterGI-English-win-x64')).expanduser().resolve()
root = app / 'User/JsScript/OpeningQuestPilot'
o = json.loads((root/'observation.json').read_text(encoding='utf-8-sig'))
assert o['session'] == a.session and o['frameId'] == a.frame, 'Observation changed; inspect again.'
c = dict(id='step-'+uuid.uuid4().hex, session=a.session, expectedFrameId=a.frame, createdAt=int(time.time()*1000), action=a.action)
for k in ['key','ms','dx','dy','x','y']:
    if getattr(a,k) is not None: c[k] = getattr(a,k)
temporary = root/'command.pending.json'
temporary.write_text(json.dumps(c), encoding='utf-8')
os.replace(temporary, root/'command.json')
deadline=time.time()+12
while time.time()<deadline:
    time.sleep(.2)
    try: r=json.loads((root/'receipt.json').read_text(encoding='utf-8-sig'))
    except (FileNotFoundError,json.JSONDecodeError): continue
    if r['id']==c['id'] and r['status']!='started':
        print(json.dumps(r))
        o=json.loads((root/'observation.json').read_text(encoding='utf-8-sig'))
        print(json.dumps({'session':o['session'],'frameId':o['frameId'],'screenshot':str(root/o['screenshotPath']),'ocr':[r['text'] for r in o['ocr']]}))
        raise SystemExit(0 if r['status']=='completed' else 1)
raise SystemExit('No terminal receipt: inspect journal and process before retrying. Do not replay blindly.')
