"""Pair two frozen landmark observers on all original and decoded views from one held-out fixed-route lease."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path

from audit_hybrid_run import audit, require
from audit_landmark_panel import read, sha, summarize, write
from audit_photo_handoff import bridge_clock
import landmark_recognizer
from landmark_recognizer import FORMAT, LandmarkRecognizer, evaluate, load_views
from landmark_shadow_sources import verify_archive
from qualify_landmarks import main as qualify_file
from train_steering import distinct


def control_metrics(folder, run, route):
    """Bind the thermal samples and independently audited first software-dispatch ages to this native lease."""
    launcher,broker=read(folder/'launcher.json'),read(folder/'broker.json')
    with (folder/'gpu.jsonl').open(encoding='utf-8') as stream:
        samples=[json.loads(line) for line in stream]
    stamps=[datetime.fromisoformat(s['atUtc']) for s in samples]
    start,end=(datetime.fromisoformat(broker[k]) for k in ('startedAtUtc','endedAtUtc'))
    require(launcher['verified'] is True and launcher['runId']==run['runId'] and
            launcher['windowsSessionId']==broker['windowsSessionId']==run['windowsSessionId']
            and not launcher['stopRequested'] and launcher['stopAtC']==78 and len(samples)>1 and
            all(not s.get('error') and 0<s['temperatureC']<launcher['stopAtC'] for s in samples)
            and stamps[0]<=start<end and abs((end-stamps[-1]).total_seconds())<6
            and all(0<(b-a).total_seconds()<=6 for a,b in zip(stamps,stamps[1:])),
            'Thermal measurements do not cover this completed RDP job')
    return dict(windowsSessionId=run['windowsSessionId'],thermalSamples=len(samples),
                peakGpuTemperatureC=max(s['temperatureC'] for s in samples),thermalSha256=sha(folder/'gpu.jsonl'),
                acceptedActions=route['acceptedActions'],appliedActions=route['appliedActions'],
                medianFirstSoftwareDispatchAgeMs=route['medianFirstSoftwareDispatchAgeMs'],
                maximumFirstSoftwareDispatchAgeMs=route['maximumFirstSoftwareDispatchAgeMs'],
                verifiedRouteSeconds=route['verifiedRouteSeconds'])


def original_views(run, recording, archive, decoded, live_head):
    """Join every retained RGB byte string to the native/release proof and to the corresponding decoded source index."""
    meta,visits,samples=decoded
    sources={s['frameId']:s for s in archive['sources']}
    require(set(samples)==set(sources) and len(sources)==archive['sourceCount'],'Original/video sample sets differ')
    originals={}
    for e in run['segments']:
        n=e['number']
        with (recording/f'{n:05d}'/'events.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line)
                if row.get('type')!='landmarkShadowSource':
                    continue
                fid=row['frameId']
                s=sources[fid]
                ev=samples[fid][1]
                require(fid not in originals and all(row[k]==s[k] for k in row if k!='rgb24Base64') and
                        (s['segment'],s['captureEpoch'],s['sourceTimestamp100ns'])==
                        (ev['segment'],ev['captureEpoch'],ev['sourceTimestamp100ns']) and n==s['segment'],
                        'Original source identity differs from decoded-video evidence')
                raw=base64.b64decode(row['rgb24Base64'],validate=True)
                require(len(raw)==192*192*3 and hashlib.sha256(raw).hexdigest()==s['rgbSha256']
                        and live_head.predict(raw)==s['prediction'],'Original bytes differ from live classifier input')
                originals[fid]=(raw,dict(ev,rgbSha256=s['rgbSha256']))
    require(originals.keys()==samples.keys(),'Original pixel archive incomplete')
    evidence=hashlib.sha256()
    for fid in sorted(originals):
        evidence.update(json.dumps(originals[fid][1],sort_keys=True).encode())
    return dict(meta,evidenceSha256=evidence.hexdigest()),visits,originals


def replay(args):
    """Preserve two independent qualifications; each must clear the existing strict native-frame gate."""
    repo=Path(__file__).resolve().parents[2]
    require(not args.out.exists(),'Choose a fresh output folder')
    freeze=read(args.freeze)
    loader=LandmarkRecognizer.load
    scorer=freeze.get('baseScorerSha256',freeze.get('scorerSha256'))
    baseline=freeze.get('sourceCheckpointSha256')
    reference=freeze.get('format')=='bettergi-g8-training-freeze-v1'
    priors=args.prior_episode or []
    if reference:
        from audit_landmark_reference import verify
        require(args.reference_parent and args.reference_lineage and args.reference_screen and args.prior_development and len(priors)==2,
                'Reference successor needs parent, independent training lineage, earlier development and both held-out episodes')
        lineage=read(args.reference_lineage)
        training=[p for p in priors if sha(p)==lineage['trainingEpisodeSha256']]
        require(len(training)==1 and verify(args.reference_parent,args.challenger,args.freeze,training[0])==lineage,
                'Reference training/parent integrity audit did not reproduce')
        weighted_id=read(args.prior_development)['checkpointSha256']
        require(any(p!=training[0] and read(p)['checkpointIds'][1]==weighted_id for p in priors),
                'The complete preceding weighted prospective lease must be excluded')
        screen=read(args.reference_screen)
        require(screen['checkpointIds'][1]==freeze['checkpointSha256'] and
                screen['referenceScreen']['withholdAdditionalLiveTest'] is False,
                'Reference successor did not clear its predeclared historical safety screen')
        baseline=read(args.reference_parent.parent/'freeze.json')['incumbentSha256']
        scorer=freeze['implementationSha256']['landmark_recognizer.py']
    if 'baseScorerSha256' in freeze:
        import weighted_landmark_recognizer
        require(sha(weighted_landmark_recognizer.__file__)==freeze['scorerSha256'] and priors,
                'Weighted challenger requires its frozen scorer and the previous episode exclusion')
        loader=weighted_landmark_recognizer.load_landmark_shadow
    heads=[loader(p) for p in (args.incumbent,args.challenger)]
    require(sha(landmark_recognizer.__file__)==scorer and
            [h.checkpoint_id for h in heads]==[baseline,freeze['checkpointSha256']],
            'Frozen checkpoints or deployed landmark scorer differ')
    path=args.run.resolve()
    run=read(path)
    recording=path.with_name('patrol-recording')
    parts=[read(repo/e['report']) for e in run['segments']]
    clock=bridge_clock(parts)
    fc=freeze['freezeQpc']
    require(fc['clock']=='windows-query-performance-counter' and fc['frequencyHz']==clock['frequency']
            and 0<fc['ticks']<clock['originTicks'],'Holdout lease began before freeze or changed clocks')
    route=audit(path,recording,repository=repo,minimum_circuits=args.circuits,minimum_legs=4*args.circuits,
                landmark_checkpoint=args.challenger)
    require(route['passed'] and route['verifiedCircuits']==args.circuits and not route['partialPatrolLegs'],
            'Prespecified native circuit count was not obtained')
    archive=verify_archive(path,recording,args.challenger,route,repo)
    require(archive==read(path.parent/'station-rgb-audit.json'),'Persisted source audit differs from original replay')
    decoded=load_views(path,'ffmpeg','ffprobe')
    archive_meta=read(args.prior_scores)['sourceIntervals']
    excluded=read(args.independence)
    require(excluded['pairedScoresSha256']==sha(args.prior_scores),'Prior exposure manifest changed')
    for other in [*archive_meta,*excluded['excludedSourceWindows']]:
        distinct([other,decoded[0]])
    prior_rgb={r[k] for r in read(args.prior_scores)['rows'] for k in ('decodedRgbSha256','liveRgbSha256')}
    prior_runs=set()
    for prior in priors:
        previous=read(prior)
        previous_gate=prior.parent/'qualification-exact.json'
        require(sha(previous_gate)==previous['qualification']['exact']['sha256'], 'Prior held-out evidence changed')
        previous_source=read(previous_gate)['run']
        require(previous_source['runId'] not in prior_runs and previous_source['runId']==previous['runId'],
                'Duplicate or mismatched preceding episode')
        prior_runs.add(previous_source['runId'])
        distinct([previous_source,decoded[0]])
        require(previous_source['sourceInterval100ns'][1]<decoded[0]['sourceInterval100ns'][0]
                and previous_source['captureEpoch']==decoded[0]['captureEpoch'], 'Required prior source did not end before this capture')
        prior_rgb.update(r[k] for r in previous['rows'] for k in ('exactSha256','decodedSha256'))
    require(run['runId'] not in freeze.get('excludedWholeLeases',[]) and
            path.parent.name not in freeze.get('excludedWholeLeases',[]),'Development lease cannot be reused')
    prior_rgb.update(freeze.get('developmentOriginals',{}).values())
    if args.prior_development:
        dev=read(args.prior_development)
        require(run['runId'] not in dev['excludedWholeLeases'] and path.parent.name not in dev['excludedWholeLeases'],
                'Earlier development source cannot qualify its successor')
        prior_rgb.update(dev['developmentOriginals'].values())
    exact=original_views(run,recording,archive,decoded,heads[1])
    prior_rgb.update(p['evidence']['rgbSha256'] for h in heads for p in h.data['prototypes'])
    for _,_,samples in (exact,decoded):
        current={e['rgbSha256'] for _,e in samples.values()}
        require(len(current)==len(samples) and current.isdisjoint(prior_rgb),
                'A physical source duplicates an earlier holdout, a prototype or an arrival in this lease')
    args.out.mkdir(parents=True,exist_ok=False)
    by_frame={}
    gates={}
    for name,data in [('exact',exact),('decoded',decoded)]:
        results=[evaluate(h,data) for h in heads]
        pair=args.out/f'paired-{name}.json'
        q=args.out/f'qualification-{name}.json'
        write(pair,dict(format=FORMAT,scope='Original pre-encode RGB192' if name=='exact' else 'Decoded H.264 RGB192',
                        evaluations=results))
        require(qualify_file(['--evaluation',str(pair.resolve()),'--incumbent-sha',heads[0].checkpoint_id,
                             '--challenger-sha',heads[1].checkpoint_id,'--output',str(q)])==0,'Invalid paired evidence')
        gates[name]=dict(sha256=sha(q),**read(q))
        for left,right in zip(results[0]['visits'],results[1]['visits'],strict=True):
            fid=left['frameId']
            row=by_frame.setdefault(fid,dict(runId=run['runId'],segment=left['evidence']['segment'],frameId=fid,
                                             direction=left['role'],station=left['station']))
            require(left['station']==right['station']==row['station'] and left['evidence']==right['evidence'],
                    'Paired ground truth or source differs')
            row[name]=[left['prediction'],right['prediction']]
            row[name+'Sha256']=left['evidence']['rgbSha256']
    rows=list(by_frame.values())
    require(len(rows)==1+4*args.circuits and all((r['frameId'],r['exact'][1])==(s['frameId'],s['prediction']['station'])
            for r,s in zip(rows,archive['sources'],strict=True)),
            'Candidate replay differs from the entire source-indexed original live sweep')
    results={}
    for name in ('exact','decoded'):
        summary=summarize(rows,name)
        summary['directions']={d:summarize([r for r in rows if r['direction']==d],name)['correct']
                               for d in sorted({r['direction'] for r in rows})}
        summary['directionSupport']={d:sum(r['direction']==d for r in rows) for d in summary['directions']}
        summary['precisionRegressions']=[station for station,(base,trial) in summary['perClass'].items()
            if base['precision'] is not None and (trial['precision'] is None or trial['precision']<base['precision'])]
        results[name]=summary
    write(args.out/'episode-audit.json',dict(format='bettergi-prospective-paired-stations-v1',runId=run['runId'],
        runSha256=sha(path),freezeSha256=sha(args.freeze),predeclaredPlanSha256=sha(args.plan),
        originalSourceAuditSha256=sha(path.parent/'station-rgb-audit.json'),checkpointIds=[h.checkpoint_id for h in heads],
        nativeLease=clock,freezeQpc=fc,freezeToLeaseMs=(clock['originTicks']-fc['ticks'])*1000/clock['frequency'],
        priorLeaseWindowChecks=len(archive_meta)+len(excluded['excludedSourceWindows'])+len(priors),
        priorEpisodeSha256=[sha(p) for p in priors],sourceInterval100ns=decoded[0]['sourceInterval100ns'],
        referenceLineageSha256=sha(args.reference_lineage) if reference else None,
        referenceScreenSha256=sha(args.reference_screen) if reference else None,
        circuits=args.circuits,uniqueNativeArrivals=len(rows),episodes=1,originalReplayMatchesLive=len(rows),
        controlMetrics=control_metrics(path.parent,run,route),
        decodedOriginalIdenticalBytes=sum(r['exactSha256']==r['decodedSha256'] for r in rows),
        crossDomainDisagreements=[{k:r[k] for k in ('segment','frameId','station','exact','decoded')}
                                  for r in rows if r['exact']!=r['decoded']],results=results,
        qualification={k:{'recommendation':v['recommendation'],'failedChecks':v['failedChecks'],'sha256':v['sha256']}
                       for k,v in gates.items()},bothGatesPass=all(v['recommendation']=='use-challenger-as-observer' for v in gates.values()),
        sourceFalseAccepts=[dict(frameId=r['frameId'],native=r['station'],classified=r['exact'][1]) for r in rows
                            if r['exact'][1]!=r['station']],
        authority='shadow-only; an episode comparison does not authorize a photo observer or game input',rows=rows))


def main():
    """Perform an exclusive-write, post-seal paired evaluation without any controller or RDP access."""
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('run','incumbent','challenger','freeze','plan','prior-scores','independence','out'):
        p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--prior-episode',type=Path,action='append',help='Exclude an entire preceding episode (repeatable)')
    for flag in ('reference-parent','reference-lineage','reference-screen','prior-development'):
        p.add_argument('--'+flag,type=Path)
    p.add_argument('--circuits',type=int,required=True)
    replay(p.parse_args())


if __name__=='__main__':
    main()
