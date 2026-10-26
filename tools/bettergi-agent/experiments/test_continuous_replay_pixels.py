"""CPU-only evidence checks for decoding continuous recorded sessions."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import continuous_replay_pixels as pixels
import prepare_replay_session as session
from test_prepare_replay_session import continuous_evidence


class ContinuousPixelEvidenceTests(unittest.TestCase):
    """Ensure cached candidate JSON cannot substitute different frames or action labels."""

    def setUp(self):
        """Use a real synthetic lease join with a receipt crossing the video boundary."""
        self.segments = continuous_evidence()
        self.plan = session.prepare_session(self.segments, history_frames=4, max_windows=1,
                                            probe_frame_ids=[14], comparison_mode='same-frames-only')
        self.assertEqual(self.plan['status'], 'prepared')

    def test_reconstructs_complete_source_plan(self):
        """Input file fingerprints are separate from the deterministically rebuilt plan."""
        self.plan['inputEvidence'] = {}
        actual = pixels.validate_document(self.plan, self.segments)
        self.assertEqual(actual['windows'], self.plan['windows'])
        self.assertFalse(actual['trainingEligible'])

    def test_rejects_changed_probe_video_index(self):
        """A valid frame identity cannot be pointed at a different encoded image."""
        self.plan['windows'][0]['probe']['videoFrameIndex'] += 1
        with self.assertRaisesRegex(session.base.EvidenceError, 'rebuild_mismatch'):
            pixels.validate_document(self.plan, self.segments)

    def test_rejects_changed_receipt_label(self):
        """The decoder must reconstruct action labels even though it does not train on them."""
        label = self.plan['windows'][0]['arms']['receipt_same_frames']['samples'][0]['label']
        self.assertIn('heldKeys', label)
        label['heldKeys'] = ['P']
        with self.assertRaisesRegex(session.base.EvidenceError, 'rebuild_mismatch'):
            pixels.validate_document(self.plan, self.segments)

    def test_rejects_changed_source_clock(self):
        """Video PTS cannot replace or silently shift the original action-label clock."""
        self.plan['windows'][0]['probe']['labelTimeMs'] += 0.001
        with self.assertRaisesRegex(session.base.EvidenceError, 'rebuild_mismatch'):
            pixels.validate_document(self.plan, self.segments)

    def test_requires_continuous_schema(self):
        """Single-video candidates need their own reader and cannot be reinterpreted here."""
        self.plan['kind'] = 'p2p-offline-history-candidates'
        with self.assertRaisesRegex(session.base.EvidenceError, 'continuous_plan_required'):
            pixels.validate_document(self.plan, self.segments)

    def test_loader_rejects_failed_plan_before_source_io(self):
        """A previously rejected lease must not reach sidecar hashing or video decoding."""
        failed = dict(schemaVersion=1, joinVersion=1, kind=self.plan['kind'], status='rejected')
        path = Mock()
        path.stat.return_value.st_size = 64
        with patch.object(session, '_read_json', return_value=failed), \
                patch.object(session.base, '_file_evidence') as source_reader, \
                patch.object(pixels.decoder, 'decode_indexed') as video_reader:
            with self.assertRaisesRegex(session.base.EvidenceError, 'continuous_plan_not_prepared'):
                pixels.load_plan(path)
            source_reader.assert_not_called()
            video_reader.assert_not_called()

    def test_deduplicates_both_arms_with_original_local_indexes(self):
        """One history crosses segments without concatenating their local video indexes."""
        original = copy.deepcopy(self.plan)
        references = pixels.collect_references(self.plan)
        self.assertEqual(set(references), {9, 10, 11, 12, 13, 14})
        self.assertEqual((references[9]['recordingSegment'], references[9]['videoFrameIndex']), (1, 8))
        self.assertEqual((references[10]['recordingSegment'], references[10]['videoFrameIndex']), (1, 9))
        self.assertEqual((references[13]['recordingSegment'], references[13]['videoFrameIndex']), (2, 0))
        self.assertEqual(self.plan, original)

    def test_rejects_disagreeing_addresses_for_one_frame(self):
        """Duplicate image references may be collapsed only when all provenance agrees."""
        self.plan['windows'][0]['arms']['receipt_same_frames']['anchor']['videoFile'] += '.different'
        with self.assertRaisesRegex(session.base.EvidenceError, 'conflicting_frame_reference'):
            pixels.collect_references(self.plan)


if __name__ == '__main__':
    unittest.main()
