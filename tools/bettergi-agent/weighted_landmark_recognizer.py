"""Freeze and replay the single half-weight G7 shadow metric without changing the G4/G6 scorer."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from landmark_recognizer import (CENTERED_FORMAT, CENTERED_METHOD, CENTERED_METRIC, G4_SHA256,
                                 G4_TEMPLATES_SHA256, G4_TRAINING_SHA256, LandmarkRecognizer, signature)
from run_rdp_patrol import native_qpc_sample

FORMAT = 'bettergi-checkpoint-landmarks-v3'
METRIC = 'g4-spatial-channel-residual-plus-one-half-global-rgb-mean-energy-v1'
METHOD = 'nearest G4 prototype, full spatial contrast plus half mean-color squared distance, class-order ties'
EXPOSED_STAIR_RUN = 'b254d2f50eff48afa1e00c97806583fe'
EXPOSED_STAIR_RGB = '0a9e9dff683ed3d1be8c4283ca28b54432a133a12c730b96506a6b24c43877bc'
DEVELOPMENT_SHA256 = '271ae34661863dec6b9b0685a6cd6222f2fc80c9d9b0ab7298e7f2c364a7a0f8'


def weight_features(features):
    """Scale each spatial channel mean by sqrt(1/2) while retaining the full spatial residual."""
    grid = np.asarray(features,dtype=np.float64).reshape(-1,120,3)
    return (grid + (np.sqrt(.5)-1.)*grid.mean(axis=1,keepdims=True)).reshape(-1,360)


class WeightedLandmarkRecognizer(LandmarkRecognizer):
    """Read-only G7 scorer. Precompute all transformed templates once per observer."""
    def __init__(self, data):
        if not isinstance(data,dict) or (data.get('format'),data.get('method'),data.get('distanceMetric')) != (FORMAT,METHOD,METRIC):
            raise ValueError('Expected the pinned half-weight G7 metric and format')
        # The frozen G6 verifier already authenticates the exact G4 training set, feature and provenance.
        super().__init__(dict(data, format=CENTERED_FORMAT, method=CENTERED_METHOD, distanceMetric=CENTERED_METRIC))
        self.data = data
        self.weighted_templates = weight_features(self.templates)

    def predict(self, rgb):
        """Squared Euclidean distance in the transformed features is S+0.5*C for every prototype."""
        error = self.weighted_templates - weight_features(signature(rgb))
        distances = np.einsum('ij,ij->i',error,error)
        i = int(np.argmin(distances))
        return dict(station=self.labels[i],squaredDistance=float(distances[i]))


def load_landmark_shadow(path):
    """Load one shadow observer and bind its digest to the same bytes used to select its scorer."""
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if (not isinstance(data,dict) or (data.get('format') != FORMAT
            and (data.get('method') == METHOD or data.get('distanceMetric') == METRIC))):
        raise ValueError('G7 distance metadata requires its matching format')
    head = WeightedLandmarkRecognizer(data) if data.get('format') == FORMAT else LandmarkRecognizer(data)
    head.checkpoint_id = hashlib.sha256(raw).hexdigest()
    return head


def freeze(base, diagnostic, destination):
    """Freeze precisely G7 and quarantine the 35 previously inspected originals and their leases."""
    raw = Path(base).read_bytes()
    if hashlib.sha256(raw).hexdigest() != G4_SHA256:
        raise ValueError('G7 requires the exact frozen G4 checkpoint')
    data = dict(json.loads(raw), format=FORMAT, method=METHOD, distanceMetric=METRIC, sourceCheckpointSha256=G4_SHA256)
    head = WeightedLandmarkRecognizer(data)
    raw = json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
    dev_raw = Path(diagnostic).read_bytes()
    rows = json.loads(dev_raw)['rows']
    excluded = {row['name']:row['rawSha256'] for row in rows}
    manifest_sha = hashlib.sha256(json.dumps(excluded,sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
    if len(rows)!=35 or manifest_sha!=DEVELOPMENT_SHA256 or excluded.get(EXPOSED_STAIR_RUN+'/10')!=EXPOSED_STAIR_RGB:
        raise ValueError('Expected all 35 exposed development originals, including the historical stair frame')
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    with (destination/'gen-07.json').open('xb') as out:
        out.write(raw)
    clock = native_qpc_sample()
    if not clock:
        raise RuntimeError('Windows QPC is required for the freeze receipt')
    receipt = dict(version=1, mode='offline-shadow-only', sourceCheckpointSha256=G4_SHA256, prototypes=len(head.labels),
                   checkpointSha256=hashlib.sha256(raw).hexdigest(), distanceMetric=METRIC, meanEnergyWeight=.5,
                   templatesSha256=G4_TEMPLATES_SHA256, trainingRunsSha256=G4_TRAINING_SHA256,
                   frozenAtUtc=datetime.now(timezone.utc).isoformat(),
                   freezeQpc=dict(clock='windows-query-performance-counter',frequencyHz=clock[0],ticks=clock[1]),
                   scorerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   baseScorerSha256=hashlib.sha256(Path(__file__).with_name('landmark_recognizer.py').read_bytes()).hexdigest(),
                   evaluator='weighted_landmark_recognizer.load_landmark_shadow(checkpoint).predict(rgb192)',
                   developmentDiagnosticSha256=hashlib.sha256(dev_raw).hexdigest(), developmentOriginals=excluded,
                   excludedWholeLeases=sorted({name.split('/')[0] for name in excluded}))
    with (destination/'freeze.json').open('x',encoding='utf-8') as out:
        json.dump(receipt,out,indent=2)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True,type=Path)
    parser.add_argument('--development-diagnostic',required=True,type=Path)
    parser.add_argument('--out-dir',required=True,type=Path)
    args = parser.parse_args()
    receipt = freeze(args.base,args.development_diagnostic,args.out_dir)
    print(json.dumps({k:receipt[k] for k in ('checkpointSha256','frozenAtUtc','freezeQpc','scorerSha256','baseScorerSha256')}))
