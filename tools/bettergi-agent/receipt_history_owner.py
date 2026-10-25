"""Single pending native proposal; only a matching terminal software report commits.

No transport, factory or input authority is supplied. The caller must authenticate
the connection and serialize request/response handling on this owner thread.
"""
import json
import math
from dataclasses import dataclass

from native_history_feedback import NativeHistoryOwner, Proposal, ProposalToken, FeedbackError, require


def canonical(value):
    """Bound detached JSON also distinguishes booleans from numeric action fields."""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(len(raw.encode('utf-8')) <= 16384, 'receipt_payload_capacity')
    return raw


def identity(value):
    """Keep origin frame/session/control/goal/source identities separate from receipt times."""
    require(type(value) is dict and set(value) == {'sessionId', 'ownerEpoch', 'goalVersion', 'controlEpoch',
        'policyGoalVersion', 'readinessEpoch', 'sourceEpoch', 'frameId', 'modelId'}, 'decision_identity_fields')
    for name in ('sessionId', 'ownerEpoch', 'sourceEpoch', 'modelId'):
        require(type(value[name]) is str and 0 < len(value[name]) <= 128, 'decision_identity:' + name)
    for name in ('goalVersion', 'controlEpoch', 'policyGoalVersion', 'readinessEpoch', 'frameId'):
        require(type(value[name]) is int and value[name] >= 0, 'decision_identity:' + name)
    return canonical(value)


def one_step(steps):
    """Only the unchanged native one-step submission is in this candidate's contract."""
    require(type(steps) is list and len(steps) == 1 and type(steps[0]) is dict, 'one_step_only')
    step = steps[0]
    require(set(step) == {'durationMs', 'keys', 'mouseDx', 'mouseDy'}
            and type(step['durationMs']) is int and step['durationMs'] == 50, 'native_step_shape')
    require(type(step['keys']) is list and len(step['keys']) <= 6
            and all(type(k) is str and 0 < len(k) <= 24 for k in step['keys'])
            and len(set(step['keys'])) == len(step['keys']), 'native_keys')
    require(all(type(step[n]) is int for n in ('mouseDx', 'mouseDy')), 'native_mouse_integers')
    return canonical(steps)


@dataclass(frozen=True)
class ReceiptSettlement:
    """History publication is based on software reporting, never physical/game success."""
    committed: bool
    reason: str
    generation: int
    sequence: int
    evidence_basis: str = 'software-completed-step'
    physical_hold_or_release_proven: bool = False
    game_effect_proven: bool = False


class ReceiptHistoryOwner(NativeHistoryOwner):
    """Reuse the accepted owner's exclusive thread/RNG/reset/poison lifetime machinery."""
    def __init__(self, adapter, runtime):
        super().__init__(adapter, runtime)
        self._prepared = None
        self._origin = None
        self._submission = None
        self._accepted = False
        self._post_proposal_rng = None

    def propose(self, image, decision_identity, source_size=None, observation_profile=None):
        """Leave idx/state/steps unchanged while retaining private encoded prefixes and IDs."""
        self._ready()
        origin = identity(decision_identity)
        self._claim(); self._phase = 'predicting'; self._sequence += 1
        token = ProposalToken(self._identity, self._generation, self._sequence)
        try:
            self._guard(); self._take_snapshot()
            previous = self._runtime.history_identity(self._adapter)
            result, prepared = self._runtime.prepare(self._adapter, image, source_size, observation_profile)
            self._prepared = prepared  # Keep all retained tensors through any later failure.
            self._runtime.synchronize(); self._guard()
            require(self._runtime.history_identity(self._adapter) == previous, 'proposal_advanced_history')
            require(type(result) is dict and result.get('parseValid') is True, 'invalid_proposal')
            one_step(result['steps'])
            self._post_proposal_rng = self._runtime.save_rng()
            self._candidate_guard = previous
            self._origin = origin; self._submission = None; self._accepted = False
            self._pending = Proposal(token, canonical(result)); self._phase = 'pending'
            return self._pending
        except BaseException as error:
            self._poison('propose', error)

    def _pending_guard(self, token, current_identity):
        """No epoch change or unrelated numerical/RNG work may cross the pending interval."""
        self._token(token)
        self._guard()
        require(identity(current_identity) == self._origin, 'pending_identity_changed')
        require(self._runtime.history_identity(self._adapter) == self._candidate_guard,
                'pending_history_changed')
        self._runtime.verify_rng(self._post_proposal_rng)

    def submission_id(self, token):
        """Return a unique public wire ID, never the private token or retained tensors."""
        self._token(token)
        return f'{self._identity}-{token.generation}-{token.sequence}'

    def bind_submission(self, token, request, current_identity, connection):
        """Bind the exact object connection and unmodified request before any possible write."""
        self._token(token)
        try:
            self._pending_guard(token, current_identity)
            require(self._submission is None and connection is not None, 'single_submission')
            require(type(request) is dict and type(request.get('requestId')) is str
                    and 0 < len(request['requestId']) <= 128, 'submission_request_id')
            require(request['requestId'] == self.submission_id(token), 'submission_id_not_current')
            origin = json.loads(self._origin)
            require(request.get('command') == 'action' and type(request.get('version')) is int
                    and request['version'] == 1 and all(request.get(n) == origin[n]
                    and type(request.get(n)) is type(origin[n]) for n in ('sessionId', 'ownerEpoch', 'goalVersion')),
                    'submission_wire_identity')
            require(request.get('frameId') == origin['frameId'] and type(request.get('frameId')) is int
                    and request.get('modelId') == origin['modelId'], 'submission_origin')
            require(one_step(request['steps']) == one_step(self._pending.result['steps']),
                    'transformed_submission')
            self._submission = (canonical(request), connection)
        except BaseException as error:
            self._poison('bind_submission', error)

    def admission(self, token, response, current_identity, connection, payload=b''):
        """Accepted is only admission; only an exact explicit rejection can discard here."""
        self._token(token)
        try:
            self._pending_guard(token, current_identity)
            require(self._submission is not None and connection is self._submission[1], 'submission_connection')
            request = json.loads(self._submission[0])
            require(type(response) is dict and response.get('requestId') == request['requestId']
                    and response.get('type') in ('accepted', 'rejected') and payload == b'',
                    'unknown_acknowledgement')
            require(not self._accepted, 'duplicate_admission')
            if response['type'] == 'rejected':
                return self._discard(token, 'known_not_admitted')
            self._accepted = True
            return None
        except BaseException as error:
            self._poison('admission', error)

    def _finish(self, token, committed, reason):
        """Release exclusive ownership only after confirmed commit/discard completion."""
        basis = ('software-completed-step' if committed else
                 'local-not-submitted' if reason == 'local_not_submitted' else 'known-not-admitted')
        result = ReceiptSettlement(committed, reason, token.generation, token.sequence, basis)
        self._release()
        self._pending = self._snapshot = self._prepared = self._candidate_guard = None
        self._origin = self._submission = self._post_proposal_rng = None
        self._accepted = False; self._phase = 'ready'
        return result

    def _discard(self, token, reason):
        """Restore original RNG and predecessor only when no submission was admitted."""
        self._phase = 'settling'; self._restore()
        return self._finish(token, False, reason)

    def not_submitted(self, token, current_identity):
        """Local cancellation is valid only before binding any potentially written request."""
        self._token(token)
        try:
            self._pending_guard(token, current_identity)
            require(self._submission is None, 'submission_may_have_occurred')
            return self._discard(token, 'local_not_submitted')
        except BaseException as error:
            self._poison('not_submitted', error)

    def receipt(self, token, receipt, current_identity, connection):
        """Commit only the retained IDs for the exact fully matched software-completed step."""
        self._token(token)
        try:
            self._pending_guard(token, current_identity)
            require(self._accepted and self._submission is not None
                    and connection is self._submission[1], 'receipt_without_bound_admission')
            request = json.loads(self._submission[0])
            require(type(receipt) is dict and all(receipt.get(n) == request[n]
                    and type(receipt.get(n)) is type(request[n]) for n in ('requestId', 'frameId', 'modelId')),
                    'receipt_origin_mismatch')
            require(receipt.get('status') == 'completed' and receipt.get('reason') == 'horizon_complete',
                    'incomplete_execution')
            rows = receipt.get('appliedSteps')
            require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'incomplete_step_count')
            row = rows[0]
            require(set(row) == {'index', 'startedAtMs', 'keys', 'mouseDx', 'mouseDy'}
                    and type(row['index']) is int and row['index'] == 0, 'applied_step_shape')
            require(canonical({n: row[n] for n in ('keys', 'mouseDx', 'mouseDy')}) ==
                    canonical({n: request['steps'][0][n] for n in ('keys', 'mouseDx', 'mouseDy')}),
                    'applied_step_differs')
            for value in (receipt.get('acceptedAtMs'), receipt.get('endedAtMs'), row['startedAtMs']):
                require(type(value) in (int, float) and math.isfinite(value), 'receipt_clock')
            # Raw R45 time samples are not dispatch-completion or physical hold bounds.
            self._phase = 'settling'
            idx, state = self._runtime.commit(self._adapter, self._prepared)
            self._runtime.verify_rng(self._post_proposal_rng)
            self._guard()
            require(self._runtime.history_identity(self._adapter) == self._candidate_guard,
                    'commit_changed_predecessor_owner')
            self._adapter.idx, self._adapter.state = idx, state
            self._adapter.steps_seen = self._snapshot['steps'] + 1
            self._runtime.validate_history(self._adapter)
            self._runtime.synchronize(); self._guard()
            return self._finish(token, True, 'matched_completed_receipt')
        except BaseException as error:
            self._poison('receipt', error)

    def unknown(self, token):
        """Lost acknowledgement/receipt, dropped reports or partial input is terminal."""
        self._token(token)
        self._poison('unknown_execution', FeedbackError('unknown_or_partial_execution'))

    def settle(self, token, outcome):
        """Do not inherit admission-based settlement as a bypass for this new contract."""
        self._token(token)
        raise FeedbackError('use_explicit_admission_and_receipt')
