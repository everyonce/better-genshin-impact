"""Verify independent photo requests and their input handoff on one recorded GPU lease."""
import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from audit_hybrid_run import audit, require
from hybrid_routes import STREET_PATROL_ROUTE
from landmark_recognizer import LandmarkRecognizer
from observation_timing import observation_timestamp
from patrol_photo_survey import require_qualified_observer, validated_targets, verify_photos


def read(path):
    """Read a sealed project JSON file."""
    return json.loads(Path(path).read_bytes())


def check_plan(plan):
    """Check all reviewed requests before trusting any report-provided labels."""
    require(plan.get('version') == 1 and isinstance(plan.get('requests'), list)
            and 2 <= len(plan['requests']) <= 4, 'Expected two to four externally declared requests')
    specs = plan['requests']
    for spec in specs:
        require(re.fullmatch('[0-9a-f]{32}', spec['id']) and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',spec['name'])
                and type(spec['circuits']) is int and spec['circuits'] > 0, 'Invalid request identity or length')
        validated_targets(spec['targets'])
    require(len({s['id'] for s in specs}) == len({s['name'] for s in specs}) == len(specs)
            and len({frozenset(s['targets']) for s in specs}) == len(specs) and sum(s['circuits'] for s in specs) <= 32,
            'Photo requests must be independently identifiable')
    return specs


def bridge_clock(parts):
    """Require a common Windows stopwatch origin as well as one native control owner."""
    hellos = [p['hello'] for p in parts]
    clocks = [(h['sessionId'], h['ownerEpoch'], h['inputTelemetry']['sessionOriginAtStopwatchTicks'],
               h['inputTelemetry']['stopwatchFrequency']) for h in hellos]
    require(len(set(clocks)) == 1 and all(c[0] and c[1] and type(c[2]) is int and c[2] > 0 and
            type(c[3]) is int and c[3] > 0 for c in clocks), 'Warm handoff changed its bridge owner or QPC clock')
    session, owner, origin, frequency = clocks[0]
    return dict(sessionId=session, ownerEpoch=owner, originTicks=origin, frequency=frequency)


def authority_parts(run, recordings, repository):
    """Join the original segment journal to reported events, decisions and native receipts."""
    parts, events, originals, decisions, terminals, frames = [], [], [], [], {}, {}
    for entry in run['segments']:
        part = read(Path(repository)/entry['report'])
        directory = Path(recordings)/f"{entry['number']:05d}"
        parts.append(part)
        journal = []
        with (directory/'events.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if not row.get('continuityContext'):
                    journal.append(row)
        native_events = part.get('hybridNavigationEvents', [])
        types = {row['type'] for row in native_events}
        require([r for r in journal if r.get('type') in types or r.get('type','').startswith('warmPhoto')] == native_events,
                'Warm or native event differs from original event journal')
        require([r for r in journal if r.get('type') == 'controlTransition'] == part.get('controlTransitions', []),
                'Control transitions differ from the original journal')
        events.extend(native_events)
        proposals = [r for r in journal if r.get('type') == 'proposal']
        require(len(proposals) == len(part['decisions']), 'Proposal journal coverage differs')
        for decision, proposal in zip(part['decisions'], proposals):
            require(all(proposal.get(k) == decision.get(k) for k in (
                'frameId','warmRequestId','acceptance','observationTimestampMs','policyGoalVersion',
                'appliedGoalRequestId','historyCommitted','hybridNavigation')),
                'Proposal ownership, history or acceptance differs from original journal')
        decisions.extend(part['decisions'])
        journal_receipts = [r for r in journal if r.get('requestId') and 'appliedSteps' in r]
        require(journal_receipts == part['receipts'], 'Terminal receipts differ from original journal')
        for receipt in journal_receipts:
            rid = receipt['requestId']
            require(terminals.setdefault(rid, receipt) == receipt, 'Conflicting terminal receipt')
        originals.extend(part.get('navigationClimbActions', []))
        require([r for r in journal if r.get('type') == 'navigationClimbAction'] == part.get('navigationClimbActions', []),
                'Recovery action ownership differs from original journal')
        with (directory/'observations.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                frame = json.loads(line)
                if not frame.get('continuityContext'):
                    require(frame['frameId'] not in frames, 'Reused source frame')
                    frames[frame['frameId']] = frame
    return parts, events, decisions, originals, terminals, frames


def check_release(row, endpoint, parts):
    """Tie the boundary to the original acknowledged release before all three stable frames."""
    proof = row['release']
    fid = endpoint['samples'][-1]['frameId']
    require(row['frameId'] == fid and row['sourceEpoch'] == endpoint['sourceEpoch'] and
            row['completedLegs'] == endpoint['completedLegs'] and row['pendingActionIds'] == [],
            'Completion differs from stable endpoint or retains pending actions')
    held = [t for p in parts for t in p['controlTransitions'] if t.get('state') == 'held'
            and t.get('reason') == 'hybridEndpoint' and t['frameId'] == endpoint['arrivalFrameId']]
    require(len(held) == 1 and held[0]['warmRelease'] == proof and held[0]['warmRequestId'] == row['warmRequestId'],
            'Boundary lacks the original owned held/release evidence')
    require(proof['type'] == 'released' and proof['arrivalFrameId'] == endpoint['arrivalFrameId']
            and proof['readinessEpoch'] == endpoint['releaseEpoch'] and proof['captureEpoch'] == endpoint['sourceEpoch']
            and proof['serverNowMs'] == endpoint['releaseAtMs'] and proof['readinessReason'] == 'client_release'
            and proof['readinessReady'] is False and proof['policyHistoryReset'] is True,
            'Boundary release identity, clock or policy history reset differs')


def lifecycle(events, parts, specs, run_id, plan_hash, clock, interrupted):
    """Bind every lifecycle marker to the plan, native endpoint and single policy-goal identity."""
    rows = [e for e in events if e['type'].startswith('warmPhoto')]
    started, completed, handoff = 'warmPhotoRequestStarted', 'warmPhotoRequestCompleted', 'warmPhotoHandoff'
    sequence = []
    for index in range(len(specs)):
        sequence.append((started,index))
        if not interrupted or index < len(specs)-1:
            sequence.append((completed,index))
        if index < len(specs)-1:
            sequence.append((handoff,index))
    require([(e['type'],e['warmRequestId']) for e in rows] == [(t,specs[i]['id']) for t,i in sequence],
            'Unexpected warm lifecycle sequence')
    require(len({r['goalEmbeddingSha256'] for r in rows}) == 1 and
            re.fullmatch('[0-9a-f]{64}',rows[0]['goalEmbeddingSha256']), 'Visual policy goal changed between requests')
    goals = [p['policyMetadata']['goal'] for p in parts]
    require(all(goal == goals[0] and not p.get('goalChanges') for goal,p in zip(goals,parts))
            and hashlib.sha256(Path(goals[0]['file']).read_bytes()).hexdigest() == rows[0]['goalEmbeddingSha256'],
            'Warm lifecycle embedding digest differs from the loaded visual policy goal')
    for row, (_, index) in zip(rows, sequence):
        spec = specs[index]
        require(row['ordinal'] == index+1 and row['name'] == spec['name'] and row['targets'] == spec['targets']
                and row['circuits'] == spec['circuits'] and row['planSha256'] == plan_hash and row['runId'] == run_id
                and all(row[k] == clock[k] for k in ('sessionId','ownerEpoch')), 'Lifecycle identity differs from external plan')
    native_start, = [e for e in events if e['type'] == 'hybridStartVerified']
    ends = [e for e in events if e['type'] == 'hybridEndpointVerified']
    require(rows[0]['frameId'] == native_start['frameId'], 'Request did not open at native start')
    boundaries, completions = [], []
    legs = 0
    for i,spec in enumerate(specs):
        legs += 4*spec['circuits']
        if interrupted and i == len(specs)-1:
            require(len(ends) < legs, 'Stop drill already completed its final route')
            break
        require(len(ends) >= legs, 'Request did not meet its own native route target')
        end = ends[legs-1]
        done = rows[3*i+1]
        check_release(done, end, parts)
        completions.append(done)
        if i == len(specs)-1:
            require(len(ends) == legs, 'Route exceeded its final request')
            break
        switch, following = rows[3*i+2:3*i+4]
        boundary = end['samples'][-1]['frameId']
        require(switch['frameId'] == following['frameId'] == boundary and
                switch['nextRequestId'] == specs[i+1]['id'] and following['previousRequestId'] == spec['id']
                and switch['release'] == done['release'] and switch['pendingActionIds'] == []
                and switch['lastAcceptedRequestId'] == done['lastAcceptedRequestId'],
                'Handoff did not reuse the released circuit endpoint')
        actual_circuit, = [e for e in events if e['type'] == 'hybridCircuitVerified' and e['frameId'] == boundary]
        pos = events.index(actual_circuit)
        require(events[pos+1:pos+4] == [done,switch,following], 'Switch does not immediately follow the verified circuit release')
        boundaries.append(boundary)
    require(boundaries == sorted(set(boundaries)), 'Request boundaries must advance on new original frames')
    for e in [native_start,*ends,*[e for e in events if e['type']=='hybridCircuitVerified']]:
        fid = e['samples'][-1]['frameId'] if 'samples' in e else e['frameId']
        require(e['warmRequestId'] == specs[bisect_left(boundaries,fid)]['id'], 'Native station belongs to another request')
    return boundaries, completions


def attribute_actions(decisions, recovery, terminals, frames, specs, boundaries, completions, clock):
    """Associate every admitted native action and all of its software dispatches with one request."""
    groups = [[] for spec in specs]
    boundary_times = [observation_timestamp(frames[fid]) for fid in boundaries]
    freq, origin = clock['frequency'], clock['originTicks']

    def ticks(ms):
        """Convert native lease milliseconds to the shared Windows QPC timeline."""
        return origin + round(ms * freq / 1000)

    accepted = {}
    tagged = [(d, False) for d in decisions] + [(a, True) for a in recovery]
    for row, is_recovery in tagged:
        fid = row['frameId']
        owner = bisect_left(boundaries,fid)
        require(row.get('warmRequestId') == specs[owner]['id'], 'Action belongs to a retired or future request')
        receipt_id = row['acceptance'].get('requestId')
        admitted = row['acceptance'].get('type') == 'accepted'
        if not is_recovery:
            require(isinstance(row.get('hybridNavigation'), dict)
                    and row['historyCommitted'] is (admitted and row['hybridNavigation']['owner'] == 'open-p2p')
                    and row.get('policyGoalVersion') == 0 and row.get('appliedGoalRequestId') is None,
                    'History was committed under a different controller or goal')
        if not admitted:
            continue
        require(receipt_id and receipt_id not in accepted and receipt_id in terminals, 'Unresolved or duplicate action ownership')
        accepted[receipt_id] = owner
        receipt, frame = terminals[receipt_id], frames[fid]
        source = frame['sourceFrame']
        sampled = observation_timestamp(frame)
        # WGC reports a 100ns QPC anchor and the bridge separately converts the same stamp to lease time.
        require(abs(ticks(source['capturedAtMs']) - round(source['timestamp100ns']*freq / 10_000_000)) <= 1,
                'Source QPC anchor disagrees with bridge clock origin')
        require(receipt['frameId'] == fid and receipt['status'] in ('completed','cancelled','replaced','expired')
                and receipt['acceptedAtMs'] == row['acceptance']['acceptedAtMs']
                and receipt['acceptedAtMs'] <= receipt['endedAtMs']
                and (owner >= len(completions) or receipt['endedAtMs'] <= completions[owner]['release']['serverNowMs'])
                and (owner == 0 or receipt['acceptedAtMs'] > boundary_times[owner-1]),
                'Old action outlived handoff or new action was admitted early')
        steps = receipt['appliedSteps']
        if not steps:
            continue
        times = [s['startedAtMs'] for s in steps]
        age = times[0] - sampled
        require(all(math.isfinite(t) for t in times) and times == sorted(times)
                and receipt['acceptedAtMs'] <= times[0] <= times[-1] <= receipt['endedAtMs'] and 0 <= age <= 150,
                'Applied step timing, software horizon or source deadline differs')
        groups[owner].append(dict(nativeRequestId=receipt_id,frameId=fid,sourceAgeMs=age,
                                  firstDispatchTicks=ticks(times[0]),lastStepTicks=ticks(times[-1]),
                                  terminalEndTicks=ticks(receipt['endedAtMs']),terminalEndMs=receipt['endedAtMs'],
                                  acceptedAtMs=receipt['acceptedAtMs']))
    require(set(accepted) == set(terminals) and all(groups), 'Missing or unattributed terminal input, or empty request')
    for group in groups:
        group.sort(key=lambda a:a['firstDispatchTicks'])
    # The runtime's completion witness must name the final admission, including a cancelled unapplied action.
    for i,done in enumerate(completions):
        final_id = max((rid for rid,index in accepted.items() if index == i), key=lambda rid:terminals[rid]['acceptedAtMs'])
        require(done['lastAcceptedRequestId'] == final_id, 'Request completion names the wrong terminal action')
    switches = []
    for i,boundary in enumerate(boundaries):
        following = next((d for d in decisions if d.get('warmRequestId') == specs[i+1]['id']), None)
        require(following and following.get('episodeStep') == 1 and following.get('validHistoryFrames') == 1,
                'First new request decision reused an old policy episode')
        old, new = max(groups[i],key=lambda a:a['lastStepTicks']), groups[i+1][0]
        gap = (new['firstDispatchTicks'] - old['lastStepTicks']) * 1000 / clock['frequency']
        require(0 < gap < 1000, 'Warm handoff missed the under-one-second dispatch limit')
        switches.append(dict(oldRequestId=specs[i]['id'],newRequestId=specs[i+1]['id'],dispatchGapMs=gap,
                             oldLast=old,newFirst=new,boundaryFrameId=boundary,boundaryQpcTicks=ticks(boundary_times[i]),
                             pendingOldActions=0,firstNewEpisodeStep=following['episodeStep'],
                             firstNewHistoryFrames=following['validHistoryFrames']))
    return groups,switches


def photo_proofs(root, report, events, specs, boundaries, head):
    """Replay each request's own native visits against its disjoint original PNG inventory."""
    native = [e for e in events if e['type'] in ('hybridStartVerified','hybridEndpointVerified')]
    poses = {e['samples'][-1]['frameId']:e['samples'][-1] for e in native}
    photos = []
    for i,spec in enumerate(specs):
        directory = Path(root)/spec['id']
        manifest = read(directory/'manifest.json')
        require(manifest.get('format') == 'bettergi-patrol-photo-survey-v1'
                and manifest['routeId'] == STREET_PATROL_ROUTE and manifest['targets'] == spec['targets']
                and manifest['checkpointId'] == head.checkpoint_id, 'Photo objective or model does not match declared request')
        sources = [s for s in report['landmarkShadow']['sources'] if bisect_left(boundaries,s['frameId']) == i]
        visits = [e['photoSurveyVisit'] for e in native if e['warmRequestId'] == spec['id'] and e.get('photoSurveyVisit') is not None]
        require(manifest['journal'] == visits, 'Photo visit journal crossed a request boundary')
        photos.append(verify_photos(directory,manifest,spec['targets'],sources,poses,head))
    return photos


def terminal_release(parts, groups):
    """Verify the final native software release acknowledges an empty tracked key state."""
    stop = parts[-1].get('stop') or {}
    ctx = stop.get('executionContext') or {}
    last = ctx.get('lastInputEvent') or {}
    require(stop.get('type') == 'stopped' and ctx.get('telemetryComplete') is True and ctx.get('active') is None
            and ctx.get('trackedState',{}).get('heldKeys') == [] and last.get('origin') == 'release:client_stop'
            and ctx['trackedState'].get('telemetryIncomplete') is False
            and ctx['trackedState'].get('releaseOutcome') == 'returned_unverified'
            and last.get('call',{}).get('operation') == 'releaseAll'
            and last['call'].get('stage') == 'returned_unverified' and last['call'].get('error') is None
            and all(t['terminalEndMs'] <= last['atMs'] for group in groups for t in group),
            'Lease lacks software release acknowledgement and empty tracked input')
    return last['atMs']


def validate_stop(folder, run, parts, specs, groups):
    """Prove the external operator stop targeted this run after a confirmed second-request step."""
    witness = read(folder/'operator-stop.json')
    marker = read(folder/'STOP')
    supervisor = read(folder/'launcher.json')
    control = read(folder/'patrol.json.control.json')
    first = groups[1][0]
    require(witness.get('version') == 1 and witness['mode'] == 'external-stop-drill'
            and witness['runId'] == run['runId'] == control['runId'] and control['command'] == 'stop'
            and witness['requestId'] == specs[1]['id'] and witness['nativeRequestId'] == first['nativeRequestId']
            and witness['frameId'] == first['frameId'], 'Stop did not target the active request and first second-task dispatch')
    require(marker == {k:v for k,v in witness.items() if k not in (
                'stopFileCreatedAtMonotonicNs','addressedStopAtMonotonicNs','addressedStopQpc')}
            and supervisor.get('runId') == run['runId'] and supervisor.get('stopReason') == 'seriesOperatorStop'
            and supervisor.get('stopRequested') is True
            and supervisor.get('stopRequestedAtMonotonicNs') == witness['addressedStopAtMonotonicNs'],
            'External STOP marker or launcher-addressed stop evidence differs')
    times = [witness[k] for k in ('observedAtMonotonicNs','stopFileCreatedAtMonotonicNs','addressedStopAtMonotonicNs')]
    require(all(type(t) is int and t > 0 for t in times) and times == sorted(times), 'Stop proof chronology differs')
    require(run['endReason'] == 'userStop', 'The addressed stop did not end the lease')
    release_ms = terminal_release(parts,groups)
    result = dict(requestId=specs[1]['id'],firstAppliedNativeRequestId=first['nativeRequestId'],
                  terminalReleaseAtMs=release_ms,physicalExecutionProven=False,
                  markerToAddressedStopMs=(times[2]-times[1])/1_000_000)
    if 'addressedStopQpc' in witness or 'addressedStopQpc' in supervisor:
        bracket = witness.get('addressedStopQpc')
        clock = bridge_clock(parts)
        require(isinstance(bracket,dict) and bracket == supervisor.get('addressedStopQpc')
                and set(bracket) == {'clock','frequencyHz','beforeTicks','afterTicks'}
                and bracket['clock'] == 'windows-query-performance-counter'
                and all(type(bracket[k]) is int for k in ('frequencyHz','beforeTicks','afterTicks'))
                and bracket['frequencyHz'] == clock['frequency'], 'Stop bracket does not match the native QPC clock')
        before, after, hz = bracket['beforeTicks'], bracket['afterTicks'], bracket['frequencyHz']
        # The bridge records elapsed TimeSpan ticks (100 ns). SIREN's 10 MHz QPC maps those one-to-one.
        require(hz == 10_000_000, 'Exact stop-return tick reconstruction requires the SIREN 10 MHz QPC')
        released = clock['originTicks'] + round(release_ms * 10_000)
        require(first['firstDispatchTicks'] <= before <= after and before <= released,
                'Addressed stop write cannot have caused this native release')
        result['addressedStopToRelease'] = dict(minimumMs=max(0,released-after)*1000/hz,
                maximumMs=(released-before)*1000/hz,releaseTicks=released,beforeTicks=before,afterTicks=after,
                frequencyHz=hz)
    return result


def audit_photo_handoff(run_path, recordings, *, repository, photo_root, requests, landmark_checkpoint,
                        qualification, authenticated_report=None, allow_incomplete=False):
    """Verify a complete handoff or report a separately verified operator-cancelled prefix."""
    run_path = Path(run_path)
    run = read(run_path)
    plan_path = run_path.parent/'photo-requests.json'
    plan_bytes = plan_path.read_bytes()
    plan = read(requests) if isinstance(requests,(str,Path)) else requests
    require(json.loads(plan_bytes) == plan, 'Recorded plan differs from externally declared requests')
    specs = check_plan(plan)
    interrupted = run.get('endReason') == 'userStop'
    require(not allow_incomplete or len(specs) == 2, 'Stop drill requires exactly two declared requests')
    require((interrupted and allow_incomplete) or run.get('endReason') == 'hybridLegLimit', 'Unexpected resident end reason')
    head = LandmarkRecognizer.load(landmark_checkpoint)
    require_qualified_observer(qualification,head.checkpoint_id)
    supervisor = read(run_path.parent/'launcher.json')
    admission = read(run_path.parent/'warm-launcher.json')
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    require(admission.get('computer','').split('.')[0].upper() == 'SIREN' and admission['planSha256'] == plan_sha
            and supervisor.get('runId') == run['runId'] and supervisor.get('stopAtC') == 78
            and supervisor.get('windowsSessionId') == run['windowsSessionId'] and run['windowsSessionId'] > 0
            and all(type(supervisor.get(k)) is int and supervisor[k] > 0 for k in ('rootPid','childPid'))
            and supervisor['rootPid'] != supervisor['childPid'] and
            (interrupted or supervisor.get('verified') is True and supervisor.get('stopRequested') is False
             and supervisor.get('stopReason') is None), 'Handoff lacks its SIREN RDP supervisor and addressed lease')
    report = audit(run_path,recordings,repository=repository,landmark_checkpoint=landmark_checkpoint,
                   minimum_circuits=specs[0]['circuits'] if interrupted else sum(r['circuits'] for r in specs))
    if authenticated_report is not None:
        earlier = read(authenticated_report) if isinstance(authenticated_report,(str,Path)) else authenticated_report
        require(all(report[k] == earlier.get(k) for k in ('passed','routeId','verifiedLegs','verifiedCircuits','landmarkShadow')),
                'Supplied patrol audit differs from independent warm audit')
    require(report.get('passed') and report['routeId'] == STREET_PATROL_ROUTE and report['controllerLeases'] == 1
            and run['modelLoads'] == 1 and run.get('failedLeases') == 0 and run.get('goalChanges') == [],
            'Warm run lacks a single resident policy and stable route/goal')
    parts, events, decisions, recovery, receipts, frames = authority_parts(run,recordings,repository)
    clock = bridge_clock(parts)
    boundaries, completed = lifecycle(events,parts,specs,run['runId'],plan_sha,clock,interrupted)
    rows, switches = attribute_actions(decisions,recovery,receipts,frames,specs,boundaries,completed,clock)
    photos = photo_proofs(photo_root,report,events,specs,boundaries,head)
    require(all(p['complete'] for p in (photos[:-1] if interrupted else photos)), 'Declared photo objective is incomplete')
    stop = validate_stop(run_path.parent,run,parts,specs,rows) if interrupted else None
    with (run_path.parent/'gpu.jsonl').open(encoding='utf-8') as stream:
        thermal = [json.loads(line) for line in stream]
    require(len(thermal) >= 2 and all(not t.get('error') and type(t.get('temperatureC')) in (int,float)
            and 0 < t['temperatureC'] < 78 for t in thermal), 'Missing or unsafe GPU telemetry during handoff')
    summaries = []
    for spec,group,photo in zip(specs,rows,photos):
        ages = [a['sourceAgeMs'] for a in group]
        summaries.append(dict(id=spec['id'],name=spec['name'],actions=len(group),photos=photo,
                              first=group[0],last=group[-1],medianSourceAgeMs=statistics.median(ages),maximumSourceAgeMs=max(ages)))
    return dict(version=1,passed=not interrupted,status='operator-stopped-prefix' if interrupted else 'qualified',
                stopVerified=interrupted,stop=stop,modelLoads=1,controllerLeases=1,runId=run['runId'],
                verifiedLegs=report['verifiedLegs'],verifiedCircuits=report['verifiedCircuits'],
                requests=summaries,clock=clock,handoffs=switches,**({'handoff':switches[0]} if len(switches)==1 else {}),
                terminalReleaseAtMs=terminal_release(parts,rows),
                peakGpuTemperatureC=max(t['temperatureC'] for t in thermal),
                windowsSessionId=run['windowsSessionId'],rootPid=supervisor['rootPid'],childPid=supervisor['childPid'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('run','recordings','photo-root','requests','landmark-checkpoint','qualification','output'):
        parser.add_argument('--'+flag, type=Path, required=True)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--allow-incomplete', action='store_true')
    args = vars(parser.parse_args())
    args['run_path'] = args.pop('run')
    destination = args.pop('output')
    result = audit_photo_handoff(**args)
    with destination.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(result['status'],destination)
