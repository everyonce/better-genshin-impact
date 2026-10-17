import argparse,json,subprocess,sys,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',required=True);p.add_argument('--witness',required=True);p.add_argument('--map',required=True);p.add_argument('--actions',required=True);a=p.parse_args()
q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-field-plan.py','--frame',a.frame,'--witness',a.witness,'--mode','actions','--region-map-witness',a.map,'--visual-position-reviewed','--actions',a.actions],check=True)
r=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot';s=json.loads((r/'controller-status.json').read_text(encoding='utf-8-sig'))
subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py','questStep','--step','actTwoField','--frame',a.frame,'--session',s['session'],'--expected-windows-session-id','7'],check=True)
