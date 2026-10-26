"""Continuous saved-file joins with deterministic fixtures; no model or live IO."""
import copy
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_replay as base
import prepare_replay_session as session
from prepare_replay_session import RecordedSegment, prepare_session, stitch_segments
from test_prepare_replay import evidence


def continuous_evidence(count=30, cut=12):
    """Split a valid lease with one accepted action's receipt crossing the boundary."""
    report, observations, frames, _, recording = evidence(count)
    # One mouse event makes accidental duplication across the join observable.
    for key in ('steps', 'rawPolicySteps'):
        report['decisions'][cut-1][key][0]['mouseDx'] = 7
    report['receipts'][cut-1]['appliedSteps'][0]['mouseDx'] = 7
    proposals = [dict(copy.deepcopy(row), type='proposal', observedAtMs=observations[i]['capturedAtMs'])
                 for i, row in enumerate(report['decisions'])]
    result = []
    for index, (start, end) in enumerate(((0, cut), (cut, count)), 1):
        path = Path('fixture-reports') / f'{index:05d}.json'
        context = {'previousReport': str(result[-1].report_path) if result else None,
                   'sameBridgeLease': bool(result),
                   'pendingProposals': [dict(copy.deepcopy(proposals[cut-1]), originSegment=1)] if result else [],
                   'sourceFrames': [{key: value for key, value in copy.deepcopy(observations[cut-1]).items()
                                     if key != 'videoQueueAccepted'}] if result else [],
                   'join': 'sessionId + ownerEpoch + requestId; frameId refers to the same lease clock'}
        local_observations = [dict(copy.deepcopy(row), continuityContext=True, videoQueueAccepted=None)
                              for row in context['sourceFrames']] + copy.deepcopy(observations[start:end])
        local_frames = [dict(copy.deepcopy(row), videoFrameIndex=i, videoPtsSeconds=i/20)
                        for i, row in enumerate(frames[start:end])]
        local_events = ([dict(copy.deepcopy(report['hello']), type='episodeStart')] if index == 1 else
                        [{'type': 'segmentStart', 'segment': index, 'sessionId': 'session', 'ownerEpoch': 'owner',
                          'continuity': copy.deepcopy(context)}])
        local_receipts = []
        for i in range(start, end):
            if i:
                local_receipts.append(copy.deepcopy(report['receipts'][i-1]))
                local_events.append(copy.deepcopy(report['receipts'][i-1]))
            local_events.append(copy.deepcopy(proposals[i]))
        if index == 2:
            local_receipts.append(copy.deepcopy(report['receipts'][-1]))
            local_events.extend([copy.deepcopy(report['receipts'][-1]),
                                 {'type': 'episodeEnd', 'acceptedInputActions': count}])
        reason = 'segmentRotated' if index == 1 else 'durationElapsed'
        local_events.append({'type': 'segmentEnd', 'segment': index, 'endReason': reason, 'leaseEnded': index == 2})
        local_recording = dict(recording, encodedFrames=end-start, recordedObservations=len(local_observations))
        local_report = copy.deepcopy(report)
        local_report.update(status='completed', endReason=reason, framesReceived=end-start,
                            acceptedInputActions=end-start, decisions=copy.deepcopy(report['decisions'][start:end]),
                            receipts=local_receipts, recording=copy.deepcopy(local_recording), continuity=context,
                            segment={'number': index, 'startedAtClientNs': 0 if index == 1 else 630000000,
                                     'endedAtClientNs': 630000000 if index == 1 else 1700000000,
                                     'leaseEnded': index == 2},
                            finalGoalState=copy.deepcopy(report['initialGoalState']), policyMetadata=None,
                            finalPolicyMetadata=None, leaseInitialGoalState=copy.deepcopy(report['initialGoalState']),
                            leaseInitialPolicyMetadata=None)
        result.append(RecordedSegment(path, Path('fixture-recordings')/f'{index:05d}', local_report,
                                      local_observations, local_frames, local_events, local_recording))
    return result


class ContinuousReplayTests(unittest.TestCase):
    """Exercise source ownership and original image addressing across rollover."""
    def test_crossing_receipt_and_video_boundary_preserve_original_addresses(self):
        segments = continuous_evidence()
        original = copy.deepcopy(segments)
        result = prepare_session(segments, history_frames=4, max_windows=1,
                                 probe_frame_ids=[14], comparison_mode='same-frames-only')
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['evidenceCounts']['observations'], 30)
        self.assertEqual(result['evidenceCounts']['receipts'], 30)
        self.assertFalse(result['trainingEligible'])
        self.assertFalse(result['expertDemonstrations'])
        window = result['windows'][0]
        self.assertEqual(window['probe']['videoFrameIndex'], 1)
        self.assertEqual(window['probe']['recordingSegment'], 2)
        arm = window['arms']['receipt_same_frames']
        self.assertEqual(arm['anchor']['recordingSegment'], 1)
        self.assertEqual(arm['anchor']['videoFrameIndex'], 8)
        self.assertEqual(arm['samples'][-1]['frame']['videoFrameIndex'], 0)
        self.assertEqual(arm['samples'][-1]['frame']['videoFile'],
                         str((segments[1].recording_dir/'frames.mp4').resolve()))
        mouse = [event for sample in arm['samples'] for event in sample['label']['mouseEvents']]
        self.assertEqual([event['eventId'] for event in mouse], ['r12:step:0'])
        self.assertTrue(all(sample['label']['heldKeys'] == ['W'] for sample in arm['samples']))
        self.assertEqual(segments, original)

    def test_changed_owner_or_missing_middle_segment_is_rejected(self):
        for field, value, reason in (('ownerEpoch', 'other', 'lease_or_configuration_changed'),):
            with self.subTest(field=field):
                segments = continuous_evidence()
                segments[1].report['hello'][field] = value
                with self.assertRaisesRegex(base.EvidenceError, reason):
                    stitch_segments(segments)
        segments = continuous_evidence()
        segments[1].report['segment']['number'] = 3
        with self.assertRaisesRegex(base.EvidenceError, 'segment_sequence_gap'):
            stitch_segments(segments)

    def test_wrong_previous_file_and_unfinished_lease_are_rejected(self):
        segments = continuous_evidence()
        segments[1].report['continuity']['previousReport'] = 'different.json'
        with self.assertRaisesRegex(base.EvidenceError, 'previous_report_mismatch'):
            stitch_segments(segments)
        with self.assertRaisesRegex(base.EvidenceError, 'lease_not_complete_chain'):
            stitch_segments(continuous_evidence()[:1])

    def test_changed_carried_proposal_cannot_replace_original_evidence(self):
        segments = continuous_evidence()
        context = segments[1].report['continuity']
        context['pendingProposals'][0]['originSegment'] = 99
        segments[1].events[0]['continuity'] = copy.deepcopy(context)
        with self.assertRaisesRegex(base.EvidenceError, 'pending_proposal_context_mismatch'):
            stitch_segments(segments)

    def test_consistently_changed_context_header_still_fails_original_join(self):
        segments = continuous_evidence()
        context = segments[1].report['continuity']
        context['sourceFrames'][0]['capturedAtMs'] += 1
        segments[1].observations[0]['capturedAtMs'] += 1
        segments[1].events[0]['continuity'] = copy.deepcopy(context)
        with self.assertRaisesRegex(base.EvidenceError, 'context_source_changed'):
            stitch_segments(segments)

    def test_local_video_indices_are_checked_before_virtual_join(self):
        segments = continuous_evidence()
        segments[1].frames[0]['videoFrameIndex'] = 12
        with self.assertRaisesRegex(base.EvidenceError, 'noncontiguous_video_index'):
            stitch_segments(segments)

    def test_missing_terminal_and_recording_loss_are_not_hidden(self):
        segments = continuous_evidence()
        segments[1].report['receipts'].pop()
        segments[1].events[:] = [row for row in segments[1].events if row.get('requestId') != 'r30']
        with self.assertRaisesRegex(base.EvidenceError, 'missing_terminal_receipts'):
            stitch_segments(segments)
        segments = continuous_evidence()
        segments[0].recording['droppedEvents'] = 1
        with self.assertRaisesRegex(base.EvidenceError, 'recording_loss:droppedEvents'):
            stitch_segments(segments)

    def test_old_terminal_clock_contradiction_remains_rejected(self):
        segments = continuous_evidence()
        receipt = segments[1].report['receipts'][-1]
        receipt['endedAtMs'] = receipt['appliedSteps'][0]['startedAtMs'] - .2
        for event in segments[1].events:
            if event.get('requestId') == receipt['requestId']:
                event.update(copy.deepcopy(receipt))
        with self.assertRaisesRegex(base.EvidenceError, 'invalid_applied_step_time'):
            prepare_session(segments, history_frames=4, max_windows=1, comparison_mode='same-frames-only')

    def test_rearm_event_is_required_and_preserved_as_a_boundary(self):
        payload = evidence()
        event = {'type': 'navigationIdleRearmed', 'clientTimeNs': 325000000, 'requestId': 'r6'}
        payload[0]['navigationIdleRecoveryEvents'] = [event]
        payload[3].insert(-1, copy.deepcopy(event))
        result = base.prepare(*payload, history_frames=4, max_windows=1,
                              probe_frame_ids=[9], comparison_mode='same-frames-only')
        self.assertEqual(result['status'], 'no_eligible_windows')
        self.assertEqual(result['rejectedCandidateCounts'], {'boundary:navigationIdleRearmed': 1})
        payload[3].remove(event)
        with self.assertRaisesRegex(base.EvidenceError, 'missing_or_contradictory_boundary_events'):
            base.prepare(*payload, history_frames=4, max_windows=1, comparison_mode='same-frames-only')

    def test_per_segment_action_counts_cannot_cancel_out_across_the_lease(self):
        segments = continuous_evidence()
        segments[0].report['acceptedInputActions'] += 1
        segments[1].report['acceptedInputActions'] -= 1
        with self.assertRaisesRegex(base.EvidenceError, 'segment_action_count_mismatch'):
            stitch_segments(segments)

    def test_repeated_context_is_not_allowed_to_claim_an_encoded_image(self):
        segments = continuous_evidence()
        segments[1].observations[0]['videoQueueAccepted'] = True
        with self.assertRaisesRegex(base.EvidenceError, 'context_claims_new_video'):
            stitch_segments(segments)


def save_fixture(root):
    """Write only disposable fixture sidecars and opaque, deliberately undecoded video bytes."""
    result = []
    for index, original in enumerate(continuous_evidence(), 1):
        directory = root/'recordings'/f'{index:05d}'
        report_path = root/'reports'/f'{index:05d}.json'
        directory.mkdir(parents=True)
        report_path.parent.mkdir(exist_ok=True)
        segment = replace(original, report_path=report_path, recording_dir=directory)
        if result:
            segment.report['continuity']['previousReport'] = str(result[-1].report_path)
            segment.events[0]['continuity'] = copy.deepcopy(segment.report['continuity'])
        report_path.write_text(json.dumps(segment.report), encoding='utf-8')
        (directory/'recording.json').write_text(json.dumps(segment.recording), encoding='utf-8')
        for name, rows in (('frames', segment.frames), ('observations', segment.observations), ('events', segment.events)):
            (directory/(name+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')
        (directory/'frames.mp4').write_bytes(b'opaque fixture; this preparer does not decode video')
        result.append(segment)
    return result


class ContinuousReplayCliTests(unittest.TestCase):
    """Verify source preservation, strict parsing, and mutation rejection at the file boundary."""
    def test_cli_preserves_all_sources_and_returns_local_video_addresses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            segments = save_fixture(root)
            before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            output = root/'audit.json'
            args = ['--reports-dir', str(root/'reports'), '--recordings-dir', str(root/'recordings'),
                    '--history-frames', '4', '--max-windows', '1', '--probe-frame-id', '14', '--output', str(output)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(session.main(args), 0)
            result = json.loads(output.read_text())
            self.assertEqual(result['windows'][0]['probe']['videoFrameIndex'], 1)
            self.assertEqual(len(result['inputEvidence']), 12)
            self.assertTrue(all(path.read_bytes() == data for path, data in before.items()))
            with self.assertRaisesRegex(base.EvidenceError, 'output_would_modify_source_directory'):
                session.main(args[:-1]+[str(segments[0].report_path)])

    def test_source_change_during_preparation_publishes_only_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            segments = save_fixture(root)
            original_prepare = session.prepare_session
            def mutate_after_preparation(*args, **kwargs):
                result = original_prepare(*args, **kwargs)
                with (segments[0].recording_dir/'frames.jsonl').open('a', encoding='utf-8') as handle:
                    handle.write('\n')
                return result
            with patch.object(session, 'prepare_session', side_effect=mutate_after_preparation), redirect_stdout(io.StringIO()):
                self.assertEqual(session.main(['--reports-dir', str(root/'reports'), '--recordings-dir', str(root/'recordings'),
                    '--history-frames', '4', '--max-windows', '1', '--output', str(root/'audit.json')]), 2)
            result = json.loads((root/'audit.json').read_text())
            self.assertEqual(result['errors'], ['input_changed_during_preparation'])
            self.assertEqual(result['windows'], [])
            self.assertFalse(result['trainingEligible'])

    def test_duplicate_properties_and_nonfinite_values_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'metadata.json'
            for content, reason in (('{"a":1,"a":2}', 'duplicate_json_property'), ('{"a":NaN}', 'nonfinite_json')):
                with self.subTest(content=content):
                    path.write_text(content, encoding='utf-8')
                    with self.assertRaisesRegex(base.EvidenceError, reason):
                        session._read_json(path)


if __name__ == '__main__':
    unittest.main()
