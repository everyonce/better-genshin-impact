"""CPU-only tests of the separate next-acquisition convention and inherited guards."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import prepare_replay as base
from prepare_replay_forward import ARM, KIND, MODE, _forward_arm, main, prepare_forward
from test_prepare_replay import evidence, receipt


def sync_actions(data):
    """Keep the synthetic report and recorder's literal proposal/receipt copies consistent."""
    decisions = {decision['frameId']: decision for decision in data[0]['decisions']}
    receipts = {item['requestId']: item for item in data[0]['receipts']}
    for event in data[3]:
        if event.get('type') == 'proposal':
            event.update(copy.deepcopy(decisions[event['frameId']]))
        elif 'type' not in event and 'requestId' in event:
            event.update(copy.deepcopy(receipts[event['requestId']]))


def change_action(data, fid, keys, mouse):
    """Change a known synthetic action everywhere it must agree, not its clocks."""
    decision = data[0]['decisions'][fid-1]
    for step in decision['steps'] + decision['rawPolicySteps'] + data[0]['receipts'][fid-1]['appliedSteps']:
        step.update(keys=keys[:], mouseDx=mouse[0], mouseDy=mouse[1])
    sync_actions(data)


class ForwardPreparationTests(unittest.TestCase):
    def prepare(self, data, **kwargs):
        return prepare_forward(*data, history_frames=3, max_windows=1, probe_frame_ids=[10], **kwargs)

    def test_original_arms_and_inputs_are_preserved_verbatim(self):
        data = evidence()
        original = copy.deepcopy(data)
        old = base.prepare(*data, history_frames=3, max_windows=1, probe_frame_ids=[10],
                           comparison_mode='same-frames-only')
        result = self.prepare(data)
        self.assertEqual(data, original)
        self.assertEqual(result['kind'], KIND)
        self.assertEqual(result['comparisonMode'], MODE)
        self.assertFalse(result['nominalGridRequirementsApplied'])
        self.assertFalse(result['trainingEligible'])
        self.assertFalse(result['humanDemonstrations'])
        self.assertFalse(result['publishedCallbackAlignmentEstablished'])
        window = result['windows'][0]
        for name in ('accepted_proxy', 'receipt_same_frames'):
            self.assertEqual(window['arms'][name], old['windows'][0]['arms'][name])
        for arm in window['arms'].values():
            self.assertEqual([item['frame']['frameId'] for item in arm['samples']], [7, 8, 9])
        self.assertEqual(window['goalProvenance'], old['windows'][0]['goalProvenance'])
        self.assertIsNone(window['probeLabel'])

    def test_forward_endpoint_and_mouse_once_exclude_probe_action(self):
        data = evidence()
        for fid, key in ((6, 'A'), (7, 'W'), (8, 'S'), (9, 'D'), (10, 'SPACE')):
            change_action(data, fid, [key], (fid, -fid))
        window = self.prepare(data)['windows'][0]
        forward = window['arms'][ARM]
        labels = [sample['label'] for sample in forward['samples']]
        self.assertEqual([label['heldKeys'] for label in labels], [['W'], ['S'], ['D']])
        self.assertEqual([label['mouseDx'] for label in labels], [7, 8, 9])
        self.assertEqual([sample['label']['mouseDx'] for sample in window['arms']['receipt_same_frames']['samples']], [6, 7, 8])
        self.assertEqual(labels[-1]['interval'], {'startExclusiveMs': 450, 'endInclusiveMs': 500})
        self.assertEqual(labels[-1]['endpointRole'], 'probe-clock-only')
        self.assertEqual(forward['labelSpanMs'], 150)
        self.assertEqual(forward['historyImageSpanMs'], 100)
        event_ids = [event['eventId'] for label in labels for event in label['mouseEvents']]
        self.assertEqual(event_ids, ['r7:step:0', 'r8:step:0', 'r9:step:0'])
        self.assertTrue(all(label['provenance'] == 'system/backend-dispatch-intent' for label in labels))

    def test_probe_and_later_outputs_cannot_change_new_labels(self):
        data = evidence()
        before = self.prepare(data)['windows'][0]['arms'][ARM]
        for fid in range(10, 31):
            change_action(data, fid, ['A', 'SPACE'], (40, -20))
        after = self.prepare(data)['windows'][0]['arms'][ARM]
        self.assertEqual(before, after)
        self.assertTrue(any(event['timeMs'] > 500 for event in base.ReceiptTimeline(data[0]['receipts']).events))

    def test_replacement_keeps_held_state_and_mouse_is_not_repeated(self):
        window = self.prepare(evidence())['windows'][0]
        timeline = base.ReceiptTimeline([receipt('r6', 300, 310, 420, ['W']),
                                         receipt('r7', 420, 430, 520, ['W'], mouse=(9, -2), status='completed')])
        arm = _forward_arm(window, timeline, {'r6': 6, 'r7': 7})
        labels = [sample['label'] for sample in arm['samples']]
        self.assertEqual([label['heldKeys'] for label in labels], [['W']]*3)
        self.assertEqual([label['mouseDx'] for label in labels], [0, 9, 0])
        self.assertFalse(any(event['kind'] == 'release' for label in labels for event in label['stateTransitions']))

    def test_horizon_cancel_and_unstarted_cancel_release_inherited_state(self):
        window = self.prepare(evidence())['windows'][0]
        timelines = [
            [receipt('r6', 300, 310, 380, ['W'], status='completed')],
            [receipt('r6', 300, 310, 380, ['W'], status='cancelled')],
            [receipt('r6', 300, 310, 360, ['W']), receipt('r7', 360, None, 380, [], status='cancelled')],
        ]
        for receipts in timelines:
            with self.subTest(receipts=receipts):
                arm = _forward_arm(window, base.ReceiptTimeline(receipts), {'r6': 6, 'r7': 7})
                labels = [sample['label'] for sample in arm['samples']]
                self.assertEqual(labels[0]['initialHeldKeys'], ['W'])
                self.assertEqual([label['heldKeys'] for label in labels], [[], [], []])
                self.assertEqual(labels[0]['stateTransitions'][-1]['kind'], 'release')

    def test_input_on_selected_acquisition_boundary_is_rejected(self):
        data = evidence()
        data[0]['receipts'][6]['appliedSteps'][0]['startedAtMs'] = 400
        sync_actions(data)
        self.assertEqual(base.prepare(*data, history_frames=3, probe_frame_ids=[10],
                                     comparison_mode='same-frames-only')['status'], 'prepared')
        result = self.prepare(data)
        self.assertEqual(result['status'], 'no_eligible_windows')
        self.assertEqual(result['rejectedCandidateCounts'], {'input_event_on_acquisition_boundary': 1})

    def test_unknown_initial_state_and_probe_owned_input_fail_closed(self):
        window = self.prepare(evidence())['windows'][0]
        with self.assertRaisesRegex(base.EvidenceError, 'unknown_initial_held_state'):
            _forward_arm(window, base.ReceiptTimeline([receipt('r7', 360, 365, 520, ['W'], status='completed')]), {'r7': 7})
        with self.assertRaisesRegex(base.EvidenceError, 'probe_or_later_action_in_history'):
            _forward_arm(window, base.ReceiptTimeline([receipt('r10', 300, 310, 520, ['W'], status='completed')]), {'r10': 10})

    def test_common_reset_goal_epoch_readiness_guards_remain(self):
        for kind in ('reset', 'goal', 'capture_epoch', 'readiness'):
            with self.subTest(kind=kind):
                data = evidence()
                if kind == 'reset':
                    data[0]['decisions'][7]['episodeStep'] = 1
                    sync_actions(data)
                elif kind == 'goal':
                    data[0]['decisions'][7]['policyGoalVersion'] = 1
                    sync_actions(data)
                else:
                    for rows in (data[1], data[2]):
                        if kind == 'capture_epoch':
                            rows[7]['sourceFrame']['captureEpoch'] = 'different'
                        else:
                            rows[7]['frameWorldReadiness']['ready'] = False
                result = self.prepare(data)
                self.assertEqual(result['status'], 'no_eligible_windows')
                self.assertTrue(result['rejectedCandidateCounts'])

    def test_missing_receipts_video_join_and_clock_contradictions_still_fail(self):
        for kind in ('receipt', 'video', 'clock'):
            with self.subTest(kind=kind):
                data = evidence()
                if kind == 'receipt':
                    data[0]['receipts'].pop()
                elif kind == 'video':
                    data[2][7]['videoFrameIndex'] = 999
                else:
                    data[1][7]['sourceFrame']['acquiredAtMs'] += 200
                    data[2][7]['sourceFrame']['acquiredAtMs'] += 200
                with self.assertRaises(base.EvidenceError):
                    self.prepare(data)

    def test_explicit_positive_unique_probes_are_required(self):
        for ids in (None, [], [True], [0], [10, 10]):
            with self.subTest(ids=ids), self.assertRaises(base.EvidenceError):
                prepare_forward(*evidence(), history_frames=3, probe_frame_ids=ids)

    def test_cli_publishes_separate_plan_and_refuses_overwrite(self):
        data = evidence()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'report.json').write_text(json.dumps(data[0]), encoding='utf-8')
            for name, rows in zip(('observations', 'frames', 'events'), data[1:4]):
                (root/(name+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')
            (root/'recording.json').write_text(json.dumps(data[4]), encoding='utf-8')
            (root/'frames.mp4').write_bytes(b'synthetic nonempty placeholder; no video decoding in this test')
            output = root/'forward-v1.json'
            args = ['--report', str(root/'report.json'), '--recording-dir', str(root), '--output', str(output),
                    '--probe-frame-id', '10', '--history-frames', '3']
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            result = json.loads(output.read_text(encoding='utf-8'))
            original_bytes = output.read_bytes()
            self.assertEqual(result['kind'], KIND)
            self.assertEqual(len(result['inputEvidence']), 6)
            self.assertEqual(set(result['preparerEvidence']), {'forward', 'base'})
            self.assertFalse(result['inferenceExecuted'])
            with self.assertRaisesRegex(base.EvidenceError, 'output_already_exists'):
                main(args)
            self.assertEqual(output.read_bytes(), original_bytes)


if __name__ == '__main__':
    unittest.main()
