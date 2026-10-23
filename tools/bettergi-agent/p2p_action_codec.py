"""Resolve the official P2P mouse decoder without changing its action tokens."""
from pathlib import Path

import yaml


MOUSE_SAMPLING_MODES = ('mean', 'conservative', 'truncated_normal')


def resolve_mouse_sampling(checkpoint, override=None, fallback='mean'):
    """Prefer the checkpoint's declared decoder; retain explicit legacy modes.

    The downloaded checkpoint keeps model_config.yaml beside its weights. A
    standalone weights file instead uses the already-loaded upstream config.
    Missing inference settings in an existing file use upstream's default mean.
    """
    if override is not None:
        mode, source = override, 'explicit-override'
    else:
        config_path = Path(checkpoint).with_name('model_config.yaml')
        if config_path.is_file():
            config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
            if not isinstance(config, dict):
                raise ValueError('P2P checkpoint model_config.yaml must contain a mapping')
            inference = config.get('inference', {})
            if not isinstance(inference, dict):
                raise ValueError('P2P checkpoint inference settings must contain a mapping')
            mode = inference.get('mouse_sampling_approach', 'mean')
            source = 'checkpoint-config'
        else:
            mode, source = fallback, 'upstream-config-fallback'
    if mode not in MOUSE_SAMPLING_MODES:
        raise ValueError(f'Unsupported P2P mouse sampling mode: {mode!r}')
    return mode, source
