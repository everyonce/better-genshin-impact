"""Prepare a separate forward-acquisition history convention, without model execution.

This preserves the original preparer and its two same-frame arms. The added arm
uses the next selected acquisition as the endpoint, approximating only the index
direction of published P2P/Recap labels, not their callback or physical timing.
"""
import argparse
from collections import Counter
import copy
import json
import os
from pathlib import Path
import tempfile

import prepare_replay as base


KIND = 'p2p-offline-forward-history-candidates'
MODE = 'same-frames-forward-acquisition-v1'
ARM = 'receipt_next_acquisition_v1'
ASSOCIATION = 'image-j-to-next-selected-acquisition-v1'
PUBLISHED_REFERENCE = {
    'openP2pRevision': 'a329d98cbe62119679a254d71bea6446773541bc',
    'recapRevision': '70ee48d5f4cd0f6bb19810a55b7ec1c3f36e226f',
    'datasetPairing': 'video_proto_dataset.py:217-240,248-275 pairs image j with annotation j+1',
    'captureAnnotation': 'Recap input_manager/mod.rs:255-315 snapshots held state and drains processed mouse events',
    'callbackTiming': 'Recap record_window.rs:371-382 uses a buffer callback, not immutable first-acquisition QPC',
    'behaviorCloningFilter': 'stage3_finetune.py:1051-1054 filters BC labels to user-action frames',
    'alignmentClaim': 'index-direction approximation only; callback/physical timing is not reproduced',
}
LIMITATIONS = [
    'receipt_same_frames retains its PRECEDING-acquisition convention unchanged.',
    'receipt_next_acquisition_v1 uses held state at the NEXT selected acquisition and mouse events in (j,j+1].',
    'The final history endpoint uses only the probe acquisition clock; no probe pixels, proposal or later input labels.',
    'Selected-image intervals may skip intermediate acquisitions; this is not fixed-rate or exact published training alignment.',
    'Recap snapshots callback-time held state and drains an asynchronous input queue; these receipts use backend-dispatch clocks.',
    'System/model trajectories remain system/model provenance, never human or expert demonstrations; no BC eligibility is asserted.',
    'Acquisition-boundary input ties are rejected because cross-source ordering is not established.',
]


def _forward_arm(window, timeline, receipt_frames):
    """Label identical history images using clock-only endpoints through the probe cutoff."""
    previous = window['arms']['receipt_same_frames']
    history = [sample['frame'] for sample in previous['samples']]
    probe = window['probe']
    endpoints = history[1:] + [probe]
    boundaries = [history[0]['labelTimeMs']] + [frame['labelTimeMs'] for frame in endpoints]
    base.require(not set(boundaries).intersection(timeline.times), 'input_event_on_acquisition_boundary')
    event_by_id = {event['eventId']: event for event in timeline.events}
    samples, mouse_ids = [], []
    for index, (frame, endpoint) in enumerate(zip(history, endpoints)):
        start, end = frame['labelTimeMs'], endpoint['labelTimeMs']
        base.require(start < end <= probe['labelTimeMs'], 'forward_interval_outside_probe_cutoff')
        label = timeline.label(start, end)
        evidence_ids = {label['initialStateEvidenceEventId'], label['stateEvidenceEventId']}
        evidence_ids.update(event['eventId'] for event in label['stateTransitions'])
        for event_id in evidence_ids:
            event = event_by_id[event_id]
            base.require(event['timeMs'] <= end <= probe['labelTimeMs'], 'forward_evidence_after_probe_cutoff')
            base.require(receipt_frames[event['requestId']] < probe['frameId'], 'probe_or_later_action_in_history')
        label.update(association=ASSOCIATION, humanDemonstration=False,
                     endpointRole='probe-clock-only' if index == len(history)-1 else 'next-history-clock-only')
        mouse_ids.extend(event['eventId'] for event in label['mouseEvents'])
        samples.append({'frame': copy.deepcopy(frame), 'label': label})
    base.require(len(mouse_ids) == len(set(mouse_ids)), 'mouse_event_reused')
    return {'labelClock': base.CLOCK, 'association': ASSOCIATION,
            'validationAnchor': copy.deepcopy(previous['anchor']),
            'validationAnchorRole': 'original validation only; forward labels start at their own image acquisition',
            'historyFrames': len(samples),
            'historyImageSpanMs': history[-1]['labelTimeMs']-history[0]['labelTimeMs'],
            'labelSpanMs': probe['labelTimeMs']-history[0]['labelTimeMs'],
            'probeGapMs': probe['labelTimeMs']-history[-1]['labelTimeMs'], 'samples': samples}


def prepare_forward(report, observations, video_frames, events, recording, *, probe_frame_ids,
                    history_frames=40, max_source_gap_ms=100.0, max_windows=6):
    """Reuse every original guard, then add a separately versioned following-interval arm."""
    base.require(isinstance(probe_frame_ids, (list, tuple)) and probe_frame_ids, 'explicit_probe_ids_required')
    base.require(all(type(fid) is int and fid > 0 for fid in probe_frame_ids), 'invalid_probe_id')
    base.require(len(set(probe_frame_ids)) == len(probe_frame_ids), 'duplicate_probe_id')
    # Ask the existing validator for all explicitly selected candidates, so a new
    # boundary rejection cannot hide a later requested valid candidate.
    base.require(type(max_windows) is int and 1 <= max_windows <= 100, 'max_windows_out_of_range')
    base.require(len(probe_frame_ids) <= 100, 'too_many_explicit_probes')
    result = base.prepare(report, observations, video_frames, events, recording,
                          history_frames=history_frames, max_source_gap_ms=max_source_gap_ms,
                          max_windows=len(probe_frame_ids), probe_frame_ids=probe_frame_ids,
                          comparison_mode='same-frames-only')
    result = copy.deepcopy(result)
    timeline = base.ReceiptTimeline(report['receipts'])
    receipt_frames = {receipt['requestId']: receipt['frameId'] for receipt in report['receipts']}
    windows, rejected = [], Counter(result['rejectedCandidateCounts'])
    for window in result['windows']:
        try:
            window['arms'][ARM] = _forward_arm(window, timeline, receipt_frames)
            window.update(windowId=len(windows)+1, comparisonMode=MODE, humanDemonstration=False)
            windows.append(window)
        except base.EvidenceError as exc:
            rejected[str(exc)] += 1
            result['rejectedCandidates'].append({'frameId': window['probe']['frameId'], 'reason': str(exc)})
        if len(windows) == max_windows:
            break
    result.update(kind=KIND, comparisonMode=MODE, windows=windows,
                  status='prepared' if windows else 'no_eligible_windows', humanDemonstrations=False,
                  publishedReference=copy.deepcopy(PUBLISHED_REFERENCE),
                  publishedCallbackAlignmentEstablished=False,
                  mouseIntervalConvention='arm-specific: receipt_same_frames is (previous,current]; '
                      'receipt_next_acquisition_v1 is (current,next], ending at probe acquisition',
                  rejectedCandidateCounts=dict(rejected), limitations=result['limitations']+LIMITATIONS)
    result['parameters'].update(maxWindows=max_windows, associationVersion=ASSOCIATION)
    return result


def main(argv=None):
    """Hash closed evidence and publish a NEW audit plan, refusing any output overwrite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--recording-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probe-frame-id', type=int, action='append', required=True)
    parser.add_argument('--history-frames', type=int, default=40)
    parser.add_argument('--max-windows', type=int, default=6)
    parser.add_argument('--max-source-gap-ms', type=float, default=100)
    args = parser.parse_args(argv)
    paths = {'report': args.report, **{name: args.recording_dir/name for name in
             ('observations.jsonl', 'frames.jsonl', 'events.jsonl', 'recording.json', 'frames.mp4')}}
    base.require(not args.output.exists(), 'output_already_exists')
    base.require(args.output.resolve() not in {path.resolve() for path in paths.values()}, 'output_would_overwrite_evidence')
    evidence = {}
    try:
        evidence = {name: base._file_evidence(path) for name, path in paths.items()}
        base.require(evidence['frames.mp4']['bytes'] > 0, 'empty_video')
        payload = {}
        for name, path in paths.items():
            if name.endswith('.jsonl'):
                with path.open(encoding='utf-8') as handle:
                    payload[name] = [json.loads(line) for line in handle if line.strip()]
            elif name != 'frames.mp4':
                payload[name] = json.loads(path.read_text(encoding='utf-8'))
        result = prepare_forward(payload['report'], payload['observations.jsonl'], payload['frames.jsonl'],
                                 payload['events.jsonl'], payload['recording.json'],
                                 probe_frame_ids=args.probe_frame_id, history_frames=args.history_frames,
                                 max_windows=args.max_windows, max_source_gap_ms=args.max_source_gap_ms)
        base.require(evidence == {name: base._file_evidence(path) for name, path in paths.items()},
                     'input_changed_during_preparation')
    except (base.EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        result = {'schemaVersion': 1, 'kind': KIND, 'comparisonMode': MODE, 'status': 'rejected',
                  'trainingEligible': False, 'expertDemonstrations': False, 'humanDemonstrations': False,
                  'inferenceExecuted': False, 'livePolicyUnchanged': True, 'labelClock': base.CLOCK,
                  'publishedCallbackAlignmentEstablished': False, 'publishedReference': PUBLISHED_REFERENCE,
                  'limitations': base.LIMITATIONS+LIMITATIONS, 'errors': [str(exc)], 'windows': []}
    result['inputEvidence'] = evidence
    result['preparerEvidence'] = {name: base._file_evidence(path) for name, path in
                                  [('forward', Path(__file__)), ('base', Path(base.__file__))]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent,
                                     prefix=args.output.name+'.', suffix='.tmp', delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(result, handle, indent=2, allow_nan=False)
    try:
        # Creating a hard link publishes the complete file atomically and fails
        # if another writer created the destination after the initial check.
        os.link(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'status': result['status'], 'windows': len(result['windows']),
                      'output': str(args.output.resolve()), 'errors': result.get('errors'),
                      'rejectedCandidateCounts': result.get('rejectedCandidateCounts')}))
    return 0 if result['status'] == 'prepared' else 2


if __name__ == '__main__':
    raise SystemExit(main())
