"""Run up to three audited street patrols on SIREN's existing minimized BetterGI RDP connection."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import threading
import time
import uuid

import run_rdp_patrol as patrol


def options(argv=None):
    """Reuse all existing launcher options; each batch keeps the ordinary 32-circuit and 600-second bounds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batches', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--series-seconds', type=int, default=1800, help='Whole-series input budget, 15 to 1800 seconds')
    parser.add_argument('--stop-file', type=Path, help='Create this file to stop the series (default: STOP in its folder)')
    args = patrol.options(argv, parser)
    if not 15 <= args.series_seconds <= 1800:
        parser.error('Set --series-seconds between 15 and 1800.')
    return args


class SeriesGuard:
    """Latch operator cancellation and pin the original Windows process, nonce and session pair."""
    def __init__(self, stop_file, seconds):
        self.stop_file = stop_file
        self.deadline_ns = time.monotonic_ns() + seconds * 1_000_000_000
        self.identity = None
        self.reason = None
        self.finished = threading.Event()
        self.last_proof = None

    def admit(self, lifecycle, root, child):
        """Admit the first authenticated pair and require an exact match at every subsequent launch."""
        def identity(status):
            return {key: status[key] for key in ('windowsSessionId', 'processId', 'instanceNonce')}
        pair = {'root': identity(root), 'child': identity(child)}
        if self.identity is not None and self.identity != pair:
            self.reason = 'seriesIdentityChanged'
            raise RuntimeError(self.reason)
        if self.identity is None:
            self.identity = pair
            self.last_proof = time.monotonic()
            # Status exchanges are read-only and can block while the desktop is busy.
            # Run them separately so they cannot delay the launcher's GPU/stop sampling.
            threading.Thread(target=self.watch_identity, args=(lifecycle, root, child), daemon=True).start()

    def watch_identity(self, lifecycle, root, child):
        """Refresh both original authenticated endpoints without touching their tasks or windows."""
        while not self.finished.wait(4):
            try:
                current_root, current_child = lifecycle.refresh(root), lifecycle.refresh(child)
                lifecycle.require_role(current_child, 'ChildSession')
                lifecycle._require_connected_root(current_root, current_child)
                if current_root.get('uiStatus') != 'current' or current_root.get('childWindowMinimized') is not True:
                    raise RuntimeError('Minimized RDP window lost')
                self.last_proof = time.monotonic()
            except Exception:
                self.reason = self.reason or 'seriesIdentityUnavailable'
                return

    def binding(self):
        """Send one bounded broker argument; the resident verifies the pair before taking any input lease."""
        root, child = self.identity['root'], self.identity['child']
        return f"{root['processId']}:{root['instanceNonce']}:{child['processId']}:{child['instanceNonce']}:{self.deadline_ns}"

    def stop_reason(self):
        """Do not resume on a recovered identity, removed stop file or transient monitoring failure."""
        if self.reason:
            return self.reason
        try:
            self.stop_file.stat()
        except FileNotFoundError:
            pass
        except OSError:
            self.reason = 'seriesStopFileUnavailable'
        else:
            self.reason = 'seriesOperatorStop'
        if time.monotonic_ns() >= self.deadline_ns:
            self.reason = self.reason or 'seriesTimeLimit'
        if self.last_proof is not None and time.monotonic() - self.last_proof >= 15:
            self.reason = self.reason or 'seriesIdentityTimeout'
        return self.reason


def run_series(args, folder):
    """Start each new batch only after its predecessor's isolated lease and requested circuits have passed audit."""
    stop = args.stop_file.resolve() if args.stop_file else folder/'STOP'
    guard = SeriesGuard(stop, args.series_seconds)
    summary = dict(status='running', computer=socket.gethostname(), requestedBatches=args.batches,
                   circuitsPerBatch=args.circuits, seriesSeconds=args.series_seconds, stopFile=str(stop),
                   verifiedBatches=0, verifiedCircuits=0, verifiedLegs=0, batches=[])
    path = folder/'series.json'
    patrol.atomic_json(path, summary)
    print(f'Series evidence: {folder}\nTo cancel, create: {stop}', flush=True)
    try:
        if os.name != 'nt' or summary['computer'].split('.')[0].upper() != 'SIREN':
            raise RuntimeError('Patrol series are restricted to the SIREN Windows host')
        for number in range(1, args.batches+1):
            if guard.stop_reason():
                raise RuntimeError(guard.reason)
            batch = folder/f'batch-{number:02d}'
            batch.mkdir(exist_ok=False)
            row = dict(number=number, directory=str(batch), status='running')
            summary['batches'].append(row)
            patrol.atomic_json(path, summary)
            try:
                patrol.run(args, batch, series=guard)
                state = json.loads((batch/'launcher.json').read_bytes())
                audit = json.loads((batch/'audit.json').read_bytes())
                if (state.get('verified') is not True or state.get('stopReason') or state.get('stopRequested') is not False
                        or audit.get('passed') is not True or audit.get('routeId') != patrol.STREET_PATROL_ROUTE
                        or audit.get('controllerLeases') != 1 or audit.get('partialPatrolLegs') != []
                        or audit.get('verifiedLegs') != 4*args.circuits or audit.get('verifiedCircuits') != args.circuits):
                    raise RuntimeError('Batch failed its route, single-owner or completion audit')
                if patrol.addressed_control(batch/'patrol.json.control.json', state['runId'])['command'] != 'run':
                    raise RuntimeError('Operator stopped or paused the addressed batch')
                row.update(status='verified', runId=state['runId'], circuits=audit['verifiedCircuits'], legs=audit['verifiedLegs'])
                summary['verifiedBatches'] += 1
                summary['verifiedCircuits'] += row['circuits']
                summary['verifiedLegs'] += row['legs']
            except (Exception, KeyboardInterrupt) as exc:
                row.update(status='stopped', error=str(exc) or 'interrupted')
                if (batch/'launcher.json').is_file():
                    batch_state = json.loads((batch/'launcher.json').read_bytes())
                    row.update(runId=batch_state.get('runId'), stopReason=batch_state.get('stopReason'),
                               stopRequested=batch_state.get('stopRequested'))
                    if row['stopReason']:
                        raise RuntimeError(row['stopReason']) from exc
                raise
            if guard.stop_reason():
                raise RuntimeError(guard.reason)
        summary['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        summary.update(status='stopped', reason=guard.reason or str(exc) or 'interrupted')
    finally:
        guard.finished.set()
        summary['identity'] = guard.identity
        patrol.atomic_json(path, summary)
    return summary


def main():
    """Reserve an exclusive evidence directory and expose the cumulative result and cancellation file."""
    args = options()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = args.evidence_root.resolve() / f'series-{stamp}-{uuid.uuid4().hex[:12]}'
    folder.mkdir(parents=True, exist_ok=False)
    summary = run_series(args, folder)
    print(f"{summary['status']}: {summary['verifiedBatches']}/{args.batches} batches, {summary['verifiedCircuits']} verified circuits")
    return int(summary['status'] != 'completed')


if __name__ == '__main__':
    raise SystemExit(main())
