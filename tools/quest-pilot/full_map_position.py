"""Read a retained BetterGI full map; produce position evidence, never gameplay input."""
import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path
from PIL import Image


def center_marker(image):
    """Require a compact cyan player marker near the map viewport center."""
    if image.size == (1920, 1080):
        image = image.crop((920, 500, 1000, 580))
    if image.size != (80, 80):
        return False
    pixels = image.convert('RGB')
    candidates = {(x, y) for y in range(80) for x in range(80)
                  if (lambda c: c[0] < 100 and c[1] > 140 and c[2] > 170)(pixels.getpixel((x, y)))}
    found = []
    while candidates:
        component = [candidates.pop()]
        for x, y in component:
            for neighbor in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
                if neighbor in candidates:
                    candidates.remove(neighbor)
                    component.append(neighbor)
        if len(component) < 90:
            continue
        xs, ys = zip(*component)
        if (16 <= max(xs)-min(xs)+1 <= 48 and 16 <= max(ys)-min(ys)+1 <= 48
                and math.hypot(sum(xs)/len(xs)-40, sum(ys)/len(ys)-40) <= 12):
            found.append(component)
    return len(found) == 1


def validate(source, audit, session, frame, now, marker, image_hash):
    if (source.get('session') != session or source.get('frameId') != frame
            or not 0 <= now-source.get('timestamp', 0) <= 600000
            or not source.get('hud', {}).get('bigMap') or not marker):
        raise ValueError('Fresh centered same-session full map required')
    rows = source.get('ocr', [])
    if not any(''.join(str(r.get('text', '')).split()) in ['UID:693306810', 'UID693306810', '693306810']
               and r.get('x', 0) > 1600 and r.get('y', 0) > 1020 for r in rows):
        raise ValueError('Original account map required')
    matched = [r for r in audit.get('rows', []) if r.get('frame') == frame]
    if not audit.get('bigMap') or len(matched) != 1 or matched[0].get('sha256', '').lower() != image_hash.lower():
        raise ValueError('Exact native full-map replay/hash required')
    r = matched[0].get('result', {})
    p = r.get('position') or {}
    if (r.get('inliers', 0) < 20 or r.get('inliers', 0) / max(1, r.get('good', 0)) < .7
            or r.get('spreadX', 0) < .25 or r.get('spreadY', 0) < .25
            or not all(isinstance(p.get(k), (int, float)) and math.isfinite(p[k]) for k in ['x', 'y'])
            or not -1700 <= p['x'] <= -500 or not 1400 <= p['y'] <= 2850):
        raise ValueError('Sparse, clustered or implausible full-map match')
    return {'sourcePositionVerified': True, 'navigationAuthorized': False, 'session': session,
            'frameId': frame, 'timestamp': source['timestamp'], 'sha256': image_hash,
            'position': dict(p, map='Teyvat'), 'inliers': r['inliers'], 'goodMatches': r['good'],
            'spreadX': r['spreadX'], 'spreadY': r['spreadY'],
            'nativeMatchMs': matched[0].get('elapsedMs'),
            'limitation': 'Position of this centered map capture only; no route, elevation, current-state or hazard-clearance proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frame', type=int, required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', default='artifacts/act-two-full-map-position-latest.json')
    args = parser.parse_args()
    root = Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
    stem = root/'observations'/args.session/f'frame-{args.frame:04}'
    source = json.loads(stem.with_suffix('.json').read_text(encoding='utf-8-sig'))
    image_hash = hashlib.sha256(stem.with_suffix('.png').read_bytes()).hexdigest()
    with Image.open(stem.with_suffix('.png')) as image:
        marker = center_marker(image)
    run = subprocess.run(['pwsh', '-NoProfile', '-File', 'tools/quest-pilot/audit-springvale-localization.ps1',
                          '-RuntimeDirectory', str(root.parents[2]), '-Session', args.session,
                          '-BigMap', '-FrameIds', str(args.frame)], capture_output=True, text=True,
                         encoding='utf-8', timeout=20)
    if run.returncode:
        raise SystemExit(run.stderr.strip() or 'Native map replay failed')
    result = validate(source, json.loads(run.stdout), args.session, args.frame,
                      int(time.time()*1000), marker, image_hash)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
