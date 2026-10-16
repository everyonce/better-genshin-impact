"""Write a finite reviewed exam segment for the existing guarded BetterGI controller."""
import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--frame',type=int,required=True);p.add_argument('--witness',type=int,required=True)
p.add_argument('--mode',choices=['inspect','ground','launch','open','flight','course','abandonInspect'],required=True)
p.add_argument('--dx',type=int,default=0);p.add_argument('--dy',type=int,default=0);p.add_argument('--holds',type=int,default=0)
p.add_argument('--backward',action='store_true')
p.add_argument('--stationary',action='store_true')
p.add_argument('--left',action='store_true')
a=p.parse_args();r=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
s=json.loads((r/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame:raise SystemExit('Controller changed')
w=json.loads((r/'observations'/s['session']/f'frame-{a.witness:04}.json').read_text(encoding='utf-8-sig'))
if w['session']!=s['session'] or w['frameId']!=a.witness or a.witness>=a.frame:raise SystemExit('Witness mismatch')
if abs(a.dx)>750 or abs(a.dy)>500 or not 0<=a.holds<=4 or a.mode in ['inspect','abandonInspect'] and a.holds:raise SystemExit('Input bound exceeded')
p=dict(reviewed=True,session=s['session'],frameId=a.frame,witnessFrameId=a.witness,createdAt=int(time.time()*1000),mode=a.mode,dx=a.dx,dy=a.dy,holds=a.holds)
if a.backward:
 if a.mode!='flight':raise SystemExit('Backward movement requires verified flight')
 p['backward']=True
if a.stationary:
 if a.mode not in ['launch','flight'] or a.backward:raise SystemExit('Stationary requires launch or flight without backward')
 p['stationary']=True
if a.left:
 if a.mode!='flight' or a.stationary or a.backward:raise SystemExit('Lateral correction requires flight without other directions')
 p['left']=True
target=r/'act-two-exam-request.json';pending=target.with_suffix('.pending.json');pending.write_text(json.dumps(p),encoding='utf-8');os.replace(pending,target)
print(json.dumps({'planWritten':True,'frame':a.frame,'mode':a.mode}))
