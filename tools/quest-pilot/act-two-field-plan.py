"""Write a bounded reviewed field plan; actual input remains in BetterGI."""
import argparse,json,time,os,subprocess,shutil
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--frame',type=int,required=True)
p.add_argument('--witness',type=int,required=True)
p.add_argument('--mode',choices=['actions','combat','climb','releaseClimb','loot'],default='actions')
p.add_argument('--enemy-level',choices=['4','5','10','11','12','13','14','any'],default='4')
p.add_argument('--visual-position-reviewed',action='store_true',help='Explicitly reviewed short recovery where minimap matching is unreliable; never used by navigation')
p.add_argument('--region-map-witness',type=int)
p.add_argument('--actions',required=True)
p.add_argument('--recovery-switch',action='store_true',help='One guarded switch between Kaeya and the Traveler during an eligible encounter')
p.add_argument('--converging-travel',action='store_true',help='Exact ambush travel stops on increasing or two unchanged distance steps')
p.add_argument('--raptor-approach',action='store_true',help='Reviewed <=1200ms approach to visible Raptor enemies before bounded combat')
p.add_argument('--raptor-pursuit',action='store_true',help='Bounded exact level13 centering and approach in the Raptor ambush')
p.add_argument('--native-combat',action='store_true')
p.add_argument('--native-windows',type=int,choices=[1,2,3],default=1)
p.add_argument('--native-search',action='store_true')
p.add_argument('--climb-probe',action='store_true',help='One600ms climb to reveal stamina; no continuation without fresh visible stamina')
p.add_argument('--shield-probe',action='store_true',help='One manually reviewed visible charge-shield Cryo-first probe, never a sustained cycle')
p.add_argument('--landing-reviewed',action='store_true',help='Fresh screenshot confirms a nearby safe landing for one guarded climb release')
p.add_argument('--event-reposition',action='store_true',help='Short movement-only reposition within the freshly verified active Ley Line event')
p.add_argument('--native-avatar',choices=['Kaeya','Lumina'],default='Kaeya')
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
if a.converging_travel:plan['convergingTravel']=True
if a.raptor_approach:plan['raptorApproach']=True
if a.raptor_pursuit:plan['raptorPursuit']=True
if a.recovery_switch:
    if a.mode!='actions' or len(plan['actions'])!=1 or plan['actions'][0] not in [dict(type='key',key=k,ms=60) for k in ['VK_1','VK_3']]:raise SystemExit('Recovery switch requires one60ms party-slot key')
    plan['recoverySwitch']=True
if a.climb_probe:
    if a.mode!='climb' or plan['actions']!=[dict(type='key',key='VK_W',ms=600)]:raise SystemExit('Climb probe is one600ms W only')
    plan['climbProbe']=True
if a.event_reposition:plan['eventReposition']=True
if a.landing_reviewed:
    if a.mode!='releaseClimb' or plan['actions']!=[dict(type='key',key='VK_X',ms=60)]:raise SystemExit('Reviewed landing requires one60ms climb release')
    plan['landingReviewed']=True
if a.native_combat:
    if a.mode!='combat' or a.enemy_level not in ['10','13'] or not a.region_map_witness or plan['actions']:raise SystemExit('Native combat requires stationary regional Lv10/Lv13 plan')
    if a.native_windows>1 and a.enemy_level!='13':raise SystemExit('Multiple native windows require exact Raptor level13')
    if a.native_search:
        if a.enemy_level!='13':raise SystemExit('Native search requires exact Raptor level13')
        plan['nativeSearch']=True
    plan['nativeWindows']=a.native_windows
    plan['nativeCombat']=True
    plan['nativeAvatar']=a.native_avatar
if a.shield_probe:
    if not a.native_combat or a.native_avatar!='Kaeya' or a.enemy_level!='13':raise SystemExit('Shield probe requires Kaeya native Lv13 mode')
    plan.update(shieldProbe=True,shieldReviewed=True)
if a.mode=='combat':plan['enemyLevel']='any' if a.enemy_level=='any' else int(a.enemy_level)
if a.single_target_diagnostic:
    if a.mode!='combat' or a.enemy_level!='4' or plan['actions'] or not a.target_anchor:
        raise SystemExit('Diagnostic requires exact Lv4 combat, no supplied actions and a reviewed target anchor')
    plan['singleTargetDiagnostic']=True
    plan['targetAnchor']=json.loads(a.target_anchor)
if a.visual_position_reviewed:plan['visualPositionReviewed']=True
if a.region_map_witness:
    plan['regionMapFrameId']=a.region_map_witness
    map_path=root/'observations'/s['session']/f'frame-{a.region_map_witness:04}.json'
    node=shutil.which('node')
    if not node:raise SystemExit('Node is required for read-only regional witness validation')
    # Reuse the actual hotloaded guard instead of duplicating its map policy.
    check=subprocess.run([node,'-e',"const fs=require('fs'),g=require(process.argv[1]),o=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^\\uFEFF/,''));if(!g.regionalMap(o,Number(process.argv[3]),process.argv[4],Number(process.argv[5])))process.exit(2);",str((root/'act-two-field.js').resolve()),str(map_path.resolve()),str(plan['createdAt']),s['session'],str(1800000 if a.native_combat else 600000)],capture_output=True,text=True,timeout=5)
    if check.returncode and not (a.native_combat and any(__import__('re').fullmatch(r'Defeatallopponents[0-6]/7',''.join(t.split())) for t in witness.get('hud',{}).get('objectives',[]))):raise SystemExit('Regional witness failed local guard validation; inspect a fresh map before submission')
target=root/'act-two-field-request.json'
pending=target.with_suffix('.pending.json')
pending.write_text(json.dumps(plan),encoding='utf-8');os.replace(pending,target)
print(json.dumps({'planWritten':True,'session':s['session'],'frame':a.frame,'witness':a.witness}))
