"""Freeze the predeclared G6 metric over G4's exact templates without viewing any images."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from landmark_recognizer import (CENTERED_FORMAT, CENTERED_METHOD, CENTERED_METRIC, G4_SHA256,
                                 G4_TEMPLATES_SHA256, G4_TRAINING_SHA256, LandmarkRecognizer)
from run_rdp_patrol import native_qpc_sample


def freeze(base, destination):
    """Persist a deterministic checkpoint and a separate, write-once Windows freeze receipt."""
    raw = Path(base).read_bytes()
    if hashlib.sha256(raw).hexdigest() != G4_SHA256:
        raise ValueError('The centered challenger requires the exact frozen G4 checkpoint')
    data = dict(json.loads(raw), format=CENTERED_FORMAT, method=CENTERED_METHOD,
                sourceCheckpointSha256=G4_SHA256, distanceMetric=CENTERED_METRIC)
    head = LandmarkRecognizer(data)
    content = json.dumps(data, sort_keys=True, separators=(',',':'), allow_nan=False).encode('ascii')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination/'gen-06.json').open('xb') as output:
        output.write(content)
    qpc = native_qpc_sample()
    if not qpc:
        raise RuntimeError('Windows QPC required for independent evaluation')
    receipt = dict(version=1, mode='offline-shadow-only', sourceCheckpointSha256=G4_SHA256,
                   checkpointSha256=hashlib.sha256(content).hexdigest(), distanceMetric=CENTERED_METRIC,
                   prototypes=len(head.labels), templatesSha256=G4_TEMPLATES_SHA256, trainingRunsSha256=G4_TRAINING_SHA256,
                   frozenAtUtc=datetime.now(timezone.utc).isoformat(),
                   freezeQpc=dict(clock='windows-query-performance-counter',frequencyHz=qpc[0],ticks=qpc[1]),
                   evaluator='LandmarkRecognizer.load(checkpoint).predict(rgb192)',
                   scorerSha256=hashlib.sha256(Path(__file__).with_name('landmark_recognizer.py').read_bytes()).hexdigest())
    with (destination/'freeze.json').open('x', encoding='utf-8') as output:
        json.dump(receipt,output,indent=2)
    return receipt


def main():
    """Create exactly one new directory for this fixed G4-derived challenger."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',required=True,type=Path)
    p.add_argument('--out-dir',required=True,type=Path)
    args = p.parse_args()
    print(json.dumps(freeze(args.base,args.out_dir)))


if __name__ == '__main__':
    main()
