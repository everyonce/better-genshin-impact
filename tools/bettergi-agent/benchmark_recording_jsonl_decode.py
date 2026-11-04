"""Compare the committed and working JSONL loaders on synthetic local evidence only."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import tracemalloc
import types

import policy_rgb_archive as current


def measure(module, root, repeats):
    """Measure wall time without tracing, then peak Python allocation separately."""
    times = []
    cpu_times = []
    for _ in range(repeats):
        gc.collect()
        cpu_start = time.process_time()
        start = time.perf_counter()
        rows, digest = module.read_recording_jsonl(root, 'events.jsonl')
        times.append(time.perf_counter() - start)
        cpu_times.append(time.process_time() - cpu_start)
        del rows
    gc.collect()
    tracemalloc.start()
    rows, digest = module.read_recording_jsonl(root, 'events.jsonl')
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {'medianMs': statistics.median(times) * 1000,
            'medianCpuMs': statistics.median(cpu_times) * 1000, 'peakMiB': peak / 2**20,
            'rows': len(rows), 'sha256': digest}


def main():
    """Load the baseline as inert source, never import or launch a controller."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='579221edf09a1642697c5209fceca729f497ba39')
    parser.add_argument('--rows', type=int, default=5000)
    parser.add_argument('--repeats', type=int, default=7)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source = subprocess.check_output(['git', 'show', args.baseline + ':tools/bettergi-agent/policy_rgb_archive.py'], cwd=repo)
    baseline = types.ModuleType('baseline_policy_rgb_archive')
    exec(compile(source, '<committed-policy-rgb-archive>', 'exec'), baseline.__dict__)
    with tempfile.TemporaryDirectory(prefix='bettergi-review-jsonl-') as directory:
        root = Path(directory)
        raw = (json.dumps({'type': 'proposal', 'frameId': 1, 'padding': 'x' * 2048}) + '\n').encode() * args.rows
        (root / 'events.jsonl').write_bytes(raw)
        before = measure(baseline, root, args.repeats)
        after = measure(current, root, args.repeats)
        assert before['rows'] == after['rows'] == args.rows
        assert before['sha256'] == after['sha256'] == hashlib.sha256(raw).hexdigest()
        print(json.dumps({'bytes': len(raw), 'repeats': args.repeats, 'baseline': before, 'working': after}, indent=2))


if __name__ == '__main__':
    main()
