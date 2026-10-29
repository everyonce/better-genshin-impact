"""Attribute predeclared photo requests to disjoint frames and actions on one verified patrol lease."""
import hashlib
import json
import math
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


def batch_plan_digest(plan):
    """Digest a nested JSON plan independently of its envelope's whitespace and byte digest."""
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()


def request_leg_counts(plan):
    """Derive exact per-request edge budgets from the reviewed ordered station graph."""
    destinations = [row['destination'] for row in plan['requests']]
    edges = itinerary_legs(plan['start'], destinations)
    return [sum(owner == i for _, _, owner in edges) for i in range(1, len(destinations)+1)]


def batch_bytes(path):
    """Read an addressed queue document under the resident's fixed memory cap."""
    with path.open('rb') as source:
        raw = source.read(16385)
    if len(raw) > 16384:
        raise ValueError('Oversized destination batch document')
    return raw


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


class WarmQueueStarved(RuntimeError):
    """A verified open-queue boundary expired without an admissible next decision."""


class WarmQueueInterrupted(RuntimeError):
    """A run-bound operator command preempted an already released queue boundary."""
    def __init__(self, reason, source):
        super().__init__(reason)
        self.reason, self.source = reason, source


class WarmPhotoRequests:
    """Serial policy-thread state for the current request, its outstanding actions and native release barrier."""

    def __init__(self, plan, directory, checkpoint_id, embedding, hello, run_id, legs, *, batch_count=None, open_queue=False, control_path=None):
        """Bind the plan, embedding and request journals to this one resident/bridge identity."""
        definition, self.plan_sha = read_plan(plan)
        self.requests = definition['requests']
        self.destinations = None
        self.confirm_first = definition.get('confirmFirstArrival', False)
        self.itinerary_start = None
        if definition['version'] == 2:
            self.itinerary_start = definition['start']
            self.destinations = tuple(r['destination'] for r in self.requests)
            self.request_legs = request_leg_counts(definition)
        else:
            self.request_legs = [4 * r['circuits'] for r in self.requests]
        self.batch_count, self.max_legs = batch_count, legs
        self.batch_boundary = None
        self.batch_witnesses = {}
        self.batch_clocks = {}
        self.batch_scope = {}
        self.batch_dispatch_before_ms = None
        self.open_queue = open_queue
        self.first_dispatch = None
        if open_queue:
            from landmark_recognizer import G4_SHA256
            self.control_path = Path(control_path) if control_path is not None else Path(plan).resolve().parent/'patrol.json.control.json'
            telemetry = hello.get('inputTelemetry') or {}
            self.frequency = telemetry.get('stopwatchFrequency')
            self.origin = telemetry.get('sessionOriginAtStopwatchTicks')
            if (batch_count is None or checkpoint_id != G4_SHA256
                    or any(type(v) is not int or v <= 0 for v in (self.frequency,self.origin))):
                raise ValueError('An open destination queue requires bounded batches, deployed G4 and the native QPC clock')
        if batch_count is not None:
            reserved = 0 if open_queue or type(batch_count) is not int else 2*(batch_count-1)
            if (not self.destinations or type(batch_count) is not int or not 2 <= batch_count <= 12
                    or type(legs) is not int or not sum(self.request_legs) + reserved <= legs <= 96):
                raise ValueError('Successive destination batches require feasible batch and total edge limits')
            if (set(definition) - {'version','mode','start','requests','confirmFirstArrival'}
                    or any(set(r) != {'id','name','destination','targets'} for r in self.requests)):
                raise ValueError('Initial batch must use the reviewed destination request schema')
            self.batch_directory = Path(plan).resolve().parent/'batches'
            suffixes = ('.json','.intent.json','.publication.json','.decision.json') if open_queue else ('.json',)
            if any((self.batch_directory/f'{n:05}{suffix}').exists() for n in range(2,batch_count+1+int(open_queue)) for suffix in suffixes):
                raise ValueError('Successor batches cannot be published before gameplay')
            self.batch_scope = dict(batchOrdinal=1,batchSha256=self.plan_sha,batchPlanSha256=batch_plan_digest(definition))
        elif sum(self.request_legs) != legs:
            raise ValueError('Warm plan does not match the resident leg limit')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.checkpoint_id = checkpoint_id
        self.identity = dict(sessionId=hello['sessionId'], ownerEpoch=hello['ownerEpoch'], runId=run_id,
                             planSha256=self.plan_sha, goalEmbeddingSha256=hashlib.sha256(Path(embedding).read_bytes()).hexdigest())
        self.index = 0
        self.active_after = None
        self.release = None
        self.release_retry_blocked = False
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
        self.pending = {}
        self.first_accepted = self.first_applied = self.last_accepted = None
        self.last_applied_at_ms = None
        self.last_terminal_ms = None
        self.gameplay_clock = None
        self._status()

    @property
    def needs_first_view(self):
        """Only request one of a declared two-view trial may defer its first positive match."""
        return self.confirm_first and self.index == 0 and self.first_confirmed_frame is None

    def _status(self):
        """Publish only sparse request milestones for the external operator-stop probe."""
        accepted, applied = self.first_accepted or (None, None), self.first_applied or (None, None)
        atomic_json(self.directory/'warm-status.json', dict(version=1, runId=self.identity['runId'],
                    sessionId=self.identity['sessionId'], ownerEpoch=self.identity['ownerEpoch'], **self.batch_scope,
                    **({'gameplayClock':self.gameplay_clock} if self.open_queue and self.gameplay_clock else {}),
                    activeRequestId=self.current['id'], activeOrdinal=self.index+1, complete=self.finished,
                    activeFirstAcceptedRequestId=accepted[0], activeFirstAcceptedFrameId=accepted[1],
                    activeFirstAppliedRequestId=applied[0], activeFirstAppliedFrameId=applied[1]))

    def require_action_frame(self, frame_id):
        """Check ownership and receipt capacity before the bridge can receive any new input."""
        if (not self.started or self.finished or self.release_retry_blocked or self.retry_endpoint is not None or self.batch_boundary is not None
                or (self.active_after is not None and frame_id <= self.active_after)):
            raise RuntimeError('Warm action is outside its request frame boundary')
        if len(self.pending) >= 32:
            raise RuntimeError('Incomplete terminal receipts at the warm request boundary')

    def accepted(self, request_id, frame_id):
        """Track each admitted ordinary or recovery action until its real terminal is observed."""
        self.require_action_frame(frame_id)
        self.pending[request_id] = frame_id
        self.last_accepted = request_id
        if self.first_accepted is None:
            self.first_accepted = (request_id, frame_id)
            self._status()

    def require_batch_dispatch_window(self, start_before_ms):
        """Keep the bridge's full 150 ms source deadline inside the previous batch's one-second handoff."""
        if self.batch_dispatch_before_ms is not None and (type(start_before_ms) not in (int,float)
                or not math.isfinite(start_before_ms) or start_before_ms >= self.batch_dispatch_before_ms):
            raise RuntimeError('Successor dispatch would exceed the one-second warm handoff')

    def awaiting_batch_dispatch_receipt(self, server_now_ms):
        """Observe without proposing until the first accepted successor yields an actual terminal receipt."""
        if self.batch_dispatch_before_ms is None or not self.pending:
            return False
        self.check_batch_interruption()
        # The request has an existing 700 ms native lifetime. A delayed receipt can prove an
        # earlier dispatch, but waiting for it never extends the deadline for that dispatch.
        if (type(server_now_ms) not in (int,float) or not math.isfinite(server_now_ms) or server_now_ms < 0
                or server_now_ms >= self.batch_dispatch_before_ms + 700):
            raise RuntimeError('First successor dispatch receipt did not settle within its bounded wait')
        return True

    def receipt(self, receipt):
        """Retire pending IDs on the policy thread, after the serial action transaction."""
        key = receipt['requestId']
        if key in self.pending:
            if self.open_queue:
                accepted,ended = receipt.get('acceptedAtMs'),receipt.get('endedAtMs')
                if (self.pending[key] != receipt.get('frameId') or receipt.get('status') not in ('completed','cancelled','replaced','expired')
                        or not isinstance(receipt.get('appliedSteps'),list)
                        or any(type(t) not in (int,float) or not math.isfinite(t) for t in (accepted,ended))
                        or not 0 <= accepted <= ended):
                    raise ValueError('Open queue requires the accepted frame and genuine terminal receipt')
                self.last_terminal_ms = max(self.last_terminal_ms or ended,ended)
            if self.batch_count and receipt.get('appliedSteps'):
                times = [s['startedAtMs'] for s in receipt['appliedSteps']]
                if any(type(t) not in (int,float) or not math.isfinite(t) for t in times):
                    raise ValueError('Invalid batch native dispatch time')
                if self.open_queue and (times != sorted(times) or not accepted <= times[0] <= times[-1] <= ended):
                    raise ValueError('Open queue dispatch is outside its terminal receipt')
                if self.batch_dispatch_before_ms is not None and (
                        self.pending[key] != receipt.get('frameId')
                        or not self.batch_dispatch_before_ms - 1000 < times[0] < self.batch_dispatch_before_ms):
                    raise ValueError('First successor dispatch is outside its original frame or one-second handoff')
                self.last_applied_at_ms = max(times) if self.last_applied_at_ms is None else max(self.last_applied_at_ms, *times)
                self.batch_dispatch_before_ms = None
            del self.pending[key]
            if self.first_applied is None and receipt.get('appliedSteps'):
                self.first_applied = (key, receipt['frameId'])
                if self.batch_count:
                    self.batch_witnesses[self.current['id']] = self.first_applied
                if self.open_queue:
                    if min(times) <= 0:
                        raise ValueError('Open queue requires an actual positive dispatch timestamp')
                    ticks = self.origin + round(min(times)*self.frequency/1000)
                    if self.first_dispatch is None:
                        self.first_dispatch = dict(firstAppliedTicks=ticks,firstNativeRequestId=key,firstFrameId=receipt['frameId'])
                    if ticks < self.first_dispatch['firstAppliedTicks']:
                        raise ValueError('Open queue dispatch clock regressed')
                    self.gameplay_clock = dict(self.first_dispatch,frequencyHz=self.frequency,witnessAppliedTicks=ticks)
                    self.batch_clocks[self.current['id']] = self.gameplay_clock
                self._status()

    def released(self, frame_id, reply):
        """Retain the endpoint release response after the existing policy-history reset has succeeded."""
        gate = reply['worldReadiness']
        evidence = dict(type=reply['type'], arrivalFrameId=frame_id, serverNowMs=reply['serverNowMs'],
                            readinessEpoch=gate['epoch'], readinessReason=gate['reason'], readinessReady=gate['ready'],
                            captureEpoch=gate['sourceFrame']['captureEpoch'], policyHistoryReset=True)
        self.release = evidence if gate['reason'] == 'client_release' else None
        self.release_retry_blocked = self.release is None
        return dict(evidence)

    def _event(self, kind, native, legs, **detail):
        """Persist causal frame, lease and request identity on every lifecycle transition."""
        goal = dict(destination=self.current['destination']) if self.destinations else dict(circuits=self.current['circuits'])
        return dict(type=kind, warmRequestId=self.current['id'], ordinal=self.index+1, name=self.current['name'],
                    targets=list(self.current['targets']), **goal, frameId=native['frameId'],
                    sourceEpoch=native['sourceEpoch'], completedLegs=legs, **self.identity, **self.batch_scope, **detail)

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
        if self.open_queue and (self.last_terminal_ms is None or self.last_terminal_ms > release['serverNowMs']):
            raise RuntimeError('Open queue requires all terminal actions to end before endpoint release')
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
        if self.index + 1 == len(self.requests) and self.batch_count and (self.open_queue or self.batch_scope['batchOrdinal'] < self.batch_count):
            self.batch_boundary = (native, proof, (received_ns or time.perf_counter_ns()) + 1_000_000_000)
        elif self.index + 1 == len(self.requests):
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

    def check_batch_interruption(self):
        """Honor the original addressed command or operator STOP marker before interpreting a boundary failure."""
        if not self.open_queue or (self.batch_boundary is None and (
                self.batch_dispatch_before_ms is None or not self.pending)):
            return
        from resident_runtime import read_control_document
        doc,error = read_control_document(self.control_path,self.identity['runId'])
        if error:
            raise ValueError('Open queue released boundary lost its addressed control: '+error)
        if doc['command']=='stop':
            raise WarmQueueInterrupted('userStop','addressedControl')
        if (self.batch_directory.parent/'STOP').exists():
            raise WarmQueueInterrupted('userStop','runLocalStopFile')
        if doc['command']=='pause':
            raise WarmQueueInterrupted('userPause','addressedControl')

    def check_batch_deadline(self):
        """A missing successor or capture cannot extend the released boundary wait."""
        self.check_batch_interruption()
        if self.batch_boundary and time.perf_counter_ns() > self.batch_boundary[2]:
            if self.open_queue:
                raise WarmQueueStarved('No qualified open-queue decision within the 1000 ms released boundary')
            raise RuntimeError('No qualified destination batch within the 1000 ms released boundary')

    def starved_event(self):
        """Identify the original released request and terminal receipt barrier when the external slot times out."""
        from run_rdp_patrol import native_qpc_sample
        native,proof,_ = self.batch_boundary
        freq,ticks = native_qpc_sample()
        return self._event('warmQueueStarved',native,native['completedLegs'],decisionOrdinal=self.batch_scope['batchOrdinal']+1,
                           failedQpc=dict(clock='windows-query-performance-counter',frequencyHz=freq,ticks=ticks),**proof)

    def consume_batch(self, admission_frame, *, still_current=None):
        """Read only the next append-only envelope at a verified boundary, authenticating its applied-action witness."""
        if not self.batch_boundary:
            raise RuntimeError('Successor needs a verified, released request boundary')
        self.check_batch_deadline()
        native, proof, _ = self.batch_boundary
        if type(admission_frame) is not int or admission_frame < native['frameId']:
            raise ValueError('Successor admission needs a fresh frame at the released station')
        number = self.batch_scope['batchOrdinal'] + 1
        prefix = self.batch_directory/f'{number:05}'
        try:
            publication_raw = batch_bytes(prefix.with_suffix('.publication.json'))
        except FileNotFoundError:
            return None
        published = json.loads(publication_raw)
        raw = batch_bytes(prefix.with_suffix('.json'))
        envelope = json.loads(raw)
        intent_raw = batch_bytes(prefix.with_suffix('.intent.json'))
        intent = json.loads(intent_raw)
        fixed = dict(version=1, mode='destination-batch', batchOrdinal=number,
                     previousSha256=self.batch_scope['batchSha256'],
                     **{key:self.identity[key] for key in ('runId','sessionId','ownerEpoch')})
        finishing = self.open_queue and isinstance(envelope,dict) and envelope.get('kind') == 'finish'
        decision_key = 'kind' if finishing else 'plan'
        if (not isinstance(envelope, dict) or set(envelope) != set(fixed) | {'witness',decision_key}
                or number > self.batch_count + int(finishing)
                or any(type(envelope[k]) is not type(value) or envelope[k] != value for k,value in fixed.items())):
            raise ValueError('Misaddressed destination batch envelope')
        witness = envelope['witness']
        if (not isinstance(witness, dict) or set(witness) != {'batchOrdinal','requestId','nativeRequestId','frameId'}
                or type(witness['batchOrdinal']) is not int or witness['batchOrdinal'] != number-1
                or type(witness['frameId']) is not int or not isinstance(witness['requestId'],str)
                or self.batch_witnesses.get(witness['requestId']) != (witness['nativeRequestId'],witness['frameId'])):
            raise ValueError('Successor is missing its predecessor gameplay witness')
        from run_rdp_patrol import native_qpc_sample
        raw_sha = hashlib.sha256(raw).hexdigest()
        if not finishing:
            plan = envelope['plan']
            requests = validate_plan(plan)
            if (set(plan) != {'version','mode','start','requests'} or plan['version'] != 2
                    or any(set(r) != {'id','name','destination','targets'} for r in requests)
                    or plan['start'] != self.current['destination']
                    or any({r[key] for r in requests} & {r[key] for r in self.requests} for key in ('id','name'))):
                raise ValueError('Successor must start at the released station with fresh request identities and names')
            counts = request_leg_counts(plan)
            reserved = 0 if self.open_queue else 2*(self.batch_count-number)
            if sum(self.request_legs) + sum(counts) + reserved > self.max_legs:
                raise ValueError('Successor exceeds the resident edge budget')
            scope = dict(batchOrdinal=number, batchSha256=raw_sha, batchPlanSha256=batch_plan_digest(plan))
        # The producer seals the exact selected plan before publishing the envelope and writes its receipt last.
        address = {k:v for k,v in fixed.items() if k != 'mode'}
        address.update(witness=witness, batchSha256=raw_sha)
        decision_proof = {}
        if self.open_queue:
            decision_raw = batch_bytes(prefix.with_suffix('.decision.json'))
            decision = json.loads(decision_raw)
            clock = self.batch_clocks[witness['requestId']]
            selected = [] if finishing else [r['destination'] for r in requests]
            if (decision.get('type') != 'destinationQueueDecision' or any(decision.get(k) != v for k,v in address.items())
                    or decision.get('gameplayClock') != clock or decision.get('selectedStations') != selected):
                raise ValueError('Open queue policy evidence differs from its addressed gameplay witness or selection')
            decision_proof['policyDecisionSha256'] = hashlib.sha256(decision_raw).hexdigest()
            address.update(decision_proof)
        observed = intent.get('observedAtMonotonicNs')
        bracket = published.get('publicationQpc') or {}
        qpc = native_qpc_sample()
        self.check_batch_deadline()
        if qpc is None:
            raise RuntimeError('A native monotonic timestamp is required for successor admission')
        if (type(observed) is not int or observed <= 0
                or intent != dict(address,type='destinationBatchIntent',observedAtMonotonicNs=observed,**{decision_key:envelope[decision_key]})
                or any(published.get(k) != v for k,v in address.items())
                or published.get('type') != 'destinationBatchPublished' or published.get('observedAtMonotonicNs') != observed
                or type(published.get('publishedAtMonotonicNs')) is not int or published['publishedAtMonotonicNs'] < observed
                or bracket.get('clock') != 'windows-query-performance-counter' or bracket.get('frequencyHz') != qpc[0]
                or not all(type(bracket.get(k)) is int for k in ('beforeTicks','afterTicks'))
                or not 0 < bracket['beforeTicks'] <= bracket['afterTicks'] <= qpc[1]):
            raise ValueError('Destination batch differs from the sealed external selection or publication')
        if self.open_queue:
            if qpc[0] != self.frequency or self.pending or self.release != proof['release']:
                raise ValueError('Open queue changed its clock, released endpoint or terminal receipt barrier')
            if bracket['beforeTicks'] < clock['witnessAppliedTicks']:
                raise ValueError('Open queue decision was published before its claimed gameplay witness')
            source_ticks = self.origin + round(native['atMs']*self.frequency/1000)
            if not source_ticks <= qpc[1] <= source_ticks+self.frequency:
                raise WarmQueueStarved('Open-queue decision missed the native 1000 ms released boundary')
            if still_current is not None and not still_current():
                return None
            self.check_batch_interruption()
        consumed = dict(clock='windows-query-performance-counter',frequencyHz=qpc[0],ticks=qpc[1])
        if finishing:
            row = self._event('warmQueueFinished',native,native['completedLegs'],decisionOrdinal=number,
                              decisionSha256=raw_sha,decisionBytes=len(raw),publicationWitness=witness,
                              intentSha256=hashlib.sha256(intent_raw).hexdigest(),publicationSha256=hashlib.sha256(publication_raw).hexdigest(),
                              admissionFrameId=admission_frame,consumedQpc=consumed,**decision_proof,**proof)
            self.finished,self.batch_boundary = True,None
            self._status()
            return None,[row]
        previous, following, legs = self.current['id'], requests[0]['id'], native['completedLegs']
        self.requests.extend(requests)
        self.request_legs.extend(counts)
        rows = [self._event('warmBatchAccepted', native, legs, nextRequestId=following, nextBatchOrdinal=number,
                            nextBatchSha256=scope['batchSha256'], nextBatchPlanSha256=scope['batchPlanSha256'],
                            nextBatchBytes=len(raw), publicationWitness=witness, admissionFrameId=admission_frame,
                            consumedQpc=consumed, **decision_proof, **proof),
                self._event('warmPhotoHandoff', native, legs, nextRequestId=following, **proof)]
        self.batch_scope, self.batch_witnesses, self.batch_clocks, self.batch_boundary = scope, {}, {}, None
        self.batch_dispatch_before_ms = self.last_applied_at_ms + 1000
        self.index += 1
        self.active_after, self.release = admission_frame, None
        self._open()
        rows.append(self._event('warmPhotoRequestStarted', native, legs, previousRequestId=previous))
        return [r['destination'] for r in requests], rows
