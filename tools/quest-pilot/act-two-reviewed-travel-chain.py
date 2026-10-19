"""Travel through one reviewed map icon and exact unlocked waypoint panel; never retry."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--frame',type=int,required=True);p.add_argument('--session',required=True);p.add_argument('--reference-map',type=int,required=True);p.add_argument('--target',required=True);p.add_argument('--panel',required=True)
p.add_argument('--map-open',action='store_true',help='Continue from a verified idle world-map frame without reopening it')
a=p.parse_args();root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot';frame=a.frame;steps=[]
def read(f):return json.loads((root/'observations'/a.session/f'frame-{f:04}.json').read_text(encoding='utf-8-sig'))
def step(name):
 global frame
 s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
 if s['state']!='idle' or s['session']!=a.session or s['frameId']!=frame:raise SystemExit('Controller changed; no input')
 r=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','questStep','--step',name,'--frame',str(frame),'--session',a.session,'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
 if r.returncode:raise SystemExit(r.stdout+r.stderr)
 q=json.loads(r.stdout.strip());steps.append(q);frame=q['frameId'];Path('artifacts/act-two-reviewed-travel-chain-latest.json').write_text(json.dumps(steps,indent=2),encoding='utf-8')
 if q['controllerState']!='idle' or q['status']=='failed':raise SystemExit('Travel stage stopped; inspect, no retry')
 return q.get('result') or {}
def plan(action,extra=[]):
 r=subprocess.run([sys.executable,'tools/quest-pilot/act-two-map-plan.py','--frame',str(frame),'--action',action,*extra],capture_output=True,text=True,encoding='utf-8')
 if r.returncode:raise SystemExit(r.stdout+r.stderr)
ref=read(a.reference_map)
if ref['session']!=a.session or not ref['hud']['bigMap']:raise SystemExit('Reviewed reference map required')
if a.map_open:
 s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
 if s['state']!='idle' or s.get('activeRequestId') or s['session']!=a.session or s['frameId']!=a.frame:raise SystemExit('Controller changed; no input')
 cur=read(a.frame)
 if not cur['hud']['bigMap']:raise SystemExit('Current frame is not a world map')
 map_frame=a.frame
else:
 o=step('actTwoWorldMap')
 if not o.get('menuOpened') or o.get('chartCycle'):raise SystemExit('Open map required for travel')
 map_frame=o['frameId'];cur=read(map_frame)
deltas=[]
for name in ['Mondstadt','WhisperingWoods','Windrise']:
 def anchor(v):
  r=[r for r in v['ocr'] if ''.join(r['text'].split())==name]
  if len(r)!=1:raise SystemExit('Map anchor missing or ambiguous')
  return r[0]
 b,c=anchor(ref),anchor(cur)
 if abs(b['width']-c['width'])>12 or abs(b['height']-c['height'])>12:raise SystemExit('Map scale/label changed')
 deltas.append((c['x']+c['width']/2-b['x']-b['width']/2,c['y']+c['height']/2-b['y']-b['height']/2))
if any(abs(x-deltas[0][0])>6 or abs(y-deltas[0][1])>6 for x,y in deltas):raise SystemExit('Inconsistent map translation')
x,y=map(int,a.target.split(','));x+=round(sum(d[0] for d in deltas)/3);y+=round(sum(d[1] for d in deltas)/3)
if not 100<x<1800 or not 100<y<950:raise SystemExit('Translated icon outside view')
im=Image.open(root/'observations'/a.session/f"frame-{map_frame:04}.png").convert('RGB').crop((x-14,y-16,x+15,y+17));cyan=sum(1 for r,g,b in im.get_flattened_data() if r<130 and g>110 and b>140 and b>r+35)
if cyan<12:raise SystemExit('Reviewed blue travel icon no longer visible')
plan('inspectReviewedTravelIcon',['--witness',str(map_frame),'--target',f'{x},{y}']);o=step('actTwoMap');panel=read(o['frameId'])
if not any(r['text'].strip()==a.panel and r['x']>1430 and 75<r['y']<145 for r in panel['ocr']):
 rows=panel['ocr']
 overlap=(any(r['text'].strip()=='Teleport Waypoint' and 1200<r['x']<1700 and 680<r['y']<900 for r in rows)
          and any(r['text'].strip()=="Adventurers' Guild" and 1200<r['x']<1700 and 680<r['y']<920 for r in rows)
          and panel['hud']['bigMap'])
 if not overlap:raise SystemExit('Expected waypoint region panel or reviewed overlap menu not verified')
 plan('chooseWaypoint');o=step('actTwoMap');panel=read(o['frameId'])
if not any(r['text'].strip()==a.panel and r['x']>1430 and 75<r['y']<145 for r in panel['ocr']):raise SystemExit('Expected waypoint region panel not verified')
if not any(r['text']=='Teleport Waypoint' for r in panel['ocr']) or not any(r['text']=='Teleport' and r['y']>960 for r in panel['ocr']):raise SystemExit('Exact unlocked waypoint panel required')
plan('teleport');o=step('actTwoMap')
if not o.get('pauseVerified'):raise SystemExit('Travel did not end with verified Inventory')
print(json.dumps(dict(controllerFrame=frame,pauseVerified=True,stages=len(steps),teleportAttempted=True,locationRequiresFreshVerification=True)))
