"""OFFLINE research prototype. GPU/model loading requires explicit --execute-gpu.

Default operation validates supplied evidence and decodes saved video on the CPU.
No controller, capture, resident client, training, or application APIs are used.
"""
from __future__ import annotations
import argparse
import ast
from bisect import bisect_left
from collections import namedtuple
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace
from typing import List

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / 'tools/bettergi-agent'
sys.path.insert(0, str(TOOLS))
SOURCE = ROOT / 'artifacts/agent/sources/open-p2p'
CHECKPOINT = ROOT / 'artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt'
RTOL, ATOL = 1e-3, 1e-3
LIMITATIONS = [
    'OFFLINE diagnostic only; trainingEligible and productionEligible are false.',
    'Decoded H.264/yuv420p pixels are not the RGB bytes originally seen live.',
    'Receipt labels are backend-dispatch intent on first-acquisition time, not physical game input.',
    'Sorted re-encoded controller actions are proxies; original sampled IDs/order are unavailable.',
    'Forty real history images plus one probe are a cold context, not restoration of the live 200-frame cache.',
    'Irregular image times remain irregular; no timestep, image, no-op, or mouse event is invented.',
    'Goal files are checked against recorded metadata and hashed now; original recordings did not hash embedding bytes.',
    'Windows FP16/dense-SDPA compatibility path, not the original BF16/FlexAttention environment.',
    'Instrumentation and shared application load make elapsed times diagnostic, not throughput benchmarks.',
    'Action/logit differences establish sensitivity only, not task success or a quality improvement.',
]


class GateFailure(RuntimeError):
    """A failed evidence/parity contract prohibits comparison results."""


def require(ok, reason):
    """Fail without changing a tolerance or substituting missing evidence."""
    if not ok:
        raise GateFailure(reason)


def digest(path):
    """Hash a stable local file in bounded memory."""
    path = Path(path)
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'file changed while hashing')
    return {'path': str(path.resolve()), 'bytes': after.st_size, 'sha256': h.hexdigest()}


def canonical(value):
    """Compare JSON representations, including tuple-to-list normalization."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def save_report(path, report):
    """Publish a complete report atomically, including failures."""
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False, suffix='.tmp') as stream:
        temp = Path(stream.name)
        json.dump(report, stream, indent=2, allow_nan=False)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class ActionCodec:
    """Strict controller-to-upstream codec, using pinned source constants on the CPU."""
    def __init__(self, source=SOURCE):
        self.path = Path(source) / 'elefant/data/action_mapping.py'
        self.tree = ast.parse(self.path.read_text(encoding='utf-8'))
        constants = {}
        names = {'UniversalAutogressiveKeyboardEncodingMap', 'MouseKeyActionMapping',
                 'MOUSE_X_BIN_EDGES', 'MOUSE_Y_BIN_EDGES'}
        for node in self.tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        constants[target.id] = ast.literal_eval(node.value)
        require(set(constants) == names, 'upstream codec constants changed')
        self.constants = constants
        self.keys = {}
        for key, index in constants['UniversalAutogressiveKeyboardEncodingMap'].items():
            if index is None or index == 0:
                continue
            name = {'Space': 'SPACE', 'LeftShift': 'LSHIFT', 'RightShift': 'RSHIFT'}.get(key, key.upper())
            if name.endswith('ARROW'):
                name = name[:-5]
            require(name not in self.keys, 'ambiguous canonical key')
            self.keys[name] = (key, index)
        self.buttons = {'LBUTTON': '0', 'RBUTTON': '1', 'MBUTTON': '2'}
        # The official implementation stores edges as float32 before bucketize(right=False).
        self.edges = [[struct.unpack('<f', struct.pack('<f', x))[0] for x in constants[name]]
                      for name in ('MOUSE_X_BIN_EDGES', 'MOUSE_Y_BIN_EDGES')]
        require(all(a < b for edges in self.edges for a, b in zip(edges, edges[1:])), 'unordered mouse edges')

    def components(self, label):
        """Reject unsupported/ambiguous aliases and overflow instead of truncating silently."""
        held = label.get('heldKeys')
        require(isinstance(held, list) and all(isinstance(x, str) for x in held)
                and len(set(held)) == len(held), 'invalid held-key state')
        require(all(k in self.keys or k in self.buttons for k in held), 'unknown or ambiguous controller key')
        keys = sorted((self.keys[k] for k in held if k in self.keys), key=lambda pair: pair[1])
        buttons = sorted((self.buttons[k] for k in held if k in self.buttons), key=int)
        require(len(keys) <= 4 and len(buttons) <= 2, 'action exceeds checkpoint capacity')
        deltas = [label.get('mouseDx'), label.get('mouseDy')]
        require(all(type(x) is int and -(2**63) <= x < 2**63 for x in deltas), 'invalid integer mouse delta')
        return keys, buttons, deltas

    def encode(self, label):
        """Return four key IDs, two button IDs, and two mouse-bin IDs."""
        keys, buttons, deltas = self.components(label)
        ids = [v for _, v in keys] + [0] * (4-len(keys))
        mouse = [self.constants['MouseKeyActionMapping'][b] for b in buttons]
        return ids + mouse + [0] * (2-len(mouse)) + [bisect_left(e, x) for e, x in zip(self.edges, deltas)]

    def validate_upstream(self, labels):
        """Execute only the pinned action_to_tensor method on CPU; no policy or CUDA import path."""
        import torch
        mapping = next(n for n in self.tree.body if isinstance(n, ast.ClassDef)
                       and n.name == 'UniversalAutoregressiveActionMapping')
        method = next(n for n in mapping.body if isinstance(n, ast.FunctionDef) and n.name == 'action_to_tensor')
        Structured = namedtuple('StructuredAction', 'keys mouse_buttons mouse_delta_x mouse_delta_y')
        namespace = dict(torch=torch, logging=logging, List=List, StructuredAction=Structured,
                         shared_pb2=SimpleNamespace(Vec2Int=object), **self.constants)
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(self.path), 'exec'), namespace)
        instance = SimpleNamespace(get_number_of_keyboard_actions=lambda: 4, get_number_of_mouse_button_actions=lambda: 2,
                                   _mouse_delta_x_edges=torch.tensor(self.edges[0], dtype=torch.float32),
                                   _mouse_delta_y_edges=torch.tensor(self.edges[1], dtype=torch.float32))
        for label in labels:
            keys, buttons, deltas = self.components(label)
            result = namespace['action_to_tensor'](instance, [k for k, _ in keys], buttons,
                                                   SimpleNamespace(x=torch.tensor(deltas[0]), y=torch.tensor(deltas[1])))
            actual = [int(v) for field in result for v in field.reshape(-1).tolist()]
            require(actual == self.encode(label), 'CPU upstream action codec parity failed')
        return {'passed': True, 'labels': len(labels), 'source': digest(self.path), 'device': 'cpu'}


def load_case(plan_path, probe_id, include_grid=False):
    """Reproduce one explicitly selected prepared window from its unchanged original evidence."""
    from prepare_replay import prepare
    from observation_profiles import verify_hello
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    require(plan.get('status') == 'prepared' and plan.get('trainingEligible') is False
            and plan.get('inferenceExecuted') is False, 'invalid prepared plan')
    matches = [w for w in plan['windows'] if w['probe']['frameId'] == probe_id]
    require(len(matches) == 1, 'explicit probe absent or ambiguous in plan')
    window = matches[0]
    p = plan['parameters']
    require(p['historyFrames'] == 40, 'this bounded prototype requires 40 history frames')
    require(window.get('probeLabel') is None, 'probe must be unlabelled')
    expected = plan['inputEvidence']
    require(set(expected) == {'report', 'observations.jsonl', 'frames.jsonl', 'events.jsonl', 'recording.json', 'frames.mp4'},
            'unexpected evidence manifest')
    payload = {}
    for name, entry in expected.items():
        require(digest(entry['path']) == entry, 'changed prepared input: ' + name)
        if name.endswith('.jsonl'):
            payload[name] = [json.loads(x) for x in Path(entry['path']).read_text(encoding='utf-8').splitlines() if x.strip()]
        elif name != 'frames.mp4':
            payload[name] = json.loads(Path(entry['path']).read_text(encoding='utf-8'))
    reproduced = prepare(payload['report'], payload['observations.jsonl'], payload['frames.jsonl'], payload['events.jsonl'],
                         payload['recording.json'], history_frames=40, max_windows=1, probe_frame_ids=[probe_id],
                         comparison_mode=plan['comparisonMode'], nominal_hz=p['nominalHz'] or 20,
                         max_jitter_ms=p['maxJitterMs'] or 20, max_source_gap_ms=p['maxSourceGapMs'],
                         probe_spacing_ms=p['probeSpacingMs'])
    require(len(reproduced['windows']) == 1, 'selected window no longer passes preparation')
    strip = lambda w: {k: v for k, v in w.items() if k != 'windowId'}
    require(canonical(strip(reproduced['windows'][0])) == canonical(strip(window)), 'prepared window does not reproduce')
    profile_contract = verify_hello(payload['report']['hello'], plan['observationProfile'], 'open-p2p')
    arm_names = ['accepted_proxy', 'receipt_same_frames']
    if include_grid:
        require('receipt_nominal_20hz' in window['arms'], 'requested grid arm absent from prepared plan')
        arm_names.append('receipt_nominal_20hz')
    return {'key': f'{plan_path.stem}-probe-{probe_id}', 'planEvidence': digest(plan_path), 'inputEvidence': expected,
            'window': window, 'armNames': arm_names, 'observationProfile': plan['observationProfile'],
            'profileContract': profile_contract,
            'encodedFrames': payload['recording.json']['encodedFrames'], 'capturePollHz': payload['report']['capturePollHz']}


def load_case_goal(case, goal_artifacts=None):
    """Retain the exact recorded goal metadata and currently verified artifact bytes."""
    import numpy as np
    from goal_embedding import load_goal
    provenance = case['window']['goalProvenance']
    metadata = provenance['goalMetadata']
    if metadata is None:
        return np.zeros((1, 768), dtype=np.float32), {'mode': 'recorded-no-text', 'provenance': provenance}
    require(isinstance(metadata, dict) and isinstance(metadata.get('file'), str), 'goal artifact path missing')
    relocation = (goal_artifacts or {}).get(metadata['file'])
    path = relocation['path'] if relocation else metadata['file']
    evidence = digest(path)
    if relocation:
        require(evidence['sha256'] == relocation['sha256'], 'relocated goal artifact hash mismatch')
    embedding, actual = load_goal(path)
    if relocation:
        require({key: value for key, value in actual.items() if key != 'file'} ==
                {key: value for key, value in metadata.items() if key != 'file'},
                'goal artifact metadata differs from recorded goal')
    else:
        require(actual == metadata, 'goal artifact metadata differs from recorded goal')
    require(digest(path) == evidence, 'goal artifact changed during load')
    result = {'mode': 'recorded-artifact', 'fileEvidence': evidence, 'provenance': provenance,
              'float32EmbeddingSha256': hashlib.sha256(embedding.tobytes()).hexdigest()}
    if relocation:
        # The supplied digest is auditable, but the old recording did not attest it.
        result['relocation'] = {'recordedPath': metadata['file'], 'resolvedPath': str(Path(path).resolve()),
                                'expectedSha256': relocation['sha256'], 'identitySource': 'caller-supplied-sha256',
                                'recordingAttestsArtifactHash': False}
    return embedding, result


def decode_indexed(video, references, encoded_frames, ffmpeg, ffprobe, diagnostics):
    """Decode selected absolute frame indexes, without seeking or resampling video time."""
    import numpy as np
    require(references, 'no requested images')
    width, height = references[0]['width'], references[0]['height']
    require(all((r['width'], r['height']) == (width, height) for r in references), 'video geometry changed')
    probe_command = [ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-show_frames',
               '-show_entries', 'stream=width,height,pix_fmt:frame=best_effort_timestamp_time', '-of', 'json', str(video)]
    result = subprocess.run(probe_command, capture_output=True, check=True, timeout=90)
    meta = json.loads(result.stdout)
    require(len(meta['streams']) == 1 and (meta['streams'][0]['width'], meta['streams'][0]['height']) == (width, height),
            'encoded video dimensions mismatch')
    require(len(meta['frames']) == encoded_frames, 'actual decoded frame count mismatch')
    indexes = sorted(set(r['videoFrameIndex'] for r in references))
    require(all(type(i) is int and 0 <= i < encoded_frames for i in indexes), 'invalid video frame index')
    for ref in references:
        pts = float(meta['frames'][ref['videoFrameIndex']]['best_effort_timestamp_time'])
        require(abs(pts-ref['videoPtsSeconds']) <= 0.000002, 'actual video PTS/index join mismatch')
    selected = '+'.join(f'eq(n\\,{i})' for i in indexes)
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-hwaccel', 'none', '-threads', '1', '-i', str(video),
               '-map', '0:v:0', '-vf', 'select=' + selected, '-fps_mode', 'passthrough', '-threads', '1', '-pix_fmt', 'rgb24',
               '-f', 'rawvideo', 'pipe:1']
    result = subprocess.run(command, capture_output=True, check=True, timeout=90)
    size = width*height*3
    require(len(result.stdout) == len(indexes)*size, 'selected decoded byte count mismatch')
    diagnostics.update(ffprobeCommand=probe_command,
                       decodedFrameCount=encoded_frames, selectedIndexes=indexes, encodedPixelFormat=meta['streams'][0]['pix_fmt'],
                       decodeCommand=command, outputPixelFormat='rgb24')
    return {i: np.frombuffer(result.stdout[j*size:(j+1)*size], dtype=np.uint8).reshape(height, width, 3).copy()
            for j, i in enumerate(indexes)}


def prepare_inputs(cases, codec, output, ffmpeg, ffprobe, *, goal_artifacts=None):
    """Save the exact decoded/preprocessed tensor inputs and re-encoded action IDs before any model load."""
    import numpy as np
    from PIL import Image
    from observation_profiles import prepare_p2p_image
    all_labels, evidence, prepared = [], [], []
    for case in cases:
        w = case['window']
        references = [s['frame'] for name in case['armNames'] for s in w['arms'][name]['samples']] + [w['probe']]
        decode_info = {}
        pixels = decode_indexed(case['inputEvidence']['frames.mp4']['path'], references, case['encodedFrames'],
                                ffmpeg, ffprobe, decode_info)
        goal, goal_evidence = load_case_goal(case, goal_artifacts)
        item = {'key': case['key'], 'probeFrameId': w['probe']['frameId'], 'goal': goal, 'arms': {}}
        record = {'key': case['key'], 'probeFrameId': w['probe']['frameId'], 'planEvidence': case['planEvidence'],
                  'inputEvidence': case['inputEvidence'], 'window': w, 'decode': decode_info,
                  'goalEvidence': goal_evidence, 'profileContract': case['profileContract'], 'arms': {}}
        for name in case['armNames']:
            arm = w['arms'][name]
            require(len(arm['samples']) == 40, 'incorrect history length')
            refs = [s['frame'] for s in arm['samples']] + [w['probe']]
            require(len({tuple(r['sourceIdentity']) for r in refs}) == 41, 'duplicate or probe history identity')
            arrays, image_evidence = [], []
            for ref in refs:
                raw = pixels[ref['videoFrameIndex']]
                processed = prepare_p2p_image(Image.fromarray(raw), case['observationProfile'], case['profileContract']['profile'])
                rgb = np.asarray(processed, dtype=np.uint8)
                require(rgb.shape == (192, 192, 3), 'wrong model image shape')
                arrays.append(rgb)
                image_evidence.append({'frameId': ref['frameId'], 'videoFrameIndex': ref['videoFrameIndex'],
                                       'decodedRgbSha256': hashlib.sha256(raw.tobytes()).hexdigest(),
                                       'modelRgbSha256': hashlib.sha256(rgb.tobytes()).hexdigest()})
            labels = [s['label'] for s in arm['samples']]
            all_labels.extend(labels)
            # This final shape placeholder is not a labelled image or a member of history.
            placeholder = codec.encode({'heldKeys': [], 'mouseDx': 0, 'mouseDy': 0})
            tokens = np.asarray([codec.encode(label) for label in labels] + [placeholder], dtype=np.int64)
            frames = np.stack(arrays)
            archive = output / f'{case["key"]}-{name}-inputs.npz'
            np.savez_compressed(archive, rgb=frames, actionTokens=tokens, goal=goal)
            item['arms'][name] = {'frames': frames, 'tokens': tokens}
            record['arms'][name] = {'inputArchive': digest(archive), 'images': image_evidence,
                                    'historyTokenIds': tokens[:-1].tolist(), 'probeShapePlaceholder': tokens[-1].tolist(),
                                    'probeIsLabelled': False}
        prepared.append(item)
        evidence.append(record)
    # Include zero and outer-bin cases, in addition to every actual supplied label.
    probes = [{'heldKeys': [], 'mouseDx': x, 'mouseDy': y} for x, y in [(0, 0), (-2000, -2000), (2000, 2000)]]
    codec_gate = codec.validate_upstream(all_labels + probes)
    for case in cases:
        for entry in case['inputEvidence'].values():
            require(digest(entry['path']) == entry, 'recorded input changed during decoding')
    return prepared, evidence, codec_gate


def numeric_gate(name, actual, expected, report, report_path, *, exact=False):
    """Record full error diagnostics before enforcing the unchanged tolerance."""
    import torch
    require(actual.shape == expected.shape and actual.dtype == expected.dtype, name + ': shape/dtype mismatch')
    a, b = actual.detach().float(), expected.detach().float()
    diff = (a-b).abs()
    tolerance = torch.zeros_like(diff) if exact else ATOL + RTOL*b.abs()
    finite = bool(torch.isfinite(a).all() and torch.isfinite(b).all())
    passed = finite and bool((diff <= tolerance).all())
    gate = {'name': name, 'passed': passed, 'exact': exact, 'rtol': 0 if exact else RTOL, 'atol': 0 if exact else ATOL,
            'shape': list(a.shape), 'dtype': str(actual.dtype), 'finite': finite,
            'maxAbsoluteError': float(diff.max()) if finite else None,
            'maxRelativeError': float((diff/b.abs().clamp_min(1e-12)).max()) if finite else None,
            'outsideTolerance': int((diff > tolerance).sum()) if finite else None}
    report['parityGates'].append(gate)
    if not passed:
        save_report(report_path, report)
    require(passed, name + ': numerical parity failed')


def structured(tokens, Structured):
    """Split [B,T,8] IDs without altering order."""
    return Structured(tokens[..., :4], tokens[..., 4:6], tokens[..., 6:7], tokens[..., 7:8])


def action_head(model, index):
    """Select the same prediction head as the upstream sampler."""
    return model.keyboard_out_logits if index < 4 else model.mouse_button_out_logits if index < 6 else (
        model.mouse_delta_x_out_logits if index == 6 else model.mouse_delta_y_out_logits)


def upstream_full_logits(source, Structured, eager_assert):
    """Extract the unchanged official head method, retaining its full-context batching geometry."""
    import torch
    path = Path(source) / 'elefant/policy_model/stage3_finetune.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    trainer = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PolicyModelTrainer')
    method = next(n for n in trainer.body if isinstance(n, ast.FunctionDef) and n.name == 'action_out_tokens_to_logits')
    namespace = dict(torch=torch, StructuredAction=Structured, eager_assert=eager_assert)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['action_out_tokens_to_logits']


def forced_sampler(model, desired, logits):
    """Supply actual history IDs through the original online decoder/cache update API."""
    def sample(hidden, index, result):
        logits.append(action_head(model, index)(hidden).detach().clone())
        token = desired[index].reshape(1, 1)
        if index < 4:
            result.keys[:, index] = token[:, 0]
            return model.key_action_embedding(token)
        if index < 6:
            result.mouse_buttons[:, index-4] = token[:, 0]
            return model.mouse_button_embedding(token)
        if index == 6:
            result.mouse_delta_x[:, 0] = token[:, 0]
            return model.mouse_delta_x_embedding(token)
        result.mouse_delta_y[:, 0] = token[:, 0]
        return model.mouse_delta_y_embedding(token)
    return sample


def incremental_reference(model, frames, goals, tokens):
    """Replay original two-pass online_forward with supplied IDs; never sample fake history."""
    import torch
    state = model.bc_transformer.init_kv_cache_state()
    idx = torch.tensor(0, dtype=torch.int64, device='cuda')
    contexts, logits = [], [[] for _ in range(8)]
    def remember(_module, args):
        contexts.append(args[0].detach().clone())
    hook = model.bc_transformer.action_decoder.input_proj.register_forward_pre_hook(remember)
    try:
        for i in range(41):
            step_logits = []
            result, idx, state = model.bc_transformer.online_forward(
                model._normalize_frames(frames[:, i:i+1]), goals[0, i], idx, state, should_grow_cache=True,
                action_sampler=forced_sampler(model, tokens[0, i], step_logits),
                empty_sampled_action_fn=model.action_mapping.make_empty_action, reshape_structured_action_fn=None,
                action_in_to_tokens_fn=model.action_in_to_tokens)
            actual = torch.cat([x.reshape(-1) for x in result])
            require(torch.equal(actual, tokens[0, i]), 'incremental supplied action was not committed exactly')
            require(len(step_logits) == 8 and len(contexts) == i+1, 'unexpected incremental decoder calls')
            for j, value in enumerate(step_logits):
                logits[j].append(value)
    finally:
        hook.remove()
    require(int(idx) == 41*12, 'unexpected final temporal position')
    return torch.cat(contexts, dim=1), [torch.cat(values, dim=1) for values in logits]


def sample_probe(model, context, seed):
    """Use explicit paired CUDA uniform values and separately paired CPU mouse RNG."""
    import torch
    generator = torch.Generator(device='cuda').manual_seed(seed)
    uniform = torch.rand(8, generator=generator, device='cuda')
    logits = []
    def sample(hidden, index, result):
        logits.append(action_head(model, index)(hidden).detach().clone())
        return model._keyboard_mouse_action_sampler(hidden, index, result, 1.0, uniform)
    action = model.bc_transformer.action_decoder.autogressive_sample(
        context, sample, model.action_mapping.make_empty_action, inference_mode=True)
    ids = [int(x) for field in action for x in field.reshape(-1).tolist()]
    with torch.device('cpu'), torch.autocast('cuda', enabled=False), torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(seed)
        decoded = model.action_mapping.tensor_to_action(action, mouse_sampling_approach='truncated_normal')
    return {'seed': seed, 'uniforms': uniform.cpu().tolist(), 'tokenIds': ids,
            'decoded': {'keys': list(decoded.keys), 'mouseButtons': list(decoded.mouse_buttons),
                        'dx': float(decoded.mouse_delta_x), 'dy': float(decoded.mouse_delta_y)},
            'logits': [x.float().cpu().reshape(-1).tolist() for x in logits]}, logits


def execute_model(args, prepared, report, output, report_path, codec):
    """The sole model-loading boundary; called only after explicit --execute-gpu."""
    import numpy as np
    import torch
    import yaml
    from p2p_loader import load_model
    require(torch.cuda.is_available(), 'CUDA unavailable')
    report['checkpointEvidence'] = digest(args.checkpoint)
    checkpoint_config = Path(args.checkpoint).parent / 'model_config.yaml'
    report['checkpointConfigEvidence'] = digest(checkpoint_config)
    inference = yaml.safe_load(checkpoint_config.read_text(encoding='utf-8'))['inference']
    require(inference['mouse_sampling_approach'] == 'truncated_normal' and inference['sampling_temperature'] == 1.0,
            'checkpoint sampling defaults differ from this diagnostic')
    started = time.perf_counter()
    report['modelLoadAttempted'] = True
    model, config, manifest = load_model(args.source, args.checkpoint, output / 'isolated-source', history=41)
    report.update(modelLoaded=True, modelLoadMs=(time.perf_counter()-started)*1000,
                  compatibility=manifest, device=torch.cuda.get_device_name(), torchVersion=torch.__version__)
    require(config.shared.n_seq_timesteps == 41 and model.action_mapping.get_seq_len() == 8, 'wrong checkpoint geometry')
    from elefant.data.action_mapping import StructuredAction
    from elefant.torch import eager_assert
    full_logit_method = upstream_full_logits(args.source, StructuredAction, eager_assert)
    results = []
    with torch.inference_mode(), torch.device('cuda'), torch.autocast('cuda', dtype=torch.float16):
        for case in prepared:
            case_result = {'key': case['key'], 'probeFrameId': case['probeFrameId'], 'arms': {}}
            report['validationEvidence'].append(case_result)
            for name, arm in case['arms'].items():
                prefix = case['key'] + '/' + name
                frames = torch.as_tensor(arm['frames'].transpose(0, 3, 1, 2).copy(), device='cuda').unsqueeze(0)
                tokens = torch.as_tensor(arm['tokens'], device='cuda').unsqueeze(0)
                goals = torch.as_tensor(case['goal'], device='cuda', dtype=torch.float16)[None, None].expand(1, 41, 1, 768).contiguous()
                normalized = model._normalize_frames(frames)
                embeddings = model.action_in_to_tokens(structured(tokens, StructuredAction))
                report['inferenceExecuted'] = True
                full_embeddings, contexts, *_ = model.bc_transformer(normalized, embeddings, goals)
                full_logits = [field[:, :, i] for field in full_logit_method(model, full_embeddings)
                               for i in range(field.shape[2])]
                alternate = tokens.clone()
                alternate[0, -1] = torch.tensor(codec.encode({'heldKeys': ['W', 'LBUTTON'], 'mouseDx': 2000, 'mouseDy': -2000}), device='cuda')
                _, alternate_contexts, *_ = model.bc_transformer(normalized, model.action_in_to_tokens(structured(alternate, StructuredAction)), goals)
                arm_result = {'samples': []}
                case_result['arms'][name] = arm_result
                arrays = {f'fullLogits{i}': value.float().cpu().numpy() for i, value in enumerate(full_logits)}
                arrays.update(fullContexts=contexts.float().cpu().numpy(), placeholderContexts=alternate_contexts.float().cpu().numpy())
                dump = output / f'{case["key"]}-{name}-parity.npz'
                np.savez_compressed(dump, **arrays)
                arm_result['parityArrays'] = digest(dump)
                numeric_gate(prefix + '/probe-placeholder', alternate_contexts, contexts, report, report_path, exact=True)
                incremental, inc_logits = incremental_reference(model, frames, goals, tokens)
                arrays.update(incrementalContexts=incremental.float().cpu().numpy(),
                              **{f'incrementalLogits{i}': v.float().cpu().numpy() for i, v in enumerate(inc_logits)})
                np.savez_compressed(dump, **arrays)
                arm_result['parityArrays'] = digest(dump)
                numeric_gate(prefix + '/all-contexts', incremental, contexts, report, report_path)
                for i in range(8):
                    numeric_gate(prefix + f'/teacher-forced-logits-{i}', inc_logits[i], full_logits[i], report, report_path)
                for seed in range(args.first_seed, args.first_seed + args.seeds):
                    full, full_sample_logits = sample_probe(model, contexts[:, -1:], seed)
                    inc, inc_sample_logits = sample_probe(model, incremental[:, -1:], seed)
                    pair = {'seed': seed, 'full': full, 'incremental': inc,
                            'tokensExact': full['tokenIds'] == inc['tokenIds'], 'decodedExact': full['decoded'] == inc['decoded']}
                    arm_result['samples'].append(pair)
                    save_report(report_path, report)
                    require(pair['tokensExact'] and pair['decodedExact'], prefix + ': complete sampled action parity failed')
                    for i in range(8):
                        numeric_gate(prefix + f'/seed-{seed}-logits-{i}', inc_sample_logits[i], full_sample_logits[i], report, report_path)
            results.append(case_result)
    # No comparison summaries are published until every numerical/action gate passes.
    comparisons = []
    for case in results:
        baseline = case['arms']['accepted_proxy']['samples']
        for name, arm in case['arms'].items():
            if name == 'accepted_proxy':
                continue
            pairs = []
            for a, b in zip(baseline, arm['samples']):
                x, y = a['full'], b['full']
                pairs.append({'seed': x['seed'], 'tokenIdsEqual': x['tokenIds'] == y['tokenIds'],
                              'decodedEqual': x['decoded'] == y['decoded'],
                              'maxLogitDifferenceByComponent': [max(abs(p-q) for p, q in zip(l, r)) for l, r in zip(x['logits'], y['logits'])]})
            if case['probeFrameId'] == args.negative_control_probe and name == 'receipt_same_frames':
                require(all(p['tokenIdsEqual'] and p['decodedEqual'] and max(p['maxLogitDifferenceByComponent']) == 0 for p in pairs),
                        'identical-label negative control failed')
            comparisons.append({'key': case['key'], 'arm': name, 'pairedSeeds': pairs,
                                'meaning': 'offline action-history sensitivity only; no quality or success label'})
    report.update(comparisons=comparisons, comparisonEligible=True, status='complete',
                  peakAllocatedVramBytes=torch.cuda.max_memory_allocated())


def parse_args(argv=None):
    """Require explicit cases; GPU execution is a separate opt-in."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', nargs=2, action='append', required=True, metavar=('PLAN', 'PROBE_ID'))
    p.add_argument('--negative-control-probe', type=int, required=True)
    p.add_argument('--include-grid', action='store_true')
    p.add_argument('--seeds', type=int, default=32, choices=range(1, 33))
    p.add_argument('--first-seed', type=int, default=1731)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', type=Path, default=SOURCE)
    p.add_argument('--checkpoint', type=Path, default=CHECKPOINT)
    p.add_argument('--ffmpeg', default='ffmpeg', help='FFmpeg executable path or command on PATH')
    p.add_argument('--ffprobe', default='ffprobe', help='FFprobe executable path or command on PATH')
    p.add_argument('--goal-artifact', nargs=3, action='append', default=[],
                   metavar=('RECORDED_PATH', 'LOCAL_FILE', 'EXPECTED_SHA256'),
                   help='Explicit hash-bound relocation; does not attest historical embedding identity')
    p.add_argument('--execute-gpu', action='store_true')
    args = p.parse_args(argv)
    require(1 <= len(args.case) <= 3, 'one to three explicit cases are allowed')
    require(0 <= args.first_seed < 2**31 - 32, 'invalid seed range')
    return args


def main(argv=None):
    """Prepare CPU inputs by default; retain terminal failures without comparison claims."""
    args = parse_args(argv)
    output = args.output.resolve()
    require(not output.exists(), 'output directory already exists; preserve earlier evidence')
    output.mkdir(parents=True)
    report_path = output / 'report.json'
    report = {'status': 'preparing', 'offlineOnly': True, 'trainingEligible': False, 'productionEligible': False,
              'inferenceExecuted': False, 'modelLoadAttempted': False, 'modelLoaded': False,
              'comparisonEligible': False, 'comparisons': [], 'validationEvidence': [],
              'parityGates': [], 'limitations': LIMITATIONS, 'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              'runnerEvidence': digest(__file__), 'numericTolerance': {'rtol': RTOL, 'atol': ATOL},
              'sampling': {'temperature': 1.0, 'mouse': 'truncated_normal', 'pairedUniformCount': 8,
                           'seedCount': args.seeds, 'firstSeed': args.first_seed}}
    started = time.perf_counter()
    try:
        cases = [load_case(path, int(fid), args.include_grid) for path, fid in args.case]
        require(len({c['key'] for c in cases}) == len(cases), 'duplicate case')
        negative = [c for c in cases if c['window']['probe']['frameId'] == args.negative_control_probe]
        require(len(negative) == 1, 'negative-control probe must name exactly one explicit case')
        codec = ActionCodec(args.source)
        prepared, evidence, cpu_gate = prepare_inputs(cases, codec, output, args.ffmpeg, args.ffprobe)
        report.update(cases=evidence, cpuCodecGate=cpu_gate)
        control = next(c for c in prepared if c['probeFrameId'] == args.negative_control_probe)
        import numpy as np
        a, b = (control['arms'][name] for name in ('accepted_proxy', 'receipt_same_frames'))
        require(np.array_equal(a['frames'], b['frames']) and np.array_equal(a['tokens'], b['tokens']),
                'negative control does not have identical image/token inputs')
        report['negativeControlInputsExact'] = True
        paths = sorted((args.source / 'elefant/policy_model').glob('*.py'))
        paths += [args.source / path for path in ('elefant/im_tokenizer/conv_tokenizer.py', 'elefant/torch/__init__.py', 'elefant/torch/util.py',
                                                'config/policy_model/150M.yaml')]
        paths += [TOOLS / name for name in ('p2p_loader.py', 'p2p_compat_attention.py', 'p2p_rotary.py', 'goal_embedding.py', 'observation_profiles.py')]
        report['sourceEvidence'] = [digest(p) for p in paths]
        report['upstreamRevision'] = subprocess.run(['git', '-C', str(args.source), 'rev-parse', 'HEAD'],
                                                     capture_output=True, text=True, check=True).stdout.strip()
        report['decoderToolEvidence'] = [digest(args.ffmpeg), digest(args.ffprobe)]
        report['status'] = 'cpu-preflight-passed'
        save_report(report_path, report)
        if args.execute_gpu:
            report['status'] = 'validating-model-parity'
            execute_model(args, prepared, report, output, report_path, codec)
    except Exception as exc:
        report.update(status='blocked', comparisonEligible=False, comparisons=[], error=str(exc), traceback=traceback.format_exc())
    finally:
        report['elapsedSeconds'] = time.perf_counter()-started
        save_report(report_path, report)
    print(json.dumps({'status': report['status'], 'inferenceExecuted': report['inferenceExecuted'],
                      'comparisonEligible': report['comparisonEligible'], 'report': str(report_path), 'error': report.get('error')}))
    return 0 if report['status'] in ('cpu-preflight-passed', 'complete') else 2


if __name__ == '__main__':
    raise SystemExit(main())
