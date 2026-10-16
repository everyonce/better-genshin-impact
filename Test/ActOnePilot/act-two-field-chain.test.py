import importlib.util
import unittest
from pathlib import Path
from copy import deepcopy

path = Path(__file__).resolve().parents[2]/'tools/quest-pilot/act-two-field-chain.py'
spec = importlib.util.spec_from_file_location('chain', path)
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.receipt = dict(submittedId='r', terminalId='r', session='s', frameId=4, status='stopped',
                            result=dict(fieldFrameId=2, pauseVerified=True, pauseProof=dict(verified=True, session='s')))
        self.observation = dict(session='s', frameId=2, hud=dict(world=True, health=dict(current=3981, max=4015),
            enemyBars=[], objectives=['Go to the exam point']))

    def test_valid_verified_transition(self):
        self.assertEqual(chain.next_checkpoint(self.receipt, 'r', 's', 1, self.observation), (4, 2))

    def test_uncertain_or_wrong_receipt_cannot_continue(self):
        for key, value in [('terminalId', None), ('submittedId', 'other'), ('session', 'other'), ('frameId', 1), ('status', 'failed')]:
            with self.subTest(key=key):
                receipt = deepcopy(self.receipt)
                receipt[key] = value
                with self.assertRaises(ValueError):
                    chain.next_checkpoint(receipt, 'r', 's', 1, self.observation)

    def test_unverified_pause_or_changed_field_cannot_continue(self):
        receipt = deepcopy(self.receipt)
        receipt['result']['pauseProof']['verified'] = False
        with self.assertRaises(ValueError):
            chain.next_checkpoint(receipt, 'r', 's', 1, self.observation)
        for key, value in [('health', dict(current=3000, max=4015)), ('enemyBars', [{}]), ('objectives', ['Different quest']), ('world', False)]:
            observation = deepcopy(self.observation)
            observation['hud'][key] = value
            with self.assertRaises(ValueError):
                chain.next_checkpoint(self.receipt, 'r', 's', 1, observation)


if __name__ == '__main__':
    unittest.main()
