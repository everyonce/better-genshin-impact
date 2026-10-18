"""Prepare a one-use map action from a reviewed current screenshot; never sends input."""
import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--frame',type=int,required=True)
p.add_argument('--action',required=True)
p.add_argument('--witness',type=int)
p.add_argument('--target',help='Reviewed map icon x,y; inspection only')
p.add_argument('--landmarks',default='Mondstadt|Whispering Woods|Windrise')
a=p.parse_args()
r=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
s=json.loads((r/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame or s.get('activeRequestId'):raise SystemExit('Controller state changed')
plan=dict(session=s['session'],frameId=a.frame,reviewed=True,createdAt=int(time.time()*1000),action=a.action)
if a.action=='inspectReviewedTravelIcon':
 if not a.target or a.witness is None or a.witness>a.frame:raise SystemExit('Reviewed icon and map witness required')
 o=json.loads((r/'observations'/s['session']/f'frame-{a.witness:04}.json').read_text(encoding='utf-8-sig'))
 if o['session']!=s['session'] or not o['hud']['bigMap'] or not 0<=plan['createdAt']-o['timestamp']<=600000:raise SystemExit('Fresh same-session full map required')
 names=a.landmarks.split('|');anchors=[]
 if len(names)!=3 or len(set(names))!=3:raise SystemExit('Three distinct geographic anchors required')
 for name in names:
  found=[v for v in o['ocr'] if ''.join(v['text'].split())==''.join(name.split())]
  if len(found)!=1:raise SystemExit(f'Ambiguous or missing map anchor: {name}')
  anchors.append(dict(found[0],text=name))
 x,y=map(int,a.target.split(','))
 if not 100<=x<=1800 or not (100<=y<=950 or 35<=y<100 and 350<=x<=1400):raise SystemExit('Target outside map inspection bounds')
 plan.update(landmarks=anchors,target=dict(x=x,y=y),witnessFrameId=a.witness)
q=r/'act-two-map-request.pending.json';q.write_text(json.dumps(plan),encoding='utf-8');os.replace(q,r/'act-two-map-request.json')
print(json.dumps({'planWritten':True,'session':s['session'],'frame':a.frame,'action':a.action}))
