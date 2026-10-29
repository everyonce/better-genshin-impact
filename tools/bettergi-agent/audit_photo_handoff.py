"""Verify independent photo requests and their input handoff on one recorded GPU lease."""
import argparse
from bisect import bisect_left
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from audit_destination_retries import RELEASE_REJECTED, RELEASE_RETRY, RETRY, verify_release_order, verify_retry_images
from audit_hybrid_run import audit, batch_edges, check_patrol_leg, destination_edges, require
from audit_warm_batches import read_batches, verify_batch_events
from hybrid_routes import STREET_PATROL_ROUTE
from landmark_recognizer import G4_SHA256, LandmarkRecognizer
from observation_timing import observation_timestamp
from patrol_photo_survey import require_qualified_observer, validated_targets, verify_photos


def read(path):
    """Read a sealed project JSON file."""
    return json.loads(Path(path).read_bytes())


def check_plan(plan):
    """Check all reviewed requests before trusting any report-provided labels."""
    require(plan.get('version') in (1,2) and isinstance(plan.get('requests'), list)
            and 2 <= len(plan['requests']) <= 4, 'Expected two to four externally declared requests')
    specs = plan['requests']
    directed = plan['version'] == 2
    require(directed or 'confirmFirstArrival' not in plan, 'A second destination view requires an itinerary')
    if directed:
        destination_edges(plan)
    for spec in specs:
        require(re.fullmatch('[0-9a-f]{32}', spec['id']) and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',spec['name'])
                and (directed or type(spec['circuits']) is int and spec['circuits'] > 0), 'Invalid request identity or length')
        validated_targets(spec['targets'])
    require(len({s['id'] for s in specs}) == len({s['name'] for s in specs}) == len(specs)
            and (directed or len({frozenset(s['targets']) for s in specs}) == len(specs)
                 and sum(s['circuits'] for s in specs) <= 32),
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


def authority_parts(run, recordings, repository, directed=False, batch_queue=False):
    """Join the original segment journal to reported events, decisions and native receipts."""
    parts, events, originals, decisions, terminals, frames = [], [], [], [], {}, {}
    active = None
    release_trace = []
    settling = False
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
        if batch_queue:
            for row in journal:
                if row.get('type') == 'warmPhotoRequestStarted':
                    require(active is None, 'Two published requests simultaneously own input')
                    active = row['warmRequestId']
                elif row.get('type') == 'warmPhotoRequestCompleted':
                    require(active == row.get('warmRequestId'), 'Unowned queue completion')
                    active = None
                elif row.get('type') in ('proposal','navigationClimbAction'):
                    require(active and row.get('warmRequestId') == active,
                            'Proposal submitted before queue admission or after request release')
        if directed:
            for row in journal:
                kind=row.get('type')
                if kind=='controlTransition' and row.get('reason')=='hybridEndpoint' and row.get('state')=='held':
                    release_trace.append(('held',row['frameId']))
                    settling = True
                if kind in ('hybridEndpointVerified',RETRY):
                    settling = (row.get('photoSurveyVisit') or {}).get('outcome') in ('confirmationPending','classificationMiss')
                if kind in ('proposal','navigationClimbAction'):
                    require(not settling, 'Original journal contains input while the endpoint was held for verification')
                if kind in (RELEASE_REJECTED,RELEASE_RETRY,'hybridEndpointVerified'):
                    key={RELEASE_REJECTED:'firstArrivalFrameId',RELEASE_RETRY:'retryArrivalFrameId',
                         'hybridEndpointVerified':'arrivalFrameId'}[kind]
                    release_trace.append((kind,row[key]))
        native_events = part.get('hybridNavigationEvents', [])
        types = {row['type'] for row in native_events}
        require([r for r in journal if r.get('type') in types or r.get('type','').startswith(('warmPhoto','warmBatch','warmQueue','hybrid'))] == native_events,
                'Warm or native event differs from original event journal')
        require([r for r in journal if r.get('type') == 'controlTransition'] == part.get('controlTransitions', []),
                'Control transitions differ from the original journal')
        events.extend(native_events)
        proposals = [r for r in journal if r.get('type') == 'proposal']
        require(len(proposals) == len(part['decisions']), 'Proposal journal coverage differs')
        for decision, proposal in zip(part['decisions'], proposals):
            if directed:
                require(all(k in proposal and proposal[k] == decision.get(k) for k in (
                        'steps','rawPolicySteps','episodeStep','validHistoryFrames','cudaGraphActive','startBeforeMs'))
                        and proposal['cudaGraphActive'] is True and proposal.get('model') == decision['hybridNavigation']['owner'],
                        'GPU evaluation, proposed inputs or episode history differ from the source journal')
            require(all(proposal.get(k) == decision.get(k) for k in (
                'frameId','warmRequestId','acceptance','observationTimestampMs','policyGoalVersion',
                'appliedGoalRequestId','historyCommitted','hybridNavigation')),
                'Proposal ownership, history or acceptance differs from original journal')
        decisions.extend(part['decisions'])
        journal_receipts = [r for r in journal if r.get('requestId') and 'appliedSteps' in r]
        require(journal_receipts == part['receipts'], 'Terminal receipts differ from original journal')
        for receipt in journal_receipts:
            rid = receipt['requestId']
            require((not directed or rid not in terminals) and terminals.setdefault(rid, receipt) == receipt,
                    'Duplicate or conflicting terminal receipt')
        originals.extend(part.get('navigationClimbActions', []))
        require([r for r in journal if r.get('type') == 'navigationClimbAction'] == part.get('navigationClimbActions', []),
                'Recovery action ownership differs from original journal')
        with (directory/'observations.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                frame = json.loads(line)
                if not frame.get('continuityContext'):
                    require(frame['frameId'] not in frames, 'Reused source frame')
                    frames[frame['frameId']] = frame
    if directed:
        verify_release_order(release_trace,events)
    return parts, events, decisions, originals, terminals, frames


def check_release(row, endpoint, parts, completion_frame=None):
    """Tie the boundary to the original acknowledged release before all three stable frames."""
    fid = endpoint['samples'][-1]['frameId'] if completion_frame is None else completion_frame
    require(row['frameId'] == fid and row['sourceEpoch'] == endpoint['sourceEpoch'] and
            row['completedLegs'] == endpoint['completedLegs'] and row['pendingActionIds'] == [],
            'Completion differs from stable endpoint or retains pending actions')
    proof = endpoint_release(endpoint, parts, row['warmRequestId'])
    require(proof == row['release'], 'Boundary lacks the original owned held/release evidence')


def endpoint_release(endpoint, parts, owner):
    """Return the owned acknowledgement at this arrival after verifying epoch, source and reset."""
    held = [t for p in parts for t in p['controlTransitions'] if t.get('state') == 'held'
            and t.get('reason') == 'hybridEndpoint' and t['frameId'] == endpoint['arrivalFrameId']]
    require(len(held) == 1 and held[0]['warmRequestId'] == owner,
            'Boundary lacks the original owned held/release evidence')
    proof = held[0]['warmRelease']
    require(proof['type'] == 'released' and proof['arrivalFrameId'] == endpoint['arrivalFrameId']
            and proof['readinessEpoch'] == endpoint['releaseEpoch'] and proof['captureEpoch'] == endpoint['sourceEpoch']
            and proof['serverNowMs'] == endpoint['releaseAtMs'] and proof['readinessReason'] == 'client_release'
            and proof['readinessReady'] is False and proof['policyHistoryReset'] is True,
            'Boundary release identity, clock or policy history reset differs')
    return proof


def lifecycle(events, parts, specs, run_id, plan_hash, clock, interrupted, edges=None, confirm_first=False,
              failed_photo=False):
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
        objective = 'destination' if edges is not None else 'circuits'
        require(row['ordinal'] == index+1 and row['name'] == spec['name'] and row['targets'] == spec['targets']
                and row[objective] == spec[objective] and row['planSha256'] == plan_hash and row['runId'] == run_id
                and all(row[k] == clock[k] for k in ('sessionId','ownerEpoch')), 'Lifecycle identity differs from external plan')
    native_start, = [e for e in events if e['type'] == 'hybridStartVerified']
    ends = [e for e in events if e['type'] == 'hybridEndpointVerified']
    require(rows[0]['frameId'] == native_start['frameId'], 'Request did not open at native start')
    if edges is not None:
        require(rows[0]['completedLegs'] == 0 and rows[0]['sourceEpoch'] == native_start['sourceEpoch']
                and events[events.index(native_start)+1] == rows[0], 'First destination lacks its original start boundary')
    boundaries, completions = [], []
    legs = 0
    milestone = 'hybridDestinationVerified' if edges is not None else 'hybridCircuitVerified'
    for i,spec in enumerate(specs):
        legs += sum(edge[2] == i+1 for edge in edges) if edges is not None else 4*spec['circuits']
        if interrupted and i == len(specs)-1:
            require((len(ends)==legs) if failed_photo else len(ends)<legs,'Unexpected last physical request completion')
            break
        require(len(ends) >= legs, 'Request did not meet its own native route target')
        end = ends[legs-1]
        done = rows[3*i+1]
        completions.append(done)
        original = end['samples'][-1]['frameId']
        boundary = original
        native, = [e for e in events if e['type'] == milestone and e['frameId'] == original]
        pos = events.index(native)
        if edges is not None:
            require(events[pos-1] == end and
                    native['requestedDestination'] == native['station'] == spec['destination'],
                    'Destination completion does not own its exact released endpoint')
            retry = [e for e in events if e['type'] == RETRY and e['initialEndpointFrameId'] == original]
            if retry:
                boundary = retry[-1]['frameId']
                require(events[pos+1:pos+1+len(retry)] == retry and done.get('initialEndpointFrameId') == original
                        and done.get('retryOrdinal') == len(retry), 'Completion differs from its stationary retry chain')
                pos += len(retry)
            else:
                require('retryOrdinal' not in done and 'initialEndpointFrameId' not in done,
                        'Destination completion claims a retry that never occurred')
            if confirm_first and i == 0:
                first, = [e for e in [end,*retry] if (e.get('photoSurveyVisit') or {}).get('outcome') == 'confirmationPending']
                require(done.get('firstConfirmedFrameId') == first['samples'][-1]['frameId'] < boundary,
                        'Destination lacks its independently planned second agreeing view')
            else:
                require('firstConfirmedFrameId' not in done, 'Unexpected second-view confirmation')
            require(events[pos+1] == done, 'Destination completion does not immediately follow its last qualified frame')
        check_release(done, end, parts, boundary)
        if i == len(specs)-1:
            require(len(ends) == legs, 'Route exceeded its final request')
            break
        switch, following = rows[3*i+2:3*i+4]
        require(switch['frameId'] == following['frameId'] == boundary and
                switch['nextRequestId'] == specs[i+1]['id'] and following['previousRequestId'] == spec['id']
                and switch['release'] == done['release'] and switch['pendingActionIds'] == []
                and switch['lastAcceptedRequestId'] == done['lastAcceptedRequestId'],
                'Handoff did not reuse the released circuit endpoint')
        if edges is not None:
            require(switch['sourceEpoch'] == following['sourceEpoch'] == end['sourceEpoch']
                    and switch['completedLegs'] == following['completedLegs'] == legs,
                    'Warm switch carries the wrong destination capture epoch or edge count')
            if boundary != original:
                require(switch.get('initialEndpointFrameId') == original and switch.get('retryOrdinal') == len(retry),
                        'Handoff differs from the original endpoint or retry count')
            else:
                require('retryOrdinal' not in switch and 'initialEndpointFrameId' not in switch,
                        'Handoff claims a retry that never occurred')
            if confirm_first and i == 0:
                require(switch.get('firstConfirmedFrameId') == done['firstConfirmedFrameId'],
                        'Handoff differs from the first confirmed view')
        require(events[pos+1:pos+4] == [done,switch,following], 'Switch does not immediately follow the verified circuit release')
        boundaries.append(boundary)
    require(boundaries == sorted(set(boundaries)), 'Request boundaries must advance on new original frames')
    for e in [native_start,*ends,*[e for e in events if e['type'] in (milestone,RETRY)]]:
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


def photo_proofs(root, report, events, specs, boundaries, head, completed=None, confirm_first=False):
    """Replay each request's own native visits against its disjoint original PNG inventory."""
    native = [e for e in events if e['type'] in ('hybridStartVerified','hybridEndpointVerified',RETRY)]
    poses = {e['samples'][-1]['frameId']:e['samples'][-1] for e in native}
    photos = []
    image_ids = set()
    for i,spec in enumerate(specs):
        directory = Path(root)/spec['id']
        manifest = read(directory/'manifest.json')
        require(manifest.get('format') == 'bettergi-patrol-photo-survey-v1'
                and manifest['routeId'] == STREET_PATROL_ROUTE and manifest['targets'] == spec['targets']
                and manifest['checkpointId'] == head.checkpoint_id, 'Photo objective or model does not match declared request')
        sources = [s for s in report['landmarkShadow']['sources'] if bisect_left(boundaries,s['frameId']) == i]
        visits = [e['photoSurveyVisit'] for e in native if e['warmRequestId'] == spec['id'] and e.get('photoSurveyVisit') is not None]
        require(manifest['journal'] == visits, 'Photo visit journal crossed a request boundary')
        second_view = confirm_first and i==0
        photo = verify_photos(directory,manifest,spec['targets'],sources,poses,head,confirm_first=second_view)
        if completed is not None:
            photo['retryEvidence'] = verify_retry_images(directory,visits,sources,head,second_view)
            collected = [v for v in visits if v.get('outcome') == 'collected']
            if i < len(completed):
                fid = completed[i]['frameId']
                require(len(collected) == 1 and collected[0]['frameId'] == fid and
                        collected[0]['station'] == spec['destination'], 'Photo source differs from request endpoint')
                source, = [s for s in sources if s['frameId'] == fid]
                require(source['liveRgbSha256'] not in image_ids, 'A completed request reused an earlier photo')
                image_ids.add(source['liveRgbSha256'])
                photo.update(frameId=fid, file=str((directory/collected[0]['file']).resolve()),
                             pngSha256=collected[0]['pngSha256'],liveRgbSha256=source['liveRgbSha256'],
                             decodedStation=source['decoded'],sourceTimestamp100ns=source['sourceTimestamp100ns'])
            else:
                require(not collected and not photo['complete'], 'Unfinished request already claims a destination photo')
        photos.append(photo)
    return photos


def directed_controls(run, supervisor, parts, events, decisions, recovery, receipts, frames, edges, clock, *, failed=False):
    """Authenticate the budgets, source clock, every proposed leg, every terminal step and every endpoint hold."""
    seconds = supervisor.get('wallTimeLimitSeconds')
    require(type(seconds) is int and 15 <= seconds <= 600 and run.get('mode') == 'resident-rdp'
            and run.get('observationProfile') == 'p2p-native-hamming-192-v1'
            and run.get('recordingBudgetExhausted') is False and 0 < run['recordedBytes'] <= 160 * 2**20
            and run['recordedBytes'] == sum(p['recording']['recordedBytes'] for p in parts)
            and all(e.get('processId') == supervisor['childPid'] and e.get('exitCode') == int(failed and i==len(parts)-1)
                    for i,e in enumerate(run['segments'])),
            'Destination route exceeded its bounded RDP or recording profile')
    require(all(p.get('decisionHz') == 10 and p.get('actionHoldMs') == 100 and p.get('maxObservationAgeMs') == 150
                and (p.get('firstInputDeadlinePolicy') or {}).get('serverEnforcementRequested') is True
                and sorted(p.get('effectiveInputKeys',[])) == ['A','D','S','W'] for p in parts),
            'Destination input cadence, freshness or permitted keys changed')
    for frame in frames.values():
        stamp = frame['sourceFrame']
        qpc = clock['originTicks'] + round(stamp['capturedAtMs'] * clock['frequency']/1000)
        require(abs(qpc-round(stamp['timestamp100ns'] * clock['frequency']/10_000_000)) <= 1,
                'A directed source clock differs from its original WGC QPC anchor')
    ends = [e for e in events if e['type'] == 'hybridEndpointVerified']
    verified = [e['samples'][-1]['frameId'] for e in ends]
    started, = [e for e in events if e['type'] == 'hybridStartVerified']
    qualified = [s['frameId'] for e in [started,*ends] for s in e['samples']]
    qualified.extend(e['arrivalFrameId'] for e in ends)
    qualified.extend(row['frameId'] for row in decisions)
    for fid in set(qualified):
        frame = frames[fid]
        gate = frame['frameWorldReadiness']
        pose = frame['navigationPose']
        motion = frame.get('motionEvidence') or {}
        require(frame['inputAvailable'] is True and gate.get('ready') is True and gate.get('sourceFrameId') == fid
                and gate.get('sourceFrame') == frame['sourceFrame'] and pose.get('frameId') == fid
                and pose.get('state') == 'valid' and pose.get('layerId') == 'City_102'
                and .99 <= pose['positionConfidence'] <= 1 and .2 <= pose['yawConfidence'] <= 1
                and 0 <= pose['yawDegrees'] < 360 and motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False,
                'Directed source does not carry its own world-readiness and input gate')
    for row in decisions:
        fid = row['frameId']
        leg = bisect_left(verified,fid)
        h = row['hybridNavigation']
        require(fid >= started['frameId'] and fid not in verified and h.get('completedLegs') == leg
                and (leg == len(ends) or fid < ends[leg]['arrivalFrameId'])
                and h.get('target') == h.get('toStation') and h.get('pose') == frames[fid]['navigationPose'],
                'Directed decision belongs to the wrong active segment or source pose')
        check_patrol_leg(h,leg,edges)
        ack = row['acceptance']
        if ack.get('type') != 'accepted':
            continue
        step = h['step']
        if h['owner'] == 'open-p2p':
            raw = row['rawPolicySteps']
            require(h.get('reason') == 'modelRouteCompatible' and len(raw) == 1
                    and raw[0].get('keys') == step.get('keys') == ['W']
                    and raw[0].get('mouseDx') == step.get('mouseDx') and abs(step['mouseDx']) <= 3
                    and raw[0].get('mouseDy') == step.get('mouseDy') == 0,
                    'GPU-owned step does not match the original image-conditioned movement')
        require(h['owner'] in ('open-p2p','hybrid-native','calibrated-camera') and row['steps'] == [step]
                and step.get('keys') in ([],['W'],['A'],['S'],['D']) and step.get('durationMs') == 100
                and step.get('mouseDy') == 0 and abs(step.get('mouseDx',999)) <= 350
                and row['startBeforeMs'] == observation_timestamp(frames[fid])+150,
                'Directed action exceeds its input or time budget')
        receipt = receipts[ack['requestId']]
        actual = receipt['appliedSteps']
        require(len(actual) <= 1 and all(s.get('index') == 0 and all(s[k] == step[k]
                for k in ('keys','mouseDx','mouseDy')) for s in actual),
                'Applied directed input differs from the original selected step')
    for row in recovery:
        fid = row['frameId']
        leg = bisect_left(verified,fid)
        require(started['frameId'] <= fid and fid not in verified and leg < len(edges)
                and (leg == len(ends) or fid < ends[leg]['arrivalFrameId']),
                'Recovery does not belong to an active directed edge')
    for e in ends:
        endpoint_release(e,parts,e['warmRequestId'])
    elapsed = max(observation_timestamp(f) for f in frames.values())-min(observation_timestamp(f) for f in frames.values())
    require(0 < elapsed <= seconds*1000, 'Recorded destination actions exceed the supervisor wall-time limit')
    return dict(wallTimeLimitSeconds=seconds, recordingLimitMiB=160, recordedBytes=run['recordedBytes'],
                legLimitMs=35000, dispatchLimitMs=150, holdMs=100, sourceSpanSeconds=elapsed/1000)


def directed_broker(folder, run, supervisor, edges, landmark_checkpoint, qualification, batch_count=None, max_legs=None,
                    open_queue=False, failed=False):
    """Bind the recorded RDP worker, addressed resident, time budget and both BetterGI peers to the original job."""
    broker = read(folder/'broker.json')
    jid = broker['jobId']
    require(re.fullmatch('[0-9a-fA-F-]{36}',jid), 'Malformed RDP job identity')
    result = read(folder/'jobs'/f'{jid}.result.json')
    job = read(folder/'jobs'/f'{jid}.job.json')
    require(result == {k:v for k,v in broker.items() if k not in ('jobFile','resultFile')}
            and job['jobId'] == jid and result.get('remoteDesktop') is True and result.get('success') is (not failed)
            and result.get('timedOut') is False and type(result.get('returnCode')) is int
            and (result['returnCode']!=0 if failed else result['returnCode']==0)
            and result['windowsSessionId'] == job['windowsSessionId'] == run['windowsSessionId'],
            'Original broker job did not complete in the addressed RDP session')
    argv = job['argv']
    def value(flag):
        """Extract one unambiguous command option in either supported argparse form."""
        matches = [v.split('=',1)[1] if '=' in v else argv[i+1] for i,v in enumerate(argv)
                   if v == flag or v.startswith(flag+'=')]
        require(len(matches) == 1, 'Missing or duplicate RDP job option '+flag)
        return matches[0]
    binding = value('--patrol-series-binding').split(':')
    batch_argv = [v for v in argv if v.split('=',1)[0] == '--warm-batch-count']
    require((not batch_argv if batch_count is None else value('--warm-batch-count') == str(batch_count)),
            'RDP broker batch budget differs from authorization')
    require(sum(v=='--warm-open-queue' for v in argv)==int(open_queue)
            and not any(v.startswith('--warm-open-queue=') for v in argv),'RDP open-queue authority differs')
    require(len(binding) == 5 and binding[0] == str(supervisor['rootPid']) and binding[2] == str(supervisor['childPid'])
            and all(re.fullmatch('[0-9a-f]{32}',binding[i]) for i in (1,3))
            and all(str(s['processId']) == binding[2] and s.get('instanceNonce') == binding[3] for s in run['segments'])
            and value('--rdp-session-id') == str(run['windowsSessionId'])
            and value('--hybrid-legs') == str(len(edges) if max_legs is None else max_legs)
            and value('--seconds') == str(supervisor['wallTimeLimitSeconds'])
            and Path(value('--warm-photo-plan')).resolve() == (folder/'photo-requests.json').resolve()
            and Path(value('--landmark-shadow')).resolve() == Path(landmark_checkpoint).resolve()
            and Path(value('--photo-qualification')).resolve() == Path(qualification).resolve(),
            'RDP job and captured process identity, objectives or budgets disagree')
    addressed = read(folder/'patrol.json.control.json')
    require(addressed.get('runId') == run['runId'] and addressed.get('command') ==
            ('stop' if run['endReason']=='userStop' else 'run'), 'Destination control addressed a different resident')
    shadow = value('--steering-shadow') if any(v.split('=',1)[0]=='--steering-shadow' for v in argv) else None
    return dict(jobId=jid,runnerPid=result['runnerProcessId'],windowsSessionId=result['windowsSessionId'],
                startedAtUtc=result['startedAtUtc'],endedAtUtc=result['endedAtUtc'],
                rootNonce=binding[1],childNonce=binding[3]), shadow


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


def validate_stop(folder, run, parts, specs, groups, index=1):
    """Prove the external operator stop targeted this run after a confirmed second-request step."""
    witness = read(folder/'operator-stop.json')
    marker = read(folder/'STOP')
    supervisor = read(folder/'launcher.json')
    control = read(folder/'patrol.json.control.json')
    first = groups[index][0]
    require(witness.get('version') == 1 and witness['mode'] == 'external-stop-drill'
            and witness['runId'] == run['runId'] == control['runId'] and control['command'] == 'stop'
            and witness['requestId'] == specs[index]['id'] and witness['nativeRequestId'] == first['nativeRequestId']
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
    result = dict(requestId=specs[index]['id'],firstAppliedNativeRequestId=first['nativeRequestId'],
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
                        qualification, authenticated_report=None, allow_incomplete=False, batch_plans=None):
    """Verify a complete handoff or report a separately verified operator-cancelled prefix."""
    run_path = Path(run_path)
    run = read(run_path)
    plan_path = run_path.parent/'photo-requests.json'
    plan_bytes = plan_path.read_bytes()
    plan = read(requests) if isinstance(requests,(str,Path)) else requests
    require(json.loads(plan_bytes) == plan, 'Recorded plan differs from externally declared requests')
    specs = check_plan(plan)
    edges = destination_edges(plan) if plan['version'] == 2 else None
    interrupted = run.get('endReason') == 'userStop'
    require(not allow_incomplete or batch_plans is not None or len(specs) == 2, 'Stop drill requires exactly two declared requests')
    admission = read(run_path.parent/'warm-launcher.json')
    opened=admission.get('openQueue') is True
    require((interrupted and allow_incomplete) or run.get('endReason') ==
            ('destinationQueueFinished' if opened else 'hybridLegLimit'), 'Unexpected resident end reason')
    head = LandmarkRecognizer.load(landmark_checkpoint)
    require(not opened or head.checkpoint_id==G4_SHA256,'Unexpected photographic authority for the open queue')
    require_qualified_observer(qualification,head)
    supervisor = read(run_path.parent/'launcher.json')
    batches = None
    require(batch_plans is not None or not admission.get('batchCount'), 'Multi-batch broker requires external batch intents')
    if batch_plans is not None:
        require(isinstance(batch_plans,list) and batch_plans and plan == batch_plans[0], 'Initial batch declaration differs')
        specs = [spec for p in batch_plans for spec in check_plan(p)]
        batches = read_batches(run_path.parent,batch_plans,plan_bytes,admission,run,interrupted)
        edges = batch_edges(batch_plans)
        if interrupted:
            stop_goal = batches[admission['stopInBatch']-1]
            specs = specs[:stop_goal['firstRequestOrdinal']]
            witness = read(run_path.parent/'operator-stop.json')
            require(witness.get('requestOrdinal') == len(specs) and witness.get('batchOrdinal') == stop_goal['batchOrdinal']
                    and witness.get('batchSha256') == stop_goal['batchSha256'],
                    'Operator stop differs from the predeclared successor batch and its first request')
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    require(admission.get('computer','').split('.')[0].upper() == 'SIREN' and admission['planSha256'] == plan_sha
            and supervisor.get('runId') == run['runId'] and supervisor.get('stopAtC') == 78
            and supervisor.get('windowsSessionId') == run['windowsSessionId'] and run['windowsSessionId'] > 0
            and all(type(supervisor.get(k)) is int and supervisor[k] > 0 for k in ('rootPid','childPid'))
            and supervisor['rootPid'] != supervisor['childPid'] and
            (interrupted or supervisor.get('verified') is True and supervisor.get('stopRequested') is False
             and supervisor.get('stopReason') is None), 'Handoff lacks its SIREN RDP supervisor and addressed lease')
    circuits = 0 if edges is not None else (specs[0]['circuits'] if interrupted else sum(r['circuits'] for r in specs))
    broker, shadow = directed_broker(run_path.parent,run,supervisor,edges,landmark_checkpoint,qualification,
                    admission['batchCount'] if batches else None,admission['maxLegs'] if batches else None,opened) if edges is not None else (None,None)
    report = audit(run_path,recordings,repository=repository,landmark_checkpoint=landmark_checkpoint,
                   minimum_circuits=circuits,destination_plan=plan if edges is not None else None,
                   destination_batches=batch_plans,shadow_checkpoint=shadow)
    if authenticated_report is not None:
        earlier = read(authenticated_report) if isinstance(authenticated_report,(str,Path)) else authenticated_report
        keys = ['passed','routeId','verifiedLegs','verifiedCircuits','landmarkShadow']
        if edges is not None:
            keys.extend(('directedLegs','steeringShadow'))
            if report['stationaryPhotoRetries'] or 'stationaryPhotoRetries' in earlier:
                keys.append('stationaryPhotoRetries')
            if report['releaseReissues'] or 'releaseReissues' in earlier:
                keys.append('releaseReissues')
        require(all(report[k] == earlier.get(k) for k in keys),
                'Supplied patrol audit differs from independent warm audit')
    require(report.get('passed') and report['routeId'] == STREET_PATROL_ROUTE and report['controllerLeases'] == 1
            and run['modelLoads'] == 1 and run.get('failedLeases') == 0 and run.get('goalChanges') == [],
            'Warm run lacks a single resident policy and stable route/goal')
    parts, events, decisions, recovery, receipts, frames = authority_parts(run,recordings,repository,edges is not None,bool(batches))
    clock = bridge_clock(parts)
    confirm_first = edges is not None and plan.get('confirmFirstArrival') is True
    request_events = [e for e in events if e['type'] not in ('warmBatchAccepted','warmQueueFinished')] if batches else events
    boundaries, completed = lifecycle(request_events,parts,specs,run['runId'],plan_sha,clock,interrupted,edges,confirm_first)
    rows, switches = attribute_actions(decisions,recovery,receipts,frames,specs,boundaries,completed,clock)
    if edges is not None:
        require({p.name for p in Path(photo_root).iterdir() if p.is_dir()} == {s['id'] for s in specs},
                'Unattributed or missing destination photo directory')
    photos = photo_proofs(photo_root,report,events,specs,boundaries,head,completed if edges is not None else None,confirm_first)
    require(all(p['complete'] for p in (photos[:-1] if interrupted else photos)), 'Declared photo objective is incomplete')
    stop = validate_stop(run_path.parent,run,parts,specs,rows,len(specs)-1 if batches else 1) if interrupted else None
    with (run_path.parent/'gpu.jsonl').open(encoding='utf-8') as stream:
        thermal = [json.loads(line) for line in stream]
    require(len(thermal) >= 2 and all(not t.get('error') and type(t.get('temperatureC')) in (int,float)
            and 0 < t['temperatureC'] < 78 for t in thermal), 'Missing or unsafe GPU telemetry during handoff')
    summaries = []
    extra = {}
    if batches:
        continuations = verify_batch_events(events,batches,rows,frames,clock,specs,interrupted,[*decisions,*recovery])
        for b in continuations:
            switch, = [s for s in switches if s['newRequestId'] == b['newRequestId']]
            b.update(dispatchGapMs=switch['dispatchGapMs'],oldLastDispatchTicks=switch['oldLast']['lastStepTicks'],
                     newFirstDispatchTicks=switch['newFirst']['firstDispatchTicks'])
        if interrupted:
            for b in continuations:
                require(b['publicationQpc']['afterTicks'] <= stop['addressedStopToRelease']['beforeTicks'],
                        'A successor batch was staged after the addressed operator stop')
        extra.update(batchContinuations=continuations,batchCount=admission['batchCount'],maxLegs=admission['maxLegs'],
                     publishedBatches=len(batches),admittedBatches=1+sum(b['status']=='accepted' for b in continuations))
        if opened:
            from audit_open_queue import verify_open_queue
            extra['openQueue']=verify_open_queue(run_path.parent,admission,batches,parts,events,rows,frames,clock,
                                                 terminal_release(parts,rows),interrupted)
    if edges is not None:
        budgets = directed_controls(run,supervisor,parts,events,decisions,recovery,receipts,frames,edges,clock)
        samples = [datetime.fromisoformat(t['atUtc']) for t in thermal]
        start, end = (datetime.fromisoformat(broker[k]) for k in ('startedAtUtc','endedAtUtc'))
        require(start < end and samples[0] <= start and -6 < (end-samples[-1]).total_seconds() < 6 and
                all(a.tzinfo and b.tzinfo and 0 < (b-a).total_seconds() <= 6 for a,b in zip(samples,samples[1:])),
                'Destination thermal samples do not cover the active broker job')
        if interrupted:
            require(stop.get('addressedStopToRelease'), 'Missing addressed operator-stop QPC bracket')
        extra.update(mode='destinations',start=plan['start'],directedLegs=report['directedLegs'],budgets=budgets,
                     stationaryPhotoRetries=report['stationaryPhotoRetries'],releaseReissues=report['releaseReissues'],
                     thermalSamples=len(samples),verifiedRouteSeconds=report['verifiedRouteSeconds'],rdpJob=broker)
        start_event, = [e for e in events if e['type'] == 'hybridStartVerified']
        request_start = start_event['atMs']
    for i,(spec,group,photo) in enumerate(zip(specs,rows,photos)):
        ages = [a['sourceAgeMs'] for a in group]
        summaries.append(dict(id=spec['id'],name=spec['name'],actions=len(group),photos=photo,
                              first=group[0],last=group[-1],medianSourceAgeMs=statistics.median(ages),maximumSourceAgeMs=max(ages)))
        if edges is not None:
            planned = [edge for edge in edges if edge[2] == i+1]
            legs = [leg for leg in report['directedLegs'] if leg['destinationOrdinal'] == i+1]
            summaries[-1].update(destination=spec['destination'],start=planned[0][0],plannedLegs=len(planned),
                                 verifiedLegs=len(legs),complete=i<len(completed),
                                 gpuEvaluations=sum(d.get('warmRequestId')==spec['id'] for d in decisions),
                                 modelAppliedActions=sum(receipts[a['nativeRequestId']]['modelId']=='open-p2p' for a in group))
            if i < len(completed):
                done_at = observation_timestamp(frames[completed[i]['frameId']])
                summaries[-1]['navigationAndPhotoSeconds'] = (done_at-request_start)/1000
                request_start = done_at
    result_status='operator-stopped-prefix' if interrupted else 'qualified'
    if opened and not interrupted:
        reason=extra['openQueue']['outcome']
        result_status={'gameplayTargetReached':'runtime-target-achieved','operatorFinish':'operator-finished',
                       'batchLimitReached':'capacity-closed','legLimitReached':'capacity-closed'}[reason]
    return dict(version=plan['version'],passed=result_status not in ('operator-stopped-prefix','capacity-closed'),status=result_status,
                stopVerified=interrupted,stop=stop,modelLoads=1,controllerLeases=1,runId=run['runId'],
                verifiedLegs=report['verifiedLegs'],verifiedCircuits=report['verifiedCircuits'],
                requests=summaries,clock=clock,handoffs=switches,**({'handoff':switches[0]} if len(switches)==1 else {}),
                terminalReleaseAtMs=terminal_release(parts,rows),
                peakGpuTemperatureC=max(t['temperatureC'] for t in thermal),
                windowsSessionId=run['windowsSessionId'],rootPid=supervisor['rootPid'],childPid=supervisor['childPid'],
                **extra)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('run','recordings','photo-root','requests','landmark-checkpoint','qualification','output'):
        parser.add_argument('--'+flag, type=Path, required=True)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--allow-incomplete', action='store_true')
    parser.add_argument('--batch-intent',type=Path,action='append',
                        help='Walking successor .intent.json files in order. The audit reads the terminal finish separately.')
    args = vars(parser.parse_args())
    args['run_path'] = args.pop('run')
    intents = args.pop('batch_intent')
    if intents or read(args['run_path'].parent/'warm-launcher.json').get('openQueue') is True:
        args['batch_plans'] = [read(args['requests']),*(read(p)['plan'] for p in (intents or []))]
    destination = args.pop('output')
    result = audit_photo_handoff(**args)
    with destination.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(result['status'],destination)
