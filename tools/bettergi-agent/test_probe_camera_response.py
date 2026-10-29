"""Offline camera-response trials with source timing, pose and action receipts on one simulated lease."""
from collections import Counter
from unittest.mock import Mock, patch
import unittest

import probe_camera_response as probe


class CameraBridge:
    """Publish a rotating but stationary native camera view with a delayed, independently timed receipt."""
    hello = dict(observationProfile=probe.P2P_NATIVE, widthLimit=192, heightLimit=192,
                 observationPreprocessing=dict(source='native_capture', resize='fir-5.1.4-interpolation-hamming',
                                               pixelFormat='rgb24', preserveAspectRatio=False))
    pixels = bytes([50]) * (192 * 192 * 3)

    def __init__(self):
        self.frame = 0
        self.yaw = 355
        self.action = None
        self.issued = []
        self.alter = lambda frame: None

    def request(self, method, **fields):
        """Return only simulated protocol messages; tests never open an operating-system pipe."""
        if method == 'action':
            self.issued.append(fields)
            self.action = (fields, self.frame*40 + 8)
            return dict(type='accepted', requestId=fields['requestId'], acceptedAtMs=self.action[1]), b''
        self.frame += 1
        i = self.frame
        at = i*40
        src = dict(captureEpoch='capture', timestamp100ns=i*400000, capturedAtMs=at,
                   acquiredAtMs=at+1, freshnessAtMs=at, freshnessClockKind='reported_compositor_qpc')
        gate = dict(ready=True, epoch=3, sourceFrameId=i, sourceFrame=src)
        receipts = []
        if self.action:
            fields, ack = self.action
            dx = fields['steps'][0]['mouseDx']
            if at >= ack+101:
                receipts = [dict(requestId=fields['requestId'], modelId=probe.MODEL, frameId=fields['frameId'],
                                 status='completed', reason='horizon_complete', acceptedAtMs=ack, endedAtMs=ack+101,
                                 appliedSteps=[dict(index=0, keys=[], mouseDx=dx, mouseDy=0, startedAtMs=ack+1)])]
                self.yaw = (self.yaw + dx*.25) % 360
                self.action = None
        pose = dict(state='valid', frameId=i, x=probe.STATION[0], y=probe.STATION[1], layerId='City_102',
                    yawDegrees=self.yaw, positionConfidence=.999, yawConfidence=.8)
        row = dict(type='frame', frameId=i, sourceFrame=src, sourceTimestampKind='wgc_reported_compositor_qpc',
                   observationProfile=probe.P2P_NATIVE, width=192, height=192, pixelFormat='rgb24',
                   capturedAtMs=at, serverNowMs=at+4, navigationPose=pose, frameWorldReadiness=gate,
                   worldReadiness=gate.copy(), motionEvidence=dict(status='normal', spaceKeyMatched=False, xKeyMatched=False),
                   inputAvailable=True, receipts=receipts, droppedReceipts=0)
        self.alter(row)
        return row, self.pixels


class CameraProbeTests(unittest.TestCase):
    """Verify the experiment qualifies actual receipts, rejects sensor confounds and emits bounded pulses."""
    def setUp(self):
        self.bridge = CameraBridge()
        self.report = {'observations': [], 'actions': [], 'receipts': []}
        self.trial = probe.Experiment(self.bridge, self.report)

    def test_brackets_wraparound_response_and_records_every_distinct_received_frame(self):
        self.trial.pulse(75)
        self.trial.pulse(-75)
        rows = {r['frameId']: r for r in self.report['observations']}
        self.assertEqual(list(rows), list(range(1, self.bridge.frame+1)))
        for a, r in zip(self.report['actions'], self.report['receipts']):
            times = lambda ids: [rows[i]['sourceAtMs'] for i in ids]
            pre, end = times(a['preFrameIds']), times(a['settledFrameIds'])
            self.assertGreaterEqual(pre[-1]-pre[0], 500)
            self.assertGreaterEqual(end[-1]-r['endedAtMs'], 700)
            self.assertGreaterEqual(end[-1]-end[0], 100)
            self.assertEqual(len(set(end)), 3)
            self.assertEqual(a['step'], dict(keys=[], durationMs=100, mouseDx=a['mouseDx'], mouseDy=0))
            self.assertEqual(a['requestId'], r['requestId'])

    def test_rejects_changed_epoch_body_position_current_gate_motion_and_dropped_receipts(self):
        for alteration in (lambda f: f['sourceFrame'].update(captureEpoch='different'),
                           lambda f: f['navigationPose'].update(x=probe.STATION[0]+.4),
                           lambda f: f['worldReadiness'].update(ready=False),
                           lambda f: f['motionEvidence'].update(status='climb'),
                           lambda f: f.update(droppedReceipts=1),
                           lambda f: f.update(serverNowMs=f['sourceAtMs']+200) if 'sourceAtMs' in f else f.update(serverNowMs=f['capturedAtMs']+200)):
            with self.subTest(alteration=alteration):
                self.setUp()
                self.bridge.alter = lambda f: alteration(f) if f['frameId'] == 4 else None
                with self.assertRaises(ValueError):
                    self.trial.pulse(75)
                self.assertFalse(self.bridge.issued)

    def test_receipt_must_belong_to_exact_pulse_before_deadline_without_vertical_or_key_input(self):
        for alter in (lambda r: r.update(requestId='foreign'), lambda r: r['appliedSteps'][0].update(keys=['W']),
                      lambda r: r['appliedSteps'][0].update(mouseDy=1), lambda r: r.update(status='replaced'),
                      lambda r: r['appliedSteps'][0].update(startedAtMs=r['acceptedAtMs']+170)):
            with self.subTest(alter=alter):
                self.setUp()
                self.bridge.alter = lambda f: alter(f['receipts'][0]) if f['receipts'] else None
                with self.assertRaises(ValueError):
                    self.trial.pulse(75)
                self.assertEqual(len(self.report['receipts']), 1)
                self.assertEqual(len(self.bridge.issued), 1)

    def test_exact_balanced_disjoint_sequence_budgets(self):
        self.assertEqual(Counter(probe.SEQUENCES['train']), {v*s: 2 for v in (30, 75, 125, 220) for s in (-1, 1)})
        self.assertEqual(Counter(probe.SEQUENCES['holdout']), {v*s: 1 for v in (45, 95, 170) for s in (-1, 1)})

    def test_failure_closes_owned_bridge_without_stopping_an_unrelated_task(self):
        api, bridge = Mock(), Mock()
        child = dict(processId=400, instanceNonce='n', windowsSessionId=7, agentPipeName='owned')
        api.start_agent.return_value = child
        bridge.hello = {}
        bridge.request.return_value = ({'type': 'stopped', 'receipts': []}, b'')
        with patch.object(probe, 'require_current_rdp'), patch.object(probe, 'control_module', return_value=api), \
                patch.object(probe, 'ready_session', return_value=({}, child)), \
                patch.object(probe, 'Bridge', return_value=bridge), patch.object(probe, 'verify_bridge_identity'), \
                self.assertRaises(ValueError):
            probe.run(Mock(rdp_session_id=7, child_nonce='n'), self.report)
        bridge.request.assert_called_once_with('stop')
        bridge.handle.close.assert_called_once()
        api.stop_agent.assert_not_called()


if __name__ == '__main__':
    unittest.main()
