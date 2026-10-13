import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installed_retention', Path(__file__).resolve().parents[2] / 'tools/quest-pilot/validate-installed-retention.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RequestReplacementTests(unittest.TestCase):
    def test_transient_lock_retries_same_request(self):
        error = PermissionError('sharing lock')
        error.winerror = 5
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'request.json'
            with patch.object(module.os, 'replace', side_effect=[error, None]) as replace, patch.object(module.time, 'sleep'):
                module.submit_observation(target, {'id': 'mission-fixed', 'mission': 'observe'})
            self.assertEqual(replace.call_args_list[0], replace.call_args_list[1])
            self.assertEqual(2, replace.call_count)

    def test_persistent_denial_is_not_ignored(self):
        error = PermissionError('persistent denial')
        error.winerror = 5
        with tempfile.TemporaryDirectory() as directory, patch.object(module.os, 'replace', side_effect=error) as replace, patch.object(module.time, 'sleep'):
            with self.assertRaises(PermissionError):
                module.submit_observation(Path(directory) / 'request.json', {'mission': 'observe'})
            self.assertEqual(6, replace.call_count)

    def test_unrelated_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module.os, 'replace', side_effect=OSError('disk error')) as replace:
            with self.assertRaises(OSError):
                module.submit_observation(Path(directory) / 'request.json', {'mission': 'observe'})
            self.assertEqual(1, replace.call_count)


if __name__ == '__main__':
    unittest.main()
