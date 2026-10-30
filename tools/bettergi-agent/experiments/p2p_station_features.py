"""Bounded offline station recognition using the installed P2P convolutional weights; never controls the game."""
import argparse
from datetime import datetime,timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from landmark_recognizer import CLASSES


def digest(raw):
    """Hash only specified evidence or the selected encoder tensors."""
    return hashlib.sha256(raw).hexdigest()


def scene(rgb):
    """Exclude the minimap and side HUD before any learned visual feature computation."""
    if not isinstance(rgb,np.ndarray) or rgb.shape!=(192,192,3) or rgb.dtype!=np.uint8:
        raise ValueError('Exact original RGB192 input required')
    return np.asarray(Image.fromarray(rgb).crop((32,32,160,160)).resize((192,192),Image.Resampling.HAMMING)).copy()


def normalize(vector):
    """Reject invalid embeddings instead of manufacturing a station label."""
    vector=np.asarray(vector,dtype=np.float32)
    norm=float(np.linalg.norm(vector))
    if vector.shape!=(1008,) or not np.isfinite(vector).all() or not np.isfinite(norm) or norm<=1e-12:
        raise ValueError('Invalid convolutional station embedding')
    return vector/norm


def predict(vector,prototypes,labels):
    """Use normalized prototypes with deterministic class-order ties and report the competing-class margin."""
    # A float64 reduction also keeps identical prototype rows tied across BLAS tail kernels.
    scores=np.einsum('ij,j->i',np.asarray(prototypes,dtype=np.float32),normalize(vector),dtype=np.float64,optimize=False)
    if len(scores)!=len(labels) or set(labels)!=set(CLASSES) or not np.isfinite(scores).all():
        raise ValueError('Incomplete or invalid station prototype bank')
    best=[max(float(score) for score,label in zip(scores,labels) if label==station) for station in CLASSES]
    index=int(np.argmax(best))
    return dict(station=CLASSES[index],cosineSimilarity=best[index],margin=best[index]-max(best[:index]+best[index+1:]))


def tensor_digest(state):
    """Bind tensor names, shapes, dtypes and actual bytes without reading unrelated checkpoint storage."""
    result=hashlib.sha256()
    for name,tensor in sorted(state.items()):
        result.update(json.dumps([name,list(tensor.shape),str(tensor.dtype)],separators=(',',':')).encode())
        result.update(tensor.detach().cpu().contiguous().view(-1).view(__import__('torch').uint8).numpy().tobytes())
    return result.hexdigest()


class ThermalGuard:
    """Stop this offline GPU experiment on unavailable telemetry or the existing 78 C boundary."""
    def __init__(self):
        self.samples=[]
        self.last=0.0

    def check(self,force=False):
        """Sample before GPU work and at most one second apart between bounded single-frame evaluations."""
        if not force and time.monotonic()-self.last<1:
            return
        result=subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/nvidia-smi.exe'),
            '--query-gpu=temperature.gpu,memory.used','--format=csv,noheader,nounits'],
            capture_output=True,text=True,check=True,timeout=3)
        lines=result.stdout.strip().splitlines()
        if len(lines)!=1:
            raise ValueError('Expected the single benchmark GPU')
        temperature,memory=map(float,lines[0].split(','))
        if not 0<temperature<78 or not np.isfinite(memory):
            raise ValueError('Unsafe or unavailable GPU telemetry')
        self.samples.append(dict(atUtc=datetime.now(timezone.utc).isoformat(),temperatureC=temperature,totalGpuMemoryMiB=memory))
        self.last=time.monotonic()


def run(dataset,checkpoint,output):
    """Freeze a training-only prototype head, then measure all predeclared held-out originals exactly once."""
    import torch
    import torchvision
    dataset,checkpoint,output=Path(dataset),Path(checkpoint),Path(output)
    if output.exists():
        raise ValueError('Choose a new immutable offline result folder')
    plan=json.loads((dataset/'plan.json').read_bytes())
    sources=json.loads((dataset/'sources.json').read_bytes())
    if digest((dataset/'images.npz').read_bytes())!=plan['imagesSha256'] or digest((dataset/'sources.json').read_bytes())!=plan['sourcesSha256']:
        raise ValueError('Predeclared data changed')
    pictures=np.load(dataset/'images.npz',allow_pickle=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if not torch.cuda.is_available():
        raise ValueError('The measured CUDA environment is required')
    thermal=ThermalGuard()
    thermal.check(True)
    began=time.perf_counter()
    before=checkpoint.stat()
    # mmap avoids materializing the 2.2 GB training checkpoint; clones retain only the required small backbone.
    archive=torch.load(checkpoint,map_location='cpu',weights_only=True,mmap=True)
    state=archive.get('state_dict',archive)
    prefix='image_tokenizer.efficientnet_preprocess.'
    selected={name.removeprefix(prefix):tensor.detach().clone() for name,tensor in state.items() if name.startswith(prefix)}
    after=checkpoint.stat()
    if not selected or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Missing encoder or changed source checkpoint')
    del state,archive
    gc.collect()
    encoder=torchvision.models.efficientnet_b0(dropout=.2,weights=None).features[:6]
    encoder.load_state_dict(selected,strict=True)
    selected_sha=tensor_digest(selected)
    torch.cuda.reset_peak_memory_stats()
    encoder.to(device='cuda',dtype=torch.float16).eval()
    runtime_sha=tensor_digest(encoder.state_dict())
    load_ms=(time.perf_counter()-began)*1000
    thermal.check(True)

    def encode(rgb):
        """Measure the full crop, host transfer, encoder, pooling and synchronized host result."""
        pixels=scene(rgb)
        tensor=torch.from_numpy(pixels.transpose(2,0,1).copy()).unsqueeze(0).to(device='cuda',dtype=torch.float16)/255
        features=encoder(tensor)
        if tuple(features.shape)!=(1,112,12,12):
            raise ValueError('Unexpected frozen P2P encoder geometry')
        values=torch.nn.functional.adaptive_avg_pool2d(features,(3,3)).flatten().float().cpu().numpy()
        return normalize(values)

    with torch.inference_mode():
        for _ in range(5):
            encode(pictures['training'][0])
        vectors=[]
        for rgb in pictures['training']:
            thermal.check()
            vectors.append(encode(rgb))
        prototypes=np.stack(vectors)
        labels=[row['station'] for row in sources['training']]
        if len(prototypes)!=plan['trainingImages']:
            raise ValueError('Training bank is incomplete')
        output.mkdir(parents=True,exist_ok=False)
        # Clone-only weights cannot accidentally serialize unrelated large checkpoint storage.
        torch.save(selected,output/'encoder.pt')
        if (output/'encoder.pt').stat().st_size>32*1024*1024:
            raise ValueError('Unexpected encoder export size')
        model=dict(format='bettergi-p2p-conv-station-experiment-v1',authority='offline shadow only',
            features=plan['features'],classifier=plan['classifier'],classes=list(CLASSES),
            sourceTensorSha256=selected_sha,runtimeHalfTensorSha256=runtime_sha,
            encoderFileSha256=digest((output/'encoder.pt').read_bytes()),trainingLeases=sources['trainingLeases'],
            prototypes=prototypes.tolist(),labels=labels,sourceRows=sources['training'])
        raw=json.dumps(model,separators=(',',':'),allow_nan=False).encode()
        with (output/'candidate.json').open('xb') as stream:
            stream.write(raw)
        frozen=dict(atUtc=datetime.now(timezone.utc).isoformat(),candidateSha256=digest(raw),
            planSha256=digest((dataset/'plan.json').read_bytes()),sourceTensorSha256=selected_sha,
            trainingImages=len(labels),holdoutEvaluated=False,authority='offline shadow only')
        with (output/'freeze.json').open('x',encoding='utf-8') as stream:
            json.dump(frozen,stream,indent=2)
        # Holdout encoding starts only after the candidate and training lineage are immutable.
        rows=[]
        for rgb,source in zip(pictures['holdout'],sources['holdout'],strict=True):
            thermal.check()
            started=time.perf_counter_ns()
            prediction=predict(encode(rgb),prototypes,labels)
            elapsed=(time.perf_counter_ns()-started)/1e6
            rows.append(dict(source,prediction=prediction['station'],cosineSimilarity=prediction['cosineSimilarity'],
                margin=prediction['margin'],endToEndMs=elapsed))
        thermal.check(True)
    old=sum(row['baseline']==row['station'] for row in sources['holdout'])
    correct=sum(row['prediction']==row['station'] for row in rows)
    regressions=[row for row in rows if row['baseline']==row['station']!=row['prediction']]
    gains=[row for row in rows if row['baseline']!=row['station']==row['prediction']]
    latency=[row['endToEndMs'] for row in rows]
    peak=torch.cuda.max_memory_allocated()/1024**2
    eligible=not regressions and correct>old and float(np.percentile(latency,95))<=10 and max(latency)<=25 and peak<=256
    result=dict(scope='offline only; no goal recovered and no photo authority granted',passed=bool(eligible),
        candidateSha256=digest(raw),baselineCorrect=old,candidateCorrect=correct,holdoutImages=len(rows),
        independentHoldoutLeases=len(sources['holdoutLeases']),regressions=regressions,corrected=gains,
        latencyMs=dict(median=float(np.median(latency)),p95=float(np.percentile(latency,95)),maximum=max(latency)),
        torchPeakAllocatedMiB=peak,encoderParameters=sum(p.numel() for p in encoder.parameters()),
        encoderExportBytes=(output/'encoder.pt').stat().st_size,sourceCheckpointBytes=before.st_size,
        sourceAccess='memory mapped; selected encoder tensors cloned only',modelLoadMs=load_ms,
        gpu=torch.cuda.get_device_name(),torchVersion=torch.__version__,torchvisionVersion=torchvision.__version__,
        peakTemperatureC=max(sample['temperatureC'] for sample in thermal.samples),thermalSamples=thermal.samples,
        rows=rows)
    with (output/'results.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({key:result[key] for key in ('passed','baselineCorrect','candidateCorrect','holdoutImages','latencyMs','torchPeakAllocatedMiB','encoderExportBytes','peakTemperatureC')}))
    return result


def main():
    """Evaluate a pinned local image set and installed checkpoint with no network or controller access."""
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','checkpoint','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args.dataset,args.checkpoint,args.output)


if __name__=='__main__':
    main()
