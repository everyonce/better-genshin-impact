"""Aggregate saved BetterGI trials and explicit human outcomes; never run a model or game."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys


def number(value):
    """Reject booleans and nonfinite JSON numbers instead of inventing measurements."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    """Summarize available samples using linear-interpolated percentiles, including coverage."""
    values = sorted(value for value in values if number(value) and value >= 0)
    if not values:
        return {'n': 0, 'mean': None, 'p50': None, 'p95': None, 'max': None}
    def percentile(q):
        position = (len(values) - 1) * q
        lower = math.floor(position)
        return values[lower] + (values[math.ceil(position)] - values[lower]) * (position - lower)
    return {'n': len(values), 'mean': statistics.fmean(values), 'p50': percentile(.5),
            'p95': percentile(.95), 'max': values[-1]}


def rate(values):
    """Missing labels stay outside the denominator and retain an explicit zero count."""
    known = [value for value in values if type(value) is bool]
    return {'known': len(known), 'true': sum(known),
            'rate': sum(known) / len(known) if known else None}


def read_json(path):
    """Read a complete saved JSON artifact; partial reports are errors, not empty trials."""
    return json.loads(path.read_text(encoding='utf-8-sig'))


def read_lines(path):
    """Read existing recorder sidecars and reject truncated or malformed records."""
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def required_text(item, name):
    """Require explicit identifiers so unrelated task settings cannot merge accidentally."""
    value = item.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def human_outcome(trial):
    """Validate labels without deriving success or progress from actions or inactivity."""
    outcome = trial.get('outcome')
    if outcome is None:
        return {}
    if trial['kind'] != 'live-control' or not isinstance(outcome, dict) or outcome.get('source') != 'human':
        raise ValueError('Gameplay outcomes require kind=live-control and source=human')
    required_text(outcome, 'rater')
    if outcome.get('success') is not None and type(outcome['success']) is not bool:
        raise ValueError('success must be true, false, or null')
    for name in ('elapsedSeconds', 'interventions'):
        value = outcome.get(name)
        if value is not None and (not number(value) or value < 0):
            raise ValueError(f'{name} must be nonnegative or null')
    if outcome.get('interventions') is not None and type(outcome['interventions']) is not int:
        raise ValueError('interventions must be an integer or null')
    progress = outcome.get('progress')
    if progress is not None:
        if not isinstance(progress, dict):
            raise ValueError('progress must be an object or null')
        required_text(progress, 'unit')
        done, total = progress.get('completed'), progress.get('total')
        if not number(done) or not number(total) or not 0 <= done <= total or total <= 0:
            raise ValueError('progress requires 0 <= completed <= total and total > 0')
    return outcome


def retain_native_history_decision(decisions, settlement, acknowledgement, pending):
    """Join bounded interrupted-decision evidence without treating settlement as admission."""
    rows = list(decisions)
    if settlement is None:
        if acknowledgement is not None:
            raise ValueError('nativeHistoryAcknowledgement requires nativeHistorySettlement')
        return rows
    if (not isinstance(settlement, dict)
            or settlement.get('outcome') not in ('accepted_admission', 'known_not_admitted', 'unknown')
            or type(settlement.get('acknowledgementKnown')) is not bool
            or type(settlement.get('completed')) is not bool
            or settlement.get('error') is not None and type(settlement['error']) is not str):
        raise ValueError('Malformed nativeHistorySettlement')
    request_id = settlement.get('requestId')
    if request_id is not None and (type(request_id) is not str or not request_id):
        raise ValueError('Native settlement requestId must be nonempty or null')
    projection = settlement.get('decision')
    if projection is not None and not isinstance(projection, dict):
        raise ValueError('Native decision projection must be an object or null')
    has_projection = projection is not None
    encoded = json.dumps(projection or {}, allow_nan=False, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > 24576:
        raise ValueError('Native decision projection exceeds producer bound')
    projection = json.loads(encoded)
    if set(projection) - {'frameId', 'steps', 'policyWallMs', 'estimatedObservationAgeMs', 'acceptance'}:
        raise ValueError('Native decision projection contains unsupported measurements')
    raw_reply = projection.get('acceptance')
    if raw_reply is not None and (not isinstance(raw_reply, dict)
            or set(raw_reply) - {'type', 'requestId', 'reason', 'receivedAtMs', 'acceptedAtMs'}):
        raise ValueError('Malformed native decision acceptance projection')

    def same(left, right):
        """Keep exact JSON types; Boolean/integer equality must not hide conflicting evidence."""
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)

    known = settlement['acknowledgementKnown']
    outcome = settlement['outcome']
    if known:
        expected = 'accepted' if outcome == 'accepted_admission' else 'rejected'
        if (outcome == 'unknown' or request_id is None or not isinstance(acknowledgement, dict)
                or type(acknowledgement.get('requestId')) is not str
                or acknowledgement['requestId'] != request_id or acknowledgement.get('type') != expected
                or pending is not None):
            raise ValueError('Native acknowledgement does not match settlement outcome/requestId')
        if raw_reply is not None and (raw_reply.get('type') != expected
                or type(raw_reply.get('requestId')) is not str or raw_reply['requestId'] != request_id):
            raise ValueError('Native decision reply differs from explicit acknowledgement')
        projection['acceptance'] = raw_reply if raw_reply is not None else dict(acknowledgement)
    elif outcome == 'known_not_admitted':
        if acknowledgement is not None or pending is not None:
            raise ValueError('Local native rejection cannot carry acknowledgement or unresolved request')
        if raw_reply is None:
            if projection:
                raise ValueError('Local native decision requires an explicit notSubmitted projection')
            return rows  # A failed prediction without a public projection is not a measured decision.
        if raw_reply.get('type') != 'notSubmitted' or raw_reply.get('requestId') not in (None, request_id):
            raise ValueError('Local native rejection requires an explicit notSubmitted projection')
        if request_id is not None and any(row.get('acceptance', {}).get('requestId') == request_id for row in rows):
            raise ValueError('Local native rejection conflicts with an existing request decision')
        # The writer emits this projection only before append. A frame/time match is not identity.
        rows.append(projection)
        return rows
    elif outcome == 'unknown':
        if (acknowledgement is not None or request_id is None or not isinstance(pending, dict)
                or type(pending.get('requestId')) is not str or pending['requestId'] != request_id):
            raise ValueError('Unknown native outcome requires its exact unacknowledgedAction latch')
        for key, value in (('frameId', (pending.get('frame') or {}).get('frameId')),
                           ('steps', pending.get('steps'))):
            if key in projection and value is not None and not same(projection[key], value):
                raise ValueError('Native projection conflicts with unresolved request: ' + key)
            projection.setdefault(key, value)
        projection['acceptance'] = {'type': 'unacknowledged', 'requestId': request_id,
                                    'reason': 'actionAcknowledgementUnavailable'}
        if raw_reply is not None:
            projection['unverifiedAcceptance'] = raw_reply
    else:
        raise ValueError('Accepted native outcome requires an explicit acknowledgement')

    matches = [index for index, row in enumerate(rows)
               if row.get('acceptance', {}).get('requestId') == request_id]
    if len(matches) > 1:
        raise ValueError('Multiple decisions match native settlement requestId')
    if not matches:
        # Segment snapshots retain normal acknowledgements after transferring the decision list.
        if not known or has_projection:
            rows.append(projection)
        return rows
    index = matches[0]
    row = dict(rows[index])
    for key, value in projection.items():
        if key not in ('acceptance', 'unverifiedAcceptance') and key in row and not same(value, row[key]):
            raise ValueError('Conflicting native decision evidence: ' + key)
    existing_reply = row.get('unverifiedAcceptance', row.get('acceptance', {}))
    expected_reply = raw_reply if outcome == 'unknown' else projection['acceptance']
    if expected_reply is not None:
        for key, value in expected_reply.items():
            existing = existing_reply.get(key)
            if key == 'reason' and type(existing) is str:
                existing = existing[:512]  # Exact producer projection truncates only the reason.
            if not same(value, existing):
                raise ValueError('Conflicting native decision acceptance: ' + key)
    for key, value in projection.items():
        row.setdefault(key, value)
    if outcome == 'unknown':
        if raw_reply is None and row.get('acceptance', {}).get('type') != 'unacknowledged':
            row['unverifiedAcceptance'] = row.get('acceptance')
        row['acceptance'] = projection['acceptance']
    rows[index] = row
    return rows


def retain_unacknowledged_action(decisions, pending):
    """Retain a terminal request without inventing its missing acknowledgement or timings."""
    rows = list(decisions)
    if pending is None:
        return rows
    if (not isinstance(pending, dict) or type(pending.get('requestId')) is not str
            or not pending['requestId']):
        raise ValueError('unacknowledgedAction requires a nonempty requestId')
    request_id = pending['requestId']
    matches = [index for index, row in enumerate(rows)
               if row.get('acceptance', {}).get('requestId') == request_id]
    if len(matches) > 1:
        raise ValueError('Multiple decisions match unacknowledgedAction.requestId')
    if matches:
        # A saved raw reply cannot clear the client's unresolved-request latch.
        row = dict(rows[matches[0]])
        if row.get('acceptance', {}).get('type') != 'unacknowledged':
            row['unverifiedAcceptance'] = row.get('acceptance')
    else:
        frame = pending.get('frame') or {}
        row = {'frameId': frame.get('frameId'), 'steps': pending.get('steps')}
    row['acceptance'] = {'type': 'unacknowledged', 'requestId': request_id,
                         'reason': 'actionAcknowledgementUnavailable'}
    if matches:
        rows[matches[0]] = row
    else:
        rows.append(row)
    return rows


def load_trial(trial, base):
    """Read one report/episode, preferring full reports over duplicated recorder events."""
    for name in ('id', 'model', 'configurationId', 'goalId', 'startStateId', 'gpuContext'):
        required_text(trial, name)
    if trial.get('kind') not in ('live-control', 'live-observe', 'offline-replay'):
        raise ValueError('kind must be live-control, live-observe, or offline-replay')
    conditioning = trial.get('conditioning', {})
    if conditioning.get('mode') not in ('none', 'fixed-generic-text', 'trial-text'):
        raise ValueError('Declare conditioning.mode as none, fixed-generic-text, or trial-text')
    if conditioning['mode'] != 'none':
        required_text(conditioning, 'text')
    outcome = human_outcome(trial)
    report_path = (base / trial['report']).resolve() if trial.get('report') else None
    episode = (base / trial['episodeDirectory']).resolve() if trial.get('episodeDirectory') else None
    if report_path is None and episode is None:
        raise ValueError('Each trial needs report or episodeDirectory')
    if episode is not None and not episode.is_dir():
        raise ValueError(f'Episode directory does not exist: {episode}')
    report = read_json(report_path) if report_path else {}
    events = read_lines(episode / 'events.jsonl') if episode else []
    frames = read_lines(episode / 'frames.jsonl') if episode else []
    starts = [event for event in events if event.get('type') == 'episodeStart']
    if len(starts) > 1:
        raise ValueError('One trial may contain only one episode/session')
    start = starts[0] if starts else {}
    if report.get('model', start.get('model', trial['model'])) != trial['model']:
        raise ValueError('Declared model differs from the saved report/episode')
    if report.get('model') and start.get('model') and report['model'] != start['model']:
        raise ValueError('Report and episode contain different models')
    if report.get('hello', {}).get('sessionId') and start.get('sessionId'):
        if report['hello']['sessionId'] != start['sessionId']:
            raise ValueError('Report and episode contain different sessions')
    offline = trial['kind'] == 'offline-replay'
    if offline and ('samples' not in report or report.get('mode') == 'live-bound-game-stream'):
        raise ValueError('offline-replay requires an offline benchmark report with samples')
    if not offline and 'samples' in report:
        raise ValueError('Offline benchmark samples cannot be labeled as live gameplay')
    if trial['kind'] == 'live-control' and report.get('inputRequested', start.get('inputRequested')) is not True:
        raise ValueError('A live-control trial requires logged inputRequested=true')
    if trial['kind'] == 'live-control' and report.get('hello', {}).get('inputEnabled') is False:
        raise ValueError('The report says BetterGI input was disabled')
    proposals = [event for event in events if event.get('type') == 'proposal']
    decisions = report.get('samples' if offline else 'decisions', proposals)
    pending = report.get('unacknowledgedAction')
    settlement = report.get('nativeHistorySettlement')
    acknowledgement = report.get('nativeHistoryAcknowledgement')
    if offline and pending is not None:
        raise ValueError('An offline replay cannot contain an unacknowledged action request')
    if offline and (settlement is not None or acknowledgement is not None):
        raise ValueError('An offline replay cannot contain live native settlement evidence')
    decisions = retain_native_history_decision(decisions, settlement, acknowledgement, pending)
    decisions = retain_unacknowledged_action(decisions, pending)
    receipts = report.get('receipts', [event for event in events if 'appliedSteps' in event and 'requestId' in event])
    observed = {frame['frameId']: frame['capturedAtMs'] for frame in frames}
    observed.update({item['frameId']: item['observedAtMs'] for item in proposals})
    recording = report.get('recording')
    if recording is None and episode and (episode / 'recording.json').is_file():
        recording = read_json(episode / 'recording.json')
    warnings = []
    if pending is not None:
        warnings.append('Unacknowledged action retained; submission and acceptance remain unknown. '
                        'Missing decision measurements remain unavailable.')
    if not decisions:
        warnings.append('No model decisions recorded')
    if not report_path:
        warnings.append('Episode-only data lack parse-valid flags and may lack final server-loss counters')
    for name in ('streamError', 'stopError', 'error'):
        if report.get(name):
            warnings.append(f'{name}: {report[name]}')
    if report.get('serverDroppedReceipts', 0):
        warnings.append('Server dropped execution receipts; execution totals are incomplete')
    if recording and (recording.get('error') or recording.get('complete') is not True):
        warnings.append('Recording incomplete: ' + str(recording.get('error') or 'not finalized'))
    if offline and report.get('status') != 'completed':
        warnings.append('Offline benchmark did not complete')
    if outcome and not trial.get('evidence'):
        warnings.append('Human outcome has no declared review evidence')
    record = {name: trial[name] for name in ('id', 'kind', 'model', 'configurationId', 'goalId', 'startStateId', 'gpuContext')}
    record.update(declaredConditioning=conditioning, outcome=outcome or None, evidence=trial.get('evidence'),
                  actionReview=trial.get('actionReview'), warnings=warnings,
                  report=str(report_path) if report_path else None, episodeDirectory=str(episode) if episode else None,
                  policyMetadata=report.get('policyMetadata', report.get('adapter', start.get('policyMetadata'))),
                  decisionHz=report.get('decisionHz', start.get('decisionHz')),
                  maxObservationAgeMs=report.get('maxObservationAgeMs', start.get('maxObservationAgeMs')),
                  frameHashes=[item.get('sha256') for item in report.get('frames', [])],
                  recording=recording, serverDroppedReceipts=report.get('serverDroppedReceipts'),
                  unacknowledgedAction=pending)
    if settlement is not None:
        record['nativeHistorySettlement'] = settlement
        record['nativeHistoryAcknowledgement'] = acknowledgement
        warnings.append('Native history settlement is retained separately from controller admission; '
                        'neither establishes physical execution or parser validity.')
        if settlement['outcome'] == 'unknown':
            record['nativeHistoryUnverifiedAcceptance'] = (settlement.get('decision') or {}).get('acceptance')
    if report_path:
        record['reportSha256'] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    return record, {'decisions': decisions, 'receipts': receipts, 'observed': observed, 'outcome': outcome,
                    'maxAgeMs': record['maxObservationAgeMs']}


def summarize(facts):
    """Pool measured samples, but weight outcome/progress means per human-labeled trial."""
    decisions = [row for item in facts for row in item['decisions']]
    receipts = [row for item in facts for row in item['receipts']]
    outcomes = [item['outcome'] for item in facts]
    accepted_to_first, capture_to_first, fresh = [], [], []
    accepted_ids = receipt_ids = receipts_with_steps = applied_steps = nonidle_steps = 0
    unacknowledged_ids = unacknowledged_receipt_ids = 0
    receipt_statuses, proposal_statuses, reasons = Counter(), Counter(), Counter()
    for item in facts:
        limit = item.get('maxAgeMs')
        for row in item['decisions']:
            age = row.get('estimatedObservationAgeMs')
            fresh.append(0 <= age < limit if number(age) and number(limit) else None)
        accepted = {row.get('acceptance', {}).get('requestId') for row in item['decisions']
                    if row.get('acceptance', {}).get('type') == 'accepted'} - {None}
        ended = {row.get('requestId') for row in item['receipts']} - {None}
        accepted_ids += len(accepted)
        receipt_ids += len(accepted & ended)
        unresolved = {row.get('acceptance', {}).get('requestId') for row in item['decisions']
                      if row.get('acceptance', {}).get('type') == 'unacknowledged'} - {None}
        unacknowledged_ids += len(unresolved)
        unacknowledged_receipt_ids += len(unresolved & ended)
        for receipt in item['receipts']:
            receipt_statuses[receipt.get('status', 'unknown')] += 1
            steps = receipt.get('appliedSteps', [])
            if steps:
                receipts_with_steps += 1
                first = steps[0].get('startedAtMs')
                accepted_at = receipt.get('acceptedAtMs')
                captured_at = item['observed'].get(receipt.get('frameId'))
                if number(first) and number(accepted_at):
                    accepted_to_first.append(first - accepted_at)
                if number(first) and number(captured_at):
                    capture_to_first.append(first - captured_at)
            applied_steps += len(steps)
            nonidle_steps += sum(bool(step.get('keys') or step.get('mouseDx') or step.get('mouseDy')) for step in steps)
    no_ops = []
    for row in decisions:
        acceptance = row.get('acceptance', {})
        proposal_statuses[acceptance.get('type', 'unrecorded')] += 1
        if acceptance.get('reason'):
            reasons[acceptance.get('type', 'unrecorded') + ':' + acceptance['reason']] += 1
        steps = row.get('steps')
        no_ops.append(all(not step.get('keys') and not step.get('mouseDx') and not step.get('mouseDy')
                          for step in steps) if steps else None)
    progress = defaultdict(list)
    progress_per_second = defaultdict(list)
    for outcome in outcomes:
        if outcome.get('progress'):
            item = outcome['progress']
            progress[item['unit']].append(item['completed'] / item['total'])
            elapsed = outcome.get('elapsedSeconds')
            if number(elapsed) and elapsed > 0:
                progress_per_second[item['unit']].append(item['completed'] / elapsed)
    metrics = {name: distribution(row.get(name) for row in decisions) for name in
               ('policyWallMs', 'fullActionMs', 'estimatedObservationAgeMs', 'observationToActionMs')}
    metrics.update(acceptedToFirstAppliedMs=distribution(accepted_to_first),
                   captureToFirstAppliedMs=distribution(capture_to_first))
    total = len(decisions)
    accepted_count = proposal_statuses.get('accepted', 0)
    rejected_count = proposal_statuses.get('rejected', 0)
    acceptance_known = sum(proposal_statuses.get(name, 0) for name in ('accepted', 'rejected', 'notSubmitted'))
    acknowledged = accepted_count + rejected_count
    return {'trials': len(facts), 'humanOutcomeTrials': sum(bool(item) for item in outcomes),
            'success': rate(item.get('success') for item in outcomes),
            'progressFractionByUnit': {unit: distribution(values) for unit, values in sorted(progress.items())},
            'progressPerSecondByUnit': {unit: distribution(values) for unit, values in sorted(progress_per_second.items())},
            'elapsedSeconds': distribution(item.get('elapsedSeconds') for item in outcomes),
            'successfulTrialSeconds': distribution(item.get('elapsedSeconds') for item in outcomes if item.get('success') is True),
            'interventions': distribution(item.get('interventions') for item in outcomes),
            'decisions': total, 'parseValid': rate(row.get('parseValid') for row in decisions),
            'protocolCompatible': rate(row.get('protocolCompatible') for row in decisions),
            'controlCadenceMet': rate(row.get('controlCadenceMet') for row in decisions),
            'withinDeclaredFreshnessLimit': rate(fresh),
            'noOpProposals': rate(no_ops), 'proposalStatusCounts': dict(proposal_statuses),
            'proposalReasonCounts': dict(reasons),
            'decisionsWithAcceptance': acceptance_known,
            'acceptedPerDecision': accepted_count / total if total and acceptance_known == total else None,
            'serverRejectedPerSubmitted': rejected_count / acknowledged
                if acknowledged and acceptance_known == total else None,
            'serverRejectedPerAcknowledgedRequest': rejected_count / acknowledged if acknowledged else None,
            'receiptStatusCounts': dict(receipt_statuses), 'receipts': len(receipts),
            'receiptsWithAppliedSteps': receipts_with_steps, 'appliedSteps': applied_steps,
            'nonIdleAppliedSteps': nonidle_steps,
            'acceptedRequestReceiptCoverage': {'acceptedWithId': accepted_ids, 'matchedReceipts': receipt_ids,
                                              'rate': receipt_ids / accepted_ids if accepted_ids else None},
            'unacknowledgedRequestReceiptCoverage': {
                'unacknowledgedWithId': unacknowledged_ids, 'matchedReceipts': unacknowledged_receipt_ids,
                'rate': unacknowledged_receipt_ids / unacknowledged_ids if unacknowledged_ids else None},
            'timingMs': metrics}


def evaluate(manifest, base):
    """Keep live/observation/replay, GPU context, task, start state and model settings distinct."""
    if manifest.get('version') != 1 or not isinstance(manifest.get('trials'), list):
        raise ValueError('Expected a version=1 manifest containing trials')
    rows, groups, ids = [], defaultdict(list), set()
    for trial in manifest['trials']:
        record, facts = load_trial(trial, base)
        if record['id'] in ids:
            raise ValueError('Trial IDs must be unique')
        ids.add(record['id'])
        record['metrics'] = summarize([facts])
        rows.append(record)
        key = tuple(record[name] for name in ('kind', 'gpuContext', 'goalId', 'startStateId', 'model', 'configurationId'))
        key += (json.dumps(record['declaredConditioning'], sort_keys=True),)
        groups[key].append((record, facts))
    aggregate = []
    for members in groups.values():
        first = members[0][0]
        group = {name: first[name] for name in ('kind', 'gpuContext', 'goalId', 'startStateId', 'model',
                                               'configurationId', 'declaredConditioning')}
        group.update(trialIds=[item[0]['id'] for item in members],
                     metrics=summarize([item[1] for item in members]))
        aggregate.append(group)
    return {'version': 1, 'scope': 'Saved measurements and explicit human labels; no inferred gameplay competence.',
            'percentiles': 'Linear interpolation; group timing pools decisions, outcomes weight trials equally.',
            'trials': rows, 'groups': aggregate}


def main():
    """Resolve artifact references relative to the manifest, and write one offline JSON summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(read_json(args.manifest), args.manifest.resolve().parent)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(str(args.output.resolve()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
