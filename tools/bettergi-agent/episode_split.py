"""Make a whole-episode dataset split visible to exporters and fitting tools without changing native evidence."""
import hashlib
import json
from pathlib import Path

FORMAT='bettergi-episode-split-v1'
SPLITS=('train','holdout','diagnostic')


def manifest_sha(folder):
    """Hash only the explicitly selected resident manifest, using bounded memory."""
    with (Path(folder)/'patrol.json').open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def read_split(folder,run_id):
    """Read a reservation only when its episode identity and original manifest still match."""
    path=Path(folder)/'experience-split.json'
    if not path.exists():return None
    with path.open('rb') as source:raw=source.read(4097)
    if len(raw)>4096:raise ValueError('Episode split record exceeds its bound')
    data=json.loads(raw)
    if (set(data)!={'format','runId','sourceManifestSha256','split'} or data.get('format')!=FORMAT
            or data.get('runId')!=run_id or data.get('split') not in SPLITS
            or data.get('sourceManifestSha256')!=manifest_sha(folder)):
        raise ValueError('Episode split differs from its original source or run')
    return data


def reserve_split(folder,run_id,split):
    """Exclusively reserve a split; later exports cannot silently move a holdout into training."""
    if split not in SPLITS:raise ValueError('Unknown episode split')
    with (Path(folder)/'patrol.json').open(encoding='utf-8') as source:resident=json.load(source)
    if not isinstance(run_id,str) or not run_id or resident.get('runId')!=run_id:
        raise ValueError('Episode split must name the original resident run')
    data=dict(format=FORMAT,runId=run_id,sourceManifestSha256=manifest_sha(folder),split=split)
    path=Path(folder)/'experience-split.json'
    try:
        with path.open('x',encoding='utf-8') as target:json.dump(data,target,indent=2)
    except FileExistsError:
        if read_split(folder,run_id)!=data:
            raise ValueError('Episode already has a different reserved split')
    return data


def require_fit_allowed(metas):
    """Retained holdout and diagnostic episodes remain evaluable but cannot enter fitting."""
    if any(meta.get('datasetSplit') not in (None,'train') for meta in metas):
        raise ValueError('Holdout or diagnostic episodes cannot be used for fitting')
