"""Independently replay every original in a frozen missed-template successor's training manifest."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from audit_hybrid_run import require
from audit_landmark_panel import read, sha, write
import landmark_recognizer
from landmark_recognizer import LandmarkRecognizer, signature


def verify(parent_file, candidate_file, freeze_file, training_episode):
    """Require exact inherited template order and one deterministic template for each admitted parent miss."""
    freeze=read(freeze_file)
    root=freeze_file.parent
    manifest=read(root/'source-manifest.json')
    parent,candidate=(LandmarkRecognizer.load(p) for p in (parent_file,candidate_file))
    require(freeze['format']=='bettergi-g8-training-freeze-v1' and freeze['authority']=='shadow only' and
            freeze['classificationScorer']=='unchanged G5 v1' and parent.checkpoint_id==freeze['parentCheckpointSha256'] and
            candidate.checkpoint_id==freeze['checkpointSha256'] and sha(root/'predeclaration.json')==freeze['predeclarationSha256']
            and sha(root/'source-manifest.json')==freeze['trainingManifestSha256'],'Reference freeze inputs differ')
    for file,digest in freeze['implementationSha256'].items():
        require(Path(file).name==file and sha(Path(landmark_recognizer.__file__).with_name(file))==digest,
                'Frozen training or scoring implementation differs')
    meta=manifest['run']
    pat=Path(meta['path'])
    run=read(pat)
    earlier=read(training_episode)
    archive=read(pat.parent/'station-rgb-audit.json')
    require(meta==freeze['trainingSource'] and run['runId']==meta['runId']==earlier['runId']==archive['runId']
            and sha(pat)==earlier['runSha256'] and sha(pat.parent/'station-rgb-audit.json')==earlier['originalSourceAuditSha256']
            and [earlier['nativeLease'][k] for k in ('sessionId','ownerEpoch')]==meta['lease'] and
            earlier['sourceInterval100ns']==meta['sourceInterval100ns'] and
            archive['sourceCount']==len(manifest['sources'])==freeze['admittedSources']==earlier['uniqueNativeArrivals'],
            'Verified native training episode does not match the manifest')
    n=len(parent.data['prototypes'])
    require(candidate.data['prototypes'][:n]==parent.data['prototypes'] and n==freeze['inheritedPrototypes'] and
            candidate.data['trainingRuns']==[*parent.data['trainingRuns'],meta],'Reference order or training lease lineage changed')
    # Match every original (including those left unmodified) to its native truth, source clock and scorer prediction.
    original={}
    for segment in run['segments']:
        folder=pat.parent/'patrol-recording'/f"{segment['number']:05d}"
        with (folder/'events.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line)
                if row.get('type')=='landmarkShadowSource':
                    key=segment['number'],row['frameId']
                    require(key not in original,'Duplicate training original')
                    original[key]=row
    admitted=[]
    preserved=0
    require(len(original)==archive['sourceCount'],'Training episodes lost or gained originals')
    for src,ref,prior in zip(manifest['sources'],archive['sources'],earlier['rows'],strict=True):
        key=src['segment'],src['frameId']
        row=original[key]
        common=('sourceTimestamp100ns','captureEpoch','sessionId','ownerEpoch','runId','childProcessId','windowsSessionId',
                'eventType','readinessEpoch','frameId','station','rgbSha256')
        require(all(row[k]==src[k]==ref[k] for k in common) and prior['exactSha256']==src['rgbSha256']
                and key==(prior['segment'],prior['frameId']) and src['station']==prior['station'],
                'Training marker, scope or source does not agree with sealed native original')
        raw=base64.b64decode(row['rgb24Base64'],validate=True)
        require(len(raw)==192*192*3 and hashlib.sha256(raw).hexdigest()==src['rgbSha256'],'Original training RGB bytes differ')
        a,b=parent.predict(raw),candidate.predict(raw)
        miss=a['station']!=src['station']
        require(a==src['g5Prediction'] and b==src['candidateTrainingPrediction'] and src['appendPrototype'] is miss
                and b['station']==src['station'],'Frozen source selection or preserved prediction differs')
        if miss:
            p=candidate.data['prototypes'][n+len(admitted)]
            require(p['signature']==signature(raw).tolist() and p['station']==src['station'] and p['runId']==meta['runId']
                    and all(p['evidence'].get(k)==v for k,v in src.items() if k not in
                            ('appendPrototype','g5Prediction','candidateTrainingPrediction')),
                    'Appended template differs from its single declared source')
            admitted.append(dict(segment=key[0],frameId=key[1],station=src['station'],rgbSha256=src['rgbSha256']))
        else:
            preserved+=1
    require(n+len(admitted)==len(candidate.data['prototypes'])==freeze['totalPrototypes'] and
            len(admitted)==freeze['addedPrototypes'] and preserved==freeze['correctG5TrainingLabelsPreserved'],
            'Reference counts differ from the immutable freeze')
    return dict(parentCheckpointSha256=parent.checkpoint_id,checkpointSha256=candidate.checkpoint_id,
                trainingManifestSha256=freeze['trainingManifestSha256'],trainingEpisodeSha256=sha(training_episode),
                trainingRunId=meta['runId'],verifiedOriginals=len(original),inheritedExactOrder=n,
                priorCorrectPreserved=preserved,added=admitted,freezeQpc=freeze['freezeQpc'],mode='training verification only')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('parent','candidate','freeze','training-episode','out'):
        p.add_argument('--'+flag,type=Path,required=True)
    args=p.parse_args()
    write(args.out,verify(args.parent,args.candidate,args.freeze,args.training_episode))
