"""Index original, receipt-backed RDP experience without calling automated play an expert demonstration."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LOSS_FIELDS = ('droppedFrames','droppedEvents','abandonedFrames','droppedObservations')
ACTORS = {'hybrid-native':'native-controller', 'open-p2p':'learned-policy',
          'calibrated-camera':'calibrated-controller', 'navigation-climb-drop-v1':'recovery-controller'}


def digest_file(path):
    """Hash only an explicitly referenced evidence file, using bounded memory."""
    digest=hashlib.sha256()
    with path.open('rb') as source:
        while block:=source.read(1024*1024):
            digest.update(block)
    return digest.hexdigest()


def rows(path):
    """Keep the original line number beside each metadata row."""
    with path.open(encoding='utf-8') as source:
        for number,line in enumerate(source,1):
            yield number,json.loads(line)


def photo_inputs(folder,repo):
    """Select the actual observer from the unique saved worker command; never substitute today's default model."""
    jobs=list((folder/'jobs').glob('*.job.json'))
    if len(jobs)!=1 or jobs[0].stat().st_size>65536:
        raise ValueError('Experience needs one bounded original worker command')
    argv=json.loads(jobs[0].read_bytes()).get('argv')
    if not isinstance(argv,list) or not all(isinstance(value,str) for value in argv):
        raise ValueError('Original worker arguments are invalid')
    scripts=[i for i,value in enumerate(argv) if Path(value).name=='stream_client.py']
    if len(scripts)!=1:
        raise ValueError('Experience needs its original stream worker')
    args=argv[scripts[0]+1:]

    def path_option(name):
        """Accept either original argument spelling, but reject duplicates and missing values."""
        flag='--'+name
        values=[]
        for i,value in enumerate(args):
            if value==flag:
                if i+1>=len(args) or args[i+1].startswith('--'):
                    raise ValueError('Missing original observer argument')
                values.append(args[i+1])
            elif value.startswith(flag+'='):
                values.append(value[len(flag)+1:])
        if len(values)!=1 or not values[0]:
            raise ValueError('Missing or duplicated original observer argument')
        path=Path(values[0])
        return (path if path.is_absolute() else repo/path).resolve()

    if path_option('output')!=folder/'patrol.json' or path_option('photo-directory')!=folder/'station-photos':
        raise ValueError('Observer command belongs to a different episode')
    checkpoint,qualification=(path_option(name) for name in ('landmark-shadow','photo-qualification'))
    if any(not path.is_relative_to(repo/'artifacts') or not path.is_file() for path in (checkpoint,qualification)):
        raise ValueError('Observer evidence must be retained local artifacts')
    return checkpoint,qualification


def qualify(folder, repo, *, observer=None):
    """Recompute supported outcomes from originals; unsupported failures remain explicitly unqualified."""
    from audit_photo_handoff import audit_photo_handoff
    from audit_queue_failure import audit_failure
    from destination_batch_sender import admitted_plans
    run=json.loads((folder/'patrol.json').read_bytes())
    owner=json.loads((folder/'warm-launcher.json').read_bytes())
    checkpoint,qualification=observer or photo_inputs(folder,repo)
    if owner.get('status')=='completed':
        return audit_photo_handoff(folder/'patrol.json',folder/'patrol-recording',repository=repo,
            photo_root=folder/'station-photos',requests=json.loads((folder/'photo-requests.json').read_bytes()),
            landmark_checkpoint=checkpoint,qualification=qualification,
            batch_plans=admitted_plans(folder) if owner.get('batchCount') else None)
    if run.get('error') in ('No qualified open-queue decision within the 1000 ms released boundary',
                           'Destination photo remained unverified after three stationary retries'):
        return audit_failure(folder,checkpoint,qualification,repo)
    return dict(passed=False,status='unqualified-failure',originalError=run.get('error'))


def action_record(proposal, receipt, observation, video, *, recovery=False):
    """Join a proposed action to its actual terminal receipt and original encoded observation."""
    acceptance=proposal.get('acceptance') or {}
    if (acceptance.get('type')!='accepted' or not receipt or not observation
            or acceptance.get('requestId')!=receipt.get('requestId')
            or proposal.get('frameId')!=receipt.get('frameId')
            or receipt.get('acceptedAtMs')!=acceptance.get('acceptedAtMs')):
        raise ValueError('An admitted input lacks its matching original source and terminal receipt')
    frame=observation['frame']
    if frame['frameId']!=proposal['frameId'] or video and (
            video['frameId']!=frame['frameId'] or video['sourceFrame']!=frame.get('sourceFrame')):
        raise ValueError('Encoded image differs from its actual action source')
    arguments=(proposal.get('arguments') or {}) if recovery else proposal
    owner=arguments.get('modelId') if recovery else (proposal.get('hybridNavigation') or {}).get('owner')
    if not owner or receipt.get('modelId')!=owner or recovery and owner!='navigation-climb-drop-v1':
        raise ValueError('Native receipt controller differs from the actual proposed controller')
    if arguments.get('observationTimestampMs')!=(frame.get('sourceFrame') or {}).get('freshnessAtMs'):
        raise ValueError('Proposed action is not bound to this original source clock')
    return dict(requestId=receipt['requestId'],frameId=frame['frameId'],warmRequestId=proposal.get('warmRequestId'),
        actor=ACTORS.get(owner,'unknown-controller'),controllerId=owner,humanExpertDemonstration=False,
        inputEvidence='native-software-dispatch',physicalExecutionProven=False,
        terminalStatus=receipt['status'],appliedSteps=receipt['appliedSteps'],acceptedAtMs=receipt['acceptedAtMs'],
        endedAtMs=receipt['endedAtMs'],sourceFrame=frame.get('sourceFrame'),sourceTimestampKind=frame.get('sourceTimestampKind'),
        observationProfile=frame.get('observationProfile'),sourceObservation=observation['reference'],
        encodedObservation=video,rawPolicyPrediction=proposal.get('rawPolicySteps'),
        proposedSteps=proposal.get('steps') if not recovery else proposal['arguments']['steps'],
        hasAppliedInput=bool(receipt['appliedSteps']),hasOriginalEncodedImage=video is not None)


def verify_video(path, index, ffprobe='C:/Programs/ffprobe.exe'):
    """Decode one retained clip on one CPU thread and verify its actual frame count, dimensions and timestamps."""
    result=subprocess.run([ffprobe,'-v','error','-threads','1','-select_streams','v:0','-show_frames','-show_streams',
        '-show_entries','stream=codec_name,width,height:frame=width,height,best_effort_timestamp_time','-of','json',str(path)],
        capture_output=True,check=True,timeout=90)
    if result.stderr:
        raise ValueError('Original encoded clip contains decoding errors')
    data=json.loads(result.stdout)
    frames=data.get('frames') or []
    if len(data.get('streams') or [])!=1 or data['streams'][0]['codec_name']!='h264':
        raise ValueError('Original retained H.264 video stream is missing')
    if len(frames)!=len(index):
        raise ValueError('Original encoded clip is truncated or has unindexed images')
    if any((frame['width'],frame['height'])!=(row['width'],row['height'])
            or abs(float(frame['best_effort_timestamp_time'])-row['videoPtsSeconds'])>.001
            for frame,row in zip(frames,index)):
        raise ValueError('Decoded image coverage or timestamps differ from the original source index')
    return dict(decodedFrames=len(frames),complete=True,domain='original encoded recording; not lossless policy RGB')


def build_manifest(folder, output, *, split='diagnostic', repo=ROOT):
    """Seal one separately qualified episode, its losses, original-file hashes and attributed action rows."""
    folder,output,repo=Path(folder).resolve(),Path(output).resolve(),Path(repo).resolve()
    if not folder.is_relative_to(repo/'artifacts/live') or output.is_relative_to(folder):
        raise ValueError('Use a managed live episode and a separate new output directory')
    from episode_split import read_split,reserve_split
    original_run=json.loads((folder/'patrol.json').read_bytes())
    reservation=read_split(folder,original_run['runId'])
    if reservation is not None and reservation['split']!=split:
        raise ValueError('Episode already has a different reserved split')
    observer=photo_inputs(folder,repo)
    proof=qualify(folder,repo,observer=observer)
    run=json.loads((folder/'patrol.json').read_bytes())
    referenced={folder/'patrol.json',folder/'warm-launcher.json',folder/'launcher.json',folder/'broker.json',
                folder/'photo-requests.json',folder/'patrol.json.control.json'}
    proposals,receipts,observations,images={}, {}, {}, {}
    losses=Counter(dict.fromkeys(LOSS_FIELDS,0))
    actors=Counter()
    leases=set()
    captures={}
    refusals=[]
    unknown=[]
    segment_rows=[]
    for entry in run['segments']:
        number=f"{entry['number']:05d}"
        report=folder/'patrol-segments'/(number+'.json')
        if Path(entry['report']).resolve()!=report:
            raise ValueError('Episode segment redirects to another run')
        part=json.loads(report.read_bytes())
        directory=folder/'patrol-recording'/number
        record_path=directory/'recording.json'
        recording=json.loads(record_path.read_bytes())
        referenced.update((report,record_path,directory/'frames.jsonl',directory/'observations.jsonl',directory/'events.jsonl',directory/'frames.mp4'))
        leases.add((part['hello']['sessionId'],part['hello']['ownerEpoch']))
        for field in LOSS_FIELDS:
            losses[field]+=recording[field]
        losses['serverDroppedReceipts']+=part.get('serverDroppedReceipts',0)
        refusals.extend(part.get('localActionRefusals',[]))
        for key in ('unacknowledgedAction','unacknowledgedRecoveryAction'):
            if part.get(key): unknown.append(dict(segment=number,kind=key,evidence=part[key]))
        for proposal in part.get('decisions',[])+part.get('navigationClimbActions',[]):
            accepted=proposal.get('acceptance') or {}
            if accepted.get('type')=='accepted':
                rid=accepted['requestId']
                if rid in proposals: raise ValueError('Duplicate admitted proposal')
                proposals[rid]=(proposal,proposal.get('type')=='navigationClimbAction')
        for receipt in part.get('receipts',[]):
            if receipt['requestId'] in receipts: raise ValueError('Duplicate native terminal receipt')
            receipts[receipt['requestId']]=receipt
        for line,frame in rows(directory/'observations.jsonl'):
            if frame.get('continuityContext'): continue
            fid=frame['frameId']
            if fid in observations: raise ValueError('Duplicate original observation')
            observations[fid]=dict(frame=frame,reference=dict(path=str((directory/'observations.jsonl').relative_to(repo)),line=line))
            source=frame.get('sourceFrame') or {}
            if source.get('captureEpoch') and source.get('timestamp100ns') is not None:
                captures.setdefault(source['captureEpoch'],[]).append(source['timestamp100ns'])
        encoded=0
        video_index=[]
        for line,frame in rows(directory/'frames.jsonl'):
            if frame['videoFrameIndex']!=encoded: raise ValueError('Encoded frame index is not contiguous')
            encoded+=1
            video_index.append(frame)
            fid=frame['frameId']
            image=dict(frameId=fid,path=str((directory/'frames.mp4').relative_to(repo)),videoFrameIndex=frame['videoFrameIndex'],
                       metadataPath=str((directory/'frames.jsonl').relative_to(repo)),metadataLine=line,
                       sourceFrame=frame.get('sourceFrame'),width=frame['width'],height=frame['height'])
            if fid not in images: images[fid]=image
            elif images[fid]['sourceFrame']!=image['sourceFrame']: raise ValueError('Conflicting encoded source identity')
        if encoded!=recording['encodedFrames']: raise ValueError('Encoded frame coverage differs from its seal')
        video_proof=verify_video(directory/'frames.mp4',video_index)
        segment_rows.append(dict(number=entry['number'],complete=recording['complete'],lossless=recording['lossless'],
                                 encodedFrames=encoded,recordedBytes=recording['recordedBytes'],videoDecode=video_proof))
    for rid in sorted(proposals.keys()-receipts.keys()):
        unknown.append(dict(kind='admitted-input-without-terminal-receipt',requestId=rid,proposal=proposals[rid][0]))
    for rid in sorted(receipts.keys()-proposals.keys()):
        unknown.append(dict(kind='terminal-receipt-without-admission-evidence',requestId=rid,receipt=receipts[rid]))
    action_rows=[]
    for rid,(proposal,recovery) in proposals.items():
        if rid not in receipts:
            continue
        fid=proposal['frameId']
        row=action_record(proposal,receipts[rid],observations.get(fid),images.get(fid),recovery=recovery)
        action_rows.append(row)
        if row['hasAppliedInput']: actors[row['actor']]+=1
    missing=[row['requestId'] for row in action_rows if row['hasAppliedInput'] and not row['hasOriginalEncodedImage']]
    qualified=proof.get('passed') is True and run.get('status')=='completed'
    eligible=(qualified and not unknown and not missing and not any(losses.values()) and len(leases)==1
              and 'unknown-controller' not in actors and all(s['complete'] and s['lossless'] for s in segment_rows))
    for row in action_rows:
        row['eligibleForImageActionTraining']=bool(eligible and row['hasAppliedInput'])
    # Hash only the exact source files referenced above and bounded, named queue/photo sidecars.
    for directory,pattern in ((folder/'batches','*.json'),(folder/'station-photos','**/*.json'),(folder/'station-photos','**/*.png')):
        referenced.update(directory.glob(pattern))
    referenced.update((folder/'jobs').glob('*.job.json'))
    for name in ('required-owner.json','queue-policy.json','audit.json','handoff-audit.json','failure-audit.json',
                 'scene-photo-claim.json','scene-photo-permit.json','scene-endurance-permit.json'):
        if (folder/name).is_file(): referenced.add(folder/name)
    originals=[]
    for path in sorted(referenced):
        if not path.resolve().is_relative_to(folder): raise ValueError('Evidence file escapes its original episode')
        originals.append(dict(path=str(path.relative_to(repo)),bytes=path.stat().st_size,sha256=digest_file(path)))
    manifest=dict(format='bettergi-automated-experience-v1',createdAtUtc=datetime.now(timezone.utc).isoformat(),
        split=split,runId=run['runId'],originalRun=str((folder/'patrol.json').relative_to(repo)),
        originalStatus=run['status'],originalEndReason=run['endReason'],originalError=run.get('error'),
        independentAudit=proof,photoObserver={key:dict(path=str(path.relative_to(repo)),sha256=digest_file(path))
            for key,path in zip(('checkpoint','qualification'),observer)},
        humanExpertDemonstrations=False,demonstrationType='automated-controller-experience',
        inputEvidence='native-software-dispatch; game outcomes require separate observation',
        imageDomain='original retained H.264 recordings; lossy pixels, not exact policy RGB',
        learnedPolicyCompetence='Only actions attributed to learned-policy; no claim of independent navigation',
        leases=[list(pair) for pair in sorted(leases)],captureIntervals100ns={k:[min(v),max(v)] for k,v in captures.items()},
        segments=segment_rows,losses=dict(losses),unknownInputOutcomes=unknown,localRefusals=refusals,
        admittedActions=len(proposals),pairedAdmittedActions=len(action_rows),
        appliedActions=sum(bool(row['appliedSteps']) for row in receipts.values()),
        appliedActionsWithPairedSource=sum(row['hasAppliedInput'] for row in action_rows),
        appliedByActor=dict(actors),appliedActionsMissingImages=missing,eligibleForImageActionTraining=bool(eligible),
        originalFiles=originals,trainingQualification='whole-run audit plus complete receipts and original encoded source coverage')
    if output.exists():raise FileExistsError(output)
    manifest['splitReservation']=reserve_split(folder,run['runId'],split)
    output.mkdir(parents=True,exist_ok=False)
    actions_path=output/'actions.jsonl'
    with actions_path.open('x',encoding='utf-8') as target:
        for row in action_rows: target.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
    manifest['actionsFile']=dict(path='actions.jsonl',rows=len(action_rows),sha256=digest_file(actions_path))
    with (output/'manifest.json').open('x',encoding='utf-8') as target:
        json.dump(manifest,target,indent=2,allow_nan=False)
    return manifest


def main():
    """Curate one selected sealed episode; never traverse unrelated releases or model caches."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--split',choices=('train','holdout','diagnostic'),default='diagnostic')
    args=parser.parse_args()
    result=build_manifest(args.folder,args.output,split=args.split)
    print(json.dumps({key:result[key] for key in ('runId','originalStatus','appliedActions','appliedByActor','losses','eligibleForImageActionTraining')}))


if __name__=='__main__':
    main()
