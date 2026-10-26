"""Join one closed resident lease for offline P2P replay preparation.

Segment boundaries retain their original evidence. No video is concatenated,
pixels decoded, model loaded, or expert training data produced.
"""
import argparse
import copy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

import prepare_replay as base


MAX_SEGMENTS = 128
MAX_JSON_BYTES = 128 * 1024 * 1024
LIST_FIELDS = ('decisions', 'receipts', 'controlTransitions', 'goalChanges',
               'navigationProgress', 'navigationIdleRecoveryEvents')
COUNTER_FIELDS = ('framesReceived', 'acceptedInputActions', 'unappliedAcceptedActions', 'receiptHistoryResets')
FIXED_FIELDS = ('hello', 'model', 'inputRequested', 'observationProfile', 'preprocessingContract',
                'capturePollHz', 'decisionHz', 'residentRunId', 'proposalJournal',
                'firstInputDeadlinePolicy', 'configuredInputKeys', 'effectiveInputKeys', 'actionHoldMs')


@dataclass(frozen=True)
class RecordedSegment:
    """Original sidecars and their file locations; the join never mutates them."""
    report_path: Path
    recording_dir: Path
    report: dict
    observations: list
    frames: list
    events: list
    recording: dict


def _header(row):
    """Remove only recorder annotations, preserving every original source field."""
    return {key: value for key, value in row.items()
            if key not in ('videoQueueAccepted', 'continuityContext')}


def _closed_recording(segment):
    """Check both final summaries against actual sidecar counts before joining."""
    report = segment.report
    base.require(report.get('status') == 'completed' and not any(report.get(key) for key in
                 ('error', 'streamError', 'stopError', 'unacknowledgedAction')), 'segment_not_complete')
    for summary in (report.get('recording', {}), segment.recording):
        base.require(summary.get('closed') is True and summary.get('complete') is True
                     and summary.get('error') is None, 'recording_not_complete')
        for key in ('droppedFrames', 'droppedEvents', 'abandonedFrames', 'droppedObservations'):
            base.require(base.integer(summary.get(key), key) == 0, 'recording_loss:' + key)
        base.require(base.integer(summary.get('encodedFrames'), 'encodedFrames') == len(segment.frames)
                     and base.integer(summary.get('recordedObservations'), 'recordedObservations')
                     == len(segment.observations), 'recording_count_mismatch')
    base.require(base.integer(report.get('serverDroppedReceipts'), 'serverDroppedReceipts') == 0,
                 'server_receipts_missing')


def stitch_segments(segments):
    """Verify one exact lease chain, then build an in-memory view for existing checks."""
    base.require(1 <= len(segments) <= MAX_SEGMENTS, 'segment_count_out_of_range')
    first = segments[0].report
    hello = first.get('hello', {})
    base.require(all(isinstance(hello.get(key), str) and hello[key] for key in ('sessionId', 'ownerEpoch')),
                 'missing_lease_identity')
    combined = copy.deepcopy(first)
    for key in LIST_FIELDS:
        combined[key] = []
    for key in COUNTER_FIELDS:
        combined[key] = 0
    observations, frames, events = [], [], []
    original_headers, addresses, pending, terminal_ids = {}, {}, {}, set()
    source_segments, prior = [], None
    first_number = base.integer(first.get('segment', {}).get('number'), 'segment.number')
    base.require(first_number > 0, 'invalid_segment_number')
    fps = base.number(first.get('capturePollHz'), 'capturePollHz')
    base.require(fps > 0, 'invalid_capture_fps')

    for offset, segment in enumerate(segments):
        report, number = segment.report, first_number + offset
        _closed_recording(segment)
        base.require(all(report.get(key) == first.get(key) for key in FIXED_FIELDS),
                     'lease_or_configuration_changed')
        metadata = report.get('segment', {})
        base.require(type(metadata.get('number')) is int and metadata['number'] == number,
                     'segment_sequence_gap')
        started = base.integer(metadata.get('startedAtClientNs'), 'segment.startedAtClientNs')
        ended = base.integer(metadata.get('endedAtClientNs'), 'segment.endedAtClientNs')
        base.require(started <= ended, 'negative_segment_interval')
        final = offset == len(segments) - 1
        base.require(metadata.get('leaseEnded') is final
                     and ((report.get('endReason') != 'segmentRotated') if final
                          else report.get('endReason') == 'segmentRotated'), 'lease_not_complete_chain')
        context = report.get('continuity')
        base.require(isinstance(context, dict), 'missing_continuity_context')
        carried = [row for row in segment.observations if row.get('continuityContext') is True]
        ordinary = [row for row in segment.observations if row.get('continuityContext') is not True]
        base.require(len(ordinary) == base.integer(report.get('framesReceived'), 'framesReceived'),
                     'segment_observation_count_mismatch')
        base.require(all(row.get('videoQueueAccepted') is None for row in carried),
                     'context_claims_new_video')
        context_frames = context.get('sourceFrames')
        context_proposals = context.get('pendingProposals')
        base.require(isinstance(context_frames, list) and isinstance(context_proposals, list),
                     'invalid_continuity_context')
        proposals = [row for row in segment.events if row.get('type') == 'proposal']
        receipts = [row for row in segment.events if 'type' not in row and 'requestId' in row]
        base.require(len(proposals) == len(report.get('decisions', []))
                     and receipts == report.get('receipts', []), 'segment_action_membership_mismatch')
        base.require(sum(row.get('acceptance', {}).get('type') == 'accepted' for row in proposals)
                     == base.integer(report.get('acceptedInputActions'), 'acceptedInputActions'),
                     'segment_action_count_mismatch')
        base.require(len(carried) == len(context_frames)
                     and [_header(row) for row in carried] == context_frames, 'carried_header_mismatch')
        starts = [row for row in segment.events if row.get('type') == 'segmentStart']
        ends = [row for row in segment.events if row.get('type') == 'segmentEnd']
        base.require(len(ends) == 1 and segment.events[-1] == ends[0]
                     and ends[0] == {'type': 'segmentEnd', 'segment': number,
                                    'endReason': report['endReason'], 'leaseEnded': final},
                     'segment_end_mismatch')
        if prior is None:
            base.require(context.get('previousReport') is None and context.get('sameBridgeLease') is False
                         and not context_frames and not context_proposals and not starts,
                         'missing_lease_start')
            base.require(segment.events[0].get('type') == 'episodeStart', 'missing_episode_start')
            base.require(report.get('leaseInitialGoalState') == report.get('initialGoalState')
                         and report.get('leaseInitialPolicyMetadata') == report.get('policyMetadata'),
                         'lease_initial_state_mismatch')
        else:
            previous = prior.report
            base.require(context.get('sameBridgeLease') is True
                         and isinstance(context.get('previousReport'), str)
                         and Path(context['previousReport']).resolve() == prior.report_path.resolve(),
                         'previous_report_mismatch')
            base.require(started == previous['segment']['endedAtClientNs'], 'segment_clock_gap')
            base.require(len(starts) == 1 and segment.events[0] == starts[0]
                         and starts[0] == {'type': 'segmentStart', 'segment': number,
                            'sessionId': first['hello']['sessionId'], 'ownerEpoch': first['hello']['ownerEpoch'],
                            'continuity': context}, 'segment_start_mismatch')
            base.require(report.get('initialGoalState') == previous.get('finalGoalState')
                         and report.get('policyMetadata') == previous.get('finalPolicyMetadata'),
                         'rollover_policy_state_mismatch')
            for key in ('leaseInitialGoalState', 'leaseInitialPolicyMetadata'):
                base.require(report.get(key) == first.get(key), 'lease_initial_state_changed')
            carried_pending = {}
            for proposal in context_proposals:
                rid = proposal.get('acceptance', {}).get('requestId')
                base.require(isinstance(rid, str) and rid and rid not in carried_pending,
                             'duplicate_or_missing_carried_proposal')
                carried_pending[rid] = proposal
            base.require(carried_pending == pending, 'pending_proposal_context_mismatch')
            expected_ids = {proposal['frameId'] for proposal in pending.values()}
            if original_headers:
                expected_ids.add(next(reversed(original_headers)))
            ids = [row.get('frameId') for row in context_frames]
            base.require(len(ids) == len(set(ids)) and set(ids) == expected_ids, 'context_frame_set_mismatch')
            base.require(all(row == original_headers.get(row['frameId']) for row in context_frames),
                         'context_source_changed')

        # Validate each real video's indices before creating transient aggregate indices.
        base._frames(ordinary, segment.frames, report['observationProfile'], fps)
        base.require(all('continuityContext' not in row for row in ordinary), 'invalid_context_marker')
        for row in ordinary:
            fid = row['frameId']
            base.require(fid not in original_headers, 'frame_reused_across_segments')
            original_headers[fid] = _header(row)
            observations.append(copy.deepcopy(row))
        for row in segment.frames:
            fid = row['frameId']
            addresses[fid] = {'recordingSegment': number,
                              'videoFile': str((segment.recording_dir / 'frames.mp4').resolve()),
                              'videoFrameIndex': row['videoFrameIndex'],
                              'videoPtsSeconds': row['videoPtsSeconds']}
            frames.append(dict(copy.deepcopy(row), videoFrameIndex=len(frames), videoPtsSeconds=len(frames)/fps))
        for event in segment.events:
            kind = event.get('type')
            if kind in ('segmentStart', 'segmentEnd'):
                continue
            if kind == 'proposal' and event.get('acceptance', {}).get('type') == 'accepted':
                rid = event['acceptance'].get('requestId')
                base.require(isinstance(rid, str) and rid and rid not in pending, 'duplicate_accepted_proposal')
                if rid not in terminal_ids:
                    pending[rid] = dict(copy.deepcopy(event), originSegment=number)
            elif kind is None and 'requestId' in event:
                rid = event['requestId']
                base.require(rid not in terminal_ids, 'duplicate_terminal_receipt')
                terminal_ids.add(rid)
                pending.pop(rid, None)
            events.append(copy.deepcopy(event))
        for key in LIST_FIELDS:
            base.require(isinstance(report.get(key, []), list), 'invalid_report_list:' + key)
            combined[key].extend(copy.deepcopy(report.get(key, [])))
        for key in COUNTER_FIELDS:
            combined[key] += base.integer(report.get(key, 0), key)
        source_segments.append({'number': number, 'report': str(segment.report_path.resolve()),
                                'recordingDirectory': str(segment.recording_dir.resolve()),
                                'framesReceived': len(ordinary), 'carriedHeaders': len(carried),
                                'pendingProposalsAtStart': len(context_proposals)})
        prior = segment

    base.require(not pending, 'missing_terminal_receipts')
    final_report = segments[-1].report
    combined.update(endReason=final_report['endReason'], finalGoalState=copy.deepcopy(final_report.get('finalGoalState')),
                    finalPolicyMetadata=copy.deepcopy(final_report.get('finalPolicyMetadata')))
    # This summary is an in-memory validation view, never a replacement recording file.
    recording = {'complete': True, 'closed': True, 'error': None,
                 'encodedFrames': len(frames), 'recordedObservations': len(observations),
                 'droppedFrames': 0, 'droppedEvents': 0, 'abandonedFrames': 0, 'droppedObservations': 0}
    combined['recording'] = copy.deepcopy(recording)
    return [combined, observations, frames, events, recording], addresses, source_segments


def prepare_session(segments, **options):
    """Apply the original replay gates and restore every original video address."""
    payload, addresses, sources = stitch_segments(segments)
    result = base.prepare(*payload, **options)
    for window in result['windows']:
        references = [window['probe']]
        for arm in window['arms'].values():
            references.append(arm['anchor'])
            references.extend(sample['frame'] for sample in arm['samples'])
        for reference in references:
            reference.update(addresses[reference['frameId']])
    result.update(kind='p2p-offline-continuous-history-candidates', joinVersion=1, sourceSegments=sources,
                  videoAddressing='original videoFile + local videoFrameIndex; videos are not concatenated')
    result['limitations'].append('Continuous source joins preserve recorded software intent; they do not create expert labels.')
    return result


def _unique_object(pairs):
    """Reject duplicate JSON properties rather than silently replacing evidence."""
    result = {}
    for key, value in pairs:
        base.require(key not in result, 'duplicate_json_property:' + key)
        result[key] = value
    return result


def _read_json(path, lines=False):
    """Decode strict saved metadata; no live runtime or model imports are needed."""
    def invalid(value):
        raise base.EvidenceError('nonfinite_json:' + value)
    with path.open(encoding='utf-8') as handle:
        if lines:
            return [json.loads(line, object_pairs_hook=_unique_object, parse_constant=invalid)
                    for line in handle if line.strip()]
        return json.load(handle, object_pairs_hook=_unique_object, parse_constant=invalid)


def main(argv=None):
    """Hash original files, prepare one complete lease, and save a separate audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports-dir', type=Path, required=True)
    parser.add_argument('--recordings-dir', type=Path, required=True)
    parser.add_argument('--first-segment', type=int)
    parser.add_argument('--last-segment', type=int)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--history-frames', type=int, default=40)
    parser.add_argument('--max-windows', type=int, default=6)
    parser.add_argument('--max-source-gap-ms', type=float, default=100)
    parser.add_argument('--probe-frame-id', type=int, action='append')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    base.require(not any(output.is_relative_to(root.resolve()) for root in (args.reports_dir, args.recordings_dir)),
                 'output_would_modify_source_directory')
    evidence = {}
    try:
        base.require((args.first_segment is None) == (args.last_segment is None), 'both_segment_bounds_required')
        if args.first_segment is not None:
            base.require(0 < args.first_segment <= args.last_segment, 'invalid_segment_bounds')
        paths = sorted(args.reports_dir.glob('[0-9][0-9][0-9][0-9][0-9].json'))
        if args.first_segment is not None:
            paths = [path for path in paths if args.first_segment <= int(path.stem) <= args.last_segment]
            base.require(len(paths) == args.last_segment - args.first_segment + 1, 'missing_selected_segment')
        base.require(1 <= len(paths) <= MAX_SEGMENTS, 'segment_count_out_of_range')
        segments, json_bytes = [], 0
        for report_path in paths:
            directory = args.recordings_dir / report_path.stem
            files = {'report': report_path, **{name: directory / name for name in (
                'recording.json', 'observations.jsonl', 'frames.jsonl', 'events.jsonl', 'frames.mp4')}}
            for name, path in files.items():
                if name != 'frames.mp4':
                    json_bytes += path.stat().st_size
                    base.require(json_bytes <= MAX_JSON_BYTES, 'metadata_memory_bound_exceeded')
                evidence[f'{report_path.stem}/{name}'] = base._file_evidence(path)
            base.require(evidence[f'{report_path.stem}/frames.mp4']['bytes'] > 0, 'empty_video')
            report = _read_json(report_path)
            base.require(report.get('segment', {}).get('number') == int(report_path.stem), 'filename_segment_mismatch')
            segments.append(RecordedSegment(report_path, directory, report,
                _read_json(files['observations.jsonl'], True), _read_json(files['frames.jsonl'], True),
                _read_json(files['events.jsonl'], True), _read_json(files['recording.json'])))
        result = prepare_session(segments, history_frames=args.history_frames, max_windows=args.max_windows,
                                 max_source_gap_ms=args.max_source_gap_ms, probe_frame_ids=args.probe_frame_id,
                                 comparison_mode='same-frames-only')
        base.require(evidence == {name: base._file_evidence(Path(pin['path'])) for name, pin in evidence.items()},
                     'input_changed_during_preparation')
    except (base.EvidenceError, OSError, ValueError, KeyError, TypeError, IndexError) as error:
        result = {'schemaVersion': 1, 'kind': 'p2p-offline-continuous-history-candidates', 'joinVersion': 1,
                  'status': 'rejected', 'trainingEligible': False, 'expertDemonstrations': False,
                  'inferenceExecuted': False, 'errors': [str(error)], 'windows': []}
    result['inputEvidence'] = evidence
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                     prefix=output.name + '.', suffix='.tmp', delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(result, handle, indent=2, allow_nan=False)
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'status': result['status'], 'windows': len(result['windows']),
                      'errors': result.get('errors'), 'output': str(output)}))
    return 0 if result['status'] == 'prepared' else 2


if __name__ == '__main__':
    raise SystemExit(main())
