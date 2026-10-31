"""Opt-in P2P history labels backed by one completed native action at a time.

The codec records held keys and a one-shot mouse delta. It has no duration token;
commanded horizons and native software intervals remain separate evidence.
"""
from bisect import bisect_left
from copy import deepcopy
import math


# This named contract is pinned independently from the legacy acceptance feedback.
MODE = 'receipt-verified-executed-actions-v1'
KEYBOARD = {'SPACE': ('Space', 1), '1': ('1', 2), '2': ('2', 3), '3': ('3', 4),
            '4': ('4', 5), 'A': ('a', 6), 'D': ('d', 7), 'E': ('e', 8),
            'F': ('f', 9), 'Q': ('q', 10), 'W': ('w', 11), 'S': ('s', 12),
            'Z': ('z', 13), 'DOWN': ('DownArrow', 14), 'UP': ('UpArrow', 15),
            'LEFT': ('LeftArrow', 16), 'RIGHT': ('RightArrow', 17),
            'LSHIFT': ('LeftShift', 18), 'RSHIFT': ('RightShift', 19)}
BUTTONS = {'LBUTTON': 1, 'RBUTTON': 2, 'MBUTTON': 3}
# Integer controller deltas are bucketized with right=False, exactly as upstream.
MOUSE_X_EDGES = (-500.1, -144.1, -76.1, -46.1, -29.1, -18.1, -11.1, -6.1,
                 -3.1, -1.1, -.1, 0, 1, 3, 6, 11, 18, 29, 46, 76, 144, 500)
MOUSE_Y_EDGES = (-150.1, -24.1, -12.1, -7.1, -4.1, -3.1, -1.1, -.1,
                 0, 1, 3, 4, 7, 12, 24, 150)


class ExecutedHistoryCadence:
    """Limit prediction starts while polling post-terminal sources without another full period."""
    def __init__(self, hz, now):
        """Keep sampling waits separate from the next permitted model prediction."""
        if type(hz) not in (int, float) or not math.isfinite(hz) or hz <= 0:
            raise ValueError('Executed-history decision frequency must be finite and positive')
        self.period = 1 / hz
        self.next_at = self._next_prediction_at = now
        self._wait_period = min(.005, self.period)

    def remaining(self, now):
        """Return the cancellable wait before the next control/source check."""
        return max(0, self.next_at - now)

    def prediction_started(self, now):
        """Consume a decision slot only when the serial loop actually begins inference."""
        if now < self._next_prediction_at - 1e-9:
            raise RuntimeError('Executed-history prediction started before its cadence')
        self._next_prediction_at = now + self.period

    def advance(self, now):
        """Retry sampling promptly after an overrun, without accumulating decision slots."""
        self.next_at = max(self._next_prediction_at, now + self._wait_period)


def executed_history_policy(hold_ms):
    """Return the immutable descriptor used by launch, reuse and offline replay."""
    if type(hold_ms) is not int or hold_ms not in (50, 60):
        raise ValueError('Executed history requires a 50 or 60 ms commanded hold')
    return dict(version=1, historyCommitMode=MODE, actionHoldMs=hold_ms,
                maxPendingActions=1, requiredReceiptStatus='completed',
                requiredReceiptReason='horizon_complete', maxAppliedSteps=1,
                postTerminalSourceRequired=True, receiptDeadline='original-proposal-and-lease',
                incompleteReceipt='release-reset-retire', mouseDelta='one-shot-unscaled',
                durationToken=False, maxKeyboardTokens=4, maxMouseButtonTokens=2)


def validate_executed_history_options(args, policy=None, control=None, *, require_bound=False):
    """Limit the initial mode to reviewed, recorded, guarded navigation without side inputs."""
    enabled = getattr(args, 'p2p_executed_history', False)
    if type(enabled) is not bool:
        raise ValueError('p2p-executed-history requires an explicit boolean')
    if not enabled:
        if policy is not None and getattr(policy, 'executed_history', False) is True:
            raise ValueError('Executed-history adapter cannot run under legacy declarations')
        return False
    executed_history_policy(getattr(args, 'action_hold_ms', None))
    required = ('resident', 'cuda_graph', 'p2p_fast_start', 'p2p_execution_feedback',
                'p2p_prewarm', 'enable_input', 'hybrid_navigation', 'soft_cadence',
                'retain_policy_rgb', 'native_combat_observation')
    forbidden = ('navigation_climb_recovery', 'allow_inspected_obstacle_recovery',
                 'warm_photo_plan', 'photo_station', 'combat_shadow', 'combat_trial_binding',
                 'steering_shadow', 'camera_calibration')
    if (any(getattr(args, key, False) is not True for key in required)
            or any(getattr(args, key, None) for key in forbidden)
            or getattr(args, 'model', None) != 'open-p2p'
            or getattr(args, 'history', None) != 41
            or getattr(args, 'hybrid_legs', None) != 1
            or getattr(args, 'goal_intent', None) != 'ground-navigation'
            or getattr(args, 'execution_context', 'off') != 'off'
            or not getattr(args, 'reviewed_scout_route', None) or not getattr(args, 'record_dir', None)
            or not 0 < getattr(args, 'seconds', 0) <= 35
            or not 0 < getattr(args, 'max_observation_age_ms', 0) <= 150
            or not 0 < getattr(args, 'record_max_mib', 0) <= 160):
        raise ValueError('Executed history requires bounded reviewed scout input, retained RGB and no side input tasks')
    if require_bound and (policy is None or getattr(policy, 'executed_history', False) is not True
            or getattr(policy, 'metadata', {}).get('historyCommitMode') != MODE
            or control is None or getattr(control, 'scout_encounter_guard', None) is None
            or getattr(control, 'frozen_goal', False) is not True):
        raise ValueError('Executed history requires its declared adapter and frozen reviewed scout guard')
    return True


class ExecutedHistoryRecorder:
    """Make every recording loss terminal before another serialized dispatch."""
    def __init__(self, recorder):
        """Retain the existing recorder and its ownership/closure lifecycle."""
        if recorder is None:
            raise ValueError('Executed history requires retained recording')
        self.recorder = recorder
        self.failure = None

    def __getattr__(self, name):
        """Keep the existing recorder or segment-archive API unchanged."""
        return getattr(self.recorder, name)

    def check(self, result=True):
        """Inspect both the archive and its current worker, including queue eviction."""
        worker = getattr(self.recorder, 'recorder', self.recorder)
        losses = {name: getattr(worker, name, 0) for name in
                  ('dropped', 'dropped_events', 'dropped_observations', 'abandoned_frames')}
        if self.failure is not None or result is False or self.recorder.error or any(losses.values()):
            self.failure = self.failure or ('Executed-history retention failed: ' + str(self.recorder.error) + ' ' + str(losses))
            raise RuntimeError(self.failure)

    def event(self, event):
        """Require the existing event queue to accept every receipt and history label."""
        try:
            result = self.recorder.event(event)
            self.check(result)
            return result
        except Exception as error:
            self.failure = self.failure or str(error)
            raise

    def put(self, metadata, pixels):
        """Require the original RGB/source record before admitting another action."""
        try:
            result = self.recorder.put(metadata, pixels)
            self.check(result)
            return result
        except Exception as error:
            self.failure = self.failure or str(error)
            raise


def encode_controller_step(step):
    """Reject every lossy key repair and encode the actual submitted integer step."""
    if (type(step) is not dict or set(step) != {'durationMs', 'keys', 'mouseDx', 'mouseDy'}
            or type(step['durationMs']) is not int or not 33 <= step['durationMs'] <= 100
            or type(step['keys']) is not list or any(type(key) is not str for key in step['keys'])
            or len(set(step['keys'])) != len(step['keys'])
            or any(type(step[key]) is not int or not -(2**31) <= step[key] < 2**31
                   for key in ('mouseDx', 'mouseDy'))):
        raise ValueError('Executed-history step must be an exact bounded controller step')
    keys, buttons = [], []
    for key in step['keys']:
        if key in KEYBOARD:
            keys.append(KEYBOARD[key][1])
        elif key in BUTTONS:
            buttons.append(BUTTONS[key])
        else:
            raise ValueError('Executed-history codec cannot represent key ' + key)
    if len(keys) > 4 or len(buttons) > 2:
        raise ValueError('Executed-history codec cannot truncate keys or mouse buttons')
    return dict(keys=sorted(keys) + [0] * (4-len(keys)),
                mouseButtons=sorted(buttons) + [0] * (2-len(buttons)),
                mouseDxBin=bisect_left(MOUSE_X_EDGES, step['mouseDx']),
                mouseDyBin=bisect_left(MOUSE_Y_EDGES, step['mouseDy']))


def validate_action_mapping(mapping):
    """Bind this strict encoder to the installed upstream mapping before any input."""
    if (mapping.get_number_of_keyboard_actions() != 4
            or mapping.get_number_of_mouse_button_actions() != 2
            or mapping.get_seq_len() != 8
            or any(mapping.keyboard_reverse_map.get(index) != name for name, index in KEYBOARD.values())
            or any(mapping.mouse_button_reverse_map.get(index) != str(index-1) for index in BUTTONS.values())):
        raise ValueError('Executed-history action mapping differs from the pinned codec')
    for actual, expected in ((mapping._mouse_delta_x_edges, MOUSE_X_EDGES),
                             (mapping._mouse_delta_y_edges, MOUSE_Y_EDGES)):
        values = actual.detach().cpu().tolist()
        if len(values) != len(expected) or any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-5)
                                               for a, b in zip(values, expected)):
            raise ValueError('Executed-history mouse bin edges differ from the pinned codec')


def teacher_forced_step(model, frame, idx, state, text, encoded, *, action_tensors=None):
    """Rebuild upstream's entire second temporal pass from the pre-prediction cache.

There is no action sampling and no extra timestep. Replacing only the last action
KV entries would leave higher-layer states conditioned on the unexecuted sample.
"""
    import torch
    transformer = model.bc_transformer
    config = transformer.config
    if (config.n_action_tokens != 8 or any(part.k_cache.shape[2] != transformer.kv_cache.max_seq_len
                                          for part in state)):
        raise ValueError('Executed history requires the full fixed-capacity eight-action-token layout')
    normalized = model._normalize_frames(frame).unsqueeze(0).unsqueeze(0)
    image = transformer.image_tokenizer(normalized).view(
        1, transformer.image_tokenizer.get_n_img_tokens(), config.embed_dim) + transformer.img_pos_tokens
    text_tokens = transformer.text_embed_mlp(text.view(
        1, transformer.text_token_size, transformer.text_tokenizer_embed_dim).to(frame.device))
    text_tokens = transformer._impute_no_text_embedding(text_tokens) + transformer.text_pos_tokens
    # A CUDA graph supplies stable token tensors; eager diagnostics retain the
    # independently checked JSON encoder path. Both use identical action embeddings.
    if action_tensors is None:
        action_type = type(model.action_mapping.make_empty_action(1))
        action = action_type(*[torch.tensor(value, dtype=torch.int64, device=frame.device).reshape(1, 1, -1)
                              for value in (encoded['keys'], encoded['mouseButtons'],
                                            [encoded['mouseDxBin']], [encoded['mouseDyBin']])])
    else:
        action=action_tensors
    action_tokens = model.action_in_to_tokens(action).view(1, config.n_action_tokens, config.embed_dim)
    tokens = torch.cat((text_tokens, image, transformer.thinking_pos_tokens.repeat(1, 1, 1),
                        transformer.action_out_token.repeat(1, 1, 1),
                        action_tokens + transformer.action_pos_tokens), dim=1)
    if tokens.shape[1] != transformer.kv_cache.step_size:
        raise ValueError('Executed-history temporal step layout differs from the pinned model')
    positions = torch.arange(tokens.shape[1], dtype=idx.dtype, device=idx.device) + idx
    _, next_state, *_ = transformer._transformer.forward(
        tokens, input_pos=positions, kv_cache_state=state, should_grow_cache=False, use_decode_mask=True)
    return positions[-1] + 1, next_state


def _number(value):
    """Reject booleans and nonfinite clock values in native evidence."""
    return type(value) in (int, float) and math.isfinite(value)


def verify_completed_receipt(receipt, request, acceptance):
    """Require a single exact native software execution; do not infer hardware delivery."""
    if (type(request) is not dict or type(request.get('requestId')) is not str or not request['requestId']
            or type(request.get('modelId')) is not str or not request['modelId']
            or type(request.get('frameId')) is not int or request['frameId'] <= 0
            or type(receipt) is not dict or type(acceptance) is not dict
            or acceptance.get('type') != 'accepted'
            or acceptance.get('requestId') != request.get('requestId')
            or any(receipt.get(key) != request.get(key) for key in ('requestId', 'frameId', 'modelId'))
            or type(receipt.get('frameId')) is not int
            or receipt.get('status') != 'completed' or receipt.get('reason') != 'horizon_complete'
            or not _number(acceptance.get('acceptedAtMs'))
            or not _number(receipt.get('acceptedAtMs'))
            or receipt.get('acceptedAtMs') != acceptance['acceptedAtMs']
            or not _number(receipt.get('endedAtMs'))):
        raise ValueError('Executed history requires the exact completed native receipt')
    applied = receipt.get('appliedSteps')
    if type(applied) is not list or len(applied) != 1 or len(request.get('steps', [])) != 1:
        raise ValueError('Executed history requires exactly one applied step')
    actual, step = applied[0], request['steps'][0]
    encode_controller_step(step)
    if (type(actual) is not dict or type(actual.get('index')) is not int or actual['index'] != 0
            or any(actual.get(key) != step[key] for key in ('keys', 'mouseDx', 'mouseDy'))
            or any(type(actual.get(key)) is not int for key in ('mouseDx', 'mouseDy'))
            or not _number(actual.get('startedAtMs'))
            or not _number(request.get('observedAtMs'))
            or not _number(request.get('startBeforeMs')) or not _number(request.get('expiresAtMs'))
            or not request['observedAtMs'] <= receipt['acceptedAtMs'] <= actual['startedAtMs'] <= request['startBeforeMs']
            or receipt['endedAtMs'] < receipt['acceptedAtMs'] + step['durationMs']
            or not actual['startedAtMs'] <= receipt['endedAtMs'] < request['expiresAtMs']):
        raise ValueError('Executed-history applied step or timing differs from the original request')
    return deepcopy(receipt)


def source_after_terminal(frame, observation_ms, predecessor):
    """Wait for a genuinely newer raw source after the last completed software interval."""
    source = frame.get('sourceFrame') or {}
    if (type(source.get('timestamp100ns')) is not int or type(frame.get('frameId')) is not int
            or frame['frameId'] <= 0 or source['timestamp100ns'] < 0 or source.get('captureEpoch') is None
            or not _number(observation_ms)):
        raise ValueError('Executed-history source identity is unavailable')
    if predecessor is None:
        return True
    old_source = predecessor['sourceFrame']
    if source.get('captureEpoch') != old_source.get('captureEpoch'):
        raise ValueError('Executed-history source epoch changed')
    return (frame['frameId'] > predecessor['frameId']
            and source['timestamp100ns'] > old_source['timestamp100ns']
            and observation_ms > predecessor['endedAtMs'])
