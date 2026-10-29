"""Check which measured camera proposals may enter the existing dispatch path."""
import math
import unittest
from unittest.mock import Mock

from patrol_camera_trial import PatrolCameraTrial


class PatrolCameraTrialTests(unittest.TestCase):
    def setUp(self):
        self.fit = Mock(checkpoint_id='fit')
        self.fit.suggest.return_value = 110
        self.trial = PatrolCameraTrial(self.fit)
        self.selection = dict(owner='hybrid-native', reason='nativeHeading',
            pose=dict(x=0, y=0, yawDegrees=70), step=dict(keys=[], mouseDx=40, mouseDy=0, durationMs=100))

    def test_first_turn_uses_current_target_and_leaves_native_step_intact(self):
        evidence = self.trial.propose(self.selection, (0, -5), 1000)
        self.assertEqual(evidence['nativeMouseDx'], 40)
        self.assertEqual(evidence['proposedMouseDx'], 110)
        self.assertIsNone(evidence['previousMouseRequestId'])
        self.fit.suggest.assert_called_once_with(20, ms_since_last_mouse=math.inf)
        self.assertEqual(self.selection['step']['mouseDx'], 40)

    def test_unresolved_latest_mouse_never_uses_an_earlier_receipt(self):
        self.trial.accepted('old', 1000, dict(mouseDx=20))
        self.trial.accepted('latest', 1100, dict(mouseDx=1, keys=['W']))
        self.trial.accepted('walk', 1150, dict(mouseDx=0, keys=['W']))
        self.trial.receipt(dict(requestId='old', endedAtMs=1300))
        self.assertIsNone(self.trial.propose(self.selection, (0, -5), 1500))
        self.fit.suggest.assert_not_called()
        self.trial.receipt(dict(requestId='latest', endedAtMs=1230))
        evidence = self.trial.propose(self.selection, (0, -5), 1500)
        self.assertEqual((evidence['msSinceLastMouse'], evidence['previousMouseRequestId']), (250, 'latest'))

    def test_reject_unqualified_or_unchanged_outputs(self):
        for dx in [None, 0, -18, 40, 251, True]:
            self.fit.suggest.return_value = dx
            self.assertIsNone(self.trial.propose(self.selection, (0, -5), 1000))
        self.fit.suggest.return_value = 80
        for changes in [dict(reason='obstacleRetreat'), dict(owner='open-p2p'),
                        dict(step=dict(keys=['A'], mouseDx=40, mouseDy=0, durationMs=100))]:
            self.assertIsNone(self.trial.propose(dict(self.selection, **changes), (0, -5), 1000))
