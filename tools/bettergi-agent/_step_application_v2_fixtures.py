"""Detached queued-wire fixtures composing the real Bridge, ledger and eager owner.

No scheduler or input implementation is supplied. Software facts below are
explicit test data; they never claim physical input or actual model execution.
"""
import io
import struct
from types import SimpleNamespace

import step_application_protocol as p
import step_application_protocol_v2 as v2
from _step_application_owner_fixtures import Runtime, Value
from step_application_test_fixtures import configuration, bridge
from step_application_transport import StepApplicationIntake
from step_application_history_owner import StepApplicationHistoryOwner
from step_application_native_binding import StepApplicationNativeBinding


def configuration_v2():
    """Keep the existing real wire-shaped lease and explicitly negotiate the new channel."""
    value = configuration()
    value.update(version=2, mode=v2.MODE)
    return value


def confirmation(config):
    """An exact inert enable reply has no production install or authentication effect."""
    return p.canonical(dict(configuration=config, initialTracked=dict(keys=[],generation=0,complete=True), limits=p.LIMITS))


class QueuedFixture:
    """One actual owner/coordinator with fake operands and length-prefixed in-memory replies."""
    def __init__(self, *, wide=False):
        """Reuse the original deterministic fake RNG/runtime, without numerical imports."""
        self.runtime = Runtime()
        self.adapter = SimpleNamespace(idx=Value(0), state=[Value(0) for _ in range(20)], steps_seen=0,
            graph=None, use_cuda_graph=False, metadata={}, observation_profile='p2p-native-hamming-192-v1',
            mouse_sampling='truncated_normal')
        config = configuration_v2()
        if wide:
            config.update(sessionId='\u0080'*64, ownerEpoch='\u0081'*64, channelId='\u0082'*64)
        self.intake = StepApplicationIntake(config, confirmation(config))
        self.bridge = bridge({}, self.intake)
        self.bridge.hello.update(sessionId=config['sessionId'], ownerEpoch=config['ownerEpoch'])
        self.owner = StepApplicationHistoryOwner(self.adapter, self.runtime, inert=True)
        self.model = dict(checkpointSha256='b'*64, profile=self.adapter.observation_profile, mapping='native-raw-to-one-step-v1')
        self.coordinator = StepApplicationNativeBinding(self.owner, self.bridge, self.intake, self.model,
                                                       inert=True, clock_ns=lambda:1000)
        self.identity = dict(sessionId='session', ownerEpoch='owner', sourceEpoch='source', modelId='model',
                            goalVersion=1, controlEpoch=1, policyGoalVersion=1, readinessEpoch=1, frameId=1)
        if wide:
            self.identity.update(sessionId=config['sessionId'], ownerEpoch=config['ownerEpoch'],
                sourceEpoch='source'*21, modelId='model'*25, controlEpoch=p.MAX_INT,
                policyGoalVersion=p.MAX_INT, readinessEpoch=p.MAX_INT)
        self.requests = {}; self.wires = {}; self.admissions = {}; self.rows = []
        self.proposal = self.request = self.wire = None
        self.tracked = dict(keys=[], generation=0, complete=True)

    def propose(self, *, observed=0.0, start_before=None, expires=None):
        """Retain original proposal steps and exact current predecessor before any fake write."""
        self.proposal = self.coordinator.propose(object(), self.identity, cutoff_client_ns=3000)
        request_id = self.owner.submission_id(self.proposal.token)
        self.request = dict(version=1, command='action', sessionId=self.identity['sessionId'],
            ownerEpoch=self.identity['ownerEpoch'], goalVersion=1, requestId=request_id,
            frameId=self.identity['frameId'], observedAtMs=observed, startBeforeMs=observed+100 if start_before is None else start_before,
            expiresAtMs=observed+150 if expires is None else expires, modelId=self.identity['modelId'], steps=self.proposal.result['steps'],
            queueAfter=self.intake.ledger.proposal_link())
        self.wire = self.coordinator.bind(self.proposal.token, self.request)
        self.requests[request_id] = p.decode(p.canonical(self.request))
        self.wires[request_id] = p.decode(p.canonical(self.wire))
        return self.proposal

    def schedule(self, *, admitted=10.0):
        """Construct explicit accepted schedule facts, preserving the predecessor's fixed end."""
        previous = self.request['queueAfter']
        start = admitted if previous is None else self.admissions[previous['requestId']]['scheduledEndMs']
        value = dict(version=2, channelId=self.intake.config['channelId'], requestId=self.request['requestId'],
            state='active' if previous is None else 'queued', queueAfter=previous,
            admittedAtMs=admitted, scheduledStartMs=start, scheduledEndMs=start+50)
        self.admissions[self.request['requestId']] = p.decode(p.canonical(value))
        return value

    def application(self):
        """Retain one complete returned-call/no-op record; never call an input backend."""
        bound = self.wire['stepApplication']['binding']; desired = bound['step']
        schedule = self.admissions[bound['requestId']]
        start = 1000 + int(schedule['scheduledStartMs']); tick = start; calls = []
        for suffix, keys in [('Up', sorted(set(self.tracked['keys'])-set(desired['keys']))),
                             ('Down', sorted(set(desired['keys'])-set(self.tracked['keys'])))]:
            for key in keys:
                calls.append(dict(callId=len(calls)+1, operation=('button' if key in p.BUTTONS else 'key')+suffix,
                    key=key, mouseDx=0, mouseDy=0, startedTicks=tick, finishedTicks=tick+1, stage='returned'))
                tick += 2
        held = tick
        if desired['mouseDx'] or desired['mouseDy']:
            calls.append(dict(callId=len(calls)+1, operation='mouseMove', key=None,
                mouseDx=desired['mouseDx'], mouseDy=desired['mouseDy'], startedTicks=tick, finishedTicks=tick+1, stage='returned'))
            tick += 2
        after = dict(keys=list(desired['keys']), generation=self.tracked['generation']+1, complete=True)
        row = dict(version=2, sequence=len(self.rows)+1, channelId=self.intake.config['channelId'],
            backendEpoch='backend', binding=bound,
            clock={name:self.intake.config[name] for name in ('clockKind','sessionOriginTicks','clockFrequency')},
            dispatchStartedTicks=start, heldReturnedTicks=held, callsReturnedTicks=tick, publicationTicks=tick+1,
            trackedBefore=self.tracked, trackedAfter=after, backendBefore='backend', backendAfter='backend',
            heldEvaluation='returned', calls=calls, outcome='complete_returned', evidenceComplete=True, executionUncertain=False)
        self.rows.append(p.decode(v2.validate_record(row, self.intake.config)))
        self.tracked = p.decode(p.canonical(after))
        return self.rows[-1]

    def batch(self, *, closed=False, lost=False, ack=None, unpublished=0):
        """The fake server exposes its complete first four-record window after the exact ACK."""
        ack = self.intake._ack if ack is None else ack
        return dict(version=2, channelId=self.intake.config['channelId'], acknowledgedThrough=ack,
            nextReservedSequence=len(self.rows)+1+unpublished, authorityLost=lost, unpublished=unpublished,
            records=[row for row in self.rows if row['sequence'] > ack][:4], closedForSubmission=closed)

    def handoff(self, predecessor, successor):
        """P terminal refers to Q software return before Q history publication exists."""
        schedule = self.admissions[successor['binding']['requestId']]
        return dict(version=2, channelId=self.intake.config['channelId'], binding=predecessor['binding'],
            applicationSequences=[predecessor['sequence']], status='completed', reason='horizon_handoff',
            publicationTicks=successor['publicationTicks']+1,
            legacyEndedAtMs=schedule['scheduledStartMs']+3.0, releaseOutcome='not_requested',
            transition=dict(successor=v2.application_link(successor), boundaryMs=schedule['scheduledStartMs'],
                successorScheduledEndMs=schedule['scheduledEndMs'], dispatchCheckedAtMs=schedule['scheduledStartMs'],
                successorCallsReturnedTicks=successor['callsReturnedTicks']))

    def terminal(self, row=None):
        """Ordinary final release stays explicitly unverified and closes further submissions."""
        row = self.rows[-1] if row is None else row
        end = self.admissions[row['binding']['requestId']]['scheduledEndMs']
        return dict(version=2, channelId=self.intake.config['channelId'], binding=row['binding'],
            applicationSequences=[row['sequence']], status='completed', reason='horizon_complete',
            publicationTicks=1000+int(end), legacyEndedAtMs=end, releaseOutcome='returned_unverified', transition=None)

    def reply(self, value):
        """Supply bounded fake pipe bytes; Bridge owns the actual prepare/intake serialization."""
        raw = p.canonical(value, 4*1024*1024)
        self.bridge.handle.data = io.BytesIO(struct.pack('<I', len(raw))+raw)

    def legacy(self, terminal):
        """A co-present legacy row describes the same software step, not game effect."""
        bound = terminal['binding']; schedule = self.admissions[bound['requestId']]
        step = bound['step']
        return dict(requestId=bound['requestId'], modelId=bound['identity']['modelId'], frameId=bound['identity']['frameId'],
            status=terminal['status'], reason=terminal['reason'], acceptedAtMs=schedule['admittedAtMs'],
            endedAtMs=terminal['legacyEndedAtMs'], appliedSteps=[dict(index=0,
                startedAtMs=schedule['scheduledStartMs'], keys=step['keys'], mouseDx=step['mouseDx'], mouseDy=step['mouseDy'])])

    def dispatch(self, *, applied=False, admitted=10.0, mutate=None):
        """Return an accepted schedule and optional test record through the actual coordinator."""
        schedule = self.schedule(admitted=admitted)
        if applied:
            self.application()
        response = dict(type='accepted', requestId=self.request['requestId'], stepApplicationAdmission=schedule,
                        stepApplications=self.batch(), stepApplicationTerminals=[])
        if mutate:
            mutate(response)
        self.reply(response)
        return self.coordinator.dispatch(self.proposal.token, current_server_ms=admitted)

    def status(self, *, terms=(), closed=False, mutate=None):
        """No native callback occurs until the actual serialized Bridge reply returns."""
        response = dict(type='status', stepApplications=self.batch(closed=closed), stepApplicationTerminals=list(terms))
        if mutate:
            mutate(response)
        self.reply(response)
        self.bridge.request('status')
        return self.coordinator.ingest_returned(current_identity=self.identity)

    def published_p_pending_q(self):
        """Reach the exact no-cycle boundary with two proposals and only one native commit."""
        self.propose(); self.dispatch(applied=True)
        self.identity['frameId'] += 1
        self.propose(observed=20.0); self.dispatch(admitted=30.0)
        return self.rows[0]
