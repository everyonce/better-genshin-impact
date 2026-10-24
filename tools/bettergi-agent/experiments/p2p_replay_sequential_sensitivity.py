"""OFFLINE sequential-only sensitivity experiment; default CPU preflight, GPU explicit.

This is a distinct contract from the failed full-context experiment. It reuses
its CPU evidence checks, but does not assert or waive full/incremental parity.
"""
import json
from pathlib import Path
import subprocess
import time
import traceback

import p2p_replay_sensitivity as base

METHOD = 'sequential-online-supplied-action-v1'
FAILED_REPORT = Path(__file__).parent / 'p2p-replay-sensitivity-run-001/report.json'


def validate_replays(prefix, contexts, alternate_contexts, logits, alternate_logits, report, report_path):
    """Jointly gate repeated history and isolation from the changed current-probe placeholder."""
    import torch
    base.require(contexts.shape[1] == 41 and len(logits) == len(alternate_logits) == 8, 'unexpected replay geometry')
    base.numeric_gate(prefix + '/all-contexts-repeat-and-placeholder', alternate_contexts, contexts,
                      report, report_path, exact=True)
    for index in range(8):
        base.numeric_gate(prefix + f'/history-logits-{index}', alternate_logits[index][:, :-1], logits[index][:, :-1],
                          report, report_path, exact=True)
    # Later probe teacher-forced heads legitimately see the alternate placeholder prefix.
    base.numeric_gate(prefix + '/probe-first-logits', alternate_logits[0][:, -1:], logits[0][:, -1:],
                      report, report_path, exact=True)
    differences = []
    for index in range(1, 8):
        a, b = alternate_logits[index][:, -1:], logits[index][:, -1:]
        base.require(bool(torch.isfinite(a).all() and torch.isfinite(b).all()), 'nonfinite placeholder-dependent logits')
        differences.append({'component': index, 'maxAbsoluteDifference': float((a.float()-b.float()).abs().max()),
                            'comparisonGate': False,
                            'reason': 'Teacher-forced head may see the changed current-probe placeholder prefix.'})
    return differences


def validate_sample_pair(prefix, reference, alternate, logits, alternate_logits, report, report_path):
    """Require exact complete sampled actions and all conditional logits for repeated probe contexts."""
    base.require(reference['seed'] == alternate['seed'] and reference['uniforms'] == alternate['uniforms'],
                 prefix + ': RNG pairing mismatch')
    base.require(reference['tokenIds'] == alternate['tokenIds'] and reference['decoded'] == alternate['decoded'],
                 prefix + ': complete sampled action repeatability failed')
    base.require(len(reference['tokenIds']) == 8 and len(logits) == len(alternate_logits) == 8,
                 prefix + ': incomplete sampled action')
    for index in range(8):
        base.numeric_gate(prefix + f'/conditional-logits-{index}', alternate_logits[index], logits[index],
                          report, report_path, exact=True)


def comparisons_after_gates(results, negative_probe):
    """Publish sensitivity summaries only after every replay/sample gate, including the negative control."""
    summaries = []
    for case in results:
        left = case['arms']['accepted_proxy']['samples']
        right = case['arms']['receipt_same_frames']['samples']
        base.require(len(left) == len(right) == 32, 'incomplete paired sample set')
        pairs = []
        for a, b in zip(left, right):
            x, y = a['referenceReplay'], b['referenceReplay']
            base.require(x['seed'] == y['seed'] and x['uniforms'] == y['uniforms'], 'cross-arm RNG pairing mismatch')
            pairs.append({'seed': x['seed'], 'tokenIdsEqual': x['tokenIds'] == y['tokenIds'],
                          'decodedEqual': x['decoded'] == y['decoded'],
                          'maxLogitDifferenceByComponent': [max(abs(p-q) for p, q in zip(l, r))
                                                           for l, r in zip(x['logits'], y['logits'])]})
        if case['probeFrameId'] == negative_probe:
            base.require(all(p['tokenIdsEqual'] and p['decodedEqual'] and max(p['maxLogitDifferenceByComponent']) == 0
                             for p in pairs), 'identical-label sequential negative control failed')
        summaries.append({'key': case['key'], 'arm': 'receipt_same_frames', 'pairedSeeds': pairs,
                          'meaning': 'Sequential-only supplied-action history sensitivity; no quality or success label.'})
    return summaries


def execute_model(args, prepared, report, output, report_path, codec):
    """Load once, replay original online_forward twice per arm, and fail before publishing any comparison."""
    import numpy as np
    import torch
    import yaml
    from p2p_loader import load_model
    base.require(torch.cuda.is_available(), 'CUDA unavailable')
    report['checkpointEvidence'] = base.digest(args.checkpoint)
    checkpoint_config = Path(args.checkpoint).parent / 'model_config.yaml'
    report['checkpointConfigEvidence'] = base.digest(checkpoint_config)
    inference = yaml.safe_load(checkpoint_config.read_text(encoding='utf-8'))['inference']
    base.require(inference['mouse_sampling_approach'] == 'truncated_normal' and inference['sampling_temperature'] == 1.0,
                 'checkpoint sampling defaults differ from this diagnostic')
    started = time.perf_counter()
    report['modelLoadAttempted'] = True
    model, config, manifest = load_model(args.source, args.checkpoint, output / 'isolated-source', history=41)
    report.update(modelLoaded=True, modelLoadMs=(time.perf_counter()-started)*1000,
                  compatibility=manifest, device=torch.cuda.get_device_name(), torchVersion=torch.__version__)
    report['sampling'].update(topP=model.top_p, topPResolved=True)
    base.require(config.shared.n_seq_timesteps == 41 and model.action_mapping.get_seq_len() == 8,
                 'wrong checkpoint geometry')
    results = []
    with torch.inference_mode(), torch.device('cuda'), torch.autocast('cuda', dtype=torch.float16):
        for case in prepared:
            result = {'key': case['key'], 'probeFrameId': case['probeFrameId'], 'arms': {}}
            report['validationEvidence'].append(result)
            for name, arm in case['arms'].items():
                prefix = case['key'] + '/' + name
                frames = torch.as_tensor(arm['frames'].transpose(0, 3, 1, 2).copy(), device='cuda').unsqueeze(0)
                tokens = torch.as_tensor(arm['tokens'], device='cuda').unsqueeze(0)
                goals = torch.as_tensor(case['goal'], device='cuda', dtype=torch.float16)[None, None].expand(1, 41, 1, 768).contiguous()
                alternate = tokens.clone()
                alternate[0, -1] = torch.tensor(codec.encode({'heldKeys': ['W', 'LBUTTON'], 'mouseDx': 2000, 'mouseDy': -2000}),
                                                device='cuda')
                base.require(not torch.equal(alternate[:, -1], tokens[:, -1]), 'placeholder contrast is empty')
                arm_result = {'samples': [], 'probeShapePlaceholder': tokens[0, -1].cpu().tolist(),
                              'alternateProbeShapePlaceholder': alternate[0, -1].cpu().tolist(),
                              'probeIsLabelled': False, 'freshCacheReplays': 2}
                result['arms'][name] = arm_result
                report['inferenceExecuted'] = True
                contexts, logits = base.incremental_reference(model, frames, goals, tokens)
                alternate_contexts, alternate_logits = base.incremental_reference(model, frames, goals, alternate)
                arrays = {'referenceContexts': contexts.float().cpu().numpy(),
                          'alternatePlaceholderContexts': alternate_contexts.float().cpu().numpy()}
                arrays.update({f'referenceTeacherLogits{i}': x.float().cpu().numpy() for i, x in enumerate(logits)})
                arrays.update({f'alternateTeacherLogits{i}': x.float().cpu().numpy() for i, x in enumerate(alternate_logits)})
                dump = output / f'{case["key"]}-{name}-sequential-parity.npz'
                np.savez_compressed(dump, **arrays)
                arm_result['parityArrays'] = base.digest(dump)
                arm_result['placeholderDependentProbeHeads'] = validate_replays(
                    prefix, contexts, alternate_contexts, logits, alternate_logits, report, report_path)
                for seed in range(args.first_seed, args.first_seed + args.seeds):
                    reference, reference_logits = base.sample_probe(model, contexts[:, -1:], seed)
                    alt, alt_logits = base.sample_probe(model, alternate_contexts[:, -1:], seed)
                    # Preserve exact conditional tensors before checking or serializing numerical values.
                    arrays.update({f'seed{seed}ReferenceLogits{i}': x.float().cpu().numpy() for i, x in enumerate(reference_logits)})
                    arrays.update({f'seed{seed}AlternateLogits{i}': x.float().cpu().numpy() for i, x in enumerate(alt_logits)})
                    np.savez_compressed(dump, **arrays)
                    arm_result['parityArrays'] = base.digest(dump)
                    base.require(all(bool(torch.isfinite(x).all()) for x in reference_logits + alt_logits),
                                 'nonfinite sampled conditional logits; tensors saved')
                    pair = {'seed': seed, 'referenceReplay': reference, 'alternatePlaceholderReplay': alt,
                            'tokensExact': reference['tokenIds'] == alt['tokenIds'],
                            'decodedExact': reference['decoded'] == alt['decoded']}
                    arm_result['samples'].append(pair)
                    base.save_report(report_path, report)
                    validate_sample_pair(prefix + f'/seed-{seed}', reference, alt, reference_logits, alt_logits,
                                         report, report_path)
            results.append(result)
    summaries = comparisons_after_gates(results, args.negative_control_probe)
    report.update(comparisons=summaries, comparisonEligible=True, status='complete',
                  peakAllocatedVramBytes=torch.cuda.max_memory_allocated())


def main(argv=None):
    """Reuse every original CPU join; separately identify the narrower exact sequential contract."""
    args = base.parse_args(argv)
    base.require(not args.include_grid, 'sequential v1 supports the two same-image arms only')
    base.require(args.seeds == 32, 'this bounded sequential experiment requires 32 paired seeds')
    output = args.output.resolve()
    base.require(not output.exists(), 'output directory already exists; preserve earlier evidence')
    output.mkdir(parents=True)
    report_path = output / 'report.json'
    report = {'status': 'preparing', 'method': METHOD, 'offlineOnly': True, 'trainingEligible': False,
              'productionEligible': False, 'inferenceExecuted': False, 'modelLoadAttempted': False, 'modelLoaded': False,
              'comparisonEligible': False, 'comparisons': [], 'validationEvidence': [], 'parityGates': [],
              'limitations': base.LIMITATIONS + [
                  'Sequential repeatability is a different contract; full-context equivalence remains unestablished.',
                  'Two passes differ only in the final shape-placeholder. Later probe teacher-forced heads may differ.',
                  'Both arms use original online_forward with fresh caches; no full batched policy call is substituted.',
                  'Sampling uses raw unmasked upstream vocabulary, without live controller admission checks. '
                  'Live raw sampling is also unmasked; its configured key subset rejects whole proposals afterward. '
                  'Offline raw-action sensitivity is not the production accepted/executed decision distribution.'],
              'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              'runnerEvidence': base.digest(__file__), 'reusedPrototypeEvidence': base.digest(base.__file__),
              'numericTolerance': {'rtol': 0, 'atol': 0, 'scope': 'same-shape sequential repeatability and placeholder isolation'},
              'sampling': {'temperature': 1.0, 'mouse': 'truncated_normal', 'pairedUniformCount': 8,
                           'seedCount': args.seeds, 'firstSeed': args.first_seed,
                           'vocabulary': 'unmasked-upstream', 'keyLogitMask': None, 'controllerAdmissionApplied': False,
                           'topP': None, 'topPResolved': False,
                           'comparisonTarget': 'raw policy actions, not accepted/executed controller actions'},
              'fullContextParityEstablished': False}
    started = time.perf_counter()
    try:
        prior = json.loads(FAILED_REPORT.read_text(encoding='utf-8'))
        base.require(prior['status'] == 'blocked' and prior['comparisonEligible'] is False,
                     'prior failed experiment no longer matches recorded provenance')
        report['priorFailedFullContextExperiment'] = {'evidence': base.digest(FAILED_REPORT),
                                                    'parityGates': prior['parityGates'], 'error': prior['error']}
        cases = [base.load_case(path, int(fid), False) for path, fid in args.case]
        base.require(len({c['key'] for c in cases}) == len(cases), 'duplicate case')
        negative = [c for c in cases if c['window']['probe']['frameId'] == args.negative_control_probe]
        base.require(len(negative) == 1, 'negative-control probe must name exactly one explicit case')
        codec = base.ActionCodec(args.source)
        prepared, evidence, cpu_gate = base.prepare_inputs(cases, codec, output, args.ffmpeg, args.ffprobe)
        report.update(cases=evidence, cpuCodecGate=cpu_gate)
        report['recordedLiveAdmission'] = []
        for case in cases:
            live = json.loads(Path(case['inputEvidence']['report']['path']).read_text(encoding='utf-8'))
            base.require(base.digest(case['inputEvidence']['report']['path']) == case['inputEvidence']['report'],
                         'source report changed while reading live admission context')
            report['recordedLiveAdmission'].append({
                'key': case['key'], 'reportEvidence': case['inputEvidence']['report'],
                'configuredInputKeys': live.get('configuredInputKeys'), 'effectiveInputKeys': live.get('effectiveInputKeys'),
                'liveRawSampler': 'unmasked-upstream',
                'keySubsetBehavior': 'post-sampling whole-proposal rejection: trialKeyNotAllowed',
                'simulatedByThisExperiment': False})
        control = next(c for c in prepared if c['probeFrameId'] == args.negative_control_probe)
        import numpy as np
        a, b = (control['arms'][name] for name in ('accepted_proxy', 'receipt_same_frames'))
        base.require(np.array_equal(a['frames'], b['frames']) and np.array_equal(a['tokens'], b['tokens']),
                     'negative control does not have identical image/token inputs')
        report['negativeControlInputsExact'] = True
        paths = sorted((args.source / 'elefant/policy_model').glob('*.py'))
        paths += [args.source / path for path in ('elefant/im_tokenizer/conv_tokenizer.py', 'elefant/torch/__init__.py',
                                                'elefant/torch/util.py', 'config/policy_model/150M.yaml')]
        paths += [base.TOOLS / name for name in ('p2p_loader.py', 'p2p_compat_attention.py', 'p2p_rotary.py',
                                               'goal_embedding.py', 'observation_profiles.py',
                                               'model_adapters.py', 'stream_client.py')]
        report['sourceEvidence'] = [base.digest(p) for p in paths]
        report['upstreamRevision'] = subprocess.run(['git', '-C', str(args.source), 'rev-parse', 'HEAD'],
                                                     capture_output=True, text=True, check=True).stdout.strip()
        report['decoderToolEvidence'] = [base.digest(args.ffmpeg), base.digest(args.ffprobe)]
        report['status'] = 'cpu-preflight-passed'
        base.save_report(report_path, report)
        if args.execute_gpu:
            report['status'] = 'validating-sequential-parity'
            execute_model(args, prepared, report, output, report_path, codec)
    except Exception as exc:
        report.update(status='blocked', comparisonEligible=False, comparisons=[], error=str(exc), traceback=traceback.format_exc())
    finally:
        report['elapsedSeconds'] = time.perf_counter()-started
        base.save_report(report_path, report)
    print(json.dumps({'status': report['status'], 'method': METHOD, 'inferenceExecuted': report['inferenceExecuted'],
                      'comparisonEligible': report['comparisonEligible'], 'report': str(report_path), 'error': report.get('error')}))
    return 0 if report['status'] in ('cpu-preflight-passed', 'complete') else 2


if __name__ == '__main__':
    raise SystemExit(main())
