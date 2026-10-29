"""Run two to four named photo requests on one pinned SIREN RDP lease and verify every handoff."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import time
import uuid

import run_rdp_patrol as patrol
from run_patrol_series import SeriesGuard
from hybrid_routes import PATROL_STATIONS, itinerary_legs


def options(argv=None):
    """Accept a bounded sequence of named goals and reuse the single-patrol bounds and local assets."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--request', action='append', nargs='+', metavar='VALUE',
                      help='Repeat two to four times with NAME CIRCUITS STATION [STATION...]')
    mode.add_argument('--destination', action='append', nargs=2, metavar=('NAME', 'STATION'),
                      help='Walk the shortest surveyed path and photograph STATION. Repeat two to four times.')
    parser.add_argument('--start-station', choices=PATROL_STATIONS,
                        help='Required native start location for destination requests (default stair-front)')
    parser.add_argument('--confirm-first-arrival', action='store_true',
                        help='Require two separate qualified views at the first requested destination')
    map_mode = parser.add_mutually_exclusive_group()
    map_mode.add_argument('--inspect-junction-map', action='store_true',
                        help='Inspect the map at the junction on the same lease before walking to the west lamp')
    map_mode.add_argument('--recover-junction-map', action='store_true', help='Close the positively recognized map of a proven interrupted inspection')
    parser.add_argument('--map-owner-from', type=Path, help='Sealed owner or verified idle child-replacement lineage')
    parser.add_argument('--map-failure',type=Path,help='Original interrupted inspection folder, required for recovery')
    parser.add_argument('--map-passive',type=Path,help='Independent original passive map capture folder, required for recovery')
    parser.add_argument('--stop-drill', action='store_true',
                        help='For a two-request plan, exercise the external STOP file after a dispatch in request two')
    args = patrol.options(argv, parser, warm=True)
    try:
        requests = []
        if args.destination:
            for name, station in args.destination:
                requests.append(dict(id=uuid.uuid4().hex, name=name, destination=station, targets=[station]))
            args.plan = dict(version=2, mode='destinations', start=args.start_station or 'stair-front', requests=requests)
            if args.confirm_first_arrival:
                args.plan['confirmFirstArrival'] = True
        else:
            if args.start_station or args.confirm_first_arrival:
                raise ValueError('--start-station and --confirm-first-arrival are only valid with --destination')
            for name, circuits, *targets in args.request:
                requests.append(dict(id=uuid.uuid4().hex, name=name, targets=targets, circuits=int(circuits)))
            args.plan = dict(version=1, requests=requests)
        from warm_photo_requests import validate_plan
        validate_plan(args.plan)
        map_visit = args.inspect_junction_map or args.recover_junction_map
        if args.recover_junction_map != bool(args.map_failure and args.map_passive) or bool(args.map_failure)!=bool(args.map_passive):
            raise ValueError('Recovery requires both the original failure and the subsequent passive map observation')
        if map_visit != bool(args.map_owner_from) or (map_visit and (
                not args.destination or args.plan['start'] != 'sidewalk-junction' or args.stop_drill
                or [r['destination'] for r in requests] != ['west-lamp','sidewalk-junction'])):
            raise ValueError('Map inspection requires a pinned owner and exactly junction to lamp to junction')
        if args.stop_drill and len(requests) != 2:
            raise ValueError('The request-two stop drill requires exactly two requests')
        args.circuits = 0 if args.destination else sum(r['circuits'] for r in requests)
        if args.destination:
            args.destination_legs = len(itinerary_legs(args.plan['start'], [r['destination'] for r in requests]))
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    return args


class WarmGuard(SeriesGuard):
    """Apply existing ownership/deadline/STOP controls and optionally exercise that same STOP path."""
    def __init__(self, folder, args):
        super().__init__(folder/'STOP', args.seconds)
        self.folder = folder
        self.drill = args.stop_drill
        self.second_id = args.plan['requests'][1]['id']
        self.stop_observation = None

    def stop_reason(self):
        """Only create the drill marker after observing an applied action in this resident's second request."""
        reason = super().stop_reason()
        if reason or not self.drill:
            return reason
        try:
            try:
                raw = (self.folder/'station-photos'/'warm-status.json').read_bytes()
            except (FileNotFoundError, PermissionError):
                return None
            status = json.loads(raw)
            if (status.get('version') != 1 or status.get('activeOrdinal') != 2
                    or status.get('activeRequestId') != self.second_id
                    or not status.get('activeFirstAppliedRequestId')):
                return None
            run_id = patrol.pin_resident(self.folder)
            native_id = status['activeFirstAppliedRequestId']
            frame_id = status.get('activeFirstAppliedFrameId')
            if (not run_id or run_id != status.get('runId') or not isinstance(native_id, str)
                    or not re.fullmatch('[0-9a-f]{32}', native_id) or type(frame_id) is not int or frame_id < 1):
                raise ValueError('Applied request is not bound to the addressed resident')
            if patrol.addressed_control(self.folder/'patrol.json.control.json', run_id)['command'] != 'run':
                return None
            proof = dict(version=1, mode='external-stop-drill', runId=run_id, requestId=self.second_id,
                         nativeRequestId=native_id, frameId=frame_id, observedAtMonotonicNs=time.monotonic_ns())
            # Exclusive creation distinguishes the exercise from an actual operator already cancelling this run.
            with self.stop_file.open('x', encoding='utf-8') as marker:
                json.dump(proof, marker)
            proof['stopFileCreatedAtMonotonicNs'] = time.monotonic_ns()
            self.stop_observation = proof
        except FileExistsError:
            pass
        except (OSError, KeyError, ValueError, TypeError):
            self.reason = 'invalidWarmStopEvidence'
        return super().stop_reason()


def audit_result(args, folder, guard):
    """Check the exact addressed lease, all original request evidence and the requested completion mode."""
    from audit_photo_handoff import audit_photo_handoff
    state = json.loads((folder/'launcher.json').read_bytes())
    broker = json.loads((folder/'broker.json').read_bytes())
    resident = json.loads((folder/'patrol.json').read_bytes())
    if (not state['runId'] or state['runId'] != resident['runId'] or not broker.get('success')
            or broker.get('returnCode') != 0 or broker.get('timedOut')):
        raise RuntimeError('Warm request broker or resident identity did not finish cleanly')
    proof = guard.stop_observation
    if args.stop_drill:
        if (not proof or state.get('stopReason') != 'seriesOperatorStop' or guard.reason != 'seriesOperatorStop'
                or state.get('stopRequested') is not True or state.get('stopCommandPublished') is not True
                or proof['runId'] != state['runId']
                or state.get('stopRequestedAtMonotonicNs', 0) < proof['stopFileCreatedAtMonotonicNs']
                or resident.get('endReason') != 'userStop'
                or patrol.addressed_control(folder/'patrol.json.control.json', state['runId'])['command'] != 'stop'):
            raise RuntimeError('Expected a verified operator stop of the second request')
        witness = dict(proof, addressedStopAtMonotonicNs=state['stopRequestedAtMonotonicNs'])
        if 'addressedStopQpc' in state:
            witness['addressedStopQpc'] = state['addressedStopQpc']
        patrol.atomic_json(folder/'operator-stop.json', witness)
        authenticated = None
    else:
        if (state.get('verified') is not True or state.get('stopReason') or state.get('stopRequested')
                or guard.stop_reason()
                or patrol.addressed_control(folder/'patrol.json.control.json', state['runId'])['command'] != 'run'):
            raise RuntimeError('Warm request ownership or prior route audit failed')
        authenticated = json.loads((folder/'audit.json').read_bytes())
    extra = {}
    if getattr(args, 'batches', None):
        from destination_batch_sender import admitted_plans
        extra['batch_plans'] = admitted_plans(folder)
    audit = audit_photo_handoff(folder/'patrol.json', folder/'patrol-recording', repository=patrol.ROOT,
        photo_root=folder/'station-photos', requests=args.plan, landmark_checkpoint=args.landmark_shadow,
        qualification=args.photo_qualification, authenticated_report=authenticated, allow_incomplete=args.stop_drill, **extra)
    patrol.atomic_json(folder/'handoff-audit.json', audit)
    if args.stop_drill:
        if audit.get('stopVerified') is not True or audit.get('passed') is not False:
            raise RuntimeError('Independent audit did not verify the stop drill')
    elif getattr(args,'open_queue',False) and audit.get('status')=='capacity-closed':
        if audit.get('passed') is not False or audit['openQueue']['outcome'] not in ('batchLimitReached','legLimitReached'):
            raise RuntimeError('Open queue cap closure differs from the independent audit')
    elif audit.get('passed') is not True:
        raise RuntimeError('Independent audit did not verify the warm handoff')
    return audit


def run(args, folder, *, guard_type=WarmGuard):
    """Submit exactly one pinned resident job and persist the supervisor result even on refusal."""
    plan_path = folder/'photo-requests.json'
    with plan_path.open('x', encoding='utf-8') as output:
        json.dump(args.plan, output, indent=2)
    args.warm_photo_plan = plan_path.resolve()
    guard = guard_type(folder, args)
    recover_map = getattr(args, 'recover_junction_map', False)
    map_visit = getattr(args, 'inspect_junction_map', False) or recover_map
    if map_visit:
        if getattr(args,'open_queue',False):
            from map_owner import evidence, replacement
            receipt, _ = evidence(args.map_owner_from, 'map-owner-lineage.json')
            expected = replacement(receipt['prior'], args.map_owner_from.resolve().parent)
            if receipt != expected or not expected.get('protectedGame') or not expected.get('priorLineageSha256'):
                raise ValueError('A map queue requires the verified R59 replacement and protected game')
            guard.required_identity = expected['identity']
        else:
            from map_owner import load_map_owner
            guard.required_identity = load_map_owner(args.map_owner_from)
            receipt=json.loads(args.map_owner_from.read_bytes())
        with (folder/'map-required-owner.json').open('x',encoding='utf-8') as out:
            json.dump(guard.required_identity,out,indent=2)
        if receipt.get('protectedGame'):
            with (folder/'map-required-game.json').open('x',encoding='utf-8') as out:
                json.dump(receipt['protectedGame'],out,indent=2)
        if recover_map:
            from audit_map_recovery import verify_failed_map_origin
            predecessor=Path(receipt['prior'])
            if predecessor.name!='map-owner-lineage.json':
                raise ValueError('Map recovery requires a replacement descended from the proven interrupted child')
            origin=verify_failed_map_origin(args.map_failure.resolve(),args.map_passive.resolve(),predecessor,patrol.ROOT)
            with (folder/'map-recovery-origin.json').open('xb') as out:
                out.write(json.dumps(origin,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8'))
    requests = args.plan['requests']
    planned = [dict(oldRequestId=old['id'], newRequestId=new['id']) for old, new in zip(requests, requests[1:])]
    summary = dict(status='running', computer=socket.gethostname(), stopFile=str(guard.stop_file),
                   stopDrill=args.stop_drill, planSha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                   plannedHandoffs=planned, verifiedHandoffs=[])
    if getattr(args, 'batches', None):
        summary.update(batchCount=args.batches, maxLegs=args.destination_legs, manualSubmission=args.manual,
                       stopInBatch=args.stop_in_batch, stopRule='first-request-first-applied' if args.stop_drill else None)
    if getattr(args,'open_queue',False):
        from destination_batch_sender import encode,exclusive_bytes
        from destination_queue_policy import BALANCED
        owner_raw = args.owner_from.read_bytes()
        owner = json.loads(owner_raw)
        if owner.get('status') not in ('completed','stopVerified') or set(owner.get('identity') or {})!={'root','child'}:
            raise ValueError('Open queue requires a sealed historical RDP owner')
        if guard.required_identity is None:
            guard.required_identity = owner['identity']
        elif owner['identity'] != guard.required_identity:
            raise ValueError('The sealed destination queue owner differs from the verified map owner')
        owner_sha = hashlib.sha256(owner_raw).hexdigest()
        planner = dict(version=1,mode='manual' if args.manual else BALANCED,
                       targetGameplaySeconds=args.target_gameplay_seconds,goalsPerBatch=4)
        policy = dict(**planner,maxBatches=args.batches,maxLegs=args.destination_legs,initialPlanSha256=summary['planSha256'],
                      requiredOwnerManifestSha256=owner_sha)
        raw = encode(policy)
        exclusive_bytes(folder/'required-owner.json',owner_raw)
        exclusive_bytes(folder/'queue-policy.json',raw)
        summary.update(openQueue=True,planner=planner,requiredOwnerManifestSha256=owner_sha,queuePolicySha256=hashlib.sha256(raw).hexdigest())
    print(f'Warm request evidence: {folder}\nTo cancel, create: {guard.stop_file}', flush=True)
    patrol.atomic_json(folder/'warm-launcher.json', summary)
    try:
        if os.name != 'nt' or summary['computer'].split('.')[0].upper() != 'SIREN':
            raise RuntimeError('Warm requests require the SIREN Windows host')
        if guard.stop_reason():
            raise RuntimeError(guard.reason)
        try:
            patrol.run(args, folder, series=guard)
        except RuntimeError:
            if not args.stop_drill or not guard.stop_observation or guard.reason != 'seriesOperatorStop':
                raise
        if hashlib.sha256(plan_path.read_bytes()).hexdigest() != summary['planSha256']:
            raise RuntimeError('The request plan changed during the lease')
        audit = audit_result(args, folder, guard)
        handoffs = audit['handoffs']
        audited = [dict(oldRequestId=row['oldRequestId'], newRequestId=row['newRequestId']) for row in handoffs]
        if getattr(args, 'batches', None):
            from destination_batch_sender import admitted_plans
            requests = [r for plan in admitted_plans(folder) for r in plan['requests']]
            if args.stop_drill:
                requests = requests[:guard.stop_observation['requestOrdinal']]
            planned = [dict(oldRequestId=a['id'], newRequestId=b['id']) for a,b in zip(requests,requests[1:])]
            summary['plannedHandoffs'] = planned
        if audited != planned:
            raise RuntimeError('Audited handoffs differ from the prescribed request sequence')
        summary['verifiedHandoffs'] = [dict(pair, dispatchGapMs=row['dispatchGapMs'])
                                       for pair, row in zip(audited, handoffs)]
        summary['status'] = 'stopVerified' if args.stop_drill else 'completed'
        if getattr(args,'open_queue',False):
            summary.update(auditStatus=audit['status'],openQueueResult=audit['openQueue'])
            if audit['status']=='capacity-closed':
                summary['status']='capacityClosed'
    except (Exception, KeyboardInterrupt) as exc:
        summary.update(status='stopped', reason=str(exc) or 'interrupted')
    finally:
        guard.finished.set()
        summary['identity'] = guard.identity
        if map_visit and summary['status']=='completed':
            # The map replay reads the final owner; expose it before publishing a completed supervisor.
            patrol.atomic_json(folder/'warm-launcher.json',dict(summary,status='auditingMap'))
            audit_map_result(args, folder, summary)
        patrol.atomic_json(folder/'warm-launcher.json', summary)
    return summary


def audit_map_result(args, folder, summary):
    """Seal the separate map replay only after the requested walking or queue handoff audit succeeds."""
    key = 'mapRecoveryVerified' if getattr(args,'recover_junction_map',False) else 'mapInspectionVerified'
    try:
        from audit_map_inspection import audit_map
        auditor=audit_map
        if key == 'mapRecoveryVerified':
            from audit_map_recovery import audit_recovery_visit
            auditor = audit_recovery_visit
        proof = auditor(folder,args.map_owner_from,args.landmark_shadow,args.photo_qualification,patrol.ROOT)
        if proof.get('passed') is not True:
            raise ValueError('Map-to-lamp audit did not pass')
        patrol.atomic_json(folder/'map-audit.json',proof)
        summary[key]=True
    except Exception as exc:
        summary.update(status='stopped',reason='Map audit failed: '+str(exc))
        summary[key]=False


def main():
    """Use a fresh exclusive folder for every completed, stopped or refused trial."""
    args = options()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = args.evidence_root.resolve()/f'warm-{stamp}-{uuid.uuid4().hex[:12]}'
    folder.mkdir(parents=True, exist_ok=False)
    summary = run(args, folder)
    print(summary.get('reason', summary['status']))
    return int(summary['status'] not in ('completed', 'stopVerified'))


if __name__ == '__main__':
    raise SystemExit(main())
