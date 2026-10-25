"""Finite fake transport and detached producer records; no real pipe or controller."""
import ast
import io
import json
from pathlib import Path
import re
import struct
import threading
import types
import step_application_protocol as p
from step_application_ledger import Outbox
from step_application_transport import StepApplicationIntake

HERE=Path(__file__).resolve().parent


def configuration():
    """Use the actual string lease types and the v1 canonical-key backend restriction."""
    return dict(version=1,mode=p.MODE,sessionId='session',ownerEpoch='owner',channelId='channel',backendId='win32-sendinput',
        backendEpoch='backend',buildSha256='a'*64,clockKind='windows_qpc',sessionOriginTicks=1000,clockFrequency=1000,
        allowedKeys=sorted(p.ALLOWED-{'SHIFT','CONTROL','ESC'}))


def transaction(*,key_list=None,delta=(0,0)):
    """Prepare one exact public request/binding and an inert channel, without submitting anything."""
    cfg=configuration();out=Outbox();before=dict(keys=[],generation=0,complete=True)
    intake=StepApplicationIntake(cfg,out.enable(cfg,before,idle=True))
    action=dict(durationMs=50,keys=['LBUTTON'] if key_list is None else key_list,mouseDx=delta[0],mouseDy=delta[1])
    decision=dict(sessionId='session',ownerEpoch='owner',sourceEpoch='source',modelId='model',goalVersion=1,
                  controlEpoch=1,policyGoalVersion=1,readinessEpoch=1,frameId=1)
    request=dict(version=1,command='action',sessionId='session',ownerEpoch='owner',goalVersion=1,requestId='request',
                 frameId=1,observedAtMs=0.0,expiresAtMs=250.0,modelId='model',steps=[action])
    token=object();model=dict(checkpointSha256='b'*64,profile='original',mapping='native-raw-to-one-step-v1')
    wire=intake.propose(request,decision,[action],model,token)
    return out,intake,wire,token


def evidence(bound, *, failed=False):
    """Explicitly observed inert call rows; failure never becomes a neutral action."""
    desired=bound['step'];calls=[];tick=1100
    for key in desired['keys']:
        calls.append(dict(callId=len(calls)+1,operation=('button' if key in p.BUTTONS else 'key')+'Down',key=key,
                          mouseDx=0,mouseDy=0,startedTicks=tick,finishedTicks=tick+1,stage='returned'));tick+=2
    held=tick
    if desired['mouseDx'] or desired['mouseDy']:
        calls.append(dict(callId=len(calls)+1,operation='mouseMove',key=None,mouseDx=desired['mouseDx'],mouseDy=desired['mouseDy'],
                          startedTicks=tick,finishedTicks=tick+1,stage='failed' if failed else 'returned'));tick+=2
    return dict(dispatchStartedTicks=1100,heldReturnedTicks=held,callsReturnedTicks=None if failed else tick,publicationTicks=tick+1,
        trackedBefore=dict(keys=[],generation=0,complete=True),trackedAfter=dict(keys=desired['keys'],generation=0 if failed else 1,complete=not failed),
        backendBefore='backend',backendAfter='backend',heldEvaluation='returned',calls=calls,
        outcome='partial_failed' if failed else 'complete_returned',evidenceComplete=not failed,executionUncertain=failed)


def response(out,wire,*,terminal=True,failed=False):
    """Publish the reviewed outbox grammar and a separate explicit terminal link."""
    bound=wire['stepApplication']['binding'];ticket=out.reserve(p.canonical(bound));raw=out.finish(ticket,evidence(bound,failed=failed));row=p.decode(raw)
    term=dict(version=1,channelId='channel',binding=p.decode(p.canonical(bound)),applicationSequences=[row['sequence']],status='completed',reason='horizon_complete',
              publicationTicks=1200,legacyEndedAtMs=50.0,releaseOutcome='returned_unverified')
    return dict(type='accepted',requestId='request',stepApplications=p.decode(out.batch()),stepApplicationTerminals=[term] if terminal else [])


class MemoryHandle:
    """Exact length-prefixed in-memory wire; records writes and allows deterministic partial failures."""
    def __init__(self,reply,*,pixels=b'',raw=None,fail_write=False):
        self.sent=bytearray();self.fail_write=fail_write
        header=raw if raw is not None else p.canonical(reply,4*1024*1024)
        self.data=io.BytesIO(struct.pack('<I',len(header))+header+pixels)

    def read(self,n):
        """Only read the supplied byte fixture."""
        return self.data.read(n)

    def write(self,data):
        """Retain a bounded fake write; optionally fail after a partial prefix."""
        if self.fail_write:
            self.sent.extend(data[:2]);raise OSError('partial_fake_write')
        self.sent.extend(data);return len(data)


def bridge(reply,intake=None,*,pixels=b'',raw=None,fail_write=False):
    """Compile the actual isolated Bridge class AST only; never execute the stream module or constructor."""
    path=HERE/'stream_client.py'
    tree=ast.parse(path.read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Bridge')
    lock=threading.Lock()
    def clock():
        assert lock.locked(),'knowledge clock sampled outside Bridge.lock'
        return 3000
    namespace=dict(json=json,re=re,struct=struct,threading=threading,time=types.SimpleNamespace(perf_counter_ns=clock))
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    instance=namespace['Bridge'].__new__(namespace['Bridge']);instance.lock=lock
    instance.handle=MemoryHandle(reply,pixels=pixels,raw=raw,fail_write=fail_write)
    instance.hello=dict(sessionId='session',ownerEpoch='owner',goalVersion=1)
    if intake is not None:instance._step_application_intake=intake
    return instance


def call(transport,wire):
    """Use the actual Bridge.request signature without duplicate envelope fields."""
    return transport.request(wire['command'],**{k:v for k,v in wire.items() if k not in {'version','command','sessionId','ownerEpoch','goalVersion'}})


def maximal_packets():
    """Add the actual new terminal and request extensions to the retained complete combined-reply witness."""
    base=HERE/'fixtures/step_application/maximum-combined-h02.json'
    combined=p.decode(base.read_bytes(),4*1024*1024)
    terms=[]
    for row in combined['stepApplications']['records']:
        terms.append(dict(version=1,channelId=row['channelId'],binding=row['binding'],applicationSequences=[row['sequence']],
            status='completed',reason='horizon_complete',publicationTicks=p.MAX_INT,legacyEndedAtMs=1.7976931348623157e308,
            releaseOutcome='returned_unverified'))
    combined['stepApplicationTerminals']=terms
    raw=p.canonical(combined,4*1024*1024)
    # Exercise all optional fields, maximum expansion UTF-8 identifiers and all four ACK IDs.
    # Binding's independent 3 KiB cap remains authoritative if not every text field fits simultaneously.
    wide='\u0080'*64; cfg=configuration();cfg.update(sessionId=wide,ownerEpoch=wide,channelId=wide)
    desired=dict(durationMs=50,keys=['LCONTROL','LBUTTON','RBUTTON','MBUTTON','LSHIFT','RSHIFT'],mouseDx=65535,mouseDy=-65535)
    original=dict(version=1,command='action',sessionId=wide,ownerEpoch=wide,goalVersion=1,requestId=wide,
        frameId=p.MAX_INT,observedAtMs=0.0,expiresAtMs=250.0,startBeforeMs=100.0,modelId=wide,steps=[desired])
    decision=dict(sessionId=wide,ownerEpoch=wide,sourceEpoch=wide,modelId=wide,goalVersion=1,controlEpoch=p.MAX_INT,
                  policyGoalVersion=p.MAX_INT,readinessEpoch=p.MAX_INT,frameId=p.MAX_INT)
    for profile_units in range(64,0,-1):
        model=dict(checkpointSha256='b'*64,profile='\u0080'*profile_units,mapping='native-raw-to-one-step-v1')
        try:bound=p.make_binding(decision,original,[desired],model);break
        except p.ProtocolError as error:
            if str(error)!='wire_bytes':raise
    else:raise AssertionError('maximum_binding_fixture')
    original_raw=p.canonical(original,16384);wire=p.decode(original_raw)
    wire['stepApplication']=dict(version=1,submissionJson=original_raw.decode('ascii'),binding=p.decode(bound,3072))
    wire['stepApplicationsAck']=dict(version=1,channelId=wide,through=32,
        terminalRequestIds=['\u0080'*63+str(i).zfill(2) for i in range(4)])
    request=p.canonical(wire,65536)
    return raw,request,dict(legacyCombinedBytes=len(base.read_bytes()),terminalLinks=4,combinedBytes=len(raw),withHeadroom=len(raw)+65536,
        headerCap=4*1024*1024,requestBytes=len(request),requestCap=65536,applicationRetentionBytes=32*8192,
        terminalRetentionBytes=32*4096,bindingRetentionBytes=32*3072,
        requestBindingBytes=len(bound),requestProfileUtf8Bytes=profile_units*2,requestIncludesStartBefore=True,
        requestGrammarUpperBoundBytes=16384+2*16384+2+3072+4096+256,
        combinedWithMaxTerminalCapsAndHeadroom=len(base.read_bytes())+4*4096+64+65536,
        notes='Concrete complete cardinality fixture; request grammar bounds original16KiB plus twice-escaped ASCII copy, binding3KiB, ACK4KiB and256B framing. Not allocator peaks.')
