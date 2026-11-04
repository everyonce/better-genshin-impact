"""Inert JSONL regression tests: exact rows, refusal order, and one decode per row."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import policy_rgb_archive as archive


class RecordingJsonlDecodeTests(unittest.TestCase):
    """Exercise both historical bytes and sealed gzip without a recorder or pipe."""

    def fixture(self, root, name, raw, compressed):
        """Create a complete synthetic transport declaration for one tested journal."""
        if not compressed:
            (root / name).write_bytes(raw)
            return
        references = {}
        for logical in archive.JOURNAL_NAMES:
            with archive.RecordingJournal(root, logical) as journal:
                if logical == name:
                    for line in raw.decode('utf-8').splitlines(keepends=True):
                        journal.write(line)
            references[logical] = journal.reference()
        (root / 'recording.json').write_text(json.dumps({
            'recordingFormat': archive.RECORDING_FORMAT,
            'journalFiles': references, 'policyRgbStoredBytes': 0}), encoding='utf-8')

    def test_each_row_decoded_once_with_order_and_digest_preserved(self):
        for compressed in (False, True):
            for name in archive.JOURNAL_NAMES:
                with self.subTest(compressed=compressed, name=name), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    expected = [{'frameId': index, 'nested': {'label': '像素'}} for index in (3, 1, 3)]
                    raw = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in expected).encode('utf-8')
                    self.fixture(root, name, raw, compressed)
                    original = archive.json.loads
                    calls = []
                    def counted(value, *args, **kwargs):
                        if isinstance(value, bytes) and b'frameId' in value:
                            calls.append(value)
                        return original(value, *args, **kwargs)
                    with patch.object(archive.json, 'loads', side_effect=counted):
                        rows, digest = archive.read_recording_jsonl(root, name)
                    self.assertEqual(rows, expected)
                    self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
                    self.assertEqual(len(calls), len(expected))
                    self.assertIsNot(rows[0], rows[2])
                    with archive.open_recording_jsonl(root / name) as stream:
                        self.assertEqual(stream.read(), raw.decode('utf-8'))

    def test_historical_blank_lines_keep_digest_but_are_not_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'\n {"frameId": 1}\n \n'
            self.fixture(root, 'events.jsonl', raw, False)
            self.assertEqual(archive.read_recording_jsonl(root, 'events.jsonl'),
                             ([{'frameId': 1}], hashlib.sha256(raw).hexdigest()))

    def test_refusal_order_and_format_validation_unchanged(self):
        cases = [
            ('events.jsonl', b'[]\n{bad}\n', ValueError, 'Invalid recording journal row'),
            ('observations.jsonl', b'[]\n{bad}\n', json.JSONDecodeError, None),
            ('observations.jsonl', b'[]\n', ValueError, 'Invalid recording journal row'),
            ('events.jsonl', b'{"type":"episodeStart","recordingFormat":"forged"}\n', ValueError,
             'Historical journal retains an undeclared recording format'),
            ('frames.jsonl', b'{"policyRgb":{"encoding":"png-rgb24-v1"}}\n', ValueError,
             'Policy RGB reference differs from the journal recording format'),
        ]
        for name, raw, error, message in cases:
            with self.subTest(name=name, raw=raw), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root, name, raw, False)
                with self.assertRaises(error) as caught:
                    archive.read_recording_jsonl(root, name)
                if message:
                    self.assertEqual(str(caught.exception), message)

    def test_corrupt_transport_and_row_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 'events.jsonl', b'{"frameId":1}\n', True)
            with self.assertRaisesRegex(ValueError, 'Invalid compressed journal reference'):
                archive.read_recording_jsonl(root, 'events.jsonl', max_decoded_bytes=1)
            path = root / 'events.jsonl.gz'
            raw = bytearray(path.read_bytes())
            raw[-1] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'Compressed journal bytes changed'):
                archive.read_recording_jsonl(root, 'events.jsonl')


if __name__ == '__main__':
    unittest.main()
