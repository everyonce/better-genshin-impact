"""Validated, local Open P2P instruction embeddings; no model work per video frame."""
import json
from pathlib import Path

import numpy as np

ENCODER = 'google/embeddinggemma-300m'
POOLING = 'attention-mask-mean-of-last-hidden-state; no-projection; no-normalization'


def load_goal(path):
    """Read a bounded plain-JSON goal vector produced by the matching upstream encoder."""
    path = Path(path)
    with path.open('rb') as stream:
        raw = stream.read(131073)
    if len(raw) > 131072:
        raise ValueError('Goal embedding exceeds 128 KiB')
    document = json.loads(raw)
    if (not isinstance(document, dict) or document.get('version') != 1 or document.get('encoder') != ENCODER
            or document.get('pooling') != POOLING or document.get('maxLength') != 128
            or not isinstance(document.get('instruction'), str) or not document['instruction'].strip()
            or len(document['instruction']) > 2000):
        raise ValueError('Goal must use the original Open P2P Gemma tokenizer and pooling contract')
    embedding = np.asarray(document['embedding'], dtype=np.float32)
    if embedding.shape != (1, 768) or not np.isfinite(embedding).all() or np.linalg.norm(embedding) < 1e-8:
        raise ValueError('Goal embedding must contain one finite, nonzero 768-dimensional vector')
    metadata = {key: value for key, value in document.items() if key != 'embedding'}
    return embedding, dict(metadata, file=str(path.resolve()))


def masked_mean(features, attention_mask):
    """Match upstream GemmaTextTokenizer.forward before its final shape expansion."""
    mask = attention_mask.unsqueeze(-1).expand(features.size()).float()
    return (features*mask).sum(1)/mask.sum(1).clamp(min=1e-9)
