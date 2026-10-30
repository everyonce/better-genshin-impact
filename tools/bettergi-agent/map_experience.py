"""Preserve the separate native map pulses and their exact PNG sources in automated experience."""
import hashlib
import json
from pathlib import Path


def collect_map_experience(folder, repo, observer):
    """Replay one completed inspection; reject unaccounted menu inputs before admitting a dataset."""
    from audit_map_inspection import audit_map
    folder,repo=Path(folder).resolve(),Path(repo).resolve()
    warm=json.loads((folder/'warm-launcher.json').read_bytes())
    directory=folder/'map-inspection'
    present=directory.exists() or any((folder/name).exists() for name in
        ('map-required-owner.json','map-audit.json','map-owner-source.json','map-recovery-origin.json'))
    if not present and not any(warm.get(key) for key in ('mapInspectionVerified','mapRecoveryVerified')):
        return None
    if warm.get('status')!='completed' or warm.get('mapInspectionVerified') is not True or warm.get('mapRecoveryVerified'):
        raise ValueError('Map experience requires a separately qualified completed inspection')
    source_path=folder/'map-owner-source.json'
    if not source_path.is_file() or source_path.stat().st_size>4096:
        raise ValueError('Map experience needs its original owner-source binding')
    paths={source_path,folder/'warm-launcher.json',folder/'map-required-owner.json',folder/'map-audit.json',directory/'transaction.json'}
    if (folder/'map-required-game.json').is_file():paths.add(folder/'map-required-game.json')
    paths.update(directory.glob('*.png'))
    before={path:hash_file(path) for path in paths}
    source=json.loads(source_path.read_bytes())
    owner_path=Path(source['path']).resolve()
    if not owner_path.is_relative_to(repo/'artifacts/live') or owner_path.name!='map-owner-lineage.json':
        raise ValueError('Map owner source must remain in retained local evidence')
    owner_raw=owner_path.read_bytes()
    if hashlib.sha256(owner_raw).hexdigest()!=source['sha256']:
        raise ValueError('Map owner source changed after collection')
    transaction=json.loads((directory/'transaction.json').read_bytes())
    if transaction.get('mode')!='inspection' or transaction.get('status')!='returnedToJunction':
        raise ValueError('Recovery or unfinished map operations need their own experience qualification')
    proof=audit_map(folder,owner_path,*observer,repo)
    if proof.get('passed') is not True or proof!=json.loads((folder/'map-audit.json').read_bytes()):
        raise ValueError('Independent map replay differs from the original qualified operation')
    if owner_path.read_bytes()!=owner_raw:
        raise ValueError('Map owner source changed during qualification')
    actions=map_pulse_rows(transaction,directory,repo)
    if before!={path:hash_file(path) for path in paths}:
        raise ValueError('Original map evidence changed during qualification')
    return dict(passed=True,audit=proof,ownerSource=source,actions=actions,
        sourceFiles=[str(path.relative_to(folder)) for path in sorted(paths)],
        sourceSha256={str(path.relative_to(folder)):before[path] for path in sorted(paths)},
        inputEvidence='audited native map pulse journal and execution context',physicalExecutionProven=False,
        imageDomain='original native 1920x1080 PNG; separate preprocessing required for policy training')


def hash_file(path):
    """Read only a named original file, without retaining its complete PNG in memory."""
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def map_pulse_rows(transaction, directory, repo):
    """Join each real pulse to its trigger PNG without inventing ordinary stream request IDs."""
    native=transaction['inspection']
    if len(native['inputs'])!=2 or native['requestId']!=transaction['requestId']:
        raise ValueError('Map pulse operation identity or count changed')
    result=[]
    for ordinal,(pulse,phase,action,key) in enumerate(zip(native['inputs'],('before','map'),
            ('openMap','closeMap'),('M','ESCAPE')),1):
        source=native[phase][-1]
        if (pulse['frameId']!=source['frameId'] or pulse['action']!=action or pulse['key']!=key
                or pulse['outcome']!='released' or pulse['releasedTicks']<pulse['requestedTicks']):
            raise ValueError('Map pulse differs from its qualified source or terminal outcome')
        image=directory/f"native-{source['frameId']}.png"
        if hashlib.sha256(image.read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('Map pulse source PNG changed')
        result.append(dict(nativeOperationId=native['requestId'],pulseOrdinal=ordinal,runId=transaction['runId'],
            actor='native-ui-controller',controllerId='map-inspection-v1',humanExpertDemonstration=False,
            inputEvidence='native-software-dispatch',physicalExecutionProven=False,terminalStatus=pulse['outcome'],
            action=dict(pulse),sourceFrame=dict(source),nativeClock={key:native[key] for key in ('originTicks','frequency')},
            lease={key:native[key] for key in ('sessionId','ownerEpoch')},
            sourceImage=dict(path=str(image.relative_to(repo)),sha256=source['sha256'],width=source['width'],height=source['height']),
            observationProfile='native-map-png-1920x1080-v1',sourceTransaction=str((directory/'transaction.json').relative_to(repo))))
    return result
