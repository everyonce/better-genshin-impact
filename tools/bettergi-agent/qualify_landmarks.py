"""Compare two frozen landmark observers on the same native-labeled street patrol. Writes evidence only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from landmark_recognizer import CLASSES, FORMAT, ROLES, metrics


STOPS = ('stair-front', 'sidewalk-junction', 'west-lamp', 'sidewalk-junction', 'stair-front')
REQUIRED_PER_STATION = 10


def require(condition, message):
    """Reject incomplete provenance or metrics before considering a generation change."""
    if not condition:
        raise ValueError(message)


def digest(value, length=64):
    """Recognize the evaluator's lowercase checkpoint hashes, frame hashes and run IDs."""
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def verify_run(meta):
    """Require the audited lease, source clock interval and frozen image digest."""
    require(isinstance(meta, dict) and isinstance(meta.get('path'), str) and meta['path']
            and digest(meta.get('runId'), 32) and digest(meta.get('captureEpoch'), 32)
            and digest(meta.get('evidenceSha256')), 'Missing frozen run or capture identity')
    lease, interval = meta.get('lease'), meta.get('sourceInterval100ns')
    require(isinstance(lease, list) and len(lease) == 2 and all(digest(v, 32) for v in lease),
            'Invalid controller lease')
    require(isinstance(interval, list) and len(interval) == 2 and all(type(v) is int for v in interval)
            and 0 < interval[0] < interval[1], 'Invalid capture interval')
    circuits = meta.get('circuits')
    require(type(circuits) is int and circuits > 0 and type(meta.get('orderedVisits')) is int
            and type(meta.get('uniqueImages')) is int and meta['orderedVisits'] == 5*circuits
            and meta['uniqueImages'] == 4*circuits+1, 'Invalid completed circuit or sample counts')


def verified_views(evaluation, meta):
    """Rebuild each source label/feature identity and eliminate only the repeated circuit boundary."""
    visits = evaluation.get('visits')
    require(isinstance(visits, list) and len(visits) == meta['orderedVisits'], 'Incomplete ordered station visits')
    unique = {}
    previous = None
    for i, row in enumerate(visits):
        stop = i % 5
        require(isinstance(row, dict) and type(row.get('circuit')) is int and type(row.get('stop')) is int
                and (row['circuit'], row['stop'], row.get('station'), row.get('role')) ==
                (1+i//5, stop, STOPS[stop], ROLES[stop]) and row.get('prediction') in CLASSES,
                'Invalid station label, prediction or visit order')
        evidence, fid = row.get('evidence'), row.get('frameId')
        require(isinstance(evidence, dict) and type(fid) is int and fid > 0 and type(evidence.get('frameId')) is int
                and fid == evidence['frameId'] and evidence.get('captureEpoch') == meta['captureEpoch']
                and digest(evidence.get('rgbSha256')) and type(evidence.get('sourceTimestamp100ns')) is int
                and type(evidence.get('segment')) is int and evidence['segment'] > 0
                and type(evidence.get('videoFrameIndex')) is int and evidence['videoFrameIndex'] >= 0,
                'Invalid source frame, capture epoch or frozen RGB evidence')
        if i and stop == 0:
            require(evidence == previous and fid in unique and row['prediction'] == unique[fid]['prediction'],
                    'Repeated circuit boundary changed its source or prediction')
        else:
            require(fid not in unique and (previous is None or
                    (previous['frameId'] < fid and previous['sourceTimestamp100ns'] < evidence['sourceTimestamp100ns']
                     and (previous['segment'], previous['videoFrameIndex']) < (evidence['segment'], evidence['videoFrameIndex']))),
                    'Station source frames or their recording indices were duplicated or reordered')
            unique[fid] = row
        previous = evidence
    rows = list(unique.values())
    require(len(rows) == meta['uniqueImages'] and [rows[0]['evidence']['sourceTimestamp100ns'],
            rows[-1]['evidence']['sourceTimestamp100ns']] == meta['sourceInterval100ns'], 'Capture window mismatch')
    images = hashlib.sha256()
    for row in rows:
        images.update(json.dumps(row['evidence'], sort_keys=True).encode())
    require(images.hexdigest() == meta['evidenceSha256'], 'Frozen evidence digest mismatch')

    # Recalculate the producer's metrics from the native labels and exact predictions.
    majority = evaluation['unique']['majority']
    require(majority in CLASSES, 'Invalid training majority class')
    for saved, expected in [(evaluation['unique'], metrics(rows, majority)),
                            (evaluation['allVisits'], metrics(visits, majority)),
                            (evaluation['perApproach'], {r:metrics([v for v in visits if v['role'] == r], majority)
                                                        for r in ROLES})]:
        require(json.dumps(saved, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True),
                'Saved confusion, sample support or accuracy differs from recomputed metrics')
    return rows


def qualify(paired, incumbent, challenger):
    """Recommend only an observational change on this route, using per-class unique-frame recall."""
    require(digest(incumbent) and digest(challenger) and incumbent != challenger,
            'Supply two distinct explicit SHA-256 digests')
    require(isinstance(paired, dict) and paired.get('format') == FORMAT, 'Unsupported landmark evaluation format')
    evaluations = paired.get('evaluations')
    require(isinstance(evaluations, list) and len(evaluations) == 2 and all(isinstance(e, dict) for e in evaluations),
            'Exactly two frozen evaluations are required')
    heads = {e.get('checkpointId'): e for e in evaluations}
    require(set(heads) == {incumbent, challenger}, 'Checkpoint IDs differ from the requested SHA-256 digests')
    old, new = heads[incumbent], heads[challenger]
    run = old.get('run')
    verify_run(run)
    verify_run(new.get('run'))
    require(run == new['run'], 'Incumbent and challenger have different frozen run provenance')
    old_rows, new_rows = verified_views(old, run), verified_views(new, run)
    require(all(a['station'] == b['station'] and a['evidence'] == b['evidence']
                for a, b in zip(old_rows, new_rows)), 'The paired evaluations use different native source samples')
    failures, stations = [], {}
    for i, station in enumerate(CLASSES):
        base, trial = old['unique']['confusion'][i], new['unique']['confusion'][i]
        n = sum(base)
        require(sum(trial) == n and n > 0, 'Station support differs')
        stations[station] = dict(uniqueSamples=n, incumbentCorrect=base[i], challengerCorrect=trial[i],
                                 incumbentRecall=base[i]/n, challengerRecall=trial[i]/n)
        if n < REQUIRED_PER_STATION:
            failures.append(f'{station} has {n} unique samples and needs at least {REQUIRED_PER_STATION}.')
        if trial[i] < base[i]:
            failures.append(f'{station} recall regressed from {base[i]}/{n} to {trial[i]}/{n}.')
    delta = new['unique']['correct'] - old['unique']['correct']
    if delta <= 0:
        failures.append('The challenger did not improve total correct unique-frame predictions.')
    return dict(format='bettergi-landmark-qualification-v1', status='compared', route='mondstadt-street-patrol-v1',
                scope='Station observer on this route', recommendation='retain-incumbent' if failures else 'use-challenger-as-observer',
                failedChecks=failures, incumbentSha256=incumbent, challengerSha256=challenger, run=run,
                minimumUniquePerStation=REQUIRED_PER_STATION, uniqueSamples=len(old_rows), incumbentCorrect=old['unique']['correct'],
                challengerCorrect=new['unique']['correct'], additionalCorrect=delta, stations=stations)


def main(argv=None):
    """Write a fresh human-readable result for valid comparisons and invalid evaluation evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--incumbent-sha', required=True)
    parser.add_argument('--challenger-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    source_hash = None
    try:
        raw = args.evaluation.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()
        evidence = qualify(json.loads(raw), args.incumbent_sha, args.challenger_sha)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        evidence = dict(format='bettergi-landmark-qualification-v1', status='invalid-evidence',
                        recommendation='retain-incumbent', failedChecks=[str(exc)], incumbentSha256=args.incumbent_sha,
                        challengerSha256=args.challenger_sha)
    evidence.update(evaluation=str(args.evaluation.resolve()), evaluationSha256=source_hash)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(evidence, out, indent=2, allow_nan=False)
        out.write('\n')
    print(f"{evidence['recommendation']} ({evidence['status']}) — {args.output}")
    return 0 if evidence['status'] == 'compared' else 2


if __name__ == '__main__':
    sys.exit(main())
