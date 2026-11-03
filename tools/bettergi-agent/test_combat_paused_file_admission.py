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


    def _metadata_budget(self, sizes, expected_error=None):
        """Exercise real acquisition/cleanup with tiny files and virtual stat sizes, not large byte allocations.

        Only this budget fixture substitutes the final content verifier. The existing tests above
        exercise actual hash, identity, sharing, parent, STOP and private-admission checks.
        """
        folder=self.folder/'budget';folder.mkdir(exist_ok=True)
        paths=[folder/('%04d.json' % index) for index in range(len(sizes))]
        for path in paths:path.write_bytes(b'x')
        pins={str(path):hashlib.sha256(b'x').hexdigest() for path in paths}
        metadata={str(path):size for path,size in zip(paths,sizes)}
        original_open=open;original_fstat=os.fstat;opened=[];by_fd={};files=None
        def opened_file(name,*args,**kwargs):
            """Keep every real stream available for the partial-retirement assertion."""
            stream=original_open(name,*args,**kwargs);opened.append(stream)
            by_fd[stream.fileno()]=metadata[str(name)]
            return stream
        def sized_fstat(fd):
            """Change only the reported size for the aggregate/per-file admission boundaries."""
            info=list(original_fstat(fd));info[6]=by_fd[fd]
            return os.stat_result(info)
        try:
            with patch('builtins.open',opened_file),patch.object(held.os,'fstat',side_effect=sized_fstat), \
                    patch.object(held.HeldFiles,'verify',return_value=({},sum(sizes))) as verify:
                if expected_error:
                    with self.assertRaisesRegex(ValueError,expected_error):held.HeldFiles(pins)
                    verify.assert_not_called()
                else:
                    files=held.HeldFiles(pins)
                    self.assertEqual(len(files.rows),len(sizes))
                    self.assertEqual(sum(row[1][2] for row in files.rows.values()),sum(sizes))
                    verify.assert_called_once_with()
        finally:
            if files is not None:self.assertEqual(files.close(),[])
        self.assertTrue(opened)
        self.assertTrue(all(stream.closed for stream in opened))
        paths[0].write_bytes(b'retired');paths[-1].write_bytes(b'retired')

    def test_measured_r73_run39_budget_shape_and_old_cap_refusal(self):
        """Retain the real count/group totals and sixteen DLL sizes without depending on live artifacts."""
        def partition(total,count):
            """Model only aggregate-size accounting; small within-group distributions are immaterial."""
            size,remainder=divmod(total,count)
            return [size+1]*remainder+[size]*(count-remainder)
        dll_sizes=[20913152, 20914688, 20843008, 20848640, 20856320, 20882944, 20883968, 20884480, 20912128, 20913152, 20913152, 20913152, 20913152, 20913152, 20913152, 20913152]
        sizes=dll_sizes+[305152]*16+partition(538904,97)
        sizes+=partition(6003463,369)*2+partition(959640,8)+partition(74810524,934)
        self.assertEqual((len(sizes),sum(sizes)),(1809,427529818))
        self.assertEqual(held.MAX_FILES,2304)
        self.assertEqual(held.MAX_FILE_BYTES,32*1024*1024)
        self.assertEqual(held.MAX_TOTAL_BYTES,448*1024*1024)
        with patch.object(held,'MAX_TOTAL_BYTES',384*1024*1024):
            self._metadata_budget(sizes,'Immutable file byte budget exceeded')
        self._metadata_budget(sizes)

    def test_exact_aggregate_cap_and_one_byte_excess_retire_all_handles(self):
        """Accept the precise 448 MiB boundary; reject its next byte before content verification."""
        sizes=[32*1024*1024]*14
        self.assertEqual(sum(sizes),held.MAX_TOTAL_BYTES)
        self._metadata_budget(sizes)
        self._metadata_budget(sizes+[1],'Immutable file byte budget exceeded')

    def test_per_file_cap_is_not_relaxed_by_aggregate_increase(self):
        """The unchanged 32 MiB individual-file ceiling still retires the just-opened stream."""
        self._metadata_budget([1,32*1024*1024+1],'unbounded immutable file')

    def test_fresh_real_byte_read_still_enforces_aggregate_cap(self):
        """Fresh verification uses the same ceiling and preserves real digest/identity checks."""
        self.files=held.HeldFiles(self.pins)
        actual,total=self.files.verify()
        self.assertEqual(actual,self.pins)
        with patch.object(held,'MAX_TOTAL_BYTES',total-1):
            with self.assertRaisesRegex(ValueError,'Immutable file byte budget changed'):self.files.verify()
        self.assertEqual(self.files.close(),[])
        self.a.write_bytes(b'released after verify refusal')


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

    def verify_reader_set(self, expected_packages=11):
        """Require every actual immutable validator read to appear in the held census."""
        owner,pins,packages=held.owner_inputs(self.path,map_owner.ARTIFACTS,map_owner.load_map_owner)
        observed=set();original=Path.open
        def read_trace(path,*args,**kwargs):
            mode=args[0] if args else kwargs.get('mode','r')
            self.assertIn('r',mode);observed.add(str(path.absolute()))
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',read_trace):actual=map_owner.load_map_owner(self.path)
        self.assertEqual(actual,owner);self.assertEqual(observed,set(pins))
        self.assertEqual(len(packages),expected_packages)
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


    def append_r69(self):
        """Extend the existing synthetic R68 receipt with one exact English R69 handoff."""
        prior=self.path
        game=json.loads(prior.read_bytes())['protectedGame']
        folder,result=self.fixture.create_next_handoff(prior,self.result,game,69)
        build,_=map_owner.target_package(69)
        owner_fixtures.write(Path(build['targetDirectory'])/'User/config.json',map_owner.R62_CLEAN_CAPTURE)
        config_sha=map_owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=config_sha
        result['replacementEvidence']['existingTargetConfigSha256']=config_sha
        owner_fixtures.write(folder/'preflight.json',preflight)
        owner_fixtures.write(folder/'ensure-child.json',result)
        self.prior,self.folder,self.result=prior,folder,result
        self.path=folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,folder))

    def test_r69_complete_reader_set_is_held(self):
        """All twelve packages and every actual immutable owner read belong to the held census."""
        self.append_r69()
        _,pins,_=self.verify_reader_set(expected_packages=12)
        self.assertEqual(len(pins),97)

    def test_r69_retained_endpoints_and_selection_remain_bound(self):
        """R68/R69 witnesses preserve exact replay; later original-path reappearance still refuses."""
        self.append_r69()
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(68,69))
        owner,pins,packages=self.verify_reader_set(expected_packages=12)
        missing=map_owner.ARTIFACTS/'release-r68'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])

    def test_r69_missing_game_evidence_refuses_before_validation(self):
        """A missing newest game-lifetime document cannot be replaced by an already-known owner."""
        self.append_r69()
        (self.folder/'game-before.json').unlink()
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaises(FileNotFoundError):
                held.owner_inputs(self.path,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()

    def append_r70(self):
        """Extend the existing synthetic R69 receipt with one exact English R70 handoff."""
        self.append_r69()
        prior=self.path
        game=json.loads(prior.read_bytes())['protectedGame']
        folder,result=self.fixture.create_next_handoff(prior,self.result,game,70)
        build,_=map_owner.target_package(70)
        owner_fixtures.write(Path(build['targetDirectory'])/'User/config.json',map_owner.R62_CLEAN_CAPTURE)
        config_sha=map_owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=config_sha
        result['replacementEvidence']['existingTargetConfigSha256']=config_sha
        owner_fixtures.write(folder/'preflight.json',preflight)
        owner_fixtures.write(folder/'ensure-child.json',result)
        self.prior,self.folder,self.result=prior,folder,result
        self.path=folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,folder))

    def test_r70_complete_reader_set_is_held(self):
        """All thirteen packages and every actual immutable owner read belong to the held census."""
        self.append_r70()
        _,pins,_=self.verify_reader_set(expected_packages=13)
        self.assertEqual(len(pins),105)

    def test_r70_retained_endpoints_and_selection_remain_bound(self):
        """R69/R70 witnesses preserve exact replay; later original-path reappearance still refuses."""
        self.append_r70()
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(69,70))
        owner,pins,packages=self.verify_reader_set(expected_packages=13)
        missing=map_owner.ARTIFACTS/'release-r69'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])

    def test_r70_missing_game_evidence_refuses_before_validation(self):
        """A missing newest game-lifetime document cannot be replaced by an already-known owner."""
        self.append_r70()
        (self.folder/'game-before.json').unlink()
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaises(FileNotFoundError):
                held.owner_inputs(self.path,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()

    def test_r70_scope_rejects_r74_before_validation(self):
        """A historical R70 chain cannot select an out-of-scope later package."""
        self.append_r70()
        game=json.loads(self.path.read_bytes())['protectedGame']
        later,_=self.fixture.create_next_handoff(self.path,self.result,game,74)
        future=later/'map-owner-lineage.json'
        owner_fixtures.write(future,dict(prior=str(self.path),protectedGame=game))
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaisesRegex(ValueError,'package scope'):
                held.owner_inputs(future,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


    def append_r71(self):
        """Extend the existing synthetic R70 receipt with one exact English R71 handoff."""
        self.append_r70()
        prior=self.path
        game=json.loads(prior.read_bytes())['protectedGame']
        folder,result=self.fixture.create_next_handoff(prior,self.result,game,71)
        build,_=map_owner.target_package(71)
        owner_fixtures.write(Path(build['targetDirectory'])/'User/config.json',map_owner.R62_CLEAN_CAPTURE)
        config_sha=map_owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=config_sha
        result['replacementEvidence']['existingTargetConfigSha256']=config_sha
        owner_fixtures.write(folder/'preflight.json',preflight)
        owner_fixtures.write(folder/'ensure-child.json',result)
        self.prior,self.folder,self.result=prior,folder,result
        self.path=folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,folder))


    def test_r71_complete_reader_set_is_held(self):
        """All fourteen packages and every actual immutable owner read belong to the held census."""
        self.append_r71()
        _,pins,_=self.verify_reader_set(expected_packages=14)
        self.assertEqual(len(pins),113)


    def test_r71_retained_endpoints_and_selection_remain_bound(self):
        """R70/R71 witnesses preserve exact replay; later original-path reappearance still refuses."""
        self.append_r71()
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(70,71))
        owner,pins,packages=self.verify_reader_set(expected_packages=14)
        missing=map_owner.ARTIFACTS/'release-r70'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])


    def test_r71_missing_game_evidence_refuses_before_validation(self):
        """A missing newest game-lifetime document cannot be replaced by an already-known owner."""
        self.append_r71()
        (self.folder/'game-before.json').unlink()
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaises(FileNotFoundError):
                held.owner_inputs(self.path,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


    def test_r71_scope_rejects_r74_before_validation(self):
        """A historical R71 chain still cannot select an unknown later package."""
        self.append_r71()
        game=json.loads(self.path.read_bytes())['protectedGame']
        later,_=self.fixture.create_next_handoff(self.path,self.result,game,74)
        future=later/'map-owner-lineage.json'
        owner_fixtures.write(future,dict(prior=str(self.path),protectedGame=game))
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaisesRegex(ValueError,'package scope'):
                held.owner_inputs(future,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


    def append_r72(self):
        """Extend the existing synthetic R71 receipt with one exact English R72 handoff."""
        self.append_r71()
        prior=self.path
        game=json.loads(prior.read_bytes())['protectedGame']
        folder,result=self.fixture.create_next_handoff(prior,self.result,game,72)
        build,_=map_owner.target_package(72)
        owner_fixtures.write(Path(build['targetDirectory'])/'User/config.json',map_owner.R62_CLEAN_CAPTURE)
        config_sha=map_owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=config_sha
        result['replacementEvidence']['existingTargetConfigSha256']=config_sha
        owner_fixtures.write(folder/'preflight.json',preflight)
        owner_fixtures.write(folder/'ensure-child.json',result)
        self.prior,self.folder,self.result=prior,folder,result
        self.path=folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,folder))


    def test_r72_complete_reader_set_is_held(self):
        """All fifteen packages and every actual immutable owner read belong to the held census."""
        self.append_r72()
        _,pins,_=self.verify_reader_set(expected_packages=15)
        self.assertEqual(len(pins),121)


    def test_r72_retained_endpoints_and_selection_remain_bound(self):
        """R71/R72 witnesses preserve exact replay; later original-path reappearance still refuses."""
        self.append_r72()
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(71,72))
        owner,pins,packages=self.verify_reader_set(expected_packages=15)
        missing=map_owner.ARTIFACTS/'release-r71'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])


    def test_r72_missing_game_evidence_refuses_before_validation(self):
        """A missing newest game-lifetime document cannot be replaced by an already-known owner."""
        self.append_r72()
        (self.folder/'game-before.json').unlink()
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaises(FileNotFoundError):
                held.owner_inputs(self.path,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


    def test_r72_scope_rejects_r75_before_validation(self):
        """A historical R72 chain still cannot select an unknown later package."""
        self.append_r72()
        game=json.loads(self.path.read_bytes())['protectedGame']
        later,_=self.fixture.create_next_handoff(self.path,self.result,game,75)
        future=later/'map-owner-lineage.json'
        owner_fixtures.write(future,dict(prior=str(self.path),protectedGame=game))
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaisesRegex(ValueError,'package scope'):
                held.owner_inputs(future,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


    def append_r73(self):
        """Extend the existing synthetic R72 receipt with one exact English R73 handoff."""
        self.append_r72()
        prior=self.path
        game=json.loads(prior.read_bytes())['protectedGame']
        folder,result=self.fixture.create_next_handoff(prior,self.result,game,73)
        result['child'].update(configuredTriggerPolicyVersion=1, configuredTriggersSuppressed=True)
        build,_=map_owner.target_package(73)
        owner_fixtures.write(Path(build['targetDirectory'])/'User/config.json',map_owner.R62_CLEAN_CAPTURE)
        config_sha=map_owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=config_sha
        result['replacementEvidence']['existingTargetConfigSha256']=config_sha
        owner_fixtures.write(folder/'preflight.json',preflight)
        owner_fixtures.write(folder/'ensure-child.json',result)
        self.prior,self.folder,self.result=prior,folder,result
        self.path=folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,folder))


    def test_r73_complete_reader_set_is_held(self):
        """All sixteen packages and every actual immutable owner read belong to the held census."""
        self.append_r73()
        _,pins,_=self.verify_reader_set(expected_packages=16)
        self.assertEqual(len(pins),129)


    def test_r73_retained_endpoints_and_selection_remain_bound(self):
        """R72/R73 witnesses preserve exact replay; later original-path reappearance still refuses."""
        self.append_r73()
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(72,73))
        owner,pins,packages=self.verify_reader_set(expected_packages=16)
        missing=map_owner.ARTIFACTS/'release-r72'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])


    def test_r73_missing_game_evidence_refuses_before_validation(self):
        """A missing newest game-lifetime document cannot be replaced by an already-known owner."""
        self.append_r73()
        (self.folder/'game-before.json').unlink()
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaises(FileNotFoundError):
                held.owner_inputs(self.path,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


    def test_r74_scope_rejects_r75_and_eighteenth_link_before_validation(self):
        """The collector independently refuses a later package and an extra otherwise-shaped link."""
        self.append_r74()
        game=json.loads(self.path.read_bytes())['protectedGame']
        later,_=self.fixture.create_next_handoff(self.path,self.result,game,75)
        future=later/'map-owner-lineage.json'
        owner_fixtures.write(future,dict(prior=str(self.path),protectedGame=game))
        extra=self.folder.parent/'excess-link'
        for name in ('before.json','preflight.json','ensure-child.json','game-before.json'):
            owner_fixtures.write(extra/name,json.loads((self.folder/name).read_bytes()))
        overlong=extra/'map-owner-lineage.json'
        owner_fixtures.write(overlong,dict(prior=str(self.path),protectedGame=game))
        for path,message in ((future,'package scope'),(overlong,'finite lineage')):
            with self.subTest(path=path),patch.object(map_owner,'load_map_owner') as validate:
                with self.assertRaisesRegex(ValueError,message):
                    held.owner_inputs(path,map_owner.ARTIFACTS,validate)
                validate.assert_not_called()





    def append_r74(self):
        """Extend the existing synthetic R73 receipt with one exact English R74 handoff."""
        self.append_r73()
        prior=self.path
        game=json.loads(prior.read_bytes())['protectedGame']
        folder,result=self.fixture.create_next_handoff(prior,self.result,game,74)
        result['child'].update(configuredTriggerPolicyVersion=1, configuredTriggersSuppressed=True)
        build,_=map_owner.target_package(74)
        owner_fixtures.write(Path(build['targetDirectory'])/'User/config.json',map_owner.R62_CLEAN_CAPTURE)
        config_sha=map_owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=config_sha
        result['replacementEvidence']['existingTargetConfigSha256']=config_sha
        owner_fixtures.write(folder/'preflight.json',preflight)
        owner_fixtures.write(folder/'ensure-child.json',result)
        self.prior,self.folder,self.result=prior,folder,result
        self.path=folder/'map-owner-lineage.json'
        owner_fixtures.write(self.path,map_owner.replacement(prior,folder))


    def test_r74_complete_reader_set_is_held(self):
        """All seventeen packages and every actual immutable owner read belong to the held census."""
        self.append_r74()
        _,pins,_=self.verify_reader_set(expected_packages=17)
        self.assertEqual(len(pins),137)


    def test_r74_retained_endpoints_and_selection_remain_bound(self):
        """R73/R74 witnesses preserve exact replay; later original-path reappearance still refuses."""
        self.append_r74()
        self.fixture.check_source_and_target_witnesses(self.prior,self.folder,self.result,(73,74))
        owner,pins,packages=self.verify_reader_set(expected_packages=17)
        missing=map_owner.ARTIFACTS/'release-r73'
        self.assertFalse(packages[str(missing)]['originalPresent'])
        report={};context={'owner':owner}
        cap=held.PausedAdmission(context,pins,(),lambda:[],[],packages,report)
        try:
            missing.mkdir()
            with self.assertRaisesRegex(ValueError,'package selection'):
                cap.consume(lambda:context,report,lambda:None)
        finally:self.assertEqual(cap.close(),[])


    def test_r74_missing_game_evidence_refuses_before_validation(self):
        """A missing newest game-lifetime document cannot be replaced by an already-known owner."""
        self.append_r74()
        (self.folder/'game-before.json').unlink()
        with patch.object(map_owner,'load_map_owner') as validate:
            with self.assertRaises(FileNotFoundError):
                held.owner_inputs(self.path,map_owner.ARTIFACTS,validate)
            validate.assert_not_called()


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
