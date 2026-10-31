"""Exercise surface camera-only feedback and stop behavior without connecting to a game."""
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import probe_camera_response as probe
import survey_surface_camera as survey
from navigation_profiles import SURFACE_PROFILE
from test_probe_camera_response import CameraBridge


class SurfaceCameraTests(unittest.TestCase):
    """A camera survey must stay at its declared anchor and cannot emit movement or attacks."""
    def setUp(self):
        self.bridge = CameraBridge()
        self.anchor = (-1064.62890625, 2165.9345703125)
        self.bridge.alter = lambda f: f['navigationPose'].update(x=self.anchor[0], y=self.anchor[1], layerId='MapBack_2')
        self.report = dict(observations=[], actions=[], receipts=[])

    def trial(self, **extra):
        """Use the same receipt intake as the original city calibration with an explicit surface scope."""
        return probe.Experiment(self.bridge, self.report, station=self.anchor, profile=SURFACE_PROFILE, seconds=35, **extra)

    def test_turn_uses_fresh_feedback_and_stops_at_requested_heading_without_any_keys(self):
        survey.turn_to(self.trial(), 270)
        self.assertLessEqual(abs(self.report['finalYawDegrees']-270), 3)
        self.assertGreater(len(self.report['actions']), 1)
        self.assertEqual(len(self.report['actions']), len(self.report['receipts']))
        for action in self.bridge.issued:
            step = action['steps'][0]
            self.assertEqual(step['keys'], [])
            self.assertEqual((step['durationMs'], step['mouseDy']), (100, 0))
            self.assertLessEqual(abs(step['mouseDx']), 250)

    def test_default_city_probe_does_not_silently_admit_a_surface_pose(self):
        row, _ = self.bridge.request('frame')
        row.update(clientReceivedNs=time.perf_counter_ns(), transportRoundTripMs=0, frameQuality='usable')
        self.assertFalse(probe.qualified(row))
        self.assertTrue(probe.qualified(row, SURFACE_PROFILE))
        row['navigationPose']['x'] = -1100.01
        self.assertFalse(probe.qualified(row, SURFACE_PROFILE))

    def test_measured_slow_response_reaches_north_without_twelve_tiny_corrections(self):
        self.bridge.yaw, self.bridge.sensitivity = 19.5, .1
        survey.turn_to(self.trial(), 270)
        self.assertLessEqual(abs(self.report['finalYawDegrees']-270), 3)
        self.assertLessEqual(len(self.report['actions']), 7)
        self.assertTrue(all(abs(row['degreesPerMouseUnit']-.1) < 1e-9 for row in self.report['cameraResponseUpdates']))

    def test_absent_reversed_or_extreme_camera_response_stops_after_one_pulse(self):
        for sensitivity in (0, -.1, .6):
            with self.subTest(sensitivity=sensitivity):
                self.setUp()
                self.bridge.sensitivity = sensitivity
                with self.assertRaisesRegex(ValueError, 'Camera response'):
                    survey.turn_to(self.trial(), 270)
                self.assertEqual(len(self.bridge.issued), 1)

    def test_body_drift_stops_without_another_camera_pulse(self):
        trial = self.trial()
        trial.pulse(-75)
        self.anchor = (self.anchor[0]+.4, self.anchor[1])
        with self.assertRaisesRegex(ValueError, 'body position changed'):
            trial.pulse(-75)
        self.assertEqual(len(self.bridge.issued), 1)

    def test_operator_stop_is_checked_before_dispatch_and_during_frame_waits(self):
        guard = Mock(side_effect=RuntimeError('operatorStop'))
        with self.assertRaisesRegex(RuntimeError, 'operatorStop'):
            survey.turn_to(self.trial(stop_check=guard), 270)
        self.assertEqual(self.bridge.issued, [])

    def test_invalid_heading_and_pulse_cannot_send_input(self):
        for heading in (float('nan'), -1, 360, True):
            with self.subTest(heading=heading), self.assertRaises(ValueError):
                survey.turn_to(self.trial(), heading)
        for dx in (0, 251, -251, True, 20.5):
            with self.subTest(dx=dx), self.assertRaises(ValueError):
                self.trial().pulse(dx)
        self.assertEqual(self.bridge.issued, [])

    def test_stale_gpu_telemetry_latches_even_if_later_sample_recovers(self):
        guard = survey.SurveyGuard.__new__(survey.SurveyGuard)
        guard.series, guard.reason = Mock(), None
        guard.series.stop_reason.return_value = None
        guard.last_sample = time.monotonic()-survey.MAX_GPU_SAMPLE_AGE_SECONDS-1
        with self.assertRaisesRegex(ValueError, 'telemetryLost'):
            guard.check()
        guard.last_sample = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'telemetryLost'):
            guard.check()

    def test_failed_start_still_stops_only_the_original_authenticated_child(self):
        child = dict(processId=24816, instanceNonce='child', windowsSessionId=3)
        root = dict(processId=10124, instanceNonce='root', windowsSessionId=1)
        owner = dict(root=root, child=child)
        api, guard = Mock(), Mock()
        api.start_agent.side_effect = RuntimeError('startup response lost')
        args = SimpleNamespace(owner_lineage=Path('lineage.json'), anchor_scene=Mock(), heading=270)
        args.anchor_scene.__truediv__ = Mock(return_value=Mock(read_bytes=Mock(return_value=b'{}')))
        with patch.object(survey, 'load_map_owner', return_value=owner), \
                patch.object(survey, 'scene_anchor', return_value=self.anchor), \
                patch.object(survey, 'control_module', return_value=api), \
                patch.object(survey, 'ready_session', return_value=(root, child)), \
                patch.object(survey, 'SurveyGuard', return_value=guard), \
                self.assertRaisesRegex(RuntimeError, 'startup response lost'):
            survey.run(args, Path('evidence'), self.report)
        api.stop_agent.assert_called_once_with(child, 12)
        guard.close.assert_called_once()

    def test_pipe_close_failure_does_not_skip_owned_agent_or_monitor_cleanup(self):
        child = dict(processId=24816, instanceNonce='child', windowsSessionId=3, agentPipeName='owned')
        root = dict(processId=10124, instanceNonce='root', windowsSessionId=1)
        api, guard, bridge = Mock(), Mock(), Mock()
        api.start_agent.return_value = child
        bridge.hello = {}
        bridge.request.return_value = (dict(type='stopped', receipts=[]), b'')
        bridge.handle.close.side_effect = OSError('pipe close failed')
        args = SimpleNamespace(owner_lineage=Path('lineage.json'), anchor_scene=Mock(), heading=270)
        args.anchor_scene.__truediv__ = Mock(return_value=Mock(read_bytes=Mock(return_value=b'{}')))
        with patch.object(survey, 'load_map_owner', return_value=dict(root=root, child=child)), \
                patch.object(survey, 'scene_anchor', return_value=self.anchor), \
                patch.object(survey, 'control_module', return_value=api), \
                patch.object(survey, 'ready_session', return_value=(root, child)), \
                patch.object(survey, 'SurveyGuard', return_value=guard), \
                patch.object(survey, 'Bridge', return_value=bridge), \
                patch.object(survey, 'verify_bridge_identity'), \
                self.assertRaisesRegex(OSError, 'pipe close failed'):
            survey.run(args, Path('evidence'), self.report)
        bridge.request.assert_called_once_with('stop')
        api.stop_agent.assert_called_once_with(child, 12)
        guard.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
