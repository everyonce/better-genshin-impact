"""OFFLINE three-arm forward-acquisition diagnostic; CPU preflight unless --execute-gpu.

No existing runner is modified. Original online_forward is reused for every
supplied-action timestep; full-context equivalence remains unestablished.
"""
import itertools
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import p2p_replay_sensitivity as base
import p2p_replay_sequential_sensitivity as sequential
import prepare_replay_forward as forward


METHOD = 'sequential-online-forward-acquisition-three-arm-v1'
ARMS = ('accepted_proxy', 'receipt_same_frames', forward.ARM)
PROBES = {2392, 711, 3079}
NEGATIVE_PROBE = 2392


def historical_provenance():
    """Read the shipped historical summary without treating it as this run's validation."""
    path = Path(__file__).with_name('historical-provenance.json')
    document = json.loads(path.read_text(encoding='utf-8'))
    base.require(document.get('schemaVersion') == 1 and document.get('historicalOnly') is True
                 and document.get('newRunValidation') is False, 'invalid historical summary')
    prior = document['fullContextExperiment']
    base.require(prior['status'] == 'blocked' and prior['comparisonEligible'] is False
                 and any(gate['passed'] is False for gate in prior['parityGates']),
                 'historical full-context failure missing')
    return {'summaryEvidence': base.digest(path), 'historicalOnly': True, 'newRunValidation': False,
            'originalReportEvidence': prior['reportEvidence'], 'runName': prior['runName'],
            'parityGates': prior['parityGates'], 'error': prior['error']}


def resolve_decoder(command):
    """Bind decoder commands to local executable files before subprocess use and hashing."""
    resolved = shutil.which(str(command))
    base.require(resolved is not None and Path(resolved).is_file(), 'decoder executable unavailable: ' + str(command))
    return str(Path(resolved).resolve())


def goal_artifact_relocations(entries, cases):
    """Require explicit digest identities and exact recorded-path membership for remaps."""
    recorded_paths = set()
    for case in cases:
        metadata = case['window']['goalProvenance']['goalMetadata']
        if isinstance(metadata, dict) and isinstance(metadata.get('file'), str):
            recorded_paths.add(metadata['file'])
    mappings = {}
    for recorded_path, local_file, expected_sha256 in entries:
        base.require(recorded_path in recorded_paths, 'unused or unknown recorded goal path')
        base.require(recorded_path not in mappings, 'duplicate recorded goal mapping')
        expected_sha256 = expected_sha256.lower()
        base.require(len(expected_sha256) == 64 and all(value in '0123456789abcdef' for value in expected_sha256),
                     'invalid expected goal artifact SHA-256')
        path = Path(local_file).resolve()
        base.require(base.digest(path)['sha256'] == expected_sha256, 'relocated goal artifact hash mismatch')
        mappings[recorded_path] = {'path': str(path), 'sha256': expected_sha256}
    return mappings


def dependency_versions():
    """Record installed distribution versions without importing a model or touching CUDA."""
    versions = {}
    for name in ('torch', 'torchvision', 'numpy', 'Pillow', 'PyYAML', 'pydantic',
                 'pydantic-yaml', 'fsspec', 'protobuf', 'einops'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {'python': sys.version, 'packages': versions}


def verify_preparers(plan):
    """Bind reconstruction to the exact preparation modules that wrote this new plan."""
    expected = plan.get('preparerEvidence', {})
    base.require(set(expected) == {'forward', 'base'}, 'missing exact preparer identity')
    for name, path in [('forward', forward.__file__), ('base', forward.base.__file__)]:
        base.require(base.digest(path) == expected[name], 'changed preparer identity: ' + name)
    return expected


def load_case(plan_path, probe_id):
    """Reconstruct the entire new plan and every label from hashed evidence before decode."""
    from observation_profiles import verify_hello
    plan_path = Path(plan_path).resolve()
    plan_evidence = base.digest(plan_path)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    base.require(plan.get('kind') == forward.KIND and plan.get('schemaVersion') == 1
                 and plan.get('comparisonMode') == forward.MODE and plan.get('status') == 'prepared',
                 'requires separately versioned forward plan')
    base.require(all(plan.get(key) is False for key in ('trainingEligible', 'expertDemonstrations',
                 'humanDemonstrations', 'inferenceExecuted', 'publishedCallbackAlignmentEstablished')),
                 'plan overclaims provenance or execution')
    verify_preparers(plan)
    matches = [window for window in plan['windows'] if window['probe']['frameId'] == probe_id]
    base.require(len(matches) == 1, 'explicit probe absent or ambiguous in forward plan')
    parameters, expected = plan['parameters'], plan['inputEvidence']
    base.require(parameters['historyFrames'] == 40, 'this bounded experiment requires 40 history images')
    base.require(set(expected) == {'report', 'observations.jsonl', 'frames.jsonl', 'events.jsonl',
                                  'recording.json', 'frames.mp4'}, 'unexpected evidence manifest')
    payload = {}
    for name, entry in expected.items():
        base.require(base.digest(entry['path']) == entry, 'changed prepared input: ' + name)
        path = Path(entry['path'])
        if name.endswith('.jsonl'):
            payload[name] = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        elif name != 'frames.mp4':
            payload[name] = json.loads(path.read_text(encoding='utf-8'))
    reconstructed = forward.prepare_forward(payload['report'], payload['observations.jsonl'], payload['frames.jsonl'],
                                             payload['events.jsonl'], payload['recording.json'], history_frames=40,
                                             max_source_gap_ms=parameters['maxSourceGapMs'],
                                             max_windows=parameters['maxWindows'],
                                             probe_frame_ids=parameters['requestedProbeFrameIds'])
    declared = {key: value for key, value in plan.items() if key not in ('inputEvidence', 'preparerEvidence')}
    base.require(base.canonical(reconstructed) == base.canonical(declared), 'forward plan does not exactly reconstruct')
    window = matches[0]
    base.require(set(window['arms']) == set(ARMS) and window.get('probeLabel') is None, 'incorrect arms or labelled probe')
    references = [[sample['frame'] for sample in window['arms'][name]['samples']] for name in ARMS]
    base.require(references[0] == references[1] == references[2], 'three arms do not have identical images')
    for entry in expected.values():
        base.require(base.digest(entry['path']) == entry, 'input changed during label reconstruction')
    base.require(base.digest(plan_path) == plan_evidence, 'plan changed during reconstruction')
    verify_preparers(plan)
    live = payload['report']
    return {'key': f'{plan_path.stem}-probe-{probe_id}', 'planEvidence': plan_evidence, 'inputEvidence': expected,
            'preparerEvidence': plan['preparerEvidence'], 'window': window, 'armNames': list(ARMS),
            'observationProfile': plan['observationProfile'],
            'profileContract': verify_hello(live['hello'], plan['observationProfile'], 'open-p2p'),
            'encodedFrames': payload['recording.json']['encodedFrames'], 'capturePollHz': live['capturePollHz'],
            'liveAdmission': {'configuredInputKeys': live.get('configuredInputKeys'),
                              'effectiveInputKeys': live.get('effectiveInputKeys'),
                              'liveRawSampler': 'unmasked-upstream',
                              'keySubsetBehavior': 'post-sampling whole-proposal rejection: trialKeyNotAllowed',
                              'simulatedByThisExperiment': False}}


def verify_prepared_inputs(prepared):
    """Require identical pixels across all arms and exact negative-control tokens before loading."""
    import numpy as np
    base.require(len(prepared) == 3 and {case['probeFrameId'] for case in prepared} == PROBES,
                 'expected the three explicitly reviewed probes')
    for case in prepared:
        base.require(set(case['arms']) == set(ARMS), 'missing prepared arm')
        for left, right in itertools.combinations(ARMS, 2):
            a, b = case['arms'][left], case['arms'][right]
            base.require(a['frames'].dtype == b['frames'].dtype == np.uint8
                         and a['frames'].shape == b['frames'].shape == (41, 192, 192, 3)
                         and np.array_equal(a['frames'], b['frames']), 'cross-arm model pixels differ')
            base.require(a['tokens'].dtype == b['tokens'].dtype == np.int64
                         and a['tokens'].shape == b['tokens'].shape == (41, 8), 'unexpected token geometry')
            base.require(np.array_equal(a['tokens'][-1], b['tokens'][-1]), 'probe placeholders differ before replay')
            if case['probeFrameId'] == NEGATIVE_PROBE:
                base.require(np.array_equal(a['tokens'], b['tokens']), 'negative-control history IDs differ')
    return {'passed': True, 'sameImagesAcrossAllArms': True, 'negativeControlAllThreePairsExact': True}


def validate_negative_contexts(prefix, contexts, logits, reference, report, report_path):
    """Also require every control context/teacher head to match across identical-input arms."""
    expected_contexts, expected_logits = reference
    base.numeric_gate(prefix+'/negative-control-contexts', contexts, expected_contexts, report, report_path, exact=True)
    base.require(len(logits) == len(expected_logits) == 8, 'incomplete negative-control teacher heads')
    for component in range(8):
        base.numeric_gate(prefix+f'/negative-control-head-{component}', logits[component], expected_logits[component],
                          report, report_path, exact=True)


def checked_samples(arm, first_seed):
    """Validate every complete saved sample before constructing any cross-arm summaries."""
    samples = arm['samples']
    base.require(len(samples) == 32, 'incomplete paired sample set')
    for expected_seed, pair in zip(range(first_seed, first_seed+32), samples):
        sample = pair['referenceReplay']
        base.require(pair['seed'] == sample['seed'] == expected_seed, 'missing/reordered paired seed')
        base.require(pair['tokensExact'] is True and pair['decodedExact'] is True
                     and pair['conditionalLogitsExact'] is True, 'unvalidated within-arm sample')
        base.require(len(sample['tokenIds']) == 8 and all(type(value) is int for value in sample['tokenIds']),
                     'incomplete sampled IDs')
        base.require(len(sample['uniforms']) == 8 and all(type(value) in (int, float) and math.isfinite(value)
                     and 0 <= value < 1 for value in sample['uniforms']), 'invalid paired uniforms')
        base.require(len(sample['logits']) == 8 and all(values and all(math.isfinite(value) for value in values)
                     for values in sample['logits']), 'incomplete/nonfinite conditional logits')
    return [pair['referenceReplay'] for pair in samples]


def comparisons_after_gates(results, first_seed):
    """Build all three pairs locally; a late failure leaves the report's comparisons empty."""
    base.require(len(results) == 3 and {case['probeFrameId'] for case in results} == PROBES, 'missing comparison case')
    summaries = []
    for case in results:
        base.require(set(case['arms']) == set(ARMS), 'missing comparison arm')
        samples = {name: checked_samples(case['arms'][name], first_seed) for name in ARMS}
        for left, right in itertools.combinations(ARMS, 2):
            pairs = []
            for a, b in zip(samples[left], samples[right]):
                base.require(a['seed'] == b['seed'] and a['uniforms'] == b['uniforms'], 'cross-arm RNG pairing mismatch')
                base.require(all(len(x) == len(y) for x, y in zip(a['logits'], b['logits'])), 'conditional vocabulary mismatch')
                differences = [max(abs(x-y) for x, y in zip(p, q)) for p, q in zip(a['logits'], b['logits'])]
                pair = {'seed': a['seed'], 'tokenIdsEqual': a['tokenIds'] == b['tokenIds'],
                        'decodedEqual': a['decoded'] == b['decoded'], 'maxLogitDifferenceByComponent': differences}
                if case['probeFrameId'] == NEGATIVE_PROBE:
                    base.require(pair['tokenIdsEqual'] and pair['decodedEqual'] and max(differences) == 0,
                                 'three-arm identical-input negative control failed')
                pairs.append(pair)
            summaries.append({'key': case['key'], 'probeFrameId': case['probeFrameId'], 'leftArm': left, 'rightArm': right,
                              'pairedSeeds': pairs, 'meaning': 'Raw action-history sensitivity only; no quality/success claim.'})
    return summaries


def execute_model(args, prepared, report, output, report_path, codec):
    """One isolated model; two original sequential replays per arm; no batched-full substitute."""
    import numpy as np
    import torch
    import yaml
    from p2p_loader import load_model
    base.require(torch.cuda.is_available(), 'CUDA unavailable')
    report['checkpointEvidence'] = base.digest(args.checkpoint)
    checkpoint_config = Path(args.checkpoint).parent/'model_config.yaml'
    report['checkpointConfigEvidence'] = base.digest(checkpoint_config)
    inference = yaml.safe_load(checkpoint_config.read_text(encoding='utf-8'))['inference']
    base.require(inference['mouse_sampling_approach'] == 'truncated_normal' and inference['sampling_temperature'] == 1.0,
                 'checkpoint sampling defaults differ from this diagnostic')
    started = time.perf_counter()
    report['modelLoadAttempted'] = True
    model, config, manifest = load_model(args.source, args.checkpoint, output/'isolated-source', history=41)
    report.update(modelLoaded=True, modelLoadMs=(time.perf_counter()-started)*1000, compatibility=manifest,
                  device=torch.cuda.get_device_name(), torchVersion=torch.__version__)
    report['sampling'].update(topP=model.top_p, topPResolved=True)
    base.require(config.shared.n_seq_timesteps == 41 and model.action_mapping.get_seq_len() == 8, 'wrong checkpoint geometry')
    results = []
    with torch.inference_mode(), torch.device('cuda'), torch.autocast('cuda', dtype=torch.float16):
        for case in prepared:
            result = {'key': case['key'], 'probeFrameId': case['probeFrameId'], 'arms': {}}
            report['validationEvidence'].append(result)
            control_reference = None
            for name in ARMS:
                arm = case['arms'][name]
                prefix = case['key']+'/'+name
                frames = torch.as_tensor(arm['frames'].transpose(0, 3, 1, 2).copy(), device='cuda').unsqueeze(0)
                tokens = torch.as_tensor(arm['tokens'], device='cuda').unsqueeze(0)
                goals = torch.as_tensor(case['goal'], device='cuda', dtype=torch.float16)[None, None].expand(1, 41, 1, 768).contiguous()
                alternate = tokens.clone()
                alternate[0, -1] = torch.tensor(codec.encode({'heldKeys': ['W', 'LBUTTON'], 'mouseDx': 2000, 'mouseDy': -2000}), device='cuda')
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
                arrays.update({f'referenceTeacherLogits{i}': value.float().cpu().numpy() for i, value in enumerate(logits)})
                arrays.update({f'alternateTeacherLogits{i}': value.float().cpu().numpy() for i, value in enumerate(alternate_logits)})
                dump = output/f'{case["key"]}-{name}-sequential-parity.npz'
                np.savez_compressed(dump, **arrays)
                arm_result['parityArrays'] = base.digest(dump)
                arm_result['placeholderDependentProbeHeads'] = sequential.validate_replays(
                    prefix, contexts, alternate_contexts, logits, alternate_logits, report, report_path)
                if case['probeFrameId'] == NEGATIVE_PROBE:
                    if control_reference is None:
                        control_reference = (contexts, logits)
                    else:
                        validate_negative_contexts(prefix, contexts, logits, control_reference, report, report_path)
                for seed in range(args.first_seed, args.first_seed+32):
                    reference, reference_logits = base.sample_probe(model, contexts[:, -1:], seed)
                    alt, alt_logits = base.sample_probe(model, alternate_contexts[:, -1:], seed)
                    arrays.update({f'seed{seed}ReferenceLogits{i}': value.float().cpu().numpy() for i, value in enumerate(reference_logits)})
                    arrays.update({f'seed{seed}AlternateLogits{i}': value.float().cpu().numpy() for i, value in enumerate(alt_logits)})
                    np.savez_compressed(dump, **arrays)
                    arm_result['parityArrays'] = base.digest(dump)
                    base.require(all(bool(torch.isfinite(value).all()) for value in reference_logits+alt_logits),
                                 'nonfinite sampled conditional logits; tensors saved')
                    pair = {'seed': seed, 'referenceReplay': reference, 'alternatePlaceholderReplay': alt,
                            'tokensExact': reference['tokenIds'] == alt['tokenIds'],
                            'decodedExact': reference['decoded'] == alt['decoded'], 'conditionalLogitsExact': False}
                    arm_result['samples'].append(pair)
                    base.save_report(report_path, report)
                    sequential.validate_sample_pair(prefix+f'/seed-{seed}', reference, alt, reference_logits, alt_logits,
                                                    report, report_path)
                    pair['conditionalLogitsExact'] = True
            results.append(result)
    summaries = comparisons_after_gates(results, args.first_seed)
    report.update(comparisons=summaries, comparisonEligible=True, status='complete',
                  peakAllocatedVramBytes=torch.cuda.max_memory_allocated())


def main(argv=None):
    """Revalidate three explicit frozen plans, then stop at CPU preflight unless authorized separately."""
    args = base.parse_args(argv)
    base.require(not args.include_grid and args.seeds == 32 and args.negative_control_probe == NEGATIVE_PROBE,
                 'requires three same-image arms, 32 paired seeds and negative probe 2392')
    base.require(len(args.case) == 3 and {int(fid) for _, fid in args.case} == PROBES, 'requires explicit probes 2392/711/3079')
    output = args.output.resolve()
    base.require(not output.exists(), 'output directory already exists; preserve earlier evidence')
    output.mkdir(parents=True)
    report_path = output/'report.json'
    report = {'status': 'preparing', 'method': METHOD, 'offlineOnly': True, 'trainingEligible': False,
              'productionEligible': False, 'humanDemonstrations': False, 'expertDemonstrations': False,
              'inferenceExecuted': False, 'modelLoadAttempted': False, 'modelLoaded': False, 'livePolicyUnchanged': True,
              'comparisonEligible': False, 'comparisons': [], 'validationEvidence': [], 'parityGates': [],
              'fullContextParityEstablished': False, 'publishedCallbackAlignmentEstablished': False,
              'arguments': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
              'runnerEvidence': base.digest(__file__), 'reusedPrototypeEvidence': base.digest(base.__file__),
              'reusedSequentialHelperEvidence': base.digest(sequential.__file__),
              'publishedReference': forward.PUBLISHED_REFERENCE,
              'numericTolerance': {'rtol': 0, 'atol': 0, 'scope': 'same-shape sequential and identical-input control checks'},
              'sampling': {'temperature': 1.0, 'mouse': 'truncated_normal', 'pairedUniformCount': 8,
                           'seedCount': 32, 'firstSeed': args.first_seed, 'vocabulary': 'unmasked-upstream',
                           'keyLogitMask': None, 'controllerAdmissionApplied': False, 'topP': None, 'topPResolved': False},
              'limitations': base.LIMITATIONS+forward.LIMITATIONS+[
                  'Full-context 1e-3 parity failed previously; this exact sequential contract neither establishes nor waives it.',
                  'All three arms use original online_forward with supplied actions; no batched-full policy call.',
                  'Probe placeholders are not labels. Later probe teacher-forced heads may depend on their placeholder prefix.',
                  'Raw sampling is unmasked here and live. Live configured-key/freshness/world gates reject whole proposals afterward.',
                  'Offline raw-action sensitivity is not the production accepted/executed action distribution.']}
    started = time.perf_counter()
    try:
        report['priorFailedFullContextExperiment'] = historical_provenance()
        report['packagedSource'] = {'version': 1, 'historicalRunnerExecutedHere': False,
                                    'numericalContract': 'unchanged exact sequential gates; no full-context parity claim'}
        report['dependencyVersions'] = dependency_versions()
        args.ffmpeg, args.ffprobe = resolve_decoder(args.ffmpeg), resolve_decoder(args.ffprobe)
        report['resolvedDecoderExecutables'] = {'ffmpeg': args.ffmpeg, 'ffprobe': args.ffprobe}
        cases = [load_case(path, int(fid)) for path, fid in args.case]
        relocations = goal_artifact_relocations(args.goal_artifact, cases)
        codec = base.ActionCodec(args.source)
        prepared, evidence, codec_gate = base.prepare_inputs(cases, codec, output, args.ffmpeg, args.ffprobe,
                                                            goal_artifacts=relocations)
        report.update(cases=evidence, cpuCodecGate=codec_gate, cpuInputGate=verify_prepared_inputs(prepared))
        report['recordedLiveAdmission'] = [{'key': case['key'], 'reportEvidence': case['inputEvidence']['report'],
                                           **case['liveAdmission']} for case in cases]
        report['preparerEvidence'] = cases[0]['preparerEvidence']
        for case in cases:
            base.require(base.digest(case['planEvidence']['path']) == case['planEvidence'], 'plan changed during decode')
            verify_preparers({'preparerEvidence': case['preparerEvidence']})
        paths = sorted((args.source/'elefant/policy_model').glob('*.py'))
        paths += [args.source/path for path in ('elefant/im_tokenizer/conv_tokenizer.py', 'elefant/torch/__init__.py',
                                               'elefant/torch/util.py', 'config/policy_model/150M.yaml')]
        paths += [base.TOOLS/name for name in ('p2p_loader.py', 'p2p_compat_attention.py', 'p2p_rotary.py',
                                             'goal_embedding.py', 'observation_profiles.py', 'model_adapters.py', 'stream_client.py')]
        report['sourceEvidence'] = [base.digest(path) for path in paths]
        report['upstreamRevision'] = subprocess.run(['git', '-C', str(args.source), 'rev-parse', 'HEAD'],
                                                    capture_output=True, text=True, check=True).stdout.strip()
        base.require(report['upstreamRevision'] == forward.PUBLISHED_REFERENCE['openP2pRevision'], 'unexpected upstream revision')
        report['decoderToolEvidence'] = [base.digest(args.ffmpeg), base.digest(args.ffprobe)]
        report['status'] = 'cpu-preflight-passed'
        base.save_report(report_path, report)
        if args.execute_gpu:
            report['status'] = 'validating-forward-sequential-parity'
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
