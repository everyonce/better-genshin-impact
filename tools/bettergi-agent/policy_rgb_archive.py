"""Bounded exact wire-pixel evidence, independent of the lossy viewing video."""
import hashlib
from pathlib import Path

RGB192_BYTES = 192 * 192 * 3


def write_policy_rgb(directory, index, metadata, pixels):
    """Called only by the recorder worker after reserving these bytes in its shared budget."""
    if (metadata['width'], metadata['height']) != (192, 192) or type(pixels) is not bytes or len(pixels) != RGB192_BYTES:
        raise ValueError('Exact policy retention requires immutable complete RGB192 bytes')
    name = f"policy-{index:08d}-frame-{metadata['frameId']:012d}.rgb"
    with (Path(directory) / name).open('xb') as output:
        output.write(pixels)
    return dict(file=name, format='rgb24', width=192, height=192, bytes=len(pixels),
                sha256=hashlib.sha256(pixels).hexdigest())


def verify_policy_rgb(directory, reference):
    """Read only one original bounded RGB file; reject redirects, truncation and changed bytes."""
    if (not isinstance(reference, dict)
            or set(reference) != {'file', 'format', 'width', 'height', 'bytes', 'sha256'}
            or reference['format'] != 'rgb24' or reference['width'] != 192 or reference['height'] != 192
            or reference['bytes'] != RGB192_BYTES or not isinstance(reference['file'], str)):
        raise ValueError('Invalid exact policy RGB reference')
    root = Path(directory).resolve()
    path = (root / reference['file']).resolve()
    if path.parent != root or path.name != reference['file'] or path.suffix != '.rgb' or path.stat().st_size != RGB192_BYTES:
        raise ValueError('Exact policy RGB path or size differs')
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Exact policy RGB bytes changed')
    return path
