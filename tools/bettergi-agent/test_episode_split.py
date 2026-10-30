"""Evidence completeness never overrides an explicitly reserved holdout split."""
import json
from pathlib import Path
import tempfile
import unittest

from episode_split import read_split,reserve_split,require_fit_allowed


class EpisodeSplitTests(unittest.TestCase):
    """Use immutable synthetic resident manifests; no model fitting, GPU allocation or game access."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name)
        (self.folder/'patrol.json').write_text('{"runId":"original"}')

    def test_holdout_reservation_is_idempotent_and_cannot_be_relabeled(self):
        self.assertIsNone(read_split(self.folder,'original'))
        expected=reserve_split(self.folder,'original','holdout')
        self.assertEqual(read_split(self.folder,'original'),expected)
        self.assertEqual(reserve_split(self.folder,'original','holdout'),expected)
        with self.assertRaisesRegex(ValueError,'different reserved split'):
            reserve_split(self.folder,'original','train')
        self.assertEqual(read_split(self.folder,'original'),expected)

    def test_changed_source_or_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'original resident run'):
            reserve_split(self.folder,'different','holdout')
        self.assertFalse((self.folder/'experience-split.json').exists())
        reserve_split(self.folder,'original','holdout')
        with self.assertRaisesRegex(ValueError,'original source'):read_split(self.folder,'different')
        (self.folder/'patrol.json').write_text('{"runId":"original","changed":true}')
        with self.assertRaisesRegex(ValueError,'original source'):read_split(self.folder,'original')

    def test_fit_rejects_holdout_diagnostic_and_unknown_split(self):
        require_fit_allowed([dict(datasetSplit='train'),{}])
        for split in ('holdout','diagnostic','unknown'):
            with self.subTest(split=split),self.assertRaisesRegex(ValueError,'cannot be used for fitting'):
                require_fit_allowed([{},dict(datasetSplit=split)])

    def test_malformed_reservation_fails_closed(self):
        path=self.folder/'experience-split.json'
        for raw in (json.dumps(dict(format='wrong',split='train')),' '*4097):
            path.write_text(raw)
            with self.assertRaises(ValueError):read_split(self.folder,'original')
