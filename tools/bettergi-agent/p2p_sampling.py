"""Explicit P2P temperature experiments outside the original native adapter profile."""
import math

import torch

from model_adapters import OpenP2PAdapter, make_adapter as make_original_adapter


def validate_temperature(value):
    """Accept a finite positive scalar while rejecting booleans and coercible strings."""
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('P2P temperature must be finite and positive')
    return float(value)


class TemperatureP2PAdapter(OpenP2PAdapter):
    """Keep the upstream model and decoder while changing their explicit sampling scalar."""

    def __init__(self, *args, p2p_temperature, **kwargs):
        """Fix the temperature before any prediction or CUDA graph is prepared."""
        # Captured graphs retain this scalar for the adapter's entire lifetime.
        self._sampling_temperature = validate_temperature(p2p_temperature)
        if kwargs.get('checkpoint_scope') is not None:
            raise ValueError('P2P temperature experiments do not support native checkpoint qualification')
        super().__init__(*args, **kwargs)
        self.metadata.update(samplingTemperature=self._sampling_temperature,
                             samplingScope='experimental-replay-or-shadow')

    def _forward(self, frame, idx, state, uniform=None):
        """Use the original GPU contexts and inference method with the configured scalar."""
        with torch.inference_mode(), torch.device('cuda'), torch.autocast(
                'cuda', dtype=self.dtype, enabled=self.dtype != torch.float32):
            return self.model.online_kv_cache_predict(
                frame, idx, state, compile=False, sampling_temperature=self._sampling_temperature,
                text_tokens_embed=self.text, unif_rand=uniform)


def make_adapter(name, *, p2p_temperature=1.0, **kwargs):
    """Keep default construction exact and select the separate experimental class on opt-in."""
    temperature = validate_temperature(p2p_temperature)
    if temperature == 1.0:
        return make_original_adapter(name, **kwargs)
    if name != 'open-p2p':
        raise ValueError('p2p-temperature requires open-p2p')
    if kwargs.get('gamescaling_prefix_cache'):
        raise ValueError('gamescaling-prefix-cache requires the GameScaling model')
    if kwargs.get('checkpoint_scope') is not None:
        raise ValueError('P2P temperature experiments do not support native checkpoint qualification')
    if not torch.cuda.is_available():
        raise RuntimeError('A CUDA-enabled PyTorch build and accessible GPU are required')
    return TemperatureP2PAdapter(p2p_temperature=temperature, **kwargs)
