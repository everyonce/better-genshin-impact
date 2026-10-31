"""Replay a bounded combat trial without opening the game or loading a model."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from combat_trial_guard import CombatTrialGuard, bind_review, canonical, proposal_rejection, sensor_frame, trial_policy
from episode_split import read_split
from native_combat import validate_frame
from policy_rgb_archive import verify_policy_rgb


def require(condition, message):
    """Reject inconsistent retained evidence instead of repairing it during audit."""
    if not condition:
        raise ValueError(message)


def digest(raw):
    """Identify the exact original bytes read by this audit."""
    return hashlib.sha256(raw).hexdigest()


def bounded_file(path, maximum=16 * 1024 * 1024):
    """Read one explicitly named artifact with a finite memory bound."""
    path = Path(path)
    require(path.is_file() and 0 < path.stat().st_size <= maximum, 'Missing or oversized artifact: ' + str(path))
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, 'Artifact grew beyond its bound')
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
    require(canonical(episode.get('combatTrialGuard')) == canonical(binding), 'Episode combat binding differs')
    replay = replay_events(binding, episode['hello'], events)
    by_frame = {}
    for index, row in enumerate(frames):
        require(type(row.get('frameId')) is int and row['frameId'] not in by_frame, 'Repeated recorded RGB frame')
        validate_frame(row)
        verify_policy_rgb(recording_folder, row.get('policyRgb'))
        require(row.get('videoFrameIndex') == index
                and row['policyRgb']['file'] == f"policy-{index:08d}-frame-{row['frameId']:012d}.rgb",
                'Policy RGB reference belongs to another video or native frame')
        by_frame[row['frameId']] = row
    require(bool(by_frame), 'No retained combat policy pixels')
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


def verify_retirement(plan, wrapper, host, broker, claim, worker_claim, manifest_sha):
    """Require the one consumed worker and its ordinary RDP broker to agree on retirement."""
    run_id, owner = plan['runId'], plan['binding']['owner']
    require(host.get('runId') == run_id and host.get('planSha256') == wrapper['planSha256']
            and host.get('launchAttempts') == 1 and host.get('terminalManifestSha256') == manifest_sha
            and canonical(host.get('broker')) == canonical(broker)
            and canonical(host.get('hostClaim')) == canonical(claim) == canonical(wrapper.get('hostClaim')),
            'Host did not retire the exact consumed combat plan')
    worker = wrapper.get('worker', {})
    require(claim.get('runId') == worker_claim.get('runId') == run_id
            and claim.get('planSha256') == worker_claim.get('planSha256') == wrapper['planSha256']
            and worker_claim.get('processId') == worker.get('processId')
            and worker_claim.get('parentProcessId') == worker.get('parentProcessId') == broker.get('runnerProcessId')
            and canonical(host.get('worker')) == canonical(worker), 'Consumed worker or broker identity differs')
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
    require(plan.get('kind') == 'combat-trial-plan-v1' and wrapper.get('kind') == 'combat-trial-wrapper-v1'
            and wrapper['runId'] == plan['runId'] == finalization['runId']
            and wrapper['planSha256'] == artifacts['plan.json']
            and finalization.get('manifestSha256') == artifacts['patrol.json'], 'Combat wrapper identities differ')
    require(plan.get('maximumHostSeconds') == 90 and plan.get('recordingMaximumBytes') == 160 * 1024 * 1024
            and type(plan.get('maximumReviewAgeSeconds')) is int and 0 < plan['maximumReviewAgeSeconds'] <= 120
            and canonical(plan.get('policy')) == canonical(trial_policy()), 'Combat plan widened its fixed bounds')
    blobs = []
    for name in ('review', 'plan', 'scene', 'sidecar', 'image', 'goal'):
        reference = plan['evidence'][name]
        raw = bounded_file(local_artifact(folder, reference['retained']))
        require(digest(raw) == reference['sha256'], 'Retained combat review bytes changed: ' + name)
        artifacts[str(reference['retained'])] = digest(raw)
        blobs.append(raw)
    binding = bind_review(*blobs)
    require(canonical(binding) == canonical(plan.get('binding'))
            and canonical(binding['owner']) == canonical(wrapper.get('owner')), 'Frozen combat review does not reproduce its binding')
    required_sources = ('combat_trial.py', 'combat_trial_guard.py', 'stream_client.py', 'native_combat.py',
                        'model_adapters.py', 'resident_runtime.py', 'episode_split.py')
    require(all('tools/bettergi-agent/' + name in plan['sourceFiles'] for name in required_sources),
            'Frozen combat source inventory is incomplete')
    for name, sha in plan['sourceFiles'].items():
        raw = bounded_file(local_artifact(folder, Path('source-snapshot') / name))
        require(digest(raw) == sha, 'Frozen combat source changed: ' + name)
    # Replay uses the implementation that actually produced this trial. A later
    # incompatible guard must be audited from its preserved source snapshot.
    for name in ('combat_trial_guard.py', 'native_combat.py'):
        key = 'tools/bettergi-agent/' + name
        require(plan['sourceFiles'].get(key) == digest(bounded_file(Path(__file__).with_name(name))),
                'Replay implementation differs from the frozen source: ' + name)
    episode = document('native-episode.json')
    require(artifacts['native-episode.json'] == wrapper.get('nativeEpisodeSha256')
            and canonical(episode) == canonical(wrapper.get('nativeEpisode')), 'Wrapper substituted its native episode')
    events, artifacts['recording/events.jsonl'] = json_lines(folder / 'recording/events.jsonl')
    frames, artifacts['recording/frames.jsonl'] = json_lines(folder / 'recording/frames.jsonl')
    report = audit_episode(episode, events, frames, folder / 'recording', binding)
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
        observations, artifacts['recording/observations.jsonl'] = json_lines(folder / 'recording/observations.jsonl')
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
