"""Train one fixed G5 extension on the sealed G6 lossless patrol; no holdout access or live interfaces."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path

from freeze_landmark_candidate import encoded, sha
from hybrid_routes import STREET_PATROL_ROUTE
from landmark_recognizer import FORMAT, LandmarkRecognizer, signature
from landmark_shadow_sources import verify_archive
from run_rdp_patrol import native_qpc_sample
from train_steering import distinct


ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT/'artifacts/agent/landmarks'
OUT = MODELS/'g8-g5-missed-originals'
TRAINING = ROOT/'artifacts/live/2026-10-29-stairs/prospective/series-20261029T170518Z-ee7af6123c15/batch-01'
EPISODE = ROOT/'artifacts/live/2026-10-29-stairs/g6-paired-prospective/episode-audit.json'
G5 = MODELS/'g5-freeze/gen-05.json'
G6 = MODELS/'g6-centered-frozen/gen-06.json'
RULE = dict(format='bettergi-g8-training-rule-v1',scope='training only',expectedOriginals=41,
            sourceCheckpointSha256='02d386d0f085dc3facbf0613cf6a0d4a187a07044a6c1a462f9f580720d7a732',
            originalShadowSha256='4c347fc40796ccd33248982e5979273d10e6dd2afed45e8f2d5be7b8f1f7e446',
            trainingEpisodeSha256='45794bdcdef0cb5281fd6902cb5e92f71f8c4e045f051a19e9dd0204ed6c5de9',
            sourceArchiveSha256='f2628a1b80807ebc26d6d297ab98303168c1d71f38290ff5437b2c7bd39953eb',
            trainingFolder=str(TRAINING.relative_to(ROOT)),sourceCheckpoint=str(G5.relative_to(ROOT)),
            scorer='unchanged G5 v1',selection='Replay all 41 original sources once in physical order. Append exactly one v1 signature per distinct native arrival G5 misclassified. Use its independently audited native label.',
            invariants='Keep every ordered G5 template and training run. Accept only if all prior correct training labels survive and all appended original views classify correctly. No tuning or negative mining.',
            zeroMiss='Retain original G5 bytes',evaluation='Separate independent qualification required; whole training lease excluded.')


def check(condition,message):
    """Refuse writes for partial, inconsistent or substituted training inputs."""
    if not condition:
        raise ValueError(message)


def stamp():
    """Capture the Windows monotonic clock for comparisons with independent future leases."""
    qpc = native_qpc_sample()
    check(qpc is not None and qpc[0]>0 and qpc[1]>0,'Windows QPC required')
    return dict(utc=datetime.now(timezone.utc).isoformat(),qpc=dict(clock='windows-query-performance-counter',frequencyHz=qpc[0],ticks=qpc[1]))


def write_once(name,raw):
    """Leave every published document exclusive and immutable across clean invocations."""
    with (OUT/name).open('xb') as stream:
        stream.write(raw)


def read_pinned(path,digest):
    """Read once and bind the exact bytes to their prespecified digest."""
    raw = path.read_bytes()
    check(sha(raw)==digest,'Changed training input: '+path.name)
    return raw


def predeclare():
    """Publish the source selection rule before any model evaluation on the designated training block."""
    OUT.mkdir(exist_ok=False)
    write_once('predeclaration.json',encoded(dict(rule=RULE,declared=stamp())))


def training_sources():
    """Join all 41 exact original byte strings to sealed visit labels, whole-lease scope and clock."""
    pair = json.loads(read_pinned(EPISODE,RULE['trainingEpisodeSha256']))
    checkpoint = read_pinned(G6,RULE['originalShadowSha256'])
    check(sha(checkpoint) in pair['checkpointIds'],'Wrong original shadow')
    run_path = TRAINING/'patrol.json'
    run = json.loads(read_pinned(run_path,pair['runSha256']))
    recording = TRAINING/'patrol-recording'
    archive = json.loads(read_pinned(TRAINING/'station-rgb-audit.json',RULE['sourceArchiveSha256']))
    route = json.loads((TRAINING/'audit.json').read_bytes())
    check(pair['originalSourceAuditSha256']==RULE['sourceArchiveSha256'] and verify_archive(run_path,recording,G6,route,ROOT)==archive
          and archive['runId']==pair['runId']==run['runId'] and archive['routeId']==STREET_PATROL_ROUTE
          and pair['circuits']==10 and archive['sourceCount']==pair['uniqueNativeArrivals']==pair['originalReplayMatchesLive']==41,
          'Original training lease and independent verifier disagree')
    pixels = {}
    for entry in run['segments']:
        segment = entry['number']
        with (recording/f'{segment:05d}'/'events.jsonl').open(encoding='utf-8') as events:
            for event in map(json.loads,events):
                if event.get('type')=='landmarkShadowSource':
                    key = (segment,event['frameId'])
                    check(key not in pixels,'Repeated original arrival')
                    pixels[key] = base64.b64decode(event['rgb24Base64'],validate=True)
    sources = []
    lease = pair['nativeLease']
    check(len(pair['rows'])==len(archive['sources'])==len(pixels)==41,'Incomplete training set')
    for source,reference in zip(archive['sources'],pair['rows']):
        key = (source['segment'],source['frameId'])
        raw = pixels.pop(key)
        check((source['sessionId'],source['ownerEpoch'])==(lease['sessionId'],lease['ownerEpoch'])
              and (source['runId'],*key,source['station'],sha(raw))==(reference['runId'],reference['segment'],reference['frameId'],
                    reference['station'],source['rgbSha256']) and source['rgbSha256']==reference['exactSha256'],
              'Source bytes or independently audited station differ')
        evidence = {k:source[k] for k in ('frameId','segment','runId','eventType','station','sessionId','ownerEpoch',
                    'windowsSessionId','childProcessId','captureEpoch','sourceTimestamp100ns','readinessEpoch','rgbSha256')}
        sources.append((raw,evidence))
    epochs = {e['captureEpoch'] for _,e in sources}
    check(len(epochs)==1,'Multiple capture generations')
    meta = dict(path=str(run_path),runId=run['runId'],lease=[lease['sessionId'],lease['ownerEpoch']],
                captureEpoch=epochs.pop(),sourceInterval100ns=pair['sourceInterval100ns'],uniqueImages=len(sources),
                evidenceSha256=RULE['sourceArchiveSha256'],scope='Whole sealed G6 patrol admitted as training')
    return meta,sources


def extend(head,meta,sources):
    """Choose additions using the immutable base head only; check candidate training integrity separately."""
    original = head.data
    check(original['format']==FORMAT and not head.centered,'Original G5 v1 metric required')
    added,rows = [],[]
    for raw,source in sources:
        prediction = head.predict(raw)
        missed = prediction['station']!=source['station']
        rows.append(dict(source,g5Prediction=prediction,appendPrototype=missed))
        if missed:
            added.append(dict(runId=meta['runId'],station=source['station'],evidence=source,signature=signature(raw).tolist()))
    if not added:
        return None,rows
    candidate = dict(original,prototypes=[*original['prototypes'],*added],trainingRuns=[*original['trainingRuns'],meta])
    distinct(candidate['trainingRuns'])
    new = LandmarkRecognizer(candidate)
    for (raw,source),row in zip(sources,rows):
        prediction = new.predict(raw)
        check(prediction['station']==source['station'],'Training integrity failed; no alternate candidate is permitted')
        row['candidateTrainingPrediction'] = prediction
    return candidate,rows


def train():
    """Freeze at most one candidate, binding every inspected training example and the original G5 bank."""
    declaration = (OUT/'predeclaration.json').read_bytes()
    declared = json.loads(declaration)
    check(declared['rule']==RULE and not (OUT/'freeze.json').exists(),'Missing, changed or already consumed rule')
    base = read_pinned(G5,RULE['sourceCheckpointSha256'])
    head = LandmarkRecognizer(json.loads(base))
    meta,sources = training_sources()
    candidate,rows = extend(head,meta,sources)
    raw = encoded(candidate) if candidate is not None else base
    manifest = encoded(dict(scope='training only',run=meta,sourcePolicy=RULE['selection'],sources=rows))
    frozen = stamp()
    check(declared['declared']['qpc']['frequencyHz']==frozen['qpc']['frequencyHz'] and
          declared['declared']['qpc']['ticks']<frozen['qpc']['ticks'],'Freeze predates declaration')
    new_count = sum(r['appendPrototype'] for r in rows)
    report = dict(format='bettergi-g8-training-freeze-v1',scope='training only',authority='shadow only',
                  outcome='candidateFrozen' if candidate is not None else 'retainG5',predeclarationSha256=sha(declaration),
                  frozenAtUtc=frozen['utc'],freezeQpc=frozen['qpc'],trainingSource=meta,trainingManifestSha256=sha(manifest),
                  parentCheckpointSha256=sha(base),checkpointSha256=sha(raw),inheritedPrototypes=len(head.labels),
                  totalPrototypes=len(head.labels)+new_count,admittedSources=len(rows),addedPrototypes=new_count,
                  classificationScorer='unchanged G5 v1',correctG5TrainingLabelsPreserved=len(rows)-new_count,
                  implementationSha256={name:sha(Path(__file__).with_name(name).read_bytes()) for name in
                      ('freeze_missed_landmark_prototypes.py','landmark_recognizer.py','landmark_shadow_sources.py')})
    write_once('source-manifest.json',manifest)
    if candidate is not None:
        write_once('gen-08.json',raw)
    write_once('freeze.json',encoded(report))
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['predeclare','train'])
    if parser.parse_args().operation=='predeclare':
        predeclare()
    else:
        print(json.dumps(train()))
