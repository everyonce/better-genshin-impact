"""Check the upstream instruction-space contract and stable graph input storage."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import torch

from goal_embedding import ENCODER, POOLING, load_goal, masked_mean
from model_adapters import OpenP2PAdapter


class GoalEmbeddingTests(unittest.TestCase):
    def document(self):
        return {'version': 1, 'encoder': ENCODER, 'pooling': POOLING, 'maxLength': 128,
                'instruction': 'Walk along the street.', 'embedding': np.ones((1, 768)).tolist()}

    def test_masked_mean_ignores_padding_and_does_not_normalize(self):
        features = torch.tensor([[[2., 4.], [4., 8.], [9000., 9000.]]])
        actual = masked_mean(features, torch.tensor([[1, 1, 0]]))
        torch.testing.assert_close(actual, torch.tensor([[3., 6.]]), rtol=0, atol=0)

    def test_loader_rejects_wrong_space_shape_and_nonfinite_values(self):
        cases = [{'encoder': 'different/model'}, {'pooling': 'normalized'}, {'maxLength': 2048},
                 {'embedding': [[1.]*767]}, {'embedding': [[float('nan')]*768]},
                 {'embedding': [[0.]*768]}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'goal.json'
            for changed in cases:
                with self.subTest(changed=list(changed)):
                    path.write_text(json.dumps(dict(self.document(), **changed)))
                    with self.assertRaises(ValueError):
                        load_goal(path)

    def test_goal_change_and_reset_keep_graph_storage_and_clear_old_history(self):
        policy = object.__new__(OpenP2PAdapter)
        policy.dtype, policy.text = torch.float32, torch.zeros((1, 768))
        policy.metadata, policy._pending_feedback = {}, False
        valid = torch.tensor(12)
        policy.temporal_cache = SimpleNamespace(reset=lambda: valid.zero_())
        policy.graph, policy.static_idx = object(), torch.tensor(9)
        policy.static_state = [SimpleNamespace(k_cache=torch.ones(3), v_cache=torch.ones(3))]
        graph, address = policy.graph, policy.text.data_ptr()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'goal.json'
            path.write_text(json.dumps(self.document()))
            policy.set_goal(path)
            policy.reset()
            self.assertIs(policy.graph, graph)
            self.assertEqual(policy.text.data_ptr(), address)
            self.assertTrue(torch.equal(policy.text, torch.ones((1, 768))))
            self.assertEqual((policy.static_idx.item(), valid.item()), (0, 0))
            self.assertEqual(torch.count_nonzero(policy.state[0].k_cache).item(), 0)
            path.write_text(json.dumps(dict(self.document(), embedding=[[-2.]*768])))
            policy.set_goal(path)
            self.assertIs(policy.graph, graph)
            self.assertEqual(policy.text.data_ptr(), address)
            self.assertTrue(torch.equal(policy.text, torch.full((1, 768), -2.)))
            policy._pending_feedback = True
            with self.assertRaisesRegex(RuntimeError, 'Resolve'):
                policy.set_goal(path)


if __name__ == '__main__':
    unittest.main()
