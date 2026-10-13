"""No deletion: inventory excludes user data and requires exact preserved bytes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).parents[2] / 'tools' / 'quest-pilot' / 'storage-cleanup.py'
spec = importlib.util.spec_from_file_location('storage_cleanup', MODULE)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class CleanupSafety(unittest.TestCase):
    def test_only_identical_non_user_build_files_are_candidates(self):
        with tempfile.TemporaryDirectory(prefix='BetterGI-cleanup-test-') as directory:
            repo = Path(directory)
            source = repo / 'artifacts' / 'r15-native-publish'
            keep = repo / 'artifacts' / 'release-r15' / 'BetterGI-English-win-x64'
            for root in (source, keep):
                (root / 'User').mkdir(parents=True)
                (root / 'Logs').mkdir()
                (root / 'same.dll').write_bytes(b'same')
                (root / 'changed.dll').write_bytes(b'old' if root == source else b'new')
                (root / 'User' / 'settings.json').write_text('{}')
                (root / 'Logs' / 'evidence.log').write_text('preserve')
            result = cleanup.plan(repo)
            self.assertEqual(result['files'], 1)
            self.assertEqual(result['bytes'], 4)
            self.assertEqual(result['candidates'][0]['path'], str(source / 'same.dll'))
            self.assertTrue((source / 'same.dll').exists())
            self.assertTrue((source / 'User' / 'settings.json').exists())

    def test_missing_preserved_copy_is_never_a_candidate(self):
        with tempfile.TemporaryDirectory(prefix='BetterGI-cleanup-test-') as directory:
            repo = Path(directory)
            source = repo / 'artifacts' / 'r15-native-publish'
            source.mkdir(parents=True)
            (source / 'unique.dll').write_bytes(b'unique')
            self.assertEqual(cleanup.plan(repo)['files'], 0)


if __name__ == '__main__':
    unittest.main()
