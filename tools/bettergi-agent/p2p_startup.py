"""Optional P2P graph preparation during policy loading, before a bridge is opened."""
import time


def validate_startup_options(args):
    """Keep startup preparation explicit and limited to masked P2P CUDA graphs."""
    enabled = getattr(args, 'p2p_prewarm', False)
    if type(enabled) is not bool:
        raise ValueError('p2p-prewarm requires an explicit boolean')
    if enabled and (getattr(args, 'model', None) != 'open-p2p'
                    or getattr(args, 'cuda_graph', False) is not True
                    or getattr(args, 'p2p_fast_start', False) is not True):
        raise ValueError('p2p-prewarm requires open-p2p, cuda-graph and p2p-fast-start')
    return enabled


def _require_empty_history(policy):
    """Never erase an active prediction or previously observed history during startup."""
    if (type(policy.steps_seen) is not int or policy.steps_seen != 0
            or policy._pending_feedback is not False or policy.idx.item() != 0
            or policy.temporal_cache.valid_tokens.item() != 0):
        raise ValueError('P2P startup preparation requires empty, settled history')


def prepare_startup_graph(policy):
    """Capture with the normal RGB192 layout and retain no synthetic observation state."""
    if (getattr(policy, 'use_cuda_graph', None) is not True
            or getattr(policy, 'temporal_cache', None) is None
            or policy.temporal_cache.enabled is not True
            or getattr(policy, 'graph', None) is not None):
        raise ValueError('P2P startup preparation requires a fresh masked CUDA graph policy')
    _require_empty_history(policy)
    import torch
    # Inference-mode allocations cannot later be updated by the ordinary live caller.
    if torch.is_inference_mode_enabled():
        raise ValueError('Prepare P2P startup outside torch.inference_mode')
    started = time.perf_counter_ns()
    # predict() uploads an HWC image then presents a strided CHW view. Preserve
    # that layout so preparation does not select a different convolution path.
    frame = torch.zeros((192, 192, 3), dtype=torch.uint8, device=policy.text.device).permute(2, 0, 1)
    if frame.stride() != (1, 576, 3):
        raise RuntimeError('Unexpected P2P startup frame layout')
    try:
        policy.temporal_cache.advance()
        # This uses the same one-time uniform draw as the cold first prediction.
        # Do not invoke predict(), decode mouse movement or emit controller input.
        policy._prepare_graph(frame)
    finally:
        policy.reset()
    _require_empty_history(policy)
    if policy.graph is None or policy.metadata.get('graphCaptureValidated') is not True:
        raise RuntimeError('P2P startup graph validation did not complete')
    torch.cuda.synchronize()
    result = dict(phase='policy_load', graphPrepared=True, graphCaptureValidated=True,
                  preparationMs=(time.perf_counter_ns()-started)/1e6,
                  preparationImage='synthetic-zero-rgb192; graph preparation only',
                  historyFramesAfterPreparation=0, controllerActionsEmitted=0)
    policy.metadata['startupGraphPreparation'] = result
    return result
