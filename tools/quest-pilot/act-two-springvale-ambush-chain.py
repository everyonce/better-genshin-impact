"""Replay the previously measured Springvale road in bounded guarded segments."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',type=int,required=True);p.add_argument('--witness',type=int,required=True);p.add_argument('--map',type=int,required=True);p.add_argument('--session',required=True);p.add_argument('--start-phase',type=int,choices=range(6),default=0);a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot';frame=a.frame;witness=a.witness
read=lambda n:json.loads((root/'observations'/a.session/f'frame-{n}.json').read_text(encoding='utf-8-sig'))
initial=read(witness);hp=initial['hud']['health'];heading=(initial.get('map')or{}).get('cameraAngle',initial['hud'].get('compassAngle'))
headingBounds=[(20,35),(170,178),(170,178),(170,178),(140,150),(140,150)][a.start_phase]
if hp!={'current':4015,'max':4015} or not headingBounds[0]<=heading<=headingBounds[1]:raise SystemExit('Reviewed full-health route checkpoint and heading required')
def walk(n,ms):return [dict(type='key',key='VK_W',ms=ms) for _ in range(n)]
phases=[([dict(type='look',dx=750,dy=0),dict(type='look',dx=750,dy=150)],130,150),
 (walk(5,600),110,135),(walk(8,800),80,110),([dict(type='look',dx=-300,dy=0)]+walk(7,800),50,80),
 (walk(6,800),30,50),([dict(type='look',dx=-180,dy=0)]+walk(2,600),20,40)]
results=[];started=time.monotonic()
for index,(actions,low,high) in enumerate(phases[a.start_phase:],start=a.start_phase):
 s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
 if s['state']!='idle' or s.get('activeRequestId') or s['session']!=a.session or s['frameId']!=frame:raise SystemExit('Controller changed; no submission')
 q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-field-plan.py','--frame',str(frame),'--witness',str(witness),'--mode','actions','--region-map-witness',str(a.map),'--visual-position-reviewed','--converging-travel','--actions',json.dumps(actions)],capture_output=True,text=True,encoding='utf-8',timeout=10)
 if q.returncode:raise SystemExit(q.stdout+q.stderr)
 q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','questStep','--step','actTwoField','--frame',str(frame),'--session',a.session,'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
 if q.returncode:raise SystemExit(q.stdout+q.stderr)
 r=json.loads(q.stdout.strip());results.append(r);v=r['result'];frame=r['frameId'];proof=v.get('pauseProof')or{}
 Path('artifacts/act-two-springvale-chain-latest.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(dict(phase=index,**r)),flush=True)
 if r['controllerState']!='idle' or not v.get('pauseVerified') or not proof.get('verified'):raise SystemExit('No verified pause; inspect')
 witness=proof['sourceFrameId'];o=read(witness);h=o['hud'];d=v.get('routeDistances',[]);last=d[-1] if d else None
 if v.get('actions')!=len(actions) or v.get('reason')!='Bounded field batch ended; inspect outcome' or h['health']!={'current':4015,'max':4015} or h['enemyBars'] or h['climbing'] or last is None or not low<=last<=high:raise SystemExit('Route evidence changed; stopped safely for fresh review')
print(json.dumps(dict(completed=True,controllerFrame=frame,worldFrame=witness,mapFrame=a.map,wallElapsedMs=round((time.monotonic()-started)*1000))))
