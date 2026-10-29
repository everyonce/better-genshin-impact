"""Attribute predeclared photo requests to disjoint frames and actions on one verified patrol lease."""
import hashlib
import json
from pathlib import Path
import re
import time

from hybrid_routes import itinerary_legs
from patrol_photo_survey import PatrolPhotoSurvey, validated_targets
from resident_runtime import atomic_json


def read_plan(path):
    """Load the bounded objectives once and retain their original file digest."""
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    validate_plan(plan)
    return plan, hashlib.sha256(raw).hexdigest()


def validate_plan(plan):
    """Validate the same fixed list in the launcher and inside the RDP child."""
    if not isinstance(plan, dict):
        raise ValueError('Expected a warm photo plan object')
    requests = plan.get('requests')
    if type(plan.get('version')) is not int or plan['version'] not in (1, 2) or not isinstance(requests, list) or not 2 <= len(requests) <= 4:
        raise ValueError('Expected two to four named photo requests')
    directed = plan['version'] == 2
    if 'confirmFirstArrival' in plan and (not directed or type(plan['confirmFirstArrival']) is not bool):
        raise ValueError('First-arrival confirmation requires a boolean on a destination plan')
    for request in requests:
        if (not isinstance(request, dict) or not isinstance(request.get('id'), str)
                or not re.fullmatch(r'[0-9a-f]{32}', request['id']) or not isinstance(request.get('name'), str)
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', request['name'])):
            raise ValueError('Invalid warm photo request identity or name')
        validated_targets(request.get('targets'))
        if directed:
            if request['targets'] != [request.get('destination')] or 'circuits' in request:
                raise ValueError('A destination request must photograph its single declared destination')
        elif type(request.get('circuits')) is not int or not 1 <= request['circuits'] <= 32:
            raise ValueError('Invalid warm circuit budget')
    if len({r['id'] for r in requests}) != len(requests) or len({r['name'] for r in requests}) != len(requests):
        raise ValueError('Warm requests require distinct identities and names')
    if directed:
        if plan.get('mode') != 'destinations':
            raise ValueError('Expected version 2 destinations mode')
        itinerary_legs(plan.get('start'), [r['destination'] for r in requests])
    elif (len({frozenset(r['targets']) for r in requests}) != len(requests)
          or sum(r['circuits'] for r in requests) > 32):
        raise ValueError('Warm patrol requests require distinct target sets within 32 circuits')
    return requests


class WarmPhotoRequests:
    """Serial policy-thread state for the current request, its outstanding actions and native release barrier."""

    def __init__(self, plan, directory, checkpoint_id, embedding, hello, run_id, legs):
        """Bind the plan, embedding and request journals to this one resident/bridge identity."""
        definition, self.plan_sha = read_plan(plan)
        self.requests = definition['requests']
        self.destinations = None
        self.confirm_first = definition.get('confirmFirstArrival', False)
        self.itinerary_start = None
        if definition['version'] == 2:
            self.itinerary_start = definition['start']
            self.destinations = tuple(r['destination'] for r in self.requests)
            edges = itinerary_legs(self.itinerary_start, self.destinations)
            self.request_legs = [sum(owner == i for _, _, owner in edges) for i in range(1, len(self.requests) + 1)]
        else:
            self.request_legs = [4 * r['circuits'] for r in self.requests]
        if sum(self.request_legs) != legs:
            raise ValueError('Warm plan does not match the resident leg limit')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.checkpoint_id = checkpoint_id
        self.identity = dict(sessionId=hello['sessionId'], ownerEpoch=hello['ownerEpoch'], runId=run_id,
                             planSha256=self.plan_sha, goalEmbeddingSha256=hashlib.sha256(Path(embedding).read_bytes()).hexdigest())
        self.index = 0
        self.active_after = None
        self.release = None
        self.retry_endpoint = None
        self.retry_deadline_ns = None
        self.retry_count = 0
        self.first_confirmed_frame = None
        self.started = self.finished = False
        self._open()

    @property
    def current(self):
        """The only photo request allowed to receive the current policy transaction."""
        return self.requests[self.index]

    def _open(self):
        """A new request begins with empty action and image history."""
        # Only the initial destination request can own the itinerary's verified starting frame.
        start = 'stair-front'
        if self.destinations:
            start = self.itinerary_start if self.index == 0 else None
        self.survey = PatrolPhotoSurvey(self.directory/self.current['id'], self.current['targets'], self.checkpoint_id,
                                        start_station=start)
        self.pending = set()
        self.first_accepted = self.first_applied = self.last_accepted = None
        self._status()

    @property
    def needs_first_view(self):
        """Only request one of a declared two-view trial may defer its first positive match."""
        return self.confirm_first and self.index == 0 and self.first_confirmed_frame is None

    def _status(self):
        """Publish only sparse request milestones for the external operator-stop probe."""
        accepted, applied = self.first_accepted or (None, None), self.first_applied or (None, None)
        atomic_json(self.directory/'warm-status.json', dict(version=1, runId=self.identity['runId'],
                    activeRequestId=self.current['id'], activeOrdinal=self.index+1, complete=self.finished,
                    activeFirstAcceptedRequestId=accepted[0], activeFirstAcceptedFrameId=accepted[1],
                    activeFirstAppliedRequestId=applied[0], activeFirstAppliedFrameId=applied[1]))

    def require_action_frame(self, frame_id):
        """Check ownership and receipt capacity before the bridge can receive any new input."""
        if (not self.started or self.finished or self.retry_endpoint is not None
                or (self.active_after is not None and frame_id <= self.active_after)):
            raise RuntimeError('Warm action is outside its request frame boundary')
        if len(self.pending) >= 32:
            raise RuntimeError('Incomplete terminal receipts at the warm request boundary')

    def accepted(self, request_id, frame_id):
        """Track each admitted ordinary or recovery action until its real terminal is observed."""
        self.require_action_frame(frame_id)
        self.pending.add(request_id)
        self.last_accepted = request_id
        if self.first_accepted is None:
            self.first_accepted = (request_id, frame_id)
            self._status()

    def receipt(self, receipt):
        """Retire pending IDs on the policy thread, after the serial action transaction."""
        key = receipt['requestId']
        if key in self.pending:
            self.pending.remove(key)
            if self.first_applied is None and receipt.get('appliedSteps'):
                self.first_applied = (key, receipt['frameId'])
                self._status()

    def released(self, frame_id, reply):
        """Retain the endpoint release response after the existing policy-history reset has succeeded."""
        gate = reply['worldReadiness']
        self.release = dict(type=reply['type'], arrivalFrameId=frame_id, serverNowMs=reply['serverNowMs'],
                            readinessEpoch=gate['epoch'], readinessReason=gate['reason'], readinessReady=gate['ready'],
                            captureEpoch=gate['sourceFrame']['captureEpoch'], policyHistoryReset=True)
        return dict(self.release)

    def _event(self, kind, native, legs, **detail):
        """Persist causal frame, lease and request identity on every lifecycle transition."""
        goal = dict(destination=self.current['destination']) if self.destinations else dict(circuits=self.current['circuits'])
        return dict(type=kind, warmRequestId=self.current['id'], ordinal=self.index+1, name=self.current['name'],
                    targets=list(self.current['targets']), **goal, frameId=native['frameId'],
                    sourceEpoch=native['sourceEpoch'], completedLegs=legs, **self.identity, **detail)

    def check_photo_deadline(self):
        """A missing frame must not extend the stationary observation window."""
        if self.retry_deadline_ns is not None and time.perf_counter_ns() > self.retry_deadline_ns:
            raise RuntimeError('Destination photo remained unverified after 1500 ms')

    def after_native(self, native, endpoint=None, *, received_ns=None):
        """Finish only after native endpoint/release proof, terminal receipts and the complete photo task."""
        if native['type'] == 'hybridStartVerified':
            if self.started:
                raise RuntimeError('Duplicate warm patrol start')
            if self.destinations and native.get('station') != self.itinerary_start:
                raise RuntimeError('Native start differs from the pinned itinerary start')
            self.started = True
            return [self._event('warmPhotoRequestStarted', native, 0)]
        retry = native['type'] == 'hybridDestinationPhotoRetry' and self.destinations is not None
        if not retry and native['type'] != ('hybridDestinationVerified' if self.destinations else 'hybridCircuitVerified'):
            return []
        if retry:
            self.check_photo_deadline()
            endpoint = self.retry_endpoint
            if (not endpoint or native.get('initialEndpointFrameId') != endpoint['samples'][-1]['frameId']
                    or native.get('retryOrdinal') != self.retry_count + 1 or self.retry_count >= 3
                    or native['frameId'] != native['samples'][-1]['frameId']
                    or any(native.get(field) != endpoint.get(field) for field in
                           ('releaseAtMs', 'releaseEpoch', 'arrivalFrameId', 'sourceEpoch'))):
                raise RuntimeError('Stationary photo retry differs from the original released endpoint')
            self.retry_count += 1
        legs = native['completedLegs']
        expected_legs = sum(self.request_legs[:self.index+1])
        if self.destinations:
            destination = self.current['destination']
            if (legs != expected_legs or native.get('destinationOrdinal') != self.index+1
                    or native.get('requestedDestination') != destination or native.get('station') != destination
                    or not endpoint or endpoint.get('station') != destination):
                raise RuntimeError('Destination handoff requires a fresh photo at its exact requested endpoint')
        elif legs != expected_legs:
            return []
        release = self.release
        if (self.pending or self.first_applied is None or not endpoint
                or (not retry and endpoint['samples'][-1]['frameId'] != native['frameId'])
                or not release or release['type'] != 'released' or release['readinessReason'] != 'client_release'
                or release['readinessReady'] is not False or release['captureEpoch'] != native['sourceEpoch']
                or release['readinessEpoch'] != endpoint['releaseEpoch'] or release['serverNowMs'] != endpoint['releaseAtMs']
                or release['arrivalFrameId'] != endpoint['arrivalFrameId']):
            raise RuntimeError('Warm request cannot finish without verified release, terminal receipts and complete photos')
        if self.destinations and self.survey.collected.get(destination) != native['frameId']:
            visit = (native if retry else endpoint).get('photoSurveyVisit') or {}
            confirmation = self.needs_first_view and visit.get('outcome') == 'confirmationPending'
            if ((not confirmation and visit.get('outcome') != 'classificationMiss') or visit.get('station') != destination
                    or visit.get('frameId') != native['frameId'] or not visit.get('retryEvidenceFile')):
                raise RuntimeError('Destination handoff requires a fresh photo at its exact requested endpoint')
            if confirmation:
                self.first_confirmed_frame = native['frameId']
            if not retry:
                self.retry_endpoint = endpoint
                self.retry_deadline_ns = (received_ns if received_ns is not None else time.perf_counter_ns()) + 1_500_000_000
            if self.retry_count >= 3:
                raise RuntimeError('Destination photo remained unverified after three stationary retries')
            self.check_photo_deadline()
            return []
        if not self.survey.snapshot()['complete']:
            raise RuntimeError('Warm request requires complete photos')
        if self.needs_first_view:
            raise RuntimeError('First destination requires two separately qualified views')
        proof = dict(release=dict(release), pendingActionIds=[], lastAcceptedRequestId=self.last_accepted)
        if retry:
            proof.update(initialEndpointFrameId=native['initialEndpointFrameId'], retryOrdinal=native['retryOrdinal'])
            if self.index == 0 and self.confirm_first:
                proof['firstConfirmedFrameId'] = self.first_confirmed_frame
            self.retry_endpoint = self.retry_deadline_ns = None
            self.retry_count = 0
        rows = [self._event('warmPhotoRequestCompleted', native, legs, **proof)]
        if self.index + 1 == len(self.requests):
            self.finished = True
            self._status()
        else:
            previous = self.current['id']
            rows.append(self._event('warmPhotoHandoff', native, legs, nextRequestId=self.requests[self.index+1]['id'], **proof))
            self.index += 1
            self.active_after = native['frameId']
            self.release = None
            self._open()
            rows.append(self._event('warmPhotoRequestStarted', native, legs, previousRequestId=previous))
        return rows
