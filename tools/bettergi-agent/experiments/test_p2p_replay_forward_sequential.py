"""CPU-only checks of reconstruction and all-three-arm publication gates; no policy loads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch
import p2p_replay_forward_sequential as runner
from test_prepare_replay import evidence


def sample_pair(seed):
    """Represent a fully validated synthetic complete eight-component sample."""
    sample = {'seed': seed, 'uniforms': [.5]*8, 'tokenIds': [0]*8,
              'decoded': {'keys': [], 'mouseButtons': [], 'dx': 0, 'dy': 0},
              'logits': [[0., 1.] for _ in range(8)]}
    return {'seed': seed, 'referenceReplay': sample, 'alternatePlaceholderReplay': copy.deepcopy(sample),
            'tokensExact': True, 'decodedExact': True, 'conditionalLogitsExact': True}


def results():
    """Make the fixed three cases with all three arms and32 paired complete seeds."""
    return [{'key': str(probe), 'probeFrameId': probe,
             'arms': {name: {'samples': [sample_pair(seed) for seed in range(1731, 1763)]} for name in runner.ARMS}}
            for probe in (2392, 711, 3079)]


class ThreeArmGates(unittest.TestCase):
    def test_all_pairs_across_every_case_are_compared(self):
        comparison = runner.comparisons_after_gates(results(), 1731)
        self.assertEqual(len(comparison), 9)
        self.assertEqual(sum(item['probeFrameId'] == 2392 for item in comparison), 3)
        self.assertTrue(all(len(item['pairedSeeds']) == 32 for item in comparison))

    def test_third_arm_is_included_in_exact_negative_control(self):
        for field in ('logits', 'tokenIds', 'decoded'):
            data = results()
            changed = data[0]['arms'][runner.forward.ARM]['samples'][31]['referenceReplay']
            if field == 'logits':
                changed[field][7][0] = .00001
            elif field == 'tokenIds':
                changed[field][7] = 1
            else:
                changed[field]['keys'] = ['W']
            report = {'comparisons': []}
            with self.subTest(field=field), self.assertRaisesRegex(runner.base.GateFailure, 'negative control'):
                report['comparisons'] = runner.comparisons_after_gates(data, 1731)
            self.assertEqual(report['comparisons'], [])

    def test_late_missing_gate_never_publishes_partial_comparisons(self):
        data = results()
        data[-1]['arms'][runner.forward.ARM]['samples'][-1]['conditionalLogitsExact'] = False
        report = {'comparisons': []}
        with self.assertRaisesRegex(runner.base.GateFailure, 'unvalidated'):
            report['comparisons'] = runner.comparisons_after_gates(data, 1731)
        self.assertEqual(report['comparisons'], [])

    def test_missing_arm_seed_vocabulary_or_rng_is_rejected(self):
        for kind in ('arm', 'seed', 'vocabulary', 'rng', 'nonfinite'):
            data = results()
            arm = data[-1]['arms'][runner.forward.ARM]
            sample = arm['samples'][-1]['referenceReplay']
            if kind == 'arm':
                del data[-1]['arms'][runner.forward.ARM]
            elif kind == 'seed':
                sample['seed'] -= 1
            elif kind == 'vocabulary':
                sample['logits'][4].append(0.)
            elif kind == 'rng':
                sample['uniforms'][7] = .6
            else:
                sample['logits'][3][0] = float('nan')
            with self.subTest(kind=kind), self.assertRaises(runner.base.GateFailure):
                runner.comparisons_after_gates(data, 1731)

    def test_noncontrol_contrasts_are_allowed_after_complete_gates(self):
        data = results()
        pair = data[1]['arms'][runner.forward.ARM]['samples'][0]
        for key in ('referenceReplay', 'alternatePlaceholderReplay'):
            pair[key]['logits'][2][0] = .25
            pair[key]['tokenIds'][2] = 1
            pair[key]['decoded']['keys'] = ['W']
        comparison = runner.comparisons_after_gates(data, 1731)
        affected = [item for item in comparison if item['probeFrameId'] == 711 and item['rightArm'] == runner.forward.ARM]
        self.assertEqual(len(affected), 2)
        self.assertTrue(all(item['pairedSeeds'][0]['maxLogitDifferenceByComponent'][2] == .25 for item in affected))

    def test_all_pixels_and_negative_control_tokens_are_exact(self):
        frames = np.zeros((41, 192, 192, 3), dtype=np.uint8)
        tokens = np.zeros((41, 8), dtype=np.int64)
        prepared = [{'probeFrameId': probe, 'arms': {name: {'frames': frames.copy(), 'tokens': tokens.copy()}
                                                   for name in runner.ARMS}} for probe in (2392, 711, 3079)]
        self.assertTrue(runner.verify_prepared_inputs(prepared)['negativeControlAllThreePairsExact'])
        prepared[0]['arms'][runner.forward.ARM]['tokens'][0, 0] = 1
        with self.assertRaisesRegex(runner.base.GateFailure, 'negative-control history'):
            runner.verify_prepared_inputs(prepared)
        prepared[0]['arms'][runner.forward.ARM]['tokens'][0, 0] = 0
        prepared[2]['arms'][runner.forward.ARM]['frames'][40, 0, 0, 0] = 1
        with self.assertRaisesRegex(runner.base.GateFailure, 'model pixels'):
            runner.verify_prepared_inputs(prepared)

    def test_control_contexts_and_every_teacher_head_are_exact(self):
        context = torch.ones(1, 41, 4)
        logits = [torch.ones(1, 41, 3) for _ in range(8)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'report.json'
            report = {'parityGates': [], 'comparisons': []}
            runner.validate_negative_contexts('control', context, logits, (context.clone(), [x.clone() for x in logits]), report, path)
            self.assertEqual(len(report['parityGates']), 9)
            changed = [x.clone() for x in logits]
            changed[7][0, 0, 0] += .00001
            with self.assertRaisesRegex(runner.base.GateFailure, 'negative-control-head-7'):
                runner.validate_negative_contexts('control', context, changed, (context, logits), report, path)
            self.assertEqual(json.loads(path.read_text())['comparisons'], [])


class ReconstructionTests(unittest.TestCase):
    def fixture(self, folder):
        """Write a small complete source episode; no video decoder is used by load_case."""
        path = Path(folder)
        data = evidence(count=50)
        extra = {'widthLimit': 192, 'heightLimit': 192, 'observationPreprocessing': {
            'source': 'native_capture', 'resize': 'fir-5.1.4-interpolation-hamming',
            'pixelFormat': 'rgb24', 'preserveAspectRatio': False}}
        data[0]['hello'].update(extra)
        data[3][0].update(extra)
        (path/'report.json').write_text(json.dumps(data[0]), encoding='utf-8')
        for name, rows in zip(('observations', 'frames', 'events'), data[1:4]):
            (path/(name+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')
        (path/'recording.json').write_text(json.dumps(data[4]), encoding='utf-8')
        (path/'frames.mp4').write_bytes(b'no decode in reconstruction unit test')
        plan = runner.forward.prepare_forward(*data, probe_frame_ids=[45], max_windows=1)
        files = {'report': path/'report.json', **{name: path/name for name in
                 ('observations.jsonl', 'frames.jsonl', 'events.jsonl', 'recording.json', 'frames.mp4')}}
        plan['inputEvidence'] = {key: runner.base.digest(value) for key, value in files.items()}
        plan['preparerEvidence'] = {'forward': runner.base.digest(runner.forward.__file__),
                                    'base': runner.base.digest(runner.forward.base.__file__)}
        target = path/'plan.json'
        target.write_text(json.dumps(plan), encoding='utf-8')
        return target, plan

    def test_exact_reconstruction_precedes_decode_and_retains_goal(self):
        with tempfile.TemporaryDirectory() as folder:
            path, plan = self.fixture(folder)
            case = runner.load_case(path, 45)
            self.assertEqual(runner.base.canonical(case['window']), runner.base.canonical(plan['windows'][0]))
            self.assertEqual(case['armNames'], list(runner.ARMS))
            self.assertEqual(case['preparerEvidence'], plan['preparerEvidence'])
            self.assertEqual(case['window']['goalProvenance'], plan['windows'][0]['goalProvenance'])

    def test_old_schema_changed_preparer_and_changed_labels_are_rejected(self):
        for kind in ('schema', 'preparer', 'label', 'goal'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                path, plan = self.fixture(folder)
                if kind == 'schema':
                    plan['kind'] = 'p2p-offline-history-candidates'
                elif kind == 'preparer':
                    plan['preparerEvidence']['forward']['sha256'] = 'changed'
                elif kind == 'goal':
                    plan['windows'][0]['goalProvenance']['goalMetadata'] = {'instruction': 'invented'}
                else:
                    plan['windows'][0]['arms'][runner.forward.ARM]['samples'][-1]['label']['mouseDx'] += 1
                path.write_text(json.dumps(plan), encoding='utf-8')
                with self.assertRaises(runner.base.GateFailure):
                    runner.load_case(path, 45)

    def test_modified_source_and_unselected_probe_fail_before_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            path, plan = self.fixture(folder)
            with self.assertRaisesRegex(runner.base.GateFailure, 'absent or ambiguous'):
                runner.load_case(path, 46)
            Path(plan['inputEvidence']['events.jsonl']['path']).write_text('{}\n', encoding='utf-8')
            with self.assertRaisesRegex(runner.base.GateFailure, 'changed prepared input'):
                runner.load_case(path, 45)


if __name__ == '__main__':
    unittest.main()
