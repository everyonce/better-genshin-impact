"""One reviewed ground segment followed by map measurement and verified pause; never retries."""
import argparse,json,math,subprocess,sys,os,time
from pathlib import Path
from datetime import datetime,timezone
p=argparse.ArgumentParser(description=__doc__)
for name in ['leg-id','start-landmark','end-landmark']:p.add_argument('--'+name,required=True)
p.add_argument('--leg-budget-ms',type=int,default=6400)
p.add_argument('--forward-ms','--movement-ms',dest='forward_ms',type=int,required=True)
p.add_argument('--direction',choices=['VK_W','VK_A','VK_S','VK_D'],default='VK_W')
p.add_argument('--heading',type=float)
p.add_argument('--via',choices=['springvaleSouth15'])
a=p.parse_args()
loop_started=time.monotonic()
if not 30<=a.forward_ms<=6400 or not a.forward_ms<=a.leg_budget_ms<=10000:raise SystemExit('Finite segment/leg budget required')
ledger=Path('artifacts/act-two-statue-landmark-segments.jsonl');prior=[json.loads(l) for l in ledger.read_text(encoding='utf-8-sig').splitlines()] if ledger.exists() else []
used=sum(e['data'].get('movementBudgetMs',e['data'].get('forwardBudgetMs',0)) for e in prior if e.get('type')=='planned' and e.get('data',{}).get('legId')==a.leg_id)
if used+a.forward_ms>a.leg_budget_ms:raise SystemExit('Leg budget exhausted; no input submitted')
c=json.loads(Path('artifacts/act-two-chart-position-latest.json').read_text(encoding='utf-8-sig'));frame=c['controllerFrame'];session=c['session'];region=c['positionEvidence']['frameId'];w=c['steps'][-1]['result']['pauseProof']['sourceFrameId']
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
o=json.loads((root/'observations'/session/f'frame-{w:04}.json').read_text(encoding='utf-8-sig'))
# Regional permission is separate from the newest centered position measurement.
# Prefer the newest map passing the unchanged runtime predicate; never relax it
# merely because a newer map has an OCR box/label dropout.
map_candidates=[]
for path in (root/'observations'/session).glob('frame-*.json'):
 candidate=json.loads(path.read_text(encoding='utf-8-sig'))
 if candidate.get('hud',{}).get('bigMap') and 0<=time.time()*1000-candidate.get('timestamp',0)<=600000:map_candidates.append(candidate)
map_candidates=sorted(map_candidates,key=lambda q:q['timestamp'],reverse=True)[:12]
select=subprocess.run(['node','-e',"const fs=require('fs'),g=require(process.argv[1]),a=JSON.parse(fs.readFileSync(0,'utf8')),s=process.argv[2],n=Number(process.argv[3]);const o=a.find(o=>g.regionalMap(o,n,s));if(!o)process.exit(2);process.stdout.write(String(o.frameId));",str((root/'act-two-field.js').resolve()),session,str(round(time.time()*1000))],input=json.dumps(map_candidates),capture_output=True,text=True,encoding='utf-8',timeout=5)
if select.returncode:raise SystemExit('No recent regional map passes runtime predicate; inspect fresh map, no input submitted')
region=int(select.stdout)

actions=[]
if a.heading is not None:
 angle=o.get('hud',{}).get('compassAngle',(o.get('map') or {}).get('cameraAngle'))
 if not isinstance(angle,(int,float)) or not math.isfinite(angle):raise SystemExit('Fresh camera orientation unavailable')
 dx=round(((a.heading-angle+540)%360-180)*10.15)
 if abs(dx)>250:raise SystemExit('Inspect camera first; segment turn exceeds250pixels')
 if dx:actions.append(dict(type='look',dx=dx,dy=0))
remaining=a.forward_ms
while remaining:ms=min(800,remaining);actions.append(dict(type='key',key=a.direction,ms=ms));remaining-=ms
if len(actions)>8:raise SystemExit('Too many bounded actions')
record=dict(utc=datetime.now(timezone.utc).isoformat(),session=session,legId=a.leg_id,startFrame=w,startLandmark=a.start_landmark,endLandmark=a.end_landmark,startPosition=c['positionEvidence']['position'],sourcePoseFrame=c['positionEvidence']['frameId'],regionPermissionFrame=region,movementBudgetMs=a.forward_ms,movementDirection=a.direction,forwardBudgetMs=a.forward_ms if a.direction=='VK_W' else 0,legBudgetMs=a.leg_budget_ms,actions=actions,arrivalVerified=False,control={'planner':'agent landmark review','executor':'BetterGI local guarded routine','humanGameplayInputs':0})
statue=dict(x=-575.6,y=1859.34)
if a.via:
 record['via']={'id':15,'position':{'x':-912.9803,'y':1790.307},'purpose':'Supporting waypoint discovery and southern road toward same Statue'}
 record['via']['distanceBefore']=math.hypot(record['startPosition']['x']+912.9803,record['startPosition']['y']-1790.307)
record['objectiveDistanceBefore']=math.hypot(record['startPosition']['x']-statue['x'],record['startPosition']['y']-statue['y'])
record['timings']={'plannedForwardInputMs':a.forward_ms if a.direction=='VK_W' else 0,'plannedDirectionalInputMs':a.forward_ms,'productiveGameplayMs':None,'verifiedPauseAndModelReviewMs':None}
def save(kind):
 with ledger.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(type=kind,data=record))+'\n')
 Path('artifacts/act-two-statue-segment-latest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
preflight=subprocess.run([sys.executable,'tools/quest-pilot/act-two-field-plan.py','--frame',str(frame),'--witness',str(w),'--mode','actions','--region-map-witness',str(region),'--visual-position-reviewed','--actions',json.dumps(actions)],capture_output=True,text=True,encoding='utf-8')
if preflight.returncode:raise SystemExit(preflight.stderr.strip() or preflight.stdout.strip() or 'Field preflight rejected; no input submitted')
save('planned')
r=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','questStep','--step','actTwoField','--frame',str(frame),'--session',session,'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
if r.returncode:raise SystemExit(r.stdout+r.stderr)
t=json.loads(r.stdout.strip());v=t.get('result') or {};record.update(terminalId=t['terminalId'],fieldFrame=v.get('fieldFrameId'),health=v.get('health'),controllerFrame=t['frameId'],pauseVerified=v.get('pauseVerified'),actionsCompleted=v.get('actions'));record['timings']['fieldRequestMs']=t.get('elapsedMs');save('field-terminal')
if t['controllerState']!='idle' or not v.get('pauseVerified') or v.get('health',{}).get('current')!=4015 or v.get('actions')!=len(actions):raise SystemExit('Segment changed/stopped early; inspect before follow-up')
q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-chart-position-chain.py','--fast','--frame',str(t['frameId']),'--session',session],capture_output=True,text=True,encoding='utf-8',timeout=100)
record['chartReturncode']=q.returncode
if q.returncode==0:
 c=json.loads(Path('artifacts/act-two-chart-position-latest.json').read_text(encoding='utf-8-sig'));record.update(endPosition=c['positionEvidence']['position'],endPoseFrame=c['positionEvidence']['frameId'],controllerFrame=c['controllerFrame']);record['measuredDisplacement']=math.hypot(record['endPosition']['x']-record['startPosition']['x'],record['endPosition']['y']-record['startPosition']['y'])
if q.returncode==0:
 if a.via:record['via']['distanceAfter']=math.hypot(record['endPosition']['x']+912.9803,record['endPosition']['y']-1790.307)
 record['objectiveDistanceAfter']=math.hypot(record['endPosition']['x']-statue['x'],record['endPosition']['y']-statue['y']);record['objectiveDistanceReduced']=record['objectiveDistanceBefore']-record['objectiveDistanceAfter'];record['timings']['chartAndLocalizationMs']=c['elapsedMs']
record['timings']['localLoopWallMs']=round((time.monotonic()-loop_started)*1000)
save('observed');print(json.dumps(record))
if q.returncode:raise SystemExit(q.stderr or q.stdout)
