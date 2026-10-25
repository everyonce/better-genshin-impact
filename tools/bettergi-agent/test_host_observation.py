"""Real client paths with fake host frames; no bridge, model, SDK or native capture."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host_observation import KIND, HostObservationContract, host_snapshot
from navigation_idle_recovery import capture_context, fresh_frame
from observation_timing import frame_timing, observation_timestamp
from prepare_replay import EvidenceError, frame_clock
import stream_client as client


def hello(policy=KIND, enabled=True):
    """Match the additive fields emitted by AgentStreamSession.WithDesktopEvidence."""
    return {'sessionId': 's', 'ownerEpoch': 'o', 'goalVersion': 1, 'inputEnabled': enabled,
            'allowedKeys': ['W'], 'supportsStartBeforeMs': True, 'maxActionStartAgeMs': 500,
            'hostSnapshotVersion': 1, 'sourceKind': KIND, 'desktopDcSourcePolicy': policy,
            'sourceFrameTiming': {'version': 3, 'knownTimestampKind': 'unknown', 'sourceKind': KIND,
                'unknownFallback': 'rejected', 'freshnessAnchor': 'host_snapshot_started_qpc',
                'maxAgeMs': 150, 'distinctSnapshotsForConfirmation': 2, 'measuresGameRenderAge': False},
            'worldReadiness': {'version': 1, 'requiredForInput': True, 'sourceKind': KIND,
                'sourceTimestampKind': 'unknown', 'freshnessAnchor': 'host_snapshot_started_qpc',
                'maxAgeMs': 150, 'confirmationFrames': 2}}


def frame(start=950, end=960, now=1000, policy=KIND):
    """Raw QPC is intentionally unrelated to milliseconds or the proposal's frame clock."""
    origin, frequency = 9_223_000_000_000, 10_000_000
    snapshot = {'version': 1, 'sourceKind': KIND, 'desktopDcSourcePolicy': policy,
                'captureEpoch': '1'*32, 'snapshotId': 1, 'clockFrequency': frequency,
                'sessionOriginAtStopwatchTicks': origin,
                'startedAtStopwatchTicks': origin+start*10_000,
                'completedAtStopwatchTicks': origin+end*10_000,
                'startedAtMs': start, 'completedAtMs': end}
    ready = policy == KIND
    return {'type': 'frame', 'frameId': 1, 'capturedAtMs': start-20, 'serverNowMs': now,
            'width': 2, 'height': 2, 'sourceWidth': 2, 'sourceHeight': 2, 'pixelFormat': 'rgb24',
            'sourceFrame': None, 'sourceTimestampKind': 'unknown', 'sourceFrameAgeMs': None,
            'reportedSourceFrameAgeMs': None, 'hostSnapshotVersion': 1, 'sourceKind': KIND,
            'desktopDcSourcePolicy': policy, 'hostSnapshot': snapshot,
            'hostAcquisitionAgeMs': now-start, 'hostAcquisitionIntervalMs': end-start,
            'worldReadiness': {'epoch': 1, 'ready': ready, 'reason': 'ready' if ready else 'capture_policy_observe_only'},
            'frameWorldReadiness': {'epoch': 1, 'ready': ready}, 'inputAvailable': ready,
            'clientReceivedNs': 1_000_000, 'transportRoundTripMs': 2}


class HostClockTests(unittest.TestCase):
    """Keep distinct acquisition/receipt/render clocks and reject invented host freshness."""
    def test_raw_start_is_age_anchor_and_wgc_metrics_stay_unknown(self):
        value = frame()
        timing = frame_timing(value, 4_000_000, 3_000_000, 1)
        self.assertEqual(observation_timestamp(value), 950)
        self.assertEqual(timing['hostCaptureAgeAtReceiptMs'], 70)
        self.assertEqual(timing['serverAgeAtReceiptMs'], 50)
        self.assertEqual(timing['hostAcquisitionAgeAtReceiptMs'], 50)
        self.assertEqual(timing['hostAcquisitionIntervalMs'], 10)
        self.assertEqual(timing['observationTimestampKind'], 'host_snapshot_started_qpc')
        self.assertFalse(timing['measuresGameRenderAge'])
        for key in ('sourceFrameAgeAtReceiptMs', 'reportedSourceFrameAgeAtReceiptMs',
                    'reportedSourceLeadAtAcquisitionMs', 'sourceAcquisitionDelayMs'):
            self.assertIsNone(timing[key])

    def test_raw_qpc_subtraction_precedes_float_conversion(self):
        value = frame()
        snapshot = value['hostSnapshot']
        snapshot.update(sessionOriginAtStopwatchTicks=2**62+17,
                        startedAtStopwatchTicks=2**62+18, completedAtStopwatchTicks=2**62+19,
                        clockFrequency=3_000_000, startedAtMs=1/3000, completedAtMs=2/3000)
        value.update(capturedAtMs=0, serverNowMs=1, hostAcquisitionAgeMs=1-1/3000,
                     hostAcquisitionIntervalMs=1/3000)
        self.assertEqual(observation_timestamp(value), 1/3000)

    def test_partial_or_missing_host_evidence_never_uses_capture_request(self):
        for key in ('hostSnapshot', 'hostSnapshotVersion', 'sourceKind', 'desktopDcSourcePolicy'):
            value = frame()
            del value[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                observation_timestamp(value)

    def test_raw_metadata_rejects_malformed_id_clock_policy_or_kind(self):
        mutations = {'snapshotId': [0, True, 1.0], 'captureEpoch': ['0'*32, 'not-a-guid'],
                     'clockFrequency': [0, True, 10_000_000.0], 'version': [1.0, True, 2],
                     'sessionOriginAtStopwatchTicks': [0], 'startedAtStopwatchTicks': [1],
                     'completedAtStopwatchTicks': [2**63], 'sourceKind': ['wgc'],
                     'desktopDcSourcePolicy': ['observe-only']}
        for key, values in mutations.items():
            for changed in values:
                value = frame()
                value['hostSnapshot'][key] = changed
                with self.subTest(key=key, value=changed), self.assertRaises(ValueError):
                    observation_timestamp(value)

    def test_mapped_clock_and_future_completion_cannot_hide_old_acquisition(self):
        for key, changed in (('startedAtMs', 999), ('completedAtMs', 959)):
            value = frame()
            value['hostSnapshot'][key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                observation_timestamp(value)
        for key, changed in (('serverNowMs', 959), ('hostAcquisitionAgeMs', 0),
                             ('hostAcquisitionIntervalMs', 0), ('capturedAtMs', 951)):
            value = frame()
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                observation_timestamp(value)

    def test_host_snapshot_cannot_have_wgc_age_or_identity(self):
        for key, changed in (('sourceFrame', {}), ('sourceFrameAgeMs', 0),
                             ('reportedSourceFrameAgeMs', 0), ('sourceTimestampKind', 'host-acquisition-v1')):
            value = frame()
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                observation_timestamp(value)

    def test_idle_recovery_uses_same_start_and_tracks_host_generation(self):
        value = frame(start=850, end=999)
        self.assertFalse(fresh_frame(value, 1_000_000, 150))
        self.assertTrue(fresh_frame(frame(), 1_000_000, 150))
        other = frame()
        other['hostSnapshot']['captureEpoch'] = '2'*32
        self.assertNotEqual(capture_context(frame()), capture_context(other))

    def test_existing_replay_preparer_stays_closed_to_host_data(self):
        with self.assertRaisesRegex(EvidenceError, 'unknown_source_clock'):
            frame_clock(frame())


class HostContractTests(unittest.TestCase):
    """Pin the explicit selection across a lease, including repeats and waiting replies."""
    def test_legacy_contract_is_unchanged_but_cannot_gain_host_evidence(self):
        contract = HostObservationContract({})
        contract.validate({'type': 'frame', 'sourceFrame': None})
        self.assertIsNone(contract.policy)
        with self.assertRaises(ValueError):
            contract.validate(frame())

    def test_invalid_hello_fails_before_admission(self):
        for key, changed in (('hostSnapshotVersion', 1.0), ('sourceKind', 'unknown'),
                             ('desktopDcSourcePolicy', None), ('inputEnabled', 1),
                             ('supportsStartBeforeMs', False)):
            value = hello()
            value[key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                HostObservationContract(value)
        value = hello()
        value['sourceFrameTiming']['unknownFallback'] = 'host_capture_request'
        with self.assertRaises(ValueError):
            HostObservationContract(value)

    def test_observe_only_never_accepts_input_request_or_server_authority(self):
        HostObservationContract(hello('observe-only', False)).validate(frame(policy='observe-only'))
        for enabled, requested in ((True, False), (False, True)):
            with self.subTest(enabled=enabled, requested=requested), self.assertRaises(ValueError):
                HostObservationContract(hello('observe-only', enabled), requested)
        contract = HostObservationContract(hello('observe-only', False))
        value = frame(policy='observe-only')
        value['inputAvailable'] = True
        with self.assertRaises(ValueError):
            contract.validate(value)

    def test_waiting_and_frame_must_retain_the_advertised_selection(self):
        for kind in ('waiting', 'frame'):
            for change in ({'hostSnapshotVersion': 1.0}, {'desktopDcSourcePolicy': 'observe-only'},
                           {'sourceKind': None}):
                with self.subTest(kind=kind, change=change), self.assertRaises(ValueError):
                    HostObservationContract(hello()).validate({**frame(), 'type': kind, **change})
        with self.assertRaises(ValueError):
            HostObservationContract(hello()).validate({'type': 'waiting'})

    def test_duplicate_can_be_redelivered_but_cannot_renew_its_clock(self):
        contract = HostObservationContract(hello())
        contract.validate(frame())
        contract.validate(frame(now=1100))
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            contract.validate(frame(start=960, end=970))

    def test_new_id_requires_serial_nonoverlapping_acquisition(self):
        for start, end, valid in ((950, 960, False), (959, 970, False), (960, 970, True)):
            contract = HostObservationContract(hello())
            contract.validate(frame())
            value = frame(start=start, end=end)
            value['hostSnapshot']['snapshotId'] = 3
            if valid:
                contract.validate(value)
            else:
                with self.subTest(start=start), self.assertRaises(ValueError):
                    contract.validate(value)

    def test_epoch_origin_frequency_and_regression_are_terminal(self):
        for key, changed in (('captureEpoch', '2'*32), ('sessionOriginAtStopwatchTicks', 100),
                             ('clockFrequency', 1_000_000), ('snapshotId', 1)):
            contract = HostObservationContract(hello())
            prior = frame()
            prior['hostSnapshot']['snapshotId'] = 2
            contract.validate(prior)
            value = copy.deepcopy(prior)
            value['hostSnapshot'][key] = changed
            if key in ('sessionOriginAtStopwatchTicks', 'clockFrequency'):
                snapshot = value['hostSnapshot']
                origin, frequency = snapshot['sessionOriginAtStopwatchTicks'], snapshot['clockFrequency']
                snapshot['startedAtStopwatchTicks'] = origin+950*frequency//1000
                snapshot['completedAtStopwatchTicks'] = origin+960*frequency//1000
            # All individual snapshots remain valid: only the lease identity join rejects these.
            host_snapshot(value)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'generation|regressed'):
                contract.validate(value)


class HostEpisodeTests(unittest.TestCase):
    """Exercise the actual consumer/submission/recording path with no external transport."""
    def run_case(self, *, start=950, observe=False, malformed=False):
        submitted, recorded, events, predictions = [], [], [], []
        policy_kind = 'observe-only' if observe else KIND

        class LocalBridge:
            def __init__(self, name):
                self.handle = io.BytesIO()
                self.hello = hello(policy_kind, not observe)

            def request(self, command, **kwargs):
                if command == 'frame':
                    value = frame(start=start, end=999, policy=policy_kind)
                    if malformed:
                        del value['hostSnapshot']
                    return value, bytes([64]*12)
                if command == 'action':
                    submitted.append(kwargs)
                    return {'type': 'accepted', 'requestId': kwargs['requestId']}, b''
                if command == 'stop':
                    return {'type': 'stopped', 'receipts': []}, b''
                raise AssertionError(command)

        class Policy:
            metadata = {'model': 'synthetic'}

            def predict(self, image, source_size):
                predictions.append(True)
                return {'parseValid': True, 'fullActionMs': 0,
                        'steps': [{'keys': ['W'], 'durationMs': 50, 'mouseDx': 0, 'mouseDy': 0}]}

        class Recorder:
            error = None

            def __init__(self, *args, **kwargs):
                pass

            def put(self, metadata, pixels):
                recorded.append(copy.deepcopy(metadata))

            def event(self, event):
                events.append(copy.deepcopy(event))

            def close(self):
                return {'status': 'complete'}

            def fail(self, reason):
                self.error = reason

        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'report.json'
            arguments = ['--model', 'observe' if observe else 'open-p2p', '--source', 'unused',
                '--checkpoint', 'unused', '--seconds', '.2', '--fps', '30', '--decision-hz', '20',
                '--max-observation-age-ms', '150', '--output', str(output),
                '--record-dir', str(Path(root)/'record')]
            if not observe:
                arguments.extend(['--enable-input', '--max-input-actions', '1'])
            args = client.parse_arguments(arguments)
            with patch.object(client, 'Bridge', LocalBridge), patch.object(client, 'AsyncVideoRecorder', Recorder), redirect_stdout(io.StringIO()):
                result = client.run_episode(args, None if observe else Policy())
            report = json.loads(output.read_text())
        return result, report, submitted, recorded, events, predictions

    def test_input_uses_raw_host_start_for_deadlines_but_keeps_frame_identity(self):
        result, report, submitted, recorded, events, predictions = self.run_case()
        self.assertEqual(result, 0)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0]['observedAtMs'], 930)
        self.assertEqual(submitted[0]['startBeforeMs'], 1100)
        self.assertEqual(submitted[0]['expiresAtMs'], 1650)
        self.assertEqual(report['decisions'][0]['observationTimestampMs'], 950)
        self.assertEqual(recorded[0]['hostSnapshot'], frame(start=950, end=999)['hostSnapshot'])
        self.assertIsNone(recorded[0]['sourceFrame'])
        self.assertEqual(events[0]['hostSourceContract'], report['hostSourceContract'])
        self.assertFalse(report['hostSourceContract']['isTrainingGroundTruth'])

    def test_recent_completion_does_not_freshen_stale_start(self):
        result, report, submitted, *_ = self.run_case(start=800)
        self.assertEqual(result, 0)
        self.assertFalse(submitted)
        self.assertEqual(report['decisions'][0]['acceptance']['reason'], 'observationTooOld')

    def test_observe_only_records_raw_headers_without_policy_or_input(self):
        result, report, submitted, recorded, _, predictions = self.run_case(observe=True)
        self.assertEqual(result, 0)
        self.assertGreater(report['captureQuality']['usableFrames'], 0)
        self.assertFalse(submitted or predictions or report['decisions'])
        self.assertFalse(recorded[0]['inputAvailable'])
        self.assertEqual(recorded[0]['hostSnapshot']['desktopDcSourcePolicy'], 'observe-only')

    def test_missing_host_stops_before_recording_prediction_or_submission(self):
        result, report, submitted, recorded, _, predictions = self.run_case(malformed=True)
        self.assertEqual(result, 1)
        self.assertIn('host snapshot', report['streamError'])
        self.assertFalse(submitted or recorded or predictions)


if __name__ == '__main__':
    unittest.main()
