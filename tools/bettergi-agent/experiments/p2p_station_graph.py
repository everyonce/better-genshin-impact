"""Test CUDA graph execution of an unchanged frozen scene encoder, with paired numerical and label parity."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.p2p_station_features import ThermalGuard,digest,normalize,predict,scene,tensor_digest
import numpy as np


class FrozenSceneEncoder:
    """A small, stateless P2P convolutional component with its own static image buffer and verified tensor identity."""
    def __init__(self,weights,source_tensor_sha,runtime_tensor_sha,*,cuda_graph=True):
        """Strictly load the exported convolutional weights and prewarm before any timed use."""
        import torch
        import torchvision
        self.torch=torch
        self.module=torchvision.models.efficientnet_b0(dropout=.2,weights=None).features[:6]
        state=torch.load(weights,map_location='cpu',weights_only=True)
        if tensor_digest(state)!=source_tensor_sha:
            raise ValueError('Frozen scene encoder weights changed')
        self.module.load_state_dict(state,strict=True)
        self.module.to(device='cuda',dtype=torch.float16).eval()
        if tensor_digest(self.module.state_dict())!=runtime_tensor_sha:
            raise ValueError('Runtime scene encoder differs from the frozen FP16 tensors')
        self.graph=None
        self.static=torch.zeros((1,3,192,192),device='cuda',dtype=torch.uint8)
        self.output=None
        if cuda_graph:
            stream=torch.cuda.Stream()
            stream.wait_stream(torch.cuda.current_stream())
            with torch.inference_mode(),torch.cuda.stream(stream):
                for _ in range(3):
                    self._forward(self.static)
            torch.cuda.current_stream().wait_stream(stream)
            torch.cuda.synchronize()
            self.graph=torch.cuda.CUDAGraph()
            with torch.inference_mode(),torch.cuda.graph(self.graph,stream=stream):
                self.output=self._forward(self.static)
            torch.cuda.current_stream().wait_stream(stream)

    def _forward(self,tensor):
        """Record exactly the existing normalization, convolution and 3-by-3 pooling operations."""
        features=self.module(tensor.to(dtype=self.torch.float16)/255)
        if tuple(features.shape)!=(1,112,12,12):
            raise ValueError('Unexpected frozen scene encoder shape')
        return self.torch.nn.functional.adaptive_avg_pool2d(features,(3,3)).flatten().float()

    def feature(self,rgb,*,eager=False):
        """Encode one HUD-free scene, returning a synchronized, normalized CPU feature vector."""
        pixels=scene(rgb)
        source=self.torch.from_numpy(pixels.transpose(2,0,1).copy()).unsqueeze(0)
        with self.torch.inference_mode():
            self.static.copy_(source)
            if self.graph is not None and not eager:
                self.graph.replay()
                output=self.output
            else:
                output=self._forward(self.static)
            return normalize(output.cpu().numpy())


def run(dataset,frozen,output):
    """Preserve the first accuracy trial and test only execution parity, latency and resource cost."""
    import torch
    dataset,frozen,output=Path(dataset),Path(frozen),Path(output)
    if output.exists():
        raise ValueError('Choose a new graph comparison output')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    sources=json.loads((dataset/'sources.json').read_bytes())
    plan=json.loads((dataset/'plan.json').read_bytes())
    model=json.loads((frozen/'candidate.json').read_bytes())
    old=json.loads((frozen/'results.json').read_bytes())
    if digest((frozen/'candidate.json').read_bytes())!=old['candidateSha256'] or digest((frozen/'encoder.pt').read_bytes())!=model['encoderFileSha256']:
        raise ValueError('Original frozen model or prior results changed')
    if digest((dataset/'sources.json').read_bytes())!=plan['sourcesSha256'] or digest((dataset/'images.npz').read_bytes())!=plan['imagesSha256']:
        raise ValueError('Original comparison data changed')
    pictures=np.load(dataset/'images.npz',allow_pickle=False)
    guard=ThermalGuard()
    guard.check(True)
    torch.cuda.reset_peak_memory_stats()
    encoder=FrozenSceneEncoder(frozen/'encoder.pt',model['sourceTensorSha256'],model['runtimeHalfTensorSha256'])
    prototypes=np.asarray(model['prototypes'],dtype=np.float32)
    labels=model['labels']
    for _ in range(5):
        encoder.feature(pictures['training'][0])
    rows=[]
    maximum_error=0
    for split in ('training','holdout'):
        for index,(rgb,source) in enumerate(zip(pictures[split],sources[split],strict=True)):
            guard.check()
            reference=encoder.feature(rgb,eager=True)
            started=time.perf_counter_ns()
            captured=encoder.feature(rgb)
            prediction=predict(captured,prototypes,labels)
            elapsed=(time.perf_counter_ns()-started)/1e6
            error=float(np.max(np.abs(reference-captured)))
            maximum_error=max(maximum_error,error)
            if error>1e-5 or prediction['station']!=predict(reference,prototypes,labels)['station']:
                raise ValueError('CUDA graph changed the frozen embedding or station prediction')
            if split=='training' and float(np.max(np.abs(reference-prototypes[index])))>1e-5:
                raise ValueError('Original training vectors did not reproduce')
            if split=='holdout':
                previous=old['rows'][index]
                if any(previous[key]!=source[key] for key in ('runId','frameId','rgbSha256','station')) or prediction['station']!=previous['prediction']:
                    raise ValueError('The original held-out prediction changed')
            rows.append(dict(runId=source['runId'],frameId=source['frameId'],split=split,station=source['station'],
                prediction=prediction['station'],featureMaxAbsError=error,endToEndMs=elapsed))
    guard.check(True)
    latencies=[row['endToEndMs'] for row in rows if row['split']=='holdout']
    peak=torch.cuda.max_memory_allocated()/1024**2
    accuracy=not old['regressions'] and old['candidateCorrect']>old['baselineCorrect']
    result=dict(scope='execution-only comparison of the same frozen model; not another independent accuracy trial',
        authority='offline shadow only',passed=bool(accuracy and np.percentile(latencies,95)<=10 and max(latencies)<=25 and peak<=256),
        candidateSha256=old['candidateSha256'],originalResultsSha256=digest((frozen/'results.json').read_bytes()),
        planSha256=digest((dataset/'plan.json').read_bytes()),sourceCodeSha256={name:digest(Path(__file__).with_name(name).read_bytes())
            for name in ('p2p_station_features.py','p2p_station_graph.py')},
        parityFrames=len(rows),maximumFeatureAbsError=maximum_error,allOriginalLabelsPreserved=True,
        baselineCorrect=old['baselineCorrect'],candidateCorrect=old['candidateCorrect'],holdoutImages=old['holdoutImages'],
        latencyMs=dict(median=float(np.median(latencies)),p95=float(np.percentile(latencies,95)),maximum=max(latencies)),
        torchPeakAllocatedMiB=peak,peakTemperatureC=max(row['temperatureC'] for row in guard.samples),thermalSamples=guard.samples,rows=rows)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({key:result[key] for key in ('passed','parityFrames','maximumFeatureAbsError','latencyMs','torchPeakAllocatedMiB','peakTemperatureC')}))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','frozen','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    arguments=parser.parse_args()
    run(arguments.dataset,arguments.frozen,arguments.output)
