"""Real pretrained policies with explicit compatibility and action boundaries."""
from collections import deque
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch
from PIL import Image


KEYS = {'Space': 'SPACE', 'Shift': 'LSHIFT', 'Ctrl': 'LCONTROL',
        'Esc': 'ESCAPE', 'LB': 'LBUTTON', 'RB': 'RBUTTON', 'MB': 'MBUTTON',
        'LeftShift': 'LSHIFT', 'RightShift': 'RSHIFT', 'Control': 'LCONTROL'}
DIGITS = dict(zip(('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'), '0123456789'))
FUNCTIONS = dict(zip(('One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve'), ('F' + str(i) for i in range(1, 13))))
# Open P2P names direction keys LeftArrow/etc.; the bridge uses Windows LEFT/etc.
ARROWS = {'LEFTARROW': 'LEFT', 'RIGHTARROW': 'RIGHT', 'UPARROW': 'UP', 'DOWNARROW': 'DOWN'}


def canonical_key(key):
    """Preserve key meaning, including case-sensitive digits/function keys."""
    canonical = DIGITS.get(key, FUNCTIONS.get(key, KEYS.get(key, key.upper())))
    return ARROWS.get(canonical, canonical)


def gamescaling_steps(action, width, height):
    """Apply the whole-chunk per-mille mouse delta once, never six times."""
    if not action.parsed or action.truncated or action.dropped:
        return []
    if not all(math.isfinite(value) for value in action.mouse):
        return []
    return [{'durationMs': 33 if index < 5 else 35,
             'keys': [canonical_key(key) for key in keys],
             'mouseDx': round(action.mouse[0] * width / 1000) if index == 0 else 0,
             'mouseDy': round(action.mouse[1] * height / 1000) if index == 0 else 0}
            for index, keys in enumerate(action.steps)]


def complete_gamescaling_action(text, action):
    """Reject truncated, nonfinite, overlong or silently repaired action strings."""
    if not action.parsed or action.truncated or action.dropped or '<|action_end|>' not in text:
        return False
    groups = action.body.split(';')
    if len(groups) != 7 or any(len(group.split()) > 4 for group in groups[1:]):
        return False
    numbers = groups[0].split()
    try:
        return len(numbers) == 3 and all(math.isfinite(float(value)) for value in numbers)
    except ValueError:
        return False


class FirstTokenClock:
    """Measure first generated token separately from a complete usable action."""
    def __init__(self):
        self.skip_prompt = True
        self.first_ns = None

    def put(self, value):
        if self.skip_prompt:
            self.skip_prompt = False
        elif self.first_ns is None:
            torch.cuda.synchronize()
            self.first_ns = time.perf_counter_ns()

    def end(self):
        pass


class GameScalingAdapter:
    """Use the checkpoint template and original action-only prompt on Windows."""
    def __init__(self, checkpoint, source, history=0, max_new_tokens=96,
                 image_width=384, dtype='float16', cuda_graph=False, instruction=None,
                 sampling='greedy', temperature=1.0, top_k=0, top_p=1.0, **kwargs):
        if instruction is not None and (not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000):
            raise ValueError('GameScaling instruction must contain 1–2000 characters')
        from gamescaling_decode import sampling_options
        self.sampling = sampling_options(sampling, temperature, top_k, top_p)
        from transformers import AutoModelForImageTextToText, AutoProcessor
        sys.path.insert(0, str(Path(source).resolve()))
        from gamescaling.prompt import build_system_prompt
        from gamescaling.action import parse_action
        self.parse_action = parse_action
        self.processor = AutoProcessor.from_pretrained(checkpoint, local_files_only=True)
        self.model = AutoModelForImageTextToText.from_pretrained(
            checkpoint, local_files_only=True, dtype=getattr(torch, dtype),
            attn_implementation='sdpa', device_map='cuda', trust_remote_code=False).eval()
        self.instruction = instruction.strip() if instruction is not None else (
            'Explore the open world, follow the current objective, avoid hazards, and interact with nearby objectives.')
        self.rules = self.instruction + ' Do not spend resources or open purchases.'
        self.system = build_system_prompt('Genshin Impact',
            rules=self.rules,
            key_bindings={'W': 'Move forward', 'A': 'Move left', 'S': 'Move backward', 'D': 'Move right',
                          'Space': 'Jump', 'Shift': 'Sprint or dodge', 'F': 'Interact', 'LB': 'Attack',
                          'E': 'Elemental skill', 'Q': 'Elemental burst', 'one': 'Character 1',
                          'two': 'Character 2', 'three': 'Character 3', 'four': 'Character 4'})
        self.history = deque(maxlen=history)
        self.max_new_tokens = max_new_tokens
        self.image_width = image_width
        self.dtype = getattr(torch, dtype)
        self.metadata = {'implementation': 'transformers-native-sdpa', 'precision': dtype,
                         'historyFrames': history, 'maxNewTokens': max_new_tokens,
                         'imageWidth': image_width, 'reasoning': False,
                         'sampling': self.sampling or {'do_sample': False},
                         'imageEncoding': 'RGB pixels; no JPEG round-trip',
                         'instruction': self.instruction, 'rules': self.rules,
                         'instructionMode': 'trial-text' if instruction is not None else 'fixed-generic-text',
                         'parameterCount': sum(parameter.numel() for parameter in self.model.parameters())}
        if cuda_graph:
            from gamescaling_decode import StaticGreedyDecode
            self.decode_graph = StaticGreedyDecode(self.model, sampling=self.sampling)
            self.metadata['cudaGraph'] = self.decode_graph.metadata
        else:
            self.decode_graph = None

    def reset(self):
        self.history.clear()

    def predict(self, image, source_size=None):
        started = time.perf_counter_ns()
        if self.image_width:
            image = image.resize((self.image_width, round(image.height * self.image_width / image.width)), Image.Resampling.BILINEAR)
        messages = [{'role': 'system', 'content': self.system}]
        def user(frame):
            return {'role': 'user', 'content': [{'type': 'text', 'text': 'current game screen'}, {'type': 'image', 'image': frame}]}
        for previous_image, previous_action in self.history:
            messages.extend([user(previous_image), {'role': 'assistant', 'content': previous_action}])
        messages.extend([user(image), {'role': 'assistant', 'content': '<think>\n\n</think>'}])
        inputs = self.processor.apply_chat_template(messages, tokenize=True, return_dict=True,
            return_tensors='pt', add_generation_prompt=False, continue_final_message=True)
        inputs = {key: value.to('cuda', dtype=self.dtype) if torch.is_floating_point(value)
                  else value.to('cuda') for key, value in inputs.items()}
        torch.cuda.synchronize()
        prepared = time.perf_counter_ns()
        clock = FirstTokenClock()
        end_id = self.processor.tokenizer.convert_tokens_to_ids('<|action_end|>')
        eos = self.model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        if end_id is not None and end_id != self.processor.tokenizer.unk_token_id:
            eos = list(set(eos + [end_id]))
        with torch.inference_mode():
            if self.decode_graph is None:
                output = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens,
                    **(self.sampling or {'do_sample': False}), streamer=clock, eos_token_id=eos, use_cache=True)
            else:
                output = self.decode_graph.generate(inputs, self.max_new_tokens, eos, clock)
        torch.cuda.synchronize()
        text = self.processor.tokenizer.decode(output[0, inputs['input_ids'].shape[-1]:], skip_special_tokens=False)
        action = self.parse_action('<think>\n\n</think>' + text)
        # Require a complete tagged chunk; do not treat budget-truncated output as valid.
        valid = complete_gamescaling_action(text, action)
        if valid:
            self.history.append((image, action.history_text))
        steps = gamescaling_steps(action, *(source_size or image.size)) if valid else []
        ended = time.perf_counter_ns()
        token_count = output.shape[-1] - inputs['input_ids'].shape[-1]
        return {'steps': steps, 'parseValid': valid, 'rawOutput': text,
                'scrollUnsupported': action.mouse[2] != 0,
                'preprocessMs': (prepared-started)/1e6,
                'firstTokenMs': (clock.first_ns-started)/1e6 if clock.first_ns else None,
                'fullActionMs': (ended-started)/1e6,
                'generatedTokens': token_count,
                'decodeAfterFirstTokenMs': (ended-clock.first_ns)/1e6 if clock.first_ns else None,
                'decodeMsPerAdditionalToken': (ended-clock.first_ns)/1e6/max(1, token_count-1) if clock.first_ns else None}


class OpenP2PAdapter:
    """Execute real 150M policy weights with persistent temporal KV state."""
    def __init__(self, checkpoint, source, cache_root, history=200, dtype='float16', cuda_graph=False,
                 fast_start=False, execution_feedback=False, goal_embedding=None, **kwargs):
        from p2p_loader import load_model
        self.model, self.config, manifest = load_model(source, checkpoint, cache_root, history, dtype)
        self.dtype = getattr(torch, dtype)
        self.use_cuda_graph = cuda_graph
        if fast_start and not cuda_graph:
            raise ValueError('Masked fast startup requires CUDA graph execution')
        if execution_feedback and not fast_start:
            raise ValueError('Execution feedback requires the resettable fixed-capacity cache')
        self.execution_feedback = execution_feedback
        self._history_backup = None
        self._pending_feedback = False
        self._goal_tensor = None
        self.temporal_cache = None
        self.graph = None
        if fast_start:
            from p2p_temporal_cache import MaskedTemporalCache
            self.temporal_cache = MaskedTemporalCache(self.model.bc_transformer)
        self.metadata = {'implementation': 'upstream-model-only-native-sdpa', 'precision': dtype,
                         'historyFrames': history, 'textConditioning': False,
                         'mouseSampling': 'mean', 'compatibility': manifest,
                         'cudaGraph': cuda_graph, 'graphCaptureValidated': False,
                         'cacheInitialization': 'masked-empty-fixed-capacity' if fast_start else 'growing-history',
                         'historyCommit': 'accepted-proposals-only' if execution_feedback else 'all-predictions',
                         'rotaryPositions': 'on-device FP32 original formula; no finite cache or periodic reset',
                         'parameterCount': sum(parameter.numel() for parameter in self.model.parameters())}
        self.reset()
        if goal_embedding:
            self.set_goal(goal_embedding)

    def set_goal(self, path):
        """Copy a validated instruction into stable graph storage and clear old goal history."""
        if self._pending_feedback:
            raise RuntimeError('Resolve the previous action before changing the instruction')
        from goal_embedding import load_goal
        embedding, metadata = load_goal(path)
        self._goal_tensor = torch.as_tensor(embedding, device=self.text.device, dtype=self.dtype)
        self.metadata.update(textConditioning=True, goal=metadata)
        self.reset()

    def reset(self):
        """Start empty episode history, retaining a validated fixed-capacity graph."""
        if self.temporal_cache is not None and self.graph is not None:
            self.temporal_cache.reset()
            self.static_idx.zero_()
            for state in self.static_state:
                state.k_cache.zero_()
                state.v_cache.zero_()
            self.idx, self.state = self.static_idx, self.static_state
        else:
            self.idx = torch.tensor(0, dtype=torch.int64, device='cuda')
            self.state = (self.temporal_cache.empty_state() if self.temporal_cache is not None
                          else self.model.bc_transformer.init_kv_cache_state())
            self.graph = None
        if not hasattr(self, 'text'):
            self.text = torch.zeros(self.config.shared.text_tokenizer_config.text_embedding_shape,
                                    device='cuda', dtype=self.dtype)
        # A retained graph keeps this tensor's storage address across pauses and goal changes.
        if getattr(self, '_goal_tensor', None) is not None:
            self.text.copy_(self._goal_tensor)
        else:
            self.text.zero_()
        self.steps_seen = 0
        self._pending_feedback = False

    def _begin_history_transaction(self):
        """Preserve the prior state so an unexecuted proposal cannot become action history."""
        if not self.execution_feedback:
            return
        if self._pending_feedback:
            raise RuntimeError('Resolve the previous action acceptance before predicting again')
        if self._history_backup is None:
            self._history_backup = [type(state)(state.k_cache.clone(), state.v_cache.clone()) for state in self.state]
            self._backup_idx = self.idx.clone()
            self._backup_valid = self.temporal_cache.valid_tokens.clone()
        else:
            for saved, state in zip(self._history_backup, self.state):
                saved.k_cache.copy_(state.k_cache)
                saved.v_cache.copy_(state.v_cache)
            self._backup_idx.copy_(self.idx)
            self._backup_valid.copy_(self.temporal_cache.valid_tokens)
        self._backup_steps = self.steps_seen
        self._pending_feedback = True

    def finish_action(self, accepted):
        """Commit a server-accepted proposal or restore history after complete rejection.

        Acceptance is not an execution receipt: focus/world transitions still reset
        history. Rejected observations are skipped; they are never relabelled as a
        different action, and offline benchmark history keeps its original behavior.
        """
        if not self.execution_feedback:
            return
        if type(accepted) is not bool or not self._pending_feedback:
            raise RuntimeError('One explicit boolean acceptance is required per pending prediction')
        if not accepted:
            self.idx.copy_(self._backup_idx)
            self.temporal_cache.valid_tokens.copy_(self._backup_valid)
            for state, saved in zip(self.state, self._history_backup):
                state.k_cache.copy_(saved.k_cache)
                state.v_cache.copy_(saved.v_cache)
            self.steps_seen = self._backup_steps
        self._pending_feedback = False

    def _forward(self, frame, idx, state, uniform=None):
        """Keep all numeric work on CUDA, including upstream tensor allocation."""
        with torch.inference_mode(), torch.device('cuda'), torch.autocast('cuda', dtype=self.dtype, enabled=self.dtype != torch.float32):
            return self.model.online_kv_cache_predict(frame, idx, state, compile=False,
                sampling_temperature=1.0, text_tokens_embed=self.text, unif_rand=uniform)

    def _prepare_graph(self, frame):
        """Capture a full-cache step and compare its output to the eager model."""
        self.static_frame = frame.clone()
        self.static_idx = self.idx.clone()
        self.static_state = [type(state)(state.k_cache.clone(), state.v_cache.clone()) for state in self.state]
        self.static_uniform = torch.rand(self.model.action_mapping.get_seq_len(), device='cuda')
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(2):
                expected = self._forward(self.static_frame, self.static_idx, self.static_state, self.static_uniform)
        torch.cuda.current_stream().wait_stream(stream)
        torch.cuda.synchronize()
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph, stream=stream):
            self.graph_result = self._forward(self.static_frame, self.static_idx, self.static_state, self.static_uniform)
        self.graph.replay()
        torch.cuda.synchronize()
        for actual, reference in zip(self.graph_result[0], expected[0]):
            torch.testing.assert_close(actual, reference, rtol=0, atol=0)
        for actual, reference in zip(self.graph_result[2], expected[2]):
            torch.testing.assert_close(actual.k_cache, reference.k_cache, rtol=1e-3, atol=1e-3)
            torch.testing.assert_close(actual.v_cache, reference.v_cache, rtol=1e-3, atol=1e-3)
        self.metadata['graphCaptureValidated'] = True

    def predict(self, image, source_size=None):
        started = time.perf_counter_ns()
        self._begin_history_transaction()
        frame = torch.from_numpy(np.array(image.resize((192, 192), Image.Resampling.BILINEAR), copy=True))
        frame = frame.permute(2, 0, 1).to('cuda')
        torch.cuda.synchronize()
        prepared = time.perf_counter_ns()
        if self.temporal_cache is not None:
            self.temporal_cache.advance()
        full = self.state[0].k_cache.shape[2] >= self.model.bc_transformer.kv_cache.max_seq_len
        graph_preparation_ms = 0
        if self.use_cuda_graph and full:
            if self.graph is None:
                graph_started = time.perf_counter_ns()
                self._prepare_graph(frame)
                graph_preparation_ms = (time.perf_counter_ns()-graph_started)/1e6
            self.static_frame.copy_(frame)
            self.static_uniform.uniform_()
            self.graph.replay()
            action, next_idx, next_state = self.graph_result
            self.static_idx.copy_(next_idx)
            for current, updated in zip(self.static_state, next_state):
                current.k_cache.copy_(updated.k_cache)
                current.v_cache.copy_(updated.v_cache)
            self.idx, self.state = self.static_idx, self.static_state
        else:
            action, self.idx, self.state = self._forward(frame, self.idx, self.state)
        torch.cuda.synchronize()
        decoded = self.model.action_mapping.tensor_to_action(action, mouse_sampling_approach='mean')
        keys = [canonical_key(key) for key in decoded.keys]
        mouse_keys = {'Left': 'LBUTTON', 'Right': 'RBUTTON', 'Middle': 'MBUTTON',
                      'LEFT': 'LBUTTON', 'RIGHT': 'RBUTTON', 'MIDDLE': 'MBUTTON',
                      '0': 'LBUTTON', '1': 'RBUTTON', '2': 'MBUTTON'}
        keys.extend(mouse_keys.get(key, canonical_key(key)) for key in decoded.mouse_buttons)
        dx, dy = float(decoded.mouse_delta_x), float(decoded.mouse_delta_y)
        valid = math.isfinite(dx) and math.isfinite(dy)
        self.steps_seen += 1
        ended = time.perf_counter_ns()
        return {'steps': [{'durationMs': 50, 'keys': keys, 'mouseDx': round(dx), 'mouseDy': round(dy)}] if valid else [],
                'parseValid': valid, 'cudaGraphActive': self.graph is not None,
                'graphPreparationMs': graph_preparation_ms, 'episodeStep': self.steps_seen,
                'validHistoryFrames': min(self.steps_seen, self.config.shared.n_seq_timesteps),
                'rawOutput': {'keys': decoded.keys, 'mouseButtons': decoded.mouse_buttons, 'dx': dx, 'dy': dy},
                'preprocessMs': (prepared-started)/1e6, 'firstTokenMs': None,
                'fullActionMs': (ended-started)/1e6, 'generatedTokens': None}


def make_adapter(name, **kwargs):
    """Load a selected real checkpoint; never substitute a dummy policy."""
    if not torch.cuda.is_available():
        raise RuntimeError('A CUDA-enabled PyTorch build and accessible GPU are required')
    return (GameScalingAdapter if name == 'gamescaling' else OpenP2PAdapter)(**kwargs)
