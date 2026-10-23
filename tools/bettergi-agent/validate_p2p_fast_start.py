"""Compare real growing history, masked history, and empty-start CUDA graph.

This diagnostic replays saved frames and never connects to game input. It fails
on action disagreement or cache errors and preserves intermediate evidence.
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
import torch

from benchmark import file_hash, stats, write_report
from model_adapters import OpenP2PAdapter


def compare(actual, expected, report):
    """Require exact sampled choices/index and compare every real cache entry."""
    for value, reference in zip(actual[0], expected[0]):
        torch.testing.assert_close(value, reference, rtol=0, atol=0)
    torch.testing.assert_close(actual[1], expected[1], rtol=0, atol=0)
    max_error = 0.0
    max_relative_rms = 0.0
    max_relative_absolute = 0.0
    for padded, growing in zip(actual[2], expected[2]):
        length = growing.k_cache.shape[2]
        for value, reference in ((padded.k_cache, growing.k_cache), (padded.v_cache, growing.v_cache)):
            suffix = value[:, :, -length:, :]
            delta = suffix.float()-reference.float()
            max_error = max(max_error, delta.abs().max().item())
            relative_rms = (delta.square().mean().sqrt() /
                            reference.float().square().mean().sqrt().clamp_min(1e-6)).item()
            max_relative_rms = max(max_relative_rms, relative_rms)
            # Fixed and growing matrix shapes use different FP16 reduction tilings.
            # Normalize by the full tensor's scale; near-zero individual entries
            # cannot define a useful relative error for this comparison.
            relative_absolute = delta.abs().max().item() / max(reference.float().abs().max().item(), 1e-6)
            max_relative_absolute = max(max_relative_absolute, relative_absolute)
            if relative_rms > report['relativeRmsLimit']:
                raise AssertionError(f'Cache relative RMS error {relative_rms} exceeds limit')
            if relative_absolute > report['relativeAbsoluteLimit']:
                raise AssertionError(f'Cache relative maximum error {relative_absolute} exceeds limit')
    return max_error, max_relative_rms, max_relative_absolute


def main():
    """Exercise empty startup, fill boundaries, rollover, graph replay and reset."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--cache-root', default='artifacts/agent/compatibility')
    parser.add_argument('--images', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--history', type=int, default=200)
    parser.add_argument('--steps', type=int, default=205)
    parser.add_argument('--feedback-only', action='store_true',
                        help='Only test graph startup/reset and accepted/rejected cache transactions')
    args = parser.parse_args()
    if args.history < 2 or args.steps <= args.history:
        parser.error('Validation must include fill and rollover')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'starting', 'settings': vars(args),
              'relativeRmsLimit': 0.002, 'relativeAbsoluteLimit': 0.005,
              'scope': 'Saved-image numerical validation; no game input.', 'steps': []}
    try:
        torch.manual_seed(724)
        started = time.perf_counter()
        policy = OpenP2PAdapter(args.checkpoint, args.source, args.cache_root,
                               history=args.history, cuda_graph=True, fast_start=True, execution_feedback=True)
        report['loadSeconds'] = time.perf_counter()-started
        print(json.dumps({'phase': 'modelLoaded', 'seconds': report['loadSeconds']}), flush=True)
        report['adapter'] = policy.metadata
        report['codeHashes'] = {name: file_hash(Path(__file__).with_name(name)) for name in
                                ('p2p_temporal_cache.py', 'model_adapters.py', 'p2p_loader.py')}
        images = [Image.open(path).convert('RGB') for path in args.images]
        frames = [torch.from_numpy(np.array(image.resize((192, 192), Image.Resampling.BILINEAR), copy=True))
                  .permute(2, 0, 1).to('cuda') for image in images]
        growing = policy.model.bc_transformer.init_kv_cache_state()
        padded = policy.state
        idx = torch.zeros((), dtype=torch.int64, device='cuda')
        policy.temporal_cache.reset()
        for step in range(0 if args.feedback_only else args.steps):
            frame = frames[step % len(frames)]
            uniform = torch.rand(policy.model.action_mapping.get_seq_len(), device='cuda')
            with policy.temporal_cache.reference_attention():
                reference = policy._forward(frame, idx, growing, uniform)
            policy.temporal_cache.advance()
            actual = policy._forward(frame, idx, padded, uniform)
            error, relative_rms, relative_absolute = compare(actual, reference, report)
            growing, padded, idx = reference[2], actual[2], reference[1]
            report['steps'].append({'step': step+1, 'maxCacheAbsoluteError': error,
                                    'maxCacheRelativeRms': relative_rms,
                                    'maxCacheRelativeAbsoluteError': relative_absolute,
                                    'exactActions': True, 'realTokens': int(idx.item())})
            report['status'] = 'validating'
            write_report(output, report)
            if step in (0, 1, args.history-2, args.history-1, args.history, args.steps-1):
                print(json.dumps(report['steps'][-1]), flush=True)
        # First live prediction must contain exactly one real observation after
        # scratch capture, and reset must retain the validated graph's pointers.
        policy.reset()
        startup = policy.predict(images[0])
        graph = policy.graph
        text_pointer = policy.text.data_ptr()
        if startup['episodeStep'] != 1 or int(policy.idx.item()) != policy.temporal_cache.step_size:
            raise AssertionError('Graph preparation invented episode history')
        report['emptyStartup'] = startup
        print(json.dumps({'phase': 'graphCaptured', 'milliseconds': startup['fullActionMs']}), flush=True)
        write_report(output, report)
        policy.finish_action(True)
        replay = []
        for index in range(20):
            replay.append(policy.predict(images[index % len(images)]))
            policy.finish_action(True)
        policy.reset()
        if policy.graph is not graph or policy.text.data_ptr() != text_pointer or int(policy.idx.item()) != 0:
            raise AssertionError('Reset did not preserve graph storage with empty history')
        after_reset = policy.predict(images[1 % len(images)])
        if after_reset['episodeStep'] != 1 or after_reset['graphPreparationMs'] != 0:
            raise AssertionError('Reset recaptured the graph or kept prior episode history')
        report['afterReset'] = after_reset
        policy.finish_action(True)
        report['graphReplayMs'] = stats([row['fullActionMs'] for row in replay])
        transactions = []
        for index in range(40):
            before = [(state.k_cache.clone(), state.v_cache.clone()) for state in policy.state]
            before_index = policy.idx.clone()
            before_valid = policy.temporal_cache.valid_tokens.clone()
            before_steps = policy.steps_seen
            result = policy.predict(images[index % len(images)])
            accepted = index % 3 == 0
            policy.finish_action(accepted)
            torch.cuda.synchronize()
            if not accepted:
                torch.testing.assert_close(policy.idx, before_index, rtol=0, atol=0)
                torch.testing.assert_close(policy.temporal_cache.valid_tokens, before_valid, rtol=0, atol=0)
                identical = [torch.eq(value, saved_tensor).all()
                             for state, saved in zip(policy.state, before)
                             for value, saved_tensor in ((state.k_cache, saved[0]), (state.v_cache, saved[1]))]
                if not torch.stack(identical).all().item():
                    raise AssertionError('Rejected proposal did not restore exact K/V history')
            if policy.steps_seen != before_steps+int(accepted) or policy.graph is not graph:
                raise AssertionError('Transaction changed graph identity or committed incorrect history')
            transactions.append({'simulatedAcceptance': accepted, 'predictionMs': result['fullActionMs'],
                                 'committedHistoryFrames': policy.steps_seen, 'rollbackBitwiseExact': not accepted})
            if index % 10 == 9:
                print(json.dumps({'phase': 'feedback', 'transactions': index+1}), flush=True)
                report['feedbackTransactions'] = transactions
                write_report(output, report)
        report['feedbackTransactions'] = transactions
        report['feedbackPredictionMs'] = stats([row['predictionMs'] for row in transactions])
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        write_report(output, report)
    print(json.dumps({'status': report['status'], 'steps': len(report['steps']),
                      'startupMs': startup['fullActionMs'], 'afterResetMs': after_reset['fullActionMs'],
                      'graphReplayMs': report['graphReplayMs']}), flush=True)


if __name__ == '__main__':
    main()
