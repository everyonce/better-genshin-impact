"""Construct actual maximum-count serialized owner/ledger states, without numerical modules."""
import hashlib
from pathlib import Path

from _step_application_owner_fixtures import Fixture
from native_history_feedback import FeedbackError
import step_application_protocol as p


def construct(output):
    """Exercise 32 actual publications and the two-bundle boundary; publish exclusive fixture bytes."""
    output=Path(output);output.mkdir(parents=True,exist_ok=False);rows=[]
    def save(name,raw,cap):
        p.require(type(raw) is bytes and len(raw)<=cap,'capacity_fixture_bound')
        (output/name).write_bytes(raw)
        rows.append(dict(name=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),cap=cap))
    for pending in (False,True):
        f=Fixture(wide=True)
        for index in range(32):
            if index:f.out.acknowledge(f.intake._ack)
            f.identity['frameId']=p.MAX_INT-32+index
            f.runtime.keys=['W','A','LBUTTON','RBUTTON','MBUTTON','RSHIFT'] if index%2==0 else ['S','D','E','Q','R','F']
            f.propose()
            if pending and index==30:f.dispatch(f.response(terminal=False))
            elif pending and index==31:f.dispatch(f.response(terminal=False))
            else:f.dispatch()
        prefix='pending' if pending else 'published'
        save(prefix+'-owner.json',f.owner.metadata(),65536)
        save(prefix+'-coordinator.json',f.coordinator.metadata(),65536)
        save(prefix+'-dispositions.json',f.intake.disposition_metadata(),16384)
        save(prefix+'-ledger.json',f.intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        p.require(len(f.intake.ledger._proposals)==32 and len(f.intake.ledger._records)==32,'full_cardinality')
        p.require(f.runtime.commits==(31 if pending else 32),'actual_commit_count')
        if pending:
            p.require(f.owner._unresolved is not None and f.owner._prepared is not None and f.owner._leased,
                      'two_retained_operations')
    failed=Fixture();failed.propose()
    class MaximumError(Exception):
        """A worst-escaping failure payload exercises actual bounded error serialization."""
    def fail(*args):raise MaximumError('\x01'*512)
    failed.intake.ledger.complete_native_ticket=fail
    try:failed.dispatch()
    except FeedbackError:pass
    else:raise AssertionError('expected_finalization_failure')
    save('failed-owner.json',failed.owner.metadata(),65536)
    save('failed-coordinator.json',failed.coordinator.metadata(),65536)
    summary=dict(schema='native-application-owner-capacity-v1',fixtures=rows,
        actualMaximumAttemptCount=32,actualMaximumApplicationCount=32,actualMaximumTerminalCount=32,
        unresolvedPlusPendingFixture=True,actualNumericalModulesImported=False,
        limits=dict(attempts=32,recordsPerReply=4,terminalsPerReply=4,applicationBytes=8192,
            terminalBytes=4096,bindingBytes=3072,wireRequestBytes=65536,combinedReplyBytes=4*1024*1024,
            ownerMetadataBytes=65536,coordinatorMetadataBytes=65536,dispositionMetadataBytes=16384,
            ledgerSnapshotBytes=512*1024),
        selectedCanonicalPayloadBounds=dict(ledgerApplications=32*8192,ledgerTerminals=32*4096,
            ledgerBindings=32*3072,configurationCopies=2*4096,transportPendingWire=65536,
            coordinatorPendingWire=65536,originalSubmissionCopies=2*16384,proposal=16384,
            modelContractCopies=2*512,privateOrigin=16384,coordinatorDecision=2048,
            ownerScope=2048,bridgeHello=2048,trackedState=512,totalBytes=704000),
        limitations=['Serialized byte caps and actual maximum-count fixtures do not bound Python object overhead.',
            'The immutable request/binding grammar caps remain enforced; no claim that every independent field maximum fits simultaneously.',
            'The original eager model, retained tensor owners, generator snapshots and transient decoded input buffers need later numerical memory qualification.',
            'The selected canonical payload sum excludes inherited runtime metadata/guards, Python objects, exception tracebacks, and transient exports; it is not a process-memory ceiling.',
            'Two retained operations use existing references; this candidate adds no tensor clone, reencoding, sampling or decoding.'])
    values=summary['selectedCanonicalPayloadBounds'];p.require(sum(v for k,v in values.items() if k!='totalBytes')==values['totalBytes'],'retained_sum')
    save('capacity.json',p.canonical(summary,65536),65536)
    return summary
