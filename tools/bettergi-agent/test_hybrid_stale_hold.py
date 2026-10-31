"""Exercise the live stream's release and no-input wait across an inert replay pause."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import stream_client as client
from test_stream_segments import ContinuousBridge, ContinuousPolicy
from test_hybrid_navigation import capability


class StaleHoldTests(unittest.TestCase):
    def test_one_acknowledged_release_then_no_proposal_until_pose_rebinds(self):
        self.check_hold(False)

    def test_stale_release_keeps_last_accepted_camera_when_a_newer_proposal_is_rejected(self):
        self.check_hold(True)

    def test_reader_terminal_during_stale_selection_is_joined_before_an_empty_release_ack(self):
        self.check_hold(True, early_receipt=True)

    def test_reader_receipt_loss_invalidates_even_with_a_matching_earlier_camera_terminal(self):
        self.check_hold(True, early_receipt=True, lost_receipt=True)

    def check_hold(self, camera, early_receipt=False, lost_receipt=False):
        request_terminal, reader_returned = threading.Event(), threading.Event()
        class Bridge(ContinuousBridge):
            def receipt(self):
                pending = self.pending
                super().receipt()
                if pending:
                    receipt = self.receipts[-1]
                    receipt['appliedSteps'][0].update(pending['steps'][0])
                    receipt.update(modelId=pending['modelId'], endedAtMs=receipt['appliedSteps'][0]['startedAtMs']+100)

            def request(self, command, **kwargs):
                if command == 'enableNavigationGuidance':
                    return dict(type='navigationGuidance', enabled=True, capability=capability()), b''
                if command == 'release':
                    self.commands.append((command, kwargs))
                    self.receipt()
                    receipts, self.receipts = self.receipts, []
                    return dict(type='released', serverNowMs=600, inputAvailable=False, receipts=receipts,
                                worldReadiness=dict(ready=False, epoch=2, reason='client_release')), b''
                if command == 'frame' and request_terminal.is_set() and self.pending and not reader_returned.is_set():
                    self.receipt()
                reply, pixels = super().request(command, **kwargs)
                if command == 'action':
                    reply['acceptedAtMs'] = kwargs['observedAtMs'] + 1
                if command == 'frame':
                    if reply.get('receipts') and request_terminal.is_set():
                        if lost_receipt:
                            reply['droppedReceipts'] = 1
                        reader_returned.set()
                    epoch = 2 if any(name == 'release' for name, _ in self.commands) else 1
                    gate = dict(ready=True, epoch=epoch)
                    reply.update(worldReadiness=gate, frameWorldReadiness=gate, inputAvailable=True)
                return reply, pixels

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'run.json'
            args = client.parse_arguments(['--model', 'open-p2p', '--source', 'inert', '--checkpoint', 'inert',
                '--resident', '--rdp-session-id', '3', '--cuda-graph', '--p2p-fast-start', '--enable-input',
                '--goal-intent', 'ground-navigation', '--hybrid-navigation', '--fps', '30', '--decision-hz', '10',
                '--max-input-actions', '2', '--seconds', '3', '--output', str(path)])
            bridge, policy, nav = Bridge('inert'), ContinuousPolicy(), Mock()
            bridge.hello.update(supportsRelease=True, allowedKeys=['W','A','S','D'])
            bridge.hello['navigationGuidance'] = capability()
            bridge.hello['worldReadiness'] = dict(version=1, requiredForInput=True)
            nav.snapshot.return_value, nav.drain_events.return_value = {}, []
            nav.prepare.side_effect = ([None] if camera else []) + [None, 'confirmingBypassReentry', 'confirmingBypassReentry', None]
            def choose(frame, result):
                if camera and policy.steps == 1:
                    return dict(owner='hybrid-native', reason='nativeHeading', target='end', completedLegs=18,
                                bypassPointIndex=0, step=dict(keys=[], durationMs=100, mouseDx=248, mouseDy=0))
                return dict(owner='open-p2p', reason='modelRouteCompatible', step=result['steps'][0])
            nav.choose.side_effect = choose
            policy.finish_action = Mock()
            eligibility = ([True] if camera else []) + [True,False,False,True,True,True]
            rejections = [None, 'observationTooOld', None] if camera else [None, None]
            eligible = iter(eligibility)
            def fresh(*_):
                value = next(eligible)
                if early_receipt and not value and not reader_returned.is_set():
                    request_terminal.set()  # Deliver after this serial tick already drained its inbox.
                    self.assertTrue(reader_returned.wait(1))
                return value
            def acknowledge(_, reply, action):
                if early_receipt:
                    self.assertEqual(reply['receipts'], [])
                    self.assertIn(action['requestId'], [c.args[0]['requestId'] for c in nav.receipt.call_args_list])
            nav.bypass.acknowledge_stale_hold.side_effect = acknowledge
            # Two stale frames precede the planner's two fresh read-only re-entry samples.
            with patch.object(client, 'Bridge', return_value=bridge), patch('hybrid_navigation.HybridNavigation',
                    return_value=nav), patch.object(client, 'fresh_frame', side_effect=fresh), \
                    patch.object(client, 'proposal_rejection', side_effect=rejections), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(client.run_episode(args, policy), 0)
            actions = [args for command, args in bridge.commands if command == 'action']
            self.assertEqual([command for command, _ in bridge.commands if command in ('action','release')],
                             ['action','release','action'])
            self.assertEqual(policy.steps, 3 if camera else 2)
            if lost_receipt:
                nav.bypass.acknowledge_stale_hold.assert_not_called()
                nav.bypass.invalidate.assert_called_once_with(nav, 'staleHoldReceiptContinuityLost')
            else:
                nav.bypass.acknowledge_stale_hold.assert_called_once()
            report = json.loads(path.read_text())
            stale, = [event for event in report['controlTransitions'] if event['reason'] == 'hybridStalePose']
            ids = [actions[0]['requestId']]
            self.assertEqual(stale['release']['receiptIds'], [] if early_receipt else ids)
            self.assertEqual(stale['release']['priorInboxReceiptIds'], ids if early_receipt else [])
            self.assertEqual(stale['release']['priorInboxReceiptCount'], int(early_receipt))
            self.assertEqual(stale['release']['worldReadiness']['reason'], 'client_release')
            self.assertEqual(stale['release']['serverNowMs'], 600)
            anchor = stale['release']['lastAcceptedAction']
            if not lost_receipt:
                self.assertEqual(nav.bypass.acknowledge_stale_hold.call_args.args[2], anchor)
            self.assertEqual(anchor['requestId'], actions[0]['requestId'])
            self.assertEqual(anchor['acceptedAtMs'], actions[0]['observedAtMs']+1)
            self.assertEqual(anchor['step'], actions[0]['steps'][0])
            if camera:
                self.assertEqual((anchor['modelId'], anchor['reason'], anchor['target'],
                                  anchor['completedLegs'], anchor['bypassPointIndex']),
                                 ('hybrid-native','nativeHeading','end',18,0))


if __name__ == '__main__':
    unittest.main()
