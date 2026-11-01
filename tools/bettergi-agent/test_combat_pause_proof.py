"""Verify bounded revision reuse without altering native UTF-16 semantics or source checks."""
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import combat_pause_proof as proof


def reference_revision(raw):
    """Compute native UTF-16 units independently, including surrogate pairs for non-BMP text."""
    value = 2166136261
    for character in raw.decode('utf-8-sig'):
        point = ord(character)
        units = (point,) if point <= 0xffff else (0xd800 + ((point - 0x10000) >> 10), 0xdc00 + ((point - 0x10000) & 1023))
        for unit in units:
            value = ((value ^ unit) * 16777619) & 0xffffffff
    return format(value, 'x')


class RevisionCacheTests(unittest.TestCase):
    """A hit saves only the deterministic FNV loop and retains bounded content metadata."""
    def setUp(self):
        """Give each test a fresh process-local cache and clean it afterward."""
        self.clear_cache()
        self.addCleanup(self.clear_cache)

    def clear_cache(self):
        """Reset only the inert revision metadata under its existing lock."""
        with proof._revision_cache_lock:
            proof._revision_cache.clear()

    def test_cold_and_warm_ascii_bom_unicode_and_surrogate_parity(self):
        """Cached and uncached results preserve exact leading-BOM and UTF-16 code-unit behavior."""
        cases = [b'', b'hello', b'\xef\xbb\xbfhello', 'caf\u00e9 \u4f60\u597d'.encode(),
                 '\U0001f642\U0001d11e'.encode(), 'a\ufeffb\x00c'.encode(), b'\xef\xbb\xbf']
        self.assertEqual(reference_revision(b'hello'), '4f9f2cab')
        self.assertEqual(reference_revision(b''), '811c9dc5')
        with patch.object(proof, '_uncached_revision', wraps=proof._uncached_revision) as calculate:
            for raw in cases:
                self.assertEqual(proof.revision(raw), reference_revision(raw))
            for raw in reversed(cases):
                self.assertEqual(proof.revision(raw), reference_revision(raw))
            self.assertEqual(calculate.call_count, len(cases))
        self.assertEqual(set(proof._revision_cache), {hashlib.sha256(raw).digest() for raw in cases})

    def test_changed_bytes_at_same_path_size_and_mtime_are_recalculated(self):
        """A rewritten script cannot inherit the previous content's revision from filesystem metadata."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'main.js'
            path.write_bytes(b'const answer = 1;')
            stamp = path.stat()
            first = proof.revision(path.read_bytes())
            path.write_bytes(b'const answer = 2;')
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            self.assertEqual((path.stat().st_size, path.stat().st_mtime_ns), (stamp.st_size, stamp.st_mtime_ns))
            second = proof.revision(path.read_bytes())
            self.assertEqual(second, reference_revision(b'const answer = 2;'))
            self.assertNotEqual(first, second)
        self.assertEqual(len(proof._revision_cache), 2)

    def test_cache_bound_evicts_least_recent_content_and_keeps_only_small_metadata(self):
        """The actual fixed limit applies even when scripts change repeatedly in one process."""
        rows = [f'// version {index}'.encode() for index in range(proof._REVISION_CACHE_LIMIT + 1)]
        for raw in rows[:-1]:
            proof.revision(raw)
        proof.revision(rows[0])
        proof.revision(rows[-1])
        self.assertEqual(len(proof._revision_cache), 128)
        self.assertIn(hashlib.sha256(rows[0]).digest(), proof._revision_cache)
        self.assertNotIn(hashlib.sha256(rows[1]).digest(), proof._revision_cache)
        self.assertTrue(all(type(key) is bytes and len(key) == 32 and type(value) is str and 1 <= len(value) <= 8
                            for key, value in proof._revision_cache.items()))
        with patch.object(proof, '_uncached_revision', wraps=proof._uncached_revision) as calculate:
            self.assertEqual(proof.revision(rows[1]), reference_revision(rows[1]))
            self.assertEqual(calculate.call_count, 1)
        self.assertEqual(len(proof._revision_cache), 128)

    def test_invalid_encoding_never_enters_cache_and_remains_an_error(self):
        """A failed UTF-8 decode cannot become a successful cached revision."""
        for _ in range(2):
            with self.assertRaises(UnicodeDecodeError):
                proof.revision(b'\xff')
        self.assertFalse(proof._revision_cache)

    def test_mutable_input_keeps_uncached_decoder_behavior(self):
        """Mutable callers remain uncached so changes cannot poison an immutable-content key."""
        raw = bytearray(b'hello')
        self.assertEqual(proof.revision(raw), reference_revision(bytes(raw)))
        raw[0] = ord('j')
        self.assertEqual(proof.revision(raw), reference_revision(bytes(raw)))
        self.assertFalse(proof._revision_cache)

    def test_warm_ui_proof_still_reads_and_rejects_changed_installed_or_archived_source(self):
        """Revision hits cannot conceal a changed file in the real native-proof validator."""
        from test_combat_trial import OWNER, ui_transition_fixture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            live = root / 'artifacts/live'
            live.mkdir(parents=True)
            folder = ui_transition_fixture(SimpleNamespace(root=root, live=live), 'pause')
            with patch.object(proof, '_uncached_revision', wraps=proof._uncached_revision) as calculate:
                proof.inspect_transition(folder, OWNER, 'pause', root=root)
                self.assertEqual(calculate.call_count, 0)
                paths = [root / 'artifacts/release/BetterGI-English-win-x64/User/JsScript/ActOnePilot/main.js',
                         folder / 'source-snapshot/main.js']
                for path in paths:
                    raw = path.read_bytes()
                    try:
                        path.write_bytes(raw + b' changed')
                        with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Native UI source bytes changed'):
                            proof.inspect_transition(folder, OWNER, 'pause', root=root)
                    finally:
                        path.write_bytes(raw)
                self.assertEqual(calculate.call_count, 0)


if __name__ == '__main__':
    unittest.main()
