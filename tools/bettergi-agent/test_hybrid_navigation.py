"""Inert route/receipt scenarios: no Windows input, model load, or live bridge."""
import copy
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hybrid_navigation import HybridNavigation, PROFILE, START, END


def capability():
    return dict(version=1, profileId=PROFILE, sameFrame=True, readOnly=True,
                start=dict(zip(('x', 'y'), START)), end=dict(zip(('x', 'y'), END)))


def frame(number, at, point=START, yaw=47, heading=47, **changes):
    pose = dict(state='valid', frameId=number, x=point[0], y=point[1], yawDegrees=yaw,
                positionConfidence=.996, yawConfidence=.6, layerId='City_102',
                headingToStartDegrees=(heading + 180) % 360, headingToEndDegrees=heading,
                mouseToStart=350, mouseToEnd=0)
    result = dict(frameId=number, capturedAtMs=at,
                  sourceFrame=dict(captureEpoch='capture-a', capturedAtMs=at, timestamp100ns=round(at * 10000)),
                  navigationPose=pose, motionEvidence=dict(status='normal', spaceKeyMatched=False))
    result.update(changes)
    return result


def proposal(keys=(), dx=0, dy=0):
    return dict(parseValid=True, steps=[dict(keys=list(keys), mouseDx=dx, mouseDy=dy, durationMs=100)])


class HybridNavigationTests(unittest.TestCase):
    def test_unavailable_unqualified_and_non_normal_poses_cannot_suspend_the_leg_deadline(self):
        """A lost recognition result must not turn a bounded walking leg into an indefinite wait."""
        for changes in (dict(navigationPose=dict(state='unavailable')),dict(navigationPose={}),
                        dict(motionEvidence=dict(status='climbing',spaceKeyMatched=True))):
            with self.subTest(changes=changes),patch('hybrid_navigation.time.perf_counter_ns',return_value=0):
                nav=self.ready()
            with patch('hybrid_navigation.time.perf_counter_ns',return_value=35_000_000_001):
                with self.assertRaisesRegex(RuntimeError,'leg_progress_deadline'):
                    nav.prepare(frame(4,400,**changes))

    def test_no_frame_wait_and_interrupt_do_not_renew_the_client_deadline(self):
        """The runtime can enforce the same deadline without calling prepare() at all."""
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=0):nav=self.ready()
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=20_000_000_000):
            nav.interrupt('hybridNoFrame')
            nav.check_leg_deadline()
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=35_000_000_001):
            with self.assertRaisesRegex(RuntimeError,'leg_progress_deadline'):nav.check_leg_deadline()

    def test_admission_without_a_qualified_pose_is_bounded_too(self):
        """Input remains unavailable while admission expires after thirty-five seconds."""
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=0):nav=HybridNavigation(capability())
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=35_000_000_001):
            with self.assertRaisesRegex(RuntimeError,'admission_pose_deadline'):nav.prepare(frame(1,100,navigationPose={}))
        self.assertEqual(nav.legs,0)

    def ready(self):
        nav = HybridNavigation(capability())
        for i in range(3):
            nav.prepare(frame(i + 1, 100 + i * 100))
        self.assertEqual(nav.phase, 'walking')
        return nav

    def test_noop_and_unrelated_model_keys_use_explicit_native_forward(self):
        nav = self.ready()
        for keys in ((), ('F',), ('E', 'W'), ('S',), ('SPACE',)):
            with self.subTest(keys=keys):
                original = proposal(keys)
                selection = nav.choose(frame(3, 300), original)
                self.assertEqual(selection['owner'], 'hybrid-native')
                self.assertEqual(selection['step']['keys'], ['W'])
                self.assertEqual(selection['modelSteps'], original['steps'])
                self.assertEqual(original, proposal(keys))

    def test_route_compatible_model_action_retains_its_identity_and_camera(self):
        nav = self.ready()
        selected = nav.choose(frame(3, 300), proposal(['W'], dx=2))
        self.assertEqual(selected['owner'], 'open-p2p')
        self.assertEqual(selected['step']['mouseDx'], 2)
        self.assertEqual(nav.choose(frame(3, 300), proposal(['W'], dy=20))['owner'], 'hybrid-native')

    def test_heading_correction_never_holds_forward_while_facing_off_route(self):
        nav = self.ready()
        item = frame(4, 400, yaw=0, heading=90)
        item['navigationPose']['mouseToEnd'] = 500
        nav.prepare(item)
        selected = nav.choose(item, proposal(['W']))
        self.assertEqual(selected['step'], dict(keys=[], mouseDx=350, mouseDy=0, durationMs=100))

    def test_short_holds_preserve_one_shot_native_and_model_camera_deltas(self):
        """Faster feedback must not shrink or multiply a selected relative mouse movement."""
        for hold in (50,60):
            with self.subTest(hold=hold):
                nav=HybridNavigation(capability(),action_hold_ms=hold)
                for number in range(1,4):nav.prepare(frame(number,number*100))
                original=proposal(['W'],dx=2)
                selected=nav.choose(frame(3,300),original)
                self.assertEqual(selected['step'],dict(keys=['W'],mouseDx=2,mouseDy=0,durationMs=hold))
                self.assertEqual(original,proposal(['W'],dx=2))
                turned=frame(4,400,yaw=0,heading=90)
                turned['navigationPose']['mouseToEnd']=500
                nav.prepare(turned)
                self.assertEqual(nav.choose(turned,proposal(['W']))['step'],
                    dict(keys=[],mouseDx=350,mouseDy=0,durationMs=hold))

    def test_short_hold_choice_never_extends_the_hundred_millisecond_ceiling(self):
        """Only the two bounded trial holds and the unchanged legacy duration are supported."""
        for hold in (True,50.0,0,49,61,101,1000):
            with self.subTest(hold=hold),self.assertRaises(ValueError):
                HybridNavigation(capability(),action_hold_ms=hold)

    def test_three_polls_of_one_frame_cannot_confirm_start(self):
        nav = HybridNavigation(capability())
        item = frame(1, 100)
        for _ in range(4):
            nav.prepare(item)
        self.assertEqual(nav.phase, 'admitting')
        self.assertEqual(len(nav.samples), 1)

    def test_newer_climb_or_missing_pose_invalidates_an_older_correction(self):
        item = frame(4, 400)
        self.assertTrue(HybridNavigation.latest_pose_usable(item))
        item['motionEvidence']['status'] = 'climb'
        self.assertFalse(HybridNavigation.latest_pose_usable(item))
        item['motionEvidence']['status'] = 'normal'
        item['navigationPose']['frameId'] = 3
        self.assertFalse(HybridNavigation.latest_pose_usable(item))
        item['navigationPose'] = None
        self.assertFalse(HybridNavigation.latest_pose_usable(item))

    def test_endpoint_requires_release_then_three_distinct_fresh_stable_poses(self):
        nav = self.ready()
        self.assertEqual(nav.prepare(frame(4, 1000, END)), 'releaseRequired')
        self.assertEqual(nav.legs, 0)
        with self.assertRaises(RuntimeError):
            nav.released(dict(type='unknown', serverNowMs=1010))
        nav.released(dict(type='released', serverNowMs=1010))
        self.assertEqual(nav.prepare(frame(5, 1050, END)), 'waitingAfterRelease')
        for i, at in enumerate((1100, 1200, 1300), 6):
            nav.prepare(frame(i, at, END))
        self.assertEqual(nav.legs, 1)
        self.assertEqual(nav.target_name, 'start')
        event = nav.drain_events()[-1]
        self.assertEqual(len(event['samples']), 3)
        self.assertTrue(all(s['atMs'] >= 1090 for s in event['samples']))

    def test_world_reconfirmation_preserves_endpoint_release_barrier(self):
        nav = self.ready()
        nav.prepare(frame(4, 1000, END))
        nav.released(dict(type='released', serverNowMs=1010))
        nav.interrupt('worldTransition')
        self.assertEqual(nav.phase, 'verifying')
        self.assertEqual(nav.release_at, 1010)

    def test_stream_admits_then_verifies_endpoint_and_preserves_action_attribution(self):
        import stream_client as client
        from test_stream_segments import ContinuousBridge, ContinuousPolicy

        class RouteBridge(ContinuousBridge):
            def __init__(self):
                super().__init__('synthetic')
                self.hello.update(navigationGuidance=capability(), supportsRelease=True, allowedKeys=['W', 'A', 'S', 'D'])
                self.hello['worldReadiness'] = dict(version=1, requiredForInput=True)
                self.actions = 0

            def request(self, command, **kwargs):
                if command == 'enableNavigationGuidance':
                    return dict(type='navigationGuidance', enabled=True, capability=capability()), b''
                if command == 'release':
                    self.commands.append((command, kwargs))
                    return dict(type='released', serverNowMs=(time.perf_counter()-self.origin)*1000,
                        worldReadiness=dict(ready=True, epoch=1), inputAvailable=True), b''
                if command == 'action':
                    self.commands.append((command, kwargs))
                    self.actions += 1
                    return dict(type='accepted', requestId=kwargs['requestId']), b''
                value, pixels = super().request(command, **kwargs)
                if command == 'frame':
                    point = END if self.actions >= 2 else START
                    value.update(frame(value['frameId'], value['capturedAtMs'], point))
                    value['sourceFrame']['acquiredAtMs'] = value['serverNowMs']
                    value.update(worldReadiness=dict(ready=True, epoch=1),
                        frameWorldReadiness=dict(ready=True, epoch=1), inputAvailable=True)
                return value, pixels

        class AlternatingPolicy(ContinuousPolicy):
            def __init__(self):
                super().__init__()
                self.commits = []

            def predict(self, image, size):
                result = super().predict(image, size)
                if self.steps == 1:
                    result['steps'][0]['keys'] = []
                return result

            def finish_action(self, committed):
                self.commits.append(committed)

        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'route.json'
            args = client.parse_arguments(['--resident', '--rdp-session-id', '3', '--model', 'open-p2p', '--source', 'synthetic',
                '--checkpoint', 'synthetic', '--cuda-graph', '--p2p-fast-start', '--seconds', '3', '--fps', '30', '--decision-hz', '10',
                '--enable-input', '--goal-intent', 'ground-navigation', '--hybrid-navigation',
                '--hybrid-legs', '1', '--output', str(output)])
            bridge, policy = RouteBridge(), AlternatingPolicy()
            with patch.object(client, 'Bridge', return_value=bridge), redirect_stdout(io.StringIO()):
                self.assertEqual(client.run_episode(args, policy), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report['endReason'], 'hybridLegLimit')
            self.assertEqual(report['hybridNavigation']['completedLegs'], 1)
            self.assertEqual(policy.commits, [False, True])
            actions = [item for name, item in bridge.commands if name == 'action']
            self.assertEqual([item['modelId'] for item in actions], ['hybrid-native', 'open-p2p'])
            self.assertEqual([name for name, _ in bridge.commands].count('stop'), 1)
            events = report['hybridNavigationEvents']
            self.assertEqual([item['type'] for item in events], ['hybridStartVerified', 'hybridEndpointVerified'])
            self.assertEqual(len(events[-1]['samples']), 3)

    def test_bad_pose_or_climbing_cannot_produce_a_native_navigation_action(self):
        nav = self.ready()
        bad = frame(4, 400)
        bad['navigationPose']['frameId'] = 3
        self.assertEqual(nav.prepare(bad), 'poseUnavailable')
        bad = frame(5, 500)
        bad['navigationPose']['positionConfidence'] = .5
        self.assertEqual(nav.prepare(bad), 'poseUnqualified')
        self.assertEqual(nav.prepare(frame(6, 600, motionEvidence=dict(status='climb', spaceKeyMatched=True))), 'motionNotNormal')

    def test_out_of_corridor_or_capture_replacement_stops_instead_of_steering(self):
        for item in (frame(4, 400, point=(START[0] + 30, START[1])),
                     frame(4, 400, sourceFrame=dict(captureEpoch='another-capture', capturedAtMs=400))):
            nav = self.ready()
            with self.assertRaises(RuntimeError):
                nav.prepare(item)
            self.assertEqual(nav.phase, 'failed')

    def test_no_progress_requires_applied_movement_not_accepted_actions(self):
        nav = self.ready()
        nav.receipt(dict(requestId='accepted-only', appliedSteps=[], endedAtMs=300))
        for at in range(300, 2400, 100):
            item = frame(at, at)
            nav.prepare(item)
            nav.choose(item, proposal())
        self.assertEqual(nav.total_recoveries, 0)
        receipt = dict(requestId='actual-movement', appliedSteps=[dict(startedAtMs=1500, keys=['W'])], endedAtMs=2300)
        nav.receipt(receipt)
        nav.receipt(receipt)
        item = frame(2400, 2400)
        nav.prepare(item)
        selected = nav.choose(item, proposal())
        self.assertEqual(nav.total_recoveries, 1)
        self.assertEqual(selected['step']['keys'], ['S'])
        self.assertEqual(nav.drain_events()[-1]['movementMs'], 800)
        item = frame(3000, 3000)
        nav.prepare(item)
        self.assertEqual(nav.choose(item, proposal())['step']['keys'], ['S'])

    def test_unreviewed_route_is_rejected_before_native_recognition_enable(self):
        value = capability()
        value['end']['x'] += 10
        with self.assertRaises(ValueError):
            HybridNavigation(value)

    def test_repeated_obstruction_exhausts_two_attempts_instead_of_looping_forever(self):
        nav = self.ready()
        point = START

        def choose(at):
            item = frame(at, at, point)
            nav.prepare(item)
            return nav.choose(item, proposal())['step']['keys']

        def receipt(start, end, key):
            nav.receipt(dict(requestId=f'{key}-{start}', appliedSteps=[
                dict(startedAtMs=start, keys=[key])], endedAtMs=end))

        at = 300
        for side in ('A', 'D', None):
            for t in range(at, at+2000, 100):
                choose(t)
                receipt(t+30, t+100, 'W')
            at += 2000
            if side is None:
                with self.assertRaisesRegex(RuntimeError, 'obstacle_recovery_exhausted'):
                    choose(at)
                break
            self.assertEqual(choose(at), ['S'])
            receipt(at+30, at+250, 'S')
            self.assertEqual(choose(at+300), [side])
            receipt(at+330, at+620, side)
            radians = math.radians(47)
            sign = 1 if side == 'D' else -1
            point = point[0]+sign*2*math.sin(radians), point[1]-sign*2*math.cos(radians)
            self.assertEqual(choose(at+650), ['W'])
            at += 950
        self.assertEqual(nav.total_recoveries, 2)


if __name__ == '__main__':
    unittest.main()
