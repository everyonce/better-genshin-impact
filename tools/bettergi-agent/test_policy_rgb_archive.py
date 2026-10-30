"""Exact-pixel provenance and budget refusal; no native input, game, or GPU model."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import stream_client as client
from observation_profiles import P2P_NATIVE
from policy_rgb_archive import RGB192_BYTES, verify_policy_rgb, write_policy_rgb
from stream_segments import RecordingBudget
from test_recorder_metadata import MemoryEncoder, observed_frame
from test_stream_client import HeldRecorder


class PolicyRgbTests(unittest.TestCase):
    """Exercise the actual asynchronous writer and original-source checks."""
    def record(self, root, *, budget=1024*1024, shared=None, count=2):
        """Admit immutable wire frames while the writer is held, then drain through the real recorder."""
        recorder = HeldRecorder(Path(root)/'episode','synthetic-encoder',20,budget,
                                retain_policy_rgb=True,shared_budget=shared)
        pixels = bytes(range(256))*(RGB192_BYTES//256)
        try:
            with patch.object(client.json,'dumps',side_effect=AssertionError('Producer performed serialization')):
                for index in range(1,count+1):
                    metadata=dict(observed_frame(index),width=192,height=192,policyRgb={'file':'forged.rgb'})
                    self.assertTrue(recorder.put(metadata,pixels))
            self.assertFalse(recorder.directory.exists())
        finally:
            recorder.release_writer.set()
            result=recorder.close()
        return recorder,result,pixels

    def test_exact_original_bytes_and_index_survive_the_worker_boundary(self):
        with tempfile.TemporaryDirectory() as root, patch.object(client.subprocess,'Popen',return_value=MemoryEncoder()):
            recorder,result,pixels=self.record(root)
            self.assertTrue(result['complete'] and result['lossless'],result)
            self.assertEqual((result['encodedFrames'],result['policyRgbFrames'],result['policyRgbBytes']),(2,2,2*len(pixels)))
            rows=[json.loads(line) for line in (recorder.directory/'frames.jsonl').read_text().splitlines()]
            for index,row in enumerate(rows):
                raw=verify_policy_rgb(recorder.directory,row['policyRgb'])
                self.assertEqual(raw.read_bytes(),pixels)
                self.assertEqual(row['policyRgb']['sha256'],hashlib.sha256(pixels).hexdigest())
                self.assertEqual((row['frameId'],row['videoFrameIndex']),(index+1,index))
            observations=[json.loads(line) for line in (recorder.directory/'observations.jsonl').read_text().splitlines()]
            self.assertTrue(all('policyRgb' not in row for row in observations))
            self.assertGreaterEqual(result['recordedBytes'],2*len(pixels))

    def test_budget_stops_before_a_second_raw_file_is_written(self):
        with tempfile.TemporaryDirectory() as root, patch.object(client.subprocess,'Popen',return_value=MemoryEncoder()):
            recorder,result,_=self.record(root,budget=200*1024)
            self.assertFalse(result['complete'])
            self.assertIn('byte budget',result['error'])
            self.assertEqual(result['policyRgbFrames'],1)
            self.assertEqual(len(list(recorder.directory.glob('*.rgb'))),1)
            self.assertLess(result['recordedBytes'],200*1024)

    def test_retiring_segment_usage_is_reserved_before_any_raw_write(self):
        with tempfile.TemporaryDirectory() as root, patch.object(client.subprocess,'Popen',return_value=MemoryEncoder()):
            shared=RecordingBudget(150*1024)
            shared.update('retiring',60*1024)
            recorder,result,_=self.record(root,budget=shared.maximum,shared=shared,count=1)
            self.assertFalse(result['complete'])
            self.assertEqual(result['policyRgbFrames'],0)
            self.assertEqual(list(recorder.directory.glob('*.rgb')),[])

    def test_changed_truncated_or_redirected_pixels_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)
            pixels=bytes(RGB192_BYTES)
            reference=write_policy_rgb(directory,0,dict(frameId=1,width=192,height=192),pixels)
            path=verify_policy_rgb(directory,reference)
            path.write_bytes(b'X'+pixels[1:])
            with self.assertRaisesRegex(ValueError,'bytes changed'):verify_policy_rgb(directory,reference)
            path.write_bytes(pixels[:-1])
            with self.assertRaisesRegex(ValueError,'size differs'):verify_policy_rgb(directory,reference)
            with self.assertRaisesRegex(ValueError,'path or size'):verify_policy_rgb(directory,dict(reference,file='../outside.rgb'))

    def test_cli_requires_the_bounded_native_pixel_profile(self):
        valid=['--retain-policy-rgb','--record-dir','unused','--record-max-mib','160','--observation-profile',P2P_NATIVE,
               '--output','unused.json']
        self.assertTrue(client.parse_arguments(valid).retain_policy_rgb)
        for changed in (valid[:5]+valid[7:],valid[:4]+['161']+valid[5:],['--retain-policy-rgb','--output','unused.json']):
            with self.subTest(argv=changed),self.assertRaises(SystemExit):client.parse_arguments(changed)


if __name__=='__main__':unittest.main()
