"""Verify the frozen color metric on synthetic pixels without opening any gameplay or holdout."""
import copy
import hashlib
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

from landmark_recognizer import (CENTERED_FORMAT, CENTERED_METHOD, CENTERED_METRIC, CLASSES, FEATURE,
                                 FORMAT, G4_SHA256, LandmarkRecognizer, signature)


BASE = Path(__file__).resolve().parents[2]/'artifacts/agent/landmarks/gen-04.json'
G6 = BASE.parent/'g6-centered-frozen/gen-06.json'
G4_QUALIFICATION = BASE.parent/'qualify-g4-fresh-10.json'


def texture():
    """Keep all synthetic channels in range under a uniform per-channel lighting shift."""
    y,x = np.indices((192,192),dtype='uint16')
    return np.stack((x%129,y%129,(x+y)%129),axis=-1).astype('uint8')


class CenteredMetricTests(unittest.TestCase):
    @unittest.skipUnless(G6.exists() and G4_QUALIFICATION.exists(), 'requires the frozen local G6 and G4 qualification')
    def test_real_photo_task_rejects_g6_under_g4_authority_before_cuda(self):
        """Run the production launcher parser and policy admission gate, allowing only the two pinned artifacts."""
        import run_rdp_patrol as patrol
        from stream_client import load_policy, parse_arguments
        flags = ['--photo-station','stair-front','--landmark-shadow',str(G6),
                 '--photo-qualification',str(G4_QUALIFICATION)]
        args = parse_arguments(patrol.patrol_argv(patrol.options(flags), 3, BASE.parent)[5:])
        pins = {G6:'4c347fc40796ccd33248982e5979273d10e6dd2afed45e8f2d5be7b8f1f7e446',
                G4_QUALIFICATION:'2be1bb61fb600d4ecc7d985bbea93ba344de48570bdf3c06c9781ed062f3ffd4'}
        reads, original = [], Path.read_bytes
        def only_pinned(path):
            self.assertIn(path,pins)
            content = original(path)
            self.assertEqual(hashlib.sha256(content).hexdigest(),pins[path])
            reads.append(path)
            return content
        factory = Mock(side_effect=AssertionError('GPU setup preceded qualification'))
        with patch.object(Path, 'read_bytes', only_pinned), patch.dict('sys.modules',{'model_adapters':types.SimpleNamespace(make_adapter=factory)}):
            with self.assertRaisesRegex(ValueError,'qualification or checkpoint digest differs'):
                load_policy(args)
        self.assertEqual(reads,[G6,G4_QUALIFICATION])
        factory.assert_not_called()

    def test_metric_schema_cannot_be_swapped_or_unknown(self):
        """Version one cannot silently accept new distance fields and version two requires pinned G4 inputs."""
        base = dict(format=FORMAT, feature=FEATURE, classes=list(CLASSES), deployment='checkpoint-shadow-only',
                    prototypes=[dict(station=s,signature=[0.]*360) for s in CLASSES])
        self.assertEqual(LandmarkRecognizer(base).predict(texture())['station'],CLASSES[0])
        for extra in (dict(distanceMetric=CENTERED_METRIC),dict(sourceCheckpointSha256=G4_SHA256),
                      dict(method=CENTERED_METHOD),dict(format=CENTERED_FORMAT)):
            with self.subTest(fields=extra), self.assertRaises(ValueError):
                LandmarkRecognizer(dict(base,**extra))

    @unittest.skipUnless(BASE.exists(), 'requires installed pinned G4 template file')
    def test_exact_g4_legacy_bits_and_full_per_channel_spatial_centering(self):
        """Check original G4 distance bits, the independent centered formula, and preserved spatial contrast."""
        incumbent = LandmarkRecognizer.load(BASE)
        self.assertEqual(incumbent.checkpoint_id,G4_SHA256)
        data = dict(incumbent.data,format=CENTERED_FORMAT,method=CENTERED_METHOD,
                    distanceMetric=CENTERED_METRIC,sourceCheckpointSha256=G4_SHA256)
        candidate = LandmarkRecognizer(data)
        t = texture()
        images = (t,t+np.array([15,22,45],dtype='uint8'),np.flip(t,axis=1),np.zeros_like(t))
        gold = ('0x1.694a840000000p+2','0x1.47aac40000000p+2','0x1.6253080000000p+2','0x1.0c9aec0000000p+2')
        centered = []
        for rgb, bits in zip(images,gold):
            self.assertEqual(incumbent.predict(rgb),dict(station='sidewalk-junction',squaredDistance=float.fromhex(bits)))
            delta = (incumbent.templates-signature(rgb)).reshape(-1,10,12,3)
            distances = ((delta-delta.mean(axis=(1,2),keepdims=True))**2).sum(axis=(1,2,3))
            i = int(distances.argmin())
            pred = candidate.predict(rgb)
            self.assertEqual(pred,dict(station=incumbent.labels[i],squaredDistance=float(distances[i])))
            centered.append(pred['squaredDistance'])
        self.assertAlmostEqual(centered[0],centered[1],places=5)
        self.assertNotAlmostEqual(centered[0],centered[2],places=4)
        for extra in (dict(format=FORMAT),dict(distanceMetric='squared-euclidean'),dict(method='legacy'),
                      dict(prototypes=data['prototypes'][:-1]),dict(trainingRuns=[]),dict(temperature=.5)):
            with self.subTest(fields=list(extra)), self.assertRaises(ValueError):
                LandmarkRecognizer(dict(data,**extra))
        altered = copy.deepcopy(data)
        altered['prototypes'][0]['signature'][0] += .00001
        with self.assertRaises(ValueError):
            LandmarkRecognizer(altered)
