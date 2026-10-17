import json,subprocess,sys,os
from pathlib import Path
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot';s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'));assert s['state']=='idle' and not s.get('activeRequestId');frame=s['frameId'];out=[]
for step in ['actTwoWorldMap','actTwoMapClose']:
 q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','questStep','--step',step,'--frame',str(frame),'--session',s['session'],'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
 if q.returncode:raise SystemExit(q.stdout+q.stderr)
 v=json.loads(q.stdout.strip());out.append(v);print(json.dumps(v),flush=True)
 if v['controllerState']!='idle' or v['status']!='completed':raise SystemExit('Map refresh stopped; inspect')
 frame=v['frameId']
Path('artifacts/act-two-map-refresh-latest.json').write_text(json.dumps(out,indent=2))
