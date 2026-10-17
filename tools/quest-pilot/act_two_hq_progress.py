"""Read-only HQ approach progress check; horizontal arrival never proves entry."""
import json, math, re
from pathlib import Path

def assess(frames):
    samples=[];approach=[]
    for o in frames[-3:]:
        h=o.get('hud') or {}; m=o.get('map') or {}
        rows=o.get('ocr') or []
        labels=[r for r in rows if 1100<=r.get('x',0)<=1600 and 380<=r.get('y',0)<=710]
        has_f=any(r.get('text')=='F' and 1080<=r.get('x',0)<=1170 and 380<=r.get('y',0)<=710 for r in rows)
        entrance=has_f and 'Knights of Favonius' in ' '.join(r.get('text','') for r in labels)
        if entrance:
            return dict(mode='verify_and_interact_with_hq_entrance',horizontalArrivalIsObjectiveProgress=False,entranceFrame=o['frameId'])
        objective=re.sub('[^A-Za-z]','',''.join(h.get('objectives',[])[:2]))
        distances=[re.fullmatch(r'(?:(?:Lower|Higher)\s+)?(\d+)m',t.strip()) for t in h.get('objectives',[])]
        distances=[int(d[1]) for d in distances if d]
        if (h.get('world') and h.get('groundControls') and m.get('map')=='Teyvat' and
            objective=='SolvethemysteryGotoKaeyaattheKnightsofFavoniusHQforahint' and len(distances)==1):
            approach.append(dict(frame=o['frameId'],session=o['session'],distance=distances[0]))
        elevation=[re.fullmatch(r'(Lower|Higher)\s+(\d+)m',t.strip()) for t in h.get('objectives',[])]
        elevation=[x for x in elevation if x]
        if not h.get('world') or not h.get('groundControls') or len(elevation)!=1 or m.get('map')!='Teyvat':
            continue
        if math.hypot(m['x']+775,m['y']-2243)>10:continue
        samples.append(dict(frame=o['frameId'],session=o['session'],direction=elevation[0][1],distance=int(elevation[0][2])))
    mismatch=(len(samples)==3 and len({x['session'] for x in samples})==1 and len({x['frame'] for x in samples})==3 and
              len({x['direction'] for x in samples})==1 and min(x['distance'] for x in samples)>=8 and
              max(x['distance'] for x in samples)-min(x['distance'] for x in samples)<=3)
    regression=(len(approach)==3 and len({x['session'] for x in approach})==1 and len({x['frame'] for x in approach})==3 and
                (approach[-1]['distance']>=approach[0]['distance']+5 or
                 abs(approach[-1]['distance']-approach[0]['distance'])<=2 and
                 max(x['distance'] for x in approach)-min(x['distance'] for x in approach)>=5))
    return dict(mode='ground_level_hq_approach' if mismatch else 'inspect_visible_stair_or_door' if regression else 'inspect_current_approach',
                stopHorizontalContinuation=mismatch or regression,horizontalArrivalIsObjectiveProgress=False,samples=samples,approach=approach)

def record_terminal(root, terminal, output):
    """Retain only three actual navigation endpoint observations; never send input."""
    result=terminal.get('result') or {}
    proof=result.get('pauseProof') or {}
    if not proof.get('verified') or not proof.get('sourceFrameId') or not proof.get('session'):
        return None
    frame=None
    end=proof.get('pauseFrameId',proof['sourceFrameId'])
    for number in range(end,max(proof['sourceFrameId']-1,end-32),-1):
        path=root/f"observations/{proof['session']}/frame-{number:04}.json"
        if not path.exists():continue
        candidate=json.loads(path.read_text(encoding='utf-8-sig'))
        if candidate.get('session')==proof['session'] and candidate.get('hud',{}).get('world'):
            frame=candidate;break
    if frame is None:return None
    history=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
    frames=[o for o in history.get('endpoints',[]) if o.get('session')==frame['session'] and o.get('frameId')!=frame['frameId'] and
            0<=frame.get('timestamp',0)-o.get('timestamp',0)<=600000]
    frames=(frames+[frame])[-3:]
    progress=assess(frames)
    output.write_text(json.dumps(dict(progress=progress,endpoints=frames),indent=2),encoding='utf-8')
    return progress

if __name__=='__main__':
    import argparse,os
    p=argparse.ArgumentParser();p.add_argument('--frames',type=int,nargs=3,required=True);a=p.parse_args()
    root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
    state=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
    frames=[json.loads((root/f"observations/{state['session']}/frame-{n:04}.json").read_text(encoding='utf-8-sig')) for n in a.frames]
    result=assess(frames);result['controllerFrame']=state['frameId'];result['session']=state['session']
    Path('artifacts/act-two-hq-progress.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
