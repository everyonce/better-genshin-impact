"""Deferred eager operations layered over the unchanged qualified native runtime."""
from dataclasses import dataclass
import math
import time

from native_history_feedback import require


@dataclass(frozen=True)
class PreparedAction:
    """Private retained tensors; never serialize or expose this object to the bridge."""
    frame: object
    native: tuple
    raw_ids: tuple
    raw_layouts: tuple


class ReceiptHistoryRuntime:
    """Reuse an already pinned native runtime; graphs and masked caches are excluded.

    The accepted dependency's OpenP2P class is AST-identical to primary 0ccd24c.
    This composition does not enable that dependency through any live factory.
    """
    def __init__(self, base, split):
        self.base, self.split = base, split

    def __getattr__(self, name):
        """Keep existing qualification, RNG lease, snapshot and retirement operations."""
        return getattr(self.base, name)

    def qualify(self, adapter):
        """Qualify the exact original adapter, then impose the narrower eager boundary."""
        self.base.qualify(adapter)
        require(adapter.use_cuda_graph is False and adapter.graph is None, 'receipt_eager_only')
        require(self.split.model is adapter.model, 'split_model_owner')
        self.split.guard()

    def guard(self, adapter):
        """Retain ordinary CPU caller context and unchanged source/storage identities."""
        self.split.guard()
        require(adapter.use_cuda_graph is False and adapter.graph is None, 'receipt_eager_only')
        return self.base.guard(adapter)

    def _ids(self, action):
        """Read the four native fields without sorting, re-binning or re-decoding them."""
        tensors = tuple(action)
        require(len(tensors) == 4, 'raw_action_fields')
        rows = []
        for tensor, count in zip(tensors, (4, 2, 1, 1)):
            require(tensor.numel() == count and tensor.dtype == self.base.torch.int64, 'raw_action_layout')
            values = tensor.detach().cpu().reshape(-1).tolist()
            require(type(values) is list and len(values) == count
                    and all(type(x) is int and x >= 0 for x in values), 'raw_action_values')
            rows.append(tuple(values))
        return tuple(rows)

    def prepare(self, adapter, image, source_size=None, observation_profile=None):
        """Use the original preprocess, native sampler and CPU decoder once each."""
        from observation_profiles import prepare_p2p_image
        t, namespace = self.base.torch, self.base.adapter_module
        started = time.perf_counter_ns()
        prepared_image = prepare_p2p_image(image, adapter.observation_profile, observation_profile)
        frame = t.from_numpy(namespace.np.array(prepared_image, copy=True))
        frame = frame.permute(2, 0, 1).to('cuda')
        self.synchronize()
        prepared_at = time.perf_counter_ns()
        with t.inference_mode(), t.device('cuda'), t.autocast('cuda', dtype=adapter.dtype,
                                                            enabled=adapter.dtype != t.float32):
            native = self.split.prepare(frame, adapter.idx, adapter.state, adapter.text)
        self.synchronize()
        raw = self._ids(native[0])
        # The native action and its reshaped views are private to this pending owner.
        layouts = tuple(self.layout(x) for x in tuple(native[0]) + tuple(native[1]))
        decoded = adapter.model.action_mapping.tensor_to_action(
            native[0], mouse_sampling_approach=adapter.mouse_sampling)
        keys = [namespace.canonical_key(key) for key in decoded.keys]
        mouse_keys = {'Left': 'LBUTTON', 'Right': 'RBUTTON', 'Middle': 'MBUTTON',
                      'LEFT': 'LBUTTON', 'RIGHT': 'RBUTTON', 'MIDDLE': 'MBUTTON',
                      '0': 'LBUTTON', '1': 'RBUTTON', '2': 'MBUTTON'}
        keys.extend(mouse_keys.get(key, namespace.canonical_key(key)) for key in decoded.mouse_buttons)
        dx, dy = float(decoded.mouse_delta_x), float(decoded.mouse_delta_y)
        require(math.isfinite(dx) and math.isfinite(dy), 'invalid_mouse_decode')
        result = {'steps': [{'durationMs': 50, 'keys': keys, 'mouseDx': round(dx), 'mouseDy': round(dy)}],
                  'parseValid': True, 'cudaGraphActive': False, 'graphPreparationMs': 0,
                  'episodeStep': adapter.steps_seen + 1,
                  'validHistoryFrames': min(adapter.steps_seen + 1, adapter.config.shared.n_seq_timesteps),
                  'rawOutput': {'keys': decoded.keys, 'mouseButtons': decoded.mouse_buttons, 'dx': dx, 'dy': dy},
                  'nativeRawTokens': {'keys': list(raw[0]), 'mouseButtons': list(raw[1]),
                                      'mouseX': raw[2][0], 'mouseY': raw[3][0]},
                  'historyStatus': 'pending_software_completed_step',
                  'preprocessMs': (prepared_at - started) / 1e6,
                  'proposalMs': (time.perf_counter_ns() - started) / 1e6}
        return result, PreparedAction(frame, native, raw, layouts)

    def commit(self, adapter, prepared):
        """Use retained sampled IDs/prefixes and check that commit consumes no RNG."""
        require(type(prepared) is PreparedAction, 'prepared_owner_type')
        native = prepared.native
        require(native[8] is adapter.state, 'prepared_predecessor_owner')
        require(self._ids(native[0]) == prepared.raw_ids
                and tuple(self.layout(x) for x in tuple(native[0]) + tuple(native[1])) == prepared.raw_layouts,
                'prepared_raw_tokens_changed')
        before = self.save_rng()
        t = self.base.torch
        with t.inference_mode(), t.device('cuda'), t.autocast('cuda', dtype=adapter.dtype,
                                                            enabled=adapter.dtype != t.float32):
            raw, idx, state = self.split.commit(native)
        self.synchronize()
        self.verify_rng(before)
        require(raw is native[0] and self._ids(raw) == prepared.raw_ids, 'committed_raw_tokens_changed')
        return idx, state
