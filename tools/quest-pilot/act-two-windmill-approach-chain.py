"""Follow the saved lower approach in <=4-waypoint guarded navigation requests."""
import argparse,json,math,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',type=int,required=True);p.add_argument('--session',required=True);a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
route=read(Path('tools/quest-pilot/routes/act-two-windmill-verified-lower-approach.json'))
frame=a.frame;started=time.monotonic();report=dict(stages=[],status='running')
output=Path('artifacts/act-two-windmill-approach-latest.json')
try:
 for index in range(0,len(route['waypoints']),4):
  state=read(root/'controller-status.json')
  if state['state']!='idle' or state.get('activeRequestId') or state['session']!=a.session or state['frameId']!=frame or time.monotonic()-started>180:raise RuntimeError('Controller or bounded chain deadline changed')
  segment={**route,'waypoints':route['waypoints'][index:index+4]};path=Path(f'artifacts/act-two-windmill-approach-stage-{index//4}.json');path.write_text(json.dumps(segment))
  deadline='4000' if index+4>=len(route['waypoints']) else '45000'
  q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','navigation','--route',str(path),'--deadline-ms',deadline,'--frame',str(frame),'--session',a.session,'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
  if q.returncode:raise RuntimeError(q.stdout+q.stderr)
  r=json.loads(q.stdout.strip().splitlines()[-1]);report['stages'].append(r);output.write_text(json.dumps(report,indent=2));print(json.dumps(r),flush=True)
  v=r.get('result')or{};proof=v.get('pauseProof')or{}
  if r['controllerState']!='idle' or v.get('navigationStatus')!='arrived' or not v.get('pauseVerified') or proof.get('session')!=a.session or not proof.get('verified') or r.get('hqProgress',{}).get('stopHorizontalContinuation'):raise RuntimeError('Navigation did not reach its verified endpoint; inspect without replaying')
  field=read(root/'observations'/a.session/f"frame-{proof['sourceFrameId']:04}.json");h=field['hud'];m=field.get('map')or{};end=segment['waypoints'][-1]
  if h.get('health')!={'current':4015,'max':4015} or not h.get('world') or not h.get('groundControls') or h.get('climbing') or h.get('enemyBars') or m.get('map')!='Teyvat' or math.hypot(m['x']-end['x'],m['y']-end['y'])>2.5:raise RuntimeError('Fresh health, ground or route endpoint changed')
  frame=r['frameId']
 report.update(status='lower-mount-review-required',frame=frame)
except Exception as error:
 report.update(status='stopped',reason=str(error));raise
finally:
 report['elapsedMs']=round((time.monotonic()-started)*1000);output.write_text(json.dumps(report,indent=2))
