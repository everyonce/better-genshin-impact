"""Run only the existing bounded Windrise Statue recovery stages; no retries."""
import argparse,json,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',type=int,required=True);p.add_argument('--session',required=True);a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
frame=a.frame;step='actTwoStatueOpen';results=[]
for stage in range(5):
 s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
 if s['state']!='idle' or s.get('activeRequestId') or s['session']!=a.session or s['frameId']!=frame:raise SystemExit('Controller changed; no action submitted')
 q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','questStep','--step',step,'--frame',str(frame),'--session',a.session,'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
 if q.returncode:raise SystemExit(q.stdout+q.stderr)
 r=json.loads(q.stdout.strip());results.append(r);frame=r['frameId'];v=r.get('result') or {}
 Path('artifacts/act-two-statue-heal-chain-latest.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 print(json.dumps(r),flush=True)
 if r.get('status')=='failed':raise SystemExit('Statue stage failed; no retry: '+str(r.get('reason')))
 if r['controllerState']!='idle':raise SystemExit('Controller not idle')
 if v.get('action')=='healStarterParty':
  if not v.get('pauseVerified'):raise SystemExit('Healing ended without verified pause')
  break
 if step=='actTwoStatueOpen' and v.get('conversationActive') or v.get('action') in ['advance','blessing']:step='actTwoStatueHeal'
 else:raise SystemExit('Unexpected Statue stage; inspect before continuing')
else:raise SystemExit('Statue stage bound reached')
