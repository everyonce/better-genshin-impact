"""Terminal scout-only refusals from source-bound native HUD evidence; never combat authority."""
import copy
import hashlib
import json
import re
import threading

from native_combat import METHOD, finite, validate_frame


def guard_policy():
    """Return a fresh fixed contract so no caller can mutate another run's limits."""
    return dict(version=1, method=METHOD, maximumHealthFractionDrop=.08, sourceFreshnessMs=150,
                stopOnEnemyBarCandidate=True, stopOnRedOrAmbiguousHealth=True,
                stopOnUnavailableWhileArmed=True, acknowledgedReleaseDisarms=True,
                requirePostReleaseHealthySource=True, attacksAllowed=False,
                enemyIdentityVerified=False)


def binding_from_review(review, review_sha):
    """Bind the estimated-health threshold to the exact manually inspected review bytes."""
    health, maximum = review.get('inspectedHealth'), review.get('inspectedMaximumHealth')
    if (type(health) is not int or type(maximum) is not int or not 0 < health <= maximum
            or not isinstance(review_sha, str) or re.fullmatch('[a-f0-9]{64}', review_sha) is None):
        raise ValueError('Scout encounter guard requires the immutable reviewed health baseline')
    return dict(policy=guard_policy(), reviewSha256=review_sha, inspectedHealth=health,
                inspectedMaximumHealth=maximum, baselineHealthFraction=health/maximum)


def validate_binding(binding):
    """Reject changed settings, extra fields and a baseline detached from its reviewed integer health."""
    if not isinstance(binding, dict) or binding != binding_from_review(binding, binding.get('reviewSha256')):
        raise ValueError('Scout encounter guard binding or fixed settings changed')
    # Equality alone treats True as 1; canonical JSON also binds the numeric and boolean types.
    expected = binding_from_review(binding, binding['reviewSha256'])
    if json.dumps(binding, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError('Scout encounter guard binding types changed')
    return copy.deepcopy(expected)


def binding_sha(binding):
    """Identify the same guard in the request, intake journal and each dispatch decision."""
    return hashlib.sha256(json.dumps(validate_binding(binding), sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sensor_frame(frame):
    """Retain only the bounded native evidence and immutable source needed for independent replay."""
    def retained(value):
        """Keep malformed nonfinite values explicit without making terminal evidence unwritable."""
        if isinstance(value,float) and not finite(value):return dict(invalidNativeNumber=repr(value))
        if isinstance(value,dict):return {key:retained(item) for key,item in value.items()}
        if isinstance(value,list):return [retained(item) for item in value]
        return value
    return retained({key: frame[key] for key in ('type', 'frameId', 'sourceFrame', 'sourceWidth',
        'sourceHeight', 'sourceFrameAgeMs', 'combatEvidence') if key in frame})


class ScoutEncounterStop(RuntimeError):
    """A latched sensor stop cannot authorize reconnect, retry, or combat."""


class ScoutEncounterGuard:
    """Serialize immutable sensor admission and retain the first terminal hazard across later frames."""
    def __init__(self, binding):
        """Start released with no admitted health evidence, preserving the original reviewed binding."""
        self.binding = validate_binding(binding)
        self.sha256 = binding_sha(binding)
        self._lock = threading.RLock()
        self.intake_lock = self._lock
        self.observations = 0
        self.distinct_sources = 0
        self.admitted = False
        self.armed = False
        self.releases = 0
        self.last_release = None
        self.reason = 'awaitingNativeHealthEvidence'
        self.last = None
        self.trip = None

    def snapshot(self):
        """Publish detached scalar state and the original triggering metadata before reader teardown."""
        with self._lock:
            return dict(bindingSha256=self.sha256, observations=self.observations,
                        distinctSources=self.distinct_sources, admitted=self.admitted,
                        armed=self.armed, releases=self.releases, lastRelease=copy.deepcopy(self.last_release),
                        state='tripped' if self.trip else 'ready' if self.reason=='healthyNativeEvidence' else 'waiting',
                        reason=self.reason, lastObservation=copy.deepcopy(self.last), trip=copy.deepcopy(self.trip))

    def observe(self, frame, received_ns):
        """Inspect every poll, including repeated sources; absent startup sensors never grant admission."""
        with self._lock:
            if self.trip:
                raise ScoutEncounterStop('Scout encounter guard: '+self.trip['reason'])
            self.observations += 1
            retained = sensor_frame(frame)
            event = dict(type='scoutEncounterGuardObservation', index=self.observations,
                         bindingSha256=self.sha256, clientReceivedNs=received_ns, frame=retained)
            reason, unavailable, evidence = None, False, None
            try:
                evidence = validate_frame(frame) if frame.get('type') == 'frame' else None
                if evidence is None or evidence['state'] == 'unavailable':
                    reason, unavailable = 'nativeSensorUnavailable', True
                elif not finite(frame.get('sourceFrameAgeMs')) or not 0 <= frame['sourceFrameAgeMs'] <= 150:
                    reason, unavailable = 'nativeSensorStale', True
                else:
                    source = evidence['sourceFrame']
                    before = self.last['frame'] if self.last else None
                    if before:
                        prior = before['sourceFrame']
                        if source['captureEpoch'] != prior['captureEpoch'] or source['timestamp100ns'] < prior['timestamp100ns']:
                            reason = 'nativeSensorSourceChanged'
                        elif source['timestamp100ns'] == prior['timestamp100ns']:
                            immutable = lambda value: {key: item for key, item in value.items()
                                                       if key not in ('frameId', 'recognitionMs')}
                            if source != prior or immutable(evidence) != immutable(before['combatEvidence']):
                                reason = 'nativeSensorEvidenceChanged'
                    if reason is None:
                        if evidence['redMaskOverloaded']:
                            reason = 'ambiguousEnemyBarEvidence'
                        elif evidence['enemyBarCandidates']:
                            reason = 'enemyBarCandidate'
                        elif evidence['playerHealthColor'] != 'green':
                            reason = 'redHealth' if evidence['playerHealthColor'] == 'red' else 'ambiguousHealth'
                        elif self.binding['baselineHealthFraction']-evidence['playerHealthFractionEstimate'] >= .08-1e-12:
                            reason = 'reviewedHealthFractionDrop'
                    if reason is None and self.last_release is not None and source['freshnessAtMs'] <= self.last_release['response']['serverNowMs']:
                        reason, unavailable = 'awaitingPostReleaseNativeEvidence', True
                    if reason is None:
                        if before is None or source['timestamp100ns'] > before['sourceFrame']['timestamp100ns']:
                            self.distinct_sources += 1
                        self.last = dict(index=self.observations, clientReceivedNs=received_ns, frame=retained)
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
                reason = 'invalidNativeSensorEvidence'
                event['validationError'] = str(error)[:512]
            self.reason = reason or 'healthyNativeEvidence'
            if reason and (self.armed or not unavailable):
                # Retain the trigger before callers can raise, record, release, or encounter reader failure.
                self.trip = dict(reason=reason, index=self.observations, clientReceivedNs=received_ns,
                                 frame=retained, **({'validationError': event['validationError']}
                                                   if 'validationError' in event else {}))
            event['state'] = self.snapshot()
            return event

    def acknowledge_release(self, response, payload_bytes, now_ns, reason):
        """Disarm only an exact acknowledged release; preserve every trip and require newer healthy pixels."""
        with self._lock:
            gate=response.get('worldReadiness') if isinstance(response,dict) else None
            if (not isinstance(response,dict) or response.get('type')!='released' or payload_bytes!=0
                    or not finite(response.get('serverNowMs')) or not isinstance(gate,dict)
                    or gate.get('ready') is not False or type(gate.get('epoch')) is not int or gate['epoch']<0):
                raise ScoutEncounterStop('Scout encounter guard: invalid release acknowledgement')
            if (self.last is not None and response['serverNowMs']<self.last['frame']['sourceFrame']['freshnessAtMs']
                    or self.last_release is not None and response['serverNowMs']<self.last_release['response']['serverNowMs']):
                raise ScoutEncounterStop('Scout encounter guard: release acknowledgement predates native evidence')
            self.armed=False
            self.releases+=1
            self.last_release=dict(number=self.releases,clientTimeNs=now_ns,reason=reason,
                                   response=copy.deepcopy(response),payloadBytes=payload_bytes)
            if self.trip is None:self.reason='awaitingPostReleaseNativeEvidence'
            return dict(type='scoutEncounterGuardRelease',bindingSha256=self.sha256,
                        **copy.deepcopy(self.last_release),state=self.snapshot())

    def check_dispatch(self, frame, now_ns):
        """Called under the stream intake lock immediately before transmission, after inference finishes."""
        with self._lock:
            if self.trip:
                raise ScoutEncounterStop('Scout encounter guard: '+self.trip['reason'])
            evidence = validate_frame(frame)
            if (self.reason!='healthyNativeEvidence' or self.last is None
                    or evidence is None or evidence['state'] != 'valid'
                    or evidence['playerHealthColor'] != 'green' or evidence['redMaskOverloaded']
                    or evidence['enemyBarCandidates'] or self.binding['baselineHealthFraction']
                    - evidence['playerHealthFractionEstimate'] >= .08-1e-12
                    or self.last_release is not None and evidence['sourceFrame']['freshnessAtMs']
                       <= self.last_release['response']['serverNowMs']):
                raise ScoutEncounterStop('Scout encounter guard: dispatch lacks admitted healthy evidence')
            # A submission attempt arms the guard before the native call. Missing evidence remains
            # terminal while armed; only a separately acknowledged release can disarm it.
            self.admitted = True
            self.armed = True
            return dict(bindingSha256=self.sha256, observationIndex=self.observations,
                        latestFrameId=self.last['frame']['frameId'], frameId=frame['frameId'],
                        clientDispatchNs=now_ns)
