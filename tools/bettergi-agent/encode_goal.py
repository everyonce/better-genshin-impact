"""Encode an instruction once on CPU using the exact pretrained P2P text space."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from goal_embedding import ENCODER, POOLING, load_goal, masked_mean


def file_hash(path):
    """Hash model identity without retaining its large weight file in memory."""
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def reference_methods(source, torch):
    """Extract only the official tokenizer/forward methods for direct parity verification."""
    path = Path(source)/'elefant/text_tokenizer/text_tokenizer.py'
    module = ast.parse(path.read_text(encoding='utf-8'))
    owner = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'GemmaTextTokenizer')
    methods = [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name in ('tokenize', 'forward')]
    if len(methods) != 2:
        raise ValueError('The official Gemma tokenizer methods could not be identified')
    # Both callers already use inference_mode; compiler wrappers do not affect this reference.
    for method in methods:
        method.decorator_list = []
    namespace = {'torch': torch}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['tokenize'], namespace['forward']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--encoder', required=True, help='Local official EmbeddingGemma directory')
    parser.add_argument('--source', required=True, help='Local official open-p2p source for parity checking')
    parser.add_argument('--instruction', required=True)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not args.instruction.strip() or len(args.instruction) > 2000 or not 1 <= args.threads <= 8:
        parser.error('Provide a nonempty instruction of at most 2000 characters and 1–8 CPU threads')
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(args.threads)
    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(args.encoder, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(args.encoder, local_files_only=True, trust_remote_code=False,
                                     dtype=torch.float32, attn_implementation='sdpa').eval()
    if model.config.hidden_size != 768 or model.config.model_type != 'gemma3_text':
        raise ValueError('Expected the original 768-dimensional Gemma text transformer')
    loaded = time.perf_counter()
    token_count = len(tokenizer(args.instruction, truncation=False)['input_ids'])
    if token_count > 128:
        raise ValueError('This instruction exceeds the original 128-token limit; shorten it rather than silently truncate it')
    tokens = tokenizer(text=[args.instruction], return_tensors='pt', padding='max_length',
                       truncation=True, max_length=128)
    original_tokenize, original_forward = reference_methods(args.source, torch)
    original = SimpleNamespace(tokenizer=tokenizer, gemma_embedding=model, max_position_embeddings=128,
                               n_text_tokens=1, embed_dim=768)
    reference_tokens = original_tokenize(original, args.instruction)
    if any(not torch.equal(tokens[key], reference_tokens[key]) for key in ('input_ids', 'attention_mask')):
        raise RuntimeError('Tokenization does not match the upstream implementation')
    with torch.inference_mode():
        features = model(tokens['input_ids'], tokens['attention_mask']).last_hidden_state
        embedding = masked_mean(features, tokens['attention_mask'])
        encoded = time.perf_counter()
        reference = original_forward(original, **reference_tokens).reshape(1, 768)
    error = float((embedding-reference).abs().max())
    if error != 0 or not torch.isfinite(embedding).all():
        raise RuntimeError(f'Embedding does not exactly match upstream forward (max error {error})')
    result = {'version': 1, 'encoder': ENCODER, 'pooling': POOLING, 'maxLength': 128,
              'instruction': args.instruction, 'tokenCount': token_count, 'dtype': 'float32', 'device': 'cpu',
              'encoderSha256': file_hash(Path(args.encoder)/'model.safetensors'),
              'tokenizerSha256': file_hash(Path(args.encoder)/'tokenizer.json'),
              'modelLoadMs': (loaded-started)*1000, 'encodeMs': (encoded-loaded)*1000,
              'parity': {'tokenIdsExact': True, 'upstreamEmbeddingMaxError': error},
              'embedding': embedding.tolist()}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    _, metadata = load_goal(output)
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
