"""Explicitly qualified, shadow-only integration of the frozen P2P scene encoder."""
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from landmark_recognizer import CLASSES

FORMAT='bettergi-p2p-scene-shadow-v1'


def read_bound(root,reference,maximum):
    """Read only a bounded artifact inside this comparison folder and verify its exact bytes."""
    path=(root/reference['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size>maximum:
        raise ValueError('Unbound or oversized scene observer artifact')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('Scene observer artifact changed')
    return path,raw


class GpuLandmarkObserver:
    """Observe station appearance without acquiring input or granting photographic authority."""
    def __init__(self,path,raw):
        """Validate the immutable offline model, measured parity and resource bounds without allocating a GPU model."""
        root=Path(path).resolve().parent
        envelope=json.loads(raw)
        if (set(envelope)!={'format','deployment','model','encoder','executionProof','accuracyProof','plan'}
                or envelope['format']!=FORMAT or envelope['deployment']!='checkpoint-shadow-only'):
            raise ValueError('Scene encoder must be explicitly shadow-only')
        _,model_raw=read_bound(root,envelope['model'],4*1024*1024)
        self.weights,_=read_bound(root,envelope['encoder'],8*1024*1024)
        _,execution_raw=read_bound(root,envelope['executionProof'],1024*1024)
        _,accuracy_raw=read_bound(root,envelope['accuracyProof'],2*1024*1024)
        _,plan_raw=read_bound(root,envelope['plan'],64*1024)
        model,execution,accuracy,plan=map(json.loads,(model_raw,execution_raw,accuracy_raw,plan_raw))
        measures=[execution['maximumFeatureAbsError'],execution['latencyMs']['p95'],
                  execution['latencyMs']['maximum'],execution['torchPeakAllocatedMiB'],execution['peakTemperatureC']]
        if not all(type(value) in (int,float) and math.isfinite(value) and value>=0 for value in measures):
            raise ValueError('Nonfinite or negative observer cost evidence')
        if (model['format']!='bettergi-p2p-conv-station-experiment-v1'
                or model['authority']!='offline shadow only'
                or model['features']!=plan['features'] or model['classifier']!=plan['classifier']
                or model['encoderFileSha256']!=envelope['encoder']['sha256']
                or execution['candidateSha256']!=envelope['model']['sha256']
                or execution['originalResultsSha256']!=envelope['accuracyProof']['sha256']
                or execution['planSha256']!=envelope['plan']['sha256']
                or accuracy['candidateSha256']!=envelope['model']['sha256']
                or execution['passed'] is not True or execution['allOriginalLabelsPreserved'] is not True
                or not 0<=execution['maximumFeatureAbsError']<=1e-5
                or execution['parityFrames']!=plan['trainingImages']+plan['holdoutImages']
                or execution['latencyMs']['p95']>10 or execution['latencyMs']['maximum']>25
                or execution['torchPeakAllocatedMiB']>256 or execution['peakTemperatureC']>=78
                or accuracy['regressions'] or accuracy['candidateCorrect']<=accuracy['baselineCorrect']):
            raise ValueError('Scene encoder lacks the unchanged offline quality, parity or cost qualification')
        # Fail closed if the executed scorer differs from the numerical-parity experiment.
        for name,digest in execution['sourceCodeSha256'].items():
            if name not in ('p2p_station_features.py','p2p_station_graph.py'):
                raise ValueError('Unexpected scene scorer dependency')
            source=Path(__file__).with_name('experiments')/name
            if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
                raise ValueError('Scene scorer changed after numerical qualification')
        if set(execution['sourceCodeSha256'])!={'p2p_station_features.py','p2p_station_graph.py'}:
            raise ValueError('Incomplete scene scorer qualification')
        self.prototypes=np.asarray(model['prototypes'],dtype=np.float32)
        self.labels=list(model['labels'])
        if (model['classes']!=list(CLASSES) or not 3<=len(self.labels)<=512
                or set(self.labels)!=set(CLASSES) or self.prototypes.shape!=(len(self.labels),1008)
                or not np.isfinite(self.prototypes).all()
                or not np.allclose(np.linalg.norm(self.prototypes,axis=1),1,atol=1e-5,rtol=0)):
            raise ValueError('Invalid frozen scene prototypes')
        self.data=dict(envelope,trainingRuns=model['trainingLeases'],feature=model['features'],method=model['classifier'])
        self.checkpoint_id=hashlib.sha256(raw).hexdigest()
        self._source_sha=model['sourceTensorSha256']
        self._runtime_sha=model['runtimeHalfTensorSha256']
        self._encoder=None
        self.runtime_metadata=None

    def prepare(self):
        """Prewarm one small observer before a control lease; preserve the policy's random-number state."""
        if self._encoder is None:
            import torch
            from experiments.p2p_station_graph import FrozenSceneEncoder
            before=torch.cuda.memory_allocated()
            started=time.perf_counter_ns()
            with torch.random.fork_rng(devices=[]):
                self._encoder=FrozenSceneEncoder(self.weights,self._source_sha,self._runtime_sha)
            self._encoder.feature(np.zeros((192,192,3),dtype=np.uint8))
            self.runtime_metadata=dict(checkpointId=self.checkpoint_id,format=FORMAT,authority='shadow-only',
                observerModelLoads=1,execution='cuda-graph-fp16',
                warmupMs=(time.perf_counter_ns()-started)/1e6,
                cudaAllocatedDeltaMiB=(torch.cuda.memory_allocated()-before)/1024**2,
                torchVersion=torch.__version__,gpu=torch.cuda.get_device_name())

    def predict(self,rgb):
        """Return the existing station-observer protocol from pixels alone, with no native pose or target input."""
        from experiments.p2p_station_features import predict
        if isinstance(rgb,(bytes,bytearray,memoryview)):
            if len(rgb)!=192*192*3:
                raise ValueError('Exact RGB192 bytes required')
            rgb=np.frombuffer(rgb,dtype=np.uint8).reshape(192,192,3)
        self.prepare()
        result=predict(self._encoder.feature(rgb),self.prototypes,self.labels)
        return dict(station=result['station'],squaredDistance=max(0.0,2*(1-result['cosineSimilarity'])))
