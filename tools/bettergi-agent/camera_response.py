"""Validate isolated mouse pulses and fit a local stationary camera response."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def delta(a, b):
    """Signed shortest yaw change from a to b."""
    return (b - a + 180) % 360 - 180


def require(ok, reason):
    """Stop when a requested causal join or source contract fails."""
    if not ok:
        raise ValueError(reason)


def numbers(*values):
    """Validate real-valued source data."""
    return all(type(v) in (float, int) and math.isfinite(v) for v in values)


def read_probe(path, sequence):
    """Join unmodified terminal steps to stable before/after observations in one sealed lease."""
    data = Path(path).read_bytes()
    archive = json.loads(data)
    require(archive.get('version') == 1 and archive.get('kind') == 'bettergi-camera-response'
            and archive.get('status') == 'completed' and archive.get('sequence') == sequence
            and (archive.get('stop') or {}).get('type') == 'stopped', 'Expected a sealed probe')
    actions, receipts = archive['actions'], archive['receipts']
    require(len(actions) == len(receipts) == (16 if sequence == 'train' else 6), 'Unexpected pulse count')
    by_request = {r['requestId']: r for r in receipts}
    require(len(by_request) == len(receipts) and {a['requestId'] for a in actions} == set(by_request), 'Unattributed action')
    observations = archive['observations']
    frames = {f['frameId']: f for f in observations}
    require(len(frames) == len(observations), 'Duplicate camera observation')
    require(archive.get('captureEpoch') and archive['hello'].get('sessionId') and archive['hello'].get('ownerEpoch'),
            'Missing camera lease identity')
    rows, prior_end = [], -math.inf
    for a in actions:
        dx, ack, r = a['mouseDx'], a['accepted'], by_request[a['requestId']]
        steps = r.get('appliedSteps') or []
        require(type(dx) is int and 0 < abs(dx) <= 250 and a.get('modelId') == r.get('modelId') == 'camera-response-probe-v1'
                and r.get('status') == 'completed' and a['frameId'] == r['frameId'] and ack.get('type') == 'accepted'
                and ack['requestId'] == r['requestId'] and ack['acceptedAtMs'] == r['acceptedAtMs']
                and len(steps) == 1, 'Unconfirmed camera terminal')
        step = steps[0]
        for s in (step, a['step']):
            require(s.get('keys') == [] and s.get('mouseDx') == dx and s.get('mouseDy') == 0
                    and not s.get('buttons') and not s.get('mouseButtons'), 'Camera pulse included another input')
        start = step['startedAtMs']
        require(numbers(start, ack['acceptedAtMs'], r['endedAtMs']) and ack['acceptedAtMs'] <= start < r['endedAtMs'],
                'Invalid camera application clock')
        pre, post, settled = ([frames[k] for k in a[field]] for field in ('preFrameIds', 'postFrameIds', 'settledFrameIds'))
        require(len(pre) >= 3 and len(settled) >= 3 and set(a['settledFrameIds']) <= set(a['postFrameIds'])
                and a['frameId'] in a['preFrameIds'], 'Missing camera source window')
        # A post-dispatch poll can carry an image captured before the actual
        # broker start. Its yaw is pre-input evidence on the compositor clock.
        pre.extend(f for f in post if f['sourceAtMs'] < start)
        post = [f for f in post if f['sourceAtMs'] >= start]
        joined = pre + post
        t = [f['sourceAtMs'] for f in joined]
        source_ticks = [f['sourceFrame']['timestamp100ns'] for f in joined]
        require(all(x < y for x,y in zip(t,t[1:])) and all(x < y for x,y in zip(source_ticks,source_ticks[1:]))
                and prior_end <= t[0] and pre[-1]['sourceAtMs'] <= start <= post[0]['sourceAtMs']
                and pre[-1]['sourceAtMs']-pre[0]['sourceAtMs'] >= 480
                and 0 <= start-frames[a['frameId']]['sourceAtMs'] <= 150 and t[-1] >= start+550
                and settled[-1]['sourceAtMs']-settled[0]['sourceAtMs'] >= 80, 'Insufficient isolated response time')
        prior_end = t[-1]
        pre_yaw = pre[-1]['navigationPose']['yawDegrees']
        rel = []
        for f in joined:
            p, src, gate, motion = f['navigationPose'], f['sourceFrame'], f['frameWorldReadiness'], f['motionEvidence']
            require(p.get('state') == 'valid' and p.get('layerId') == 'City_102' and p.get('frameId') == f['frameId']
                    and numbers(p.get('x'), p.get('y'), p.get('yawDegrees'), p.get('positionConfidence'), p.get('yawConfidence'))
                    and p['positionConfidence'] >= .99 and p['yawConfidence'] >= .2
                    and src.get('captureEpoch') == archive['captureEpoch'] and src.get('freshnessAtMs') == f['sourceAtMs']
                    and f.get('frameQuality') == 'usable' and f.get('inputAvailable') is True
                    and gate.get('ready') is True and (f.get('worldReadiness') or {}).get('ready') is True
                    and gate.get('epoch') == archive['worldEpoch'] and gate.get('sourceFrameId') == f['frameId']
                    and (f.get('worldReadiness') or {}).get('epoch') == gate['epoch'] and gate.get('sourceFrame') == src
                    and motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False
                    and math.hypot(p['x']-pre[0]['navigationPose']['x'],p['y']-pre[0]['navigationPose']['y']) <= .20,
                    'Body moved or camera source became unqualified')
            rel.append(delta(pre_yaw, p['yawDegrees']))
        base = statistics.median(rel[:len(pre)])
        end = statistics.median(delta(pre_yaw, f['navigationPose']['yawDegrees']) for f in settled)
        require(max(rel[:len(pre)])-min(rel[:len(pre)]) <= 2
                and max(abs(delta(pre_yaw, f['navigationPose']['yawDegrees'])-end) for f in settled) <= 1.5,
                'Unstable yaw before or after isolated pulse')
        # Find the first measured post-input frame after which yaw remains in
        # the final tolerance band. This delay is measured separately from gain.
        tol = max(1., abs(end-base)*.10)
        last_outside = max((i for i,v in enumerate(rel[len(pre):]) if abs(v-end)>tol), default=-1)
        require(last_outside+1 < len(post), 'Pulse never settled')
        rows.append(dict(requestId=a['requestId'], frameId=a['frameId'], mouseDx=dx, deltaYaw=end-base,
            startedAtMs=start, endedAtMs=r['endedAtMs'], before=pre[0]['frameId'], after=settled[-1]['frameId'],
            settledMs=post[last_outside+1]['sourceAtMs']-start))
    require(sum(r['mouseDx'] for r in rows) == 0, 'Pulse set is not balanced')
    return dict(path=str(Path(path).resolve()), sha256=hashlib.sha256(data).hexdigest(),
        sessionId=archive['hello']['sessionId'], ownerEpoch=archive['hello']['ownerEpoch'], captureEpoch=archive['captureEpoch'],
        sourceWindow100ns=[frames[actions[0]['preFrameIds'][0]]['sourceFrame']['timestamp100ns'],
                           frames[actions[-1]['postFrameIds'][-1]]['sourceFrame']['timestamp100ns']], rows=rows)


def score(rows, gain):
    """Report signed-turn correctness and errors in measured native degrees."""
    errors = [abs(r['deltaYaw'] - r['mouseDx']*gain) for r in rows]
    return dict(maeDegrees=statistics.mean(errors), maxErrorDegrees=max(errors),
                correctSign=sum(r['deltaYaw']*r['mouseDx'] > 0 for r in rows), n=len(rows))


def fit_response(train, holdout):
    """Fit through-origin OLS on training pulses only, then score one separate unseen lease."""
    require(train['sessionId'] != holdout['sessionId'] and train['ownerEpoch'] != holdout['ownerEpoch']
            and train['sha256'] != holdout['sha256'], 'Calibration holdout must be a separate lease')
    a,b = train['sourceWindow100ns'], holdout['sourceWindow100ns']
    require(train['captureEpoch'] != holdout['captureEpoch'] or max(a[0],b[0])>min(a[1],b[1]), 'Source time overlap')
    rows = train['rows']
    require(sorted(r['mouseDx'] for r in rows) == sorted(sign*n for sign in (-1,1)
            for n in (30,75,125,220) for _ in range(2))
            and sorted(r['mouseDx'] for r in holdout['rows']) == [-170,-95,-45,45,95,170],
            'Unbalanced or unexpected training/held-out magnitudes')
    gain = sum(r['mouseDx']*r['deltaYaw'] for r in rows)/sum(r['mouseDx']**2 for r in rows)
    require(.03 <= gain <= .5, 'Gain outside supported sensitivity range')
    fitted, reference = score(holdout['rows'], gain), score(holdout['rows'], .10)
    delay = max(r['settledMs'] for r in rows)
    eligible = (fitted['correctSign'] == fitted['n'] and score(rows, gain)['correctSign'] == len(rows)
               and fitted['maeDegrees'] + .1 <= reference['maeDegrees'] and fitted['maeDegrees'] <= .9*reference['maeDegrees']
               and fitted['maeDegrees'] < 2 and delay <= 700)
    return dict(format='bettergi-camera-response-v1', trialEligible=eligible, degreesPerCount=gain,
             settleGuardMs=math.ceil(delay+100), maxMouseDx=min(250,max(abs(r['mouseDx']) for r in rows)),
             confidence=dict(calibration='separate stationary holdout', maxErrorDegrees=fitted['maxErrorDegrees'],
                             correctDirectionFraction=fitted['correctSign']/fitted['n']),
             train=train, holdout=holdout, fit=score(rows,gain), heldOut=fitted, fixedPointOne=reference,
             nativeSmallAngleHalfDegree=score(holdout['rows'], .5), nativeLargeAngleThirdDegree=score(holdout['rows'], 1/3))


class CameraCalibration:
    """Suggest a count only for a separately verified, settled native turn."""
    @classmethod
    def load(cls, path):
        """Read the small content-addressed calibration artifact."""
        raw = Path(path).read_bytes()
        obj = cls()
        obj.data = json.loads(raw)
        require(obj.data.get('format') == 'bettergi-camera-response-v1' and obj.data.get('trialEligible') is True,
                'Independent trial criteria not satisfied')
        derived = fit_response(obj.data['train'], obj.data['holdout'])
        require(derived['trialEligible'] and all(derived[k] == obj.data.get(k) for k in (
            'degreesPerCount','settleGuardMs','maxMouseDx','heldOut','fixedPointOne','confidence')),
            'Calibration does not match held-out evidence')
        obj.checkpoint_id = hashlib.sha256(raw).hexdigest()
        return obj

    def suggest(self, error_degrees, *, ms_since_last_mouse):
        """Abstain while a previous command may be in flight or current heading is already aligned."""
        d = self.data
        if (not numbers(error_degrees) or (not numbers(ms_since_last_mouse) and ms_since_last_mouse != math.inf)
                or not 5 < abs(error_degrees) <= 180
                or ms_since_last_mouse < d['settleGuardMs']):
            return None
        return max(-d['maxMouseDx'], min(d['maxMouseDx'], round(error_degrees/d['degreesPerCount'])))


def main():
    """Produce either a qualified calibration or a report explaining its holdout performance."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('train', 'holdout', 'out'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    report = fit_response(read_probe(args.train, 'train'), read_probe(args.holdout, 'holdout'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2, allow_nan=False)
    print(json.dumps({k:report[k] for k in ('trialEligible','degreesPerCount','settleGuardMs','heldOut','fixedPointOne')}))


if __name__ == '__main__':
    main()
