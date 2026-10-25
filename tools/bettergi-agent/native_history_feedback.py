"""Isolated native-history transactions; no factory, CLI, bridge or live-input entry."""
from dataclasses import dataclass
from enum import Enum
import copy
import json
import threading
import uuid

GRAPH_FIELDS=('graph','static_frame','static_idx','static_state','static_uniform','graph_result')
_MISSING=object()


class FeedbackError(RuntimeError):
    """A protocol/admission error does not settle any other proposal."""


class OwnerPoisoned(FeedbackError):
    """Uncertain work is terminal for this owner, never a successful rollback."""


class Outcome(Enum):
    """Only an independently joined bridge receipt may eventually classify these outcomes."""
    ACCEPTED_ADMISSION='accepted_admission'
    KNOWN_NOT_ADMITTED='known_not_admitted'
    UNKNOWN='unknown'


@dataclass(frozen=True,eq=False)
class ProposalToken:
    """Exact object identity plus owner/generation/sequence; Boolean settlement is unsupported."""
    owner: str
    generation: int
    sequence: int


@dataclass(frozen=True)
class Proposal:
    """Detached finite JSON prevents caller edits from rewriting the pending proposal."""
    token: ProposalToken
    action_json: str

    @property
    def result(self):
        """Each caller gets an independent CPU-only dictionary."""
        return json.loads(self.action_json)


@dataclass(frozen=True)
class Settlement:
    """Admission bookkeeping, never a claim of completed physical execution."""
    owner: str
    generation: int
    sequence: int
    committed: bool
    physical_input_acknowledged: bool=False


def require(value,message):
    """Reject before publishing or mutating a different transaction."""
    if not value:raise FeedbackError(message)


class NativeHistoryOwner:
    """One owner thread and one outstanding token around an unchanged OpenP2PAdapter.

    The runtime owns cooperative CPU/CUDA generator exclusion. A future real worker
    must also exclude uncooperative users of those process-global generators.
    """
    def __init__(self,adapter,runtime):
        self._thread=threading.current_thread();self._identity=uuid.uuid4().hex
        self._adapter=adapter;self._runtime=runtime
        self._generation=0;self._sequence=0;self._phase='ready'
        self._pending=None;self._snapshot=None;self._leased=False;self._failure=None;self._candidate_guard=None
        runtime.qualify(adapter)
        self._model_guard=runtime.guard(adapter)

    @property
    def status(self):
        """Metadata only; never expose mutable tensor/backup objects."""
        return dict(owner=self._identity,generation=self._generation,phase=self._phase,
            pending=self._pending.token.sequence if self._pending else None,
            failure=copy.deepcopy(self._failure),inputAuthority=False)

    def _thread_check(self):
        require(threading.current_thread() is self._thread,'owner_thread')

    def _ready(self):
        self._thread_check();require(self._phase=='ready','owner_not_ready:'+self._phase)

    def _claim(self):
        self._runtime.claim(self._identity);self._leased=True

    def _release(self):
        self._runtime.release(self._identity);self._leased=False

    def _guard(self):
        require(self._runtime.guard(self._adapter)==self._model_guard,'model_or_context_changed')

    def _poison(self,stage,error):
        """Retain uncertain graph/backup objects and generator lease until worker retirement."""
        self._phase='poisoned';self._generation+=1
        self._failure=dict(stage=stage,type=type(error).__name__,message=str(error)[:512],
            restorationConfirmed=False,resourcesRetained=True)
        raise OwnerPoisoned(stage+':'+type(error).__name__) from error

    def _take_snapshot(self):
        """Eager uses old references; existing graph saves every externally reachable I/O tensor."""
        a=self._adapter;r=self._runtime
        s=dict(idx=a.idx,state=a.state,steps=a.steps_seen,
            fields={k:getattr(a,k,_MISSING) for k in GRAPH_FIELDS},metadata_ref=a.metadata,
            metadata=copy.deepcopy(a.metadata),graph_identity=None,copies=[],rng=None)
        self._snapshot=s  # Partial backups remain owned if clone/synchronize fails.
        r.validate_history(a)
        if a.graph is not None:
            s['graph_identity']=r.graph_identity(a)
            tensors=r.graph_tensors(a)
            require(sum(r.nbytes(t) for t in tensors)<=48*1024*1024,'graph_backup_capacity')
            for tensor in tensors:s['copies'].append((tensor,r.layout(tensor),r.clone(tensor)))
        s['rng']=r.save_rng()
        r.synchronize()  # Backups finish before the numerical call; this is feedback overhead.
        return s

    def propose(self,image,source_size=None,observation_profile=None):
        """Delegate exactly once in the ordinary caller context; no dormant setup or extra forward."""
        self._ready();self._claim();self._phase='predicting';self._sequence+=1
        token=ProposalToken(self._identity,self._generation,self._sequence)
        try:
            self._guard();s=self._take_snapshot()
            result=self._adapter.predict(image,source_size,observation_profile=observation_profile)
            self._runtime.synchronize();self._guard()
            self._runtime.validate_history(self._adapter)
            require(self._adapter.steps_seen==s['steps']+1,'proposal_step_progress')
            if s['graph_identity'] is not None:
                require(self._runtime.graph_identity(self._adapter)==s['graph_identity'],'captured_storage_changed')
            require(type(result) is dict and result.get('parseValid') is True,'invalid_returned_proposal')
            payload=json.dumps(result,separators=(',',':'),allow_nan=False)
            require(len(payload.encode())<=16384,'proposal_payload_capacity')
            self._candidate_guard=self._runtime.history_identity(self._adapter)
            self._pending=Proposal(token,payload);self._phase='pending'
            return self._pending
        except BaseException as error:self._poison('propose',error)

    def _token(self,token):
        self._thread_check();require(self._phase=='pending','owner_not_pending:'+self._phase)
        require(type(token) is ProposalToken and self._pending is not None
            and token is self._pending.token and token.owner==self._identity
            and token.generation==self._generation,'pending_token_mismatch')

    def _restore(self):
        """Restore the same old storage or the exact eager references, then confirm completion."""
        a=self._adapter;r=self._runtime;s=self._snapshot
        if s['graph_identity'] is not None:
            require(r.graph_identity(a)==s['graph_identity'],'captured_storage_changed')
            for tensor,layout,saved in s['copies']:
                require(r.layout(tensor)==layout,'restore_layout_changed');r.copy(tensor,saved)
        else:
            # A first-full proposal may have created a graph. Complete work before
            # dropping its owner fields; those owners are not retained as dormant.
            r.synchronize()
        for key,value in s['fields'].items():
            if value is _MISSING:
                if hasattr(a,key):delattr(a,key)
            else:setattr(a,key,value)
        a.idx=s['idx'];a.state=s['state'];a.steps_seen=s['steps']
        require(a.metadata is s['metadata_ref'],'metadata_owner_changed')
        a.metadata.clear();a.metadata.update(copy.deepcopy(s['metadata']))
        r.restore_rng(s['rng']);r.synchronize()
        if s['graph_identity'] is not None:
            require(r.graph_identity(a)==s['graph_identity'],'restored_storage_changed')
        r.verify_rng(s['rng']);self._guard()

    def settle(self,token,outcome):
        """Exact pending-token settlement; unknown/partial execution is terminal, not rejection."""
        self._token(token);require(type(outcome) is Outcome,'explicit_outcome_required')
        if outcome is Outcome.UNKNOWN:self._poison('unknown_outcome',FeedbackError('unknown_or_partial_execution'))
        self._phase='settling'
        try:
            self._guard()
            require(self._runtime.history_identity(self._adapter)==self._candidate_guard,'pending_history_owner_changed')
            if self._snapshot['graph_identity'] is not None:
                require(self._runtime.graph_identity(self._adapter)==self._snapshot['graph_identity'],'captured_storage_changed')
            if outcome is Outcome.KNOWN_NOT_ADMITTED:self._restore()
            else:self._runtime.synchronize()
            result=Settlement(token.owner,token.generation,token.sequence,outcome is Outcome.ACCEPTED_ADMISSION)
            self._release();self._pending=None;self._snapshot=None;self._candidate_guard=None;self._phase='ready'
            return result
        except BaseException as error:self._poison('settle',error)

    def _reset(self,operation):
        """Healthy reset requires no pending proposal; stale settlement cannot affect the new generation."""
        self._ready();self._claim();self._phase='resetting';self._generation+=1
        try:
            self._guard();self._runtime.synchronize();operation()
            # Native reset leaves stale graph fields in the original adapter.
            # Retire them only after successful completion, without retaining a dormant owner.
            self._runtime.synchronize()
            for name in GRAPH_FIELDS:
                if name=='graph':self._adapter.graph=None
                elif hasattr(self._adapter,name):delattr(self._adapter,name)
            self._adapter.metadata['graphCaptureValidated']=False
            self._runtime.validate_history(self._adapter)
            require(self._adapter.steps_seen==0,'reset_steps');self._guard()
            self._snapshot=None;self._release();self._phase='ready'
        except BaseException as error:self._poison('reset',error)

    def reset(self):
        """Reset without reseeding; resolve/reject a pending proposal first, or quarantine it."""
        self._reset(self._adapter.reset)

    def set_goal(self,path):
        """Use the original validated goal loader/reset; bridge release remains a separate prerequisite."""
        self._reset(lambda:self._adapter.set_goal(path))

    def close(self):
        """Healthy closure only; poisoned owners require external worker retirement."""
        self._ready();self._claim();self._phase='closing'
        try:
            self._guard();self._runtime.synchronize();self._release();self._phase='closed'
        except BaseException as error:self._poison('close',error)
