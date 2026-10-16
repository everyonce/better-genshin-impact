"""Write a bounded reviewed field plan; actual input remains in BetterGI."""
import argparse,json,time,os
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--frame',type=int,required=True)
p.add_argument('--witness',type=int,required=True)
p.add_argument('--mode',choices=['actions','combat','climb','releaseClimb','loot'],default='actions')
p.add_argument('--enemy-level',choices=['4','5','11','13','14','any'],default='4')
p.add_argument('--visual-position-reviewed',action='store_true',help='Explicitly reviewed short recovery where minimap matching is unreliable; never used by navigation')
p.add_argument('--region-map-witness',type=int)
p.add_argument('--actions',required=True)
p.add_argument('--single-target-diagnostic',action='store_true')
p.add_argument('--target-anchor',help='Reviewed prior visible target bar JSON: x,y,width,height')
a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame:raise SystemExit('Controller state changed')
witness_path=root/'observations'/s['session']/f'frame-{a.witness:04}.json'
if not witness_path.is_file():raise SystemExit('Field witness is missing; inspect a retained world observation before constructing a plan')
witness=json.loads(witness_path.read_text(encoding='utf-8-sig'))
if witness.get('session')!=s['session'] or witness.get('frameId')!=a.witness or a.witness>=a.frame:
    raise SystemExit('Field witness session/frame does not match the current controller')
if not a.region_map_witness and not isinstance(witness.get('hud',{}).get('enemyBarDiagnostic'),dict):
    raise SystemExit('Field witness lacks enemy-scan diagnostics; obtain a stationary navigation observation first')
plan=dict(reviewed=True,session=s['session'],frameId=a.frame,witnessFrameId=a.witness,createdAt=int(time.time()*1000),mode=a.mode,actions=json.loads(a.actions))
if a.mode=='combat':plan['enemyLevel']='any' if a.enemy_level=='any' else int(a.enemy_level)
if a.single_target_diagnostic:
    if a.mode!='combat' or a.enemy_level!='4' or plan['actions'] or not a.target_anchor:
        raise SystemExit('Diagnostic requires exact Lv4 combat, no supplied actions and a reviewed target anchor')
    plan['singleTargetDiagnostic']=True
    plan['targetAnchor']=json.loads(a.target_anchor)
if a.visual_position_reviewed:plan['visualPositionReviewed']=True
if a.region_map_witness:plan['regionMapFrameId']=a.region_map_witness
target=root/'act-two-field-request.json'
pending=target.with_suffix('.pending.json')
pending.write_text(json.dumps(plan),encoding='utf-8');os.replace(pending,target)
print(json.dumps({'planWritten':True,'session':s['session'],'frame':a.frame,'witness':a.witness}))
