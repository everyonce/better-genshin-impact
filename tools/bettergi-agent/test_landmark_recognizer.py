"""The landmark head may consume center pixels only and must generalize across independent trials."""
import copy
import unittest

import numpy as np

from landmark_recognizer import CLASSES, LandmarkRecognizer, evaluate, fit, signature


def run(tag, offset=0):
    """Synthetic circuits share the terminal/entry frame between two successive laps."""
    stations = ['stair-front','sidewalk-junction','west-lamp','sidewalk-junction','stair-front']
    views, samples = [], {}
    for lap in range(2):
        for i,s in enumerate(stations):
            k=lap*4+i
            views.append(dict(frameId=k,circuit=lap+1,stop=i,station=s))
            rgb=np.zeros((192,192,3),np.uint8)
            rgb[40:120,48:144,CLASSES.index(s)]=120+offset
            samples[k]=(rgb,dict(frameId=k))
    meta=dict(runId=tag,lease=[tag+'s',tag+'o'],captureEpoch=tag,
              sourceInterval100ns=[100,200],evidenceSha256=tag,circuits=2)
    return meta,views,samples


class LandmarkTests(unittest.TestCase):
    def test_only_center_rgb_can_change_the_classifier(self):
        rgb=run('a')[2][0][0]
        hud=np.full_like(rgb,255)
        hud[40:120,48:144]=rgb[40:120,48:144]
        np.testing.assert_array_equal(signature(rgb),signature(hud))
        head=LandmarkRecognizer(fit([run('a')]))
        self.assertEqual(head.predict(rgb),head.predict(hud.tobytes()))
        with self.assertRaises(ValueError):
            head.predict({'pixels':rgb,'station':'stair-front'})

    def test_held_out_unique_and_role_metrics_deduplicate_shared_boundary(self):
        source=run('a')
        head=LandmarkRecognizer(fit([source]))
        self.assertEqual(len(head.labels),9)
        acquired=run('b',5)
        report=evaluate(head,acquired)
        self.assertEqual((report['unique']['correct'],report['allVisits']['samples']),(9,10))
        self.assertEqual(report['perApproach']['junction-from-west-lamp']['correct'],2)
        self.assertEqual(report['unique']['majorityCorrect'],4)
        self.assertEqual(list(report['unique']['classRecall'].values()),[1.,1.,1.])
        with self.assertRaises(ValueError):
            evaluate(head,source)

    def test_wrong_class_or_geometry_checkpoint_does_not_load(self):
        data=fit([run('a')])
        broken=copy.deepcopy(data)
        broken['prototypes'][0]['signature'].append(0.)
        with self.assertRaises(ValueError):
            LandmarkRecognizer(broken)
        with self.assertRaises(ValueError):
            LandmarkRecognizer(dict(data,format='other'))


if __name__=='__main__':
    unittest.main()
