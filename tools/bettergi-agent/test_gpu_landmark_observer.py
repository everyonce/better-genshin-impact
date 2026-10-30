"""Synthetic artifact and authority tests; no GPU allocation or game control."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from gpu_landmark_observer import FORMAT,GpuLandmarkObserver
from landmark_recognizer import CLASSES
from patrol_photo_survey import require_photo_metric
from weighted_landmark_recognizer import load_landmark_shadow


class GpuObserverTests(unittest.TestCase):
    """Bound every dependency and prevent a shadow-only metric from entering photo admission."""
    def setUp(self):
        """Create explicitly synthetic qualification fixtures in a private temporary directory."""
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.envelope=dict(format=FORMAT,deployment='checkpoint-shadow-only')
        self.bind('encoder',b'synthetic weights: never loaded')
        self.plan=dict(trainingImages=3,holdoutImages=3,features='synthetic feature',classifier='synthetic classifier')
        self.bind('plan',self.plan)
        self.model=dict(format='bettergi-p2p-conv-station-experiment-v1',authority='offline shadow only',
            features=self.plan['features'],classifier=self.plan['classifier'],classes=list(CLASSES),
            encoderFileSha256=self.envelope['encoder']['sha256'],sourceTensorSha256='a'*64,
            runtimeHalfTensorSha256='b'*64,trainingLeases=[],labels=list(CLASSES),
            prototypes=np.eye(3,1008,dtype=np.float32).tolist())
        self.bind('model',self.model)
        self.accuracy=dict(candidateSha256=self.envelope['model']['sha256'],regressions=[],candidateCorrect=3,baselineCorrect=2)
        self.bind('accuracyProof',self.accuracy)
        source=Path(__file__).with_name('experiments')
        self.execution=dict(candidateSha256=self.envelope['model']['sha256'],
            originalResultsSha256=self.envelope['accuracyProof']['sha256'],planSha256=self.envelope['plan']['sha256'],
            passed=True,allOriginalLabelsPreserved=True,maximumFeatureAbsError=0,parityFrames=6,
            latencyMs=dict(p95=3,maximum=5),torchPeakAllocatedMiB=6,peakTemperatureC=60,
            sourceCodeSha256={name:hashlib.sha256((source/name).read_bytes()).hexdigest()
                for name in ('p2p_station_features.py','p2p_station_graph.py')})
        self.bind('executionProof',self.execution)

    def bind(self,key,value):
        """Seal a test artifact and its deliberately synthetic parent reference."""
        raw=value if isinstance(value,bytes) else json.dumps(value).encode()
        path=self.root/(key+'.bin')
        path.write_bytes(raw)
        self.envelope[key]=dict(path=path.name,sha256=hashlib.sha256(raw).hexdigest())

    def load(self):
        """Use the production dispatch path without invoking prepare or predict."""
        path=self.root/'observer.json'
        path.write_text(json.dumps(self.envelope))
        return load_landmark_shadow(path)

    def test_load_is_lazy_and_photos_remain_rejected(self):
        with patch.object(GpuLandmarkObserver,'prepare',side_effect=AssertionError('No GPU permitted')):
            head=self.load()
            self.assertIsNone(head._encoder)
            with self.assertRaisesRegex(ValueError,'shadow-only'):
                require_photo_metric(head)

    def test_changed_weight_bytes_are_rejected(self):
        (self.root/self.envelope['encoder']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            self.load()

    def test_artifact_escape_is_rejected(self):
        self.envelope['encoder']['path']='../outside.pt'
        with self.assertRaisesRegex(ValueError,'Unbound'):
            self.load()

    def test_wrong_or_missing_execution_source_is_rejected(self):
        for key,value in [('p2p_station_graph.py','0'*64),('unexpected.py','0'*64)]:
            with self.subTest(source=key):
                original=dict(self.execution['sourceCodeSha256'])
                self.execution['sourceCodeSha256'][key]=value
                self.bind('executionProof',self.execution)
                with self.assertRaises(ValueError):
                    self.load()
                self.execution['sourceCodeSha256']=original

    def test_speed_and_nonfinite_measurements_cannot_pass(self):
        for value in (10.01,float('nan'),float('inf'),-1):
            with self.subTest(p95=value):
                self.execution['latencyMs']['p95']=value
                self.bind('executionProof',self.execution)
                with self.assertRaises(ValueError):
                    self.load()

    def test_malformed_pixels_fail_before_gpu_prepare(self):
        head=self.load()
        with patch.object(head,'prepare',side_effect=AssertionError('No GPU permitted')):
            with self.assertRaisesRegex(ValueError,'RGB192'):
                head.predict(b'truncated')

    def test_prediction_protocol_uses_only_visual_features(self):
        head=self.load()
        class Encoder:
            """Return a deterministic visual feature without any controller or native position."""
            def feature(self,rgb):
                return np.eye(1,1008,dtype=np.float32)[0]
        head._encoder=Encoder()
        self.assertEqual(head.predict(bytes(192*192*3)),dict(station=CLASSES[0],squaredDistance=0.0))


if __name__=='__main__':
    unittest.main()
