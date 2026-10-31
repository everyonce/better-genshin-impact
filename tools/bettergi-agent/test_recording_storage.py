"""Inert storage corruption, exact-byte recovery and physical-budget tests; no game or model."""
import copy
from contextlib import ExitStack, redirect_stdout
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

import policy_rgb_archive as archive
import stream_client as client
import test_policy_rgb_archive as rgb_tests
from test_recorder_metadata import MemoryEncoder, observed_frame
from test_stream_client import HeldRecorder


def digest(raw):
    """Keep encoded-byte mutations independent of decoded-byte checks in adversarial fixtures."""
    return hashlib.sha256(raw).hexdigest()


def journal_fixture(directory, *, events=None):
    """Write genuine v2 gzip streams and their original final seal without a controller."""
    rows = {
        'events.jsonl': events if events is not None else [
            {'type':'episodeStart','recordingFormat':archive.RECORDING_FORMAT},
            {'type':'scoutEncounterGuardObservation','frame':{'frameId':9,'serverNowMs':12.5,
                'groundControlEvidence':{'crops':[{'rgbBase64':'AAEC','sha256':digest(b'\0\1\2')}]}}},
            {'type':'scoutEncounterGuardObservation','frame':{'frameId':9,'serverNowMs':13.5}},
            {'type':'scoutEncounterGuardRelease','reason':'sensor-failure','response':{'type':'released'}}],
        'frames.jsonl':[{'frameId':9,'videoFrameIndex':0}],
        'observations.jsonl':[{'frameId':9,'clientReceivedNs':100},{'frameId':9,'clientReceivedNs':200}],
    }
    references={}
    for name,items in rows.items():
        with archive.RecordingJournal(directory,name) as writer:
            for row in items:writer.write(json.dumps(row,separators=(',',':'))+'\n')
            writer.flush()
        references[name]=writer.reference()
    seal=dict(recordingFormat=archive.RECORDING_FORMAT,journalFiles=references,policyRgbStoredBytes=0)
    (Path(directory)/'recording.json').write_text(json.dumps(seal),encoding='utf-8')
    return rows,seal


class RecordingStorageTests(unittest.TestCase):
    def test_forward_preparation_cannot_create_a_reserved_gzip_file_in_raw_evidence(self):
        """An export must not introduce a compressed-name collision that invalidates a raw recording."""
        import prepare_replay_forward as forward
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);record=root/'recording';record.mkdir()
            raw=record/'frames.jsonl';raw.write_bytes(b'{}\n')
            output=record/'frames.jsonl.gz'
            with self.assertRaisesRegex(forward.base.EvidenceError,'output_would_overwrite_evidence'):
                forward.main(['--report',str(root/'report.json'),'--recording-dir',str(record),
                    '--output',str(output),'--probe-frame-id','1'])
            self.assertFalse(output.exists())
            self.assertEqual(raw.read_bytes(),b'{}\n')

    """Exercise both formats and malformed encoded evidence under strict decode bounds."""
    def test_raw_jsonl_keeps_original_hash_and_order_without_a_new_declaration(self):
        with tempfile.TemporaryDirectory() as folder:
            raw=b'{"frameId":9}\r\n{"frameId":9,"unavailable":true}\r\n'
            (Path(folder)/'observations.jsonl').write_bytes(raw)
            rows,sha=archive.read_recording_jsonl(folder,'observations.jsonl')
            self.assertEqual(rows,[{'frameId':9},{'frameId':9,'unavailable':True}])
            self.assertEqual(sha,digest(raw))
            self.assertEqual(archive.recording_journal_path(folder,'observations.jsonl').suffix,'.jsonl')

    def test_compressed_rows_preserve_duplicate_sources_crops_and_release_order(self):
        with tempfile.TemporaryDirectory() as folder:
            expected,seal=journal_fixture(folder)
            for name,rows in expected.items():
                actual,sha=archive.read_recording_jsonl(folder,name)
                self.assertEqual(actual,rows)
                self.assertEqual(sha,seal['journalFiles'][name]['sha256'])
                with archive.open_recording_jsonl(Path(folder)/name) as source:
                    self.assertEqual([json.loads(line) for line in source],rows)
            self.assertEqual(archive.recording_metadata(folder,seal),seal)

    def test_removed_changed_or_mixed_declarations_are_not_historical_fallbacks(self):
        for change in ('removed','unknown','report','mixed','missingJournal'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                _,seal=journal_fixture(folder)
                altered=copy.deepcopy(seal)
                if change=='removed':altered.pop('recordingFormat')
                elif change=='unknown':altered['recordingFormat']='gzip-jsonl-png-rgb-v3'
                elif change=='report':altered['policyRgbStoredBytes']=1
                elif change=='mixed':(Path(folder)/'events.jsonl').write_text('{}\n')
                else:altered['journalFiles'].pop('events.jsonl')
                if change!='report':(Path(folder)/'recording.json').write_text(json.dumps(altered))
                with self.assertRaises(ValueError):
                    archive.recording_metadata(folder,altered if change=='report' else None)

    def test_plain_journal_cannot_hide_retained_new_format_markers(self):
        for name,row in (('events.jsonl',{'type':'episodeStart','recordingFormat':archive.RECORDING_FORMAT}),
                         ('frames.jsonl',{'frameId':1,'policyRgb':{'encoding':archive.PNG_ENCODING}})):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                (Path(folder)/name).write_text(json.dumps(row)+'\n')
                with self.assertRaises(ValueError):archive.read_recording_jsonl(folder,name)
                with self.assertRaises(ValueError):archive.open_recording_jsonl(Path(folder)/name)

    def test_gzip_encoded_decoded_hashes_crc_footer_and_extra_members_are_checked(self):
        for change in ('encodedHash','decodedHash','crc','truncated','member','expansion','rows'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                _,seal=journal_fixture(folder)
                reference=seal['journalFiles']['events.jsonl']
                path=Path(folder)/reference['file']
                raw=path.read_bytes()
                if change=='encodedHash':reference['storedSha256']='0'*64
                elif change=='decodedHash':reference['sha256']='0'*64
                elif change=='rows':reference['rows']+=1
                else:
                    if change=='crc':raw=raw[:-8]+bytes([raw[-8]^1])+raw[-7:]
                    elif change=='truncated':raw=raw[:-4]
                    elif change=='member':raw+=gzip.compress(b'')
                    else:raw=gzip.compress(b'A'*4096);reference['bytes']=1
                    path.write_bytes(raw)
                    reference.update(storedBytes=len(raw),storedSha256=digest(raw))
                (Path(folder)/'recording.json').write_text(json.dumps(seal))
                with self.assertRaises(ValueError):
                    archive.read_recording_jsonl(folder,'events.jsonl',max_decoded_bytes=1024)

    def test_row_and_decode_bounds_precede_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            journal_fixture(folder)
            with self.assertRaises(ValueError):archive.read_recording_jsonl(folder,'events.jsonl',max_rows=2)
            with self.assertRaises(ValueError):archive.read_recording_jsonl(folder,'events.jsonl',max_decoded_bytes=20)

    def test_valid_crop_rich_journal_can_exceed_32_mib_within_the_64_mib_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            payload='X'*32768
            expected=[{'frameId':index,'payload':payload} for index in range(1025)]
            _,seal=journal_fixture(folder,events=expected)
            self.assertGreater(seal['journalFiles']['events.jsonl']['bytes'],32*1024*1024)
            rows,sha=archive.read_recording_jsonl(folder,'events.jsonl')
            self.assertEqual(rows,expected)
            self.assertEqual(sha,seal['journalFiles']['events.jsonl']['sha256'])
            with self.assertRaises(ValueError):
                archive.read_recording_jsonl(folder,'events.jsonl',max_decoded_bytes=32*1024*1024)

    def test_episode_start_must_declare_the_new_transport(self):
        from experience_manifest import rows as experience_rows
        for declaration in ({},{'recordingFormat':'raw-v1'}):
            with self.subTest(declaration=declaration),tempfile.TemporaryDirectory() as folder:
                journal_fixture(folder,events=[dict(type='episodeStart',**declaration)])
                with self.assertRaisesRegex(ValueError,'Initial episode'):
                    archive.read_recording_jsonl(folder,'events.jsonl')
                with self.assertRaisesRegex(ValueError,'Initial episode'):
                    archive.open_recording_jsonl(Path(folder)/'events.jsonl')
                with self.assertRaisesRegex(ValueError,'Initial episode'):
                    list(experience_rows(Path(folder)/'events.jsonl'))

    def test_raw_path_abi_and_png_exact_bytes_remain_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            pixels=bytes(range(256))*(archive.RGB192_BYTES//256)
            raw=archive.write_policy_rgb(folder,0,dict(frameId=4,width=192,height=192),pixels)
            png=archive.write_policy_rgb(folder,1,dict(frameId=5,width=192,height=192),pixels,encoding=archive.PNG_ENCODING)
            self.assertEqual(archive.verify_policy_rgb(folder,raw).read_bytes(),pixels)
            self.assertEqual(archive.read_policy_rgb(folder,png,index=1,frame_id=5),pixels)
            self.assertLess(png['storedBytes'],png['bytes'])
            self.assertNotEqual(png['sha256'],png['storedSha256'])
            with self.assertRaisesRegex(ValueError,'read_policy_rgb'):archive.verify_policy_rgb(folder,png)
            with self.assertRaisesRegex(ValueError,'filename'):archive.read_policy_rgb(folder,png,index=0,frame_id=5)

    def test_png_corruption_wrong_geometry_extra_bytes_and_decode_expansion_refuse(self):
        def chunk(kind,raw):
            """Construct valid CRCs so malformed semantics reach the bounded PNG validator."""
            return struct.pack('>I',len(raw))+kind+raw+struct.pack('>I',zlib.crc32(kind+raw)&0xffffffff)
        for change in ('encodedHash','decodedHash','crc','truncated','trailing','geometry','expansion'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                reference=archive.write_policy_rgb(folder,0,dict(frameId=1,width=192,height=192),
                    bytes(archive.RGB192_BYTES),encoding=archive.PNG_ENCODING)
                path=Path(folder)/reference['file'];raw=path.read_bytes()
                if change=='encodedHash':reference['storedSha256']='0'*64
                elif change=='decodedHash':reference['sha256']='0'*64
                else:
                    if change=='crc':raw=raw[:-1]+bytes([raw[-1]^1])
                    elif change=='truncated':raw=raw[:-5]
                    elif change=='trailing':raw+=b'ignored-data'
                    else:
                        width=193 if change=='geometry' else 192
                        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,192,8,2,0,0,0))
                        raw+=chunk(b'IDAT',zlib.compress(bytes(archive.RGB192_BYTES*2)))+chunk(b'IEND',b'')
                    path.write_bytes(raw);reference.update(storedBytes=len(raw),storedSha256=digest(raw))
                with self.assertRaises(ValueError):archive.read_policy_rgb(folder,reference)

    def test_png_cannot_be_attached_to_an_undeclared_historical_seal(self):
        with tempfile.TemporaryDirectory() as folder:
            reference=archive.write_policy_rgb(folder,0,dict(frameId=1,width=192,height=192),
                bytes(archive.RGB192_BYTES),encoding=archive.PNG_ENCODING)
            with self.assertRaisesRegex(ValueError,'recording declaration'):
                archive.read_policy_rgb(folder,reference,index=0,frame_id=1,recording={})

    def test_writer_charges_stored_bytes_even_when_logical_rgb_exceeds_budget(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(client.subprocess,'Popen',return_value=MemoryEncoder()):
            recorder,result,pixels=rgb_tests.PolicyRgbTests().record(folder,budget=8192)
            self.assertTrue(result['complete'] and result['lossless'],result)
            self.assertGreater(result['policyRgbBytes'],8192)
            self.assertLess(result['recordedBytes'],8192)
            self.assertEqual(result['recordedBytes'],sum(path.stat().st_size for path in recorder.directory.iterdir()
                if path.name!='recording.json'))
            self.assertEqual(result['policyRgbBytes'],2*len(pixels))

    def test_writer_failure_finalizes_handles_and_never_claims_completion(self):
        original=archive.RecordingJournal.close
        def broken_close(journal):
            """Close the real descriptor first, then emulate a footer durability failure."""
            original(journal)
            if journal.name=='events.jsonl.gz':raise OSError('injected journal footer failure')
        with tempfile.TemporaryDirectory() as folder,patch.object(archive.RecordingJournal,'close',broken_close):
            recorder=HeldRecorder(Path(folder)/'episode','unused',20,1024*1024)
            recorder.event({'type':'episodeStart'})
            recorder.release_writer.set()
            result=recorder.close()
            self.assertFalse(result['complete'])
            self.assertTrue(result['closed'] and result['workerRetired'])
            self.assertIn('injected journal footer failure',result['error'])
            self.assertEqual(archive.read_recording_jsonl(recorder.directory,'events.jsonl')[0][0]['recordingFormat'],
                             archive.RECORDING_FORMAT)

    def test_compressed_continuous_cli_keeps_physical_pins_and_logical_memory_bound(self):
        import prepare_replay_session as session
        from test_prepare_replay_session import save_fixture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            segments=save_fixture(root)
            physical=logical=0
            for segment in segments:
                directory=segment.recording_dir
                references={}
                originals={name:archive.read_recording_jsonl(directory,name)[0] for name in archive.JOURNAL_NAMES}
                for name in archive.JOURNAL_NAMES:
                    rows=originals[name]
                    with archive.RecordingJournal(directory,name) as writer:
                        for row in rows:
                            if row.get('type')=='episodeStart':row['recordingFormat']=archive.RECORDING_FORMAT
                            writer.write(json.dumps(row)+'\n')
                    references[name]=writer.reference()
                    (directory/name).unlink()
                seal=dict(segment.recording,recordingFormat=archive.RECORDING_FORMAT,
                          journalFiles=references,policyRgbStoredBytes=0)
                (directory/'recording.json').write_text(json.dumps(seal))
                if 'recording' in segment.report:
                    segment.report['recording'].update(recordingFormat=archive.RECORDING_FORMAT,
                                                       journalFiles=references,policyRgbStoredBytes=0)
                    segment.report_path.write_text(json.dumps(segment.report))
                fixed=segment.report_path.stat().st_size+(directory/'recording.json').stat().st_size
                physical+=fixed+sum(reference['storedBytes'] for reference in references.values())
                logical+=fixed+sum(reference['bytes'] for reference in references.values())
            args=['--reports-dir',str(root/'reports'),'--recordings-dir',str(root/'recordings'),
                  '--history-frames','4','--max-windows','1','--probe-frame-id','14','--output',str(root/'prepared.json')]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(session.main(args),0)
            result=json.loads((root/'prepared.json').read_bytes())
            self.assertEqual(result['windows'][0]['probe']['videoFrameIndex'],1)
            for name,pin in result['inputEvidence'].items():
                if name.endswith('.jsonl'):
                    self.assertTrue(pin['path'].endswith('.jsonl.gz'))
                    self.assertEqual(pin['sha256'],digest(Path(pin['path']).read_bytes()))
            self.assertGreater(logical,physical+1)
            with patch.object(session,'MAX_JSON_BYTES',physical+1),redirect_stdout(io.StringIO()):
                self.assertEqual(session.main(args[:-1]+[str(root/'too-small.json')]),2)
            self.assertIn('metadata_memory_bound_exceeded',json.loads((root/'too-small.json').read_bytes())['errors'])


class CompressedLoopTests(unittest.TestCase):
    """Replay the production stream loop and real compressed writer with inert native/model boundaries."""
    def run_loop(self, folder, *, combat=False, hold=50, fail_encoding=False, state=None):
        """Keep real PIL/PNG and recorder threads; replace only the bridge, policy and viewing encoder."""
        from test_combat_trial_stream import CombatTrialStreamTests,TrialBridge,TrialPolicy
        from test_p2p_executed_history_stream import HistoryBridge,HistoryPolicy,inert_arguments
        from test_resident_goals import dormant_control
        from scout_encounter_guard import ScoutEncounterGuard
        from test_scout_encounter_guard import binding
        folder=Path(folder)
        args=CombatTrialStreamTests().arguments(folder) if combat else inert_arguments(folder,hold=hold)
        # Use the deployed capture/decision cadence rather than the older memory-only fixture's 100 Hz.
        args.fps,args.decision_hz,args.seconds=20,10,3
        record=folder/'recording'/'00001'
        args.record_dir=str(record)
        control=dormant_control(folder,frozen_goal=True)
        control.set_initial_goal(dict(instruction='fixed combat' if combat else 'fixed scout'),
                                 'stationary' if combat else 'ground-navigation')
        if not combat:control.scout_encounter_guard=ScoutEncounterGuard(binding())
        bridge=TrialBridge() if combat else HistoryBridge()
        encode_failure,writer_failed=threading.Event(),threading.Event()
        def during_predict():
            """Force an actual asynchronous encoder failure while the model boundary is in flight."""
            encode_failure.set()
            if not writer_failed.wait(2):raise AssertionError('Writer failed to observe the injected encoding failure')
        policy=TrialPolicy() if combat else HistoryPolicy(during_predict if fail_encoding else None)
        actual_write=archive.write_policy_rgb
        def encode(*arguments,**keywords):
            """Refuse only a later writer-side PNG, after prediction has begun."""
            if encode_failure.is_set():raise OSError('injected PNG encoding failure')
            return actual_write(*arguments,**keywords)
        with ExitStack() as stack:
            stack.enter_context(patch.object(client.subprocess,'Popen',return_value=MemoryEncoder()))
            if fail_encoding:stack.enter_context(patch.object(archive,'write_policy_rgb',side_effect=encode))
            recorder=client.AsyncVideoRecorder(record,'inert-encoder',args.fps,160*1024*1024,
                                                frame_capacity=32,retain_policy_rgb=True)
            original_fail=recorder.fail
            def fail(reason):
                """Expose the real recorder's sticky failure only after its state is visible."""
                original_fail(reason)
                writer_failed.set()
            recorder.fail=fail
            if state is not None:state.update(recorder=recorder,bridge=bridge,policy=policy)
            stack.enter_context(patch.object(client,'Bridge',return_value=bridge))
            stack.enter_context(patch.object(client,'AsyncVideoRecorder',return_value=recorder))
            stack.enter_context(patch('resident_runtime.verify_bridge_identity'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            try:result=client.run_episode(args,policy,control)
            finally:recorder.close()
        report=json.loads((folder/'run.json').read_bytes())
        events=archive.read_recording_jsonl(record,'events.jsonl')[0]
        frames=archive.read_recording_jsonl(record,'frames.jsonl')[0]
        return result,report,events,frames,record,bridge,policy

    def test_compressed_actual_scout_loop_replays_fifty_and_sixty_ms_commits(self):
        from audit_hybrid_run import verify_executed_history,EXECUTED_HISTORY_MODE
        for hold in (50,60):
            with self.subTest(hold=hold),tempfile.TemporaryDirectory() as folder:
                code,part,events,frames,record,bridge,policy=self.run_loop(folder,hold=hold)
                self.assertEqual((code,part['status']),(0,'completed'))
                observations=archive.read_recording_jsonl(record,'observations.jsonl')[0]
                by_frame={row['frameId']:row for row in observations}
                result=verify_executed_history(part,[part],by_frame,[dict(number=1)],record.parent,
                    dict(historyCommitMode=EXECUTED_HISTORY_MODE,actionHoldMs=hold))
                self.assertEqual((result['committedActions'],result['finalHistoryFrames']),(3,3))
                self.assertEqual(len(bridge.actions),len(policy.commits))
                for index,row in enumerate(frames):
                    self.assertEqual(archive.read_policy_rgb(record,row['policyRgb'],index=index,
                        frame_id=row['frameId'],recording=part['recording']),bridge.pixels)
                self.assertTrue(part['recording']['complete'] and part['recording']['lossless'])

    def test_compressed_actual_combat_loop_replays_all_pulses_and_terminal_pixels(self):
        from audit_combat_trial import audit_episode
        with tempfile.TemporaryDirectory() as folder:
            code,part,events,frames,record,bridge,_=self.run_loop(folder,combat=True)
            self.assertEqual((code,len(bridge.actions)),(0,3))
            result=audit_episode(part,events,frames,record,part['combatTrialGuard'])
            self.assertTrue(result['trialCompleteVerified'])
            self.assertEqual(result['verifiedRgbFrames'],part['recording']['policyRgbFrames'])
            original=copy.deepcopy(part['recording'])
            part['recording']['policyRgbStoredBytes']+=1
            with self.assertRaisesRegex(ValueError,'seal differs'):
                audit_episode(part,events,frames,record,part['combatTrialGuard'])
            part['recording']=original

    def test_async_png_failure_during_prediction_releases_without_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            state={}
            with self.assertRaisesRegex(RuntimeError,'retention failed.*injected PNG'):
                self.run_loop(folder,fail_encoding=True,state=state)
            self.assertEqual(state['bridge'].actions,[])
            self.assertIn('release',state['bridge'].commands)
            self.assertEqual(state['bridge'].commands[-1],'stop')
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertFalse(report['recording']['complete'])
            self.assertTrue(report['recording']['closed'] and report['recording']['workerRetired'])
            self.assertIn('injected PNG encoding failure',report['recording']['error'])


if __name__=='__main__':unittest.main()
