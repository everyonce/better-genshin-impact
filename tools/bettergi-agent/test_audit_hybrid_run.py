"""Tampered local evidence must not become a verified gameplay result."""
import json
from pathlib import Path
import tempfile
import unittest

from audit_hybrid_run import audit
from hybrid_navigation import END


class HybridAuditTests(unittest.TestCase):
    def fixture(self, root, change=None):
        frames = []
        samples = []
        for number, at in enumerate((50, 200, 300, 400), 1):
            pose = dict(state='valid', frameId=number, x=END[0], y=END[1], yawDegrees=47,
                        layerId='City_102', positionConfidence=.999, yawConfidence=.6)
            frames.append(dict(frameId=number, capturedAtMs=at, sourceFrame=dict(captureEpoch='epoch', capturedAtMs=at),
                               navigationPose=pose, frameWorldReadiness=dict(ready=True)))
            if number > 1:
                samples.append({k:pose[k] for k in ('frameId', 'x', 'y', 'yawDegrees')} | dict(atMs=at))
        endpoint = dict(type='hybridEndpointVerified', completedLegs=1, endpoint='end',
                        releaseAtMs=100, sourceEpoch='epoch', samples=samples)
        part = dict(status='completed', hello=dict(sessionId='session', ownerEpoch='owner'),
                    recording=dict(complete=True, workerRetired=True),
                    hybridNavigationEvents=[dict(type='hybridStartVerified', target='end', frameId=1, atMs=50), endpoint],
                    hybridNavigation=dict(completedLegs=1),
                    decisions=[dict(frameId=1, observationTimestampMs=50,
                                    acceptance=dict(type='accepted', requestId='action'),
                                    hybridNavigation=dict(owner='hybrid-native'))],
                    receipts=[dict(requestId='action', frameId=1, modelId='hybrid-native',
                                   appliedSteps=[dict(startedAtMs=75)])])
        run = dict(status='completed', evidenceComplete=True, modelLoads=1, inputRequested=True,
                   acceptedInputActions=1, segments=[dict(number=1, report='part.json')])
        if change:
            change(run, part, frames)
        recording = root/'recording'/'00001'
        recording.mkdir(parents=True)
        (recording/'observations.jsonl').write_text('\n'.join(json.dumps(v) for v in frames), encoding='utf-8')
        (root/'part.json').write_text(json.dumps(part), encoding='utf-8')
        (root/'run.json').write_text(json.dumps(run), encoding='utf-8')
        return audit(root/'run.json', root/'recording', repository=root)

    def test_complete_joined_evidence_passes_without_claiming_physical_delivery(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.fixture(Path(root))
            self.assertEqual(result['verifiedLegs'], 1)
            self.assertFalse(result['physicalInputDeliveryVerified'])

    def test_missing_source_receipt_late_input_and_changed_pose_are_rejected(self):
        mutations = (
            lambda run, part, frames: frames.pop(),
            lambda run, part, frames: part['receipts'].clear(),
            lambda run, part, frames: part['receipts'][0]['appliedSteps'][0].update(startedAtMs=201),
            lambda run, part, frames: frames[-1]['navigationPose'].update(x=END[0]+1),
            lambda run, part, frames: part['hybridNavigationEvents'][-1].update(releaseAtMs=150),
            lambda run, part, frames: run.update(modelLoads=2),
            lambda run, part, frames: part['recording'].update(droppedFrames=1),
            lambda run, part, frames: part['receipts'][0].update(modelId='open-p2p'),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    self.fixture(Path(root), mutate)
