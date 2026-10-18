"""Prepare one reviewed bounded hideout action; BetterGI owns all game input."""
import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',type=int,required=True);p.add_argument('--witness',type=int,required=True);p.add_argument('--mode',choices=['inspect','move','drop','bomb','currentProbe','flightBomb','groundApproach'],required=True);p.add_argument('--ms',type=int,default=0);p.add_argument('--key',choices=['VK_W','VK_A','VK_S','VK_D'],default='VK_W');p.add_argument('--dx',type=int,default=0);p.add_argument('--dy',type=int,default=0);p.add_argument('--edge-reviewed',action='store_true');p.add_argument('--flight-reviewed',action='store_true');p.add_argument('--current-landmark');p.add_argument('--bomb-target-landmark');p.add_argument('--flight-actions',default='[]');p.add_argument('--ground-landmark');p.add_argument('--ground-actions',default='[]');a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot';s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame or not 0<=a.ms<=800 or abs(a.dx)>500 or abs(a.dy)>400:raise SystemExit('Controller state changed or input bound exceeded')
v=dict(reviewed=True,session=s['session'],frameId=a.frame,witnessFrameId=a.witness,createdAt=int(time.time()*1000),mode=a.mode,ms=a.ms,key=a.key,dx=a.dx,dy=a.dy,flightReviewed=a.flight_reviewed,edgeReviewed=a.edge_reviewed)
if a.mode=='groundApproach' or a.mode=='currentProbe' and a.ground_landmark:
 actions=json.loads(a.ground_actions)
 if a.ms or a.dx or a.dy or a.edge_reviewed or a.mode=='groundApproach' and (a.flight_reviewed or a.bomb_target_landmark) or a.mode=='currentProbe' and (not a.flight_reviewed or not a.bomb_target_landmark) or not a.ground_landmark or len(a.ground_landmark.strip())<24 or not isinstance(actions,list) or not 1<=len(actions)<=3 or any(not isinstance(x,dict) or x.get('key')!='VK_W' or type(x.get('ms')) is not int or not 30<=x['ms']<=800 for x in actions):raise SystemExit('Reviewed straight ground approach requires1-3W holds, each30-800ms, zero camera and no launch/bomb')
 if a.mode=='groundApproach':v.update(groundReviewed=True,groundLandmark=a.ground_landmark,groundActions=actions)
 else:v['groundSetup']=dict(mode='groundApproach',groundReviewed=True,groundLandmark=a.ground_landmark,groundActions=actions,ms=0,dx=0,dy=0)
if a.mode=='currentProbe':
 if not a.current_landmark or len(a.current_landmark.strip())<24 or a.ms or a.dx or a.dy:raise SystemExit('Named visible current and stationary zero-offset probe required')
 v.update(currentReviewed=True,currentLandmark=a.current_landmark)
if a.bomb_target_landmark:
 actions=json.loads(a.flight_actions)
 if a.mode not in ['currentProbe','flightBomb'] or a.ms or a.dx or a.dy or not a.flight_reviewed or len(a.bomb_target_landmark.strip())<24 or not isinstance(actions,list) or len(actions)>3 or any(not isinstance(v,dict) or v.get('key') not in ['VK_W','VK_A','VK_S','VK_D'] or type(v.get('ms')) is not int or not 0<=v['ms']<=800 for v in actions) or sum(v['ms'] for v in actions)>1600:raise SystemExit('Bounded reviewed local bomb followup required')
 v.update(bombFollowup=True,bombTargetLandmark=a.bomb_target_landmark,flightActions=actions)
if a.mode=='flightBomb' and not v.get('bombFollowup'):raise SystemExit('Airborne cycle requires reviewed target and flight proof')
target=root/'act-two-hideout-aerial-request.json';pending=target.with_suffix('.pending.json');pending.write_text(json.dumps(v),encoding='utf-8');os.replace(pending,target);print(json.dumps(v))
