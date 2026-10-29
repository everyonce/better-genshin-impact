"""Inert stair-post passage, waypoint steering and invalidation scenarios."""
from contextlib import redirect_stderr
import io
import math
import unittest

from hybrid_navigation import HybridNavigation
from hybrid_routes import COURTYARD_ROUTE, STAIR_POST_ROUTE, route_heading, route_points
from stream_client import parse_arguments
from test_hybrid_navigation import capability, frame, proposal


class HybridBypassTests(unittest.TestCase):
    def setUp(self):
        self.start, self.end = route_points(STAIR_POST_ROUTE)
        self.length = math.dist(self.start, self.end)
        self.nav = HybridNavigation(capability(), STAIR_POST_ROUTE, remember_bypass=True)
        self.at = 0
        self.world_epoch = 1
        for _ in range(3):
            self.observe(self.start)

    def point(self, advance, left=0):
        """Choose an actual world point relative to the published stair-post segment."""
        ux, uy = ((self.end[i] - self.start[i])/self.length for i in (0, 1))
        return self.start[0] + advance*ux + left*uy, self.start[1] + advance*uy - left*ux

    def observe(self, point, gap=100, stamp=None, yaw=None):
        """One monotone native frame carrying the original bridge's integer anchor bearings."""
        self.at += gap
        target = self.nav.bypass.waypoint or self.nav.target
        measured = dict(x=point[0], y=point[1])
        data = frame(self.at, self.at, point, yaw=route_heading(measured, target) if yaw is None else yaw,
                     frameWorldReadiness=dict(ready=True, epoch=self.world_epoch,
                                              sourceFrame=dict(captureEpoch='capture-a')))
        pose = data['navigationPose']
        native_a, native_b = route_points(COURTYARD_ROUTE)
        pose.update(headingToStartDegrees=int(route_heading(pose, native_a)),
                    headingToEndDegrees=int(route_heading(pose, native_b)))
        if stamp is not None:
            data['sourceFrame']['timestamp100ns'] = stamp
        state = self.nav.prepare(data)
        choice = self.nav.choose(data, proposal(['W'])) if state is None else None
        return state, choice

    def hold(self, key, start, end):
        """Deliver a terminal receipt from this controller's synthetic lease."""
        self.nav.receipt(dict(requestId=f'{key}-{start}', endedAtMs=end,
                              appliedSteps=[dict(startedAtMs=start, keys=[key], mouseDx=0, mouseDy=0)]))

    def escape(self, forward_receipt=True, climb=False):
        """Stand at contact with verified W, retreat and traverse the commanded clear side."""
        contact, p, q, r = self.point(4), self.point(3), self.point(3, 1.8), self.point(6, 1.1)
        if climb:
            self.nav.interrupt('climbRecovery')
            self.nav.latch_climb_exit(dict(sourceEpoch='capture-a', resumeWorldEpoch=1, climbAttempt=1,
                dropRequestId='drop-x', dropFrameId=self.at+1, dropEndedAtMs=self.at+10,
                cleanupReleaseAtMs=self.at+20, exitFrameIds=[self.at+30, self.at+50],
                resumeFrameId=self.at+50, resumeAtMs=self.at+50, resumeSourceId=(self.at+50)*10000))
        else:
            for _ in range(20):
                self.observe(contact)
                self.hold('W', self.at+5, self.at+85)
        self.assertEqual(self.observe(contact)[1]['reason'], 'obstacleRetreat')
        self.hold('S', self.at+5, self.at+215)
        self.assertEqual(self.observe(p, gap=220)[1]['reason'], 'obstacleSidestep')
        self.hold('A', self.at+5, self.at+215)
        self.observe(q, gap=220)
        self.assertEqual(self.nav.phase, 'walking')
        if forward_receipt:
            self.hold('W', self.at+5, self.at+95)
        self.observe(r)
        return p, q, r

    def finish_leg(self, destination):
        self.assertEqual(self.observe(destination)[0], 'releaseRequired')
        self.endpoint_release()
        for _ in range(3):
            result = self.observe(destination)[0]
        self.assertEqual(result, 'endpointVerified')

    def endpoint_release(self):
        """The native controller increments the readiness epoch when acknowledging release."""
        self.world_epoch += 1
        gate = dict(ready=False, epoch=self.world_epoch, reason='client_release',
                    sourceFrame=dict(captureEpoch='capture-a'))
        self.nav.released(dict(type='released', serverNowMs=self.at+5, worldReadiness=gate))
        return gate

    def test_verified_pass_teaches_then_replays_reverse_and_forward(self):
        p, q, r = self.escape()
        self.assertIsNone(self.nav.bypass.learned)
        self.finish_leg(self.end)
        events = self.nav.drain_events()
        self.assertEqual([e['type'] for e in events[-2:]], ['hybridEndpointVerified', 'hybridBypassLearned'])
        self.assertEqual(events[-1]['completedLegs'], 1)
        self.assertEqual(events[-1]['triggerKind'], 'stationaryForward')
        self.assertEqual([(o['x'], o['y']) for o in events[-1]['points']], [p, q, r])
        for initial, steps, final in ((self.end, (r, q, p), self.start), (self.start, (p, q, r), self.end)):
            _, selection = self.observe(initial)
            for i, waypoint in enumerate(steps):
                self.assertEqual(selection['steeringPoint'], dict(x=waypoint[0], y=waypoint[1], kind='bypass'))
                self.assertEqual(selection['bypassPointIndex'], i)
                _, selection = self.observe(waypoint)
            self.assertEqual(selection['steeringPoint'], dict(x=final[0], y=final[1], kind='endpoint'))
            self.finish_leg(final)

    def test_no_forward_hold_prevents_learning_despite_motion_and_endpoint(self):
        self.escape(forward_receipt=False)
        self.finish_leg(self.end)
        self.assertIsNone(self.nav.bypass.learned)

    def test_confirmed_climb_exit_teaches_only_after_a_separate_verified_pass(self):
        self.escape(climb=True)
        self.assertIsNone(self.nav.bypass.learned)
        self.finish_leg(self.end)
        event = self.nav.events[-1]
        self.assertEqual((event['type'], event['triggerKind']), ('hybridBypassLearned', 'climbDrop'))
        handoff = next(e for e in self.nav.events if e['type'] == 'hybridClimbRecovery')
        self.assertEqual((handoff['climbExit']['dropRequestId'], handoff['frameId']),
                         ('drop-x', event['contact']['frameId']))

    def test_observation_gap_invalidates_pending_pass_even_if_endpoint_later_verifies(self):
        self.escape()
        self.observe(self.point(7), gap=300)
        self.finish_leg(self.end)
        self.assertIsNone(self.nav.bypass.learned)
        self.assertIn('sourceDiscontinuity', [e.get('reason') for e in self.nav.events])

    def test_own_release_at_five_hz_preserves_completed_pass_until_reconfirmation(self):
        self.escape()
        self.assertEqual(self.observe(self.end)[0], 'releaseRequired')
        release = self.endpoint_release()
        bypass = self.nav.bypass
        # Frame 377 in post-walk-31 carried the new current gate and old valid payload.
        status = dict(worldReadiness=release, inputAvailable=False, serverNowMs=self.at+38,
                      sourceFrame=dict(captureEpoch='capture-a'))
        self.assertTrue(bypass.release_wait(self.nav, status, 'worldReadiness'))
        # The next recorded payload was confirming while the current gate was already ready.
        status.update(worldReadiness=dict(release, ready=True, reason='world_ready'),
                      frameWorldReadiness=dict(release, reason='world_confirming'), serverNowMs=self.at+95)
        self.assertTrue(bypass.release_wait(self.nav, status, 'worldReadiness'))
        self.assertTrue(bypass.release_wait(self.nav, status, 'frameWorldReadiness'))
        self.assertEqual(self.observe(self.end, gap=400)[0], 'verifyingEndpoint')
        self.assertFalse(bypass.release_wait(self.nav, status, 'worldReadiness'))
        self.observe(self.end, gap=200)
        self.assertEqual(self.observe(self.end, gap=200)[0], 'endpointVerified')
        self.assertIsNotNone(bypass.learned)
        self.assertEqual(self.nav.events[-2]['releaseEpoch'], release['epoch'])

    def test_unrelated_readiness_generations_capture_and_late_release_still_discard(self):
        self.escape()
        self.assertEqual(self.observe(self.end)[0], 'releaseRequired')
        release = self.endpoint_release()
        for gate in (dict(release, epoch=self.world_epoch+1), dict(release, reason='game_window_unfocused'),
                     dict(release, sourceFrame=dict(captureEpoch='replacement'))):
            status = dict(worldReadiness=gate, inputAvailable=False, serverNowMs=self.at+40)
            self.assertFalse(self.nav.bypass.release_wait(self.nav, status, 'worldReadiness'))
        self.world_epoch += 1
        for _ in range(3):
            self.observe(self.end, gap=200)
        self.assertIsNone(self.nav.bypass.learned)

    def test_reconfirmation_time_budget_cannot_hide_an_unbounded_pose_gap(self):
        self.escape()
        self.assertEqual(self.observe(self.end)[0], 'releaseRequired')
        self.endpoint_release()
        self.observe(self.end, gap=1100)
        self.observe(self.end)
        self.observe(self.end)
        self.assertIsNone(self.nav.bypass.learned)

    def test_repeated_source_stamp_invalidates_pass(self):
        self.escape()
        self.observe(self.point(7), stamp=self.at*10000)
        self.finish_leg(self.end)
        self.assertIsNone(self.nav.bypass.learned)

    def test_new_stall_on_replay_forgets_waypoints_and_invokes_ordinary_recovery(self):
        self.escape()
        self.finish_leg(self.end)
        self.observe(self.end)
        for _ in range(23):
            _, selected = self.observe(self.end)
            if selected['reason'] == 'obstacleRetreat':
                break
            self.hold('W', self.at+5, self.at+85)
        self.assertEqual(self.nav.phase, 'recovering')
        self.assertIsNone(self.nav.bypass.learned)
        self.assertIsNone(self.nav.bypass.contact)
        self.assertIn('newStall', [e.get('reason') for e in self.nav.events])

    def test_control_interruption_or_lease_replacement_discards_learned_route(self):
        self.escape()
        self.finish_leg(self.end)
        self.assertIsNone(HybridNavigation(capability(), STAIR_POST_ROUTE, True).bypass.learned)
        self.nav.interrupt('goalChange')
        self.assertIsNone(self.nav.bypass.learned)

    def test_climb_during_replay_cannot_reteach_a_partial_path_after_interrupt(self):
        self.escape()
        self.finish_leg(self.end)
        self.observe(self.end)
        self.nav.interrupt('climbRecovery')
        self.nav.recovery_attempts = 1
        self.nav.bypass.stalled(self.nav, 'climbDrop')
        self.assertIsNone(self.nav.bypass.contact)

    def test_flag_is_opt_in_and_stair_post_only(self):
        self.assertIsNone(HybridNavigation(capability(), STAIR_POST_ROUTE).bypass)
        with self.assertRaisesRegex(ValueError, 'stair-post'):
            HybridNavigation(capability(), COURTYARD_ROUTE, True)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_arguments(['--model', 'observe', '--remember-hybrid-bypass', '--output', 'unused.json'])

    def suspended_replay(self, acknowledge=True):
        """Start an actual taught reverse leg and enter the generic stale-frame hold."""
        self.escape()
        self.finish_leg(self.end)
        self.observe(self.end)
        self.observe(self.end)  # A qualified decision aimed at the first reverse waypoint.
        self.nav.interrupt('hybridStalePose')
        self.world_epoch += 1
        gate = dict(ready=False, epoch=self.world_epoch, reason='client_release',
                    sourceFrame=dict(captureEpoch='capture-a'))
        ack = dict(type='released', serverNowMs=self.at+100, worldReadiness=gate)
        if acknowledge:
            self.nav.bypass.acknowledge_stale_hold(self.nav, ack)
        return ack

    def test_stale_held_replay_requires_three_fresh_samples_before_same_waypoint_reuse(self):
        ack = self.suspended_replay()
        bypass = self.nav.bypass
        waypoint = bypass.waypoint
        following = tuple(a + .35*(b-a) for a,b in zip(self.end, waypoint))
        self.assertTrue(bypass.release_wait(self.nav, dict(ack, serverNowMs=self.at+110), 'worldReadiness'))
        with self.assertRaisesRegex(RuntimeError, 'suspended'):
            self.nav.choose({}, proposal())
        for gap in (260, 100, 100):
            self.assertEqual(self.observe(following, gap=gap), ('confirmingBypassReentry', None))
        self.assertIsNone(bypass.suspension)
        self.assertEqual(self.nav.events[-1]['type'], 'hybridBypassRebound')
        self.assertEqual(len(self.nav.events[-1]['samples']), 3)
        self.assertEqual(bypass.waypoint, waypoint)
        self.assertEqual(self.observe(following)[1]['bypassPointIndex'], 0)

    def test_missing_or_unrelated_stale_hold_acknowledgment_discards_replay(self):
        ack = self.suspended_replay(acknowledge=False)
        ack['worldReadiness']['epoch'] += 1
        self.nav.bypass.acknowledge_stale_hold(self.nav, ack)
        self.assertIsNone(self.nav.bypass.learned)
        self.setUp()
        self.suspended_replay(acknowledge=False)
        self.assertEqual(self.observe(self.end)[0], 'confirmingBypassReentry')
        self.assertIsNone(self.nav.bypass.learned)

    def test_unproven_lesson_cannot_be_suspended(self):
        self.escape()
        self.nav.interrupt('hybridStalePose')
        self.assertIsNone(self.nav.bypass.contact)
        self.assertIsNone(self.nav.bypass.suspension)

    def camera_hold(self, corruption='', angular_error=83):
        """Reproduce a bounded keyless turn completed after the last source pose but before release."""
        self.escape()
        self.finish_leg(self.end)
        self.observe(self.end)
        bypass = self.nav.bypass
        heading = route_heading(dict(x=self.end[0], y=self.end[1]), bypass.waypoint)
        yaw = (heading-angular_error) % 360
        _, selection = self.observe(self.end, yaw=yaw)
        step = selection['step']
        action = dict(requestId='camera', frameId=self.at, modelId='hybrid-native', step=step,
                      observedAtMs=self.at, acceptedAtMs=self.at+65, sourceEpoch='capture-a', reason=selection['reason'],
                      target=self.nav.target_name, completedLegs=self.nav.legs, bypassPointIndex=bypass.index)
        receipt = dict(requestId='camera', modelId='hybrid-native', frameId=self.at, status='completed',
                       acceptedAtMs=self.at+65, endedAtMs=self.at+169,
                       appliedSteps=[dict(startedAtMs=self.at+69, **step)])
        self.nav.interrupt('hybridStalePose')
        self.world_epoch += 1
        ack = dict(type='released', serverNowMs=self.at+250, receipts=[receipt], worldReadiness=dict(
            ready=False, reason='client_release', epoch=self.world_epoch, sourceFrame=dict(captureEpoch='capture-a')))
        if corruption == 'receiptKeys':
            receipt['appliedSteps'][0]['keys'] = ['W']
        elif corruption == 'wrongAction':
            action['requestId'] = 'another'
        elif corruption == 'otherApplied':
            self.hold('D', self.at+171, self.at+200)
        elif corruption == 'alreadyCollected':
            self.nav.receipt(receipt)
            ack['receipts'] = []
        bypass.acknowledge_stale_hold(self.nav, ack, action)
        return yaw

    def test_signed_camera_turn_joins_pure_receipt_and_stable_stationary_reentry(self):
        for source, signed_error in (('', 83), ('alreadyCollected', -83)):
            with self.subTest(source=source):
                self.setUp()
                yaw = self.camera_hold(source, signed_error)
                settled = (yaw + math.copysign(63, signed_error)) % 360
                for gap in (420, 100, 100):
                    self.assertEqual(self.observe(self.end, gap=gap, yaw=settled), ('confirmingBypassReentry', None))
                event = self.nav.events[-1]
                self.assertEqual(event['type'], 'hybridBypassRebound')
                self.assertEqual(event['cameraReceipt']['requestId'], 'camera')

    def test_anchor_camera_proof_requires_its_exact_terminal_receipt_from_reader_inbox(self):
        """R42's reader drained 517 before the empty release ACK. The earlier 513 hold overlapped."""
        bypass = self.nav.bypass
        source = 'capture-a'
        bypass.suspension = dict(target='end', leg=2, capture=source,
            anchor=dict(frameId=517, atMs=18356.6348, x=-844.88671875, y=2255.4892578125),
            facts=dict(yawDegrees=279, waypoint=dict(x=-844.791015625, y=2252.7421875), bypassPointIndex=0))
        action = dict(requestId='5455efc661614abf9a454703da511891', modelId='hybrid-native', frameId=517,
                      sourceEpoch=source, reason='nativeHeading', target='end', completedLegs=2,
                      bypassPointIndex=0, observedAtMs=18356.6348, acceptedAtMs=18430.5559,
                      step=dict(keys=[], durationMs=100, mouseDx=250, mouseDy=0))
        ack = dict(serverNowMs=18663.2916, receipts=[])
        previous = dict(requestId='9a48afdef01c49a6aeaa8228eac99417', modelId='hybrid-native', frameId=513,
                        status='replaced', acceptedAtMs=18331.074, endedAtMs=18430.5559,
                        appliedSteps=[dict(startedAtMs=18331.0921, keys=[], mouseDx=250, mouseDy=0)])
        current = dict(requestId=action['requestId'], modelId='hybrid-native', frameId=517,
                       status='completed', acceptedAtMs=18430.5559, endedAtMs=18530.8673,
                       appliedSteps=[dict(startedAtMs=18430.569, keys=[], mouseDx=250, mouseDy=0)])
        self.nav.receipt(previous)
        self.assertIsNone(bypass._camera_receipt(ack, action))
        self.nav.receipt(current)
        self.assertEqual(bypass._camera_receipt(ack, action), dict(requestId=action['requestId'],
                         frameId=517, mouseDx=250, startedAtMs=18430.569, endedAtMs=18530.8673))
        self.assertEqual(ack['receipts'], [])

    def test_unexplained_yaw_or_position_rejects_even_with_camera_on_the_lease(self):
        for reason in ('receiptKeys', 'wrongAction', 'otherApplied', 'wrongSign', 'tooFar', 'overshoot', 'translated'):
            with self.subTest(reason=reason):
                self.setUp()
                yaw = self.camera_hold(reason, angular_error=35 if reason == 'overshoot' else 83)
                change = -63 if reason == 'wrongSign' else 80 if reason == 'tooFar' else 63
                point = self.point(self.length-.5) if reason == 'translated' else self.end
                self.observe(point, gap=420, yaw=(yaw+change) % 360)
                self.assertIsNone(self.nav.bypass.learned)

    def test_stale_hold_refuses_departure_expiry_climb_and_changed_readiness(self):
        for reason in ('shift', 'late', 'world', 'climb', 'newStall'):
            with self.subTest(reason=reason):
                self.setUp()
                self.suspended_replay()
                if reason == 'shift':
                    self.observe(self.point(self.length, 2.1), gap=230)
                elif reason == 'late':
                    self.observe(self.end, gap=1800)
                elif reason == 'world':
                    self.world_epoch += 1
                    self.observe(self.end, gap=230)
                elif reason == 'newStall':
                    self.nav.bypass.stalled(self.nav)
                else:
                    self.nav.interrupt('climbRecovery')
                self.assertIsNone(self.nav.bypass.learned)
