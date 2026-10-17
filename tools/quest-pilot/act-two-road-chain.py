"""Bounded navigation -> reviewed Dadaupa defense -> navigation. No unknown-outcome retries."""
import argparse, json, os, subprocess, sys
from pathlib import Path


def defense_candidate(field):
    """Only the already reviewed, close Dadaupa road encounter can enter combat."""
    m=field.get('map') or {};h=field.get('hud') or {};p=h.get('health') or {};bars=h.get('enemyBars') or []
    return (m.get('map')=='Teyvat' and ((m.get('x',0)+1409.45)**2+(m.get('y',0)-1587.87)**2)**.5<=2
            and h.get('world') is True and h.get('groundControls') is True and not h.get('climbing')
            and p.get('max')==4015 and p.get('current',0)>=4015*.85 and 1<=len(bars)<=2
            and all(b.get('width',0)>=20 and b.get('height',0)>=8 for b in bars)
            and (h.get('enemyBarDiagnostic') or {}).get('level')=='any'
            and any(''.join(t.split())=='Lookforthelocationintheriddle' for t in h.get('objectives',[])))


def main():
    p=argparse.ArgumentParser();p.add_argument('--frame',required=True,type=int);p.add_argument('--session',required=True);p.add_argument('--route',required=True,type=Path);a=p.parse_args()
    root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    route=read(a.route);frame=a.frame;results=[];cursor=0;defenses=0
    output=Path('artifacts/act-two-road-chain-latest.json');slice_path=Path('artifacts/act-two-road-chain-route.json')
    def command(kind,*args):
        nonlocal frame
        state=read(root/'controller-status.json')
        if state['state']!='idle' or state.get('activeRequestId') or state['session']!=a.session or state['frameId']!=frame:raise RuntimeError('Controller changed; no input sent')
        q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-command-result.py',kind,*args,'--frame',str(frame),'--session',a.session,'--expected-windows-session-id','7'],capture_output=True,text=True,encoding='utf-8',timeout=95)
        if q.returncode:raise RuntimeError(q.stdout+q.stderr)
        r=json.loads(q.stdout.strip());frame=r['frameId'];results.append(r);output.write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(r),flush=True)
        if r.get('controllerState')!='idle' or not (r.get('result') or {}).get('pauseVerified'):raise RuntimeError('No verified safe terminal; stop chain')
        return r.get('result') or {}
    for segment in range(3):
        part={**route,'waypoints':route['waypoints'][cursor:]};slice_path.write_text(json.dumps(part),encoding='utf-8')
        v=command('navigation','--route',str(slice_path),'--deadline-ms','45000')
        advance=v.get('nextWaypointIndex')
        if type(advance)!=int or not 0<=advance<=len(part['waypoints']):raise RuntimeError('Invalid route cursor')
        cursor+=advance
        if v.get('navigationStatus')=='arrived' and cursor==len(route['waypoints']):return
        if v.get('groundRecovered'):raise RuntimeError('Ground recovered; route needs a different path, never replay into wall')
        if str(v.get('reason','')).startswith('Navigation deadline reached'):continue
        if v.get('reason')!='Guild approach requires safe grounded travel' or defenses>=2:raise RuntimeError('Unsupported route stop; inspect')
        field=read(root/'observations'/a.session/f"frame-{v['pauseProof']['sourceFrameId']:04}.json")
        if not defense_candidate(field):raise RuntimeError('Encounter is outside reviewed defense scope; no combat input')
        q=subprocess.run([sys.executable,'tools/quest-pilot/act-two-field-plan.py','--frame',str(frame),'--witness',str(field['frameId']),'--mode','combat','--enemy-level','any','--actions','[]'],capture_output=True,text=True,encoding='utf-8',timeout=10)
        if q.returncode:raise RuntimeError(q.stdout+q.stderr)
        d=command('questStep','--step','actTwoField');defenses+=1
        after=read(root/'observations'/a.session/f"frame-{d['fieldFrameId']:04}.json");h=after.get('hud') or {};hp=h.get('health') or {}
        if not h.get('world') or not h.get('groundControls') or h.get('climbing') or h.get('enemyBars') or hp.get('max')!=4015 or hp.get('current',0)<4015*.85:raise RuntimeError('Defense did not prove clear healthy ground; stop chain')
    raise RuntimeError('Three-segment chain limit reached; preserve checkpoint')


if __name__=='__main__':main()
