"""Benchmark real model responses against a constant latest-frame replay stream.

Frames are decoded before timing, so these numbers measure model/queue latency,
not fresh game capture, disk decoding, or physical input-to-display response.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
from pathlib import Path
import statistics
import subprocess
import threading
import time
import traceback
from action_validation import action_observations


class LatestFrameStream:
    """A single replaceable slot prevents inference from accumulating stale work."""
    def __init__(self, frames, fps):
        self.frames = frames
        self.period = 1 / fps
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.latest = None
        self.thread = threading.Thread(target=self._publish, daemon=True)

    def _publish(self):
        index = 0
        deadline = time.perf_counter()
        while not self.stopped.is_set():
            with self.lock:
                self.latest = (index, time.perf_counter_ns(), self.frames[index % len(self.frames)])
            index += 1
            deadline += self.period
            self.stopped.wait(max(0, deadline - time.perf_counter()))

    def take(self, after=-1):
        while not self.stopped.is_set():
            with self.lock:
                value = self.latest
            if value and value[0] != after:
                return value
            self.stopped.wait(0.001)
        raise RuntimeError('Frame stream stopped')


def stats(values):
    """Return nearest-rank percentiles with an explicit sample count."""
    values = sorted(value for value in values if value is not None)
    if not values:
        return None
    return {'count': len(values), 'p50': statistics.median(values),
            'p95': values[math.ceil(len(values) * .95) - 1], 'min': min(values), 'max': max(values)}


def file_hash(path):
    """Hash weights incrementally without retaining a second copy in RAM."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(output, report):
    """Replace complete reports atomically so monitoring never reads partial JSON."""
    pending = output.with_suffix(output.suffix + '.tmp')
    pending.write_text(json.dumps(report, indent=2), encoding='utf-8')
    os.replace(pending, output)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['gamescaling', 'open-p2p'], required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--goal-embedding', help='Local validated P2P goal JSON; encoding is outside the timed loop')
    parser.add_argument('--instruction', help='Per-trial GameScaling text goal; P2P uses goal-embedding')
    parser.add_argument('--images', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cache-root', default='artifacts/agent/compatibility')
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--sample-mode', choices=['latest', 'independent'], default='latest',
                        help='Independent GameScaling cases cycle images, reset history, and use seed+round for matched-image sampling comparisons')
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--fps', type=float, default=30)
    parser.add_argument('--history', type=int, default=None)
    parser.add_argument('--image-width', type=int, default=384)
    parser.add_argument('--max-new-tokens', type=int, default=64)
    parser.add_argument('--sampling', choices=['greedy', 'sample'], default='greedy', help='GameScaling token selection; defaults to the validated greedy path')
    parser.add_argument('--temperature', type=float, default=1.0, help='GameScaling sampling temperature; requires --sampling sample for overrides')
    parser.add_argument('--top-k', type=int, default=0, help='GameScaling sampling top-k; 0 explicitly disables filtering')
    parser.add_argument('--top-p', type=float, default=1.0, help='GameScaling sampling top-p; 1 explicitly disables nucleus filtering')
    parser.add_argument('--dtype', choices=['float16', 'float32'], default='float16')
    parser.add_argument('--cuda-graph', action='store_true', help='Capture full-cache P2P steps or fixed-shape GameScaling decode blocks')
    parser.add_argument('--gamescaling-prefix-cache', action='store_true',
                        help='Opt in to validated invariant text-prefix reuse; requires GameScaling, history 0, and cuda-graph')
    parser.add_argument('--p2p-fast-start', action='store_true', help='Start P2P graph inference with correctly masked empty history')
    parser.add_argument('--keep-warmup-context', action='store_true', help='Retain populated temporal state for a steady-state eager comparison')
    parser.add_argument('--position-offset', type=int, default=0, help='Diagnostic OpenP2P step offset; does not simulate prior gameplay')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--game-running', action='store_true', help='Operator attestation, not automatically detected')
    args = parser.parse_args()
    if args.gamescaling_prefix_cache and (args.model != 'gamescaling' or not args.cuda_graph or args.history not in (None, 0)):
        parser.error('gamescaling-prefix-cache requires gamescaling, history 0, and cuda-graph')
    return args


def main():
    args = arguments()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'starting', 'model': args.model, 'settings': vars(args),
              'scope': 'Offline historical-frame replay; no game control or capability score.',
              'host': platform.platform(), 'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'samples': []}
    stream = None
    try:
        if args.samples < 1 or args.warmup < 0 or not 0 < args.fps <= 240:
            raise ValueError('samples must be positive; warmup nonnegative; fps in (0,240]')
        if args.p2p_fast_start and (args.model != 'open-p2p' or not args.cuda_graph):
            raise ValueError('p2p-fast-start requires open-p2p and cuda-graph')
        if args.instruction is not None and (args.model != 'gamescaling' or not args.instruction.strip() or len(args.instruction) > 2000):
            raise ValueError('instruction requires gamescaling and 1–2000 characters')
        if args.goal_embedding and args.model != 'open-p2p':
            raise ValueError('goal-embedding requires open-p2p')
        if args.sample_mode == 'independent' and args.model != 'gamescaling':
            raise ValueError('Independent snapshot comparisons currently support GameScaling only')
        if args.model != 'gamescaling' and (args.sampling, args.temperature, args.top_k, args.top_p) != ('greedy', 1.0, 0, 1.0):
            raise ValueError('Sampling overrides currently apply to GameScaling only')
        from PIL import Image
        import numpy as np
        import torch
        from model_adapters import make_adapter
        if args.model == 'gamescaling':
            from gamescaling_decode import sampling_options
            sampling_options(args.sampling, args.temperature, args.top_k, args.top_p)
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        report['packages'] = {package: importlib.metadata.version(package) for package in
                              ['torch', 'torchvision', 'transformers', 'Pillow', 'safetensors']}
        code_root = Path(__file__).resolve().parent
        report['adapterCodeHashes'] = {path.name: file_hash(path) for path in sorted(code_root.glob('*.py'))}
        report['gpu'] = {'name': torch.cuda.get_device_name(), 'computeCapability': torch.cuda.get_device_capability(),
                         'cudaRuntime': torch.version.cuda}
        report['sourceRevision'] = subprocess.check_output(['git', '-C', args.source, 'rev-parse', 'HEAD'], text=True).strip()
        checkpoint = Path(args.checkpoint)
        weight_files = sorted(checkpoint.glob('*.safetensors')) if checkpoint.is_dir() else [checkpoint]
        report['weightHashes'] = {str(path): file_hash(path) for path in weight_files}
        frame_paths = []
        for name in args.images:
            path = Path(name)
            frame_paths.extend(sorted(path.glob('*.png'))[:100] if path.is_dir() else [path])
        if not frame_paths:
            raise ValueError('No PNG replay frames found')
        frames = []
        for path in frame_paths:
            with Image.open(path) as image:
                frames.append(image.convert('RGB'))
        report['frames'] = [{'path': str(path), 'sha256': file_hash(path)} for path in frame_paths]
        torch.cuda.reset_peak_memory_stats()
        start_load = time.perf_counter()
        policy = make_adapter(args.model, checkpoint=str(checkpoint), source=args.source,
            cache_root=args.cache_root, history=args.history if args.history is not None else (0 if args.model == 'gamescaling' else 200),
            image_width=args.image_width, max_new_tokens=args.max_new_tokens, dtype=args.dtype,
            goal_embedding=args.goal_embedding, instruction=args.instruction,
            sampling=args.sampling, temperature=args.temperature, top_k=args.top_k, top_p=args.top_p,
            cuda_graph=args.cuda_graph, fast_start=args.p2p_fast_start,
            gamescaling_prefix_cache=args.gamescaling_prefix_cache)
        torch.cuda.synchronize()
        report['loadSeconds'] = time.perf_counter() - start_load
        report['adapter'] = policy.metadata
        if args.position_offset:
            if args.model != 'open-p2p' or args.position_offset < 0:
                raise ValueError('A nonnegative position offset is supported only for OpenP2P diagnostics')
            policy.idx.fill_(args.position_offset * policy.model.bc_transformer.step_size)
            policy.steps_seen = args.position_offset
        warmup_started = time.perf_counter()
        for warmup_index in range(args.warmup):
            frame = frames[warmup_index % len(frames)]
            policy.predict(frame, frame.size)
        report['warmupSeconds'] = time.perf_counter() - warmup_started
        # A CUDA graph requires a populated, fixed-size cache. Preserve exactly
        # the declared warmup frames and disclose that context in the result.
        report['warmupContextRetained'] = args.sample_mode == 'latest' and (args.cuda_graph or args.keep_warmup_context or args.position_offset != 0)
        if not report['warmupContextRetained']:
            policy.reset()
        if args.sample_mode == 'latest':
            stream = LatestFrameStream(frames, args.fps)
            stream.thread.start()
        else:
            report['scope'] = 'Independent saved-image comparison; empty history and seed+round per case. No stream-queue or gameplay capability claim.'
        previous = -1
        for index in range(args.samples):
            sample_seed = None
            if stream is not None:
                frame_id, published_ns, frame = stream.take(previous)
            else:
                # Same image/round gets the same seed in every comparison arm.
                # The validated decode graph is retained while chat history resets.
                policy.reset()
                sample_seed = args.seed + index // len(frames)
                torch.manual_seed(sample_seed)
                np.random.seed(sample_seed)
                frame_id, frame = index, frames[index % len(frames)]
                published_ns = time.perf_counter_ns()
            inference_start_ns = time.perf_counter_ns()
            result = policy.predict(frame, frame.size)
            completed_ns = time.perf_counter_ns()
            result.update(action_observations(result, frame.size))
            result.update({'sample': index, 'frameId': frame_id,
                           'sourceImageIndex': frame_id % len(frames), 'sampleSeed': sample_seed,
                           'skippedFrames': max(0, frame_id - previous - 1) if previous >= 0 else 0,
                           'queueAgeMs': (inference_start_ns-published_ns)/1e6,
                           'observationToActionMs': (completed_ns-published_ns)/1e6})
            report['samples'].append(result)
            previous = frame_id
            print(json.dumps({'sample': index, 'fullActionMs': round(result['fullActionMs'], 2),
                              'parseValid': result['parseValid'], 'skippedFrames': result['skippedFrames']}), flush=True)
            # Persist partial measurements so a later OOM does not erase evidence.
            report['status'] = 'running'
            write_report(output, report)
        report['summary'] = {metric: stats([row[metric] for row in report['samples']]) for metric in
                             ['preprocessMs', 'firstTokenMs', 'fullActionMs', 'queueAgeMs', 'observationToActionMs']}
        report['parseValidRate'] = sum(row['parseValid'] for row in report['samples']) / args.samples
        report['protocolCompatibleRate'] = sum(row['protocolCompatible'] for row in report['samples']) / args.samples
        report['noOpActionRate'] = sum(row['noOpAction'] for row in report['samples']) / args.samples
        report['skippedFrames'] = sum(row['skippedFrames'] for row in report['samples'])
        report['peakAllocatedMiB'] = torch.cuda.max_memory_allocated() / 2**20
        report['peakReservedMiB'] = torch.cuda.max_memory_reserved() / 2**20
        latency = report['summary']['observationToActionMs']['p95']
        report['latencyGate'] = {'p95Under200Ms': latency <= 200, 'p95Under50Ms': latency <= 50,
                                 'allActionsParsed': report['parseValidRate'] == 1,
                                 'liveControlQualified': False,
                                 'reason': 'Replay latency alone does not validate Genshin behavior or live input/capture latency.'}
        report['status'] = 'completed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        print(report['error']['traceback'], flush=True)
    finally:
        if stream:
            stream.stopped.set()
            stream.thread.join(timeout=2)
        write_report(output, report)
    print(str(output.resolve()), flush=True)
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
