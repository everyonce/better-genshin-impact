"""Audit recorded fixed-route endpoint and software-input evidence; no game or GPU access."""
import argparse
import json
import math
from pathlib import Path
import statistics

from hybrid_navigation import START, END
from observation_timing import observation_timestamp


def require(condition, message):
    """Fail closed on incomplete evidence rather than inferring successful gameplay."""
    if not condition:
        raise ValueError(message)


def audit(run_path, recordings, *, repository, minimum_legs=1):
    """Join endpoint samples to retained same-frame poses and actions to terminal receipts."""
    run = json.loads(Path(run_path).read_text(encoding='utf-8-sig'))
    require(run.get('status') == 'completed' and run.get('evidenceComplete') is True,
            'Resident run did not finish with complete evidence')
    require(run.get('modelLoads') == 1 and run.get('inputRequested') is True,
            'Expected one resident GPU model and an input-enabled trial')
    parts, frames = [], {}
    for entry in run['segments']:
        part = json.loads((Path(repository)/entry['report']).read_text(encoding='utf-8-sig'))
        parts.append(part)
        recording = part.get('recording') or {}
        require(recording.get('complete') is True and recording.get('workerRetired') is True,
                'Recording is incomplete or its writer has not retired')
        require(not any(recording.get(k, 0) for k in
                ('droppedFrames', 'droppedEvents', 'abandonedFrames', 'droppedObservations')), 'Recording loss')
        path = Path(recordings)/f"{entry['number']:05d}"/'observations.jsonl'
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row.get('continuityContext'):
                    continue
                require(row['frameId'] not in frames, 'Duplicate original frame identity')
                frames[row['frameId']] = row
    require(bool(parts), 'No recorded segments')
    lease = tuple(parts[0]['hello'][k] for k in ('sessionId', 'ownerEpoch'))
    require(all(tuple(p['hello'][k] for k in ('sessionId', 'ownerEpoch')) == lease for p in parts),
            'More than one controller lease was used')
    require(all(p.get('status') == 'completed' for p in parts), 'A segment failed')
    events = [e for p in parts for e in p.get('hybridNavigationEvents', [])]
    starts = [e for e in events if e['type'] == 'hybridStartVerified']
    endpoints = [e for e in events if e['type'] == 'hybridEndpointVerified']
    require(len(starts) == 1, 'Expected one independently admitted starting endpoint')
    require(len(endpoints) >= minimum_legs, 'Insufficient verified route legs')
    target = starts[0]['target']
    prior_frame, prior_at, source_epoch = starts[0]['frameId'], starts[0]['atMs'], None
    for count, endpoint in enumerate(endpoints, 1):
        require(endpoint['completedLegs'] == count and endpoint['endpoint'] == target,
                'Endpoint count or alternating route order differs')
        target_point = START if target == 'start' else END
        samples = endpoint['samples']
        require(len(samples) == 3, 'Endpoint lacks three distinct samples')
        require(endpoint['releaseAtMs'] >= prior_at, 'Endpoint release precedes prior verified progress')
        if source_epoch is None:
            source_epoch = endpoint['sourceEpoch']
        require(endpoint['sourceEpoch'] == source_epoch, 'Capture generation changed')
        for index, sample in enumerate(samples):
            require(sample['frameId'] > prior_frame and sample['atMs'] > prior_at, 'Source did not advance')
            require(sample['atMs'] >= endpoint['releaseAtMs'] + 80, 'Sample precedes the release barrier')
            if index:
                require(sample['atMs'] - samples[index-1]['atMs'] >= 80, 'Endpoint samples are too close')
            for older in samples[:index]:
                require(math.dist((sample['x'], sample['y']), (older['x'], older['y'])) <= 1.5
                        and abs((sample['yawDegrees']-older['yawDegrees']+180) % 360-180) <= 3,
                        'Endpoint samples are not stable')
            require(sample['frameId'] in frames, 'Endpoint source header is missing')
            frame = frames[sample['frameId']]
            pose = frame.get('navigationPose') or {}
            require(pose.get('state') == 'valid' and pose.get('frameId') == sample['frameId'], 'Invalid joined pose')
            require(all(pose[k] == sample[k] for k in ('x', 'y', 'yawDegrees')), 'Endpoint differs from source pose')
            require(frame['sourceFrame']['captureEpoch'] == source_epoch and
                    observation_timestamp(frame) == sample['atMs'], 'Endpoint source clock differs')
            require(math.dist((pose['x'], pose['y']), target_point) <= 2, 'Endpoint is outside its acceptance radius')
            require(pose['layerId'] == 'City_102' and .99 <= pose['positionConfidence'] <= 1
                    and .2 <= pose['yawConfidence'] <= 1, 'Unqualified native match')
            require(frame.get('frameWorldReadiness', {}).get('ready') is True, 'Endpoint is not a world frame')
            prior_frame, prior_at = sample['frameId'], sample['atMs']
        target = 'end' if target == 'start' else 'start'
    decisions = [d for p in parts for d in p.get('decisions', [])]
    accepted = {d['acceptance']['requestId']: d for d in decisions if d.get('acceptance', {}).get('type') == 'accepted'}
    receipts = {r['requestId']: r for p in parts for r in p.get('receipts', [])}
    require(len(accepted) == run['acceptedInputActions'], 'Accepted-action total differs')
    require(set(accepted) <= set(receipts), 'An accepted action has no terminal receipt')
    dispatch_ages = []
    for request, decision in accepted.items():
        receipt = receipts[request]
        require(decision['frameId'] in frames and
                observation_timestamp(frames[decision['frameId']]) == decision['observationTimestampMs'],
                'Action source clock differs from its recorded frame')
        require(receipt['frameId'] == decision['frameId'], 'Receipt joined to another source frame')
        require(receipt['modelId'] == decision['hybridNavigation']['owner'], 'Controller attribution differs')
        steps = receipt.get('appliedSteps') or []
        if steps:
            age = steps[0]['startedAtMs'] - decision['observationTimestampMs']
            require(0 <= age <= 150, 'First software input exceeded the source deadline')
            dispatch_ages.append(age)
    require(parts[-1]['hybridNavigation']['completedLegs'] == len(endpoints), 'Final leg total differs')
    return dict(version=1, passed=True, scope='fixed-courtyard-endpoint-and-software-input-joins',
                verifiedLegs=len(endpoints), controllerLeases=1, modelLoads=1,
                verifiedRouteSeconds=(endpoints[-1]['samples'][-1]['atMs']-starts[0]['atMs'])/1000,
                sourceFrames=len(frames), acceptedActions=len(accepted), appliedActions=len(dispatch_ages),
                medianFirstSoftwareDispatchAgeMs=statistics.median(dispatch_ages) if dispatch_ages else None,
                maximumFirstSoftwareDispatchAgeMs=max(dispatch_ages) if dispatch_ages else None,
                physicalInputDeliveryVerified=False, generalNavigationQualified=False)


def main():
    """Audit only explicitly supplied local evidence paths and save a small result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--recordings', required=True)
    parser.add_argument('--repository', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--minimum-legs', type=int, default=1)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.run, args.recordings, repository=args.repository, minimum_legs=args.minimum_legs)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
