"""Synthetic closed-file admission cases; no game, pipe, model or process is invoked."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import types
from unittest.mock import patch
import courtyard_evidence as subject
import courtyard_sequence as sequence


class Bundle:
    """Small producer-shaped mock files with deliberately different runtime IDs."""
    def __init__(self,folder):
        self.folder=folder;self.app=folder/'app';self.app.mkdir()
        (self.app/'BetterGI.dll').write_bytes(b'mock-main')
        (self.app/'Fischless.GameCapture.dll').write_bytes(b'mock-capture')
        self.root=dict(processId=411,windowsSessionId=4,instanceNonce='a'*32,assemblySha256='b'*64,
            instanceType='Primary',childWindowMinimized=True,childSessionId=7,childConnectedState=1)
        self.child=dict(processId=812,windowsSessionId=7,instanceNonce='c'*32)
        self.game=dict(ProcessId=915,Name='GenshinImpact.exe',SessionId=7,CreationUtc='2026-01-02T03:04:05.1234560Z')
        self.started=dict(self.child,instanceType='ChildSession',rootProcessId=411,remoteDesktop=True,uiStatus='current',
            runtimeRunning=True,automationState='game_ready',assemblySha256=subject.sha(self.app/'BetterGI.dll'),
            appDirectory=str(self.app),agentInputEnabled=False,taskRunning=False,agentStreamRunning=False)
        self.source='d'*64
        replacement=dict(phase='replacement_ready',restartAcknowledged=True,replacementProcessId=812,replacementNonce='c'*32)
        endpoint=self.write('endpoint.json',dict(ready=True,replacementEvidence=replacement))
        started=self.write('started.json',self.started)
        hot=self.write('hot.json',dict(ready=True,endpointReady=True,runtimeReady=True,root=self.root,child=self.started,
            gameProcess=self.game,replacementEvidence=replacement,endpointResultSha256=endpoint['sha256'],explicitStartResultSha256=started['sha256']))
        snapshot_root=folder/'source-snapshot'
        rows=[]
        for name in ('tools/rdp-automation/rdp_control.py','tools/rdp-automation/child_runner.py','tools/quest-pilot/controller-control.py'):
            path=snapshot_root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'# inert fixture\n')
            row=subject.pin(path);row['path']=name;rows.append(row)
        snapshot=self.write('source-snapshot-manifest.json',dict(schema='r45-worktree-tool-snapshot-v1',files=rows,
            sourceManifestSha256=self.source,replacementProofSha256=hot['sha256'],endpointResultSha256=endpoint['sha256'],explicitStartResultSha256=started['sha256']))
        self.live=dict(schema='r45-validation-binding-v1',approvedForValidation=True,child=self.child,
            dllSha256=self.started['assemblySha256'],captureDllSha256=subject.sha(self.app/'Fischless.GameCapture.dll'),
            sourceRevision='e'*40,sourceProvenance=dict(kind='worktree-snapshot-v1',sourceManifestSha256=self.source),
            buildManifest=self.write('build.json',{'synthetic':True}),sourceSnapshotManifest=snapshot,hotReplacement=hot,
            endpointReplacement=endpoint,explicitStartResult=started,routeAuditorPackage=self.write('auditor.json',{'synthetic':True}))
        self.status=dict(self.started,captureMode='DesktopDc',configuredDesktopDcSourcePolicy=subject.HOST_POLICY,
            effectiveDesktopDcSourcePolicy=subject.HOST_POLICY,desktopDcSourcePolicyVersion=1,
            desktopDcSourcePolicies=['observe-only',subject.HOST_POLICY])
        run='1'*32;native=self.app/'User/NavigationBaselines'/run;native.mkdir(parents=True)
        journal=self.write(str(native/'journal.json'),dict(schemaVersion=2,sourcePolicy=subject.HOST_POLICY,runId=run,
            gameProcessId=915,windowsSessionId=7,readbackPendingCount=0,capturePolicy='task_owned_timer',timingContract='v4',
            profileId=subject.SEED,trainingEligible=False,humanDemonstration=False,completeLowLevelDispatchTrace=False,
            ownerCompletionRequired=True,observations=[],inputTransitions=[]))
        result=dict(profileId=subject.SEED,sourcePolicy=subject.HOST_POLICY,routeVersion=None,legs=[],continuation=None,
            verified=True,error=None,inputReleaseError=None,evidence=dict(sourcePolicy=subject.HOST_POLICY,
            journalPath=journal['path'],journalSha256=journal['sha256']))
        self.status['navigationBaseline']=dict(profileId=subject.SEED,runId=run,result=result,state='completed',error=None,
            evidenceComplete=True,endpointContinuationVersion=2,hostEndpointContinuationVersion=1,timingContract='v4',
            capturePolicy='task_owned_timer',sourcePolicy=subject.HOST_POLICY,gameProcessId=915,windowsSessionId=7)
        self.summary_changes={};self.audit_changes={};self.proof_changes={}

    def write(self,name,value):
        path=self.folder/name;path.write_text(json.dumps(value,allow_nan=False),encoding='utf-8');return subject.pin(path)

    def finish(self):
        """Seal a mutually joined synthetic proof; tests then vary one meaningful field."""
        live=self.write('live.json',self.live)
        closed=self.write('closed.json',dict(self.live,liveValidationBinding=live))
        result=self.write('result.json',dict(status=self.status,error=None))
        summary=dict(success=True,error=None,cleanupError=None,bindingSha256=live['sha256'],child=self.child,nativeResult=result,action='short')
        summary.update(self.summary_changes)
        summary=self.write('summary.json',summary)
        owner=self.status['navigationBaseline']
        audit=dict(schema='host-native-route-audit-r45-v1',routeEvidenceAccepted=True,runId=owner['runId'],profileId=subject.SEED,
            sourceKind=subject.HOST_POLICY,child=self.child,assemblySha256=self.live['dllSha256'],analyzerPackage=self.live['routeAuditorPackage'],
            artifactLinks=[result,closed],producerContract=dict(sourceManifestSha256=self.source))
        audit.update(self.audit_changes);audit=self.write('audit.json',audit)
        proof=dict(schema='r45-courtyard-predecessor-v1',runId=owner['runId'],profileId=subject.SEED,bindingSha256=closed['sha256'],
            summary=summary,result=result,routeAudit=audit,auditPackage=self.live['routeAuditorPackage'],binding=closed)
        proof.update(self.proof_changes)
        pin=self.write('proof.json',proof);return Path(pin['path']),pin['sha256']


class AdmissionCases(unittest.TestCase):
    """Exercise actual file/status validators with an inert, full producer-shaped bundle."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.folder=Path(temp.name)
        guard=patch('subprocess.Popen',side_effect=AssertionError('No process in evidence test'));guard.start();self.addCleanup(guard.stop)
        self.bundle=Bundle(self.folder)
    def check(self):return subject.prepare(*self.bundle.finish())
    def rejected(self):
        with self.assertRaises((RuntimeError,KeyError,ValueError)):self.check()
    def test_nonresearch_identities_and_seed_direction_are_data_driven(self):
        binding,proof,status,direction=self.check()
        self.assertEqual((binding['_root']['processId'],binding['child']['processId'],binding['_game']['ProcessId']),(411,812,915))
        self.assertEqual(direction,'return');self.assertEqual(proof['runId'],'1'*32)
    def test_actual_binding_field_is_approved_for_validation(self):
        self.bundle.live.pop('approvedForValidation');self.bundle.live['approved']=True;self.rejected()
    def test_unknown_proof_schema_is_not_guessed(self):
        self.bundle.proof_changes['schema']='future-v2';self.rejected()
    def test_unaccepted_report_cannot_admit(self):
        self.bundle.audit_changes['routeEvidenceAccepted']=False;self.rejected()
    def test_report_producer_must_match_deployment(self):
        self.bundle.audit_changes['producerContract']={'sourceManifestSha256':'f'*64};self.rejected()
    def test_report_must_link_exact_result_and_binding(self):
        self.bundle.audit_changes['artifactLinks']=[];self.rejected()
    def test_summary_missing_cleanup_is_not_clean(self):
        self.bundle.summary_changes['cleanupError']='not checked';self.rejected()
    def test_summary_binding_drift_is_rejected(self):
        self.bundle.summary_changes['bindingSha256']='0'*64;self.rejected()
    def test_native_failure_is_not_an_accepted_predecessor(self):
        self.bundle.status['navigationBaseline']['state']='failed';self.rejected()
    def test_exact_integer_host_capability(self):
        self.bundle.status['navigationBaseline']['hostEndpointContinuationVersion']=1.0;self.rejected()
    def test_nonnull_effective_wgc_option_is_rejected(self):
        self.bundle.status['effectiveConversion']='cpu';self.rejected()
    def test_nonexistent_top_level_game_pid_is_not_required(self):
        self.assertNotIn('gameProcessId',self.bundle.status);self.check()
    def test_owner_game_identity_remains_required(self):
        self.bundle.status['navigationBaseline']['gameProcessId']=916;self.rejected()
    def test_child_nonce_drift_is_rejected(self):
        self.bundle.status['instanceNonce']='9'*32;self.rejected()
    def test_pinned_client_bytes_cannot_change(self):
        path,digest=self.bundle.finish();(self.folder/'source-snapshot/tools/rdp-automation/rdp_control.py').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'Pinned'):subject.prepare(path,digest)
    def test_native_journal_bytes_cannot_change(self):
        path,digest=self.bundle.finish()
        Path(self.bundle.status['navigationBaseline']['result']['evidence']['journalPath']).write_bytes(b'{}')
        with self.assertRaisesRegex(RuntimeError,'hash'):subject.prepare(path,digest)
    def test_deployed_binary_bytes_cannot_change(self):
        path,digest=self.bundle.finish();(self.bundle.app/'BetterGI.dll').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'binary'):subject.prepare(path,digest)
    def test_substituted_proof_digest_is_rejected_first(self):
        path,_=self.bundle.finish()
        with self.assertRaisesRegex(RuntimeError,'hash'):subject.prepare(path,'0'*64)
    def test_duplicate_json_and_nonfinite_values_are_rejected(self):
        for text in ('{"x":1,"x":2}','{"x":NaN}','{"x":1e999}'):
            path=self.folder/'bad.json';path.write_text(text)
            with self.assertRaises(RuntimeError):subject.read(path)
    def test_pin_length_bool_is_not_an_integer(self):
        pin=self.bundle.write('empty.json',{});pin['bytes']=True
        with self.assertRaises(RuntimeError):subject.verify_pin(pin)
    def test_saved_compact_owner_must_be_exact_latest(self):
        _,_,saved,_=self.check();current=copy.deepcopy(saved);current['navigationBaseline'].pop('result')
        subject.require_latest(current,saved);current['navigationBaseline']['runId']='2'*32
        with self.assertRaises(RuntimeError):subject.require_latest(current,saved)
    def test_default_plan_has_no_queries_import_or_output_directory(self):
        path,digest=self.bundle.finish();output=self.folder/'not-created'
        argv=['courtyard_sequence.py','--predecessor',str(path),'--predecessor-sha256',digest,'--output-dir',str(output)]
        with (patch('sys.argv',argv),patch.object(subject,'load_client',side_effect=AssertionError('No client')),
              patch.object(sequence,'current',side_effect=AssertionError('No query')),contextlib.redirect_stdout(io.StringIO()) as text):
            self.assertEqual(sequence.main(),0)
        self.assertFalse(output.exists());plan=json.loads(text.getvalue())
        self.assertTrue(plan['preparedOnly']);self.assertEqual(plan['legs'][0]['profileId'],subject.RETURN)
    def test_return_predecessor_selects_forward_without_custom_targets(self):
        self.assertEqual([x['profileId'] for x in sequence.plan_names(1,4,'forward')],
            [subject.FORWARD,subject.RETURN]*2)
        with self.assertRaises(RuntimeError):sequence.plan_names(1,1,'other')


class ParentCases(unittest.TestCase):
    """Actual parent orchestration with fake current/broker seams and no child process."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.folder=Path(temp.name)/'fresh'
        guard=patch('subprocess.Popen',side_effect=AssertionError('No process'));guard.start();self.addCleanup(guard.stop)
        self.binding={'_bindingPin':{'sha256':'a'*64},
            'child':dict(processId=812,windowsSessionId=7,instanceNonce='e'*32)}
        self.args=types.SimpleNamespace(output_dir=self.folder)
        self.plan=dict(toolFiles=[],package=dict(path=str(sequence.HERE/'courtyard_sequence.py'),sha256='c'*64,bytes=1),
            legs=[dict(name='leg-01-return',direction='return')])
        self.before={'root':{'processId':411},'child':self.binding['child']}
        self.broker=dict(returnCode=0,timedOut=False,windowsSessionId=7,remoteDesktop=True,outputIncomplete=False,
            stdoutTruncated=False,stderrTruncated=False,success=True)
        def command(*args):
            # Match the actual successful worker envelope; retain the parent boundary assertions below.
            item=self.plan['legs'][0]
            leg=dict(name=item['name'],action='courtyard-'+item['direction'],child=self.binding['child'],
                bindingSha256=self.binding['_bindingPin']['sha256'],supervisorPackage=self.plan['package'],
                success=True,error=None,mutationCalls=1,nativeTerminalObserved=True,
                nativeResult=dict(path=str((self.folder/'legs'/item['name']/'result.json').resolve()),
                    bytes=123,sha256='d'*64))
            sequence.publish(self.folder,self.folder/'worker-result.json',
                dict(schema='r45-courtyard-worker-result-v1',stopReason='leg_limit',error=None,
                    nativeOwnerRetirementKnown=True,automaticReplay=False,legs=[leg]))
            return self.broker
        self.rc=types.SimpleNamespace(run_command=unittest.mock.Mock(side_effect=command))
    def run_parent(self,postflight=None,latest_error=None):
        states=[self.before,self.before if postflight is None else postflight]
        with (patch.object(subject,'load_client',return_value=self.rc),patch.object(sequence,'current',side_effect=states) as current,
              patch.object(sequence,'latest',side_effect=latest_error),contextlib.redirect_stdout(io.StringIO())):
            code=sequence.execute(self.args,self.binding,{}, {},self.plan)
        return code,sequence.read(self.folder/'summary.json'),current
    def test_one_broker_call_uses270s_and_batch_only_cim(self):
        code,summary,current=self.run_parent();self.assertEqual(code,0);self.assertTrue(summary['success'])
        self.rc.run_command.assert_called_once();args=self.rc.run_command.call_args.args
        self.assertEqual(args[4],270);self.assertEqual(args[6],32768)
        self.assertEqual(current.call_count,2)
        self.assertTrue(all(c.kwargs['include_game'] is True for c in current.call_args_list))
    def test_worker_timeout_does_not_retry_or_imply_native_retirement(self):
        self.broker.update(timedOut=True,returnCode=1,success=False)
        code,summary,_=self.run_parent();self.assertEqual(code,1);self.rc.run_command.assert_called_once()
        self.assertTrue(summary['nativeRetirementCannotBeInferredFromWorkerExit']);self.assertFalse(summary['success'])
    def test_postflight_error_suppresses_success(self):
        code,summary,_=self.run_parent(postflight=RuntimeError('game changed'))
        self.assertEqual(code,1);self.assertIsNotNone(summary['cleanupError'])
    def test_latest_owner_drift_prevents_broker_launch(self):
        code,summary,current=self.run_parent(latest_error=RuntimeError('latest changed'))
        self.assertEqual(code,1);self.rc.run_command.assert_not_called();self.assertEqual(current.call_count,2)
    def test_existing_output_prevents_client_import_or_replay(self):
        self.folder.mkdir()
        with patch.object(subject,'load_client') as client,self.assertRaises(FileExistsError):
            sequence.execute(self.args,self.binding,{}, {},self.plan)
        client.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
