"""Prepare one reviewed bounded hideout action; BetterGI owns all game input."""
import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',type=int,required=True);p.add_argument('--witness',type=int,required=True);p.add_argument('--mode',choices=['inspect','move','drop','bomb','currentProbe'],required=True);p.add_argument('--ms',type=int,default=0);p.add_argument('--key',choices=['VK_W','VK_A','VK_S','VK_D'],default='VK_W');p.add_argument('--dx',type=int,default=0);p.add_argument('--dy',type=int,default=0);p.add_argument('--edge-reviewed',action='store_true');p.add_argument('--flight-reviewed',action='store_true');p.add_argument('--current-landmark');a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot';s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame or not 0<=a.ms<=800 or abs(a.dx)>500 or abs(a.dy)>400:raise SystemExit('Controller state changed or input bound exceeded')
v=dict(reviewed=True,session=s['session'],frameId=a.frame,witnessFrameId=a.witness,createdAt=int(time.time()*1000),mode=a.mode,ms=a.ms,key=a.key,dx=a.dx,dy=a.dy,flightReviewed=a.flight_reviewed,edgeReviewed=a.edge_reviewed)
if a.mode=='currentProbe':
 if not a.current_landmark or len(a.current_landmark.strip())<24 or a.ms or a.dx or a.dy:raise SystemExit('Named visible current and stationary zero-offset probe required')
 v.update(currentReviewed=True,currentLandmark=a.current_landmark)
target=root/'act-two-hideout-aerial-request.json';pending=target.with_suffix('.pending.json');pending.write_text(json.dumps(v),encoding='utf-8');os.replace(pending,target);print(json.dumps(v))
