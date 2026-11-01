"""Replay a bounded combat trial without opening the game or loading a model."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from combat_trial_guard import (CombatTrialGuard, bind_review, canonical, proposal_rejection, sensor_frame, trial_policy,
                               combat_scope)
from episode_split import read_split
from native_combat import validate_capability,validate_frame
from policy_rgb_archive import (JOURNAL_NAMES, RECORDING_FORMAT, read_policy_rgb, read_recording_jsonl,
                                recording_journal_path, recording_metadata)


def require(condition, message):
    """Reject inconsistent retained evidence instead of repairing it during audit."""
    if not condition:
        raise ValueError(message)


def digest(raw):
    """Identify the exact original bytes read by this audit."""
    return hashlib.sha256(raw).hexdigest()


def bounded_file(path, maximum=16 * 1024 * 1024, *, source_sha256=None):
    """Read one explicitly named artifact with a finite memory bound."""
    path = Path(path)
    # Only the declared source inventory may contain an empty Python module.
    # Structured records and pixels keep the original nonempty contract.
    if source_sha256 is not None:
        require(path.suffix == '.py' and isinstance(source_sha256, str)
                and len(source_sha256) == 64 and all(c in '0123456789abcdef' for c in source_sha256),
                'Invalid declared Python source pin')
    allow_empty = source_sha256 == digest(b'')
    require(path.is_file() and (0 if allow_empty else 1) <= path.stat().st_size <= maximum,
            'Missing or oversized artifact: ' + str(path))
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, 'Artifact grew beyond its bound')
    require(bool(raw) or allow_empty, 'Artifact became empty while reading')
    if source_sha256 is not None:
        require(digest(raw) == source_sha256, 'Frozen combat source changed: ' + str(path))
    return raw


def local_artifact(folder, name):
    """Keep retained evidence inside its trial, refusing link or parent redirects."""
    root = Path(folder).resolve()
    candidate = root / name
    path = candidate.resolve()
    require(path.is_relative_to(root) and candidate.absolute() == path, 'Artifact redirects outside its declared location')
    return path


def json_lines(path):
    """Read bounded original journal rows, keeping their recorded order."""
    path = Path(path)
    if path.name in JOURNAL_NAMES:
        return read_recording_jsonl(path.parent,path.name,max_decoded_bytes=160*1024*1024,max_rows=10000)
    raw = bounded_file(path, 160 * 1024 * 1024)
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    require(len(rows) <= 10000 and all(isinstance(row, dict) for row in rows), 'Invalid combat journal')
    return rows, digest(raw)


def replay_events(binding, hello, events):
    """Re-execute every guard transition and compare the complete state after each event."""
    trace = [row for row in events if str(row.get('type', '')).startswith('combatTrial')]
    require(bool(trace), 'Missing combat guard events')
    started = trace[0].get('state', {}).get('startedNs')
    guard = CombatTrialGuard(binding, binding['owner'], hello, started)
    previous = started
    counts = {}
    for row in trace:
        kind, now = row['type'], row.get('clientTimeNs')
        require(type(now) is int and now >= previous, 'Combat journal clock moved backwards')
        previous = now
        if kind == 'combatTrialObservation':
            require('roundTripMs' in row, 'Combat poll lacks its original transport timing')
            replayed = guard.observe(row['frame'], now, round_trip_ms=row['roundTripMs'])
        elif kind == 'combatTrialDispatch':
            arguments = row['arguments']
            frame = row['state']['pending']['frame']
            proposed = dict(parseValid=True, steps=arguments['steps'])
            replayed = guard.prepare_action(frame, proposed, arguments['requestId'], now,
                                            owner=binding['owner'], hello=hello)
        elif kind == 'combatTrialLocalRefusal':
            replayed = guard.prepare_action(row['frame'], row['proposal'], row['requestId'], now,
                                            owner=binding['owner'], hello=hello)
        elif kind == 'combatTrialAdmission':
            replayed = guard.admission(row['response'], row['payloadBytes'], now)
        elif kind == 'combatTrialReceipt':
            replayed = guard.receipt(row['receipt'], now)
        elif kind == 'combatTrialRelease':
            replayed = guard.acknowledge_release(row['response'], row['payloadBytes'], now, row['reason'])
        elif kind == 'combatTrialStop':
            trigger = row['trigger']
            replayed = guard.fail(trigger['reason'], now,
                **{key: value for key, value in trigger.items() if key not in ('reason', 'clientTimeNs')})
        else:
            raise ValueError('Unknown combat journal event: ' + kind)
        require(canonical(replayed) == canonical(row), 'Combat event replay differs: ' + kind)
        counts[kind] = counts.get(kind, 0) + 1
    return dict(state=guard.snapshot(), counts=counts, eventCount=len(trace))


def frame_identity(row):
    """Compare immutable native pixels and HUD evidence across repeated poll envelopes."""
    evidence = dict(row.get('combatEvidence') or {})
    evidence.pop('recognitionMs', None)
    return dict(frameId=row.get('frameId'), capturedAtMs=row.get('capturedAtMs'),
                sourceFrame=row.get('sourceFrame'), sourceWidth=row.get('sourceWidth'),
                sourceHeight=row.get('sourceHeight'), combatEvidence=evidence,
                frameWorldReadiness=row.get('frameWorldReadiness'))


def verify_frozen_goal(episode):
    """Reject late raw goal requests even if a derived completion summary was cleared."""
    run_id = episode.get('residentRunId')
    require(isinstance(run_id, str) and bool(run_id)
            and episode.get('combatTrialFinalControl') == dict(version=1, runId=run_id, command='run')
            and episode.get('goalChanges') == [], 'Combat control or goal changed')
    first, last = episode.get('initialGoalState'), episode.get('finalGoalState')
    require(isinstance(first, dict) and isinstance(last, dict), 'Missing combat goal snapshots')
    for state in (first, last):
        require(state.get('policyGoalVersion') == 0 and state.get('goalIntent') == 'stationary'
                and all(state.get(key) is None for key in ('appliedGoalRequestId', 'goalRequestId', 'goalRequestStatus', 'goalError')),
                'Combat goal was requested to change')
    require(first.get('controlEpoch') == last.get('controlEpoch')
            and canonical(first.get('goalMetadata')) == canonical(last.get('goalMetadata')),
            'Combat goal identity changed through the trial')
    return first.get('goalMetadata')


def audit_episode(episode, events, frames, recording_folder, binding):
    """Join replayed authority, actual proposal records, terminal receipts and exact retained RGB."""
    recording = episode.get('recording', {})
    seal = recording_metadata(recording_folder,recording)
    if seal.get('recordingFormat') == RECORDING_FORMAT:
        require(all(row.get('recordingFormat') == RECORDING_FORMAT for row in events if row.get('type') == 'episodeStart'),
                'Combat episode recording format declaration differs')
    require(canonical(episode.get('combatTrialGuard')) == canonical(binding), 'Episode combat binding differs')
    capability=validate_capability(episode['hello'].get('combatObservation'))
    if capability['version']==2 or 'nativeCombatObservation' in episode:
        validate_capability(episode.get('nativeCombatObservation'),capability)
    replay = replay_events(binding, episode['hello'], events)
    by_frame = {}
    for index, row in enumerate(frames):
        require(type(row.get('frameId')) is int and row['frameId'] not in by_frame, 'Repeated recorded RGB frame')
        validate_frame(row,capability)
        read_policy_rgb(recording_folder,row.get('policyRgb'),index=index,frame_id=row['frameId'],recording=recording)
        require(row.get('videoFrameIndex') == index,
                'Policy RGB reference belongs to another video or native frame')
        by_frame[row['frameId']] = row
    require(bool(by_frame), 'No retained combat policy pixels')
    if seal.get('recordingFormat') == RECORDING_FORMAT:
        require(sum(row['policyRgb']['storedBytes'] for row in frames) == recording['policyRgbStoredBytes'],
                'Stored combat policy RGB byte count differs')
    observed = [row for row in events if row.get('type') == 'combatTrialObservation'
                and row.get('frame', {}).get('type') == 'frame']
    for row in frames:
        joined = [event for event in observed if event['frame'].get('frameId') == row['frameId']
                  and canonical(event['frame']) == canonical(sensor_frame(row))
                  and event['clientTimeNs'] == row.get('clientReceivedNs')
                  and event['roundTripMs'] == row.get('transportRoundTripMs')]
        require(len(joined) == 1, 'Recorded pixels lack their exact original guard intake')
    for event in observed:
        source = by_frame.get(event['frame'].get('frameId'))
        require(source is not None and canonical(frame_identity(source)) == canonical(frame_identity(event['frame'])),
                'A guard observation lacks its exact retained RGB frame')
    dispatches = [row for row in events if row.get('type') == 'combatTrialDispatch']
    accepted = [row for row in episode.get('decisions', []) if (row.get('acceptance') or {}).get('type') == 'accepted']
    admissions = [row['response'] for row in events if row.get('type') == 'combatTrialAdmission'
                  and row.get('response', {}).get('type') == 'accepted']
    receipts = episode.get('receipts', [])
    trace_receipts = [row['receipt'] for row in events if row.get('type') == 'combatTrialReceipt']
    require(canonical(receipts) == canonical(trace_receipts), 'Native receipt sequence differs from the complete guard trace')
    envelopes = episode.get('combatTrialReceiptEnvelopes', [])
    require(canonical([receipt for row in envelopes for receipt in row.get('receipts', [])]) == canonical(receipts),
            'Native receipts lack their original transport envelopes')
    releases = [{key: row[key] for key in ('response', 'payloadBytes', 'clientTimeNs', 'reason')}
                for row in events if row.get('type') == 'combatTrialRelease']
    require(canonical(episode.get('combatTrialReleases')) == canonical(releases),
            'Native release acknowledgements differ from the complete guard trace')
    require(len(dispatches) <= 3 and len(accepted) <= 3, 'Combat action bound exceeded')
    identities = set()
    for row in dispatches:
        args = row['arguments']
        require(args['requestId'] not in identities, 'Combat action request was replayed')
        identities.add(args['requestId'])
        source = by_frame.get(args['frameId'])
        require(source is not None and canonical(frame_identity(source)) == canonical(frame_identity(row['state']['pending']['frame'])),
                'Combat dispatch lacks its exact recorded source pixels')
    accepted_ids = [row['acceptance']['requestId'] for row in accepted]
    require(len(set(accepted_ids)) == len(accepted_ids)
            and accepted_ids == [row['requestId'] for row in admissions],
            'Accepted proposal and native admission identities do not form one ordered match')
    for row, admission in zip(accepted, admissions):
        request = row['acceptance']['requestId']
        matched = [event for event in dispatches if event['arguments']['requestId'] == request]
        require(len(matched) == 1 and proposal_rejection(row) is None, 'Accepted action lacks one pure model attack')
        marker = matched[0]
        require(canonical(row.get('combatTrialGuard')) == canonical(marker)
                and canonical(row['steps']) == canonical(marker['arguments']['steps'])
                and canonical(row['acceptance']) == canonical(admission)
                and row['frameId'] == marker['arguments']['frameId'], 'Accepted proposal differs from guarded dispatch or admission')
        raw = row.get('rawPolicySteps')
        require(proposal_rejection(dict(parseValid=True, steps=raw)) is None,
                'Raw policy proposal was not a pure normal attack')
        require(canonical([dict(raw[0], durationMs=100)]) == canonical(row['steps'])
                and row.get('controllerResampling') == 'explicit-bounded-key-hold; mouse applied once',
                'Controller changed more than the explicit normal-attack hold')
    terminal = replay['state']
    require(terminal['acceptedActions'] == episode.get('combatTrialGuardState', {}).get('acceptedActions'),
            'Recorded trace omits a known native admission')
    if episode.get('status') == 'completed':
        verify_frozen_goal(episode)
        require(terminal['trialComplete'] is True and terminal['phase'] == 'complete' and terminal['trip'] is None
                and terminal['acceptedActions'] == terminal['completedActions'] == len(accepted) == len(dispatches) == 3
                and terminal['pending'] is None and terminal['armed'] is False
                and canonical(terminal) == canonical(episode.get('combatTrialGuardState')),
                'Completed episode does not reproduce its full three-pulse drain')
        require(episode.get('endReason') == 'combatTrialComplete' and episode.get('acceptedInputActions') == 3
                and not any(episode.get(key) for key in ('error', 'streamError', 'stopError', 'unacknowledgedAction')),
                'Completed episode retains a control failure')
        require(canonical(receipts) == canonical([item['receipt'] for item in terminal['completed']])
                and all(row.get('droppedReceipts') == 0 for row in envelopes),
                'Completed episode contains extra or missing native receipts')
        for completed in terminal['completed']:
            require(sum(canonical(receipt) == canonical(completed['receipt']) for receipt in receipts) == 1,
                    'Completed pulse lacks its original terminal receipt')
            post = completed['postFrame']
            require(post['frameId'] in by_frame and canonical(frame_identity(post)) == canonical(frame_identity(by_frame[post['frameId']])),
                    'Completed pulse lacks exact post-release pixels')
        recording = episode.get('recording', {})
        require(recording.get('complete') is True and recording.get('lossless') is True
                and recording.get('workerRetired') is True and not recording.get('error'), 'Completed recording is incomplete')
        require(all(type(recording.get(key)) is int and recording[key] == len(frames)
                    for key in ('encodedFrames', 'policyRgbFrames', 'recordedObservations'))
                and all(type(recording.get(key)) is int and recording[key] == 0
                        for key in ('droppedFrames', 'droppedEvents', 'droppedObservations', 'abandonedFrames')),
                'Completed recording counters differ from retained evidence')
        require((episode.get('stop') or {}).get('type') == 'stopped', 'Native stop is unacknowledged')
    return dict(replay=replay, verifiedRgbFrames=len(by_frame), guardedDispatches=len(dispatches),
                acceptedProposalJoins=len(accepted), trialCompleteVerified=episode.get('status') == 'completed',
                terminalStateFullyReplayed=canonical(terminal) == canonical(episode.get('combatTrialGuardState')),
                combatSuccess=False, enemyIdentityVerified=False, damageVerified=False, killVerified=False)


def verify_python_runtime(folder, plan):
    """Rebuild new process-chain pins from archived executable/config bytes only."""
    record = plan.get('workerRuntime')
    if record is None:
        require('workerRuntime' not in plan and not (folder / 'python-runtime').exists()
            and not (folder / 'python-runtime').is_symlink(),
            'Undeclared Python runtime archive cannot select historical replay')
        return None
    from combat_process_identity import runtime_contract
    require(isinstance(record, dict) and set(record) == {'contract', 'retained'}
        and set(record['retained']) == set(record['contract']['files']), 'Archived Python runtime is incomplete')
    def reader(path):
        """Never substitute today's pyvenv.cfg or Python binary for an original process proof."""
        name = str(path)
        require(name in record['retained'], 'Runtime replay introduced an unpinned file')
        retained = local_artifact(folder, record['retained'][name])
        require(retained.is_relative_to(folder / 'python-runtime'), 'Runtime archive escaped its scope')
        raw = bounded_file(retained, 4 * 1024 * 1024)
        require(digest(raw) == record['contract']['files'][name], 'Archived Python runtime bytes changed')
        return raw
    reader.venv = record['contract'].get('kind') == 'windows-venv-redirector-v1'
    actual = runtime_contract(plan['resources'], reader)
    require(actual == record['contract'], 'Archived Python runtime descriptor changed')
    return actual


def verify_retirement(plan, wrapper, host, broker, claim, worker_claim, manifest_sha):
    """Require the one consumed worker and its ordinary RDP broker to agree on retirement."""
    run_id, owner = plan['runId'], plan['binding']['owner']
    require(host.get('runId') == run_id and host.get('planSha256') == wrapper['planSha256']
            and host.get('launchAttempts') == 1 and host.get('terminalManifestSha256') == manifest_sha
            and canonical(host.get('broker')) == canonical(broker)
            and canonical(host.get('hostClaim')) == canonical(claim) == canonical(wrapper.get('hostClaim')),
            'Host did not retire the exact consumed combat plan')
    worker = wrapper.get('worker', {})
    consumed_sha = wrapper.get('preparationSha256') if 'preparedPolicy' in plan else wrapper['planSha256']
    if 'preparedPolicy' in plan:
        require(host.get('preparationSha256') == consumed_sha == plan['preparedPolicy']['preparationSha256'],
                'Host lost the original paused preparation claim')
    require(claim.get('runId') == worker_claim.get('runId') == run_id
            and claim.get('planSha256') == worker_claim.get('planSha256') == consumed_sha
            and worker_claim.get('processId') == worker.get('processId')
            and worker_claim.get('parentProcessId') == worker.get('parentProcessId')
            and canonical(host.get('worker')) == canonical(worker), 'Consumed worker or broker identity differs')
    from combat_process_identity import verify_worker_broker
    verify_worker_broker(worker, broker, (plan.get('workerRuntime') or {}).get('contract'))
    for identity in (worker, broker):
        require(identity.get('remoteDesktop') is True and identity.get('elevated') is False
                and identity.get('integrityRid') == 8192
                and identity.get('windowsSessionId') == owner['child']['windowsSessionId'],
                'Combat process was not ordinary RDP')
    require(broker.get('timedOut') is False and broker.get('outputIncomplete') is False
            and host.get('ownerIdleMinimizedAfter') is True, 'Combat worker retirement or output is unresolved')
    if wrapper['status'] == 'completed':
        require(host.get('status') == 'completed' and broker.get('success') is True and broker.get('returnCode') == 0
                and not host.get('stopReason') and not host.get('error') and not host.get('monitorCleanupError'),
                'Completed wrapper conflicts with host supervision')


def verify_preparation_chain(folder, plan, wrapper, document):
    """Replay paused loading and the one post-resume arm independently of runtime admission."""
    names = ('preparation.json', 'prepared.json', 'RESUME-REQUESTED.json', 'RESUMED.json',
             'ARM-REQUESTED.json', 'ARM.json', 'ARM-CONSUMED.json', 'pause-evidence', 'resume-evidence',
             'loading-pause-probe', 'verify-evidence')
    probe_markers = ('inventoryProbeResult', 'inventoryProbeResultSha256', 'inventoryProbeCleanupError')
    if 'preparedPolicy' not in plan:
        require(wrapper.get('kind') == 'combat-trial-wrapper-v1'
            and not any(name in wrapper for name in ('preparationSha256', 'preparedPolicy', 'armSha256',
                'inputEnabledBeforeArm', 'modelPreparation') + probe_markers)
            and not any((folder / name).exists() for name in names), 'Historical combat run retains undeclared preparation evidence')
        return None
    from combat_pause_proof import inspect_transition
    preparation, ready, resumed, arm, consumed, resume_request, arm_request, claim, worker_claim = (document(name) for name in
        ('preparation.json', 'prepared.json', 'RESUMED.json', 'ARM.json', 'ARM-CONSUMED.json',
         'RESUME-REQUESTED.json', 'ARM-REQUESTED.json', 'CONSUMED.json', 'WORKER-CONSUMED.json'))
    shas = {name: digest(bounded_file(local_artifact(folder, name))) for name in
            ('preparation.json', 'prepared.json', 'RESUMED.json', 'ARM.json', 'plan.json')}
    run_id, worker, owner = plan['runId'], wrapper.get('worker'), plan['binding']['owner']
    verify_python_runtime(folder, plan)
    require(wrapper.get('kind') == 'combat-trial-prepared-wrapper-v1' and wrapper.get('inputEnabledBeforeArm') is False
        and combat_scope(preparation) == combat_scope(ready) == combat_scope(plan) == combat_scope(wrapper)
        and ((preparation.get('version') == 1 and preparation.get('kind') == 'combat-trial-paused-preparation-v1'
              and 'loadingPauseVerification' not in preparation)
             or (preparation.get('version') == 2 and preparation.get('kind') == 'combat-trial-paused-preparation-v2'
                 and preparation.get('loadingPauseVerification') == 'native-input-disabled-inventory-probe-v1'
                 and isinstance(preparation.get('workerRuntime'), dict)))
        and preparation.get('runId') == run_id and preparation.get('directory') == str(folder)
        and preparation.get('inputEnabled') is False and preparation.get('attacksAllowed') is False
        and 'binding' not in preparation and 'policy' not in preparation
        and preparation.get('maximumHostSeconds') == 90 and preparation.get('maximumPauseProofAgeSeconds') == 30
        and preparation.get('goalSha256') == plan['binding']['goalSha256']
        and all(canonical(preparation.get(name)) == canonical(plan.get(name)) for name in
            ('owner', 'ownerFile', 'ownerSha256', 'sourceFiles', 'modelConfiguration', 'resources', 'checkpointSha256', 'checkpointStamp', 'workerRuntime'))
        and preparation.get('owner') == owner, 'Paused preparation changed its authority, model or owner')
    require(ready.get('version') == 1 and ready.get('kind') == 'combat-prepared-policy-v1'
        and ready.get('state') == 'preparedPaused' and ready.get('inputEnabled') is False
        and ready.get('runId') == run_id and ready.get('preparationSha256') == shas['preparation.json']
        and ready.get('worker') == worker and ready.get('owner') == owner and ready.get('modelLoads') == 1
        and ready.get('goalSha256') == preparation['goalSha256']
        and ready.get('sourceFilesSha256') == digest(canonical(plan['sourceFiles']))
        and ready.get('modelConfigurationSha256') == digest(canonical(plan['modelConfiguration']))
        and ready.get('policyMetadata') == wrapper.get('policyMetadata')
        and ready.get('hostClaim') == claim == wrapper.get('hostClaim')
        and claim.get('runId') == run_id and claim.get('planSha256') == shas['preparation.json']
        and worker_claim == dict(runId=run_id, planSha256=shas['preparation.json'],
            processId=worker['processId'], parentProcessId=worker['parentProcessId']), 'Paused model readiness was substituted')
    require(all(type(value) is int and value > 0 for value in (preparation.get('createdAtUnixNs'),
        ready.get('preparedAtUnixNs'), ready.get('preparedAtClientNs'), claim.get('startedAtUnixNs'),
        claim.get('startedMonotonicNs'), claim.get('deadlineMonotonicNs')))
        and preparation['createdAtUnixNs'] <= claim['startedAtUnixNs'] <= ready['preparedAtUnixNs']
        and claim['deadlineMonotonicNs'] - claim['startedMonotonicNs'] == 90_000_000_000,
        'Paused preparation widened or restarted its host deadline')
    root = next((path.parent for path in folder.parents if path.name == 'artifacts'), None)
    require(root is not None, 'Paused preparation lost its original artifact namespace')

    def replay_ui(record, operation):
        """Use retained native PNGs and request/receipt originals, never mutable installed files."""
        require(isinstance(record, dict) and set(record) == {'directory', 'proof', 'retained'}
            and set(record['retained']) == set(record['proof']['files']), 'Incomplete archived inventory transition')
        def reader(path):
            """Keep every original dependency joined to one exact archived byte sequence."""
            name = str(path)
            require(name in record['retained'], 'Inventory proof introduced an unretained dependency')
            retained = local_artifact(folder, record['retained'][name])
            require(retained.is_relative_to(folder / (operation + '-evidence')), 'Inventory archive escaped its phase')
            raw = bounded_file(retained)
            require(digest(raw) == record['proof']['files'][name], 'Archived inventory evidence changed')
            return raw
        actual = inspect_transition(record['directory'], owner, operation, root=root, read_file=reader)
        require(canonical(actual) == canonical(record['proof']), 'Archived inventory transition no longer replays')
        return actual

    pause = replay_ui(preparation['pause'], 'pause')
    resume = replay_ui(resumed.get('resume'), 'resume')
    loading = ready.get('modelPreparation') or {}
    loading_pause = pause
    if preparation['kind'] == 'combat-trial-paused-preparation-v2':
        require('tools/bettergi-agent/combat_pause_probe.py' in preparation['sourceFiles'],
                'Passive inventory producer source was not archived')
        loading_pause = replay_ui(loading.get('inventoryProbe'), 'verify')
        probe_record = loading['inventoryProbe']
        probe_result_path = folder / 'loading-pause-probe/result.json'
        require(Path(probe_record['directory']) == probe_result_path.parent,
                'Passive inventory probe directory changed')
        original_result = bounded_file(local_artifact(folder, probe_result_path))
        archived_result = bounded_file(local_artifact(folder, probe_record['retained'][str(probe_result_path)]))
        require(original_result == archived_result and digest(original_result) == wrapper.get('inventoryProbeResultSha256')
            and json.loads(original_result) == wrapper.get('inventoryProbeResult')
            and 'inventoryProbeCleanupError' not in wrapper,
            'Terminal passive inventory result or cleanup differs from the loading proof')
        original_plan = str(Path(probe_record['directory']) / 'plan.json')
        probe_plan = json.loads(bounded_file(local_artifact(folder, probe_record['retained'][original_plan])))
        require(probe_plan.get('kind') == 'combat-loading-inventory-probe-v1'
            and probe_plan.get('runId') == run_id and probe_plan.get('preparationSha256') == shas['preparation.json']
            and loading_pause['sourceFiles'] == pause['sourceFiles']
            and loading_pause['terminalTimestampUnixMs'] * 1_000_000 >= claim['startedAtUnixNs']
            and loading_pause['cleanupAcknowledgedAtUnixNs'] <= loading.get('startedAtUnixNs', 0),
            'Passive loading proof changed its consumed preparation or cleanup ordering')
    else:
        require('inventoryProbe' not in loading and not (folder / 'loading-pause-probe').exists()
            and not (folder / 'verify-evidence').exists() and not any(key in wrapper for key in probe_markers),
            'Historical preparation retained undeclared loading probe')
    require(loading == wrapper.get('modelPreparation') and loading.get('inputEnabled') is False
        and type(loading.get('startedAtUnixNs')) is int and type(loading.get('finishedAtUnixNs')) is int
        and preparation['createdAtUnixNs'] <= loading['startedAtUnixNs'] <= loading['finishedAtUnixNs'] <= ready['preparedAtUnixNs']
        and 0 <= loading['startedAtUnixNs'] - loading_pause['terminalTimestampUnixMs'] * 1_000_000 <= 30_000_000_000
        and loading.get('modelLoadSeconds') == wrapper.get('modelLoadSeconds')
        and type(loading['modelLoadSeconds']) in (int, float) and math.isfinite(loading['modelLoadSeconds'])
        and loading['modelLoadSeconds'] >= 0 and wrapper.get('modelLoadAttempts') == wrapper.get('modelLoads') == 1,
        'Model loading lacked a recent positive pause or changed its preparation phase')
    historical_pause_age = preparation['createdAtUnixNs'] - pause['terminalTimestampUnixMs'] * 1_000_000
    require(0 <= historical_pause_age
        and (preparation['kind'] == 'combat-trial-paused-preparation-v2' or historical_pause_age <= 30_000_000_000)
        and pause['cleanupAcknowledgedAtUnixNs'] <= preparation['createdAtUnixNs']
        and resume['sourceFiles'] == pause['sourceFiles']
        and resume['transition']['requestCreatedAtUnixMs'] * 1_000_000 >= ready['preparedAtUnixNs'],
        'Inventory pause or post-ready resume timing changed')
    require(resumed.get('version') == 1 and resumed.get('kind') == 'combat-preparation-resumed-v1'
        and resumed.get('runId') == run_id and resumed.get('preparationSha256') == shas['preparation.json']
        and resumed.get('preparedSha256') == shas['prepared.json'] and resumed.get('worker') == worker
        and resumed.get('owner') == owner and resumed.get('inputEnabled') is False
        and type(resumed.get('resumedAtUnixNs')) is int and type(resumed.get('resumedAtClientNs')) is int
        and resumed['resumedAtClientNs'] > ready['preparedAtClientNs']
        and resumed['resumedAtUnixNs'] >= resume['cleanupAcknowledgedAtUnixNs']
        and 0 <= resumed['resumedAtUnixNs'] - resume['terminalTimestampUnixMs'] * 1_000_000 <= 30_000_000_000,
        'Resume marker changed worker or phase')
    link = dict(kind='paused-prepared-combat-authority-v1', preparationFile=str(folder / 'preparation.json'),
        preparationSha256=shas['preparation.json'], preparedSha256=shas['prepared.json'], resumedSha256=shas['RESUMED.json'],
        worker=worker, armRequestId=arm.get('requestId'))
    require(plan['preparedPolicy'] == wrapper.get('preparedPolicy') == link
        and wrapper.get('preparationSha256') == shas['preparation.json'] and wrapper.get('armSha256') == shas['ARM.json']
        and resume_request == dict(runId=run_id, preparedSha256=shas['prepared.json'])
        and arm_request == dict(runId=run_id, requestId=arm.get('requestId'), preparationSha256=shas['preparation.json'],
            preparedSha256=shas['prepared.json'])
        and consumed == dict(runId=run_id, armSha256=shas['ARM.json'], preparationSha256=shas['preparation.json'],
            preparedSha256=shas['prepared.json'], worker=worker), 'Prepared arm did not retain its exact one-shot claims')
    require(arm == dict(version=1, kind='combat-preparation-arm-v1', runId=run_id, requestId=link['armRequestId'],
        preparationSha256=shas['preparation.json'], preparedSha256=shas['prepared.json'], resumedSha256=shas['RESUMED.json'],
        worker=worker, planSha256=shas['plan.json'], createdAtUnixNs=arm.get('createdAtUnixNs'),
        createdAtClientNs=arm.get('createdAtClientNs')) and isinstance(link['armRequestId'], str)
        and len(link['armRequestId']) == 32 and all(character in '0123456789abcdef' for character in link['armRequestId'])
        and type(arm.get('createdAtUnixNs')) is int and type(arm.get('createdAtClientNs')) is int
        and resumed['resumedAtUnixNs'] <= arm['createdAtUnixNs'] <= wrapper['finishedAtUnixNs']
        and resumed['resumedAtClientNs'] < arm['createdAtClientNs'], 'Combat arm chronology or exact worker binding changed')
    review = json.loads(bounded_file(local_artifact(folder, plan['evidence']['review']['retained'])))
    require(type(review.get('reviewedAtUnixNs')) is int and review['reviewedAtUnixNs'] >= resumed['resumedAtUnixNs']
        and plan['binding']['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100 > resumed['resumedAtClientNs'],
        'Combat arm reused a source or review from before resume')
    return dict(preparationSha256=shas['preparation.json'], preparedSha256=shas['prepared.json'],
                resumedSha256=shas['RESUMED.json'], armSha256=shas['ARM.json'], inputEnabledBeforeArm=False)


def verify_temperatures(samples, finished_ns):
    """Check actual retained samples, including freshness at the terminal boundary."""
    require(bool(samples), 'Missing GPU supervision samples')
    stamps, temperatures = [], []
    for sample in samples:
        temperature = sample.get('temperatureC')
        require(not sample.get('error') and type(temperature) in (int, float)
                and math.isfinite(temperature) and 0 <= temperature < 78, 'GPU supervision failed or reached its stop')
        stamps.append(int(datetime.fromisoformat(sample['atUtc']).timestamp() * 1e9))
        temperatures.append(temperature)
    require(all(0 <= after - before < 6_000_000_000 for before, after in zip(stamps, stamps[1:]))
            and -6_000_000_000 < finished_ns - stamps[-1] < 6_000_000_000,
            'GPU supervision timing is incomplete')
    return max(temperatures)


def audit_trial(folder):
    """Verify a retired wrapper and its original frozen review before replaying the native episode."""
    folder = Path(folder).resolve()
    artifacts = {}

    def document(name):
        """Bind each structured artifact to the exact bytes consumed by this invocation."""
        raw = bounded_file(local_artifact(folder, name))
        artifacts[str(name)] = digest(raw)
        value = json.loads(raw)
        require(isinstance(value, dict), 'Expected a combat artifact object')
        return value

    plan, wrapper, finalization = (document(name) for name in ('plan.json', 'patrol.json', 'finalization.json'))
    require(plan.get('kind') == 'combat-trial-plan-v1' and wrapper.get('kind') in
            ('combat-trial-wrapper-v1', 'combat-trial-prepared-wrapper-v1')
            and wrapper['runId'] == plan['runId'] == finalization['runId']
            and wrapper['planSha256'] == artifacts['plan.json']
            and finalization.get('manifestSha256') == artifacts['patrol.json'], 'Combat wrapper identities differ')
    require(plan.get('maximumHostSeconds') == 90 and plan.get('recordingMaximumBytes') == 160 * 1024 * 1024
            and type(plan.get('maximumReviewAgeSeconds')) is int and 0 < plan['maximumReviewAgeSeconds'] <= 120
            and canonical(plan.get('policy')) == canonical(trial_policy(combat_scope(plan))), 'Combat plan widened its fixed bounds')
    blobs = []
    for name in ('review', 'plan', 'scene', 'sidecar', 'image', 'goal'):
        reference = plan['evidence'][name]
        raw = bounded_file(local_artifact(folder, reference['retained']))
        require(digest(raw) == reference['sha256'], 'Retained combat review bytes changed: ' + name)
        artifacts[str(reference['retained'])] = digest(raw)
        blobs.append(raw)
    binding = bind_review(*blobs)
    require(canonical(binding) == canonical(plan.get('binding'))
            and combat_scope(binding) == combat_scope(plan) == combat_scope(wrapper)
            and canonical(binding['owner']) == canonical(wrapper.get('owner')), 'Frozen combat review does not reproduce its binding')
    prepared = verify_preparation_chain(folder, plan, wrapper, document)
    verify_python_runtime(folder, plan)
    required_sources = ('combat_trial.py', 'combat_trial_guard.py', 'stream_client.py', 'native_combat.py',
                        'model_adapters.py', 'resident_runtime.py', 'episode_split.py')
    require(all('tools/bettergi-agent/' + name in plan['sourceFiles'] for name in required_sources),
            'Frozen combat source inventory is incomplete')
    for name, sha in plan['sourceFiles'].items():
        raw = bounded_file(local_artifact(folder, Path('source-snapshot') / name), source_sha256=sha)
        require(digest(raw) == sha, 'Frozen combat source changed: ' + name)
    # Replay uses the implementation that actually produced this trial. A later
    # incompatible guard must be audited from its preserved source snapshot.
    for name in ('combat_trial_guard.py', 'native_combat.py'):
        key = 'tools/bettergi-agent/' + name
        require(plan['sourceFiles'].get(key) == digest(bounded_file(Path(__file__).with_name(name))),
                'Replay implementation differs from the frozen source: ' + name)
    if prepared is not None:
        require(plan['sourceFiles'].get('tools/bettergi-agent/combat_pause_proof.py') ==
            digest(bounded_file(Path(__file__).with_name('combat_pause_proof.py'))),
            'Inventory proof replay implementation differs from the frozen source')
    if 'workerRuntime' in plan:
        require(plan['sourceFiles'].get('tools/bettergi-agent/combat_process_identity.py') ==
            digest(bounded_file(Path(__file__).with_name('combat_process_identity.py'))),
            'Python process replay implementation differs from the frozen source')
    episode = document('native-episode.json')
    require(artifacts['native-episode.json'] == wrapper.get('nativeEpisodeSha256')
            and canonical(episode) == canonical(wrapper.get('nativeEpisode')), 'Wrapper substituted its native episode')
    events, events_sha = json_lines(folder / 'recording/events.jsonl')
    frames, frames_sha = json_lines(folder / 'recording/frames.jsonl')
    for name in ('events.jsonl','frames.jsonl'):
        path = recording_journal_path(folder/'recording',name)
        artifacts[str(path.relative_to(folder)).replace('\\','/')] = digest(bounded_file(path,160*1024*1024))
    report = audit_episode(episode, events, frames, folder / 'recording', binding)
    if episode.get('recording',{}).get('recordingFormat') == RECORDING_FORMAT:
        report['decodedJournalSha256'] = {'events.jsonl':events_sha,'frames.jsonl':frames_sha}
    if prepared is not None:
        arm = document('ARM.json')
        require(episode['combatTrialGuardState']['startedNs'] > arm['createdAtClientNs'],
                'Combat lease preceded its separately bound arm')
        report['pausedPreparation'] = prepared
    split = read_split(folder, plan['runId'])
    require(split is not None and split['split'] == 'diagnostic'
            and canonical(split) == canonical(finalization.get('datasetSplit')), 'Combat trial lost its original diagnostic split')
    host, broker, claim, worker_claim = (document(name) for name in
        ('result.json', 'broker.json', 'CONSUMED.json', 'WORKER-CONSUMED.json'))
    verify_retirement(plan, wrapper, host, broker, claim, worker_claim, artifacts['patrol.json'])
    payload = 0
    for path in (folder / 'recording').iterdir():
        require(path.is_file() and path.absolute() == path.resolve(), 'Unexpected recording child or redirect')
        payload += path.stat().st_size
    require(payload == wrapper.get('recordedBytes') and wrapper.get('recordedBytesComplete') is True
            and payload <= plan['recordingMaximumBytes'], 'Combat recording accounting differs')
    report['verifiedRecordedBytes'] = payload
    if wrapper.get('status') == 'completed':
        worker = wrapper.get('worker', {})
        require(report['trialCompleteVerified'] and wrapper.get('cleanupVerified') is True
                and wrapper.get('ownerIdleMinimizedAfter') is True and wrapper.get('episodeCalls') == wrapper.get('modelLoads') == 1
                and wrapper.get('nativeStartOutcome') == 'confirmed' and worker.get('remoteDesktop') is True
                and worker.get('elevated') is False and worker.get('integrityRid') == 8192
                and worker.get('windowsSessionId') == binding['owner']['child']['windowsSessionId']
                and finalization.get('status') == 'completed', 'Completed wrapper lacks one ordinary owned trial and cleanup')
        require(wrapper.get('finalControlReadError') is None
                and wrapper.get('finalControlDocument') == dict(version=1, runId=plan['runId'], command='run')
                and canonical(wrapper.get('finalGoalState')) == canonical(episode.get('finalGoalState'))
                and wrapper.get('goalChanges') == [] and episode.get('residentRunId') == plan['runId'],
                'Wrapper retained a changed final control or goal')
        goal_metadata = {key: value for key, value in json.loads(blobs[-1]).items() if key != 'embedding'}
        goal_metadata['file'] = plan['evidence']['goal']['path']
        require(canonical(verify_frozen_goal(episode)) == canonical(goal_metadata),
                'Loaded goal metadata differs from the original reviewed instruction')
        metadata = wrapper.get('policyMetadata', {})
        preparation = metadata.get('startupGraphPreparation', {})
        require(metadata.get('precision') == 'float16' and metadata.get('historyFrames') == 41
                and metadata.get('cudaGraph') is True and metadata.get('graphCaptureValidated') is True
                and metadata.get('historyCommit') == 'accepted-proposals-only'
                and preparation.get('graphPrepared') is True and preparation.get('controllerActionsEmitted') == 0
                and preparation.get('historyFramesAfterPreparation') == 0, 'Loaded combat policy was not the measured prewarmed configuration')
        started = episode['combatTrialGuardState']['startedNs']
        reviewed = json.loads(blobs[0])['reviewedAtUnixNs']
        limit = plan['maximumReviewAgeSeconds'] * 1_000_000_000
        require(0 <= started - binding['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100 <= limit
                and 0 <= claim['startedAtUnixNs'] - reviewed + started - claim['startedMonotonicNs'] <= limit,
                'Combat review was stale when the native lease began')
        temperatures = []
        for name in ('gpu.jsonl', 'host-supervision/gpu.jsonl'):
            samples, artifacts[name] = json_lines(folder / name)
            temperatures.append(verify_temperatures(samples, wrapper['finishedAtUnixNs']))
        report['peakGpuTemperatureC'] = max(temperatures)
        observations, observations_sha = json_lines(folder / 'recording/observations.jsonl')
        path = recording_journal_path(folder/'recording','observations.jsonl')
        artifacts[str(path.relative_to(folder)).replace('\\','/')] = digest(bounded_file(path,160*1024*1024))
        if 'decodedJournalSha256' in report:
            report['decodedJournalSha256']['observations.jsonl'] = observations_sha
        require(len(observations) == len(frames), 'Original observation journal count differs from retained pixels')
    require(all(wrapper.get(key) is False for key in ('combatSuccess', 'enemyIdentityVerified', 'damageVerified', 'killVerified')),
            'Transport evidence was promoted into a combat outcome')
    report.update(status='completed', runId=plan['runId'], wrapperStatus=wrapper['status'], artifactSha256=artifacts)
    return report


def main(argv=None):
    """Write a new audit artifact without modifying any original experiment file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    report = audit_trial(args.trial)
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in ('status', 'runId', 'wrapperStatus', 'verifiedRgbFrames',
                                                'guardedDispatches', 'acceptedProposalJoins', 'trialCompleteVerified')}))


if __name__ == '__main__':
    main()
