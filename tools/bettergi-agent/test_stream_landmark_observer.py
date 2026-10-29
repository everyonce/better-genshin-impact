"""Check that the online landmark observer sees exactly the verified image."""
import hashlib
import unittest
from unittest.mock import Mock

from stream_client import observe_station


class StationObserverTests(unittest.TestCase):
    def test_labels_and_native_pose_are_never_inputs(self):
        pixels = b'camera bytes'
        head = Mock(checkpoint_id='frozen')
        head.predict.return_value = dict(station='west-lamp', squaredDistance=0.24)
        event = dict(type='hybridEndpointVerified', station='stair-front',
                     samples=[dict(frameId=2), dict(frameId=4)])
        observe_station(head, event, dict(frameId=4, pose=(5, 9)), pixels)
        head.predict.assert_called_once_with(pixels)
        visual = event['visualStation']
        self.assertEqual((visual['frameId'], visual['checkpointId']), (4, 'frozen'))
        self.assertEqual(visual['prediction']['station'], 'west-lamp')
        self.assertEqual(visual['rgbSha256'], hashlib.sha256(pixels).hexdigest())

    def test_mismatched_start_frame_fails_before_classification(self):
        head = Mock()
        event = dict(type='hybridStartVerified', frameId=3)
        with self.assertRaisesRegex(RuntimeError, 'exact verified source frame'):
            observe_station(head, event, dict(frameId=4), b'')
        head.predict.assert_not_called()

    def test_non_station_events_skip_classification(self):
        head = Mock()
        event = dict(type='hybridDecision')
        observe_station(head, event, None, None)
        head.predict.assert_not_called()
        self.assertNotIn('visualStation', event)
