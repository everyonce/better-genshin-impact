"""Stall and escape evidence failures on inert pose/receipt sequences."""
import math
import unittest

from hybrid_navigation import HybridNavigation, START
from test_hybrid_navigation import capability, frame, proposal


class HybridRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.nav = HybridNavigation(capability())
        for i in range(3):
            self.nav.prepare(frame(i+1, (i+1)*100))

    def choose(self, at, point=START, yaw=47, source_stamp=None):
        item = frame(at, at, point, yaw=yaw, heading=yaw)
        if source_stamp is not None:
            item['sourceFrame']['timestamp100ns'] = source_stamp
        self.nav.prepare(item)
        return self.nav.choose(item, proposal())['step']['keys']

    def hold(self, at, end, *keys, dx=0, dy=0, tag=''):
        self.nav.receipt(dict(requestId=f'{at}-{keys}-{tag}', endedAtMs=end,
                              appliedSteps=[dict(startedAtMs=at, keys=list(keys), mouseDx=dx, mouseDy=dy)]))

    def stall(self):
        for t in range(400, 2400, 100):
            self.assertEqual(self.choose(t), ['W'])
            self.hold(t+20, t+95, 'W')
        self.assertEqual(self.choose(2400), ['S'])

    def test_overlap_chord_camera_or_nonforward_holds_cannot_make_a_stall(self):
        for t in range(400, 2400, 100):
            self.choose(t)
        self.hold(1200, 1550, 'W')
        self.hold(1250, 1600, 'W')  # 400 ms of distinct W, not 700.
        self.hold(1600, 1750, 'S')
        self.hold(1750, 1900, 'W', 'D')
        self.hold(1900, 2100, 'W', dx=30)
        self.hold(2100, 2300, 'W', dy=10)
        self.assertEqual(self.choose(2400), ['W'])
        self.assertEqual(self.nav.total_recoveries, 0)

    def test_repeated_source_timestamp_during_stall_window_invalidates_evidence(self):
        self.hold(400, 2300, 'W')
        for t in range(400, 2500, 100):
            self.choose(t, source_stamp=1300*10000 if t == 1400 else t*10000)
        self.assertEqual(self.nav.phase, 'walking')

    def test_missing_observations_or_yaw_swing_preclude_stationary_evidence(self):
        self.hold(400, 5300, 'W')
        for t in range(400, 5500, 100):
            if t in (1700, 1800):
                continue
            self.choose(t, yaw=55 if t in (3300, 4800) else 47)
        self.assertEqual(self.nav.phase, 'walking')

    def test_leaving_and_returning_to_same_pose_is_not_a_continuous_stall(self):
        self.hold(400, 2300, 'W')
        for t in range(400, 2500, 100):
            point = (START[0]-1, START[1]-1) if 1200 <= t <= 1600 else START
            self.choose(t, point)
        self.assertEqual(self.nav.total_recoveries, 0)

    def test_side_hold_and_signed_clearance_are_both_required(self):
        self.nav.first_recovery_side = 'D'
        self.stall()
        self.hold(2420, 2660, 'S')
        self.assertEqual(self.choose(2700), ['D'])
        self.nav.interrupt('hybridStalePose')
        self.assertEqual(self.nav.phase, 'recovering')
        # An applied strafe cannot count backward displacement or displacement
        # toward the opposite side as clearance.
        yaw = math.radians(47)
        wrong_side = START[0]-2*math.sin(yaw), START[1]+2*math.cos(yaw)
        clear = START[0]+2*math.sin(yaw), START[1]-2*math.cos(yaw)
        self.assertEqual(self.choose(3000, clear), ['D'])
        self.hold(2720, 3020, 'D')
        self.assertEqual(self.choose(3100, wrong_side), ['D'])
        self.assertEqual(self.choose(3200, clear), ['W'])

    def test_unconfirmed_clearance_and_missing_receipts_stop_within_a_budget(self):
        self.stall()
        self.hold(2430, 2670, 'S')
        self.assertEqual(self.choose(2700), ['A'])
        self.hold(2720, 3620, 'A')
        with self.assertRaisesRegex(RuntimeError, 'lateral_clearance_unverified'):
            self.choose(3700)

    def test_missing_terminal_retreat_cannot_authorize_a_sidestep(self):
        self.stall()
        self.hold(2420, 2490, 'S')
        self.hold(2450, 2520, 'S')
        for t in (2500, 2600, 2700):
            self.assertEqual(self.choose(t), ['S'])
        for t in (2800, 3700):
            self.assertEqual(self.choose(t), [])
        with self.assertRaisesRegex(RuntimeError, 'obstacle_recovery_deadline'):
            self.choose(6100)

    def test_post_climb_gate_keeps_route_epoch_and_shared_attempt_budget(self):
        proof = dict(climbAttempt=1, dropRequestId='synthetic-x', dropFrameId=500, dropEndedAtMs=610,
                     cleanupReleaseAtMs=630, exitFrameIds=[710, 800], resumeFrameId=800,
                     resumeAtMs=800, resumeSourceId=8_000_000, sourceEpoch='capture-a', resumeWorldEpoch=3)
        for case, failure in [('epoch', 'climb_resume_world_epoch_changed'),
                              ('corridor', 'outside_fixed_courtyard_corridor'),
                              ('budget', 'obstacle_recovery_exhausted')]:
            with self.subTest(case=case):
                nav = HybridNavigation(capability())
                nav.latch_climb_exit(proof)
                self.assertIsNone(nav.pending_climb_exit)
                for stamp in (100, 200, 300):
                    nav.prepare(frame(stamp, stamp))
                nav.recovery_attempts = 2 if case == 'budget' else 0
                nav.latch_climb_exit(proof)
                post = frame(900, 900, (START[0]+20, START[1]) if case == 'corridor' else START,
                             frameWorldReadiness=dict(ready=True, epoch=4 if case == 'epoch' else 3))
                with self.assertRaisesRegex(RuntimeError, failure):
                    nav.prepare(post)
                self.assertEqual(nav.selections, {})


if __name__ == '__main__':
    unittest.main()
