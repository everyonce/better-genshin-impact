"""Pure eager references, generator lease and real detached wire grammar for focused tests."""
import io
import json
import struct
from types import SimpleNamespace

import step_application_protocol as p
from step_application_ledger import Outbox
from step_application_transport import StepApplicationIntake
from step_application_history_owner import StepApplicationHistoryOwner
from step_application_native_binding import StepApplicationNativeBinding
from native_history_feedback import require
from step_application_test_fixtures import configuration, bridge


class Value:
    """A retained plain object is sufficient to distinguish actual owner references."""
    def __init__(self, value):
        self.value = value


class Runtime:
    """No numerical libraries; deterministic two-generator and partial-commit failure seams."""
    def __init__(self):
        self.rng = (17, 29); self.lease = None
        self.claims = self.releases = self.prepares = self.commits = self.restores = 0
        self.model_revision = 0; self.release_hook = self.commit_hook = self.sync_hook = None
        self.validate_hook = None; self.last_returned = None; self.keys = ['LBUTTON']
        self.malformed_return = False

    def qualify(self, adapter):
        require(adapter.graph is None and not adapter.use_cuda_graph, 'fixture_eager')

    def guard(self, adapter):
        return (self.model_revision, adapter.observation_profile, adapter.mouse_sampling)

    def claim(self, owner):
        self.claims += 1
        require(self.lease is None, 'non_reentrant_lease')
        self.lease = owner

    def release(self, owner):
        require(self.lease == owner, 'release_other_owner')
        self.releases += 1; self.lease = None
        if self.release_hook:self.release_hook()

    def save_rng(self):
        return self.rng

    def restore_rng(self, value):
        self.restores += 1; self.rng = value

    def verify_rng(self, value):
        require(self.rng == value, 'rng_changed')

    def history_identity(self, adapter):
        return (id(adapter.idx), id(adapter.state), tuple(id(x) for x in adapter.state),
                adapter.steps_seen, id(adapter.metadata), json.dumps(adapter.metadata, sort_keys=True))

    def validate_history(self, adapter):
        require(type(adapter.state) is list and len(adapter.state) == 20
                and adapter.idx.value == 12*adapter.steps_seen, 'fixture_history')
        if self.validate_hook:self.validate_hook()

    def synchronize(self):
        if self.sync_hook:self.sync_hook()

    def prepare(self, adapter, image, source_size, profile):
        require(self.lease is not None, 'prepare_unleased')
        self.prepares += 1; self.rng = (self.rng[0]+1, self.rng[1]+2)
        return dict(parseValid=True, steps=[dict(durationMs=50, keys=list(self.keys), mouseDx=0, mouseDy=0)]), \
            (image, adapter.idx, adapter.state, self.rng)

    def commit(self, adapter, prepared):
        require(self.lease is not None and prepared[1] is adapter.idx and prepared[2] is adapter.state,
                'commit_predecessor')
        self.commits += 1
        self.last_returned = (Value(adapter.idx.value+12), [Value(x.value+1) for x in adapter.state])
        if self.commit_hook:self.commit_hook()
        return self.last_returned[:1] if self.malformed_return else self.last_returned


class Fixture:
    """Actual Bridge.request AST, pure memory handle, actual protocol/outbox/ledger and new owner."""
    def __init__(self, *, wide=False):
        self.runtime = Runtime()
        self.adapter = SimpleNamespace(idx=Value(0), state=[Value(0) for _ in range(20)], steps_seen=0,
            graph=None, use_cuda_graph=False, metadata={}, observation_profile='p2p-native-hamming-192-v1',
            mouse_sampling='truncated_normal')
        self.out = Outbox(); config = configuration()
        if wide:
            config.update(sessionId='\u0080'*64, ownerEpoch='\u0081'*64, channelId='\u0082'*64)
        self.intake = StepApplicationIntake(config, self.out.enable(config, dict(keys=[],generation=0,complete=True), idle=True))
        self.bridge = bridge({}, self.intake)
        self.bridge.hello.update(sessionId=config['sessionId'],ownerEpoch=config['ownerEpoch'])
        self.owner = StepApplicationHistoryOwner(self.adapter, self.runtime, inert=True)
        self.model = dict(checkpointSha256='b'*64,profile=self.adapter.observation_profile,mapping='native-raw-to-one-step-v1')
        self.coordinator = StepApplicationNativeBinding(self.owner, self.bridge, self.intake, self.model,
                                                       inert=True, clock_ns=lambda:1000)
        self.identity = dict(sessionId='session',ownerEpoch='owner',sourceEpoch='source',modelId='model',goalVersion=1,
            controlEpoch=1,policyGoalVersion=1,readinessEpoch=1,frameId=1)
        if wide:
            # Binding's independent 3072-byte cap is respected, even with escaped UTF-8 identity text.
            self.identity.update(sessionId=config['sessionId'],ownerEpoch=config['ownerEpoch'],
                sourceEpoch='source'*21, modelId='model'*25, controlEpoch=p.MAX_INT,
                policyGoalVersion=p.MAX_INT,readinessEpoch=p.MAX_INT)
        self.tracked = dict(keys=[], generation=0, complete=True)
        self.proposal = self.request = self.wire = self.last_row = None

    def propose(self, *, bind=True):
        self.proposal = self.coordinator.propose(object(), self.identity, cutoff_client_ns=3000)
        self.request = dict(version=1,command='action',sessionId=self.identity['sessionId'],ownerEpoch=self.identity['ownerEpoch'],goalVersion=1,
            requestId=self.owner.submission_id(self.proposal.token),frameId=self.identity['frameId'],
            observedAtMs=0.0,startBeforeMs=100.0,expiresAtMs=150.0,modelId=self.identity['modelId'],steps=self.proposal.result['steps'])
        if bind:self.wire = self.coordinator.bind(self.proposal.token, self.request)
        return self.proposal

    def application(self):
        bound = self.wire['stepApplication']['binding']; desired = bound['step']; tick = 1100+100*self.tracked['generation']
        start = tick; calls = []
        for kind, keys in [('Up', sorted(set(self.tracked['keys'])-set(desired['keys']))),
                           ('Down', sorted(set(desired['keys'])-set(self.tracked['keys'])))]:
            for key in keys:
                calls.append(dict(callId=len(calls)+1, operation=('button' if key in p.BUTTONS else 'key')+kind,
                    key=key,mouseDx=0,mouseDy=0,startedTicks=tick,finishedTicks=tick+1,stage='returned'));tick+=2
        after = dict(keys=desired['keys'],generation=self.tracked['generation']+1,complete=True)
        evidence = dict(dispatchStartedTicks=start,heldReturnedTicks=tick,callsReturnedTicks=tick,publicationTicks=tick+1,
            trackedBefore=self.tracked,trackedAfter=after,backendBefore='backend',backendAfter='backend',heldEvaluation='returned',
            calls=calls,outcome='complete_returned',evidenceComplete=True,executionUncertain=False)
        reservation = self.out.reserve(p.canonical(bound)); self.last_row = p.decode(self.out.finish(reservation,evidence))
        self.tracked = after
        return self.last_row

    def terminal(self, row=None):
        row = self.last_row if row is None else row
        return dict(version=1,channelId=self.intake.config['channelId'],binding=row['binding'],applicationSequences=[row['sequence']],
            status='completed',reason='horizon_complete',publicationTicks=row['publicationTicks']+1,
            legacyEndedAtMs=50.0,releaseOutcome='returned_unverified')

    def response(self, *, applied=True, terminal=True, kind='accepted'):
        if applied:self.application()
        return dict(type=kind,requestId=self.request['requestId'],stepApplications=p.decode(self.out.batch()),
            stepApplicationTerminals=[self.terminal()] if applied and terminal else [])

    def reply(self, value, *, raw=None):
        body = p.canonical(value,4*1024*1024) if raw is None else raw
        self.bridge.handle.data = io.BytesIO(struct.pack('<I',len(body))+body)

    def dispatch(self, response=None):
        self.reply(self.response() if response is None else response)
        return self.coordinator.dispatch(self.proposal.token, current_server_ms=20.0)

    def status(self, *, terminals=()):
        response = dict(type='status',stepApplications=p.decode(self.out.batch()),stepApplicationTerminals=list(terminals))
        self.reply(response)
        self.bridge.request('status')
        return self.coordinator.ingest_returned(current_identity=self.identity)
