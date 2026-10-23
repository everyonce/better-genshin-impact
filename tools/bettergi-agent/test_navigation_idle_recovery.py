"""CPU-only navigation recovery, immutable goal intent, and control-race regressions."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import control_resident
import resident_runtime as runtime
import stream_client as client
from navigation_idle_recovery import NavigationIdleRecovery, MOTION_METHOD, eligible_frame


CAPABILITY = {'version': 1, 'method': MOTION_METHOD, 'sameFrame': True, 'normalIsGroundedProof': False}


def frame(stamp=1000, epoch=0, status='normal'):
    """Create synthetic known-source pixels with separately attributed host/source clocks."""
    return {'frameId': 1, 'capturedAtMs': stamp+1, 'serverNowMs': stamp+2,
            'sourceFrame': {'capturedAtMs': stamp+30, 'acquiredAtMs': stamp, 'freshnessAtMs': stamp,
                            'freshnessClockKind': 'first_acquisition_qpc'},
            'clientReceivedNs': 10_000_000_000, 'transportRoundTripMs': 1,
            'frameQuality': 'usable', 'inputAvailable': True,
            'worldReadiness': {'ready': True, 'epoch': epoch},
            'frameWorldReadiness': {'ready': True, 'epoch': epoch},
            'motionEvidence': {'status': status, 'method': MOTION_METHOD,
                               'spaceKeyMatched': status in ('fly', 'climb'), 'xKeyMatched': status == 'climb'}}


def proposal(keys=(), request_id='noop', accepted=True, dx=0):
    """Only server acceptance counts toward a no-op interval."""
    return {'acceptance': {'type': 'accepted' if accepted else 'rejected', 'requestId': request_id},
            'steps': [{'keys': list(keys), 'mouseDx': dx, 'mouseDy': 0, 'durationMs': 50}]}


def recovery(threshold=1):
    """Start one explicit navigation goal in a test-only bridge lease."""
    value = NavigationIdleRecovery(threshold)
    value.begin_lease('test-lease')
    value.set_goal(0, None, 'ground-navigation')
    return value


def trigger(value, start=0):
    """Supply a continuous accepted no-op interval without wall-clock waiting."""
    result = None
    for tick in range(5):
        result = value.proposal(proposal(), frame(), start+tick*.25, True)
    return result


def released():
    """A release invalidates old source observations and returns the new readiness epoch."""
    return {'type': 'released', 'serverNowMs': 1010, 'worldReadiness': {'ready': False, 'epoch': 1}}


class RecoveryTests(unittest.TestCase):
    def test_disabled_and_non_navigation_goals_do_not_trigger(self):
        value = recovery(None)
        for tick in range(100):
            self.assertIsNone(value.proposal(proposal(), frame(), tick*.25, True))
        for intent in ('unspecified', 'stationary'):
            value = recovery()
            value.set_goal(1, 'new-goal', intent)
            self.assertIsNone(trigger(value))
            self.assertEqual(value.attempts, 0)

    def test_normal_and_confirmed_climb_qualify_but_fly_unknown_and_unavailable_do_not(self):
        for motion, expected in [('normal', True), ('climb', True), ('fly', False), ('unknown', False)]:
            item = frame(status=motion)
            self.assertEqual(eligible_frame(item, item, 10, 10_010_000_000, 150, CAPABILITY), expected)
        item = frame()
        item['motionEvidence']['xKeyMatched'] = True  # Existing native Normal semantics only require absent Space.
        self.assertTrue(eligible_frame(item, item, 10, 10_010_000_000, 150, CAPABILITY))
        for changes in ({'motionEvidence': {}}, {'frameWorldReadiness': {'ready': False, 'epoch': 0}},
                        {'worldReadiness': {'ready': True, 'epoch': 1}}, {'inputAvailable': False},
                        {'frameQuality': 'allWhite'}, {'clientReceivedNs': 9_000_000_000}):
            item = dict(frame(), **changes)
            self.assertFalse(eligible_frame(item, item, 10, 10_010_000_000, 150, CAPABILITY))
        self.assertFalse(eligible_frame(frame(), frame(), 10, 10_010_000_000, 150, {}))

    def test_ineligible_rejected_camera_and_acceptance_gaps_break_the_streak(self):
        for result, eligible in [(proposal(), False), (proposal(accepted=False), True), (proposal(dx=2), True)]:
            value = recovery()
            value.proposal(proposal(), frame(), 0, True)
            value.proposal(result, frame(), .5, eligible)
            self.assertIsNone(value.proposal(proposal(), frame(), 1, True))
            self.assertEqual(value.noops, 1)
        value = recovery()
        value.proposal(proposal(), frame(), 0, True)
        self.assertIsNone(value.proposal(proposal(), frame(), 2, True))
        self.assertEqual(value.noops, 1)

    def test_one_reset_releases_before_reset_and_stays_latched_across_pause_goal_and_lease(self):
        value = recovery()
        order = []
        event = value.execute(trigger(value), lambda: (order.append('release'), released())[1],
                              lambda: order.append('reset'), lambda: order.append('discard'), lambda: True)
        self.assertEqual(order, ['release', 'discard', 'reset'])
        self.assertEqual(event['outcome'], 'reset')
        self.assertFalse(value.armed)
        value.interrupt('userPause')
        value.set_goal(1, 'next', 'ground-navigation')
        value.begin_lease('next-bridge')
        self.assertIsNone(trigger(value, 2))
        self.assertEqual((value.attempts, value.resets), (1, 1))
        self.assertEqual(value.post_reset_noops, 5)

    def test_release_failure_does_not_reset_or_rearm(self):
        value = recovery()
        reset, discard = Mock(), Mock()
        result = value.execute(trigger(value), Mock(side_effect=OSError('broken pipe')), reset, discard, lambda: True)
        self.assertEqual(result['outcome'], 'releaseFailed')
        self.assertFalse(value.armed)
        reset.assert_not_called()
        discard.assert_not_called()
        self.assertIsNone(trigger(value, 2))

    def test_malformed_release_is_not_an_acknowledged_reset(self):
        for response in ({'type': 'rejected'}, dict(released(), serverNowMs=float('nan')),
                         dict(released(), worldReadiness={}), dict(released(), serverNowMs=-1)):
            value, reset = recovery(), Mock()
            result = value.execute(trigger(value), lambda: response, reset, Mock(), lambda: True)
            self.assertEqual(result['outcome'], 'releaseFailed')
            reset.assert_not_called()

    def test_pending_control_before_and_after_release_wins(self):
        for checks, expected, release_count in [([False], 'supersededBeforeRelease', 0),
                                                ([True, False], 'supersededAfterRelease', 1)]:
            value, release, reset = recovery(), Mock(return_value=released()), Mock()
            event = value.execute(trigger(value), release, reset, Mock(), Mock(side_effect=checks))
            self.assertEqual(event['outcome'], expected)
            self.assertEqual(release.call_count, release_count)
            reset.assert_not_called()

    def test_post_release_barrier_rejects_pre_release_source_even_with_new_host_capture(self):
        value = recovery()
        value.execute(trigger(value), released, Mock(), Mock(), lambda: True)
        for item, fresh in [(frame(1010, 1), True), (frame(1009, 1), True), (frame(1011, 0), True),
                            (frame(1011, 1), False)]:
            item['capturedAtMs'] = 1100
            self.assertFalse(value.allows_frame(item, item, fresh))
        item = frame(1011, 1)
        self.assertTrue(value.allows_frame(item, item))
        self.assertIsNone(value.barrier)

    def test_only_matched_later_directional_receipt_rearms(self):
        value = recovery()
        value.proposal(proposal(['W'], 'old'), frame(), 0, True)
        value.execute(trigger(value, 1), released, Mock(), Mock(), lambda: True)
        for request_id, keys, started in [('old', ['W'], 1011), ('new', [], 1012),
                                         ('new', ['W'], 1009), ('new', ['W', 'S'], 1013)]:
            value.proposal(proposal(['W'], 'new'), frame(), 3, True)
            self.assertIsNone(value.receipt({'requestId': request_id,
                                            'appliedSteps': [{'keys': keys, 'startedAtMs': started}]}))
            self.assertFalse(value.armed)
        value.proposal(proposal(['W'], 'new'), frame(), 4, True)
        event = value.receipt({'requestId': 'new', 'appliedSteps': [{'keys': ['W'], 'startedAtMs': 1014}]})
        self.assertEqual(event['type'], 'navigationIdleRearmed')
        self.assertEqual(event['releaseToMovementDispatchMs'], 4)
        self.assertTrue(value.armed)
        self.assertIsNotNone(trigger(value, 5))

    def test_camera_only_or_wrong_goal_movement_does_not_rearm(self):
        value = recovery()
        value.execute(trigger(value), released, Mock(), Mock(), lambda: True)
        value.proposal(proposal(dx=10, request_id='camera'), frame(), 2, True)
        self.assertIsNone(value.receipt({'requestId': 'camera', 'appliedSteps': [{'keys': [], 'startedAtMs': 1011}]}))
        value.proposal(proposal(['W'], 'walk'), frame(), 3, True)
        value.set_goal(1, 'new-goal', 'unspecified')
        self.assertIsNone(value.receipt({'requestId': 'walk', 'appliedSteps': [{'keys': ['W'], 'startedAtMs': 1012}]}))
        self.assertFalse(value.armed)


class GoalIntentTests(unittest.TestCase):
    def test_initial_and_new_goal_intents_are_versioned_and_new_omitted_intent_is_exempt(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime.threading, 'Thread'):
            control = runtime.ResidentControl(Path(directory)/'control.json', Path(directory)/'status.json', 'c'*32)
            control.set_initial_goal({}, 'ground-navigation')
            self.assertEqual(control.goal_state()['goalIntent'], 'ground-navigation')
            request = {'command': 'run', 'goalRequestId': 'a'*32,
                       'goalEmbedding': str(Path(directory)/'next.json')}
            control._observe(request, None)
            policy = SimpleNamespace(set_goal=Mock(), metadata={'goal': {}})
            runtime.apply_pending_goal(control, policy, lambda: None)
            self.assertEqual(control.goal_state()['policyGoalVersion'], 1)
            self.assertEqual(control.goal_state()['goalIntent'], 'unspecified')
            control._observe(dict(request, goalIntent='ground-navigation'), None)
            self.assertEqual(control.snapshot()[0], 'pause')
            self.assertIn('cannot change its intent', control.goal_state()['goalError'])

    def test_cli_preserves_intent_on_pause_but_does_not_inherit_it_for_new_goal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'control.json'
            runtime.atomic_json(path, {'version': 1, 'runId': 'c'*32, 'command': 'run'})
            def command(*arguments):
                with patch.object(sys, 'argv', ['control_resident.py', '--file', str(path), *arguments]), \
                        redirect_stdout(io.StringIO()):
                    control_resident.main()
                return json.loads(path.read_text())
            first = command('--goal-embedding', str(Path(directory)/'goal.json'), '--goal-intent', 'ground-navigation')
            paused = command('--command', 'pause')
            self.assertEqual(paused['goalIntent'], 'ground-navigation')
            self.assertEqual(paused['goalRequestId'], first['goalRequestId'])
            new = command('--goal-embedding', first['goalEmbedding'])
            self.assertEqual(new['goalIntent'], 'unspecified')
            self.assertNotEqual(new['goalRequestId'], first['goalRequestId'])

    def test_cli_defaults_disabled_and_rejects_unqualified_reset(self):
        args = client.parse_arguments(['--output', 'unused.json'])
        self.assertIsNone(args.navigation_idle_reset_seconds)
        self.assertEqual(args.goal_intent, 'unspecified')
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            client.parse_arguments(['--output', 'unused.json', '--navigation-idle-reset-seconds', '8'])


class RecoveryEpisodeTests(unittest.TestCase):
    def test_actual_episode_resets_once_and_does_not_infer_from_racing_old_source(self):
        class FakeBridge:
            """Synthetic world stream that deliberately republishes old source pixels after release."""
            def __init__(self):
                self.hello = {'sessionId': 'test', 'inputEnabled': True, 'allowedKeys': ['W'],
                              'supportsRelease': True, 'motionEvidence': CAPABILITY,
                              'worldReadiness': {'version': 1, 'requiredForInput': True}}
                self.handle = SimpleNamespace(close=lambda: None)
                self.started, self.count, self.epoch = time.perf_counter(), 0, 0
                self.actions, self.stale_ids, self.releases = [], [], 0
                self.stale_remaining = 0
                self.cutoff = None
                self.last_action = None

            def stamp(self):
                return 1000 + (time.perf_counter()-self.started)*1000

            def request(self, command, **kwargs):
                if command == 'stop':
                    return {'type': 'stopped', 'receipts': []}, b''
                if command == 'action':
                    self.actions.append(kwargs['frameId'])
                    self.last_action = kwargs['requestId']
                    return {'type': 'accepted', 'requestId': kwargs['requestId']}, b''
                if command == 'release':
                    self.releases += 1
                    self.epoch += 1
                    self.cutoff, self.stale_remaining = self.stamp(), 3
                    return {'type': 'released', 'serverNowMs': self.cutoff,
                            'receipts': [{'requestId': self.last_action, 'modelId': 'open-p2p', 'appliedSteps': []}],
                            'worldReadiness': {'ready': False, 'epoch': self.epoch}}, b''
                self.count += 1
                stamp = self.stamp()
                source_stamp = stamp-3
                if self.stale_remaining:
                    self.stale_remaining -= 1
                    source_stamp = self.cutoff-1
                    self.stale_ids.append(self.count)
                metadata = frame(source_stamp, self.epoch, 'climb')
                metadata.update(type='frame', frameId=self.count, capturedAtMs=stamp-1, serverNowMs=stamp,
                                width=2, height=2, sourceWidth=2, sourceHeight=2, receipts=[])
                return metadata, self.count.to_bytes(4, 'little') + bytes(range(8))

        class FakePolicy:
            """Keep an opaque graph/model identity unchanged across reset, with no GPU dependency."""
            execution_feedback = True
            metadata = {'synthetic': True}

            def __init__(self):
                self.images, self.resets, self.pending = [], 0, False
                self.graph = object()

            def predict(self, image, size):
                self.images.append(int.from_bytes(image[:4], 'little'))
                self.pending = True
                return dict(parseValid=True, fullActionMs=0, steps=proposal()['steps'])

            def finish_action(self, accepted):
                self.pending = False

            def reset(self):
                if self.pending:
                    raise AssertionError('Reset interleaved with a pending prediction')
                self.resets += 1

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'report.json'
            args = client.parse_arguments(['--model', 'open-p2p', '--source', 'fake', '--checkpoint', 'fake',
                    '--cuda-graph', '--p2p-fast-start', '--p2p-execution-feedback', '--enable-input',
                    '--goal-intent', 'ground-navigation', '--navigation-idle-reset-seconds', '1',
                    '--seconds', '1.45', '--fps', '100', '--decision-hz', '100', '--soft-cadence',
                    '--max-observation-age-ms', '500', '--output', str(output)])
            bridge, policy = FakeBridge(), FakePolicy()
            graph = policy.graph
            with patch.object(client, 'Bridge', return_value=bridge), redirect_stdout(io.StringIO()), \
                    patch.dict(sys.modules, {'PIL': SimpleNamespace(Image=SimpleNamespace(frombytes=lambda *args: args[2]))}):
                self.assertEqual(client.run_episode(args, policy), 0)
            result = json.loads(output.read_text())
            self.assertEqual(bridge.releases, 1)
            self.assertEqual(policy.resets, 1)
            self.assertIs(policy.graph, graph)
            self.assertTrue(bridge.stale_ids)
            self.assertFalse(set(bridge.stale_ids) & set(policy.images))
            self.assertFalse(set(bridge.stale_ids) & set(bridge.actions))
            self.assertEqual(result['navigationIdleRecoveryEvents'][0]['outcome'], 'reset')
            self.assertEqual(result['navigationIdleRecoveryEvents'][0]['motionEvidence']['status'], 'climb')
            self.assertGreater(result['navigationIdleRecovery']['postResetAcceptedNoops'], 0)


if __name__ == '__main__':
    unittest.main()
