"""One owned checkpoint stream; source-only, with numerical/native qualification pending.

This proves a scoped initial load, not later parameter immutability or loaded-code
qualification. The existing runtime source/method guards remain necessary.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import PureWindowsPath
import stat
import time

AVAILABLE = False
BUFFER_BYTES = 1024 * 1024
METADATA_BYTES = 4096
PROFILE = 'p2p-native-hamming-192-v1'
MAPPING = 'native-raw-to-one-step-v1'


def require(condition, name):
    """Reject a violated load contract without fallback, retry or source substitution."""
    if not condition:
        raise ValueError(name)


def canonical(value):
    """Detach only small JSON provenance; never serialize weights or model objects."""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    require(len(raw) <= 65536, 'provenance_json_bound')
    return raw


def local_path(value):
    """Admit an explicit local drive path, excluding UNC/device and relative paths."""
    path = PureWindowsPath(value)
    require(path.is_absolute() and len(path.drive) == 2 and path.drive[0].isalpha()
            and path.drive[1] == ':' and '..' not in path.parts, 'local_absolute_path')
    return str(path).casefold()


def digest(value):
    """Require exact lowercase SHA256 metadata, independently checked against read bytes."""
    require(type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value), 'sha256')
    return value


class _WindowsReadApi:
    """Deferred stdlib Windows calls; no imports or native operations at module import."""
    def open_handle(self, path):
        """Open existing read-only, non-inheritable, denying write/delete sharing."""
        import _winapi
        return _winapi.CreateFile(path, 0x80000000, 0x00000001, 0, 3, 0x00000080, 0)

    def to_fd(self, handle):
        """Successful conversion transfers ownership; failure leaves the raw handle owned."""
        import msvcrt
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)

    def binary(self, fd):
        """Keep CRT reads binary before constructing the sole owning Python stream."""
        import msvcrt
        msvcrt.setmode(fd, os.O_BINARY)

    def to_stream(self, fd):
        """Successful fdopen owns the descriptor; no whole-file buffer or path reopen."""
        return os.fdopen(fd, 'rb', buffering=0)

    def info(self, stream):
        """Inspect the actual opened object, not a separate pathname stat."""
        return os.fstat(stream.fileno())

    def close_handle(self, handle):
        """Close only a raw handle whose ownership has not transferred."""
        import _winapi
        _winapi.CloseHandle(handle)

    def close_fd(self, fd):
        """Close only a descriptor not yet transferred to the stream."""
        os.close(fd)


@dataclass(frozen=True)
class _LoadReceipt:
    """An identity-bound in-process receipt; exported dictionaries are never authority."""
    adapter: object
    model: object
    config: object
    checkpoint_sha256: str
    checkpoint_bytes: int
    source_path: str
    config_sha256: str
    compatibility_sha256: str
    inert: bool

    def metadata(self):
        """Return detached bounded initial-load facts, with no activation authority."""
        return dict(schema='native-checkpoint-load-v1', verifiedLoad=True, inert=self.inert,
                    checkpointSha256=self.checkpoint_sha256, checkpointBytes=self.checkpoint_bytes,
                    configSha256=self.config_sha256, compatibilitySha256=self.compatibility_sha256,
                    profile=PROFILE, history=41, precision='float16', mouseSampling='truncated_normal',
                    initialLoadOnly=True, runtimeActivationAvailable=False)


class CheckpointLoadScope:
    """Single-use scope spanning the optional loader and the complete adapter constructor.

    Inert injection is explicit and cannot produce live authority. Native entry is
    unconditionally blocked in this source candidate. A failed scope retains its
    partial adapter/model and current OS owner for external cleanup diagnosis.
    """
    def __init__(self, *, checkpoint, size, sha256, source, config_sha256,
                 compatibility_sha256, deadline, inert=False, api=None, clock=None):
        require(type(inert) is bool and (inert or AVAILABLE), 'checkpoint_scope_activation_unavailable')
        require(type(size) is int and 0 < size <= 4 * 1024**3, 'checkpoint_size_bound')
        require(type(deadline) in (int, float) and math.isfinite(deadline), 'load_deadline')
        require((inert and api is not None) or (not inert and api is None and clock is None), 'api_injection')
        self.checkpoint = local_path(checkpoint)
        self.source = local_path(source)
        self.size, self.sha256 = size, digest(sha256)
        self.config_sha256 = digest(config_sha256)
        self.compatibility_sha256 = digest(compatibility_sha256)
        self._api = api if inert else _WindowsReadApi()
        self._clock = time.monotonic if clock is None else clock
        self._deadline, self._inert = deadline, inert
        self._phase = 'new'
        self._adapter = self._model = self._config = self._receipt = None
        self._raw = self._fd = self._stream = None
        self._close_attempted = False
        self._loader_started = self._source_checked = self._strict_loaded = False
        self._primary = self._cleanup = None

    def _time(self):
        """Check the caller's finite preparation deadline between bounded hash reads."""
        now = self._clock()
        require(type(now) in (int, float) and math.isfinite(now) and now < self._deadline, 'load_deadline_expired')

    def begin_adapter(self, adapter, *, checkpoint, history, dtype, cuda_graph,
                      fast_start, execution_feedback, p2p_mouse_sampling, observation_profile):
        """Retain the real partially initialized adapter before imports or allocations."""
        require(self._phase == 'new', 'scope_single_use')
        self._adapter = adapter
        self._phase = 'constructing'
        self._time()
        require(local_path(checkpoint) == self.checkpoint and type(history) is int and history == 41
                and dtype == 'float16' and cuda_graph is False and fast_start is False
                and execution_feedback is False and p2p_mouse_sampling == 'truncated_normal'
                and observation_profile == PROFILE, 'requested_native_profile')

    def begin_loader(self, source, checkpoint, history, dtype):
        """Qualify the exact one loader invocation, never an independently declared model."""
        require(self._phase == 'constructing' and not self._loader_started, 'loader_scope')
        self._loader_started = True
        require(local_path(source) == self.source and local_path(checkpoint) == self.checkpoint
                and type(history) is int and history == 41 and dtype == 'float16', 'loader_binding')
        self._time()

    def check_source(self, config_bytes, manifest):
        """Bind the consumed YAML bytes and actual compatibility manifest separately from weights."""
        require(self._loader_started and self._model is None and type(config_bytes) is bytes, 'source_stage')
        require(hashlib.sha256(config_bytes).hexdigest() == self.config_sha256, 'config_bytes')
        require(hashlib.sha256(canonical(manifest)).hexdigest() == self.compatibility_sha256, 'compatibility_manifest')
        self._source_checked = True

    def construct_model(self, model_type, config):
        """Keep the actual allocated object before its initializer can fail."""
        require(self._source_checked and self._model is None, 'model_single_allocation')
        self._model = model_type.__new__(model_type)
        self._config = config
        model_type.__init__(self._model, config)
        return self._model

    def load(self, torch, checkpoint, model):
        """Hash and load the same owning stream, then perform the original strict state load."""
        require(self._phase == 'constructing' and model is self._model and not self._strict_loaded
                and local_path(checkpoint) == self.checkpoint and self._stream is None, 'load_identity')
        self._time()
        self._raw = self._api.open_handle(str(checkpoint))
        self._fd = self._api.to_fd(self._raw)
        self._raw = None
        self._api.binary(self._fd)
        self._stream = self._api.to_stream(self._fd)
        self._fd = None
        info = self._api.info(self._stream)
        require(stat.S_ISREG(info.st_mode) and info.st_size == self.size, 'opened_file_shape')
        buffer = bytearray(BUFFER_BYTES)
        view = memoryview(buffer)
        hasher, count = hashlib.sha256(), 0
        while count < self.size:
            self._time()
            remaining = min(BUFFER_BYTES, self.size-count)
            read = self._stream.readinto(view[:remaining])
            require(type(read) is int and 0 < read <= remaining, 'checkpoint_short_read')
            hasher.update(view[:read]); count += read
        self._time()
        require(self._stream.readinto(view[:1]) == 0, 'checkpoint_extra_bytes')
        require(hasher.hexdigest() == self.sha256, 'checkpoint_hash')
        self._stream.seek(0)
        require(self._stream.tell() == 0, 'checkpoint_rewind')
        state = torch.load(self._stream, map_location='cpu', weights_only=True, mmap=False)
        state = state.get('state_dict', state)
        model.load_state_dict(state, strict=True)
        self._strict_loaded = True
        self._time()
        return state  # Preserve the loader's original state-dictionary lifetime through conversion.

    def _profile(self, adapter):
        """Check actual returned identities and resolved values; no checksum-only admission."""
        require(adapter is self._adapter and adapter.model is self._model
                and adapter.config is self._config, 'returned_adapter_model_config')
        metadata = adapter.metadata
        require(adapter.observation_profile == PROFILE and adapter.mouse_sampling == 'truncated_normal'
                and adapter.use_cuda_graph is False and adapter.graph is None
                and adapter.temporal_cache is None and adapter.execution_feedback is False
                and metadata['historyFrames'] == 41 and type(metadata['historyFrames']) is int
                and metadata['precision'] == 'float16' and str(adapter.dtype) == 'torch.float16'
                and metadata['mouseSamplingSource'] == 'explicit-override'
                and metadata['cacheInitialization'] == 'growing-history'
                and self._config.shared.n_seq_timesteps == 41
                and type(self._config.policy_model.n_transformer_layers) is int
                and self._config.policy_model.n_transformer_layers == 10
                and self._config.policy_model.attention_history_len == [41] * self._config.policy_model.n_transformer_layers
                and metadata['preprocessing']['observationProfile'] == PROFILE, 'resolved_native_profile')
        require(hashlib.sha256(canonical(metadata['compatibility'])).hexdigest()
                == self.compatibility_sha256, 'returned_source_manifest')

    def _close(self):
        """Attempt exactly one close on the currently owning layer; never retry or double-close."""
        require(not self._close_attempted, 'close_already_attempted')
        self._close_attempted = True
        if self._stream is not None:
            self._stream.close()
            require(self._stream.closed is True, 'stream_close_unconfirmed')
            self._stream = None
        elif self._fd is not None:
            self._api.close_fd(self._fd); self._fd = None
        elif self._raw is not None:
            self._api.close_handle(self._raw); self._raw = None

    def complete_adapter(self, adapter):
        """Issue a receipt only after all initialization and close operations have succeeded."""
        require(self._phase == 'constructing' and self._strict_loaded, 'incomplete_load')
        self._profile(adapter)
        self._time()
        self._close()
        receipt = _LoadReceipt(adapter, self._model, self._config, self.sha256, self.size,
                               self.source, self.config_sha256, self.compatibility_sha256, self._inert)
        metadata = receipt.metadata()
        require(len(canonical(metadata)) <= METADATA_BYTES, 'load_metadata_bound')
        adapter.metadata['checkpointLoad'] = metadata
        self._receipt = receipt
        self._phase = 'complete'

    def fail(self, primary):
        """Preserve primary and cleanup errors separately, never masking the original exception."""
        self._receipt = None
        self._primary = primary
        self._phase = 'failed'
        if not self._close_attempted:
            try:
                self._close()
            except BaseException as cleanup:
                self._cleanup = cleanup
                BaseException.add_note(primary, 'checkpoint cleanup failed: ' + type(cleanup).__name__[:64])

    def receipt_for(self, adapter, model_contract):
        """Require this scope's actual receipt, model and native profile; detached data cannot substitute."""
        require(self._phase == 'complete' and type(self._receipt) is _LoadReceipt, 'load_receipt_unavailable')
        receipt = self._receipt
        # The immutable completed receipt, not reassigned scope inputs, defines admission.
        bindings = ((self.sha256, receipt.checkpoint_sha256), (self.size, receipt.checkpoint_bytes),
                    (self.source, receipt.source_path), (self.config_sha256, receipt.config_sha256),
                    (self.compatibility_sha256, receipt.compatibility_sha256), (self._inert, receipt.inert))
        require(all(type(current) is type(verified) and current == verified
                    for current, verified in bindings), 'receipt_scope_binding_changed')
        self._profile(adapter)
        require(model_contract == dict(checkpointSha256=receipt.checkpoint_sha256, profile=PROFILE, mapping=MAPPING)
                and receipt.adapter is adapter and receipt.model is adapter.model
                and receipt.config is adapter.config, 'receipt_contract_identity')
        return receipt

    def status(self):
        """Report bounded state without error strings, checkpoint bytes, tensors or tracebacks."""
        return dict(phase=self._phase, strictLoaded=self._strict_loaded, closeAttempted=self._close_attempted,
                    ownerRetained=('stream' if self._stream is not None else 'fd' if self._fd is not None
                                   else 'handle' if self._raw is not None else None),
                    partialAdapterRetained=self._adapter is not None, partialModelRetained=self._model is not None,
                    receiptAvailable=self._receipt is not None,
                    primaryError=None if self._primary is None else type(self._primary).__name__[:64],
                    cleanupError=None if self._cleanup is None else type(self._cleanup).__name__[:64])


def bind_loaded_owner(scope, owner, bridge, intake, model_contract, *, inert=False):
    """Optional admission before the frozen coordinator; still inert-only and default off."""
    require(type(scope) is CheckpointLoadScope and inert is True and scope._inert,
            'loaded_owner_activation_unavailable')
    receipt = scope.receipt_for(owner._adapter, model_contract)
    from step_application_native_binding import StepApplicationNativeBinding
    admitted_contract = dict(checkpointSha256=receipt.checkpoint_sha256, profile=PROFILE, mapping=MAPPING)
    binding = StepApplicationNativeBinding(owner, bridge, intake, admitted_contract, inert=True)
    binding._checkpoint_load_receipt = receipt
    return binding
