"""Pinned evidence adapter for the already validated fixed DesktopDc courtyard."""
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import sys

HOST_POLICY = 'host-acquisition-v1'
SEED = 'mondstadt-city-leg-1-v1'
RETURN = 'mondstadt-city-courtyard-return-v1'
FORWARD = 'mondstadt-city-courtyard-forward-v1'
PROFILES = {'return': RETURN, 'forward': FORWARD}

def require(condition, message):
    """Reject ambiguity before another mutation can be admitted."""
    if not condition:
        raise RuntimeError(message)


def pin(path):
    """Return an exact file identity without executing its contents."""
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def read(path, limit=16*1024*1024):
    """Bound JSON and reject duplicate keys/nonfinite numbers before interpreting evidence."""
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value
    def nonfinite(value):
        raise RuntimeError('Nonfinite JSON value: ' + value)
    def number(value):
        parsed = float(value)
        require(math.isfinite(parsed), 'Nonfinite JSON number: ' + value)
        return parsed
    path = Path(path)
    require(path.stat().st_size <= limit, 'Oversized JSON input.')
    payload = path.read_bytes()
    require(len(payload) <= limit, 'JSON input grew beyond its bound.')
    return json.loads(payload.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=number)


def verify_pin(row):
    """Resolve an absolute file pin without assuming a particular research directory."""
    require(type(row) is dict and set(row) == {'path','bytes','sha256'}
            and type(row['path']) is str and Path(row['path']).is_absolute()
            and type(row['bytes']) is int and row['bytes'] >= 0
            and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Malformed file pin.')
    actual = pin(row['path'])
    require(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'], 'Pinned file changed.')
    return Path(row['path']).resolve()


def sha(path):
    """Hash one existing file; never execute a pinned script."""
    return pin(path)['sha256']


def require_root(status, binding):
    """Preserve the exact primary and its minimized connected child desktop."""
    root = binding['_root']
    require(all(type(status.get(k)) is int and status[k] == root[k]
                for k in ('processId','windowsSessionId'))
            and status.get('instanceNonce') == root['instanceNonce']
            and status.get('assemblySha256','').lower() == root['assemblySha256'].lower()
            and status.get('instanceType') == 'Primary', 'The preserved primary changed.')
    require(status.get('childWindowMinimized') is True
            and status.get('childSessionId') == binding['child']['windowsSessionId']
            and status.get('childConnectedState') == 1, 'RDP connection/minimized state changed.')


def require_child(status, binding, *, idle=True):
    """Admit the pinned ready child; the independent game CIM check stays batch-level."""
    child = binding['child']
    require(type(status) is dict and all(status.get(k) == child[k]
                for k in ('processId','windowsSessionId','instanceNonce'))
            and all(type(status.get(k)) is int for k in ('processId','windowsSessionId'))
            and status.get('instanceType') == 'ChildSession'
            and status.get('rootProcessId') == binding['_root']['processId'], 'Child identity changed.')
    require(status.get('remoteDesktop') is True and status.get('uiStatus') == 'current'
            and status.get('runtimeRunning') is True and status.get('automationState') == 'game_ready',
            'Exact game runtime is unavailable.')
    require(status.get('assemblySha256','').lower() == binding['dllSha256']
            and Path(status.get('appDirectory','')).resolve() == binding['_app'], 'Child package changed.')
    require(status.get('agentInputEnabled') is False, 'Agent input must stay disabled.')
    if idle:
        require(status.get('taskRunning') is False and status.get('agentStreamRunning') is False,
                'Competing task or stream; do not take over.')


def require_policy(status, policy):
    """Require the exact active DesktopDc policy and its advertised capabilities."""
    require(policy in ('observe-only', HOST_POLICY)
            and type(status.get('desktopDcSourcePolicyVersion')) is int
            and status['desktopDcSourcePolicyVersion'] == 1
            and status.get('desktopDcSourcePolicies') == ['observe-only', HOST_POLICY],
            'Exact DesktopDc policy capability missing.')
    require(status.get('captureMode') == 'DesktopDc'
            and status.get('configuredDesktopDcSourcePolicy') == status.get('effectiveDesktopDcSourcePolicy') == policy,
            'Configured/active DesktopDc policy differs.')
    require(all(status.get(k) is None for k in
                ('effectiveReadbackMode', 'effectiveSourceRetention', 'effectiveConversion')),
            'Desktop capture cannot advertise active WGC options.')


def same_pin(a, b):
    """Require the complete file identity, including byte length and resolved path."""
    return (type(a) is dict and type(b) is dict and type(a.get('bytes')) is int
            and type(b.get('bytes')) is int and a['bytes'] == b['bytes']
            and a.get('sha256') == b.get('sha256') and type(a.get('path')) is str
            and type(b.get('path')) is str and Path(a['path']).resolve() == Path(b['path']).resolve())


def require_latest(current_child, saved_status):
    """Ordinary status omits only the result; the exact retained owner must otherwise match."""
    strip = lambda owner: {k: v for k, v in owner.items() if k != 'result'}
    require(strip(current_child.get('navigationBaseline') or {})
            == strip(saved_status['navigationBaseline']), 'Latest native owner differs from the accepted predecessor.')


def audit_native(status, binding, *, profile_id='mondstadt-city-leg-1-v1'):
    """Hash exact first-slice artifacts; full numerical/decision audit remains separately reported."""
    owner = status.get('navigationBaseline') or {}; result = owner.get('result') or {}; evidence = result.get('evidence')
    continued = profile_id in ('mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1')
    require(continued or profile_id == 'mondstadt-city-leg-1-v1', 'Unsupported fixed host profile.')
    require(owner.get('profileId') == profile_id and owner.get('timingContract') == 'v4'
            and owner.get('capturePolicy') == 'task_owned_timer' and owner.get('sourcePolicy') == HOST_POLICY
            and owner.get('readbackMode') is None and owner.get('gameProcessId') == binding['_game']['ProcessId']
            and owner.get('windowsSessionId') == binding['child']['windowsSessionId'] and owner.get('shadowCapture') is None
            and (continued or owner.get('continuation') is None), 'Native host selection/identity changed.')
    if continued:
        reference = owner.get('continuation') or {}; link = result.get('continuation') or {}
        require(type(owner.get('hostEndpointContinuationVersion')) is int and owner['hostEndpointContinuationVersion'] == 1
                and type(owner.get('endpointContinuationVersion')) is int and owner['endpointContinuationVersion'] == 2
                and type(link.get('version')) is int and link['version'] == 2
                and type(reference.get('version')) is int and reference == dict(version=2,
                    predecessorRunId=link.get('predecessorRunId'), predecessorProfileId=link.get('predecessorProfileId')),
                'Host continuation capability/full/compact projection differs.')
        require(link.get('sourcePolicy') == HOST_POLICY and link.get('readbackMode') is None
                and link.get('childAssemblySha256', '').lower() == status.get('assemblySha256', '').lower()
                and re.fullmatch('[0-9a-f]{64}', link.get('childAssemblySha256', ''))
                and link.get('childProcessId') == status.get('processId')
                and link.get('childNonce') == status.get('instanceNonce')
                and link.get('windowsSessionId') == binding['child']['windowsSessionId'] and link.get('gameProcessId') == binding['_game']['ProcessId']
                and link.get('physicalInputAcknowledged') is False,
                'Host continuation runtime/build/source contract differs.')
    if not evidence:
        require(result.get('verified') is not True, 'Verified short lacks its hash-bound journal.')
        return None
    require(evidence.get('sourcePolicy') == result.get('sourcePolicy') == HOST_POLICY
            and evidence.get('readbackMode') is None and evidence.get('shadowCapture') is None
            and result.get('profileId') == profile_id and result.get('waypoint') is None,
            'Unsupported host evidence selection.')
    if continued:
        require(type(result.get('routeVersion')) is int and result['routeVersion'] == 1
                and type(result.get('legs')) is list and len(result['legs']) <= 1, 'Unexpected one-leg shape.')
        if result.get('verified') is True:
            require(len(result['legs']) == 1 and result['legs'][0].get('outcome') == 'completed',
                    'Verified courtyard lacks its completed leg.')
    else:
        require(result.get('routeVersion') is None and result.get('legs') == [] and result.get('continuation') is None,
                'Ordinary short gained continuation evidence.')
    require(re.fullmatch('[0-9a-f]{32}', owner.get('runId', '')) and owner['runId'] != '0'*32,
            'Malformed native run identity.')
    directory = (binding['_app'] / 'User/NavigationBaselines' / owner['runId']).resolve(); files = []; journal = None
    for stem in ('journal', 'initialImage', 'finalImage'):
        name, digest = evidence.get(stem + 'Path'), evidence.get(stem + 'Sha256')
        if name is None:
            require(digest is None, 'Artifact hash without a path.'); continue
        path = Path(name).resolve()
        require(path.is_relative_to(directory) and path.stat().st_size <= (6 if stem == 'journal' else 32)*1024*1024,
                'Native artifact path/size exceeded its bound.')
        require(isinstance(digest, str) and sha(path) == digest.lower(), 'Native artifact hash differs.')
        files.append(dict(kind=stem, **pin(path)))
        if stem == 'journal':
            journal = read(path)
    require(journal is not None and journal.get('schemaVersion') == 2 and type(journal['schemaVersion']) is int
            and journal.get('sourcePolicy') == HOST_POLICY and journal.get('runId') == owner['runId']
            and journal.get('gameProcessId') == binding['_game']['ProcessId'] and journal.get('windowsSessionId') == binding['child']['windowsSessionId']
            and journal.get('readbackMode') is None and journal.get('readbackPendingCount') == 0
            and journal.get('capturePolicy') == 'task_owned_timer' and journal.get('timingContract') == 'v4'
            and journal.get('profileId') == profile_id, 'Host journal identity/policy mismatch.')
    require(journal.get('trainingEligible') is False and journal.get('humanDemonstration') is False
            and journal.get('completeLowLevelDispatchTrace') is False and journal.get('ownerCompletionRequired') is True,
            'Unexpected journal authority claims.')
    return dict(schema='r45-native-host-artifacts-v1', runId=owner['runId'], state=owner.get('state'), files=files,
        observations=len(journal['observations']), inputTransitions=len(journal['inputTransitions']),
        hostMetadataOnly=True, renderFreshnessMeasured=False, independentFullRouteAudit=False)


def require_predecessor(path, binding, direction):
    """Only files are read here; an accepted old-build run cannot authorize a new child."""
    require(direction in PROFILES, 'Unknown fixed direction.')
    proof = read(path)
    require(proof.get('schema') == 'r45-courtyard-predecessor-v1', 'Wrong predecessor proof schema.')
    for key in ('summary', 'result', 'routeAudit', 'auditPackage', 'binding'):
        verify_pin(proof[key])
        require(type(proof[key].get('bytes')) is int, 'Predecessor pin lacks byte length.')
    require(same_pin(proof['auditPackage'], binding.get('routeAuditorPackage')),
            'The exact R45 route auditor must be separately bound before continuation.')
    require(proof.get('bindingSha256') == proof['binding']['sha256'], 'Predecessor audit binding differs.')
    closed = read(proof['binding']['path'])
    require(same_pin(closed.get('liveValidationBinding'), binding['_bindingPin']),
            'Closed route binding does not name this exact live-validation binding.')
    verify_pin(closed['liveValidationBinding'])
    require(closed.get('child') == binding['child'] and closed.get('dllSha256') == binding['dllSha256']
            and closed.get('sourceRevision') == binding['sourceRevision']
            and closed.get('sourceProvenance') == binding['sourceProvenance'], 'Predecessor runtime/source changed.')
    for key in ('buildManifest', 'sourceSnapshotManifest', 'hotReplacement', 'endpointReplacement', 'explicitStartResult'):
        require(same_pin(closed.get(key), pin(verify_pin(binding[key]))), 'Predecessor deployment proof differs: ' + key)
        verify_pin(closed[key])
    summary, result_file, audit = (read(proof[key]['path']) for key in ('summary', 'result', 'routeAudit'))
    require(summary.get('success') is True and summary.get('error', 'missing') is None
            and summary.get('cleanupError', 'missing') is None
            and summary.get('bindingSha256') == binding['_bindingPin']['sha256']
            and summary.get('child') == binding['child'] and same_pin(summary.get('nativeResult'), proof['result']),
            'Predecessor helper did not complete cleanly on this exact deployment.')
    require(result_file.get('error', 'missing') is None, 'Predecessor result retains a helper error.')
    status = result_file.get('status') or {}; require_child(status, binding); require_policy(status, HOST_POLICY)
    owner = status.get('navigationBaseline') or {}; result = owner.get('result') or {}
    profile = proof.get('profileId'); allowed = (SEED, FORWARD) if direction == 'return' else (RETURN,)
    require(profile in allowed and owner.get('profileId') == result.get('profileId') == profile
            and owner.get('runId') == proof.get('runId')
            and re.fullmatch('[0-9a-f]{32}', proof.get('runId', '')) and proof['runId'] != '0'*32,
            'Wrong immediate predecessor direction/run.')
    require(owner.get('state') == 'completed' and owner.get('error', 'missing') is None
            and owner.get('evidenceComplete') is True and result.get('verified') is True
            and result.get('error', 'missing') is None and result.get('inputReleaseError', 'missing') is None,
            'Predecessor native owner is not cleanly verified.')
    expected_action = 'short' if profile == SEED else 'courtyard-' + ('return' if profile == RETURN else 'forward')
    require(summary.get('action') == expected_action, 'Predecessor action/profile changed.')
    require(type(owner.get('endpointContinuationVersion')) is int and owner['endpointContinuationVersion'] == 2
            and type(owner.get('hostEndpointContinuationVersion')) is int and owner['hostEndpointContinuationVersion'] == 1,
            'Predecessor does not advertise the exact host continuation capability.')
    require(audit.get('schema') == 'host-native-route-audit-r45-v1'
            and audit.get('routeEvidenceAccepted') is True and audit.get('runId') == proof['runId']
            and audit.get('profileId') == profile and audit.get('sourceKind') == HOST_POLICY
            and audit.get('child') == binding['child'] and audit.get('assemblySha256') == binding['dllSha256']
            and same_pin(audit.get('analyzerPackage'), proof['auditPackage']), 'Predecessor route audit is not accepted/bound.')
    links = audit.get('artifactLinks')
    require(type(links) is list and all(any(same_pin(link, proof[key]) for link in links)
            for key in ('result', 'binding')), 'Route audit does not join exact predecessor result/binding files.')
    require((audit.get('producerContract') or {}).get('sourceManifestSha256')
            == binding['sourceProvenance']['sourceManifestSha256'], 'Predecessor audit producer differs.')
    if profile != SEED:
        require(audit.get('continuationAccepted') is True, 'Prior courtyard continuation was not independently accepted.')
    # Rehash the actual immediate predecessor artifacts now, without importing the auditor or transport.
    artifact = audit_native(status, binding, profile_id=profile)
    require(artifact is not None, 'Predecessor artifact evidence is missing.')
    return dict(proofFile=pin(path), **proof), status


def prepare(predecessor_path, predecessor_sha):
    """Join the accepted current-format proof to its deployment and immutable tool snapshot."""
    require(sha(predecessor_path) == predecessor_sha, 'Predecessor proof hash differs.')
    proof = read(predecessor_path)
    require(proof.get('schema') == 'r45-courtyard-predecessor-v1', 'Unsupported predecessor proof schema.')
    closed = read(verify_pin(proof['binding']))
    live_path = verify_pin(closed['liveValidationBinding'])
    binding = read(live_path)
    require(binding.get('schema') == 'r45-validation-binding-v1' and binding.get('approvedForValidation') is True,
            'Unsupported or unapproved live binding.')
    binding['_bindingPin'] = pin(live_path)
    for key in ('buildManifest','sourceSnapshotManifest','hotReplacement','endpointReplacement','explicitStartResult','routeAuditorPackage'):
        verify_pin(binding[key])
        require(same_pin(closed.get(key), binding[key]), 'Closed deployment pin differs: ' + key)
    hot = read(binding['hotReplacement']['path'])
    endpoint = read(binding['endpointReplacement']['path'])
    started = read(binding['explicitStartResult']['path'])
    require(all(hot.get(k) is True for k in ('ready','endpointReady','runtimeReady'))
            and endpoint.get('ready') is True and started == hot.get('child')
            and hot.get('endpointResultSha256') == binding['endpointReplacement']['sha256']
            and hot.get('explicitStartResultSha256') == binding['explicitStartResult']['sha256'],
            'Separate endpoint/start proof changed.')
    replacement = hot.get('replacementEvidence') or {}
    require(replacement == endpoint.get('replacementEvidence') and replacement.get('restartAcknowledged') is True
            and replacement.get('phase') == 'replacement_ready'
            and replacement.get('replacementProcessId') == binding['child']['processId']
            and replacement.get('replacementNonce') == binding['child']['instanceNonce'], 'Replacement identity differs.')
    binding['_root'] = hot['root']; binding['_game'] = hot['gameProcess']
    binding['_app'] = Path(started['appDirectory']).resolve()
    require(binding['_app'].is_absolute() and binding['_game'].get('Name') == 'GenshinImpact.exe'
            and type(binding['_game'].get('ProcessId')) is int and binding['_game']['ProcessId'] > 0
            and type(binding['_game'].get('SessionId')) is int
            and binding['_game']['SessionId'] == binding['child']['windowsSessionId']
            and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}Z',binding['_game'].get('CreationUtc','')),
            'Protected game identity is malformed; CIM and native FILETIME are distinct.')
    require_root(hot['root'], binding); require_child(started, binding)
    for filename, key in (('BetterGI.dll','dllSha256'),('Fischless.GameCapture.dll','captureDllSha256')):
        require(sha(binding['_app']/filename) == binding[key], 'Deployed binary changed: ' + filename)
    snapshot = read(binding['sourceSnapshotManifest']['path'])
    require(snapshot.get('schema') == 'r45-worktree-tool-snapshot-v1'
            and snapshot.get('sourceManifestSha256') == binding['sourceProvenance']['sourceManifestSha256']
            and snapshot.get('replacementProofSha256') == binding['hotReplacement']['sha256']
            and snapshot.get('endpointResultSha256') == binding['endpointReplacement']['sha256']
            and snapshot.get('explicitStartResultSha256') == binding['explicitStartResult']['sha256'],
            'Snapshot does not belong to the accepted deployment.')
    snapshot_root = (Path(binding['sourceSnapshotManifest']['path']).parent/'source-snapshot').resolve()
    files = snapshot.get('files'); require(type(files) is list and 0 < len(files) <= 4096, 'Unbounded tool inventory.')
    seen = set()
    for row in files:
        name = row.get('path'); require(type(name) is str and name.startswith('tools/') and name not in seen, 'Invalid tool inventory path.')
        target = (snapshot_root/name).resolve()
        require(target.is_relative_to(snapshot_root), 'Tool snapshot path escaped.')
        verify_pin(dict(path=str(target),bytes=row['bytes'],sha256=row['sha256'])); seen.add(name)
    required = {'tools/rdp-automation/rdp_control.py','tools/rdp-automation/child_runner.py','tools/quest-pilot/controller-control.py'}
    require(required <= seen, 'Client/transport/owned runner are not in the pinned snapshot.')
    binding['_client'] = snapshot_root/'tools/rdp-automation/rdp_control.py'
    profile = proof.get('profileId')
    require(profile in (SEED,RETURN,FORWARD), 'Not an accepted fixed courtyard predecessor.')
    direction = 'forward' if profile == RETURN else 'return'
    accepted, previous = require_predecessor(predecessor_path,binding,direction)
    return binding, accepted, previous, direction


def load_client(binding):
    """Import only the rehashed deployment snapshot, after all pure-file admission checks."""
    require('rdp_control' not in sys.modules and 'child_runner' not in sys.modules, 'A client/runner was already imported.')
    sys.path.insert(0,str(binding['_client'].parent))
    module = importlib.import_module('rdp_control')
    require(Path(module.__file__).resolve() == binding['_client'], 'Wrong client import.')
    require(Path(module.transport.__file__).resolve() == binding['_client'].parents[1]/'quest-pilot/controller-control.py',
            'Wrong pipe transport import.')
    return module
