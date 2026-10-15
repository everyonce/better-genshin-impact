"""Write a bounded reviewed field plan; actual input remains in BetterGI."""
import argparse,json,time,os
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--frame',type=int,required=True)
p.add_argument('--witness',type=int,required=True)
p.add_argument('--mode',choices=['actions','combat','climb'],default='actions')
p.add_argument('--enemy-level',choices=['4','5','any'],default='4')
p.add_argument('--visual-position-reviewed',action='store_true',help='Explicitly reviewed short recovery where minimap matching is unreliable; never used by navigation')
p.add_argument('--actions',required=True)
a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame:raise SystemExit('Controller state changed')
plan=dict(reviewed=True,session=s['session'],frameId=a.frame,witnessFrameId=a.witness,createdAt=int(time.time()*1000),mode=a.mode,actions=json.loads(a.actions))
if a.mode=='combat':plan['enemyLevel']='any' if a.enemy_level=='any' else int(a.enemy_level)
if a.visual_position_reviewed:plan['visualPositionReviewed']=True
target=root/'act-two-field-request.json'
pending=target.with_suffix('.pending.json')
pending.write_text(json.dumps(plan),encoding='utf-8');os.replace(pending,target)
print(json.dumps({'planWritten':True,'session':s['session'],'frame':a.frame,'witness':a.witness}))
