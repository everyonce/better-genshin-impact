"""CPU-only tests for exact sequential replay gates, with no model construction."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import torch
import p2p_replay_sequential_sensitivity as sequential


class SequentialGates(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / 'report.json'
        self.report = {'parityGates': [], 'comparisonEligible': False, 'comparisons': []}
        self.context = torch.arange(41*4, dtype=torch.float32).reshape(1, 41, 4)
        self.logits = [torch.ones(1, 41, 3)*index for index in range(8)]

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self, context=None, logits=None):
        return sequential.validate_replays('fixture', self.context, self.context.clone() if context is None else context,
                                            self.logits, [x.clone() for x in self.logits] if logits is None else logits,
                                            self.report, self.path)

    def test_repeated_history_and_probe_context_are_exact_gates(self):
        result = self.validate()
        self.assertEqual(len(result), 7)
        self.assertEqual(len(self.report['parityGates']), 10)
        self.assertTrue(all(gate['passed'] and gate['rtol'] == gate['atol'] == 0 for gate in self.report['parityGates']))

    def test_probe_placeholder_may_change_later_teacher_forced_heads(self):
        changed = [x.clone() for x in self.logits]
        changed[3][:, -1] += 10
        differences = self.validate(logits=changed)
        self.assertEqual(differences[2]['maxAbsoluteDifference'], 10)
        self.assertFalse(differences[2]['comparisonGate'])

    def test_probe_context_change_is_blocked_and_evidence_kept(self):
        changed = self.context.clone()
        changed[:, -1, 0] += .0001  # Even a sub-1e-3 deviation fails this exact contract.
        with self.assertRaisesRegex(sequential.base.GateFailure, 'numerical parity'):
            self.validate(context=changed)
        saved = json.loads(self.path.read_text())
        self.assertFalse(saved['parityGates'][0]['passed'])
        self.assertEqual(saved['parityGates'][0]['atol'], 0)
        self.assertEqual(saved['comparisons'], [])

    def test_history_teacher_forced_change_is_never_exempted(self):
        changed = [x.clone() for x in self.logits]
        changed[3][:, -2] += .0001
        with self.assertRaisesRegex(sequential.base.GateFailure, 'history-logits-3'):
            self.validate(logits=changed)

    def test_first_probe_head_is_independent_of_placeholder_and_must_match(self):
        changed = [x.clone() for x in self.logits]
        changed[0][:, -1] += .0001
        with self.assertRaisesRegex(sequential.base.GateFailure, 'probe-first-logits'):
            self.validate(logits=changed)

    @staticmethod
    def sample(seed=1731):
        return {'seed': seed, 'uniforms': [.5]*8, 'tokenIds': [0]*8,
                'decoded': {'keys': [], 'mouseButtons': [], 'dx': 0, 'dy': 0},
                'logits': [[0., 1.]]*8}

    def test_equal_actions_do_not_excuse_changed_conditional_logits(self):
        sample = self.sample()
        logits = [torch.tensor([[[0., 1.]]]) for _ in range(8)]
        alternate = [x.clone() for x in logits]
        alternate[7][0, 0, 0] += .0001
        with self.assertRaisesRegex(sequential.base.GateFailure, 'conditional-logits-7'):
            sequential.validate_sample_pair('sample', sample, copy.deepcopy(sample), logits, alternate, self.report, self.path)

    def test_rng_and_complete_action_mismatches_fail(self):
        logits = [torch.ones(1, 1, 2) for _ in range(8)]
        for field, value in [('seed', 99), ('uniforms', [.6]*8), ('tokenIds', [1]*8),
                             ('decoded', {'keys': ['W'], 'mouseButtons': [], 'dx': 0, 'dy': 0})]:
            first, changed = self.sample(), self.sample()
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(sequential.base.GateFailure):
                sequential.validate_sample_pair('sample', first, changed, logits, logits, self.report, self.path)

    def test_identical_input_negative_control_requires_exact_cross_arm_outputs(self):
        samples = [{'referenceReplay': self.sample(seed)} for seed in range(32)]
        case = {'key': 'control', 'probeFrameId': 2392,
                'arms': {'accepted_proxy': {'samples': samples}, 'receipt_same_frames': {'samples': copy.deepcopy(samples)}}}
        self.assertEqual(len(sequential.comparisons_after_gates([case], 2392)), 1)
        case['arms']['receipt_same_frames']['samples'][4]['referenceReplay']['logits'][0] = [0., 1.00001]
        with self.assertRaisesRegex(sequential.base.GateFailure, 'negative control'):
            sequential.comparisons_after_gates([case], 2392)


if __name__ == '__main__':
    unittest.main()
