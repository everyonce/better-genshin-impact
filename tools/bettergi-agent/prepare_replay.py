"""Prepare auditable P2P history comparisons; never run inference or export training data.

Example (use one CLOSED segment, not its resident summary):
  python prepare_replay.py --report SEGMENT.json --recording-dir RECORDING --output PLAN.json

All labels are system/model provenance and trainingEligible is always false.
The label clock is immutable first acquisition, NOT game render/input time.
"""
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


CLOCK = 'server-monotonic immutable sourceFrame.acquiredAtMs; not game-render time'
COMPARISON_MODES = ('three-arm', 'same-frames-only')
LIMITATIONS = [
    'Candidate preparation only: no pixels decoded, inference, expert labels, or training.',
    'Video is H.264 CRF20/yuv420p; decoded pixels cannot establish live RGB tensor parity.',
    'Video PTS/index identifies an encoded image, not elapsed capture time.',
    'Accepted actions are decoded-proposal proxies; original sampled token IDs are unavailable.',
    'Applied receipts establish backend-dispatch intent, not OS/game acknowledgement or physical key state.',
    'Acquisition-time action association is an explicit comparison convention, not verified behavioral alignment.',
    'When selected, nominal 20Hz selection retains real timestamps/jitter; absent frames/actions are never synthesized.',
    'Equal history-frame counts cover different wall-time spans; all arms start with bounded cold histories.',
    'Automatic probes are availability candidates biased toward complete low-jitter windows; review scenes before evaluation.',
    'No Genshin training coverage or task success is inferred from these model-generated trajectories.',
]


class EvidenceError(ValueError):
    """An evidence contradiction or missing contract prevents trustworthy preparation."""


def require(condition, reason):
    """Fail closed with a stable, auditable reason."""
    if not condition:
        raise EvidenceError(reason)


def number(value, name):
    """Reject booleans, missing clocks, NaN, and infinities."""
    require(type(value) in (int, float) and math.isfinite(value), 'invalid_number:' + name)
    return value


def integer(value, name):
    """Require an actual JSON integer for IDs, counters, and mouse deltas."""
    require(type(value) is int and value >= 0, 'invalid_integer:' + name)
    return value


def action(step):
    """Preserve the complete controller key/button state; do not invent token IDs."""
    require(isinstance(step, dict), 'invalid_action')
    keys = step.get('keys')
    require(isinstance(keys, list) and all(isinstance(k, str) and k for k in keys)
            and len(set(keys)) == len(keys), 'invalid_keys')
    require(type(step.get('mouseDx')) is int and type(step.get('mouseDy')) is int, 'invalid_mouse_delta')
    return {'heldKeys': sorted(keys), 'mouseDx': step['mouseDx'], 'mouseDy': step['mouseDy']}


def goal_identity(decision):
    """Bind a decision to its exact policy goal and resident-control epoch."""
    require(all(k in decision for k in ('controlEpoch', 'policyGoalVersion', 'appliedGoalRequestId', 'goalIntent')),
            'missing_goal_identity')
    return tuple(decision[k] for k in ('controlEpoch', 'policyGoalVersion', 'appliedGoalRequestId', 'goalIntent'))


def frame_clock(frame):
    """Validate the r14 immutable-source contract without treating reported QPC as render truth."""
    source = frame.get('sourceFrame')
    require(isinstance(source, dict) and frame.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc',
            'unknown_source_clock')
    require(isinstance(source.get('captureEpoch'), str) and source['captureEpoch'], 'missing_capture_epoch')
    integer(source.get('timestamp100ns'), 'timestamp100ns')
    acquired = number(source.get('acquiredAtMs'), 'acquiredAtMs')
    reported = number(source.get('capturedAtMs'), 'source.capturedAtMs')
    freshness = number(source.get('freshnessAtMs'), 'freshnessAtMs')
    expected = 'reported_compositor_qpc' if reported <= acquired else 'first_acquisition_qpc'
    require(freshness == min(acquired, reported) and source.get('freshnessClockKind') == expected,
            'contradictory_source_clock')
    require(acquired <= number(frame.get('serverNowMs'), 'serverNowMs'), 'acquisition_after_response')
    number(frame.get('capturedAtMs'), 'host.capturedAtMs')
    number(frame.get('clientReceivedNs'), 'clientReceivedNs')
    return acquired, (source['captureEpoch'], source['timestamp100ns'])


class ReceiptTimeline:
    """Reconstruct backend-dispatched complete states; replacement does not release keys."""
    def __init__(self, receipts):
        self.events = []
        for receipt in receipts:
            rid = receipt['requestId']
            accepted = number(receipt.get('acceptedAtMs'), 'acceptedAtMs')
            ended = number(receipt.get('endedAtMs'), 'endedAtMs')
            require(accepted >= 0 and ended >= 0, 'negative_action_clock')
            require(accepted <= ended, 'receipt_end_before_acceptance')
            require(receipt.get('status') in ('replaced', 'completed', 'cancelled'), 'unknown_receipt_status')
            require(receipt['status'] != 'completed' or bool(receipt['appliedSteps']), 'completed_without_applied_step')
            previous = accepted
            for index, step in enumerate(receipt['appliedSteps']):
                started = number(step.get('startedAtMs'), 'startedAtMs')
                require(started >= 0, 'negative_action_clock')
                require(step.get('index') == index and previous <= started <= ended, 'invalid_applied_step_time')
                previous = started
                self.events.append({'timeMs': started, 'eventId': f'{rid}:step:{index}', 'kind': 'apply',
                                    'requestId': rid, 'stepIndex': index, **action(step)})
            if receipt['status'] != 'replaced':
                self.events.append({'timeMs': ended, 'eventId': f'{rid}:release', 'kind': 'release',
                                    'requestId': rid, 'reason': receipt.get('reason'),
                                    'heldKeys': [], 'mouseDx': 0, 'mouseDy': 0})
        self.events.sort(key=lambda e: e['timeMs'])
        # Receipt clocks do not establish ordering of distinct equal-time state mutations.
        require(all(a['timeMs'] < b['timeMs'] for a, b in zip(self.events, self.events[1:])),
                'ambiguous_equal_time_input_events')
        self.times = [e['timeMs'] for e in self.events]

    def label(self, start, end):
        """Associate mouse once with (start,end], and complete held state with end."""
        require(start < end, 'nonmonotonic_label_interval')
        left = bisect_right(self.times, start)
        right = bisect_right(self.times, end)
        require(left > 0, 'unknown_initial_held_state')
        selected = self.events[left:right]
        state = self.events[right - 1]
        mouse = [dict(e) for e in selected if e['kind'] == 'apply' and (e['mouseDx'] or e['mouseDy'])]
        return {'provenance': 'system/backend-dispatch-intent', 'trainingEligible': False,
                'labelClock': CLOCK, 'interval': {'startExclusiveMs': start, 'endInclusiveMs': end},
                'initialHeldKeys': self.events[left-1]['heldKeys'],
                'initialStateEvidenceEventId': self.events[left-1]['eventId'],
                'heldKeys': state['heldKeys'], 'stateEvidenceEventId': state['eventId'],
                'mouseDx': sum(e['mouseDx'] for e in mouse), 'mouseDy': sum(e['mouseDy'] for e in mouse),
                'mouseEvents': mouse, 'stateTransitions': [dict(e) for e in selected]}


def _complete(report, recording, observations, frames, events):
    """Require a closed, loss-free r14 segment and its matching recorder sidecars."""
    require(report.get('model') == 'open-p2p', 'requires_open_p2p_segment_report')
    require(report.get('inputRequested') is True, 'requires_recorded_system_input')
    require(not report.get('streamError') and not report.get('unacknowledgedAction'), 'unknown_action_or_stream_outcome')
    for summary in (report.get('recording', {}), recording):
        require(summary.get('complete') is True and summary.get('closed') is True and not summary.get('error'),
                'recording_not_complete')
        for key in ('droppedFrames', 'droppedEvents', 'abandonedFrames', 'droppedObservations'):
            require(summary.get(key) == 0, 'recording_loss:' + key)
        require(summary.get('encodedFrames') == len(frames)
                and summary.get('recordedObservations') == len(observations), 'recording_count_mismatch')
    require(report.get('serverDroppedReceipts') == 0, 'server_receipts_missing')
    require(len(observations) == report.get('framesReceived') and observations, 'observation_count_mismatch')
    starts = [e for e in events if e.get('type') == 'episodeStart']
    ends = [e for e in events if e.get('type') == 'episodeEnd']
    hello = report.get('hello', {})
    require(len(starts) == 1 and len(ends) == 1, 'episode_boundaries_missing')
    require(starts[0].get('sessionId') == hello.get('sessionId') and hello.get('sessionId'), 'session_identity_mismatch')
    require(isinstance(hello.get('ownerEpoch'), str) and hello['ownerEpoch'], 'missing_owner_epoch')
    require(starts[0].get('observationProfile') == report.get('observationProfile') == hello.get('observationProfile'),
            'profile_mismatch')
    require(hello.get('clockFrequency') == 1000 and starts[0].get('clockFrequency') == 1000, 'unsupported_session_clock')
    require(ends[0].get('acceptedInputActions') == report.get('acceptedInputActions'), 'episode_action_count_mismatch')
    for report_key, event_types in (('controlTransitions', ('controlTransition',)),
                                    ('goalChanges', ('policyGoalChange',)),
                                    ('navigationIdleRecoveryEvents', ('navigationIdleRecovery', 'navigationIdleRearmed'))):
        require(report.get(report_key, []) == [e for e in events if e.get('type') in event_types],
                'missing_or_contradictory_boundary_events:' + report_key)


def _frames(observations, video_frames, profile, fps):
    """Join actual encoded images and reject contradictory or nonmonotonic source metadata."""
    require(fps > 0, 'invalid_capture_fps')
    by_id, seen_source = {}, {}
    previous_time, previous_id, previous_client = -math.inf, -1, -math.inf
    for row in observations:
        fid = integer(row.get('frameId'), 'frameId')
        t, source_id = frame_clock(row)
        client = row['clientReceivedNs']
        require(fid > previous_id and t >= previous_time and client > previous_client, 'nonmonotonic_observations')
        if source_id in seen_source:
            require(seen_source[source_id] == t, 'source_identity_changed_acquisition')
        else:
            require(t > previous_time, 'ambiguous_acquisition_time')
            seen_source[source_id] = t
        require(row.get('observationProfile') == profile and row.get('pixelFormat') == 'rgb24', 'frame_profile_mismatch')
        for key in ('width', 'height', 'sourceWidth', 'sourceHeight'):
            require(integer(row.get(key), key) > 0, 'invalid_frame_dimensions')
        require(row.get('droppedReceipts') == 0, 'frame_reports_dropped_receipts')
        require(row.get('videoQueueAccepted') is True, 'video_frame_not_admitted')
        by_id[fid] = dict(row, labelTimeMs=t, sourceIdentity=source_id)
        previous_time, previous_id, previous_client = t, fid, client
    require(len(video_frames) == len(by_id), 'missing_video_join')
    seen_video, previous_video_id = set(), -1
    for index, row in enumerate(video_frames):
        fid = row.get('frameId')
        require(fid in by_id and fid not in seen_video, 'ambiguous_video_join')
        require(fid > previous_video_id, 'nonmonotonic_video_join')
        require(integer(row.get('videoFrameIndex'), 'videoFrameIndex') == index, 'noncontiguous_video_index')
        require(abs(number(row.get('videoPtsSeconds'), 'videoPtsSeconds') - index/fps) < 1e-6, 'video_pts_mismatch')
        observation = by_id[fid]
        for key in ('capturedAtMs', 'sourceFrame', 'width', 'height', 'sourceWidth', 'sourceHeight', 'pixelFormat', 'observationProfile',
                    'frameWorldReadiness', 'worldReadiness', 'clientReceivedNs'):
            require(row.get(key) == observation.get(key), 'video_metadata_mismatch:' + key)
        observation.update(videoFrameIndex=index, videoPtsSeconds=row['videoPtsSeconds'])
        seen_video.add(fid)
        previous_video_id = fid
    return by_id


def _decisions(report, events, by_id):
    """Join every accepted action to one terminal receipt and recorder proposal."""
    decisions = report.get('decisions', [])
    require(decisions, 'no_policy_decisions')
    proposals = [e for e in events if e.get('type') == 'proposal']
    require(len(proposals) == len(decisions), 'missing_recorded_proposals')
    accepted, previous_id = {}, -1
    for decision, recorded in zip(decisions, proposals):
        fid = decision.get('frameId')
        require(fid in by_id and fid > previous_id, 'missing_or_nonmonotonic_decision_frame')
        previous_id = fid
        goal_identity(decision)
        integer(decision.get('episodeStep'), 'episodeStep')
        for key in ('frameId', 'steps', 'rawPolicySteps', 'acceptance', 'controlEpoch', 'policyGoalVersion',
                    'appliedGoalRequestId', 'goalIntent'):
            require(decision.get(key) == recorded.get(key), 'proposal_report_mismatch:' + key)
        require(recorded.get('observedAtMs') == by_id[fid]['capturedAtMs'], 'proposal_host_identity_mismatch')
        acknowledgement = decision.get('acceptance', {})
        is_accepted = acknowledgement.get('type') == 'accepted'
        require(decision.get('historyCommitted') is is_accepted, 'unknown_history_commit')
        if is_accepted:
            rid = acknowledgement.get('requestId')
            require(isinstance(rid, str) and rid and rid not in accepted, 'duplicate_or_missing_request_id')
            require(decision.get('parseValid') is True and len(decision.get('steps', [])) == 1
                    and len(decision.get('rawPolicySteps', [])) == 1, 'unsupported_proposal_shape')
            require(action(decision['steps'][0]) == action(decision['rawPolicySteps'][0]), 'resampled_action_changed')
            accepted[rid] = decision
    receipts = report.get('receipts', [])
    recorded_receipts = [e for e in events if 'type' not in e and 'requestId' in e]
    require(len(receipts) == len(accepted) == report.get('acceptedInputActions'), 'missing_terminal_receipts')
    require(len(recorded_receipts) == len(receipts), 'missing_recorded_receipts')
    recorded_by_id = {r['requestId']: r for r in recorded_receipts}
    require(len(recorded_by_id) == len(receipts), 'duplicate_recorded_receipt')
    seen = set()
    for receipt in receipts:
        rid = receipt.get('requestId')
        require(rid in accepted and rid not in seen, 'orphan_or_duplicate_receipt')
        require(receipt == recorded_by_id.get(rid), 'receipt_report_mismatch')
        seen.add(rid)
        decision = accepted[rid]
        require(receipt.get('frameId') == decision['frameId'] and receipt.get('modelId') == 'open-p2p', 'receipt_identity_mismatch')
        require(receipt.get('acceptedAtMs') == decision['acceptance'].get('acceptedAtMs'), 'receipt_acceptance_mismatch')
        require(number(receipt.get('acceptedAtMs'), 'acceptedAtMs') >= by_id[decision['frameId']]['serverNowMs'],
                'receipt_before_observation_response')
        require(isinstance(receipt.get('appliedSteps'), list) and len(receipt['appliedSteps']) <= 1, 'unsupported_receipt_shape')
        if receipt['appliedSteps']:
            require(action(receipt['appliedSteps'][0]) == action(decision['steps'][0]), 'receipt_action_mismatch')
    ordered = sorted(receipts, key=lambda r: number(r.get('acceptedAtMs'), 'acceptedAtMs'))
    for previous, current in zip(ordered, ordered[1:]):
        require(previous['acceptedAtMs'] < current['acceptedAtMs']
                and number(previous.get('endedAtMs'), 'endedAtMs') <= current['acceptedAtMs'],
                'ambiguous_overlapping_action_owners')
        require(previous['status'] != 'replaced' or previous['endedAtMs'] == current['acceptedAtMs'],
                'replacement_successor_clock_mismatch')
    require(not ordered or ordered[-1]['status'] != 'replaced', 'missing_replacement_successor')
    return decisions, accepted, receipts


def _boundaries(decisions, receipts, events, by_id):
    """Represent resets/holds conservatively; client-clock events use a bracketing interval."""
    boundaries = []
    def add(start, end, reason):
        boundaries.append({'startMs': start, 'endMs': end, 'reason': reason})
    for previous, current in zip(decisions, decisions[1:]):
        start, end = by_id[previous['frameId']]['labelTimeMs'], by_id[current['frameId']]['labelTimeMs']
        expected = previous['episodeStep'] + int(previous['historyCommitted'])
        if current['episodeStep'] != expected:
            add(start, end, 'policy_history_reset_or_unexplained_step')
        if goal_identity(previous) != goal_identity(current):
            add(start, end, 'goal_or_control_epoch_change')
    for receipt in receipts:
        if not receipt['appliedSteps']:
            add(by_id[receipt['frameId']]['labelTimeMs'], receipt['endedAtMs'], 'accepted_but_unapplied_history')
    rows = list(by_id.values())
    clients = [f['clientReceivedNs'] for f in rows]
    harmless = {'episodeStart', 'episodeEnd', 'proposal', 'navigationProgress', 'captureQualitySummary'}
    for event in events:
        kind = event.get('type')
        if kind in harmless or (kind is None and 'requestId' in event):
            continue
        if kind == 'controlTransition' and event.get('state') == 'running':
            continue
        if 'clientTimeNs' in event:
            client = number(event['clientTimeNs'], 'boundary.clientTimeNs')
            index = bisect_right(clients, client)
            if index == 0:
                add(-math.inf, rows[0]['labelTimeMs'], 'initial_control_boundary')
            elif index == len(rows):
                add(rows[-1]['labelTimeMs'], math.inf, 'terminal_control_boundary')
            else:
                add(rows[index-1]['labelTimeMs'], rows[index]['labelTimeMs'], kind)
        elif type(event.get('releasedAtMs')) in (int, float):
            at = number(event['releasedAtMs'], 'releasedAtMs')
            add(at, at, kind)
        else:
            # Do not guess at goal/reset timing from event order or unrelated clocks.
            raise EvidenceError('undatable_control_or_unknown_event:' + str(kind))
    return boundaries


def _reference(frame, target=None):
    """Keep every image address, source identity, real clock, and optional selection jitter."""
    result = {k: frame[k] for k in ('frameId', 'videoFrameIndex', 'videoPtsSeconds', 'width', 'height', 'sourceWidth', 'sourceHeight',
                                   'observationProfile', 'capturedAtMs', 'sourceFrame', 'sourceIdentity', 'labelTimeMs')}
    result['labelClock'] = CLOCK
    if target is not None:
        result.update(nominalTargetMs=target, selectionJitterMs=frame['labelTimeMs']-target)
    return result


def _goal_provenance(report, decision, anchor_client_ns):
    """Resolve the exact applied goal, never borrowing the startup embedding for a later version."""
    initial = report.get('initialGoalState')
    require(isinstance(initial, dict) and 'goalMetadata' in initial, 'missing_initial_goal_provenance')
    version, request = decision['policyGoalVersion'], decision['appliedGoalRequestId']
    if (version, request) == (initial.get('policyGoalVersion'), initial.get('appliedGoalRequestId')):
        require(decision['goalIntent'] == initial.get('goalIntent'), 'initial_goal_intent_mismatch')
        return {'source': 'initialGoalState', 'goalMetadata': initial['goalMetadata'],
                'initialGoalState': initial, 'appliedEvent': None}
    matches = [event for event in report.get('goalChanges', [])
               if event.get('policyGoalVersion') == version and event.get('appliedGoalRequestId') == request
               and event.get('status') == 'applied' and not event.get('error')]
    require(len(matches) == 1 and isinstance(request, str) and request, 'unresolved_applied_goal_provenance')
    event = matches[0]
    require(event.get('requestId') == request and event.get('goalIntent') == decision['goalIntent']
            and 'goalMetadata' in event, 'applied_goal_identity_mismatch')
    require(number(event.get('clientTimeNs'), 'goal.clientTimeNs') <= anchor_client_ns, 'goal_applied_after_history_anchor')
    return {'source': 'policyGoalChange', 'goalMetadata': event['goalMetadata'],
            'initialGoalState': initial, 'appliedEvent': event}


def _check_window(rows, probe, anchors, selected, boundaries, max_gap):
    """Reject discontinuities anywhere between the earliest anchor and excluded target."""
    start, end = min(f['labelTimeMs'] for f in anchors), probe['labelTimeMs']
    for boundary in boundaries:
        require(not (boundary['startMs'] <= end and boundary['endMs'] >= start),
                'boundary:' + boundary['reason'])
    covered = [f for f in rows if start <= f['labelTimeMs'] <= end]
    require(all(b['labelTimeMs']-a['labelTimeMs'] <= max_gap for a, b in zip(covered, covered[1:])), 'source_observation_gap')
    epoch = probe['frameWorldReadiness'].get('epoch')
    capture_epoch = probe['sourceFrame']['captureEpoch']
    for f in covered:
        exact, current = f.get('frameWorldReadiness', {}), f.get('worldReadiness', {})
        require(f.get('inputAvailable') is True and f.get('frameQuality') == 'usable'
                and exact.get('ready') is True and current.get('ready') is True
                and exact.get('epoch') == current.get('epoch') == epoch, 'world_or_capture_not_ready')
        require(f['sourceFrame']['captureEpoch'] == capture_epoch, 'capture_epoch_boundary')
        require(all(f[k] == probe[k] for k in ('width', 'height', 'sourceWidth', 'sourceHeight')), 'capture_geometry_boundary')
    for history in selected:
        identities = [f['sourceIdentity'] for f in history] + [probe['sourceIdentity']]
        require(len(identities) == len(set(identities)), 'duplicate_real_frame_or_probe_in_history')
        require(all(f['labelTimeMs'] < end for f in history), 'probe_not_strictly_after_history')


def prepare(report, observations, video_frames, events, recording, *, history_frames=40,
            nominal_hz=20.0, max_jitter_ms=20.0, max_source_gap_ms=100.0,
            max_windows=6, probe_spacing_ms=5000.0, probe_frame_ids=None, comparison_mode='three-arm'):
    """Compare label histories, optionally adding a nominal-rate arm; never synthesize history."""
    require(comparison_mode in COMPARISON_MODES, 'unknown_comparison_mode')
    include_grid = comparison_mode == 'three-arm'
    require(type(history_frames) is int and 1 <= history_frames <= 200, 'history_frames_out_of_range')
    require(type(max_windows) is int and 1 <= max_windows <= 100, 'max_windows_out_of_range')
    for name, value in [('max_source_gap_ms', max_source_gap_ms), ('probe_spacing_ms', probe_spacing_ms)]:
        require(number(value, name) > 0, 'nonpositive:' + name)
    if include_grid:
        require(number(nominal_hz, 'nominal_hz') == 20.0, 'only_nominal_20hz_supported')
        require(0 < number(max_jitter_ms, 'max_jitter_ms') < 1000/nominal_hz/2, 'overlapping_grid_selection_tolerance')
    _complete(report, recording, observations, video_frames, events)
    by_id = _frames(observations, video_frames, report['observationProfile'], number(report['capturePollHz'], 'capturePollHz'))
    decisions, accepted, receipts = _decisions(report, events, by_id)
    timeline = ReceiptTimeline(receipts)
    boundaries = _boundaries(decisions, receipts, events, by_id)
    rows = list(by_id.values())
    unique = list({f['sourceIdentity']: f for f in reversed(rows)}.values())
    unique.sort(key=lambda f: f['labelTimeMs'])
    times = [f['labelTimeMs'] for f in unique]
    accepted_decisions = [d for d in decisions if d['historyCommitted']]
    windows, rejections = [], Counter()
    requested = set(probe_frame_ids) if probe_frame_ids is not None else None
    if requested is not None:
        require(requested <= {d['frameId'] for d in decisions}, 'requested_probe_has_no_decision')
    attempts = []
    for decision in decisions:
        probe = by_id[decision['frameId']]
        if requested is not None and probe['frameId'] not in requested:
            continue
        if requested is None and windows and probe['labelTimeMs']-windows[-1]['probe']['labelTimeMs'] < probe_spacing_ms:
            continue
        try:
            prior = [d for d in accepted_decisions if by_id[d['frameId']]['labelTimeMs'] < probe['labelTimeMs']]
            require(len(prior) >= history_frames+1, 'insufficient_accepted_history')
            prior = prior[-history_frames-1:]
            accepted_frames = [by_id[d['frameId']] for d in prior]
            grid, targets = [], []
            arm_specs = [('accepted_proxy', accepted_frames, None), ('receipt_same_frames', accepted_frames, None)]
            if include_grid:
                for offset in range(history_frames+1, 0, -1):
                    target = probe['labelTimeMs']-offset*1000/nominal_hz
                    index = bisect_right(times, target)
                    choices = [unique[i] for i in (index-1, index) if 0 <= i < len(unique) and times[i] < probe['labelTimeMs']]
                    require(choices, 'missing_grid_frame')
                    chosen = min(choices, key=lambda f: (abs(f['labelTimeMs']-target), f['labelTimeMs']))
                    require(abs(chosen['labelTimeMs']-target) <= max_jitter_ms, 'grid_jitter_exceeded')
                    grid.append(chosen)
                    targets.append(target)
                arm_specs.append(('receipt_nominal_20hz', grid, targets))
            _check_window(rows, probe, [history[0] for _, history, _ in arm_specs],
                          [history for _, history, _ in arm_specs], boundaries, max_source_gap_ms)
            require(all(goal_identity(d) == goal_identity(decision) for d in prior), 'goal_or_control_epoch_change')
            goal_provenance = _goal_provenance(report, decision,
                                               min(history[0]['clientReceivedNs'] for _, history, _ in arm_specs))
            arms = {}
            for name, history, nominal in arm_specs:
                samples = []
                for index, (previous, current) in enumerate(zip(history, history[1:]), 1):
                    if name == 'accepted_proxy':
                        source = prior[index]
                        label = {'provenance': 'system/model-decoded-proposal-proxy', 'trainingEligible': False,
                                 'labelClock': CLOCK, 'requestId': source['acceptance']['requestId'],
                                 'association': 'proposal tied to observation frame; not held state at that time',
                                 'interval': {'startExclusiveMs': previous['labelTimeMs'], 'endInclusiveMs': current['labelTimeMs']},
                                 **action(source['rawPolicySteps'][0])}
                    else:
                        label = timeline.label(previous['labelTimeMs'], current['labelTimeMs'])
                    samples.append({'frame': _reference(current, nominal[index] if nominal else None), 'label': label})
                mouse_ids = [e['eventId'] for sample in samples for e in sample['label'].get('mouseEvents', [])]
                require(len(mouse_ids) == len(set(mouse_ids)), 'mouse_event_reused')
                arms[name] = {'labelClock': CLOCK, 'anchor': _reference(history[0], nominal[0] if nominal else None),
                              'historyFrames': len(samples), 'wallSpanMs': history[-1]['labelTimeMs']-history[0]['labelTimeMs'],
                              'probeGapMs': probe['labelTimeMs']-history[-1]['labelTimeMs'], 'samples': samples}
            windows.append({'windowId': len(windows)+1, 'trainingEligible': False, 'expertDemonstration': False,
                            'comparisonMode': comparison_mode,
                            'labelClock': CLOCK, 'probe': _reference(probe), 'probeLabel': None,
                            'goalIdentity': {k: decision[k] for k in ('controlEpoch', 'policyGoalVersion', 'appliedGoalRequestId', 'goalIntent')},
                            'goalProvenance': goal_provenance,
                            'arms': arms})
        except EvidenceError as exc:
            rejections[str(exc)] += 1
            attempts.append({'frameId': probe['frameId'], 'reason': str(exc)})
        if len(windows) >= max_windows:
            break
    return {'schemaVersion': 1, 'kind': 'p2p-offline-history-candidates', 'status': 'prepared' if windows else 'no_eligible_windows',
            'comparisonMode': comparison_mode, 'nominalGridRequirementsApplied': include_grid,
            'trainingEligible': False, 'expertDemonstrations': False, 'inferenceExecuted': False,
            'labelClock': CLOCK, 'mouseIntervalConvention': '(previous acquisition, current acquisition]; each event exactly once per arm',
            'sourceClockMeaning': 'first-acquisition association; reported/freshness/host clocks retained; physical-input timing unverified',
            'limitations': LIMITATIONS + ([] if include_grid else [
                'Same-frames-only compares label histories on identical accepted images; it does not test nominal 20Hz timing.']),
            'observationProfile': report['observationProfile'],
            'sessionId': report['hello']['sessionId'], 'ownerEpoch': report['hello'].get('ownerEpoch'),
            'policyMetadata': report.get('policyMetadata'), 'firstInputDeadlinePolicy': report.get('firstInputDeadlinePolicy'),
            'livePolicyUnchanged': True, 'parameters': {'historyFrames': history_frames, 'nominalHz': nominal_hz if include_grid else None,
                'maxJitterMs': max_jitter_ms if include_grid else None, 'maxSourceGapMs': max_source_gap_ms, 'maxWindows': max_windows,
                'probeSpacingMs': probe_spacing_ms, 'requestedProbeFrameIds': sorted(requested) if requested is not None else None},
            'evidenceCounts': {'observations': len(rows), 'distinctSources': len(unique), 'decisions': len(decisions),
                'accepted': len(accepted), 'receipts': len(receipts), 'timelineEvents': len(timeline.events), 'boundaries': len(boundaries)},
            'rejectedCandidateCounts': dict(rejections), 'rejectedCandidates': attempts, 'windows': windows}


def _file_evidence(path):
    """Hash each input, including encoded video, without loading the video into memory."""
    digest = hashlib.sha256()
    before = path.stat()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'input_changed_while_hashing')
    return {'path': str(path.resolve()), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def main(argv=None):
    """Write an atomic candidate/audit JSON; a rejected preparation exits nonzero."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--recording-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--comparison-mode', choices=COMPARISON_MODES, default='three-arm')
    parser.add_argument('--history-frames', type=int, default=40)
    parser.add_argument('--max-windows', type=int, default=6)
    parser.add_argument('--max-jitter-ms', type=float, default=20)
    parser.add_argument('--max-source-gap-ms', type=float, default=100)
    parser.add_argument('--probe-spacing-ms', type=float, default=5000)
    parser.add_argument('--probe-frame-id', type=int, action='append')
    args = parser.parse_args(argv)
    paths = {'report': args.report, **{name: args.recording_dir/name for name in
             ('observations.jsonl', 'frames.jsonl', 'events.jsonl', 'recording.json', 'frames.mp4')}}
    require(args.output.resolve() not in {p.resolve() for p in paths.values()}, 'output_would_overwrite_evidence')
    evidence = {}
    try:
        evidence = {name: _file_evidence(path) for name, path in paths.items()}
        require(evidence['frames.mp4']['bytes'] > 0, 'empty_video')
        payload = {}
        for name, path in paths.items():
            if name.endswith('.jsonl'):
                with path.open(encoding='utf-8') as handle:
                    payload[name] = [json.loads(line) for line in handle if line.strip()]
            elif name != 'frames.mp4':
                payload[name] = json.loads(path.read_text(encoding='utf-8'))
        result = prepare(payload['report'], payload['observations.jsonl'], payload['frames.jsonl'],
                         payload['events.jsonl'], payload['recording.json'], history_frames=args.history_frames,
                         max_windows=args.max_windows, max_jitter_ms=args.max_jitter_ms,
                         max_source_gap_ms=args.max_source_gap_ms, probe_spacing_ms=args.probe_spacing_ms,
                         probe_frame_ids=args.probe_frame_id, comparison_mode=args.comparison_mode)
        require(evidence == {name: _file_evidence(path) for name, path in paths.items()}, 'input_changed_during_preparation')
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        result = {'schemaVersion': 1, 'kind': 'p2p-offline-history-candidates', 'status': 'rejected',
                  'comparisonMode': args.comparison_mode,
                  'trainingEligible': False, 'expertDemonstrations': False, 'inferenceExecuted': False,
                  'labelClock': CLOCK, 'limitations': LIMITATIONS, 'errors': [str(exc)], 'windows': []}
    result['inputEvidence'] = evidence
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent,
                                     prefix=args.output.name + '.', suffix='.tmp', delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(result, handle, indent=2, allow_nan=False)
    try:
        os.replace(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'status': result['status'], 'windows': len(result['windows']), 'output': str(args.output.resolve()),
                      'errors': result.get('errors'), 'rejectedCandidateCounts': result.get('rejectedCandidateCounts')}))
    return 0 if result['status'] == 'prepared' else 2


if __name__ == '__main__':
    raise SystemExit(main())
