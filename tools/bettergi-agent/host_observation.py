"""Validate explicit host acquisitions without inventing compositor or render clocks."""
import math
import re


KIND = 'host-acquisition-v1'
POLICIES = ('observe-only', KIND)
FIELDS = ('hostSnapshotVersion', 'sourceKind', 'desktopDcSourcePolicy', 'hostSnapshot')


def declared(message):
    """Even a partial/null declaration must never fall through to legacy receipt time."""
    return any(key in message for key in FIELDS)


def finite(value):
    """Reject bool, NaN and string clocks from untrusted JSON."""
    return type(value) in (int, float) and math.isfinite(value)


def selection(message):
    """Require the exact separate host evidence kind and startup-fixed policy."""
    if (type(message.get('hostSnapshotVersion')) is not int or message['hostSnapshotVersion'] != 1
            or message.get('sourceKind') != KIND or message.get('desktopDcSourcePolicy') not in POLICIES):
        raise ValueError('Invalid host snapshot contract')
    return message['desktopDcSourcePolicy']


def host_snapshot(frame):
    """Return checked raw evidence, or None only for an undeclared legacy backend."""
    if not declared(frame):
        return None
    policy = selection(frame)
    snapshot = frame.get('hostSnapshot')
    if (not isinstance(snapshot, dict) or type(snapshot.get('version')) is not int
            or snapshot['version'] != 1 or snapshot.get('sourceKind') != KIND
            or snapshot.get('desktopDcSourcePolicy') != policy):
        raise ValueError('Missing or invalid host snapshot')
    epoch = snapshot.get('captureEpoch')
    if not isinstance(epoch, str) or not re.fullmatch('[0-9a-f]{32}', epoch) or int(epoch, 16) == 0:
        raise ValueError('Invalid host snapshot epoch')
    names = ('snapshotId', 'clockFrequency', 'sessionOriginAtStopwatchTicks',
             'startedAtStopwatchTicks', 'completedAtStopwatchTicks')
    if any(type(snapshot.get(key)) is not int or not 0 < snapshot[key] <= 2**63-1 for key in names):
        raise ValueError('Invalid host snapshot identity or clock')
    origin, start, end, frequency = (snapshot[key] for key in
        ('sessionOriginAtStopwatchTicks', 'startedAtStopwatchTicks', 'completedAtStopwatchTicks', 'clockFrequency'))
    if not origin <= start <= end:
        raise ValueError('Invalid host snapshot clock order')
    # Match the producer's Int128 subtraction followed by double multiply/divide.
    start_ms, end_ms = (float(tick-origin)*1000/frequency for tick in (start, end))
    now = frame.get('serverNowMs')
    if (not finite(now) or not finite(frame.get('capturedAtMs'))
            or not 0 <= frame['capturedAtMs'] <= start_ms <= end_ms <= now
            or not finite(snapshot.get('startedAtMs')) or snapshot['startedAtMs'] != start_ms
            or not finite(snapshot.get('completedAtMs')) or snapshot['completedAtMs'] != end_ms
            or not finite(frame.get('hostAcquisitionAgeMs')) or frame['hostAcquisitionAgeMs'] != now-start_ms
            or not finite(frame.get('hostAcquisitionIntervalMs')) or frame['hostAcquisitionIntervalMs'] != end_ms-start_ms):
        raise ValueError('Host snapshot raw and mapped clocks disagree')
    if (frame.get('sourceTimestampKind') != 'unknown'
            or any(key not in frame or frame[key] is not None for key in
                   ('sourceFrame', 'sourceFrameAgeMs', 'reportedSourceFrameAgeMs'))):
        raise ValueError('Host snapshots cannot carry WGC source timing')
    return snapshot


class HostObservationContract:
    """Pin one bridge's typed host selection and serial acquisition identity."""
    def __init__(self, hello, enable_input=False):
        self.policy = selection(hello) if declared(hello) else None
        self.previous = None
        if self.policy is None:
            return
        timing, readiness = hello.get('sourceFrameTiming', {}), hello.get('worldReadiness', {})
        if (not isinstance(timing, dict) or not isinstance(readiness, dict)
                or type(timing.get('version')) is not int or timing['version'] != 3
                or timing.get('sourceKind') != KIND or timing.get('knownTimestampKind') != 'unknown'
                or timing.get('unknownFallback') != 'rejected'
                or timing.get('freshnessAnchor') != 'host_snapshot_started_qpc'
                or timing.get('measuresGameRenderAge') is not False
                or timing.get('maxAgeMs') != 150 or timing.get('distinctSnapshotsForConfirmation') != 2
                or type(readiness.get('version')) is not int or readiness['version'] != 1
                or readiness.get('requiredForInput') is not True or readiness.get('sourceKind') != KIND
                or readiness.get('sourceTimestampKind') != 'unknown'
                or readiness.get('freshnessAnchor') != 'host_snapshot_started_qpc'
                or readiness.get('maxAgeMs') != 150 or readiness.get('confirmationFrames') != 2
                or hello.get('supportsStartBeforeMs') is not True or hello.get('maxActionStartAgeMs') != 500
                or type(hello.get('inputEnabled')) is not bool):
            raise ValueError('Unsupported host acquisition freshness contract')
        if self.policy == 'observe-only' and (enable_input or hello['inputEnabled']):
            raise ValueError('Desktop observe-only policy cannot authorize input')

    def validate(self, message):
        """Validate before publishing frames, including repeated payloads and waiting responses."""
        if self.policy is None:
            if declared(message):
                raise ValueError('Undeclared host evidence on a legacy bridge')
            return
        if selection(message) != self.policy:
            raise ValueError('Host capture policy changed during the bridge lease')
        if self.policy == 'observe-only' and message.get('inputAvailable') is not False:
            raise ValueError('Observe-only host bridge advertised input availability')
        if message.get('type') != 'frame':
            return
        snapshot = host_snapshot(message)
        previous = self.previous
        if previous is not None:
            if any(snapshot[key] != previous[key] for key in
                   ('captureEpoch', 'clockFrequency', 'sessionOriginAtStopwatchTicks')):
                raise ValueError('Host capture generation or clock changed during the bridge lease')
            if snapshot['snapshotId'] < previous['snapshotId']:
                raise ValueError('Host snapshot identity regressed')
            if snapshot['snapshotId'] == previous['snapshotId']:
                if snapshot != previous:
                    raise ValueError('Repeated host snapshot metadata changed')
            elif (snapshot['startedAtStopwatchTicks'] <= previous['startedAtStopwatchTicks']
                  or snapshot['startedAtStopwatchTicks'] < previous['completedAtStopwatchTicks']):
                raise ValueError('Host acquisitions must be serial and strictly newer')
        self.previous = dict(snapshot)

    def describe(self):
        """Expose the clock and authority limits in the retained episode/recorder header."""
        return {'version': 1, 'sourceKind': KIND, 'desktopDcSourcePolicy': self.policy,
                'freshnessAnchor': 'host_snapshot_started_qpc', 'measuresGameRenderAge': False,
                'isTrainingGroundTruth': False}
