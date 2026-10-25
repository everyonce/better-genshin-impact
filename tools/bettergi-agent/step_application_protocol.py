"""Detached proposed v1 software-application records; no transport or input operations.

This first-stage protocol is not implemented by R45 or by the telemetry candidate.
Authenticated negotiation, real post-call instrumentation and a numerical owner
remain external prerequisites. No field proves physical input or a game effect.
"""
import hashlib
import json
import math
import sys

VERSION=1
MODE='native-single-50ms-v1'
RECORD_BYTES=8192
OUTBOX_RECORDS=32
BATCH_RECORDS=4
REPLY_BYTES=256*1024
MAX_CALLS=19  # Twelve old keys up, six native keys down, one mouse call.
MAX_INT=2**63-1
LIMITS=dict(recordBytes=RECORD_BYTES,retainedRecords=OUTBOX_RECORDS,batchRecords=BATCH_RECORDS,
    channelAttempts=32,headerBytes=4*1024*1024)
IDENTITY_TEXT=('sessionId','ownerEpoch','sourceEpoch','modelId')
IDENTITY_INT=('goalVersion','controlEpoch','policyGoalVersion','readinessEpoch','frameId')
BUTTONS={'LBUTTON','RBUTTON','MBUTTON'}
ALLOWED=set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')|set('0123456789')|{f'F{i}' for i in range(1,13)}|{
    'SPACE','SHIFT','LSHIFT','RSHIFT','CONTROL','LCONTROL','ESC','ESCAPE','TAB',
    'LBUTTON','RBUTTON','MBUTTON','UP','DOWN','LEFT','RIGHT'}


class ProtocolError(ValueError):
    """A malformed or uncertain authority boundary cannot authorize dependent work."""


def require(value,label):
    """Reject uncertainty explicitly rather than normalizing malformed wire values."""
    if not value:raise ProtocolError(label)


def canonical(value,limit=REPLY_BYTES):
    """Detach JSON bytes with exact scalar types and a finite publication bound."""
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    require(len(raw)<=limit,'json_capacity')
    return raw


def decode(raw,limit=REPLY_BYTES):
    """Accept only bytes; reject duplicate fields, nonfinite numbers and excess input."""
    require(type(raw) is bytes and len(raw)<=limit,'wire_bytes')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'duplicate_field');result[key]=value
        return result
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:require(False,'nonfinite'))
    canonical(value,limit)
    return value


def fields(value,names):
    """Exact schemas prevent silent typed or versioned reinterpretation."""
    require(type(value) is dict and set(value)==set(names),'fields')


def integer(value,minimum=0,maximum=MAX_INT):
    """Booleans and oversized counters are not valid integer identities."""
    require(type(value) is int and minimum<=value<=maximum,'integer')


def text(value,maximum=128):
    """Bound identifiers by UTF-8 bytes, with no embedded control characters."""
    require(type(value) is str and 0<len(value.encode('utf8'))<=maximum
            and all(ord(c)>=32 and ord(c)!=127 for c in value),'text')


def digest(value):
    """Require an explicit lower-case SHA256 value, never an arbitrary label."""
    require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'digest')


def keys(value,maximum=12,*,policy=True):
    """Unique exact key lists preserve configured and reserved-key policy without reordering."""
    require(type(value) is list and len(value)<=maximum and all(type(k) is str and k in ALLOWED for k in value),'keys')
    require(len(value)==len(set(value)),'duplicate_key')
    require(not policy or not(set(value)&{'CONTROL','LCONTROL'} and set(value)&{'ESC','ESCAPE'}),'reserved_hotkey')


def configuration(value):
    """Describe exact authenticated session/channel/backend/QPC identity; default is disabled."""
    fields(value,('version','mode','sessionId','ownerEpoch','channelId','backendId','backendEpoch',
        'buildSha256','clockKind','sessionOriginTicks','clockFrequency','allowedKeys'))
    require(type(value['version']) is int and value['version']==VERSION and value['mode']==MODE,'version_mode')
    for name in ('sessionId','ownerEpoch','channelId','backendId','backendEpoch'):text(value[name])
    digest(value['buildSha256']);require(value['clockKind']=='windows_qpc','clock_kind')
    integer(value['sessionOriginTicks'],1);integer(value['clockFrequency'],1,10**12)
    keys(value['allowedKeys'],len(ALLOWED),policy=False)
    return canonical(value,4096)


def identity(value):
    """Match the actual nine-field client decision identity, including string ownerEpoch."""
    fields(value,(*IDENTITY_TEXT,*IDENTITY_INT))
    for name in IDENTITY_TEXT:text(value[name])
    for name in IDENTITY_INT:integer(value[name])


def step(value):
    """Initial mode only admits one untransformed native 50 ms interval."""
    fields(value,('durationMs','keys','mouseDx','mouseDy'))
    require(type(value['durationMs']) is int and value['durationMs']==50,'native_duration')
    keys(value['keys'],6)
    for name in ('mouseDx','mouseDy'):integer(value[name],-65535,65535)


def make_binding(decision,request,proposal_steps,model_contract):
    """Bind exact submitted bytes and decoded proposal; raw native tokens stay private."""
    identity(decision);fields(model_contract,('checkpointSha256','profile','mapping'))
    digest(model_contract['checkpointSha256']);text(model_contract['profile'])
    require(model_contract['mapping']=='native-raw-to-one-step-v1','mapping')
    require(type(request) is dict and request.get('command')=='action'
        and type(request.get('version')) is int and request['version']==1,'request')
    for name in ('sessionId','ownerEpoch','goalVersion','frameId','modelId'):
        require(type(request.get(name)) is type(decision[name]) and request[name]==decision[name],'request_identity')
    text(request.get('requestId'))
    require(type(proposal_steps) is list and len(proposal_steps)==1,'one_step')
    step(proposal_steps[0]);require(canonical(request.get('steps'))==canonical(proposal_steps),'transformed_submission')
    raw=canonical(request,16384)
    result=dict(identity=decision,requestId=request['requestId'],submissionSha256=hashlib.sha256(raw).hexdigest(),
        model=model_contract,intervalCount=1,stepIndex=0,step=proposal_steps[0])
    return canonical(result,3072)


def binding(value,config):
    """Validate detached receipt binding against this exact negotiated lease."""
    fields(value,('identity','requestId','submissionSha256','model','intervalCount','stepIndex','step'))
    identity(value['identity']);text(value['requestId']);digest(value['submissionSha256']);step(value['step'])
    require(type(value['intervalCount']) is int and value['intervalCount']==1
        and type(value['stepIndex']) is int and value['stepIndex']==0,'single_interval')
    fields(value['model'],('checkpointSha256','profile','mapping'));digest(value['model']['checkpointSha256'])
    text(value['model']['profile']);require(value['model']['mapping']=='native-raw-to-one-step-v1','mapping')
    require(all(value['identity'][k]==config[k] for k in ('sessionId','ownerEpoch')),'binding_lease')
    require(set(value['step']['keys'])<=set(config['allowedKeys']),'negotiated_keys')
    canonical(value,3072)


def tracked(value):
    """State is complete software bookkeeping, never a physical-key measurement."""
    fields(value,('keys','generation','complete'))
    keys(value['keys']);integer(value['generation']);require(type(value['complete']) is bool,'tracked_complete')


def validate_record(value,config):
    """Recompute complete call coverage including valid no-op and inherited-key evaluation."""
    fields(value,('version','sequence','channelId','backendEpoch','binding','clock',
        'dispatchStartedTicks','heldReturnedTicks','callsReturnedTicks','publicationTicks',
        'trackedBefore','trackedAfter','backendBefore','backendAfter','heldEvaluation','calls','outcome','evidenceComplete','executionUncertain'))
    require(type(value['version']) is int and value['version']==VERSION,'record_version')
    integer(value['sequence'],1);require(value['channelId']==config['channelId']
        and value['backendEpoch']==config['backendEpoch'],'record_channel')
    binding(value['binding'],config)
    expected_clock={k:config[k] for k in ('clockKind','sessionOriginTicks','clockFrequency')}
    require(canonical(value['clock'])==canonical(expected_clock),'record_clock')
    start=value['dispatchStartedTicks'];published=value['publicationTicks']
    integer(start,config['sessionOriginTicks']);integer(published,start)
    held=value['heldReturnedTicks'];returned=value['callsReturnedTicks']
    for t in (held,returned):
        if t is not None:integer(t,start,published)
    require(held is None or returned is None or held<=returned,'record_time_order')
    times=[start,held,returned,published]
    tracked(value['trackedBefore']);tracked(value['trackedAfter'])
    text(value['backendBefore']);text(value['backendAfter'])
    require(value['heldEvaluation'] in ('returned','failed','unknown'),'held_evaluation')
    require(value['outcome'] in ('complete_returned','partial_failed','unknown'),'outcome')
    require(type(value['evidenceComplete']) is bool and type(value['executionUncertain']) is bool,'evidence_flags')
    calls=value['calls'];require(type(calls) is list and len(calls)<=MAX_CALLS,'call_count')
    seen=set();previous=times[0];transitions=[];mouse=[];add_seen=False
    for row in calls:
        fields(row,('callId','operation','key','mouseDx','mouseDy','startedTicks','finishedTicks','stage'))
        integer(row['callId'],1);require(row['callId'] not in seen,'duplicate_call');seen.add(row['callId'])
        integer(row['startedTicks'],previous);integer(row['finishedTicks'],row['startedTicks'],published);previous=row['finishedTicks']
        require(row['stage'] in ('returned','failed','unknown'),'call_stage')
        op=row['operation'];require(op in ('keyUp','buttonUp','keyDown','buttonDown','mouseMove'),'call_operation')
        if op=='mouseMove':
            require(row['key'] is None and held is not None and row['startedTicks']>=held,'mouse_boundary')
            for k in ('mouseDx','mouseDy'):integer(row[k],-65535,65535)
            mouse.append((row['mouseDx'],row['mouseDy']))
        else:
            require(not mouse and (held is None or row['finishedTicks']<=held),'held_boundary')
            keys([row['key']],1);require(type(row['mouseDx']) is int and type(row['mouseDy']) is int
                and row['mouseDx']==row['mouseDy']==0,'key_delta')
            down=op.endswith('Down');require(down or not add_seen,'transition_order');add_seen=add_seen or down
            require(op.startswith('button')==(row['key'] in BUTTONS),'key_backend_operation')
            transitions.append((down,row['key']))
    if value['outcome']=='complete_returned':
        require(held is not None and returned is not None and previous<=returned
            and value['evidenceComplete'] and not value['executionUncertain'] and value['heldEvaluation']=='returned'
            and value['backendBefore']==value['backendAfter']==config['backendEpoch']
            and all(row['stage']=='returned' for row in calls),'incomplete_authority')
        before=value['trackedBefore'];after=value['trackedAfter'];desired=value['binding']['step']
        require(before['complete'] and after['complete'] and after['generation']==before['generation']+1,'tracked_provenance')
        require(after['keys']==desired['keys'],'tracked_desired')
        expected={(False,k) for k in set(before['keys'])-set(desired['keys'])}|{(True,k) for k in set(desired['keys'])-set(before['keys'])}
        require(len(transitions)==len(expected) and set(transitions)==expected,'transition_coverage')
        delta=(desired['mouseDx'],desired['mouseDy'])
        require(mouse==([] if delta==(0,0) else [delta]),'mouse_coverage')
    else:
        require(not value['evidenceComplete'] and value['executionUncertain'],'uncertain_authority')
        require(returned is None,'uncertain_return_time')
    require((value['heldEvaluation']=='returned')==(held is not None),'held_return_time')
    return canonical(value,RECORD_BYTES)


def reservation_byte_bound(bound,config,before,sequence):
    """Conservative exact-grammar byte witness, checked before dispatch can be authorized.

    Some combinations are intentionally impossible (key call with mouse deltas).
    Every variable serialized field is at least as wide as any admitted record.
    Observed backend strings can be 128 UTF-8 bytes; JSON escaping is at most 3x
    under text()'s no-controls rule. Repeating U+0080 realizes that upper width.
    """
    biggest_keys=sorted(ALLOWED,key=lambda k:(-len(k),k))[:12]
    row=dict(version=VERSION,sequence=sequence,channelId=config['channelId'],backendEpoch=config['backendEpoch'],
        binding=bound,clock={k:config[k] for k in ('clockKind','sessionOriginTicks','clockFrequency')},
        dispatchStartedTicks=MAX_INT,heldReturnedTicks=MAX_INT,callsReturnedTicks=MAX_INT,publicationTicks=MAX_INT,
        trackedBefore=before,trackedAfter=dict(keys=biggest_keys,generation=MAX_INT,complete=False),
        backendBefore='\u0080'*64,backendAfter='\u0080'*64,heldEvaluation='returned',
        calls=[dict(callId=MAX_INT,operation='buttonDown',key='LCONTROL',mouseDx=-65535,mouseDy=-65535,
            startedTicks=MAX_INT,finishedTicks=MAX_INT,stage='returned') for _ in range(MAX_CALLS)],
        outcome='complete_returned',evidenceComplete=False,executionUncertain=False)
    return len(canonical(row,65536))


def validate_terminal(value,config):
    """A proposed explicit link is separate from the unchanged legacy terminal fields."""
    fields(value,('version','channelId','binding','applicationSequences','status','reason',
        'publicationTicks','legacyEndedAtMs','releaseOutcome'))
    require(type(value['version']) is int and value['version']==VERSION and value['channelId']==config['channelId'],'terminal_version')
    binding(value['binding'],config)
    seq=value['applicationSequences'];require(type(seq) is list and len(seq)<=1,'terminal_links')
    for item in seq:integer(item,1)
    require(value['status'] in ('completed','cancelled','replaced','unknown'),'terminal_status');text(value['reason'],64)
    integer(value['publicationTicks'],config['sessionOriginTicks'])
    require(type(value['legacyEndedAtMs']) in (int,float) and math.isfinite(value['legacyEndedAtMs']),'legacy_time')
    require(value['releaseOutcome'] in ('returned_unverified','not_requested','unknown'),'release_outcome')
    return canonical(value,4096)


def for_configuration(value):
    """Choose only a fully validated explicit channel version; never infer from reply contents."""
    if type(value) is dict and type(value.get('version')) is int and value['version'] == 2:
        import step_application_protocol_v2 as queued
        queued.configuration(value)
        return queued
    configuration(value)
    return sys.modules[__name__]


def host_observation_after(record,host,delay_ms=60):
    """Use actual same-domain acquisition ticks; receipt age and WGC units are not substitutes."""
    fields(host,('clockKind','sessionOriginTicks','clockFrequency','startedTicks','completedTicks'))
    require(all(type(host[k]) is type(record['clock'][k]) and host[k]==record['clock'][k]
        for k in record['clock']),'host_clock')
    require(type(delay_ms) is int and 30<=delay_ms<=60,'observation_delay')
    integer(host['startedTicks'],host['sessionOriginTicks']);integer(host['completedTicks'],host['startedTicks'])
    wait=(host['clockFrequency']*delay_ms+999)//1000
    require(host['startedTicks']>=record['callsReturnedTicks']+wait,'pre_input_pixels')
    return True
