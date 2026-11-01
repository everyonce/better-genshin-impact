"""One input-disabled native inventory observation immediately before combat prewarm."""
import json
import copy
import os
from pathlib import Path
import re
import time
import uuid

from combat_pause_proof import CORE_REVISIONS, inventory_visible, revision


def probe_inventory(preparation, folder, lifecycle, watch, control):
    """Own one passive pilot, one observe request and owner-bound cleanup; never send keys."""
    import combat_trial as trial
    folder = Path(folder)
    out = folder / 'loading-pause-probe'
    out.mkdir(exist_ok=False)
    owner = preparation['owner']
    root, child = trial.require_idle(lifecycle, owner)
    app = trial.local_path(child['appDirectory'], root=trial.ROOT / 'artifacts')
    pilot, group_path = app / 'User/JsScript/ActOnePilot', app / 'User/ScriptGroup/ActOneRun.json'
    request_path = pilot / 'request.json'
    trial.require(not group_path.exists() and not request_path.exists(), 'Passive probe found an existing group or request')
    source_record = preparation['pause']
    old_group = str(Path(source_record['directory']) / 'group.json')
    group = json.loads(trial.read_bytes(source_record['retained'][old_group]))
    group['projects'][0]['jsScriptSettingsObject'] = dict(enableInput=False, autoEnterGame=False)
    for key in ('enabled', 'autoPickEnabled', 'autoSkipEnabled', 'autoRunEnabled', 'autoFightEnabled',
                'jsScriptUseEnabled', 'soloTaskUseFightEnabled', 'autoEatEnabled'):
        group['config']['pathingConfig'][key] = False
    group['config']['enableShellConfig'] = False
    sources = source_record['proof']['sourceFiles']
    source_dir = out / 'source-snapshot'
    source_dir.mkdir()
    for name, sha in sources.items():
        raw = trial.read_bytes(pilot / name)
        trial.require(trial.digest(raw) == sha, 'Passive probe native source changed: ' + name)
        (source_dir / name).write_bytes(raw)
    group_sha = trial.exclusive_json(out / 'group.json', group)
    plan = dict(version=1, kind='combat-loading-inventory-probe-v1', runId=preparation['runId'],
        preparationSha256=trial.digest(trial.read_bytes(folder / 'preparation.json')),
        owner=owner, allowedPilotOperations=['observe'], maximumObservationRequests=1,
        inputEnabled=False, modelLoaded=False, autoEnterGame=False, walkingAllowed=False, attacksAllowed=False,
        sourceFiles=sources, groupSha256=group_sha)
    trial.exclusive_json(out / 'plan.json', plan)
    report = dict(status='failed', controls=[], requests=[], observations=[], modelLoaded=False,
        inputEnabled=False, inventoryVerified=False, physicalInputDeliveryVerified=False,
        pilotStartAttempted=False, pilotStartOutcome='notAttempted')
    session = request_raw = None
    observed_start_session = None
    created_group = False
    deadline = time.monotonic() + 20
    if hasattr(watch, 'series'):
        deadline = min(deadline, watch.series.deadline_ns / 1e9)

    def state(*, supervising=True, integrity=True):
        """Keep watchdog latches and the exact original pair active during passive capture."""
        nonlocal observed_start_session
        if supervising:
            watch.check()
            trial.exact_control(control, preparation['runId'])
            trial.require(time.monotonic() < deadline, 'Passive inventory probe timed out')
        current_root, current_child = trial.owner_pair(lifecycle, owner)
        trial.require(current_child.get('agentStreamRunning') is False
            and Path(current_child.get('appDirectory', '')) == app, 'Passive probe runtime changed')
        if session is not None and current_child.get('serviceOwnsPilot') is True:
            trial.require(current_child.get('scriptSession') == session, 'Passive probe script ownership changed')
        start = report.get('startEvidence')
        candidate = current_child.get('scriptSession')
        if start and start.get('acknowledged') is True and candidate and candidate != start['priorSession']:
            trial.require(observed_start_session in (None, candidate), 'Passive startup session was replaced')
            observed_start_session = candidate
        if integrity and created_group:
            actual = json.loads(trial.read_bytes(group_path))
            trial.require(type(actual.get('index')) is int and 0 <= actual['index'] <= 100,
                          'Passive probe group index changed')
            actual['index'] = group['index']
            trial.require(actual == group, 'Passive probe group authority changed')
        # Discovery and integrity reads can block. Recheck all terminal latches
        # after them so a stale idle response cannot authorize a later start.
        if supervising:
            watch.check()
            trial.exact_control(control, preparation['runId'])
            trial.require(time.monotonic() < deadline, 'Passive inventory probe timed out')
        return current_root, current_child

    def command(name):
        """Stop through the owner-bound API only after an immediate matching session check."""
        nonlocal observed_start_session
        current_root, live = state(supervising=name != 'stopPilot', integrity=name != 'stopPilot')
        if name == 'stopPilot':
            trial.require(isinstance(session, str) and session and live.get('serviceOwnsPilot') is True
                and live.get('scriptSession') == session, 'Unknown passive pilot start cannot be stopped')
        else:
            trial.require(name == 'startPilot' and trial.idle_child(live), 'Passive pilot admission is not idle')
            report['startEvidence'] = dict(ownerBefore=copy.deepcopy(dict(root=current_root, child=live)),
                priorSession=live.get('scriptSession'), sentAtUnixNs=time.time_ns(), acknowledged=False)
            report.update(pilotStartAttempted=True, pilotStartOutcome='unresolved')
        # Native stopPilot has no expectedScriptSession parameter. The preceding
        # check is explicit evidence, not an atomic native script reservation.
        result = lifecycle.transport.exchange(dict(command=name, targetProcessId=owner['child']['processId'],
            targetWindowsSessionId=owner['child']['windowsSessionId'], targetNonce=owner['child']['instanceNonce']),
            owner['child']['processId'], owner['child']['windowsSessionId'])
        report['controls'].append(dict(command=name, receivedAtUnixNs=time.time_ns(), status=result))
        if name == 'startPilot':
            trial.require(all(result.get(key) == value for key, value in owner['child'].items())
                and result.get('serviceOwnsPilot') is True and result.get('taskRunning') is True
                and result.get('agentStreamRunning') is False and result.get('pilotState') in ('starting', 'idle'),
                'Passive start acknowledgement differs from the original owner')
            report['startEvidence'].update(acknowledged=True, acknowledgedAtUnixNs=report['controls'][-1]['receivedAtUnixNs'])
            candidate = result.get('scriptSession')
            if candidate and candidate != report['startEvidence']['priorSession']:
                observed_start_session = candidate
        trial.runtime.atomic_json(out / 'progress.json', report)
        return result

    def learn_started_session_for_cleanup():
        """Correlate startup under exclusive orchestration for cleanup, never for new work."""
        nonlocal session
        start = report.get('startEvidence') or {}
        trial.require(start.get('acknowledged') is True and len(report['controls']) == 1
            and report['controls'][0]['command'] == 'startPilot' and not report['requests']
            and isinstance(start.get('priorSession'), str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', start['priorSession'])
            and type(start.get('sentAtUnixNs')) is int and type(start.get('acknowledgedAtUnixNs')) is int
            and start['acknowledgedAtUnixNs'] >= start['sentAtUnixNs']
            and trial.idle_child(start['ownerBefore']['child']),
            'Unknown passive pilot start cannot be adopted for cleanup')
        limit = time.monotonic() + 3
        # R64 has no caller-bound start ticket. Fresh session/source continuity
        # rejects observed replacement, but is not atomic correlation against an
        # unobserved identical start by another concurrent controller.
        cleanup = dict(kind='passive-startup-cleanup-v1', cleanupOnly=True, maximumWaitSeconds=3,
            correlation='exclusive-controller-fresh-session-v1', atomicStartCorrelation=False,
            startedAtUnixNs=time.time_ns(), polls=0, confirmed=False)
        report['startupCleanup'] = cleanup
        while True:
            trial.require(time.monotonic() < limit, 'Passive startup cleanup identity timed out')
            _, live = state(supervising=False)
            cleanup['polls'] += 1
            trial.require(not request_path.exists(), 'A request appeared during passive startup cleanup')
            trial.require(live.get('serviceOwnsPilot') is True and live.get('taskRunning') is True,
                          'Passive startup ownership changed before cleanup confirmation')
            if live.get('pilotState') == 'idle':
                try:
                    raw = trial.read_bytes(pilot / 'controller-status.json', allow_empty=True)
                    heartbeat = json.loads(raw)
                except (FileNotFoundError, json.JSONDecodeError):
                    # Native heartbeat publication can be briefly incomplete.
                    # This only waits for evidence; it grants no work authority.
                    time.sleep(.05)
                    continue
                except PermissionError as error:
                    if not trial.status_sharing_failure(error, pilot / 'controller-status.json'):
                        raise
                    time.sleep(.05)
                    continue
                candidate, now_ms = heartbeat.get('session'), time.time_ns() // 1_000_000
                trial.require(isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', candidate)
                    and candidate != start['priorSession'] and candidate == live.get('scriptSession') == observed_start_session
                    and heartbeat.get('version') == 1 and heartbeat.get('state') == 'idle'
                    and heartbeat.get('processId') == owner['child']['processId']
                    and heartbeat.get('windowsSessionId') == owner['child']['windowsSessionId']
                    and heartbeat.get('remoteDesktop') is True and heartbeat.get('activeRequestId') is None
                    and heartbeat.get('error') is None and type(heartbeat.get('frameId')) is int and heartbeat['frameId'] >= 1
                    and type(heartbeat.get('heartbeatAt')) is int
                    and start['sentAtUnixNs'] // 1_000_000 <= heartbeat['heartbeatAt'] <= now_ms
                    and now_ms - heartbeat['heartbeatAt'] <= 1500
                    and live.get('heartbeatFresh') is True and type(live.get('heartbeatAtUnixMs')) is int
                    and start['sentAtUnixNs'] // 1_000_000 <= live['heartbeatAtUnixMs'] <= now_ms
                    and now_ms - live['heartbeatAtUnixMs'] <= 1500,
                    'Passive cleanup heartbeat is stale, foreign or active')
                for name, sha in sources.items():
                    trial.require(trial.digest(trial.read_bytes(pilot / name)) == sha,
                                  'Passive startup source changed before cleanup')
                trial.require(not request_path.exists(), 'A request appeared during passive startup cleanup')
                trial.require(time.monotonic() < limit, 'Passive startup cleanup identity timed out')
                cleanup.update(confirmed=True, confirmedAtUnixNs=time.time_ns(), session=candidate,
                    heartbeat=heartbeat, heartbeatSha256=trial.digest(raw), ownerAtConfirmation=copy.deepcopy(live))
                session = candidate
                report.update(scriptSession=session, pilotStartOutcome='confirmed', confirmationPhase='cleanupOnly')
                return
            trial.require(live.get('pilotState') == 'starting', 'Passive startup failed before cleanup identity')
            time.sleep(.05)

    def retain(label):
        """Retain original JSON/PNG pairs, not a re-timestamped observation summary."""
        raw = trial.read_bytes(pilot / 'observation.json')
        value = json.loads(raw)
        trial.require(value.get('session') == session and type(value.get('frameId')) is int
            and value['frameId'] > 0 and type(value.get('timestamp')) in (int, float)
            and 0 <= time.time_ns() / 1_000_000 - value['timestamp'] <= 1000, 'Passive inventory source is stale or foreign')
        source = pilot / 'observations' / session / ('frame-' + str(value['frameId']).zfill(4))
        declared = Path(value.get('screenshotPath', ''))
        declared = declared if declared.is_absolute() else pilot / declared
        trial.require(declared.absolute() == source.with_suffix('.png')
            and json.loads(trial.read_bytes(source.with_suffix('.json'))) == value, 'Passive native frame source differs')
        pixels = trial.read_bytes(source.with_suffix('.png'))
        (out / (label + '.json')).write_bytes(raw)
        (out / (label + '.png')).write_bytes(pixels)
        report['observations'].append(dict(label=label, frameId=value['frameId'], source=str(source.with_suffix('.png')),
            jsonSha256=trial.digest(raw), imageSha256=trial.digest(pixels)))
        return value

    try:
        watch.check()
        trial.exact_control(control, preparation['runId'])
        trial.exclusive_json(group_path, group)
        created_group = True
        command('startPilot')
        while True:
            _, live = state()
            if live.get('serviceOwnsPilot') is True and live.get('pilotState') == 'idle':
                heartbeat, _ = trial.document(pilot / 'controller-status.json')
                candidate = heartbeat.get('session')
                trial.require(isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', candidate)
                    and live.get('scriptSession') == candidate and heartbeat.get('processId') == owner['child']['processId']
                    and heartbeat.get('windowsSessionId') == owner['child']['windowsSessionId']
                    and heartbeat.get('state') == 'idle', 'Passive heartbeat ownership differs')
                session = candidate
                report['scriptSession'] = session
                report['pilotStartOutcome'] = 'confirmed'
                break
            trial.require(live.get('pilotState') not in ('faulted', 'failed', 'stopped'), 'Passive pilot startup failed')
            time.sleep(.05)
        before = retain('before')
        trial.require(inventory_visible(before), 'Passive probe did not start in inventory')
        state()
        trial.require(not request_path.exists(), 'Another request appeared before passive observation')
        request = dict(id='combat-pause-' + uuid.uuid4().hex, session=session, mission='observe',
            expectedFrameId=before['frameId'], createdAt=time.time_ns() // 1_000_000)
        trial.require(0 <= request['createdAt'] - before['timestamp'] <= 1000, 'Passive request source expired')
        trial.exclusive_json(out / (request['id'] + '.request.json'), request)
        temporary = request_path.with_name('.combat-pause-' + uuid.uuid4().hex + '.tmp')
        try:
            trial.exclusive_json(temporary, request)
            if os.name == 'nt':
                os.rename(temporary, request_path)
            else:
                os.link(temporary, request_path)
        finally:
            temporary.unlink(missing_ok=True)
        request_raw = trial.read_bytes(request_path)
        receipt_path = pilot / 'receipts' / session / (request['id'] + '.json')
        while True:
            state()
            trial.require(trial.read_bytes(request_path) == request_raw, 'Passive request was substituted')
            if receipt_path.exists():
                receipt, _ = trial.document(receipt_path)
                if receipt.get('status') not in ('started', 'running'):
                    (out / (request['id'] + '.receipt.json')).write_bytes(trial.read_bytes(receipt_path))
                    report['requests'].append(dict(request=request, receipt=receipt))
                    trial.require(receipt.get('id') == request['id'] and receipt.get('session') == session
                        and receipt.get('mission') == 'observe' and receipt.get('status') == 'completed',
                        'Passive observation did not complete')
                    after = retain('after')
                    events = (receipt.get('details') or {}).get('inputEvents')
                    trial.require(isinstance(events, list) and len(events) == 1
                        and events[0] == dict(type='controllerRevision', startedAt=events[0].get('startedAt'),
                            files={name: revision(trial.read_bytes(pilot / name)) for name in CORE_REVISIONS})
                        and receipt.get('frameId') == after['frameId'] and after['frameId'] > before['frameId']
                        and inventory_visible(after), 'Passive observation contained input or lost inventory')
                    report.update(status='completed', inventoryVerified=True, pauseFrameId=after['frameId'])
                    break
            time.sleep(.05)
    except BaseException as error:
        report['error'] = str(error) or type(error).__name__
    finally:
        try:
            # Source/group/request corruption must block further observation or
            # loading, but cannot suppress retirement of our confirmed session.
            _, live = state(supervising=False, integrity=False)
            if live.get('serviceOwnsPilot') is True:
                if session is None:
                    learn_started_session_for_cleanup()
                command('stopPilot')
            trial.await_idle(lifecycle, owner)
            current_root, current_child = state(supervising=False, integrity=False)
            trial.require(trial.idle_child(current_child), 'Passive probe did not retire')
            trial.exclusive_json(out / 'owner-after-stop.json', dict(root=current_root, child=current_child))
            report['ownerIdleMinimizedAfter'] = True
            if created_group:
                state(supervising=False)
                (out / 'group-after-stop.json').write_bytes(trial.read_bytes(group_path))
                group_path.unlink()
                created_group = False
                report['temporaryGroupRemoved'] = True
            if request_raw is not None:
                trial.require(trial.read_bytes(request_path) == request_raw, 'Passive request changed during cleanup')
                request_path.unlink()
                report['ownTerminalRequestRemoved'] = True
        except BaseException as error:
            report.update(status='failed', cleanupError=str(error) or type(error).__name__)
        if report['pilotStartOutcome'] == 'unresolved':
            report.update(status='failed', cleanupError=report.get('cleanupError') or 'Passive pilot start outcome remains unresolved')
        trial.exclusive_json(out / 'result.json', report)
    trial.require(report['status'] == 'completed', 'Passive inventory verification failed: ' +
                  str(report.get('error') or report.get('cleanupError')))
    # Reopen all original native bytes only after confirmed cleanup. This proof
    # grants loading authority; it never grants a combat input lease.
    record = trial.retain_ui_proof(folder, out, owner, 'verify')
    return record
