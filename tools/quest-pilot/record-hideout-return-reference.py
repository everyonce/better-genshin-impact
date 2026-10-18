"""Preserve at most eight compact route regression references, never bulk captures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument('--session', required=True)
p.add_argument('--frame', type=int, required=True)
p.add_argument('--index', type=int, choices=range(8), required=True)
p.add_argument('--landmarks', required=True)
a = p.parse_args()
root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
source = root / 'observations' / a.session / f'frame-{a.frame:04}.png'
metadata = json.loads(source.with_suffix('.json').read_text(encoding='utf-8-sig'))
if metadata.get('session') != a.session or metadata.get('frameId') != a.frame:
    raise ValueError('Reference identity mismatch')
target = Path('Test/ActOnePilot/fixtures/hideout-return')
target.mkdir(exist_ok=True)
image_path = target / f'checkpoint-{a.index}.jpg'
if image_path.exists():
    raise ValueError('Existing reference is unique evidence; do not overwrite automatically')
with Image.open(source) as image:
    image.thumbnail((1280, 720))
    image.convert('RGB').save(image_path, quality=75, optimize=True)
if image_path.stat().st_size > 300000:
    raise ValueError('Reference exceeds compact regression budget')
metadata.update(referenceLandmarks=a.landmarks, sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                referencePurpose='Compact route regression; not full-resolution recognition input')
image_path.with_suffix('.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
print(json.dumps(dict(reference=str(image_path), bytes=image_path.stat().st_size)))
