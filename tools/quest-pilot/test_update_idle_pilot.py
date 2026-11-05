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

    def test_new_helpers_precede_all_existing_scripts_under_both_leases(self):
        self.blobs.update({'leaf.js':(None,b''),'helper.js':(None,b'leaf()\n')})
        def replace(source,dest,before_replace):
            self.assertTrue(all((self.pilot/p).is_file() for p in u.LEASES))
            self.assertEqual((self.pilot/'leaf.js').read_bytes(),b'')
            self.assertEqual((self.pilot/'helper.js').read_bytes(),b'leaf()\n')
            u.PROTO.replace_pending(source,dest,before_replace=before_replace)
        result=self.update(replace=replace)
        self.assertEqual(result['publicationOrder'],['leaf.js','helper.js','a.js','b.js'])
        self.assertEqual(result['files']['leaf.js'],dict(operation='add',originalSha256=None,
                         fromGitSha256=None,toGitSha256=u.sha(b'')))
        self.assertFalse((self.out/'original-helper.js').exists())
        self.assertFalse((self.out/'stage-helper.js').exists())
        self.assertEqual(result['status'],'installed')

    def test_mixed_rollback_restores_references_then_removes_our_additions(self):
        self.blobs['helper.js']=(None,b'helper')
        def replace(source,dest,before_replace):
            self.assertEqual((self.pilot/'helper.js').read_bytes(),b'helper')
            if source.name=='stage-b.js':raise OSError('failed reference')
            u.PROTO.replace_pending(source,dest,before_replace=before_replace)
        with self.assertRaisesRegex(OSError,'failed reference'):self.update(replace=replace)
        result=u.read(self.out/'result.json')
        self.assertEqual((result['status'],result['restored']),('rolled_back',['a.js','helper.js']))
        self.assertEqual((self.pilot/'a.js').read_bytes(),b'old a\r\n')
        self.assertFalse((self.pilot/'helper.js').exists())
        self.assertFalse(any((self.pilot/p).exists() for p in u.LEASES))

    def test_preexisting_equal_dependency_is_foreign(self):
        self.blobs['helper.js']=(None,b'helper')
        (self.pilot/'helper.js').write_bytes(b'helper')
        with self.assertRaisesRegex(RuntimeError,'occupied'):self.update()
        self.assertEqual((self.pilot/'helper.js').read_bytes(),b'helper')
        self.assertEqual((self.pilot/'a.js').read_bytes(),b'old a\r\n')

    def test_intervening_claim_does_not_overwrite_or_remove_foreign_file(self):
        self.blobs['helper.js']=(None,b'helper')
        publish=u.publish_addition
        def claim(staged,dest):
            dest.write_bytes(b'other owner')
            publish(staged,dest)
        with patch.object(u,'publish_addition',claim), self.assertRaises(FileExistsError):self.update()
        self.assertEqual((self.pilot/'helper.js').read_bytes(),b'other owner')
        self.assertEqual((self.pilot/'a.js').read_bytes(),b'old a\r\n')

    def test_modified_new_file_is_left_for_recovery(self):
        self.blobs['helper.js']=(None,b'helper')
        def replace(*args,**kwargs):
            (self.pilot/'helper.js').write_bytes(b'edited')
            raise OSError('interrupted')
        with self.assertRaisesRegex(OSError,'interrupted'):self.update(replace=replace)
        self.assertEqual((self.pilot/'helper.js').read_bytes(),b'edited')
        self.assertEqual(u.read(self.out/'result.json')['status'],'recovery_required')
        self.assertTrue(all((self.pilot/p).is_file() for p in u.LEASES))

    def test_equal_bytes_from_a_different_file_are_left_for_recovery(self):
        self.blobs['helper.js']=(None,b'helper')
        def replace(*args,**kwargs):
            other=self.pilot/'other';other.write_bytes(b'helper')
            os.replace(other,self.pilot/'helper.js')
            raise OSError('file identity changed')
        with self.assertRaisesRegex(OSError,'identity changed'):self.update(replace=replace)
        self.assertEqual((self.pilot/'helper.js').read_bytes(),b'helper')
        self.assertEqual(u.read(self.out/'result.json')['status'],'recovery_required')

    def test_only_an_empty_source_tree_result_is_a_new_script(self):
        old,new='a'*40,'b'*40
        regular=b'100644 blob '+b'1'*40+b'\t'+(u.PREFIX+'helper.js').encode()+b'\0'
        symlink=regular.replace(b'100644',b'120000')
        for before,after,valid in ((b'',regular,True),(b'',b'',False),(symlink,regular,False),(b'',symlink,False)):
            def git(command,**kwargs):
                if 'rev-parse' in command:return command[-1][:40].encode()
                if 'ls-tree' in command:return before if old in command else after
                self.assertIn('cat-file',command)
                return b''
            with self.subTest(before=before,after=after), patch.object(u.subprocess,'check_output',git):
                if valid:self.assertEqual(u.committed(old,new,['helper.js'])[1]['helper.js'],[None,b''])
                else:
                    with self.assertRaisesRegex(RuntimeError,'regular Git file'):u.committed(old,new,['helper.js'])

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
