"""Run a bounded, explicitly admitted fixed courtyard sequence; no reset or replay."""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
import courtyard_evidence as evidence
from courtyard_evidence import require, pin, read, verify_pin, HOST_POLICY, SEED, RETURN, FORWARD

HERE = Path(__file__).resolve().parent
WORKER_SECONDS = 270
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 48
MAX_TOTAL_BYTES = 8 * 1024 * 1024

def publish(batch, path, value):
    """Exclusive, flushed publication precedes dispatch and stays globally bounded."""
    batch, path = Path(batch).resolve(), Path(path).resolve()
    require(path.is_relative_to(batch) and not path.exists(), 'Output escapes batch or already exists.')
    payload = (json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    require(len(payload) <= MAX_FILE_BYTES, 'Output JSON exceeds its byte bound.')
    files = [p for p in batch.rglob('*') if p.is_file()]
    require(len(files) < MAX_FILES and sum(p.stat().st_size for p in files) + len(payload) <= MAX_TOTAL_BYTES,
            'Batch output bound reached; stop without another call.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())


def error_record(error):
    """Retain bounded error text while the exact returned status has its own file."""
    text = str(error)
    return dict(type=type(error).__name__, message=text[:4096], messageTruncated=len(text) > 4096)


def require_link(status, previous, *, timing_contract='v4'):
    """Join the immediate full predecessor without loading recursive ancestry."""
    owner, prior = status['navigationBaseline'], previous['navigationBaseline']
    require(timing_contract in ('v4', 'v5') and owner.get('timingContract') == prior.get('timingContract') == timing_contract,
            'Cross-version continuation is forbidden.')
    result, prior_result = owner['result'], prior['result']
    link = result.get('continuation') or {}
    require(link.get('predecessorRunId') == prior['runId']
            and link.get('predecessorProfileId') == prior['profileId']
            and link.get('predecessorEvidence') == prior_result['evidence']
            and link.get('predecessorFinalSource') == dict(kind=HOST_POLICY, hostSnapshot=prior_result['samples'][-1]['hostSnapshot']),
            'Returned leg does not retain the immediate predecessor proof.')
    if prior_result.get('continuation') is not None:
        old = prior_result['continuation']
        require(link.get('runtimeIdentity') == old.get('runtimeIdentity')
                and link.get('gameStartedAtUtcTicks') == old.get('gameStartedAtUtcTicks')
                and link.get('childAssemblySha256') == old.get('childAssemblySha256'),
                'Runtime/game/build changed between courtyard legs.')


def run_legs(batch, plan, binding, previous, rc, support, checks, *, clock=time.monotonic_ns, started_at=None):
    """One worker loop; each next leg requires the prior clean client terminal and envelope."""
    timing_contract = plan.get('timingContract', 'v4')
    require(timing_contract in ('v4', 'v5'), 'Unknown sequence timing selection.')
    require(previous['navigationBaseline'].get('timingContract') == timing_contract, 'Predecessor timing differs.')
    if timing_contract == 'v5':
        require(binding.get('timingContract') == 'v5', 'Explicit v5 sequence binding required.')
    started = clock() if started_at is None else started_at
    deadline = started + int(plan['admissionSeconds'] * 1_000_000_000)
    rows = []; stop = 'leg_limit'; failure = None; active = None
    original_mutate = rc.mutate

    def guarded_mutate(command, child, **fields):
        """Keep the original mutation unchanged behind a final one-shot cutoff/identity gate."""
        require(active is not None and active['calls'] == 0, 'Unexpected or repeated mutation.')
        expected = dict(timingContract=timing_contract,capturePolicy='task_owned_timer',routeProfile=active['profileId'],
                        continuationFromRunId=active['predecessorRunId'])
        require(command == 'startNavigationBaseline' and fields == expected, 'Unexpected mutation/selector.')
        support.require_child(child,binding); support.require_policy(child,HOST_POLICY)
        at = clock(); require(at < deadline, 'Admission cutoff reached before mutation delegation.')
        publish(batch,active['folder']/'dispatch.json',dict(command=command,fields=fields,
            mutationPublicationBoundaryAtMonotonicNs=at,admissionDeadlineMonotonicNs=deadline,physicalInputAcknowledged=False))
        delegated_at = clock()
        require(delegated_at < deadline, 'Admission cutoff reached during dispatch publication.')
        active['calls'] += 1; active['dispatchAtMonotonicNs'] = delegated_at
        return original_mutate(command,child,**fields)

    rc.mutate = guarded_mutate
    try:
        for item in plan['legs']:
            if clock() >= deadline:
                stop = 'admission_cutoff'; break
            folder = Path(batch)/'legs'/item['name']; folder.mkdir(parents=True,exist_ok=False)
            active = dict(item,folder=folder,calls=0,predecessorRunId=previous['navigationBaseline']['runId'])
            entered = clock()
            publish(batch,folder/'admission.json',dict(**item,clientCallStartedAtMonotonicNs=entered,
                admissionDeadlineMonotonicNs=deadline,predecessorRunId=active['predecessorRunId'],resetAttempted=False))
            terminal = None; native_error = None; leg_error = None; returned = None; terminal_identity_valid = False
            try:
                require(clock() < deadline, 'Admission cutoff reached before client entry.')
                try:
                    terminal = rc.run_navigation_baseline(previous,45,timing_contract=timing_contract,capture_policy='task_owned_timer',
                        route_profile=item['profileId'],continuation_from_run_id=active['predecessorRunId'])
                except rc.NavigationBaselineError as error:
                    terminal = error.status; native_error = str(error)
                returned = clock()
                publish(batch,folder/'result.json',dict(status=terminal,error=native_error))
                support.require_child(terminal,binding); support.require_policy(terminal,HOST_POLICY)
                owner = terminal.get('navigationBaseline') or {}; result = owner.get('result') or {}
                require(owner.get('profileId') == item['profileId'],'Returned native owner profile changed.')
                terminal_identity_valid = True
                require(active['calls'] == 1 and native_error is None and owner.get('state') == 'completed'
                        and owner.get('profileId') == item['profileId'] and owner.get('evidenceComplete') is True
                        and owner.get('error') is None and result.get('verified') is True
                        and result.get('inputReleaseError','missing') is None and result.get('error','missing') is None,
                        native_error or 'No clean completed native leg.')
                envelope = checks.audit_native(terminal,profile_id=item['profileId'])
                require(envelope is not None,'Native artifact envelope missing.')
                require_link(terminal,previous,timing_contract=timing_contract)
                publish(batch,folder/'artifact-audit.json',envelope)
            except Exception as error:
                leg_error = error_record(error); failure = leg_error; stop = 'failed_or_unknown'
                if not (folder/'result.json').exists():
                    publish(batch,folder/'result.json',dict(status=terminal,error=leg_error,returnedStatusKnown=terminal is not None))
            row = dict(schema='r45-validation-summary-v1',action='courtyard-'+item['direction'],name=item['name'],
                child=binding['child'],bindingSha256=binding['_bindingPin']['sha256'],
                success=leg_error is None,error=leg_error,cleanupError=None,resetAttempted=False,inputRequested=True,
                executionKind='bounded-courtyard-batch-v1',supervisorPackage=plan['package'],
                predecessorRunId=active['predecessorRunId'],predecessorProfileId=previous['navigationBaseline']['profileId'],
                clientCallStartedAtMonotonicNs=entered,mutationCallStartedAtMonotonicNs=active.get('dispatchAtMonotonicNs'),
                terminalReturnedAtMonotonicNs=returned,mutationCalls=active['calls'],
                nativeTerminalObserved=terminal_identity_valid and active['calls'] == 1
                    and re.fullmatch('[0-9a-f]{32}',(terminal.get('navigationBaseline') or {}).get('runId','')) is not None
                    and (terminal.get('navigationBaseline') or {}).get('runId') != active['predecessorRunId']
                    and (terminal.get('navigationBaseline') or {}).get('state') in ('completed','failed','cancelled')
                    and terminal.get('taskRunning') is False,
                cleanupBasis='Returned native client terminal only; root/game postflight is batch-level.',
                fullRouteAuditPending=True,continuousGameplayProven=False,physicalInputAcknowledged=False,
                renderFreshnessMeasured=False,trainingEligible=False)
            if (folder/'result.json').exists():row['nativeResult']=pin(folder/'result.json')
            publish(batch,folder/'summary.json',row); rows.append(row)
            if leg_error is not None:break
            previous = terminal
    finally:
        rc.mutate = original_mutate
    return dict(schema='r45-courtyard-worker-result-v1',startedAtMonotonicNs=started,
        admissionDeadlineMonotonicNs=deadline,endedAtMonotonicNs=clock(),stopReason=stop,error=failure,
        legs=rows,nativeOwnerRetirementKnown=bool(rows) and rows[-1]['nativeTerminalObserved'],
        fullRouteAuditsPending=True,automaticReplay=False,continuousGameplayProven=False)


def plan_names(first_index, max_legs, direction='return'):
    """Derive only alternating fixed corridor legs with fresh local output names."""
    require(type(first_index) is int and 1 <= first_index <= 99, 'Invalid local leg index.')
    require(type(max_legs) is int and 1 <= max_legs <= 4, 'Maximum legs must be 1..4.')
    require(direction in ('return','forward'), 'Unknown fixed direction.')
    first = 0 if direction == 'return' else 1
    return [dict(name=f'leg-{first_index+i:02d}-{"return" if (i+first)%2==0 else "forward"}',
                 direction='return' if (i+first)%2==0 else 'forward',
                 profileId=RETURN if (i+first)%2==0 else FORWARD) for i in range(max_legs)]


def game_identity(binding):
    """One bounded query-only CIM check at each parent boundary, never per leg."""
    game = binding['_game']; game_pid = game['ProcessId']
    require(type(game_pid) is int and game_pid > 0, 'Game PID must be a positive integer.')
    command = """$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process -Filter 'ProcessId = %d' | ForEach-Object {
 if ($null -eq $_.CreationDate) { throw 'Game creation time unavailable.' }
 [pscustomobject]@{ProcessId=$_.ProcessId;Name=$_.Name;SessionId=$_.SessionId;CreationUtc=$_.CreationDate.ToUniversalTime().ToString('o')}
} | ConvertTo-Json -Compress""" % game_pid
    value = json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
        text=True,timeout=10,creationflags=0x08000000))
    require(value == game, 'Protected game identity changed.')
    return value


def current(rc,binding,*,include_game):
    """Read exact current identity/idle state, with no input or lifecycle mutation."""
    root_pin = binding['_root']
    root = rc.exchange('status',root_pin['processId'],root_pin['windowsSessionId'])
    child = rc.refresh(binding['child'])
    evidence.require_root(root,binding); evidence.require_child(child,binding); evidence.require_policy(child,HOST_POLICY)
    value = dict(root=root,child=child)
    if include_game: value['game'] = game_identity(binding)
    return value


def latest(rc,before,saved,binding):
    """Keep both compact-owner equality and dedicated full-result equality before dispatch."""
    evidence.require_latest(before['child'],saved)
    full = rc._navigation_baseline_result(before['child'],host_continuation=True)
    evidence.require_child(full,binding); evidence.require_policy(full,HOST_POLICY)
    require(full.get('navigationBaseline') == saved['navigationBaseline'], 'Latest full predecessor changed.')
    return full


def tool_pins():
    """Bind both shipped wrapper files into the single parent-to-worker plan."""
    return [pin(HERE/name) for name in ('courtyard_sequence.py','courtyard_evidence.py')]


def worker(batch,plan_sha):
    """Admit one exclusive broker-owned worker; timeout never causes a native replay."""
    started_at = time.monotonic_ns(); batch = Path(batch).resolve()
    require(pin(batch/'worker-plan.json')['sha256'] == plan_sha, 'Worker plan changed.')
    plan = read(batch/'worker-plan.json',MAX_FILE_BYTES)
    require(plan.get('schema') == 'courtyard-sequence-plan-v1' and plan.get('toolFiles') == tool_pins()
            and plan.get('workerSeconds') == WORKER_SECONDS, 'Worker source/ownership plan differs.')
    publish(batch,batch/'worker-started.json',dict(plan=pin(batch/'worker-plan.json'),workerPid=os.getpid(),
        startedAtMonotonicNs=started_at,clock=dict(vars(time.get_clock_info('monotonic')))))
    proof_path = verify_pin(plan['predecessor'])
    binding, proof, saved, direction = evidence.prepare(proof_path,plan['predecessor']['sha256'],timing_contract=plan.get('timingContract','v4'))
    require(plan['binding'] == binding['_bindingPin'] and plan['legs'] == plan_names(1,plan['maxLegs'],direction),
            'Worker predecessor/direction/binding differs.')
    require(type(plan['admissionSeconds']) in (int,float) and math.isfinite(plan['admissionSeconds'])
            and 0 < plan['admissionSeconds'] <= 180,'Admission cutoff exceeds its bound.')
    rc = evidence.load_client(binding); before = current(rc,binding,include_game=False)
    full = latest(rc,before,saved,binding)
    publish(batch,batch/'worker-preflight.json',dict(**before,predecessorProof=proof,latestOwnerFull=full))
    checks = SimpleNamespace(audit_native=lambda status,profile_id:evidence.audit_native(status,binding,profile_id=profile_id,timing_contract=plan.get('timingContract','v4')))
    result = run_legs(batch,plan,binding,full,rc,evidence,checks,started_at=started_at)
    publish(batch,batch/'worker-result.json',result)
    return 0 if result['error'] is None else 1


def require_broker_retired(result,session):
    """A bounded worker return and native owner retirement are independent facts."""
    require(type(result.get('returnCode')) is int and type(result.get('timedOut')) is bool
            and result.get('windowsSessionId') == session and result.get('remoteDesktop') is True
            and result.get('outputIncomplete') is False and result.get('stdoutTruncated') is False
            and result.get('stderrTruncated') is False, 'Broker output/worker retirement is uncertain.')


def broker_diagnostics(result):
    """Project bounded broker facts even when a later worker-result check fails."""
    if type(result) is not dict:
        return None
    value = {key: result.get(key) if type(result.get(key)) is bool else None
             for key in ('success','timedOut','remoteDesktop','outputIncomplete','stdoutTruncated','stderrTruncated')}
    for key in ('returnCode','windowsSessionId'):
        item = result.get(key)
        value[key] = item if type(item) is int and -(2**31) <= item < 2**31 else None
    return value


def worker_error_diagnostics(value):
    """Accept only the worker's existing bounded error record; never echo arbitrary JSON."""
    if value is None:
        return None
    require(type(value) is dict and type(value.get('type')) is str and 0 < len(value['type']) <= 128
            and type(value.get('message')) is str and len(value['message']) <= 4096
            and type(value.get('messageTruncated')) is bool, 'Malformed worker error record.')
    return {key:value[key] for key in ('type','message','messageTruncated')}


def worker_diagnostics(batch, plan, binding):
    """Read one bounded saved worker summary; terminal fields are reports, not OS retirement proof."""
    path = batch/'worker-result.json'
    result = read(path,MAX_FILE_BYTES)
    require(type(result) is dict and 'error' in result and result.get('schema') == 'r45-courtyard-worker-result-v1'
            and result.get('stopReason') in ('leg_limit','admission_cutoff','failed_or_unknown')
            and type(result.get('nativeOwnerRetirementKnown')) is bool
            and result.get('automaticReplay') is False, 'Malformed worker result.')
    legs = result.get('legs')
    require(type(legs) is list and 0 <= len(legs) <= len(plan['legs']) <= 4, 'Worker leg count differs.')
    projected = []
    for row, expected in zip(legs,plan['legs']):
        require(type(row) is dict and 'error' in row and row.get('name') == expected['name']
                and row.get('action') == 'courtyard-'+expected['direction']
                and row.get('child') == binding['child'] and row.get('bindingSha256') == binding['_bindingPin']['sha256']
                and row.get('supervisorPackage') == plan['package']
                and type(row.get('success')) is bool and type(row.get('nativeTerminalObserved')) is bool
                and type(row.get('mutationCalls')) is int and row['mutationCalls'] in (0,1),
                'Worker leg identity or reported outcome differs.')
        native = row.get('nativeResult')
        if native is not None:
            expected_path = (batch/'legs'/expected['name']/'result.json').resolve()
            require(type(native) is dict and set(native) == {'path','bytes','sha256'}
                    and type(native['path']) is str and len(native['path']) <= 4096
                    and Path(native['path']).is_absolute() and Path(native['path']).resolve() == expected_path
                    and type(native['bytes']) is int and 0 <= native['bytes'] <= MAX_FILE_BYTES
                    and type(native['sha256']) is str and re.fullmatch('[0-9a-f]{64}',native['sha256']),
                    'Malformed reported native-result pin.')
            native = {key:native[key] for key in ('path','bytes','sha256')}
        projected.append(dict(name=row['name'],action=row['action'],success=row['success'],
            error=worker_error_diagnostics(row.get('error')),mutationCalls=row['mutationCalls'],
            nativeTerminalReported=row['nativeTerminalObserved'],reportedNativeResult=native))
    require(result['nativeOwnerRetirementKnown'] == bool(projected and projected[-1]['nativeTerminalReported'])
            and all(not row['nativeTerminalReported'] or row['mutationCalls'] == 1 for row in projected),
            'Worker terminal report is inconsistent.')
    error = worker_error_diagnostics(result['error'])
    require(all(row['success'] == (row['error'] is None)
                and (not row['success'] or row['nativeTerminalReported']) for row in projected)
            and all(row['success'] for row in projected[:-1]), 'Worker leg success is inconsistent.')
    require(error == (projected[-1]['error'] if projected else None)
            and ((result['stopReason'] == 'failed_or_unknown') == (error is not None)),
            'Worker stop reason or final error is inconsistent.')
    require((result['stopReason'] != 'leg_limit' or len(projected) == len(plan['legs']))
            and (result['stopReason'] != 'admission_cutoff' or len(projected) < len(plan['legs'])),
            'Worker stop reason or leg count is inconsistent.')
    return dict(resultFile=pin(path),stopReason=result['stopReason'],
        error=error,attemptedLegCount=len(projected),
        successfulLegCount=sum(row['success'] for row in projected),
        nativeOwnerRetirementReported=result['nativeOwnerRetirementKnown'],
        lastLeg=projected[-1] if projected else None)


def execute(args,binding,proof,saved,plan):
    """One owned worker and batch-only pre/postflight; this function never resets or retries."""
    batch = args.output_dir.resolve(); batch.mkdir(parents=True,exist_ok=False)
    publish(batch,batch/'worker-plan.json',plan)
    rc = evidence.load_client(binding); failure=None;cleanup=None;broker=None
    diagnostics = dict(broker=None,worker=None,workerReadError=None)
    try:
        before = current(rc,binding,include_game=True); latest(rc,before,saved,binding)
        publish(batch,batch/'preflight.json',dict(**before,predecessorProof=proof))
        executable = Path(sys.executable).resolve()
        argv = [str(executable),'-B','-X','utf8',str(HERE/'courtyard_sequence.py'),
                '--worker',str(batch),'--plan-sha256',pin(batch/'worker-plan.json')['sha256']]
        broker = rc.run_command(before['root'],argv,str(HERE),str(executable),WORKER_SECONDS,str(batch/'broker'),32768)
        diagnostics['broker'] = broker_diagnostics(broker)
        publish(batch,batch/'broker-result.json',broker); require_broker_retired(broker,binding['child']['windowsSessionId'])
        # A timed-out or uncertain broker never authorizes interpretation of a possibly partial worker file.
        if broker['timedOut'] is False:
            try: diagnostics['worker'] = worker_diagnostics(batch,plan,binding)
            except Exception as error: diagnostics['workerReadError'] = error_record(error)
        worker = diagnostics['worker']
        detail = worker['error']['message'] if worker is not None and worker['error'] is not None else 'No verified worker error.'
        require(broker.get('success') is True and broker['returnCode'] == 0 and broker['timedOut'] is False,
                'Worker timed out; native terminal is unknown; no replay.' if broker['timedOut'] else
                f"Worker reported failure (returnCode={broker['returnCode']}): {detail} No replay.")
        require(worker is not None, 'Worker result unavailable or malformed; native completion is unknown.')
        require(worker['error'] is None and worker['nativeOwnerRetirementReported'] is True,'Native completion is unknown.')
    except Exception as error:
        failure = error_record(error)
    finally:
        try: publish(batch,batch/'postflight.json',current(rc,binding,include_game=True))
        except Exception as error:
            cleanup=error_record(error)
            if not (batch/'postflight.json').exists():publish(batch,batch/'postflight.json',dict(error=cleanup))
    final=dict(schema='courtyard-sequence-outcome-v1',toolFiles=plan['toolFiles'],binding=binding['_bindingPin'],
        success=failure is None and cleanup is None,error=failure,cleanupError=cleanup,
        workerProcessReturnRecorded=type(broker) is dict and type(broker.get('returnCode')) is int,
        diagnostics=diagnostics,workerTerminalReportIsNotOsRetirement=True,
        nativeRetirementCannotBeInferredFromWorkerExit=True,fullRouteAuditsPending=True,
        continuousGameplayProven=False,inputPhysicalAcknowledgment=False,automaticReplay=False)
    publish(batch,batch/'summary.json',final);print(json.dumps(final,allow_nan=False))
    return 0 if final['success'] else 1


def main():
    """Default only verifies files and prints a bounded plan; --execute is explicit."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predecessor',type=Path);parser.add_argument('--predecessor-sha256')
    parser.add_argument('--output-dir',type=Path);parser.add_argument('--max-legs',type=int,default=4)
    parser.add_argument('--seconds',type=float,default=180);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--worker',type=Path);parser.add_argument('--plan-sha256')
    parser.add_argument('--timing-contract',choices=('v4','v5'),default='v4')
    args=parser.parse_args()
    if args.worker:
        require(not args.execute and args.plan_sha256 is not None, 'Worker requires one exact parent plan.')
        return worker(args.worker,args.plan_sha256)
    require(args.predecessor is not None and args.predecessor_sha256 is not None and args.output_dir is not None,
            'Provide the accepted predecessor/hash and a fresh output directory.')
    require(not args.output_dir.exists(), 'Output directory already exists; no replay.')
    require(math.isfinite(args.seconds) and 0 < args.seconds <= 180,'Admission window must be at most 180 seconds.')
    binding,proof,saved,direction=evidence.prepare(args.predecessor,args.predecessor_sha256,timing_contract=args.timing_contract)
    plan=dict(schema='courtyard-sequence-plan-v1',toolFiles=tool_pins(),package=pin(__file__),binding=binding['_bindingPin'],
        predecessor=pin(args.predecessor),legs=plan_names(1,args.max_legs,direction),maxLegs=args.max_legs,
        admissionSeconds=args.seconds,workerSeconds=WORKER_SECONDS,timingContract=args.timing_contract,fullRouteAuditsAreRetrospective=True)
    if not args.execute:
        print(json.dumps(dict(preparedOnly=True,**plan),allow_nan=False));return 0
    return execute(args,binding,proof,saved,plan)


if __name__ == '__main__':
    raise SystemExit(main())
