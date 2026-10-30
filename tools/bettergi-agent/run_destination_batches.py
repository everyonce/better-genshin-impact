"""Launch one bounded minimized SIREN patrol or submit the next destination batch to its active lease."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import sys
import threading
import time
import uuid

from destination_batch_sender import (admitted_plans, create_plan, exclusive_bytes, encode, qualification_goals,
                                     read_json, submit, witness_for)
from hybrid_routes import PATROL_STATIONS, itinerary_legs
from destination_queue_limits import ENDURANCE, STANDARD
import run_rdp_patrol as patrol
from run_patrol_series import SeriesGuard
import run_warm_photo_requests as warm


def launch_options(argv):
    """Pin the lease bounds and the initial goals only; later request IDs do not exist at launch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batches', type=int, required=True)
    parser.add_argument('--leg-limit', type=int, required=True)
    parser.add_argument('--start-station', choices=PATROL_STATIONS, required=True)
    parser.add_argument('--manual', action='store_true', help='Wait for the standalone submit command for every successor')
    parser.add_argument('--open-queue',action='store_true',help='Require an explicit finish in the next shared queue slot')
    parser.add_argument('--target-gameplay-seconds',type=int,help='Finish after this span of positively witnessed native dispatches')
    parser.add_argument('--owner-from',type=Path,help='Sealed prior launcher/series manifest with the original RDP owner')
    parser.add_argument('--inspect-junction-map', action='store_true', help='Inspect the junction map before the first automatic queue destination')
    parser.add_argument('--map-owner-from', type=Path, help='Verified R59 replacement receipt for the same RDP pair and protected game')
    parser.add_argument('--destination', nargs=2, action='append', metavar=('NAME','STATION'), help='Initial batch goals')
    parser.add_argument('--stop-in-batch', type=int, help='Stop after the first applied action of this later batch')
    args = patrol.options(argv, parser, warm=True)
    limits = ENDURANCE if args.endurance else STANDARD
    if (not 2 <= args.batches <= limits.batches or not (2 if args.open_queue else 2*args.batches) <= args.leg_limit <= limits.legs
            or args.stop_in_batch is not None and not 2 <= args.stop_in_batch <= args.batches):
        parser.error(f'Use 2–{limits.batches} batches, a leg cap up to {limits.legs}, and an optional later stop batch.')
    if args.open_queue:
        if not args.owner_from or (args.target_gameplay_seconds is None) != args.manual or (
                args.target_gameplay_seconds is not None and not 1<=args.target_gameplay_seconds<args.seconds):
            parser.error('Open queues require --owner-from and either --manual or a gameplay target below the wall-time cap.')
    elif args.target_gameplay_seconds is not None or args.owner_from is not None:
        parser.error('--target-gameplay-seconds and --owner-from require --open-queue.')
    try:
        destinations = args.destination or qualification_goals(args.start_station,1,0)
        args.plan = create_plan(args.start_station,destinations)
        if args.inspect_junction_map != bool(args.map_owner_from) or (args.inspect_junction_map and (
                not args.open_queue or args.manual or args.stop_in_batch is not None
                or args.start_station != 'sidewalk-junction'
                or [r['destination'] for r in args.plan['requests']] != ['west-lamp','sidewalk-junction'])):
            raise ValueError('A map visit requires both map flags, an automatic open queue, and exactly junction to lamp to junction')
        legs = len(itinerary_legs(args.start_station,[r['destination'] for r in args.plan['requests']]))
        reserve = 0 if args.open_queue else (2 if args.manual else 7)*(args.batches-1)
        if legs+reserve > args.leg_limit:
            raise ValueError('The leg limit cannot accommodate the declared batch count')
    except ValueError as exc:
        parser.error(str(exc))
    args.destination_legs, args.circuits, args.stop_drill = args.leg_limit, 0, args.stop_in_batch is not None
    return args


def verify_manual_lease(folder, status):
    """Match the addressed resident, deadline and live minimized process pair to the original submitted broker job."""
    jobs = list((folder/'jobs').glob('*.job.json'))
    if len(jobs) != 1:
        raise ValueError('Missing unique pinned BetterGI job')
    job = read_json(jobs[0])
    binding, = [arg.split('=',1)[1] for arg in job['argv'] if arg.startswith('--patrol-series-binding=')]
    root_pid, root_nonce, child_pid, child_nonce, deadline = binding.split(':')
    if (time.monotonic_ns() >= int(deadline) or '--output' not in job['argv']
            or Path(job['argv'][job['argv'].index('--output')+1]).resolve() != folder/'patrol.json'):
        raise ValueError('Broker job expired or targets a different resident')
    # The original manifest owns the Windows session. The asynchronous progress file owns the live PID/command.
    manifest = read_json(folder/'patrol.json')
    progress = read_json(folder/'patrol.json.status.json')
    if (manifest.get('runId') != status['runId'] or manifest.get('windowsSessionId') != job['windowsSessionId']
            or manifest.get('mode') != 'resident-rdp' or manifest.get('status') != 'running'
            or manifest.get('modelLoads') != 1 or manifest.get('inputRequested') is not True
            or Path(manifest.get('controlFile','')).resolve() != folder/'patrol.json.control.json'
            or progress.get('runId') != status['runId'] or progress.get('childProcessId') != int(child_pid)
            or progress.get('childReplaced') is not False or progress.get('state') not in ('running','waitingForWorld','observing')
            or progress.get('command') != 'run' or progress.get('requestedCommand') != 'run' or progress.get('controlError')
            or type(progress.get('updatedAtUnixMs')) is not int
            or not 0 <= time.time()*1000-progress['updatedAtUnixMs'] <= 5000):
        raise ValueError('The active resident manifest, child process or fresh controller status differs from the pinned job')
    lifecycle = patrol.control_module()
    discovered = lifecycle.discover()
    if discovered['unavailable']:
        raise ValueError('Incomplete BetterGI discovery while submitting destinations')
    root, = [s for s in discovered['instances'] if s['processId'] == int(root_pid) and s['instanceNonce'] == root_nonce]
    child, = [s for s in discovered['instances'] if s['processId'] == int(child_pid) and s['instanceNonce'] == child_nonce]
    lifecycle.require_role(root,'Primary')
    lifecycle.require_role(child,'ChildSession')
    lifecycle._require_connected_root(root,child)
    if (root.get('childWindowMinimized') is not True or child.get('windowsSessionId') != job['windowsSessionId']
            or child.get('agentStreamRunning') is not True or child.get('runtimeRunning') is not True):
        raise ValueError('The pinned minimized RDP input lease is no longer active')


class BatchGuard(SeriesGuard):
    """Send externally chosen work only after an applied native witness in the preceding active batch."""
    def __init__(self, folder, args):
        super().__init__(folder/'STOP',args.seconds)
        self.folder, self.args = folder, args
        self.stop_observation = None

    def admit(self, lifecycle, root, child):
        """Retain the independent identity and thermal monitors while polling sparse status promptly."""
        super().admit(lifecycle,root,child)
        threading.Thread(target=self.monitor_batches,daemon=True).start()

    def monitor_batches(self):
        """Poll only the small warm status file; leave the GPU watchdog on its original cadence."""
        last_batch = 0
        while not self.finished.wait(.1) and not super().stop_reason():
            try:
                try:
                    status = read_json(self.folder/'station-photos'/'warm-status.json')
                except (FileNotFoundError,PermissionError):
                    continue
                b = status['batchOrdinal']
                if status.get('complete') or not status.get('activeFirstAppliedRequestId') or b <= last_batch:
                    continue
                if self.args.stop_in_batch == b:
                    plans = admitted_plans(self.folder)
                    witness = witness_for(self.folder,status,plans)
                    ordinal = 1+sum(len(p['requests']) for p in plans[:b-1])
                    if not witness or status['activeOrdinal'] != ordinal:
                        raise ValueError('Missed the declared first-request STOP witness')
                    proof = dict(version=1,mode='external-stop-drill',runId=status['runId'],requestId=witness['requestId'],
                                 nativeRequestId=witness['nativeRequestId'],frameId=witness['frameId'],batchOrdinal=b,
                                 batchSha256=status['batchSha256'],requestOrdinal=ordinal,observedAtMonotonicNs=time.monotonic_ns())
                    # Use the same external STOP marker and addressed control path as an operator cancellation.
                    exclusive_bytes(self.stop_file, encode(proof))
                    proof['stopFileCreatedAtMonotonicNs'] = time.monotonic_ns()
                    self.stop_observation = proof
                    return
                if not self.args.manual and (b < self.args.batches or getattr(self.args,'open_queue',False)):
                    if submit(self.folder,b+1) is None:
                        continue
                last_batch = b
            except FileExistsError:
                if not self.stop_file.exists():
                    self.reason = 'concurrentBatchSender'
                return
            except (OSError, KeyError, TypeError, ValueError) as exc:
                self.reason = 'invalidBatchPublication: ' + str(exc)
                return


def main(argv=None):
    """The two commands run in separate processes and never require foregrounding BetterGI."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ('launch','submit','finish'):
        print('Usage: run_destination_batches.py {launch|submit|finish} --help',file=sys.stderr)
        return 2
    operation = argv.pop(0)
    if operation == 'launch':
        args = launch_options(argv)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        folder = args.evidence_root.resolve()/f'batches-{stamp}-{uuid.uuid4().hex[:12]}'
        (folder/'batches').mkdir(parents=True,exist_ok=False)
        summary = warm.run(args,folder,guard_type=BatchGuard)
        print(summary.get('reason',summary.get('auditStatus',summary['status'])),flush=True)
        return int(summary['status'] not in ('completed','stopVerified'))
    finish = operation=='finish'
    parser = argparse.ArgumentParser(description='Submit named destinations or finish an addressed manually supplied lease.')
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--batch',type=int,default=2,help='Explicit successor ordinal. Defaults to the first successor, 2.')
    if not finish:
        parser.add_argument('--destination',action='append',nargs=2,required=True,metavar=('NAME','STATION'))
    parser.add_argument('--wait-seconds',type=int,default=60)
    args = parser.parse_args(argv)
    if (not 0 <= args.wait_seconds <= 600 or not 2 <= args.batch <= ENDURANCE.batches+int(finish)
            or not finish and not 2 <= len(args.destination) <= 4):
        parser.error('Use 2–4 destinations or an explicit finish, and a wait of at most 600 seconds.')
    folder = args.folder.resolve()
    try:
        if os.name != 'nt' or socket.gethostname().split('.')[0].upper() != 'SIREN':
            raise ValueError('Submitting destinations requires the SIREN Windows host')
        if read_json(folder/'warm-launcher.json').get('manualSubmission') is not True:
            raise ValueError('This lease uses its own benchmark sender')
        deadline = time.monotonic()+args.wait_seconds
        while True:
            result = submit(folder,args.batch,getattr(args,'destination',None),verify_manual_lease,finish=finish)
            if result is not None:
                print(f'Published {operation} in destination slot {args.batch}',flush=True)
                return 0
            if time.monotonic() >= deadline:
                raise ValueError('No prior applied gameplay witness before the deadline')
            time.sleep(.1)
    except (OSError,KeyError,ValueError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
