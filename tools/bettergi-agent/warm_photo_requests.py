"""Attribute predeclared photo requests to disjoint frames and actions on one verified patrol lease."""
import hashlib
import json
from pathlib import Path
import re

from patrol_photo_survey import PatrolPhotoSurvey, validated_targets
from resident_runtime import atomic_json


def read_plan(path):
    """Load the bounded objectives once and retain their original file digest."""
    raw = Path(path).read_bytes()
    return validate_plan(json.loads(raw)), hashlib.sha256(raw).hexdigest()


def validate_plan(plan):
    """Validate the same fixed list in the launcher and inside the RDP child."""
    if not isinstance(plan, dict):
        raise ValueError('Expected a warm photo plan object')
    requests = plan.get('requests')
    if plan.get('version') != 1 or not isinstance(requests, list) or not 2 <= len(requests) <= 4:
        raise ValueError('Expected a version 1 plan with two to four photo requests')
    for request in requests:
        if (not isinstance(request, dict) or not isinstance(request.get('id'), str)
                or not re.fullmatch(r'[0-9a-f]{32}', request['id']) or not isinstance(request.get('name'), str)
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', request['name'])
                or type(request.get('circuits')) is not int or not 1 <= request['circuits'] <= 32):
            raise ValueError('Invalid warm photo request identity, name or circuit budget')
        validated_targets(request['targets'])
    if (len({r['id'] for r in requests}) != len(requests) or len({r['name'] for r in requests}) != len(requests)
            or len({frozenset(r['targets']) for r in requests}) != len(requests)
            or sum(r['circuits'] for r in requests) > 32):
        raise ValueError('Warm requests require distinct identities, names and target sets within 32 circuits')
    return requests


class WarmPhotoRequests:
    """Serial policy-thread state for the current request, its outstanding actions and native release barrier."""

    def __init__(self, plan, directory, checkpoint_id, embedding, hello, run_id, legs):
        """Bind the plan, embedding and request journals to this one resident/bridge identity."""
        self.requests, self.plan_sha = read_plan(plan)
        if 4 * sum(r['circuits'] for r in self.requests) != legs:
            raise ValueError('Warm plan does not match the resident leg limit')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.checkpoint_id = checkpoint_id
        self.identity = dict(sessionId=hello['sessionId'], ownerEpoch=hello['ownerEpoch'], runId=run_id,
                             planSha256=self.plan_sha, goalEmbeddingSha256=hashlib.sha256(Path(embedding).read_bytes()).hexdigest())
        self.index = 0
        self.active_after = None
        self.release = None
        self.started = self.finished = False
        self._open()

    @property
    def current(self):
        """The only photo request allowed to receive the current policy transaction."""
        return self.requests[self.index]

    def _open(self):
        """A new request begins with empty action and image history."""
        self.survey = PatrolPhotoSurvey(self.directory/self.current['id'], self.current['targets'], self.checkpoint_id)
        self.pending = set()
        self.first_accepted = self.first_applied = self.last_accepted = None
        self._status()

    def _status(self):
        """Publish only sparse request milestones for the external operator-stop probe."""
        accepted, applied = self.first_accepted or (None, None), self.first_applied or (None, None)
        atomic_json(self.directory/'warm-status.json', dict(version=1, runId=self.identity['runId'],
                    activeRequestId=self.current['id'], activeOrdinal=self.index+1, complete=self.finished,
                    activeFirstAcceptedRequestId=accepted[0], activeFirstAcceptedFrameId=accepted[1],
                    activeFirstAppliedRequestId=applied[0], activeFirstAppliedFrameId=applied[1]))

    def require_action_frame(self, frame_id):
        """Check ownership and receipt capacity before the bridge can receive any new input."""
        if not self.started or self.finished or (self.active_after is not None and frame_id <= self.active_after):
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
        return dict(type=kind, warmRequestId=self.current['id'], ordinal=self.index+1, name=self.current['name'],
                    targets=list(self.current['targets']), circuits=self.current['circuits'], frameId=native['frameId'],
                    sourceEpoch=native['sourceEpoch'], completedLegs=legs, **self.identity, **detail)

    def after_native(self, native, endpoint=None):
        """Finish only after native endpoint/release proof, terminal receipts and the complete photo task."""
        if native['type'] == 'hybridStartVerified':
            if self.started:
                raise RuntimeError('Duplicate warm patrol start')
            self.started = True
            return [self._event('warmPhotoRequestStarted', native, 0)]
        if native['type'] != 'hybridCircuitVerified':
            return []
        legs = native['completedLegs']
        if legs != 4 * sum(r['circuits'] for r in self.requests[:self.index+1]):
            return []
        release = self.release
        if (not self.survey.snapshot()['complete'] or self.pending or self.first_applied is None
                or not endpoint or endpoint['samples'][-1]['frameId'] != native['frameId']
                or not release or release['type'] != 'released' or release['readinessReason'] != 'client_release'
                or release['readinessReady'] is not False or release['captureEpoch'] != native['sourceEpoch']
                or release['readinessEpoch'] != endpoint['releaseEpoch'] or release['serverNowMs'] != endpoint['releaseAtMs']
                or release['arrivalFrameId'] != endpoint['arrivalFrameId']):
            raise RuntimeError('Warm request cannot finish without verified release, terminal receipts and complete photos')
        proof = dict(release=dict(release), pendingActionIds=[], lastAcceptedRequestId=self.last_accepted)
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
