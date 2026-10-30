"""Distill receipt-backed BetterGI steering and score independent sealed RDP runs."""
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time

from hybrid_routes import PATROL_SEGMENTS, PATROL_STATIONS, STREET_PATROL_ROUTE, patrol_leg, route_points
from steering_head import CLASSES, FEATURES, FORMAT, SteeringHead, features, finite


@dataclass
class Run:
    """Inputs and targets are independent; metadata identifies the original capture lease."""
    meta: dict
    samples: list


def applied_label(decision, frame, terminal):
    """Admit one exact native action whose only applied step began on time and finished or was replaced."""
    h = decision.get('hybridNavigation') or {}
    acceptance = decision.get('acceptance') or {}
    if (h.get('owner') != 'hybrid-native' or h.get('reason') not in ('modelIdleOrOffRoute', 'nativeHeading')
            or decision.get('parseValid') is not True or frame.get('frameQuality') != 'usable'
            or decision.get('frameId') != frame['frameId'] or h.get('pose') != frame.get('navigationPose')
            or decision.get('observationTimestampMs') != (frame.get('sourceFrame') or {}).get('freshnessAtMs')
            or not terminal or acceptance.get('type') != 'accepted' or terminal.get('modelId') != 'hybrid-native'
            or not acceptance.get('requestId') or terminal.get('requestId') != acceptance['requestId']
            or terminal.get('frameId') != frame['frameId'] or terminal.get('acceptedAtMs') != acceptance.get('acceptedAtMs')
            or terminal.get('status') not in ('completed', 'replaced') or len(terminal.get('appliedSteps') or []) != 1):
        return None
    step = terminal['appliedSteps'][0]
    source, ack = decision['observationTimestampMs'], acceptance.get('acceptedAtMs')
    started, ended, deadline = step.get('startedAtMs'), terminal.get('endedAtMs'), decision.get('startBeforeMs')
    if (not all(finite(t) for t in (source, ack, started, ended, deadline))
            or not source <= ack <= started <= deadline <= source+150.001 or ended <= started
            or step.get('mouseDy') != 0 or step.get('buttons') or step.get('mouseButtons')
            or decision.get('steps') != [h.get('step')]
            or any(step.get(k) != h['step'].get(k) for k in ('keys', 'mouseDx', 'mouseDy'))):
        return None
    dx = step.get('mouseDx')
    if h['reason'] == 'modelIdleOrOffRoute' and step.get('keys') == ['W'] and dx == 0:
        return 'forward'
    if h['reason'] == 'nativeHeading' and step.get('keys') == [] and finite(dx) and dx:
        return 'turnRight' if dx > 0 else 'turnLeft'
    return None


def steering_point(route, selection, edges=None):
    """Recover the shadow target from evidence. Directed hops require the independently declared plan."""
    target = selection.get('target')
    legs = selection.get('completedLegs')
    origin = selection.get('fromStation')
    if edges is not None or selection.get('navigationMode') == 'itinerary':
        if (edges is None or route != STREET_PATROL_ROUTE or selection.get('navigationMode') != 'itinerary'
                or type(legs) is not int or not 0 <= legs < len(edges)
                or type(selection.get('segmentIndex')) is not int or selection['segmentIndex'] != legs
                or type(selection.get('destinationOrdinal')) is not int or selection.get('toStation') != target
                or (origin, target, selection['destinationOrdinal'], selection.get('requestedDestination')) != edges[legs]
                or (origin, target) not in PATROL_SEGMENTS or selection.get('steeringPoint') is not None
                or selection.get('bypassPointIndex') is not None):
            return None
        return PATROL_STATIONS[target]
    p = selection.get('steeringPoint')
    if p:
        return p['x'], p['y']
    if selection.get('bypassPointIndex') is not None:
        return None
    if route == STREET_PATROL_ROUTE:
        if type(legs) is int and legs >= 0 and selection.get('toStation') == target and (origin, target) == patrol_leg(legs):
            return PATROL_STATIONS[target]
    elif target in ('start', 'end'):
        return route_points(route)[int(target == 'end')]
    return None


def read_run(path):
    """Hash the actual input artifacts and join unique frame/request IDs across rotation boundaries."""
    path = Path(path).resolve()
    digest = hashlib.sha256()
    def hashed_json(p):
        data = p.read_bytes()
        digest.update(data)
        return json.loads(data)
    manifest = hashed_json(path)
    if (manifest.get('status') != 'completed' or manifest.get('evidenceComplete') is not True
            or not manifest.get('runId') or manifest.get('modelLoads') != 1 or manifest.get('inputRequested') is not True):
        raise ValueError(f'Not a sealed complete single-model input run: {path}')
    from episode_split import read_split
    reservation=read_split(path.parent,manifest['runId'])
    decisions, receipts, routes, frames = {}, {}, {}, {}
    leases, epochs, stamps = set(), set(), []
    for entry in manifest['segments']:
        num = f"{entry['number']:05d}"
        p = hashed_json(path.with_name(path.stem+'-segments')/(num+'.json'))
        recording = p.get('recording') or {}
        if (p.get('status') != 'completed' or p.get('model') != 'open-p2p'
                or p.get('residentRunId') != manifest['runId'] or p.get('serverDroppedReceipts') != 0
                or p.get('observationProfile') != 'p2p-native-hamming-192-v1' or not recording
                or any(recording.get(k) != 0 for k in ('droppedFrames', 'droppedEvents', 'abandonedFrames', 'droppedObservations'))):
            raise ValueError(f'Incomplete or incompatible training archive: {path}, {num}')
        leases.add((p['hello']['sessionId'], p['hello']['ownerEpoch']))
        for d in p['decisions']:
            k = d['frameId']
            if k in decisions:
                raise ValueError('Duplicate decision on the same source')
            decisions[k], routes[k] = d, p['hybridNavigation']['routeId']
        for receipt in p['receipts']:
            k = receipt['requestId']
            if k in receipts:
                raise ValueError('Repeated terminal receipt')
            receipts[k] = receipt
        with (path.with_name(path.stem+'-recording')/num/'observations.jsonl').open('rb') as rows:
            for line in rows:
                digest.update(line)
                f = json.loads(line)
                if f.get('continuityContext'):
                    continue
                epoch = (f.get('sourceFrame') or {}).get('captureEpoch')
                if epoch:
                    epochs.add(epoch)
                    stamps.append(f['sourceFrame']['timestamp100ns'])
                if f['frameId'] in frames:
                    raise ValueError('Duplicate source frame')
                frames[f['frameId']] = f
    if len(leases) != 1 or len(epochs) != 1:
        raise ValueError('Expected one capture epoch and one control lease')
    edges,itinerary_proof=None,None
    if any((row.get('hybridNavigation') or {}).get('navigationMode')=='itinerary' for row in decisions.values()):
        from training_itinerary import qualified_edges
        edges,itinerary_proof=qualified_edges(path.parent)
        digest.update(json.dumps(itinerary_proof,sort_keys=True,separators=(',',':')).encode('utf-8'))
    samples = []
    for k, d in decisions.items():
        f, h = frames.get(k), d.get('hybridNavigation') or {}
        if not f:
            raise ValueError('Missing original observation')
        label = applied_label(d, f, receipts.get((d.get('acceptance') or {}).get('requestId')))
        if label is None:
            continue
        # The saved point was selected before dispatch on this frame. Never project
        # replay waypoints backward from a subsequently learned detour.
        goal = steering_point(routes[k], h, edges)
        if goal is None:
            continue
        raw = d.get('rawPolicySteps')
        row = features(f, goal, raw)
        if row is not None:
            samples.append((row, CLASSES.index(label), f, goal, raw))
    if not samples:
        raise ValueError(f'No eligible native steering labels in {path}')
    policy = p['policyMetadata']
    meta = dict(path=str(path), runId=manifest['runId'], lease=list(leases.pop()), captureEpoch=epochs.pop(),
                sourceInterval100ns=[min(stamps), max(stamps)], evidenceSha256=digest.hexdigest(),
                routes=sorted(set(routes.values())), decisions=len(decisions),
                labels=len(samples), classCounts=dict(Counter(CLASSES[s[1]] for s in samples)),
                visualPolicy=dict(model=p['model'], implementation=policy['implementation'], parameters=policy['parameterCount'],
                    precision=policy['precision'], observationProfile=p['observationProfile'],
                    instruction=(policy.get('goal') or {}).get('instruction'),
                    encoderSha256=(policy.get('goal') or {}).get('encoderSha256')))
    if itinerary_proof is not None:
        meta['directedItinerary']=itinerary_proof
    if reservation is not None:
        meta['datasetSplit']=reservation['split']
        meta['splitReservation']=reservation
    return Run(meta, samples)


def distinct(metas):
    """Reject aliases, split segments and reused RDP leases even under renamed manifests."""
    for key in ('runId', 'lease', 'evidenceSha256'):
        identities = [tuple(m[key]) if key == 'lease' else m[key] for m in metas]
        if len(identities) != len(set(identities)):
            raise ValueError(f'Training and evaluation archives must be independent: duplicate {key}')
    # The same always-on RDP capture can serve many different leases. Keep only
    # physically disjoint source-time windows when the compositor epoch is shared.
    for i, left in enumerate(metas):
        for right in metas[i+1:]:
            a, b = left['sourceInterval100ns'], right['sourceInterval100ns']
            if left['captureEpoch'] == right['captureEpoch'] and max(a[0], b[0]) <= min(a[1], b[1]):
                raise ValueError('Training and evaluation source windows overlap')


def fit(runs):
    """Fit a deterministic class-balanced multinomial linear model using training rows only."""
    import numpy as np
    from episode_split import require_fit_allowed
    require_fit_allowed([r.meta for r in runs])
    distinct([r.meta for r in runs])
    samples = [s for r in runs for s in r.samples]
    x, y = np.array([s[0] for s in samples]), np.array([s[1] for s in samples])
    counts = np.bincount(y, minlength=len(CLASSES))
    if min(counts) == 0:
        raise ValueError('Each steering class needs training support')
    label = np.eye(len(CLASSES))[y]
    weights = np.zeros((x.shape[1], len(CLASSES)))
    importance = 1/(len(CLASSES)*counts[y])
    # Fixed schedule chosen independently of evaluation runs. Standardization
    # uses the published physical feature bounds, so no holdout statistics leak.
    for _ in range(2500):
        logits = x @ weights
        probs = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs /= probs.sum(axis=1, keepdims=True)
        grad = x.T @ ((probs-label)*importance[:, None])
        grad[1:] += .0003*weights[1:]
        weights -= .35*grad
    return SteeringHead(dict(format=FORMAT, deployment='shadow-only', classes=list(CLASSES), features=list(FEATURES),
        weights=weights.T.tolist(), trainingRuns=[r.meta for r in runs],
        optimizer=dict(name='full-batch class-balanced softmax', iterations=2500, learningRate=.35, l2=.0003),
        trainerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        featureCodeSha256=hashlib.sha256(Path(__file__).with_name('steering_head.py').read_bytes()).hexdigest()))


def metrics(labels, predictions):
    """Per-class precision/recall and confusion counts, including explicit P2P abstentions."""
    table = [[0]*(len(CLASSES)+1) for _ in CLASSES]
    for actual, predict in zip(labels, predictions):
        table[actual][predict] += 1
    per = {}
    for i, name in enumerate(CLASSES):
        tp, n = table[i][i], sum(table[i])
        predicted = sum(row[i] for row in table)
        per[name] = dict(support=n, precision=tp/predicted if predicted else 0., recall=tp/n if n else None)
    recall = [d['recall'] for d in per.values() if d['recall'] is not None]
    return dict(accuracy=sum(table[i][i] for i in range(len(CLASSES)))/len(labels),
                balancedAccuracy=sum(recall)/len(recall), perClass=per, confusion=table,
                confusionColumns=[*CLASSES, 'abstain'])


def evaluate(head, run):
    """Measure single-frame CPU inference, and compare to majority, raw P2P and the geometric teacher rule."""
    distinct([*head.checkpoint['trainingRuns'], run.meta])
    labels, learned, visual, rule, timings = [], [], [], [], []
    for row, y, f, goal, raw in run.samples:
        start = time.perf_counter_ns()
        pick = head.predict(f, goal, raw)
        timings.append((time.perf_counter_ns()-start)/1000)
        labels.append(y)
        learned.append(CLASSES.index(pick['actionClass']))
        error = row[1]*10
        rule.append(0 if abs(error) <= 5 else 1 if error < 0 else 2)
        s = raw[0]
        visual.append(0 if s['keys'] == ['W'] and abs(s['mouseDx']) <= 3 and s['mouseDy'] == 0 else
                      (1 if s['mouseDx'] < 0 else 2) if not s['keys'] and s['mouseDx'] and s['mouseDy'] == 0 else 3)
    majority = max(CLASSES, key=lambda c: sum(r['classCounts'].get(c, 0) for r in head.checkpoint['trainingRuns']))
    timings.sort()
    return dict(run=run.meta, learned=metrics(labels, learned), trainMajority=metrics(labels, [CLASSES.index(majority)]*len(labels)),
                rawVisualProposal=metrics(labels, visual), nativeFiveDegreeRule=metrics(labels, rule),
                latencyMicroseconds=dict(p50=timings[len(timings)//2], p95=timings[int(.95*(len(timings)-1))],
                                         max=timings[-1], samples=len(timings)))


def save(path, data):
    """Create a new result, keeping older generation weights and evaluation evidence intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as output:
        json.dump(data, output, indent=2, allow_nan=False)
        output.write('\n')


def compare(previous, candidate, run):
    """Score both frozen heads on one ordered label set and record paired wins and regressions."""
    before, after = evaluate(previous, run), evaluate(candidate, run)
    changes = []
    label_ids = hashlib.sha256()
    for row, y, frame, _, _ in run.samples:
        old = previous.classify(row)['actionClass']
        new = candidate.classify(row)['actionClass']
        label = CLASSES[y]
        source = frame['sourceFrame']
        label_ids.update(f"{source['captureEpoch']}:{source['timestamp100ns']}:{frame['frameId']}:{label}\n".encode())
        if old != new:
            changes.append(dict(frameId=frame['frameId'], signedBearingErrorDegrees=row[1]*10,
                                teacher=label, previous=old, candidate=new))
    return dict(run=run.meta, orderedLabelDigest=label_ids.hexdigest(), previousCheckpointId=previous.checkpoint_id,
        candidateCheckpointId=candidate.checkpoint_id, previous=before['learned'], candidate=after['learned'],
        nativeRule=before['nativeFiveDegreeRule'], wins=sum(r['candidate']==r['teacher'] for r in changes),
        losses=sum(r['previous']==r['teacher'] for r in changes), changed=len(changes), disagreements=changes)


def main():
    """Train repeatable generations or evaluate an existing one on further independent runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    train = commands.add_parser('train')
    train.add_argument('--train-run', action='append', type=Path, required=True)
    eval_cmd = commands.add_parser('evaluate')
    paired = commands.add_parser('compare')
    paired.add_argument('--previous', type=Path, required=True)
    paired.add_argument('--candidate', type=Path, required=True)
    for cmd in (train, eval_cmd, paired):
        cmd.add_argument('--eval-run', action='append', type=Path, required=True)
        cmd.add_argument('--report', type=Path, required=True)
    for cmd in (train, eval_cmd):
        cmd.add_argument('--checkpoint', type=Path, required=True)
    args = parser.parse_args()
    # Keep the CPU-only training job small while the GPU continues gameplay.
    for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS'):
        os.environ[key] = '1'
    if args.command == 'compare':
        a, b = SteeringHead.load(args.previous), SteeringHead.load(args.candidate)
        runs = [read_run(path) for path in args.eval_run]
        distinct([r.meta for r in runs])
        reports = [compare(a, b, run) for run in runs]
        save(args.report, dict(format=FORMAT, deployment='shadow-only', paired=reports))
        for report in reports:
            print(json.dumps({k: report[k] for k in ('orderedLabelDigest','wins','losses','changed')}))
        return
    train_runs = [read_run(path) for path in args.train_run] if args.command == 'train' else []
    head = fit(train_runs) if train_runs else SteeringHead.load(args.checkpoint)
    eval_runs = [read_run(path) for path in args.eval_run]
    distinct(head.checkpoint['trainingRuns']+[r.meta for r in eval_runs])
    if train_runs:
        save(args.checkpoint, head.checkpoint)
    results = [evaluate(head, run) for run in eval_runs]
    save(args.report, dict(format=FORMAT, deployment='shadow-only', checkpoint=str(args.checkpoint.resolve()),
        checkpointSha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(), trainingRuns=head.checkpoint['trainingRuns'],
        evaluations=results, scope='Receipt-backed native forward and horizontal camera steps only. Recovery, '
        'policy-owned actions, stops and other game functions excluded. Scores measure offline teacher agreement.'))
    for result in results:
        print(json.dumps(dict(run=result['run']['runId'], labels=result['run']['labels'],
              accuracy=result['learned']['accuracy'], balancedAccuracy=result['learned']['balancedAccuracy'],
              ruleAccuracy=result['nativeFiveDegreeRule']['accuracy'], latencyUs=result['latencyMicroseconds'])))


if __name__ == '__main__':
    main()
