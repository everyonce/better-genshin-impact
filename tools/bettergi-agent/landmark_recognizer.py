"""Learn station appearance from audited patrol checkpoint images. No controller IO."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np

from audit_hybrid_run import audit, require
from patrol_landmarks import circuit_visits, indexed_frames
from train_steering import distinct

FORMAT = 'bettergi-checkpoint-landmarks-v1'
CLASSES = ('sidewalk-junction', 'stair-front', 'west-lamp')
ROLES = ('entry-or-previous-return', 'junction-from-stairs', 'west-lamp-from-junction',
         'junction-from-west-lamp', 'stair-front-from-junction')
FEATURE = 'rgb192 crop(x48:144,y40:120);8x8-cell mean;subtract 0.65*crop channel mean;divide by 255'


def signature(rgb):
    """Extract a 12-by-10 RGB grid only from the center image, before any labeling or scoring."""
    if isinstance(rgb, (bytes, bytearray, memoryview)):
        rgb = np.frombuffer(rgb, dtype=np.uint8).reshape(192,192,3)
    require(isinstance(rgb, np.ndarray) and rgb.shape == (192,192,3) and rgb.dtype == np.uint8, 'RGB192 required')
    cells = rgb[40:120,48:144].reshape(10,8,12,8,3).mean(axis=(1,3), dtype=np.float32)
    return ((cells-.65*cells.mean(axis=(0,1)))/255).ravel()


class LandmarkRecognizer:
    """Nearest training checkpoint under a fixed image-only feature metric."""
    def __init__(self, data):
        """Sort templates into explicit class order for deterministic distance ties."""
        require(data.get('format') == FORMAT and data.get('feature') == FEATURE and data.get('classes') == list(CLASSES)
                and data.get('deployment') == 'checkpoint-shadow-only', 'Unrecognized landmark classifier')
        rows = sorted(data['prototypes'], key=lambda r: CLASSES.index(r['station']))
        self.templates = np.asarray([r['signature'] for r in rows], dtype=np.float32)
        self.labels = [r['station'] for r in rows]
        require(set(self.labels) == set(CLASSES) and self.templates.shape == (len(rows),360)
                and np.isfinite(self.templates).all(), 'Missing classes or invalid landmark prototypes')
        self.checkpoint_id, self.data = None, data

    @classmethod
    def load(cls, path):
        """Load the portable templates and hash the exact checkpoint file bytes."""
        raw = Path(path).read_bytes()
        obj = cls(json.loads(raw))
        obj.checkpoint_id = hashlib.sha256(raw).hexdigest()
        return obj

    def predict(self, rgb):
        """Accept pixels alone. Output a station hypothesis at an already-verified checkpoint."""
        error = self.templates-signature(rgb)
        distances = np.einsum('ij,ij->i',error,error)
        i = int(np.argmin(distances))
        return dict(station=self.labels[i], squaredDistance=float(distances[i]))


def decode(directory, refs, count, ffmpeg, ffprobe):
    """Decode audited absolute indexes on a single CPU thread and verify exact MP4 presentation time."""
    video = directory/'frames.mp4'
    probe = [ffprobe,'-v','error','-threads','1','-select_streams','v:0','-show_frames','-show_streams',
             '-show_entries','stream=width,height:frame=best_effort_timestamp_time','-of','json',str(video)]
    meta = json.loads(subprocess.run(probe,capture_output=True,timeout=90,check=True).stdout)
    require(len(meta['streams']) == 1 and (meta['streams'][0]['width'],meta['streams'][0]['height']) == (192,192)
            and len(meta['frames']) == count, 'Retained video does not match source index')
    indexes = sorted({r['videoFrameIndex'] for r in refs})
    for r in refs:
        require((r['width'],r['height']) == (192,192) and 0 <= r['videoFrameIndex'] < count and
                abs(float(meta['frames'][r['videoFrameIndex']]['best_effort_timestamp_time'])-r['videoPtsSeconds']) <= .001,
                'Selected encoded timestamp mismatch')
    select = '+'.join(f'eq(n\\,{i})' for i in indexes)
    cmd = [ffmpeg,'-nostdin','-v','error','-hwaccel','none','-threads','1','-filter_threads','1','-i',str(video),
           '-map','0:v:0','-vf','select='+select,'-fps_mode','passthrough','-threads','1','-pix_fmt','rgb24',
           '-f','rawvideo','pipe:1']
    raw = subprocess.run(cmd,capture_output=True,timeout=90,check=True).stdout
    require(len(raw) == len(indexes)*192*192*3, 'Decoded frame count mismatch')
    pixels = np.frombuffer(raw,dtype=np.uint8).reshape(-1,192,192,3)
    return dict(zip(indexes,pixels))


def load_views(path, ffmpeg, ffprobe):
    """Obtain supervision from audited native visits, join the exact source frame and decode original pixels."""
    path = Path(path).resolve()
    repository = Path(__file__).resolve().parents[2]
    recordings = path.with_name(path.stem+'-recording')
    summary = audit(path, recordings, repository=repository, minimum_circuits=1)
    require(summary['passed'] and not summary['partialPatrolLegs'], 'Patrol must end on a verified full circuit')
    run = json.loads(path.read_bytes())
    parts = [(e,json.loads((repository/e['report']).read_bytes())) for e in run['segments']]
    start, = [e['frameId'] for _,p in parts for e in p['hybridNavigationEvents'] if e['type']=='hybridStartVerified']
    visits = [v for n in range(1,summary['verifiedCircuits']+1) for v in circuit_visits(summary,start,n)]
    target = {v['frameId'] for v in visits}
    samples, digest = {}, hashlib.sha256()
    for e,p in parts:
        directory = recordings/f"{e['number']:05d}"
        frames, count = indexed_frames(directory,p)
        found = sorted(target & frames.keys())
        if not found:
            continue
        refs = [frames[f] for f in found]
        decoded = decode(directory,refs,count,ffmpeg,ffprobe)
        for f in refs:
            fid = f['frameId']
            require(fid not in samples, 'Duplicated source index across segments')
            src, rgb = f['sourceFrame'], decoded[f['videoFrameIndex']]
            evidence = dict(frameId=fid,segment=e['number'],videoFrameIndex=f['videoFrameIndex'],
                sourceTimestamp100ns=src['timestamp100ns'],captureEpoch=src['captureEpoch'],
                rgbSha256=hashlib.sha256(rgb.tobytes()).hexdigest())
            digest.update(json.dumps(evidence,sort_keys=True).encode())
            samples[fid] = (rgb,evidence)
    require(set(samples) == target, 'An audited station image is missing')
    labels = {}
    for v in visits:
        require(labels.setdefault(v['frameId'],v['station']) == v['station'], 'Conflicting supervision on a shared frame')
    ticks = [e['sourceTimestamp100ns'] for _,e in samples.values()]
    epochs = {e['captureEpoch'] for _,e in samples.values()}
    require(len(epochs)==1, 'An RDP capture epoch changed within the run')
    hello = parts[0][1]['hello']
    meta = dict(path=str(path),runId=run['runId'],lease=[hello['sessionId'],hello['ownerEpoch']],captureEpoch=epochs.pop(),
                sourceInterval100ns=[min(ticks),max(ticks)],evidenceSha256=digest.hexdigest(),
                circuits=summary['verifiedCircuits'],orderedVisits=len(visits),uniqueImages=len(samples))
    return meta,visits,samples


def fit(runs):
    """Retain each unique labeled training image once, including distinct approaches to the junction."""
    metas = [r[0] for r in runs]
    distinct(metas)
    prototypes = []
    for meta,visits,samples in runs:
        for fid,station in sorted({(v['frameId'],v['station']) for v in visits}):
            rgb,evidence = samples[fid]
            prototypes.append(dict(runId=meta['runId'],station=station,evidence=evidence,signature=signature(rgb).tolist()))
    return dict(format=FORMAT,feature=FEATURE,classes=list(CLASSES),deployment='checkpoint-shadow-only',
                method='nearest unique labeled prototype, squared Euclidean distance, class-order ties',
                trainingRuns=metas,prototypes=prototypes,
                implementationSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def metrics(rows, majority):
    """Report true-row, predicted-column confusion and the training-set majority reference."""
    conf = [[0]*len(CLASSES) for _ in CLASSES]
    for r in rows:
        conf[CLASSES.index(r['station'])][CLASSES.index(r['prediction'])] += 1
    correct = sum(conf[i][i] for i in range(len(CLASSES)))
    return dict(samples=len(rows),correct=correct,accuracy=correct/len(rows),classes=list(CLASSES),confusion=conf,
                classRecall={s:conf[i][i]/sum(conf[i]) if sum(conf[i]) else None for i,s in enumerate(CLASSES)},
                majority=majority,majorityCorrect=sum(r['station']==majority for r in rows),
                majorityAccuracy=sum(r['station']==majority for r in rows)/len(rows))


def evaluate(head, run):
    """Score both unique source frames and repeated circuit boundaries on a sealed unseen run."""
    meta,visits,samples = run
    distinct([*head.data['trainingRuns'],meta])
    head.predict(next(iter(samples.values()))[0])  # Warm the image operations before timing.
    predictions, latency = {}, []
    for fid,(rgb,_) in samples.items():
        start = time.perf_counter_ns()
        predictions[fid] = head.predict(rgb)['station']
        latency.append((time.perf_counter_ns()-start)/1000)
    counts = Counter(head.labels)
    majority = max(CLASSES,key=counts.__getitem__)
    rows = [dict(**v,prediction=predictions[v['frameId']],role=ROLES[v['stop']],evidence=samples[v['frameId']][1]) for v in visits]
    unique = {v['frameId']:v for v in rows}
    return dict(checkpointId=head.checkpoint_id,run=meta,unique=metrics(list(unique.values()),majority),
                allVisits=metrics(rows,majority),perApproach={role:metrics([r for r in rows if r['role']==role],majority)
                for role in ROLES},latencyMicroseconds=dict(samples=len(latency),p50=float(np.median(latency)),
                p95=float(np.percentile(latency,95))),visits=rows)


def main():
    """Freeze a generation without reading evaluation runs, then score existing checkpoints together."""
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    train=sub.add_parser('train')
    train.add_argument('--train-run',type=Path,action='append',required=True)
    test=sub.add_parser('evaluate')
    test.add_argument('--checkpoint',type=Path,action='append',required=True)
    test.add_argument('--eval-run',type=Path,required=True)
    for cmd in (train,test):
        cmd.add_argument('--out',type=Path,required=True)
        cmd.add_argument('--ffmpeg',default='ffmpeg')
        cmd.add_argument('--ffprobe',default='ffprobe')
    args=parser.parse_args()
    require(not args.out.exists(),'Choose a fresh output path')
    if args.command=='train':
        data=fit([load_views(p,args.ffmpeg,args.ffprobe) for p in args.train_run])
    else:
        heads=[LandmarkRecognizer.load(p) for p in args.checkpoint]
        run=load_views(args.eval_run,args.ffmpeg,args.ffprobe)
        data=dict(format=FORMAT,scope='Verified patrol station checkpoints only',evaluations=[evaluate(h,run) for h in heads])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x',encoding='utf-8') as f:
        json.dump(data,f,separators=(',',':'),allow_nan=False)
    print(hashlib.sha256(args.out.read_bytes()).hexdigest(),args.out)


if __name__=='__main__':
    main()
