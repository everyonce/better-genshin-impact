"""Submit one existing guarded BetterGI mission and print its compact terminal result. No retry."""
import json,subprocess,sys
from pathlib import Path
r=subprocess.run([sys.executable,'tools/quest-pilot/act-one-command.py',*sys.argv[1:],'--compact','--wait-seconds','70'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
rows=[json.loads(l)for l in r.stdout.splitlines()if l.startswith('{')]
s=next((v['submitted']for v in rows if 'submitted'in v),None);q=next((v for v in rows if 'terminalId'in v),None)
Path('artifacts/act-two-command-last.json').write_text(json.dumps(dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2),encoding='utf-8')
if not q or q.get('submittedId')!=s or q.get('terminalId')!=s or not q.get('controllerQuiescent'):
 print(r.stdout);print(r.stderr);raise SystemExit('No verified quiescent terminal; inspect before further input')
print(json.dumps({k:q.get(k)for k in ['terminalId','status','reason','result','elapsedMs','frameId','controllerState']}))
raise SystemExit(r.returncode)
