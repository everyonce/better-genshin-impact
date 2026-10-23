"""Native PyTorch replacement for Open P2P's FlexAttention transport.

This evaluates the upstream boolean mask function exactly, using dense SDPA.
It changes the execution backend, not the learned weights or attention graph.
No Triton, CUDA compiler, or global monkey patch is required.
"""
from dataclasses import dataclass, replace

import torch
from torch.nn import functional as F


@dataclass
class DenseMask:
    """Keep the upstream mask callable and decode-offset metadata."""
    mask_mod: object
    BLOCK_SIZE: tuple = (128, 128)
    seq_lengths: tuple = (0, 0)

    def to(self, device):
        """Masks are evaluated directly on the query's device."""
        return self

    def __getitem__(self, index):
        """Decode slicing changes the mask callable in upstream get_decode_mask."""
        return replace(self)


def create_block_mask(mask_mod, B=None, H=None, Q_LEN=0, KV_LEN=0,
                      BLOCK_SIZE=128, device=None, **kwargs):
    """Represent a mask without allocating the full training sequence matrix."""
    block = (BLOCK_SIZE, BLOCK_SIZE) if isinstance(BLOCK_SIZE, int) else BLOCK_SIZE
    return DenseMask(mask_mod, block, (Q_LEN, KV_LEN))


def flex_attention(query, key, value, block_mask, enable_gqa=False, **kwargs):
    """Apply the exact upstream per-token mask with stock scaled attention."""
    q = torch.arange(query.shape[-2], device=query.device)[:, None]
    k = torch.arange(key.shape[-2], device=query.device)[None, :]
    mask = block_mask.mask_mod(0, 0, q, k)
    return F.scaled_dot_product_attention(
        query.contiguous(), key.contiguous(), value.contiguous(),
        attn_mask=mask, dropout_p=0.0, enable_gqa=enable_gqa,
    )
