"""Keep the raw source separate from the independently decoded frame on a paired holdout."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_landmark_episode import original_views


class OriginalViewTests(unittest.TestCase):
    """A valid first-capture payload may have different bytes from its lossy archived video frame."""

    def test_separate_raw_digest_and_exact_source_clock(self):
        raw=bytes(192*192*3)
        digest=hashlib.sha256(raw).hexdigest()
        prediction={'station':'stair-front','squaredDistance':0.0}
        class Head:
            """Only the original byte string reproduces this test observer."""
            def predict(self,data):
                return prediction if data==raw else None
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'00001').mkdir()
            marker=dict(type='landmarkShadowSource',frameId=7,captureEpoch='epoch',sourceTimestamp100ns=100,
                        rgbSha256=digest)
            payload=dict(marker,rgb24Base64=base64.b64encode(raw).decode('ascii'))
            (folder/'00001'/'events.jsonl').write_text(json.dumps(payload)+'\n')
            source=dict(marker,segment=1,prediction=prediction)
            video=dict(frameId=7,captureEpoch='epoch',sourceTimestamp100ns=100,segment=1,rgbSha256='f'*64)
            decoded=({},[],{7:(b'video',video)})
            run={'segments':[{'number':1}]}
            archive=dict(sources=[source],sourceCount=1)
            meta,_,samples=original_views(run,folder,archive,decoded,Head())
            self.assertEqual(samples[7][1]['rgbSha256'],digest)
            self.assertNotEqual(meta['evidenceSha256'],video['rgbSha256'])
            self.assertEqual(video['rgbSha256'],'f'*64)
            video['sourceTimestamp100ns']+=1
            with self.assertRaisesRegex(ValueError,'source identity differs'):
                original_views(run,folder,archive,decoded,Head())


if __name__=='__main__':
    unittest.main()
