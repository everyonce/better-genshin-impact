"""Submit one existing guarded BetterGI mission and print its compact terminal result. No retry."""
import json,subprocess,sys
from pathlib import Path
r=subprocess.run([sys.executable,'tools/quest-pilot/act-one-command.py',*sys.argv[1:],'--compact','--wait-seconds','70'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
rows=[json.loads(l)for l in r.stdout.splitlines()if l.startswith('{')]
s=next((v['submitted']for v in rows if 'submitted'in v),None);q=next((v for v in rows if 'terminalId'in v),None)
Path('artifacts/act-two-command-last.json').write_text(json.dumps(dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2),encoding='utf-8')
if not q or q.get('submittedId')!=s or q.get('terminalId')!=s or not q.get('controllerQuiescent'):
 print(r.stdout);print(r.stderr);raise SystemExit('No verified quiescent terminal; inspect before further input')
summary={k:q.get(k)for k in ['terminalId','status','reason','result','elapsedMs','frameId','controllerState']}
if sys.argv[1:2]==['navigation']:
 import os
 from act_two_hq_progress import record_terminal
 try:
  root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
  summary['hqProgress']=record_terminal(root,q,Path('artifacts/act-two-hq-navigation-progress.json'))
 except (OSError,ValueError,KeyError) as error:
  summary['hqProgress']={'mode':'inspect_current_approach','reason':str(error),'horizontalArrivalIsObjectiveProgress':False}
print(json.dumps(summary))
raise SystemExit(r.returncode)
