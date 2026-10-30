"""Paired original-image summaries must expose every regression and distinct native class."""
import unittest
from qualify_scene_shadow import scores


class SceneQualificationTests(unittest.TestCase):
    """Test the comparison math without loading CUDA or touching a game session."""
    def test_equal_net_accuracy_does_not_hide_a_new_error(self):
        rows=[dict(frameId=1,rgbSha256='a',native='stair-front',baseline='sidewalk-junction',candidate='stair-front'),
              dict(frameId=2,rgbSha256='b',native='west-lamp',baseline='west-lamp',candidate='stair-front')]
        result=scores(rows)
        self.assertEqual(result['baselineCorrect'],result['candidateCorrect'])
        self.assertEqual(result['regressions'],[rows[1]])
        self.assertEqual(result['corrections'],[rows[0]])
        self.assertEqual(result['perClass']['west-lamp']['candidateCorrect'],0)

    def test_repeated_pixels_do_not_increase_unique_coverage(self):
        row=dict(frameId=1,rgbSha256='same',native='stair-front',baseline='stair-front',candidate='stair-front')
        result=scores([row,dict(row,frameId=2)])
        self.assertEqual(result['images'],2)
        self.assertEqual(result['uniquePerClass']['stair-front'],1)
        self.assertEqual(result['uniquePerClass']['west-lamp'],0)

    def test_unknown_station_is_not_a_success(self):
        with self.assertRaises(ValueError):
            scores([dict(native='unknown',baseline='unknown',candidate='unknown',rgbSha256='a')])


if __name__=='__main__':
    unittest.main()
