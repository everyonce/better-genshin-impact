"""CPU-only prototype checks: no policy construction or CUDA calls."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import patch

import p2p_replay_sensitivity as runner

TEST_SOURCE = Path(os.environ.get('P2P_SOURCE', runner.SOURCE))
FFMPEG = os.environ.get('P2P_FFMPEG') or shutil.which('ffmpeg')
FFPROBE = os.environ.get('P2P_FFPROBE') or shutil.which('ffprobe')


class CodecTests(unittest.TestCase):
    def setUp(self):
        if not (TEST_SOURCE/'elefant/data/action_mapping.py').is_file():
            self.skipTest('Supply the pinned upstream source via P2P_SOURCE')
        self.codec = runner.ActionCodec(TEST_SOURCE)

    def test_meaning_sorted_padding_and_zero_bins(self):
        action = {'heldKeys': ['W', 'LSHIFT', 'A', 'RBUTTON', 'LBUTTON'], 'mouseDx': 0, 'mouseDy': 0}
        ids = self.codec.encode(action)
        self.assertEqual(ids[:6], [6, 11, 18, 0, 1, 2])
        self.assertNotEqual(ids[6:], [0, 0])  # token zero is an extreme bin, not zero movement
        self.assertTrue(self.codec.validate_upstream([action])['passed'])

    def test_every_supported_key_and_boundary_matches_actual_upstream_cpu_method(self):
        labels = [{'heldKeys': [key], 'mouseDx': 0, 'mouseDy': 0} for key in self.codec.keys]
        for axis, edges in enumerate(self.codec.edges):
            values = {int(v)+offset for v in edges for offset in (-1, 0, 1)}
            for value in values:
                labels.append({'heldKeys': [], 'mouseDx': value if axis == 0 else 0,
                               'mouseDy': value if axis == 1 else 0})
        result = self.codec.validate_upstream(labels)
        self.assertTrue(result['passed'])
        self.assertGreater(result['labels'], 50)

    def test_unknown_alias_capacity_and_noninteger_motion_fail(self):
        for keys in (['X'], ['SHIFT'], ['W', 'W'], ['A', 'D', 'W', 'S', 'SPACE'], ['LBUTTON', 'RBUTTON', 'MBUTTON']):
            with self.subTest(keys=keys), self.assertRaises(runner.GateFailure):
                self.codec.encode({'heldKeys': keys, 'mouseDx': 0, 'mouseDy': 0})
        for value in (True, 1.5, float('nan'), 2**64):
            with self.subTest(value=value), self.assertRaises(runner.GateFailure):
                self.codec.encode({'heldKeys': [], 'mouseDx': value, 'mouseDy': 0})


class EvidenceTests(unittest.TestCase):
    def test_original_full_logit_method_keeps_component_batching(self):
        if not (TEST_SOURCE/'elefant/policy_model/model_free.py').is_file():
            self.skipTest('Supply the pinned upstream source via P2P_SOURCE')
        import torch
        Structured = namedtuple('Structured', 'keys mouse_buttons mouse_delta_x mouse_delta_y')
        shapes = []
        def head(x):
            shapes.append(tuple(x.shape))
            return x
        def check(actual, expected):
            self.assertEqual(actual, expected)
        mapping = SimpleNamespace(get_number_of_keyboard_choices=lambda: 2, get_number_of_mouse_button_choices=lambda: 2,
                                  get_n_mouse_x_bins=lambda: 2, get_n_mouse_y_bins=lambda: 2)
        model = SimpleNamespace(n_actions=8, n_keyboard_actions=4, n_mouse_button_actions=2, action_mapping=mapping,
                                keyboard_out_logits=head, mouse_button_out_logits=head,
                                mouse_delta_x_out_logits=head, mouse_delta_y_out_logits=head)
        method = runner.upstream_full_logits(TEST_SOURCE, Structured, check)
        result = method(model, torch.ones((1, 3, 8, 2)))
        self.assertEqual(shapes, [(1, 3, 4, 2), (1, 3, 2, 2), (1, 3, 1, 2), (1, 3, 1, 2)])
        self.assertEqual(len(result), 4)

    def test_gpu_is_never_the_default(self):
        args = runner.parse_args(['--case', 'plan.json', '711', '--negative-control-probe', '711', '--output', 'ignored'])
        self.assertFalse(args.execute_gpu)
        self.assertEqual(args.seeds, 32)

    def test_goal_metadata_and_bytes_are_bound_without_loading_encoder(self):
        from goal_embedding import ENCODER, POOLING
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'goal.json'
            goal = {'version': 1, 'encoder': ENCODER, 'pooling': POOLING, 'maxLength': 128,
                    'instruction': 'Stand still.', 'embedding': [[1.0]*768]}
            path.write_text(json.dumps(goal), encoding='utf-8')
            metadata = {k: v for k, v in goal.items() if k != 'embedding'}
            metadata['file'] = str(path.resolve())
            case = {'window': {'goalProvenance': {'source': 'initialGoalState', 'goalMetadata': metadata}}}
            embedding, evidence = runner.load_case_goal(case)
            self.assertEqual(embedding.shape, (1, 768))
            self.assertEqual(evidence['fileEvidence']['sha256'], runner.digest(path)['sha256'])
            goal['instruction'] = 'Walk.'
            path.write_text(json.dumps(goal), encoding='utf-8')
            with self.assertRaisesRegex(runner.GateFailure, 'metadata differs'):
                runner.load_case_goal(case)

    def test_numeric_failure_retains_deltas_and_never_relaxes_threshold(self):
        import torch
        with tempfile.TemporaryDirectory() as temporary:
            report = {'parityGates': [], 'comparisons': [], 'comparisonEligible': False}
            path = Path(temporary) / 'report.json'
            with self.assertRaisesRegex(runner.GateFailure, 'numerical parity'):
                runner.numeric_gate('cpu-only', torch.tensor([1.1]), torch.tensor([1.0]), report, path)
            written = json.loads(path.read_text())
            self.assertFalse(written['parityGates'][0]['passed'])
            self.assertGreater(written['parityGates'][0]['maxAbsoluteError'], .09)
            self.assertEqual(written['parityGates'][0]['atol'], .001)
            self.assertEqual(written['comparisons'], [])

    def test_changed_prepared_inputs_and_unselected_probe_fail_before_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'plan.json'
            value = {'status': 'prepared', 'trainingEligible': False, 'inferenceExecuted': False,
                     'windows': [{'probe': {'frameId': 711}, 'probeLabel': None}], 'parameters': {'historyFrames': 40},
                     'inputEvidence': {name: {'path': str(path), 'bytes': 0, 'sha256': 'wrong'} for name in
                                       ('report', 'observations.jsonl', 'frames.jsonl', 'events.jsonl', 'recording.json', 'frames.mp4')}}
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(runner.GateFailure, 'absent or ambiguous'):
                runner.load_case(path, 712)
            with self.assertRaisesRegex(runner.GateFailure, 'changed prepared input'):
                runner.load_case(path, 711)


class VideoTests(unittest.TestCase):
    @unittest.skipUnless(FFMPEG and FFPROBE, 'Supply FFmpeg/FFprobe via PATH or P2P_FFMPEG/P2P_FFPROBE')
    def test_exact_absolute_indexes_and_pts_with_bounded_synthetic_video(self):
        import numpy as np
        ffmpeg, ffprobe = FFMPEG, FFPROBE
        images = np.stack([np.full((4, 4, 3), value, dtype=np.uint8) for value in (0, 40, 90, 150, 255)])
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / 'synthetic.mkv'
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '4x4',
                            '-framerate', '20', '-i', 'pipe:0', '-threads', '1', '-c:v', 'ffv1', '-pix_fmt', 'bgr0', str(video)],
                           input=images.tobytes(), check=True, timeout=15, capture_output=True)
            refs = [{'width': 4, 'height': 4, 'videoFrameIndex': i, 'videoPtsSeconds': i/20} for i in (3, 1, 3)]
            diagnostics = {}
            result = runner.decode_indexed(video, refs, 5, ffmpeg, ffprobe, diagnostics)
            self.assertEqual(set(result), {1, 3})
            self.assertTrue(np.array_equal(result[1], images[1]))
            self.assertTrue(np.array_equal(result[3], images[3]))
            self.assertEqual(diagnostics['selectedIndexes'], [1, 3])
            refs[0]['videoPtsSeconds'] = .14
            with self.assertRaisesRegex(runner.GateFailure, 'PTS/index'):
                runner.decode_indexed(video, refs, 5, ffmpeg, ffprobe, {})


if __name__ == '__main__':
    unittest.main()
