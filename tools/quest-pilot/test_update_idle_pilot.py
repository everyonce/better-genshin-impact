"""Inert update transactions. Native broker, game windows and installed release paths stay out of these tests."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('idle_update',Path(__file__).with_name('update-idle-pilot.py'))
u=importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class IdleUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.pilot=root/'pilot';self.pilot.mkdir()
        self.out=root/'evidence';self.out.mkdir()
        self.blobs={'a.js':(b'old a\n',b'new a\n'),'b.js':(b'old b\n',b'new b\n')}
        for name,(before,_) in self.blobs.items():
            (self.pilot/name).write_bytes(before.replace(b'\n',b'\r\n'))

    def update(self, check=lambda:None, replace=u.PROTO.replace_pending):
        return u.install(self.pilot,self.out,self.blobs,check,lambda p:p.stat(),replace)

    def test_success_preserves_disk_preimage_and_uses_git_bytes(self):
        result=self.update()
        self.assertEqual(result['status'],'installed')
        for name,(before,after) in self.blobs.items():
            self.assertEqual((self.pilot/name).read_bytes(),after)
            self.assertEqual((self.out/('original-'+name)).read_bytes(),before.replace(b'\n',b'\r\n'))
        self.assertFalse(any((self.pilot/p).exists() for p in u.LEASES))

    def test_failure_on_second_file_rolls_back_only_the_first(self):
        def replace(source,dest,before_replace):
            before_replace()
            if source.name=='stage-b.js':raise OSError('simulated sharing failure')
            os.replace(source,dest)
        with self.assertRaisesRegex(OSError,'sharing failure'):self.update(replace=replace)
        result=u.read(self.out/'result.json')
        self.assertEqual((result['status'],result['swapped'],result['restored']),('rolled_back',['a.js'],['a.js']))
        for name,(before,after) in self.blobs.items():
            self.assertEqual((self.pilot/name).read_bytes(),before.replace(b'\n',b'\r\n'))
        self.assertFalse(any((self.pilot/p).exists() for p in u.LEASES))

    def test_loss_of_ownership_after_swap_retains_evidence_and_leases(self):
        def check():
            if (self.pilot/'a.js').read_bytes()==b'new a\n':raise RuntimeError('owner changed')
        with self.assertRaisesRegex(RuntimeError,'owner changed'):self.update(check)
        self.assertEqual(u.read(self.out/'result.json')['status'],'recovery_required')
        self.assertEqual((self.out/'original-a.js').read_bytes(),b'old a\r\n')
        self.assertTrue(all((self.pilot/p).is_file() for p in u.LEASES))

    def test_source_change_or_existing_lease_does_not_publish(self):
        existing=self.pilot/u.LEASES[1];existing.write_bytes(b'live route')
        with self.assertRaises(FileExistsError):self.update()
        self.assertEqual(existing.read_bytes(),b'live route')
        self.assertFalse((self.pilot/u.LEASES[0]).exists())
        existing.unlink()
        (self.pilot/'b.js').write_bytes(b'user modification')
        with self.assertRaisesRegex(RuntimeError,'disagree'):self.update()
        self.assertEqual((self.pilot/'a.js').read_bytes(),b'old a\r\n')
        self.assertEqual((self.pilot/'b.js').read_bytes(),b'user modification')

    def test_foreign_adviser_and_unfinished_slot_refused(self):
        config=self.pilot/'gpu-adviser-config.json';config.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'adviser'):self.update()
        config.unlink()
        (self.pilot/'request.json').write_text('{"session":"bad","id":"wrong"}')
        with self.assertRaises((RuntimeError,ValueError,OSError)):self.update()
        self.assertEqual((self.pilot/'a.js').read_bytes(),b'old a\r\n')

    def test_caller_cannot_supply_path_or_git_expression(self):
        for value in ('a/b.js',r'..\bgi.js','a.json','C:foo.js','../x.js'):
            with self.assertRaisesRegex(RuntimeError,'basenames'):u.committed('abcdef0','1234567',[value])
        with self.assertRaisesRegex(RuntimeError,'basenames'):u.committed('abcdef0','1234567',['A.js','a.js'])
        with self.assertRaisesRegex(RuntimeError,'commit IDs'):u.committed('HEAD~1','1234567',['a.js'])

    def pins(self):
        root=dict(processId=13,windowsSessionId=1,instanceNonce='rootNonce',instanceType='Primary',
                  childConnectedState=1,childWindowMinimized=True,childSessionId=4,automationEnabled=True,
                  appDirectory=str(self.pilot),assemblySha256='abc',taskRunning=False)
        child=dict(processId=26,windowsSessionId=4,instanceNonce='childNonce',instanceType='ChildSession',
                   rootProcessId=13,remoteDesktop=True,runtimeRunning=True,appDirectory=str(self.pilot),
                   assemblySha256='def',activeRequestId=None,serviceOwnsPilot=False,scriptSession='s-01')
        game=dict(processId=39,windowsSessionId=4,startedFileTime=12345,executable='game.exe',hwnd=123)
        return dict(owner=dict(root=root,child=child),session='s-01',game=game)

    def test_refresh_checks_both_nonces_release_and_game_window(self):
        pin=self.pins();reconcile=Mock()
        for change in (None,'root','child','release','game','busy'):
            def refresh(e):
                v=dict(e)
                if change in ('root','child') and e is pin['owner'][change]:v['instanceNonce']='other'
                if change=='release' and e is pin['owner']['child']:v['appDirectory']=str(self.out)
                if change=='busy' and e is pin['owner']['child']:v['activeRequestId']='new'
                return v
            rdp=Mock(refresh=refresh)
            probe=lambda *_: dict(pin['game'],hwnd=999) if change=='game' else pin['game']
            if change:
                with self.assertRaises(RuntimeError):u.verify_idle(pin,rdp,reconcile,probe)
            else:u.verify_idle(pin,rdp,reconcile,probe)

    def test_public_run_must_be_terminal_and_belong_to_the_current_pair(self):
        run=Path(self.tmp.name)/'completed.rdp';run.mkdir();pin=self.pins();owner=pin['owner']
        (run/'launch.json').write_text(json.dumps(dict(output=str(run),owner=owner)))
        launcher=dict(workerResult=str(run/'worker-result.json'),owner=owner,pilotRetired=True,status='failed',exitCode=2)
        (run/'launcher-result.json').write_text(json.dumps(launcher))
        worker=dict(owner=owner,ownerAfter=owner['child'],game=pin['game'],session=pin['session'],status='failed',
                    exitCode=2,leaseRemoved=True,cleanupErrors=[],pilotRetired=True)
        for updates in ({},{'status':'running'},{'leaseRemoved':False},{'pilotRetired':False},
                        {'ownerAfter':dict(owner['child'],instanceNonce='new')}):
            (run/'worker-result.json').write_text(json.dumps(worker|updates))
            if updates:
                with self.assertRaises(RuntimeError):u.terminal_run(run)
            else:self.assertEqual(u.terminal_run(run),pin)


if __name__=='__main__':
    unittest.main()
