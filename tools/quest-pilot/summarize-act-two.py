"""Summarize durable measured intervals; never call unclassified time productive gameplay."""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def main():
    rows = [json.loads(line) for line in (ROOT / 'artifacts/act-two-events.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    receipts, observations = {}, {}
    for row in rows:
        receipt = row.get('receipt') or (row.get('data') if row.get('type') == 'receipt' else None)
        if isinstance(receipt, dict) and receipt.get('id'):
            receipts[(receipt.get('session'), receipt['id'])] = receipt
        if row.get('type') == 'observation':
            value = row.get('data') or row.get('observation') or row
            if value.get('frameId') is not None:
                observations[(row.get('session') or value.get('session'), value['frameId'])] = value
    pipeline = Counter()
    for value in observations.values():
        for key, number in (value.get('timings') or {}).items():
            if key.endswith('Ms') and isinstance(number, (float, int)):
                pipeline[key] += number
    events, statuses, requests = Counter(), Counter(), defaultdict(list)
    key_hold_ms = 0
    request_ms = 0
    pause_gap_ms = 0
    for receipt in receipts.values():
        details = receipt.get('details') or {}
        elapsed = details.get('elapsedMs') or 0
        request_ms += elapsed
        statuses[receipt.get('status')] += 1
        if receipt.get('timestamp'):
            requests[receipt.get('session')].append((receipt['timestamp'] - elapsed, receipt['timestamp'], receipt))
        for event in details.get('inputEvents') or []:
            events[event.get('type', 'unknown')] += 1
            if event.get('type') == 'key':
                key_hold_ms += event.get('durationMs') or 0
    now = int(time.time() * 1000)
    for session, sequence in requests.items():
        sequence.sort()
        for i, (start, end, receipt) in enumerate(sequence):
            result = (receipt.get('details') or {}).get('result') or {}
            if result.get('pauseVerified') or result.get('pausedInventory'):
                next_start = sequence[i+1][0] if i+1 < len(sequence) else end
                pause_gap_ms += max(0, next_start - end)
    timestamps = [v['timestamp'] for v in observations.values() if isinstance(v.get('timestamp'), (int, float))]
    report = {'asOfUnixMs': now, 'uniqueTerminalReceipts': len(receipts), 'receiptStatuses': statuses,
              'observationsPreserved': len(observations), 'observationPipelineMs': pipeline,
              'requestElapsedMs': request_ms, 'keyHoldBudgetMs': key_hold_ms,
              'verifiedPauseGapsBetweenRequestsMs': pause_gap_ms, 'eventCounts': events,
              'observationCoverageFirstUnixMs': min(timestamps) if timestamps else None,
              'observationCoverageLastUnixMs': max(timestamps) if timestamps else None,
              'limitations': ['Pipeline components overlap; do not sum them.',
                  'Key budgets exclude uninstrumented mouse holds and are not productive gameplay time.',
                  'Pause gaps count only proven pauses between requests within a session.',
                  'Decision, menus, loading, build/test, recovery and blocked gaps remain partially unclassified.',
                  'Root-directed requests are interventions; event types are not all physical actions.']}
    (ROOT / 'artifacts/act-two-timing-summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('uniqueTerminalReceipts', 'observationsPreserved', 'requestElapsedMs', 'keyHoldBudgetMs', 'verifiedPauseGapsBetweenRequestsMs')}))

if __name__ == '__main__':
    main()
