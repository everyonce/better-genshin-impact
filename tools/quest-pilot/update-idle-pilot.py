"""Replace explicitly named Git versions of idle ActOnePilot scripts after a public RDP run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import uuid

ROUTE = runpy.run_path(str(Path(__file__).with_name('run-rdp-route.py')))
require, read, save = (ROUTE[name] for name in ('require', 'read', 'save'))
PROTO = ROUTE['FILE_PROTOCOL']
REPO = Path(__file__).resolve().parents[2]
PREFIX = 'BetterGenshinImpact/User/JsScript/ActOnePilot/'
GAME = ('processId', 'windowsSessionId', 'startedFileTime', 'executable', 'hwnd')
LEASES = ('.rdp-route-launcher.lock', '.route-controller.lock')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def terminal_run(directory):
    """Require a genuine finished public run, including the original child’s authenticated retirement."""
    launch, worker, launcher = (read(directory/name) for name in
                               ('launch.json', 'worker-result.json', 'launcher-result.json'))
    require(directory.suffix == '.rdp' and Path(launch['output']).resolve() == directory
            and Path(launcher['workerResult']).resolve() == directory/'worker-result.json', 'Run directory mismatch.')
    state = worker.get('status')
    require(state in ('arrived', 'failed', 'gpu_unverified') and worker.get('exitCode') == (0 if state=='arrived' else 2)
            and launcher.get('status') == state and launcher.get('exitCode') == worker['exitCode']
            and launcher.get('pilotRetired') is True
            and worker.get('pilotRetired') is True and worker.get('leaseRemoved') is True
            and worker.get('cleanupErrors') == [], 'Public route has not finished cleanly retiring its pilot.')
    for role in ('root', 'child'):
        expected = launch['owner'][role]
        require(all(ROUTE['same_owner'](record['owner'][role], expected) for record in (worker,launcher)),
                'Route owner receipts disagree.')
    require(ROUTE['same_owner'](worker['ownerAfter'],launch['owner']['child']) and worker.get('session')
            and worker['game']['windowsSessionId']==launch['owner']['child']['windowsSessionId']
            and all(worker['game'].get(k) for k in GAME), 'Missing retired child or game identity.')
    return dict(owner=launch['owner'],game=worker['game'],session=worker['session'])


def committed(before, after, names):
    """Resolve immutable local commits and read only regular top-level JavaScript blobs."""
    require(names and len(set(n.lower() for n in names))==len(names) and
            all(re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*\.js', n) and not Path(n).is_reserved() for n in names),
            'Use distinct top-level pilot .js basenames.')
    env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_ALLOW_PROTOCOL='none',GIT_TERMINAL_PROMPT='0')
    def git(*args):
        return subprocess.check_output(['git','--no-replace-objects','--no-optional-locks','-C',str(REPO),*args],
                                       env=env,timeout=20)
    versions=[]
    for ref in (before,after):
        require(re.fullmatch(r'[0-9a-fA-F]{7,40}',ref), 'Supply explicit hexadecimal Git commit IDs.')
        full=git('rev-parse','--verify',ref+'^{commit}').decode().strip()
        require(full.startswith(ref.lower()), 'Use a commit ID, not a tag object.')
        versions.append(full)
    require(versions[0]!=versions[1], 'The two revisions are identical.')
    blobs={}
    for name in names:
        pair=[]
        for version in versions:
            entry=git('ls-tree','-z',version,'--',PREFIX+name).rstrip(b'\0')
            meta,sep,path=entry.partition(b'\t')
            require(sep and path.decode()==PREFIX+name and meta.startswith(b'100644 blob '),
                    'Missing regular Git file '+name)
            pair.append(git('cat-file','blob',meta.split()[-1].decode()))
        require(pair[0]!=pair[1], 'No change between revisions for '+name)
        blobs[name]=pair
    return versions,blobs


def slot_state(pilot):
    """An empty request slot needs no synthetic history; an existing request must have a genuine final receipt."""
    slot=pilot/'request.json'
    if not slot.exists():
        return None
    raw=slot.read_bytes()
    q=json.loads(raw)
    receipt=read(PROTO.request_receipt_path(pilot,q['session'],q['id']))
    observation=read(PROTO.observation_path(pilot,q['session'],receipt['frameId']))
    PROTO.validate_terminal_receipt(q,receipt,observation)
    return raw


def verify_idle(pin, rdp, reconcile, game_probe):
    """Refresh both original pipe endpoints and the real game window inside its own ordinary RDP session."""
    expected=pin['owner']
    current=ROUTE['select_owner']({'instances':[rdp.refresh(expected[role]) for role in ('root','child')]},
                                  expected['child']['processId'],expected)
    for role in ('root','child'):
        actual,old=current[role],expected[role]
        require(Path(actual['appDirectory']).resolve()==Path(old['appDirectory']).resolve()
                and actual.get('assemblySha256')==old.get('assemblySha256'), 'Release directory or assembly changed.')
    require(current['root'].get('taskRunning') is False, 'The primary host is busy.')
    child=current['child']
    reconcile._idle(rdp,child)
    require(child.get('serviceOwnsPilot') is False and not child.get('activeRequestId')
            and child.get('scriptSession') in (None,'',pin['session']), 'A subsequent pilot or request owns the child.')
    game=game_probe(Path(child['appDirectory']).resolve(),child['windowsSessionId'])
    require(all(game.get(k)==pin['game'][k] for k in GAME),'The original game lifetime or window changed.')


def exclusive(path, data):
    """Create an original or transaction record without clobbering someone else's bytes."""
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def install(pilot, output, blobs, check, no_links, replace=PROTO.replace_pending):
    """Own both public leases during the batch and restore only our proven writes on failure."""
    no_links(pilot)
    no_links(output)
    require(pilot.stat().st_dev==output.stat().st_dev, 'Evidence and installed scripts must share a volume.')
    token=json.dumps(dict(launchId='idle-pilot-update-'+output.name,output=str(output))).encode()
    owned=[]; changed=[]; original={}; release=True
    report=dict(files={},status='preparing')
    def guard():
        check()
        require(all(path.read_bytes()==token for path in owned), 'An update lease changed.')
        require(not os.path.lexists(pilot/'gpu-adviser-config.json'), 'A GPU adviser is still active.')
        current=pilot/'request.json'
        require((current.read_bytes() if current.exists() else None)==slot, 'The pilot request slot changed.')
    def swap(name, staged, expected):
        def verify():
            guard()
            path=pilot/name
            no_links(path)
            require(path.read_bytes()==expected, 'Installed file changed: '+name)
        replace(staged,pilot/name,before_replace=verify)
    try:
        check()
        for basename in LEASES:
            path=pilot/basename
            with path.open('xb') as lock:
                owned.append(path)
                lock.write(token)
        slot=slot_state(pilot)
        guard()
        for name,(before,after) in blobs.items():
            path=pilot/name
            no_links(path)
            disk=path.read_bytes()
            require(disk==before or (b'\r' not in before and disk==before.replace(b'\n',b'\r\n')),
                    'Installed bytes disagree with --from-ref: '+name)
            original[name]=disk
            exclusive(output/('original-'+name),disk)
            exclusive(output/('stage-'+name),after)
            report['files'][name]=dict(originalSha256=sha(disk),fromGitSha256=sha(before),toGitSha256=sha(after))
        report['status']='prepared'
        save(output/'result.json',report)
        for name,(_,after) in blobs.items():
            staged=output/('stage-'+name)
            require(staged.read_bytes()==after,'Staged Git blob changed: '+name)
            swap(name,staged,original[name])
            changed.append(name)
        guard()
        require(all((pilot/name).read_bytes()==blobs[name][1] for name in changed),'Installed readback failed.')
        report['status']='installed'
        save(output/'result.json',report)
    except BaseException as error:
        report.update(status='failed',error=str(error),swapped=list(changed),restored=[])
        try:
            for name in reversed(changed):
                backup=(output/('original-'+name)).read_bytes()
                require(backup==original[name], 'Original backup changed: '+name)
                staged=output/('restore-'+name)
                exclusive(staged,backup)
                swap(name,staged,blobs[name][1])
                require((pilot/name).read_bytes()==backup,'Rollback readback failed: '+name)
                report['restored'].append(name)
            if changed:report['status']='rolled_back'
        except BaseException as recovery:
            release=False
            report.update(status='recovery_required',recoveryError=str(recovery))
        save(output/'result.json',report)
        raise
    finally:
        if release:
            try:
                require(all(path.read_bytes()==token for path in owned), 'A route lease changed during cleanup.')
                for path in reversed(owned):
                    path.unlink()
            except (RuntimeError,OSError) as error:
                report.update(status='cleanup_required',cleanupError=str(error))
                save(output/'result.json',report)
                raise
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--completed-run',required=True,type=Path)
    parser.add_argument('--from-ref',required=True)
    parser.add_argument('--to-ref',required=True)
    parser.add_argument('files',nargs='+')
    parser.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    directory=args.completed_run.resolve(strict=True)
    pin=terminal_run(directory)
    versions,blobs=committed(args.from_ref,args.to_ref,args.files)
    rdp,_,_=ROUTE['helpers']()
    import child_reconciliation as reconcile
    owner=ROUTE['select_owner'](rdp.discover(),pin['owner']['child']['processId'],pin['owner'])
    app=Path(pin['owner']['child']['appDirectory']).resolve()
    package=reconcile.verified_package(rdp,app,REPO/'artifacts')
    require(package['dllSha256'].lower()==owner['child']['assemblySha256'].lower(), 'Loaded release assembly differs.')
    evidence=app.parent.parent/'pilot-updates'
    if args.worker is not None:
        from child_runner import require_ordinary_rdp, windows_identity
        require_ordinary_rdp(windows_identity(),owner['child']['windowsSessionId'])
        output=args.worker.absolute()
        require(output.parent==evidence and re.fullmatch('[0-9a-f]{32}',output.name), 'Invalid worker evidence directory.')
        rdp._no_links(output)
        expected=read(output/'plan.json')
        require(expected==dict(completedRun=str(directory),versions=versions,files=args.files,
                               release=str(app),session=pin['session']), 'Worker plan or retirement session changed.')
        result=install(app/'User/JsScript/ActOnePilot',output,blobs,
                       lambda:verify_idle(pin,rdp,reconcile,ROUTE['foreground_game']),rdp._no_links)
        print(json.dumps(result))
        return 0
    evidence.mkdir(exist_ok=True)
    rdp._no_links(evidence)
    output=evidence/uuid.uuid4().hex
    output.mkdir()
    save(output/'plan.json',dict(completedRun=str(directory),versions=versions,files=args.files,
                                 release=str(app),session=pin['session']))
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--completed-run',str(directory),
             '--from-ref',versions[0],'--to-ref',versions[1],'--worker',str(output),*args.files]
    print('Update evidence: '+str(output),flush=True)
    broker=rdp.run_command(owner['root'],command,str(REPO),sys.executable,120,str(output/'jobs'),65536)
    save(output/'broker.json',broker)
    require(broker.get('returnCode')==0 and broker.get('timedOut') is False
            and broker.get('windowsSessionId')==owner['child']['windowsSessionId']
            and read(output/'result.json')['status']=='installed','Update did not complete. Inspect '+str(output))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(2)
