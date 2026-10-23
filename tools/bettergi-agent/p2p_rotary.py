"""Evaluate upstream RoPE's FP32 formula without a finite position cache.

The original pos_embed.py (MIT, based on torchtune) constructs an outer product
of position and theta, then stacks cosine and sine. Computing only the queried
positions uses the same formula while permitting a continuously rolling KV cache.
"""
import torch


def rotary_values(theta, sequence_length, input_pos=None):
    """Return FP32 cosine/sine values for only the current device-side positions."""
    positions = (torch.arange(sequence_length, device=theta.device, dtype=torch.float32)
                 if input_pos is None else input_pos.float())
    angles = positions.unsqueeze(-1) * theta.float()
    return torch.stack((angles.cos(), angles.sin()), dim=-1)


def restore_rotary_precision(model):
    """Restore the upstream FP32 frequencies after converting model weights to FP16."""
    for module in model.modules():
        if type(module).__name__ != 'RotaryPositionalEmbeddings':
            continue
        exponents = torch.arange(0, module.dim, 2, device=module.theta.device).float() / module.dim
        theta = 1.0 / (module.base ** exponents)
        module.register_buffer('theta', theta, persistent=False)
