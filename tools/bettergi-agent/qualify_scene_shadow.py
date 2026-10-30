"""Independently qualify the predeclared two-lease scene observer; this file grants no photo authority."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import statistics

from audit_hybrid_run import audit,require
from landmark_recognizer import CLASSES,LandmarkRecognizer
from landmark_shadow_sources import verify_archive
from weighted_landmark_recognizer import load_landmark_shadow


def digest(raw):
    """Bind specified original evidence without walking caches or unrelated artifacts."""
    return hashlib.sha256(raw).hexdigest()


def scores(rows):
    """Keep paired original-image counts, class coverage and new errors visible."""
    require(all(r[k] in CLASSES for r in rows for k in ('native','baseline','candidate')),'Unknown station class')
    return dict(images=len(rows),baselineCorrect=sum(r['baseline']==r['native'] for r in rows),
        candidateCorrect=sum(r['candidate']==r['native'] for r in rows),
        regressions=[r for r in rows if r['baseline']==r['native']!=r['candidate']],
        corrections=[r for r in rows if r['candidate']==r['native']!=r['baseline']],
        uniquePerClass={s:len({r['rgbSha256'] for r in rows if r['native']==s}) for s in CLASSES},
        perClass={s:dict(images=sum(r['native']==s for r in rows),
            baselineCorrect=sum(r['native']==s and r['baseline']==s for r in rows),
            candidateCorrect=sum(r['native']==s and r['candidate']==s for r in rows)) for s in CLASSES})


def run(comparison,series,output,repo):
    """Recompute route, receipts, releases, original replay and paired recognition for both fresh leases."""
    comparison,series,output,repo=map(lambda p:Path(p).resolve(),(comparison,series,output,repo))
    require(not output.exists(),'Choose a new immutable qualification output')
    plan_raw=(comparison/'prospective-plan.json').read_bytes()
    plan=json.loads(plan_raw)
    require(plan['format']=='bettergi-p2p-scene-prospective-plan-v1','Unknown prospective plan')
    for key in ('checkpoint','offlineModel','offlineResults','executionParity'):
        ref=plan[key]
        require(digest((comparison/ref['path']).read_bytes())==ref['sha256'],'Frozen comparison artifact changed')
    for name,sha in plan['sourceCodeSha256'].items():
        require(digest((repo/'tools/bettergi-agent'/name).read_bytes())==sha,'Prospective runtime source changed')
    baseline_path=repo/'artifacts/agent/landmarks/gen-04.json'
    require(digest(baseline_path.read_bytes())==plan['baselineSha256'],'Baseline changed')
    original_plan=json.loads((comparison/'plan.json').read_bytes())
    source_raw=(comparison/'sources.json').read_bytes()
    require(digest(source_raw)==original_plan['sourcesSha256'],'Original data split changed')
    dataset=json.loads(source_raw)
    exclusions=dataset['trainingLeases']+dataset['holdoutLeases']
    previous_rgb={row['rgbSha256'] for key in ('training','holdout') for row in dataset[key]}
    checkpoint=comparison/plan['checkpoint']['path']
    candidate=load_landmark_shadow(checkpoint)
    baseline=LandmarkRecognizer.load(baseline_path)
    manifest_raw=(series/'series.json').read_bytes()
    manifest=json.loads(manifest_raw)
    limits=plan['trials']
    require(limits==dict(leases=2,circuitsPerLease=10,originalsPerLease=41,uniquePerClassPerLease=10,
        maximumSecondsPerLease=400,maximumSeriesSeconds=850),'Different qualification bounds')
    require(manifest['status']=='completed' and manifest['identity']==plan['identity']
        and manifest['requestedBatches']==manifest['verifiedBatches']==limits['leases']==len(manifest['batches'])
        and manifest['circuitsPerBatch']==limits['circuitsPerLease']
        and manifest['seriesSeconds']==limits['maximumSeriesSeconds'],'Incomplete or changed prospective series')
    from experiments.p2p_station_features import ThermalGuard
    thermal=ThermalGuard()
    thermal.check(True)
    trials=[]
    for entry in manifest['batches']:
        folder=Path(entry['directory']).resolve()
        require(folder.parent==series and entry['status']=='verified','Unbound prospective batch')
        report_raw=(folder/'patrol.json').read_bytes()
        report=json.loads(report_raw)
        launcher=json.loads((folder/'launcher.json').read_bytes())
        require(launcher['verified'] is True and launcher['stopRequested'] is False and launcher['stopReason'] is None
            and launcher['wallTimeLimitSeconds']==limits['maximumSecondsPerLease']
            and launcher['childPid']==plan['identity']['child']['processId']
            and launcher['rootPid']==plan['identity']['root']['processId'],'Changed owner, bounds or interrupted launcher')
        recording=folder/'patrol-recording'
        evidence=audit(folder/'patrol.json',recording,repository=repo,minimum_legs=4*limits['circuitsPerLease'],
            minimum_circuits=limits['circuitsPerLease'],landmark_checkpoint=checkpoint,
            ffmpeg='C:/Programs/ffmpeg.exe',ffprobe='C:/Programs/ffprobe.exe')
        thermal.check(True)
        originals=verify_archive(folder/'patrol.json',recording,checkpoint,evidence,repo)
        thermal.check(True)
        part=json.loads((repo/report['segments'][0]['report']).read_bytes())
        lease=[part['hello']['sessionId'],part['hello']['ownerEpoch']]
        interval=[min(row['sourceTimestamp100ns'] for row in originals['sources']),max(row['sourceTimestamp100ns'] for row in originals['sources'])]
        epoch=originals['sources'][0]['captureEpoch']
        require(interval[0]*plan['qpcFrequency']>plan['frozenQpc']*10_000_000,'Prospective input predates the plan')
        for old in exclusions+trials:
            require(report['runId']!=old['runId'] and lease!=old['lease'] and
                (epoch!=old['captureEpoch'] or interval[0]>old['sourceInterval100ns'][1]
                 or interval[1]<old['sourceInterval100ns'][0]),'Prospective lease overlaps prior evidence')
        rows=[]
        captured={}
        for name in {row['eventsFile'] for row in originals['sources']}:
            path=Path(name).resolve()
            require(path.is_relative_to(recording),'Unbound original RGB journal')
            with path.open(encoding='utf-8') as stream:
                for event in map(json.loads,stream):
                    if event.get('type')=='landmarkShadowSource':
                        require(event['frameId'] not in captured,'Duplicate original source')
                        captured[event['frameId']]=event
        require(len(captured)==len(originals['sources'])==limits['originalsPerLease'],'Incomplete original views')
        live=evidence['landmarkShadow']['sources']
        for source,view in zip(originals['sources'],live,strict=True):
            thermal.check()
            event=captured[source['frameId']]
            rgb=base64.b64decode(event['rgb24Base64'],validate=True)
            sha=digest(rgb)
            require(sha==source['rgbSha256']==view['liveRgbSha256'] and sha not in previous_rgb,
                'Changed original or previously evaluated pixels')
            prediction=candidate.predict(rgb)
            require(prediction==source['prediction'] and prediction['station']==view['live']
                and prediction['squaredDistance']==view['liveSquaredDistance'],'Original live prediction changed')
            rows.append(dict(frameId=source['frameId'],rgbSha256=sha,native=source['station'],
                baseline=baseline.predict(rgb)['station'],candidate=prediction['station'],elapsedMs=view['elapsedUs']/1000))
        result=scores(rows)
        times=[row['elapsedMs'] for row in rows]
        latency=dict(median=statistics.median(times),p95=statistics.quantiles(times,n=100,method='inclusive')[94],maximum=max(times))
        metadata=part['policyMetadata']['landmarkObserver']
        require(all(json.loads((repo/p['report']).read_bytes())['policyMetadata']['landmarkObserver']==metadata
            for p in report['segments']),'Observer reloaded or changed across segments')
        temperatures=[json.loads(line)['temperatureC'] for line in (folder/'gpu.jsonl').read_bytes().splitlines()]
        passed=bool(not result['regressions'] and all(v>=limits['uniquePerClassPerLease'] for v in result['uniquePerClass'].values())
            and all(v['candidateCorrect']>=v['baselineCorrect'] for v in result['perClass'].values())
            and latency['p95']<=10 and latency['maximum']<=25 and 0<=metadata['cudaAllocatedDeltaMiB']<=256
            and max(temperatures)<78 and metadata['observerModelLoads']==report['modelLoads']==evidence['modelLoads']==evidence['controllerLeases']==1
            and evidence['maximumFirstSoftwareDispatchAgeMs']<=150 and evidence['verifiedLegs']==4*limits['circuitsPerLease'])
        trials.append(dict(passed=passed,runId=report['runId'],lease=lease,captureEpoch=epoch,sourceInterval100ns=interval,
            folder=str(folder),residentSha256=digest(report_raw),originalArchiveSha256=digest(json.dumps(originals,sort_keys=True).encode()),
            metrics=result,liveObserverLatencyMs=latency,observerRuntime=metadata,maximumTemperatureC=max(temperatures),
            routeSeconds=evidence['verifiedRouteSeconds'],appliedActions=evidence['totalAppliedActions'],
            medianDispatchAgeMs=evidence['medianFirstSoftwareDispatchAgeMs'],maximumDispatchAgeMs=evidence['maximumFirstSoftwareDispatchAgeMs'],
            independentNativeAuditPassed=True,exactOriginalReplayPassed=True,rows=rows))
        previous_rgb.update(row['rgbSha256'] for row in rows)
    result=dict(format='bettergi-p2p-scene-prospective-result-v1',passed=all(t['passed'] for t in trials),
        scope='Independent prospective shadow qualification only; no photographic authority granted',
        planSha256=digest(plan_raw),seriesSha256=digest(manifest_raw),checkpointSha256=candidate.checkpoint_id,
        scorerSha256=digest(Path(__file__).read_bytes()),trials=trials,combined=scores([r for t in trials for r in t['rows']]),
        offlineAuditThermalSamples=thermal.samples)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ('passed','checkpointSha256','combined')},indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('comparison','series','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--repository',type=Path,default=Path(__file__).resolve().parents[2])
    args=parser.parse_args()
    run(args.comparison,args.series,args.output,args.repository)
