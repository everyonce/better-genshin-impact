"""Portable repository fixtures for Windows sharing and inert reviewed-worker admission; no live artifacts or input."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import combat_paused_file_admission as held
import combat_trial as trial
import map_owner
import test_map_owner as owner_fixtures
import test_combat_trial as fixtures
from test_combat_paused_review import PausedReviewTrialTests


def digest(path):
    """Hash an inert fixture or retained read-only source."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class HeldFileTests(unittest.TestCase):
    """Exercise real Windows read-sharing-only handles with disposable workspace files."""
    def setUp(self):
        """Own a unique bounded fixture directory and two original inputs."""
        self.tmp=tempfile.TemporaryDirectory(prefix='inert-held-')
        self.folder=Path(self.tmp.name)
        self.a=self.folder/'source.py';self.b=self.folder/'proof.json'
        self.a.write_bytes(b'original source\n');self.b.write_bytes(b'{"original":true}\n')
        self.pins={str(p):digest(p) for p in (self.a,self.b)}
        self.files=None

    def tearDown(self):
        """Close every test-owned handle before removing only its known workspace directory."""
        if self.files is not None:self.files.close()
        self.assertTrue(self.folder.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.tmp.cleanup()

    def test_real_write_delete_denial_and_release(self):
        self.files=held.HeldFiles(self.pins)
        for path in (self.a,self.b):
            with self.assertRaises(PermissionError):path.write_bytes(b'changed')
            with self.assertRaises(PermissionError):path.unlink()
        actual,size=self.files.verify()
        self.assertEqual(actual,self.pins)
        self.assertEqual(size,sum(p.stat().st_size for p in (self.a,self.b)))
        self.assertTrue(all(not os.get_inheritable(row[0].fileno()) for row in self.files.rows.values()))
        self.assertEqual(self.files.close(),[])
        self.a.write_bytes(b'after retirement')

    def test_declared_empty_python_only(self):
        self.a.write_bytes(b'');self.pins[str(self.a)]=digest(self.a)
        with self.assertRaisesRegex(ValueError,'empty'):held.HeldFiles(self.pins)
        self.files=held.HeldFiles(self.pins,empty_sources=[self.a])
        self.assertEqual(self.files.verify()[0],self.pins)
        self.files.close();self.b.write_bytes(b'');self.pins[str(self.b)]=digest(self.b)
        with self.assertRaisesRegex(ValueError,'declared Python'):held.HeldFiles(self.pins,empty_sources=[self.b])

    def test_existing_writer_and_bad_hash_refuse_and_close_partial_set(self):
        with self.b.open('r+b'):
            with self.assertRaises(PermissionError):held.HeldFiles(self.pins)
        self.b.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):held.HeldFiles(self.pins)
        self.a.write_bytes(b'partial handles were released')

    def test_partial_acquisition_close_error_is_typed(self):
        original=held.HeldFiles.close
        def close(files):return original(files)+['inert partial close failure']
        with self.a.open('r+b'),patch.object(held.HeldFiles,'close',close):
            with self.assertRaises(held.HandleCleanupError) as caught:held.HeldFiles(self.pins)
        self.assertEqual(caught.exception.cleanup_errors,['inert partial close failure'])
        self.b.write_bytes(b'partial handles were released')

    def test_first_stream_validation_and_close_errors_are_both_retained(self):
        original_open=open
        class ClosingFailure:
            """Release the disposable real handle while simulating a failed close acknowledgement."""
            def __init__(self,stream):self.stream=stream
            def fileno(self):return self.stream.fileno()
            def close(self):self.stream.close();raise OSError('inert first stream close failure')
        def opened(*args,**kwargs):return ClosingFailure(original_open(*args,**kwargs))
        with patch('builtins.open',opened),patch.object(held.os,'set_inheritable',side_effect=ValueError('inert first validation failure')):
            with self.assertRaises(held.HandleCleanupError) as caught:held.HeldFiles(self.pins)
        self.assertIn('first validation failure',str(caught.exception))
        self.assertIn('first stream close failure',caught.exception.cleanup_errors[0])
        self.a.write_bytes(b'first handle was released')

    def test_raw_handle_conversion_and_cleanup_errors_are_both_retained(self):
        import _winapi,msvcrt
        original_close=_winapi.CloseHandle
        def close(handle):original_close(handle);raise OSError('inert raw handle close failure')
        with patch.object(msvcrt,'open_osfhandle',side_effect=ValueError('inert fd conversion failure')),patch.object(_winapi,'CloseHandle',close):
            with self.assertRaises(held.HandleCleanupError) as caught:held.source_reader(str(self.a),0)
        self.assertIn('fd conversion failure',str(caught.exception))
        self.assertIn('raw handle close failure',caught.exception.cleanup_errors[0])
        self.a.write_bytes(b'raw handle was released')

    def test_closed_handle_or_corrupt_read_refuses(self):
        self.files=held.HeldFiles(self.pins)
        path=next(iter(self.files.rows));stream,identity,pin=self.files.rows[path]
        class Corrupt:
            """Read corruption is simulated; the actual local sharing handle remains real."""
            def fileno(self):return stream.fileno()
            def seek(self,*args):return stream.seek(*args)
            def read(self,*args):return b'corrupt'
            def close(self):return stream.close()
        self.files.rows[path]=(Corrupt(),identity,pin)
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.files.verify()
        self.files.rows[path]=(stream,identity,pin);stream.close()
        with self.assertRaises(ValueError):self.files.verify()

    def test_parent_namespace_substitution_refuses_or_is_denied(self):
        nested=self.folder/'original';nested.mkdir();source=nested/'a.py';source.write_bytes(b'x')
        self.files=held.HeldFiles({str(source):digest(source)})
        moved=self.folder/'moved'
        try:nested.rename(moved)
        except PermissionError:self.files.verify()
        else:
            nested.mkdir()
            with self.assertRaisesRegex(ValueError,'namespace'):self.files.verify()

    def test_all_closes_attempted_and_error_preserved(self):
        self.files=held.HeldFiles(self.pins)
        path=next(iter(self.files.rows));stream,identity,pin=self.files.rows[path]
        class FaultedClose:
            """Release the real handle, then report the simulated close error."""
            def close(self):stream.close();raise OSError('inert close failure')
        self.files.rows[path]=(FaultedClose(),identity,pin)
        errors=self.files.close()
        self.assertEqual(len(errors),1);self.assertIn('inert close failure',errors[0])
        self.a.write_bytes(b'all handles closed');self.b.write_bytes(b'all handles closed')
        self.files=None

    def test_one_private_context_foreign_report_and_reuse_refused(self):
        report={};context=dict(runId='inert-a',owner={'processId':12})
        cap=held.PausedAdmission(context,self.pins,(),lambda:['a'],['a'],{},report)
        self.files=cap.files
        with self.assertRaisesRegex(ValueError,'foreign'):cap.consume(lambda:context,{},lambda:None)
        changed=copy.deepcopy(context);changed['runId']='inert-b'
        with self.assertRaisesRegex(ValueError,'another run'):cap.consume(lambda:changed,report,lambda:None)
        with self.assertRaisesRegex(ValueError,'consumed'):cap.consume(lambda:context,report,lambda:None)
        self.assertTrue(report['consumed']);self.assertEqual(cap.close(),[])

    def test_stop_and_new_source_during_fresh_read_refuse(self):
        report={};context=dict(runId='inert');names=['a'];stopped=[False]
        cap=held.PausedAdmission(context,self.pins,(),lambda:list(names),['a'],{},report)
        self.files=cap.files;original=cap.files.verify
        def mutate():
            """A new importable name appears during a slow read; it cannot inherit authority."""
            value=original();names.append('new.py');return value
        with patch.object(cap.files,'verify',side_effect=mutate),self.assertRaisesRegex(ValueError,'census'):
            cap.consume(lambda:context,report,lambda:None)
        cap.close()
        report={};cap=held.PausedAdmission(context,self.pins,(),lambda:['a'],['a'],{},report)
        self.files=cap.files;original=cap.files.verify
        def stop():
            """Deliver STOP during the final hash operation, before any native call can follow."""
            value=original();stopped[0]=True;return value
        def liveness():
            """Model only the original STOP latch, without a native process."""
            if stopped[0]:raise ValueError('inert STOP')
        with patch.object(cap.files,'verify',side_effect=stop),self.assertRaisesRegex(ValueError,'STOP'):
            cap.consume(lambda:context,report,liveness)
        cap.close()

    def test_finite_budgets_and_namespace_selection(self):
        with patch.object(held,'MAX_TOTAL_BYTES',1),self.assertRaisesRegex(ValueError,'budget'):
            held.HeldFiles(self.pins)
        self.a.write_bytes(b'released')
        self.pins[str(self.a)]=digest(self.a)
        missing=self.folder/'new-release';report={};context={'runId':'x'}
        cap=held.PausedAdmission(context,self.pins,(),lambda:[],[],
            {str(missing):dict(originalPresent=False,selected='historical-witness')},report)
        self.files=cap.files;missing.mkdir()
        with self.assertRaisesRegex(ValueError,'package selection'):cap.consume(lambda:context,report,lambda:None)
        cap.close()


class OwnerClosureTests(unittest.TestCase):
    """Build the finite lineage entirely from the repository's existing synthetic owner fixture."""
    def setUp(self):
        """Use disposable package bytes and recorded identities, never installed releases or live processes."""
        self.fixture=owner_fixtures.MapOwnerTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        prior,self.folder,self.result,_=self.fixture.create_r68_successor()
        self.path=self.folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,self.folder))
        self.prior=prior

    def verify_reader_set(self):
        """Require every actual immutable validator read to appear in the held census."""
        owner,pins,packages=held.owner_inputs(self.path,map_owner.ARTIFACTS,map_owner.load_map_owner)
        observed=set();original=Path.open
        def read_trace(path,*args,**kwargs):
            mode=args[0] if args else kwargs.get('mode','r')
            self.assertIn('r',mode);observed.add(str(path.absolute()))
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',read_trace):actual=map_owner.load_map_owner(self.path)
        self.assertEqual(actual,owner);self.assertEqual(observed,set(pins))
        self.assertEqual(len(packages),11)
        files=held.HeldFiles(pins)
        try:
            self.assertEqual(files.verify()[0],pins)
            self.assertEqual(map_owner.load_map_owner(self.path),owner)
        finally:self.assertEqual(files.close(),[])
        return owner,pins,packages

    def test_complete_synthetic_owner_reader_set_is_held(self):
        """Exercise all eleven live-package selections without an ignored artifact dependency."""
        self.verify_reader_set()

    def test_retained_package_reader_set_and_selection_are_bound(self):
        """Retained witnesses are exact alternatives; reappearance of an original cannot change admission."""
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(67,68))
        owner,pins,packages=self.verify_reader_set()
        missing=map_owner.ARTIFACTS/'release-r67'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])

    def test_missing_owner_evidence_refuses_before_handles(self):
        """A missing native game-lifetime document is not replaced with cached owner identity."""
        (self.folder/'game-before.json').unlink()
        with self.assertRaises(FileNotFoundError):
            held.owner_inputs(self.path,map_owner.ARTIFACTS,map_owner.load_map_owner)


class WorkerHeldTests(PausedReviewTrialTests):
    """Run the actual staged worker with original inert GPU/native boundaries."""
    def begin(self):
        """Prepare a reviewed paused fixture without model or input work."""
        self.capture_and_pause();self.prepare()

    def assert_retired(self,*,started=False):
        """Every terminal path must close its exact file capability and retain cleanup evidence."""
        report=self.report();state=report['pausedImmutableAdmission']
        self.assertTrue(state['closed']);self.assertEqual(state['closeErrors'],[])
        self.assertEqual(self.lifecycle.starts,int(started));self.assertTrue(report['cleanupVerified'])
        self.code.write_bytes(self.code.read_bytes())
        return report

    def test_held_real_worker_success_and_unchanged_new_proof_replay(self):
        self.begin();original=trial.verify_ui_proof
        with patch.object(trial,'verify_ui_proof',wraps=original) as verify:
            self.assertEqual(self.worker(),0,self.report())
        report=self.assert_retired(started=True)
        self.assertEqual((self.loads,self.episodes),(1,1))
        self.assertTrue(report['pausedImmutableAdmission']['consumed'])
        self.assertGreater(report['pausedImmutableAdmission']['freshHashBytes'],0)
        self.assertTrue(any(call.args[0]['directory']==str(self.resume_folder) and call.args[2]=='resume'
            for call in verify.call_args_list))
        self.assertEqual(report['finalPausedReviewAdmission']['verifiedInputsSha256'],
            self.prechecked_seen['verifiedInputsSha256'])

    def test_held_source_write_after_resume_is_denied_before_native_start(self):
        self.begin()
        def resume(ready):self.resume(ready);self.code.write_bytes(b'substituted source')
        self.assertEqual(self.worker(resume=resume),1)
        report=self.assert_retired();self.assertIn('Permission denied',report['error'])
        self.assertFalse(report['nativeStartAttempted'])

    def test_held_archived_source_and_review_are_not_mutable(self):
        self.begin()
        def resume(ready):
            """Both old archived code and the exact inspected review remain read-only."""
            self.resume(ready)
            for path in (self.folder/'source-snapshot'/self.code.relative_to(self.root),self.evidence['review']):
                with self.assertRaises(PermissionError):path.write_bytes(b'changed')
        self.assertEqual(self.worker(resume=resume),0,self.report())
        self.assert_retired(started=True)

    def test_held_extra_module_after_resume_is_rejected(self):
        self.begin()
        def resume(ready):self.resume(ready);(self.code.parent/'PIL.py').write_bytes(b'unpinned')
        self.assertEqual(self.worker(resume=resume),1)
        self.assertIn('census',self.assert_retired()['error'])

    def test_held_stop_during_final_read_has_no_native_start(self):
        self.begin();original=held.HeldFiles.verify
        def verify(files):
            """Only the final post-resume read delivers this synthetic operator stop."""
            value=original(files)
            if hasattr(self,'resume_folder'):trial.request_stop(self.folder,self.preparation,'inert-final-read-stop')
            return value
        with patch.object(held.HeldFiles,'verify',verify):self.assertEqual(self.worker(),1)
        report=self.assert_retired();self.assertFalse(report['nativeStartAttempted'])

    def test_held_starting_status_stop_is_preserved(self):
        self.test_stop_during_starting_status_write_remains_an_unattempted_native_start()
        self.assert_retired()

    def test_held_new_resume_substitution_still_fails_full_replay(self):
        self.begin()
        def resume(ready):self.resume(ready);(self.resume_folder/'after.png').write_bytes(b'changed new image')
        self.assertEqual(self.worker(resume=resume),1)
        self.assertIn('UI proof source changed',self.assert_retired()['error'])

    def test_held_unknown_native_start_never_retries_and_closes_files(self):
        self.begin();self.lifecycle.start_error=TimeoutError('inert unknown start')
        self.assertEqual(self.worker(),1)
        report=self.assert_retired(started=True)
        self.assertEqual(report['status'],'unresolved')
        self.assertEqual(report['nativeStartOutcome'],'unresolved')
        self.assertTrue(report['pausedImmutableAdmission']['consumed'])

    def test_held_close_error_does_not_promote_native_completion(self):
        self.begin();original=held.HeldFiles.close
        def close(files):
            """Retire real test handles, then retain a cleanup uncertainty."""
            errors=original(files)
            return errors+['inert reported close failure']
        with patch.object(held.HeldFiles,'close',close):self.assertEqual(self.worker(),1)
        report=self.report();self.assertEqual(self.lifecycle.starts,1)
        self.assertEqual(report['status'],'unresolved')
        self.assertIn('close failure',report['immutableHandleCleanupError'])
        self.code.write_bytes(self.code.read_bytes())

    def test_held_pretransfer_close_error_is_unresolved(self):
        self.begin();original=held.HeldFiles.close
        def close(files):
            """The await-side STOP cleanup closes handles but reports an uncertain retirement."""
            return original(files)+['inert pretransfer close failure']
        def stopped(ready):trial.request_stop(self.folder,self.preparation,'inert-pretransfer-stop')
        with patch.object(held.HeldFiles,'close',close):self.assertEqual(self.worker(resume=stopped),1)
        report=self.report()
        self.assertEqual((self.lifecycle.starts,self.episodes),(0,0))
        self.assertEqual(report['status'],'unresolved')
        self.assertIn('seriesOperatorStop',report['error'])
        self.assertIn('pretransfer close failure',report['immutableHandleCleanupError'])
        self.assertFalse(report['pausedImmutableAdmission']['closed'])
        self.code.write_bytes(self.code.read_bytes())

    def test_held_partial_acquisition_close_error_is_unresolved(self):
        self.begin();original=held.HeldFiles.close
        def close(files):return original(files)+['inert acquisition close failure']
        with self.code.open('r+b'),patch.object(held.HeldFiles,'close',close):
            self.assertEqual(self.worker(),1)
        report=self.report()
        self.assertEqual((self.lifecycle.starts,self.episodes),(0,0))
        self.assertEqual(report['status'],'unresolved')
        self.assertIn('acquisition close failure',report['immutableHandleCleanupError'])
        self.code.write_bytes(self.code.read_bytes())

    def test_held_empty_declared_source_remains_compatible(self):
        (self.model_source/'__init__.py').write_bytes(b'')
        self.begin();self.assertEqual(self.worker(),0,self.report())
        self.assert_retired(started=True)


def load_tests(loader, tests, pattern):
    """Run only this focused cohort, not the inherited unrelated historical test suite."""
    suite=unittest.TestSuite()
    for cls in (HeldFileTests,OwnerClosureTests):suite.addTests(loader.loadTestsFromTestCase(cls))
    for name in loader.getTestCaseNames(WorkerHeldTests):
        if name.startswith('test_held_'):suite.addTest(WorkerHeldTests(name))
    return suite


if __name__=='__main__':unittest.main(verbosity=2)
