"""Pin complete historical station leases before comparative scoring, then replay both pixel domains."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import landmark_recognizer
from audit_hybrid_run import audit, require
from freeze_landmark_candidate import original_rgb
from landmark_recognizer import CLASSES, LandmarkRecognizer, decode
from observation_timing import observation_timestamp
from patrol_landmarks import indexed_frames
from train_steering import distinct


def read(path):
    """Read a saved JSON document."""
    return json.loads(Path(path).read_bytes())


def sha(path):
    """Hash exactly the named evidence file with bounded memory."""
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path, data):
    """Require a fresh output file for every pin and score."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(data,stream,indent=2,allow_nan=False)
        stream.write('\n')


def leases_for_pin(repository, contract):
    """Enumerate whole leases, keeping or excluding each by the prespecified metadata criteria."""
    selected, excluded = [], []
    incumbent = contract['incumbentSha256']
    for family in contract['families']:
        for path in sorted((repository/family).glob('**/patrol.json')):
            run = read(path)
            identity = run.get('runId')
            reason = contract['excludeRunIds'].get(identity)
            if not reason and (run.get('status')!='completed' or run.get('evidenceComplete') is not True):
                reason = 'incomplete resident evidence'
            parts = []
            if not reason:
                parts = [(e,read(repository/e['report'])) for e in run['segments']]
                marks = [m for _,p in parts for m in p['hybridNavigationEvents']
                         if m['type'] in ('hybridStartVerified','hybridEndpointVerified')]
                if not marks or any((m.get('visualStation') or {}).get('checkpointId')!=incumbent for m in marks):
                    reason = 'lacks the frozen incumbent on every physical station'
            if reason:
                excluded.append(dict(path=str(path),runId=identity,reason=reason))
                continue
            # Pin the entire lease, every sealed recording and all available lossless station files.
            folder = path.parent
            files = {path}
            for e,_ in parts:
                directory = folder/'patrol-recording'/f"{e['number']:05d}"
                files.update([repository/e['report'],*[directory/k for k in
                             ('events.jsonl','frames.jsonl','observations.jsonl','recording.json','frames.mp4')]])
            files.update(p for p in (folder/'station-photos').rglob('*') if p.is_file())
            hello = parts[0][1]['hello']
            selected.append(dict(path=str(path),runId=identity,lease=[hello['sessionId'],hello['ownerEpoch']],
                                 sourceEpoch=marks[0]['sourceEpoch'],nativeArrivals=len(marks),
                                 files={str(f.relative_to(repository)):sha(f) for f in sorted(files)}))
    require(selected and len({p['runId'] for p in selected})==len(selected), 'Empty or aliased selected leases')
    return dict(format='bettergi-historical-landmark-panel-v1',contract=contract,leases=selected,excluded=excluded)


def score_lease(repository, lease, heads):
    """Use only source-bound physical station events; include every sealed native arrival exactly once."""
    pat=Path(lease['path'])
    run=read(pat)
    dr=pat.parent
    require(run['runId']==lease['runId'],'Resident identity differs')
    seen, file_joins, rows, ticks = set(),set(),[],[]
    for e in run['segments']:
        n=e['number']
        part=read(repository/e['report'])
        directory=dr/'patrol-recording'/f'{n:05d}'
        hello=part['hello']
        require([hello['sessionId'],hello['ownerEpoch']]==lease['lease'],'Changed lease')
        frames,count=indexed_frames(directory,part)
        ticks.extend(f['sourceFrame']['timestamp100ns'] for f in frames.values())
        with (directory/'events.jsonl').open(encoding='utf-8') as stream:
            marks=[r for line in stream if (r:=json.loads(line)).get('type') in
                   ('hybridStartVerified','hybridEndpointVerified','hybridDestinationPhotoRetry')]
        require(marks==[r for r in part['hybridNavigationEvents'] if r['type'] in
                       ('hybridStartVerified','hybridEndpointVerified','hybridDestinationPhotoRetry')],
                'Station reports differ from original station journal')
        require(all(r['type']!='hybridDestinationPhotoRetry' for r in marks),
                'This historical fixed-route panel expects one observation per physical arrival')
        refs=[frames[m['samples'][-1]['frameId']] for m in marks]
        decoded=decode(directory,refs,count,'ffmpeg','ffprobe') if refs else {}
        for m,f in zip(marks,refs):
            fid=f['frameId']
            sample=m['samples'][-1]
            visual=m['visualStation']
            source=f['sourceFrame']
            truth=m['station']
            require(fid not in seen and truth in CLASSES and visual['checkpointId']==heads[0].checkpoint_id
                    and fid==visual['frameId']==sample['frameId']==f['navigationPose']['frameId']
                    and observation_timestamp(f)==sample['atMs'] and source['captureEpoch']==m['sourceEpoch']==lease['sourceEpoch']
                    and all(f['navigationPose'][k]==sample[k] for k in ('x','y','yawDegrees')),'Station source identity differs')
            seen.add(fid)
            rgb=decoded[f['videoFrameIndex']]
            row=dict(runId=lease['runId'],segment=n,frameId=fid,station=truth,sourceTimestamp100ns=source['timestamp100ns'],
                     captureEpoch=m['sourceEpoch'],liveIncumbent=visual['prediction']['station'],liveRgbSha256=visual['rgbSha256'],
                     videoFrameIndex=f['videoFrameIndex'],decodedRgbSha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                     decoded=[h.predict(rgb)['station'] for h in heads])
            photo=m.get('photoSurveyVisit') or {}
            fn=photo.get('file') or photo.get('retryEvidenceFile')
            if fn:
                base=dr/'station-photos'
                if m.get('warmRequestId'):
                    base/=m['warmRequestId']
                path=(base/fn).resolve()
                require(path.is_relative_to(base.resolve()) and path not in file_joins and
                        photo['station']==truth and photo['frameId']==fid and photo['liveRgbSha256']==visual['rgbSha256']
                        and photo['sourceEpoch']==m['sourceEpoch'] and photo['sourceTimestamp100ns']==source['timestamp100ns'],
                        'Original photo source or request differs')
                digest=photo.get('pngSha256') or photo['retryEvidencePngSha256']
                raw=original_rgb(path,digest,visual['rgbSha256'])
                rgb=np.frombuffer(raw,dtype=np.uint8).reshape(192,192,3)
                labels=[h.predict(rgb)['station'] for h in heads]
                require(labels[0]==row['liveIncumbent'],'Frozen incumbent did not reproduce its original pixel verdict')
                file_joins.add(path)
                row.update(exact=labels,png=str(path.relative_to(repository)),pngSha256=digest)
            rows.append(row)
    require(len(rows)==lease['nativeArrivals'] and file_joins=={p.resolve() for p in (dr/'station-photos').rglob('*.png')},
            'A verified arrival or original station PNG is missing from this panel')
    return rows,dict(runId=run['runId'],lease=lease['lease'],captureEpoch=lease['sourceEpoch'],
                     sourceInterval100ns=[min(ticks),max(ticks)],evidenceSha256=sha(pat))


def summarize(rows, domain):
    """Count negative classes, paired incident changes and lease-level results without counting retry frames as trials."""
    panel=[r for r in rows if domain in r]
    stations={}
    for station in CLASSES:
        stats=[]
        for h in (0,1):
            truth=sum(r['station']==station for r in panel)
            pred=sum(r[domain][h]==station for r in panel)
            tp=sum(r['station']==r[domain][h]==station for r in panel)
            stats.append(dict(truePositive=tp,falsePositive=pred-tp,falseNegative=truth-tp,trueNegative=len(panel)-truth-pred+tp,
                              precision=tp/pred if pred else None,recall=tp/truth if truth else None))
        stations[station]=stats
    by_lease={}
    for rid in sorted({r['runId'] for r in panel}):
        sample=[r for r in panel if r['runId']==rid]
        by_lease[rid]=dict(arrivals=len(sample),correct=[sum(r[domain][h]==r['station'] for r in sample) for h in (0,1)])
    return dict(evaluatedArrivals=len(panel),perClass=stations,leases=by_lease,
                correct=[sum(r[domain][h]==r['station'] for r in panel) for h in (0,1)],
                completelyCorrectLeases=[sum(v['arrivals']==v['correct'][h] for v in by_lease.values()) for h in (0,1)],
                pairedChanges=[{k:r[k] for k in ('runId','segment','frameId','station',domain)}
                               for r in panel if r[domain][0]!=r[domain][1]])


def exclude_development(corpus, freeze, parent_digest):
    """Derive a retrospective-only panel from an already disclosed pin by removing entire development leases."""
    exposed=set(freeze['excludedWholeLeases'])
    keep,removed=[],[]
    for lease in corpus['leases']:
        if lease['runId'] in exposed or Path(lease['path']).parent.name in exposed:
            removed.append(dict(runId=lease['runId'],path=lease['path'],reason='Whole lease now exposed for challenger development'))
        else:
            keep.append(lease)
    require(removed and keep and freeze['developmentOriginals'],'Expected declared development overlap and surviving controls')
    return dict(corpus,leases=keep,excluded=[*corpus['excluded'],*removed],parentPinSha256=parent_digest,
                derivedForChallengerSha256=freeze['checkpointSha256'],wholeDevelopmentExclusions=sorted(exposed),
                excludedDevelopmentRgbSha256=sorted(set(freeze['developmentOriginals'].values())),
                priorDisclosure='All historical G4/G6 results were already disclosed before this challenger comparison.')


def screen_reference(rows, previous, plan, rejections, metas):
    """Audit a new reference bank against the already-pinned pixels, including changes hidden by average accuracy."""
    require(plan['eligibleWholeRunIds']==sorted(m['runId'] for m in metas) and
            rejections==plan['rejectedBeforeScoring']==previous['rejectedBeforeScoring'],
            'Admissible or rejected whole-lease set changed from the prespecified screen')
    old={(r['runId'],r['frameId']):r for r in previous['rows']}
    require(len(rows)==len(old)==len(previous['rows']),'Reference screen lost a source')
    result={}
    for domain in ('exact','decoded'):
        harms,gains=[],[]
        by_episode={}
        for row in rows:
            baseline=old[(row['runId'],row['frameId'])]
            require(all(row.get(k)==baseline.get(k) for k in
                        ('runId','segment','frameId','station','sourceTimestamp100ns','captureEpoch','liveIncumbent',
                         'liveRgbSha256','decodedRgbSha256','videoFrameIndex','png','pngSha256')) and
                    (domain in baseline)==(domain in row),'Pixels, source, native label or coverage changed')
            if domain not in row:
                continue
            incumbent,challenger=row[domain]
            require(incumbent==baseline[domain][0],'Incumbent prediction changed on the same source')
            counters=by_episode.setdefault(row['runId'],dict(arrivals=0,incumbentCorrect=0,challengerCorrect=0))
            counters['arrivals']+=1
            counters['incumbentCorrect']+=incumbent==row['station']
            counters['challengerCorrect']+=challenger==row['station']
            outcome=dict(runId=row['runId'],frameId=row['frameId'],station=row['station'],
                         incumbent=incumbent,challenger=challenger)
            if incumbent!=challenger and incumbent==row['station']:
                harms.append(outcome)
            if incumbent!=challenger and challenger==row['station']:
                gains.append(outcome)
        clean_harms=[r for r in harms if by_episode[r['runId']]['incumbentCorrect']==by_episode[r['runId']]['arrivals']]
        result[domain]=dict(perEpisode=by_episode,newErrors=harms,correctedErrors=gains,newErrorsInFormerlyPerfectLeases=clean_harms)
    result['withholdAdditionalLiveTest']=bool(result['exact']['newErrors'] or result['decoded']['newErrorsInFormerlyPerfectLeases'])
    return result


def main():
    """Pin the metadata-only inventory, or compare two frozen classifiers against the exact same pinned sources."""
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    pin=sub.add_parser('pin')
    pin.add_argument('--contract',type=Path,required=True)
    subset=sub.add_parser('exclude-development')
    subset.add_argument('--pin',type=Path,required=True)
    subset.add_argument('--freeze',type=Path,required=True)
    score=sub.add_parser('score')
    for flag in ('pin','incumbent','challenger','freeze'):
        score.add_argument('--'+flag,type=Path,required=True)
    score.add_argument('--parent-pin',type=Path,help='Original immutable panel when a later challenger excludes exposed leases')
    score.add_argument('--screen-plan',type=Path,help='Prespecified whole-lease harm test for a frozen reference-bank successor')
    score.add_argument('--reference-scores',type=Path,help='Original source rows and G4 verdicts on the pinned panel')
    score.add_argument('--reference-parent',type=Path,help='Exact predecessor template checkpoint of the reference-bank successor')
    for cmd in (pin,subset,score):
        cmd.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    repo=Path(__file__).resolve().parents[2]
    if a.mode=='pin':
        write(a.out,leases_for_pin(repo,read(a.contract)))
        return
    corpus=read(a.pin)
    freeze=read(a.freeze)
    if a.mode=='exclude-development':
        write(a.out,exclude_development(corpus,freeze,sha(a.pin)))
        return
    loader=LandmarkRecognizer.load
    frozen_base=freeze.get('sourceCheckpointSha256')
    scorer=freeze.get('baseScorerSha256',freeze.get('scorerSha256'))
    screen_plan,previous=None,None
    if a.screen_plan:
        require(a.reference_scores and a.reference_parent and freeze.get('classificationScorer') and
                freeze['parentCheckpointSha256']==sha(a.reference_parent) and
                freeze['trainingManifestSha256']==sha(a.freeze.parent/'source-manifest.json') and
                freeze['predeclarationSha256']==sha(a.freeze.parent/'predeclaration.json'),
                'Reference successor freeze or recorded development differs')
        screen_plan,previous=read(a.screen_plan),read(a.reference_scores)
        require(sha(a.pin)==screen_plan['priorInventorySha256'] and sha(a.reference_scores)==screen_plan['priorScoresSha256']
                and previous['pinSha256']==sha(a.pin),'Reference panel differs from its prespecified controls')
        frozen_base=corpus['contract']['incumbentSha256']
        scorer=freeze['implementationSha256']['landmark_recognizer.py']
    if 'baseScorerSha256' in freeze:
        import weighted_landmark_recognizer
        require(a.parent_pin and sha(weighted_landmark_recognizer.__file__)==freeze['scorerSha256'] and
                corpus==exclude_development(read(a.parent_pin),freeze,sha(a.parent_pin)),
                'Weighted challenger needs its correct prior exposure exclusions and frozen scorer')
        loader=weighted_landmark_recognizer.load_landmark_shadow
    h=[loader(p) for p in (a.incumbent,a.challenger)]
    require(h[0].checkpoint_id==corpus['contract']['incumbentSha256']==frozen_base
            and h[1].checkpoint_id==freeze['checkpointSha256']
            and sha(landmark_recognizer.__file__)==scorer,
            'Classifier or scorer differs from its pin')
    if screen_plan:
        parent=read(a.reference_parent)
        require(h[1].data['prototypes'][:len(parent['prototypes'])]==parent['prototypes']
                and h[1].data['trainingRuns']==[*parent['trainingRuns'],freeze['trainingSource']]
                and len(h[1].data['prototypes'])==freeze['totalPrototypes'],'Frozen reference bank lineage differs')
    rows,metas,rejections=[],[],[]
    admissible=[]
    for lease in corpus['leases']:
        # Check all physical records before scoring any classifier. A failed lease stays in the published denominator.
        pat=Path(lease['path'])
        require(lease['runId'] not in freeze.get('excludedWholeLeases',[]) and
                pat.parent.name not in freeze.get('excludedWholeLeases',[]),'An exposed development lease is present')
        for name,digest in lease['files'].items():
            path=(repo/name).resolve()
            require(path.is_relative_to(repo) and sha(path)==digest,'Pinned evidence changed: '+name)
        try:
            native=audit(pat,pat.parent/'patrol-recording',repository=repo)
            require(native['passed'],'Resident route audit failed')
        except ValueError as exc:
            losses=[]
            for e in read(pat)['segments']:
                recording=read(repo/e['report'])['recording']
                losses.append({k:recording.get(k) for k in
                               ('droppedFrames','droppedEvents','abandonedFrames','droppedObservations')})
            rejections.append(dict(runId=lease['runId'],reason=str(exc),recordingLossBySegment=losses,
                                   excludedWholeLease=True,unscoredArrivals=lease['nativeArrivals']))
            continue
        admissible.append(lease)
    for lease in admissible:
        found,meta=score_lease(repo,lease,h)
        rows.extend(found)
        metas.append(meta)
    for head in h:
        distinct([*head.data['trainingRuns'],*metas])
    retained={r[k] for r in rows for k in ('liveRgbSha256','decodedRgbSha256')}
    require(retained.isdisjoint(freeze.get('developmentOriginals',{}).values()),
            'A live or decoded source duplicates a development original')
    write(a.out,dict(format='bettergi-historical-landmark-scores-v1',classification='retrospective',
                     pinSha256=sha(a.pin),freezeSha256=sha(a.freeze),checkpointIds=[v.checkpoint_id for v in h],
                     pinnedLeases=len(corpus['leases']),rejectedBeforeScoring=rejections,completePinnedCorpus=not rejections,
                     independentLeases=len(metas),sourceIntervals=metas,priorDisclosure=corpus.get('priorDisclosure'),
                     excludedDevelopmentRgbCount=len(set(freeze.get('developmentOriginals',{}).values())),
                     decoded=summarize(rows,'decoded'),
                     exact=summarize(rows,'exact'),originalIncumbentCorrect=sum(r['liveIncumbent']==r['station'] for r in rows),
                     referenceScreen=screen_reference(rows,previous,screen_plan,rejections,metas) if screen_plan else None,
                     screenPlanSha256=sha(a.screen_plan) if screen_plan else None,
                     exactSubsetSelection='Historical photo collectors retained requested images conditional on the incumbent verdict.',
                     rows=rows))


if __name__=='__main__':
    main()
