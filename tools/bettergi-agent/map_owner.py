"""Verify the sealed SIREN owner through the explicitly bounded R57 → R58 → R59 → R60 chain."""
import argparse
import hashlib
import json
from pathlib import Path
import re


ARTIFACTS = Path(__file__).resolve().parents[2] / 'artifacts'
ROOT_DLL = '0bd78a568fe314a8d97312f0d5c7a2375e93e4325e288ac50d4953946b26ec62'
OLD_DLL = '0c849ea73fc52ec236bb741044bc45919b9578856607379d8e588681bad2b1ff'
CLEAN_CAPTURE = {'captureMode':'WindowsGraphicsCaptureV2','wgcV2ReadbackMode':'blocking',
                 'wgcV2SourceRetention':'hold-until-readback-v1','wgcV2UseCpuConvert':True}


def require(value, message):
    """Reject incomplete evidence before returning a pair usable for live admission."""
    if not value:
        raise ValueError(message)


def evidence(path, name):
    """Only open a bounded public run report under the local evidence tree."""
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to((ARTIFACTS / 'live').resolve()) and path.name == name,
            'Unexpected run evidence path')
    require(0 < path.stat().st_size <= 4 * 1024 * 1024, 'Invalid evidence size')
    raw = path.read_bytes()
    return json.loads(raw.decode('utf-8-sig')), hashlib.sha256(raw).hexdigest()


def identity(status):
    """Return only the session, process and instance nonce used by SeriesGuard."""
    pair = {key: status[key] for key in ('windowsSessionId','processId','instanceNonce')}
    require(all(type(pair[k]) is int and pair[k] > 0 for k in ('windowsSessionId','processId'))
            and isinstance(pair['instanceNonce'], str) and re.fullmatch('[a-f0-9]{32}', pair['instanceNonce']),
            'Invalid Windows process identity')
    return pair


def prior_owner(path):
    """Join the sealed warm launcher to the independently audited broker job and both original nonces."""
    warm, warm_sha = evidence(path, 'warm-launcher.json')
    audit, audit_sha = evidence(Path(path).parent / 'handoff-audit.json', 'handoff-audit.json')
    success = (warm.get('status'), audit.get('status'), audit.get('passed'), audit.get('stopVerified'))
    require(type(audit.get('passed')) is bool and type(audit.get('stopVerified')) is bool
            and warm.get('computer') == 'SIREN' and warm.get('auditStatus') == audit.get('status')
            and success in (('completed','runtime-target-achieved',True,False),
                            ('stopVerified','operator-stopped-prefix',False,True)), 'Unsealed prior gameplay result')
    pair = {r: identity(warm['identity'][r]) for r in ('root','child')}
    root, child, job = pair['root'], pair['child'], audit['rdpJob']
    require(root['processId'] == audit['rootPid'] and child['processId'] == audit['childPid']
            and root['windowsSessionId'] != child['windowsSessionId'] and root['processId'] != child['processId']
            and root['instanceNonce'] == job['rootNonce'] and child['instanceNonce'] == job['childNonce']
            and child['windowsSessionId'] == job['windowsSessionId'] == audit['windowsSessionId'],
            'Prior owner does not match the audited RDP job')
    return pair, {'priorSha256':warm_sha,'priorAuditSha256':audit_sha}


def target_package(number=58):
    """Independently check both selected binaries against the numbered managed build manifest."""
    require(number in (58,59,60), 'Unsupported map release')
    original = ARTIFACTS.resolve() / f'release-r{number}'
    # Historical identity needs only the two binaries and manifest, not a retired runtime's assets.
    # A damaged or partially present live release never falls back to its witness.
    release = original if original.exists() else ARTIFACTS.resolve()/'release-retention/package-witnesses'/original.name
    target = release / 'BetterGI-English-win-x64'
    manifest = release / 'build-manifest.json'
    require(manifest.resolve(strict=True) == manifest and manifest.stat().st_size <= 65536, 'Invalid build manifest')
    raw = manifest.read_bytes()
    build = json.loads(raw.decode('utf-8-sig'))
    require(build['version'] == 1 and build['selfContained'] is True and build['publishConfiguration'] == 'Release'
            and build['validationConfiguration'] == 'Debug' and build['runtimeIdentifier'] == 'win-x64'
            and Path(build['targetDirectory']).resolve() == original/'BetterGI-English-win-x64', f'Unexpected R{number} build identity')
    for name in ('exe','dll'):
        file = target / ('BetterGI.' + name)
        require(file.resolve(strict=True) == file and file.stat().st_size > 0, 'Unsafe package binary')
        with file.open('rb') as stream:
            require(hashlib.file_digest(stream,'sha256').hexdigest() == build[name+'Sha256'], f'Changed R{number} binary')
    return build, hashlib.sha256(raw).hexdigest()


def preserve_package_witness(number):
    """Retain exact historical identity bytes before automatic cleanup removes an obsolete runtime."""
    build,digest=target_package(number)
    original=ARTIFACTS.resolve()/f'release-r{number}'
    witness=ARTIFACTS.resolve()/'release-retention/package-witnesses'/original.name
    source=original if original.exists() else witness
    for relative in ('build-manifest.json','BetterGI-English-win-x64/BetterGI.exe','BetterGI-English-win-x64/BetterGI.dll'):
        before=source/relative
        after=witness/relative
        require(before.resolve(strict=True)==before,'Unexpected identity witness source link')
        raw=before.read_bytes()
        after.parent.mkdir(parents=True,exist_ok=True)
        if after.exists():require(after.resolve(strict=True)==after and after.read_bytes()==raw,'Changed historical identity witness')
        else:
            with after.open('xb') as stream:stream.write(raw)
        expected=digest if relative=='build-manifest.json' else build['exeSha256' if relative.endswith('.exe') else 'dllSha256']
        require(hashlib.sha256(after.read_bytes()).hexdigest()==expected,'Identity witness bytes differ')
    return dict(release=number,witnessDirectory=str(witness),manifestSha256=digest)


def successor_release(receipt):
    """Inspect the finite predecessor shape before recursion; no fourth handoff or self-reference is admitted."""
    if Path(receipt['prior']).name=='warm-launcher.json':return 59
    parent,_=evidence(Path(receipt['prior']),'map-owner-lineage.json')
    require(Path(parent['prior']).name=='warm-launcher.json','Only the bounded R58/R59 predecessors are supported')
    return 60


def checked_pair(root, child, package, child_sha):
    """Require an idle authenticated game child and the same connected minimized R56 host."""
    require(root['instanceType'] == 'Primary' and root['automationEnabled'] is True and root['remoteDesktop'] is False
            and root['uiStatus'] == 'current' and root['childWindowMinimized'] is True and root['childConnectedState'] == 1
            and root['childSessionId'] == child['windowsSessionId'] and root['assemblySha256'].lower() == ROOT_DLL
            and Path(root['appDirectory']).resolve() == ARTIFACTS.resolve() / 'release-r56' / 'BetterGI-English-win-x64',
            'Original minimized R56 primary was not verified')
    require(child['instanceType'] == 'ChildSession' and child['automationEnabled'] is True and child['remoteDesktop'] is True
            and child['uiStatus'] == 'current' and child['automationState'] == 'game_ready' and child['runtimeRunning'] is True
            and child['pilotState'] in ('idle','completed','failed','cancelled') and child['taskRunning'] is False
            and child['agentStreamRunning'] is False and child['rootProcessId'] == root['processId']
            and child['assemblySha256'].lower() == child_sha and Path(child['appDirectory']).resolve() == package,
            'Game child ownership, idle state or package changed')
    return {'root':identity(root), 'child':identity(child)}


def preflight(prior, before):
    """Validate a captured pre-replacement discovery against the previous completed run and explicit target."""
    if Path(prior).name == 'warm-launcher.json':
        old, pins = prior_owner(prior)
        number, source_sha = 58, OLD_DLL
    else:
        # Inspect the bounded original rail before recursion; additional or circular chains remain rejected.
        receipt, prior_sha = evidence(prior,'map-owner-lineage.json')
        number=successor_release(receipt)
        old = load_map_owner(prior)
        previous, build_sha = target_package(number-1)
        require(build_sha == receipt['buildSha256'], 'Original predecessor build manifest changed')
        pins = {'priorLineageSha256':prior_sha,'priorBuildSha256':build_sha}
        source_sha = previous['dllSha256']
    discovery, pins['beforeSha256'] = evidence(before, 'before.json')
    require(discovery.get('unavailable') == [] and len(discovery['instances']) == 2, 'Ambiguous RDP discovery')
    roles = {s['instanceType']:s for s in discovery['instances']}
    package = ARTIFACTS.resolve() / f'release-r{number-1}' / 'BetterGI-English-win-x64'
    require(checked_pair(roles['Primary'],roles['ChildSession'],package,source_sha) == old, 'Original child occupant changed')
    require(roles['ChildSession'].get('idleRestartVersion') == 2, 'Idle replacement capability unavailable')
    build, pins['buildSha256'] = target_package(number)
    if number in (59,60):
        game, pins['gameBeforeSha256'] = evidence(Path(before).with_name('game-before.json'),'game-before.json')
        require(set(game) == {'processId','windowsSessionId','startedFileTime','executable'}
                and type(game['processId']) is int and game['processId'] > 0
                and game['processId'] not in (old['root']['processId'],old['child']['processId'])
                and type(game['startedFileTime']) is int and game['startedFileTime'] > 0
                and game['windowsSessionId'] == old['child']['windowsSessionId']
                and isinstance(game['executable'],str) and game['executable'].casefold() in ('genshinimpact.exe','yuanshen.exe'),
                'Missing protected game identity in the original RDP session')
        pins['protectedGame'] = game
    return old, build, pins


def check_clean_target(build):
    """Before replacement, refuse auto-staging unless the isolated target already has exactly the public capture settings."""
    path = Path(build['targetDirectory']) / 'User/config.json'
    require(path.resolve(strict=True) == path and 0 < path.stat().st_size <= 1024, 'Missing clean target settings')
    raw = path.read_bytes()
    require(json.loads(raw.decode('utf-8-sig')) == CLEAN_CAPTURE, 'Unexpected target capture settings')
    return hashlib.sha256(raw).hexdigest()


def replacement(prior, folder):
    """Verify actual ensure-child output and both ends of the acknowledged restart before issuing lineage."""
    old, build, pins = preflight(prior, folder / 'before.json')
    pre, pins['preflightSha256'] = evidence(folder / 'preflight.json','preflight.json')
    require(pre.get('source') == old and all(pre.get(k) == build[k] for k in ('targetDirectory','exeSha256','dllSha256'))
            and isinstance(pre.get('targetConfigSha256'),str) and re.fullmatch('[0-9a-f]{64}',pre['targetConfigSha256']),
            'Preflight does not identify the selected source, target and configuration')
    raw, pins['replacementSha256'] = evidence(folder / 'ensure-child.json', 'ensure-child.json')
    require(all(raw.get(k) is True for k in ('success','rootReady','childReady','gameReady','childReplaced'))
            and raw.get('readinessScope') == 'game_runtime' and raw.get('childStartDispatched') is False,
            'An idle in-place child replacement was not proven')
    target = Path(build['targetDirectory']).resolve()
    selected = raw['selectedPackage']
    require(Path(selected['targetDirectory']).resolve() == target and all(selected[k] == build[k] for k in ('exeSha256','dllSha256')),
            'Selected target disagrees with the build')
    pair = checked_pair(raw['root'],raw['child'],target,build['dllSha256'])
    if 'protectedGame' in pins:
        game = pins['protectedGame']
        require(pre.get('protectedGame') == raw.get('protectedGame') == game and game['processId'] != pair['child']['processId'],
                'The original game lifetime was not retained through the child replacement')
    a,b,r = old['child'],pair['child'],raw['replacementEvidence']
    require(pair['root'] == old['root'] and a['windowsSessionId'] == b['windowsSessionId']
            and a['processId'] != b['processId'] and a['instanceNonce'] != b['instanceNonce']
            and raw['previousProcessId'] == r['previousProcessId'] == a['processId'] and r['previousNonce'] == a['instanceNonce']
            and (r['replacementProcessId'],r['replacementNonce']) == (b['processId'],b['instanceNonce'])
            and r['phase'] == 'replacement_ready' and r['restartRequestAttempted'] is True and r['restartAcknowledged'] is True
            and r.get('existingTargetConfigSha256') == pre['targetConfigSha256']
            and type(r['readinessPolls']) is int and r['readinessPolls'] > 0 and Path(r['targetDirectory']).resolve() == target,
            'Replacement does not link old and new authenticated owners')
    return {'version':1,'kind':'idle-map-child-replacement','identity':pair,'prior':str(Path(prior).resolve()),**pins}


def load_map_owner(path):
    """Load a historical warm owner, or recompute the R58 handoff from the original immutable reports."""
    path = Path(path)
    if path.name == 'warm-launcher.json':
        return prior_owner(path)[0]
    receipt, _ = evidence(path,'map-owner-lineage.json')
    expected = replacement(receipt['prior'],path.resolve().parent)
    require(receipt == expected, 'Replacement lineage receipt does not match its source evidence')
    return expected['identity']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('game-before','preflight','seal','verify'))
    parser.add_argument('path',type=Path,help='Original warm launcher for preflight/seal, or the owner receipt to verify')
    parser.add_argument('--folder',type=Path,help='Run evidence directory containing before.json and ensure-child.json')
    parser.add_argument('--game-process-id',type=int,help='Exact observed Genshin process for the R58 to R59 handoff')
    args = parser.parse_args()
    if args.operation == 'verify':
        print(json.dumps(load_map_owner(args.path)))
    elif args.operation == 'game-before':
        require(args.game_process_id is not None and args.game_process_id > 0, 'Specify the exact observed game PID')
        receipt, _ = evidence(args.path,'map-owner-lineage.json')
        successor_release(receipt)
        old = load_map_owner(args.path)
        require(args.game_process_id not in (old['root']['processId'],old['child']['processId']), 'A control process cannot be the game')
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rdp-automation'))
        from root_upgrade import OwnedProcess
        from rdp_control import protected_game_identity
        process = OwnedProcess(args.game_process_id)
        try:
            print(json.dumps(protected_game_identity(process,old['child']['windowsSessionId'],args.game_process_id)))
        finally:
            process.close()
    else:
        if not args.folder:
            parser.error('preflight and seal require --folder')
        if args.operation == 'preflight':
            old, build, pins = preflight(args.path,args.folder / 'before.json')
            print(json.dumps(dict(source=old,targetConfigSha256=check_clean_target(build),
                                  **({'protectedGame':pins['protectedGame']} if 'protectedGame' in pins else {}),
                                  **{k:build[k] for k in ('targetDirectory','exeSha256','dllSha256')})))
        else:
            receipt = replacement(args.path,args.folder)
            with (args.folder / 'map-owner-lineage.json').open('x',encoding='utf-8') as out:
                json.dump(receipt,out,indent=2)
            print(json.dumps(receipt['identity']))
