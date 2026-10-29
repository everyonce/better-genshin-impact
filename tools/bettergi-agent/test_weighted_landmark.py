"""Offline G7 schema and arithmetic regressions on synthetic, three-channel textures."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

from landmark_recognizer import CENTERED_METRIC, FORMAT as LEGACY_FORMAT, LandmarkRecognizer, signature
from weighted_landmark_recognizer import WeightedLandmarkRecognizer, load_landmark_shadow, weight_features

ROOT = Path(__file__).resolve().parents[2]/'artifacts/agent/landmarks'
G4, G6, G7 = ROOT/'gen-04.json', ROOT/'g6-centered-frozen/gen-06.json', ROOT/'g7-half-color-frozen/gen-07.json'
G7_SHA = '99531706a59ce3e53156f0ad1a4532292e375d1ed783ba49bc82653ebce1e3c6'
G4_QUALIFICATION = ROOT/'qualify-g4-fresh-10.json'


class WeightedLandmarkTests(unittest.TestCase):
    @unittest.skipUnless(G7.exists() and G4_QUALIFICATION.exists(),'requires frozen G7 and actual G4 qualification')
    def test_real_fixed_patrol_accepts_g7_shadow_and_refuses_g7_photo(self):
        """Walk the real launcher and policy admission path, using a stub only at the GPU boundary."""
        import run_rdp_patrol as patrol
        from stream_client import load_policy, observe_station, parse_arguments
        def arguments(flags):
            options = patrol.options(['--landmark-shadow',str(G7),*flags])
            return parse_arguments(patrol.patrol_argv(options, 3, ROOT)[5:])
        gpu = Mock()
        with patch.dict('sys.modules',{'model_adapters':types.SimpleNamespace(make_adapter=gpu)}), patch('p2p_startup.prepare_startup_graph'):
            shadow = arguments(['--retain-station-rgb'])
            self.assertTrue(shadow.retain_station_rgb)
            policy = load_policy(shadow)
            self.assertIsInstance(policy.landmark_shadow,WeightedLandmarkRecognizer)
            gpu.assert_called_once()
            pixels = bytes(192*192*3)
            mark = dict(type='hybridStartVerified',frameId=1)
            observe_station(policy.landmark_shadow,mark,dict(frameId=1),pixels)
            self.assertEqual(mark['visualStation']['checkpointId'],G7_SHA)
            self.assertEqual(mark['visualStation']['prediction'],load_landmark_shadow(G7).predict(pixels))
            gpu.reset_mock()
            self.assertEqual(hashlib.sha256(G4_QUALIFICATION.read_bytes()).hexdigest(),
                             '2be1bb61fb600d4ecc7d985bbea93ba344de48570bdf3c06c9781ed062f3ffd4')
            photo = arguments(['--photo-station','stair-front','--photo-qualification',str(G4_QUALIFICATION)])
            with self.assertRaisesRegex(ValueError,'qualification or checkpoint digest differs'):
                load_policy(photo)
            gpu.assert_not_called()

    @unittest.skipUnless(G4.exists() and G6.exists() and G7.exists(),'requires frozen G4, G6 and G7 checkpoints')
    def test_actual_photo_admission_blocks_matching_single_episode_pass_for_experimental_metrics(self):
        """A fully recomputable passing synthetic episode is sufficient only for the deployed family."""
        import run_rdp_patrol as patrol
        from qualify_landmarks import qualify
        from stream_client import load_policy, parse_arguments
        from test_qualify_landmarks import OLD, paired
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            pair,qual = Path(tmp)/'pair.json',Path(tmp)/'qualification.json'
            for path in (G4,G6,G7):
                checkpoint_id = hashlib.sha256(path.read_bytes()).hexdigest()
                data = paired(old_errors=[2,4])
                data['evaluations'][1]['checkpointId'] = checkpoint_id
                result = qualify(data,OLD,checkpoint_id)
                self.assertEqual(result['recommendation'],'use-challenger-as-observer')
                pair.write_text(json.dumps(data))
                qual.write_text(json.dumps(dict(result,evaluation=pair.name,
                                                 evaluationSha256=hashlib.sha256(pair.read_bytes()).hexdigest())))
                flags = ['--landmark-shadow',str(path),'--photo-qualification',str(qual),'--photo-station','west-lamp']
                args = parse_arguments(patrol.patrol_argv(patrol.options(flags),3,ROOT)[5:])
                gpu = Mock()
                with self.subTest(checkpoint=path.name),patch.dict('sys.modules',{'model_adapters':types.SimpleNamespace(make_adapter=gpu)}),patch('p2p_startup.prepare_startup_graph'):
                    if path == G4:
                        self.assertEqual(load_policy(args).landmark_shadow.checkpoint_id,checkpoint_id)
                        gpu.assert_called_once()
                    else:
                        with self.assertRaisesRegex(ValueError,'shadow-only for photographic goals'):
                            load_policy(args)
                        gpu.assert_not_called()

    def test_transform_equals_half_color_energy_for_arbitrary_features(self):
        """The complete distances, rather than just the winning class, must match S plus 0.5 times C."""
        rng = np.random.default_rng(731)
        bank = rng.standard_normal((168,360)).astype(np.float32)
        query = rng.standard_normal(360).astype(np.float32)
        errors = (bank.astype(np.float64)-query.astype(np.float64)).reshape(-1,120,3)
        means = errors.mean(axis=1,keepdims=True)
        expected = ((errors-means)**2).sum(axis=(1,2))+.5*120*(means**2).sum(axis=(1,2))
        actual = ((weight_features(bank)-weight_features(query))**2).sum(axis=1)
        np.testing.assert_allclose(actual,expected,rtol=1e-13,atol=1e-12)
        # For uniform channel shifts, spatial error alone would be zero and original G4 would be twice as large.
        offset = np.tile([.2,.4,-.1],120)
        self.assertAlmostEqual(float((weight_features(offset)**2).sum()),.5*120*(.2**2+.4**2+.1**2),places=12)

    @unittest.skipUnless(G4.exists() and G6.exists() and G7.exists(),'requires three frozen local checkpoints')
    def test_observer_matches_formula_and_retains_legacy_predictions(self):
        """Each scorer selects its own pinned metric; the old loaders still return their exact previous float values."""
        g4,g6,g7 = (load_landmark_shadow(p) for p in (G4,G6,G7))
        old4,old6 = (LandmarkRecognizer.load(p) for p in (G4,G6))
        self.assertEqual(g7.checkpoint_id,G7_SHA)
        np.testing.assert_array_equal(g7.templates,g4.templates)
        for seed in range(4):
            a = np.random.default_rng(seed).integers(0,256,(192,192,3),dtype=np.uint8)
            self.assertEqual(g4.predict(a),old4.predict(a))
            self.assertEqual(g6.predict(a),old6.predict(a))
            err = (g4.templates.astype(np.float64)-signature(a).astype(np.float64)).reshape(-1,120,3)
            means = err.mean(axis=1,keepdims=True)
            scores = ((err-means)**2).sum(axis=(1,2))+.5*120*(means**2).sum(axis=(1,2))
            idx = int(np.argmin(scores))
            prediction = g7.predict(a.tobytes())
            self.assertEqual(prediction['station'],g4.labels[idx])
            self.assertAlmostEqual(prediction['squaredDistance'],float(scores[idx]),places=12)

    @unittest.skipUnless(G7.exists(),'requires the frozen G7 checkpoint')
    def test_tampering_with_format_metric_template_or_weight_fails_before_scoring(self):
        data = json.loads(G7.read_bytes())
        with self.assertRaises(ValueError):
            LandmarkRecognizer(data)
        for extra in (dict(format=LEGACY_FORMAT),dict(distanceMetric=CENTERED_METRIC),dict(method='g4'),
                      dict(meanEnergyWeight=.75),dict(prototypes=data['prototypes'][1:]),dict(trainingRuns=[])):
            with self.subTest(keys=list(extra)), self.assertRaises(ValueError):
                WeightedLandmarkRecognizer(dict(data,**extra))
        # A v1 declaration cannot smuggle a weighted metric, even if the source hash is stripped.
        legacy = dict(data,format=LEGACY_FORMAT)
        legacy.pop('distanceMetric')
        legacy.pop('sourceCheckpointSha256')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path=Path(temp)/'bad.json'
            path.write_text(json.dumps(legacy))
            with self.assertRaisesRegex(ValueError,'matching format'):
                load_landmark_shadow(path)
