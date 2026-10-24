"""Explicit fake/file cases only; native processes and transport construction are forbidden."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
import sys
from unittest.mock import patch
import courtyard_sequence as subject


def status(profile=subject.FORWARD, run='a'*32, previous=None):
    """A small synthetic terminal; full real artifact acceptance stays with the pinned helper."""
    evidence={'journalSha256':run*2}
    sample={'hostSnapshot':{'CaptureEpoch':'e','SnapshotId':1}}
    result=dict(profileId=profile,verified=True,error=None,inputReleaseError=None,evidence=evidence,samples=[sample])
    if previous is not None:
        prior=previous['navigationBaseline']
        result['continuation']=dict(predecessorRunId=prior['runId'],predecessorProfileId=prior['profileId'],
            predecessorEvidence=prior['result']['evidence'],predecessorFinalSource=dict(kind=subject.HOST_POLICY,
            hostSnapshot=prior['result']['samples'][-1]['hostSnapshot']),runtimeIdentity='r',
            gameStartedAtUtcTicks=123,childAssemblySha256='d'*64)
    return dict(processId=20928,windowsSessionId=3,instanceNonce='n'*32,taskRunning=False,policy=subject.HOST_POLICY,
        navigationBaseline=dict(state='completed',error=None,evidenceComplete=True,runId=run,profileId=profile,result=result))


class NativeError(RuntimeError):
    """Mirrors the frozen client's retained status exception interface."""
    def __init__(self,message,value):super().__init__(message);self.status=value


class FakeClient:
    """Only records delegations; no fake invokes a transport or process."""
    NavigationBaselineError=NativeError
    def __init__(self):
        self.mutations=[];self.entries=[];self.mode='pass';self.hook=lambda *args:None
        self.mutate=self.delegate
    def delegate(self,command,child,**fields):
        self.mutations.append((command,copy.deepcopy(child),copy.deepcopy(fields)))
        self.hook(command,child,fields)
        return {'ack':'same object'}
    def run_navigation_baseline(self,prior,timeout,**kwargs):
        self.entries.append((copy.deepcopy(prior),timeout,copy.deepcopy(kwargs)))
        if self.mode=='preflight-error':raise RuntimeError('No mutation yet')
        fields=dict(timingContract=kwargs['timing_contract'],capturePolicy=kwargs['capture_policy'],
            routeProfile=kwargs['route_profile'],continuationFromRunId=kwargs['continuation_from_run_id'])
        if self.mode=='wrong-fields':fields['shadowCapture']='forbidden'
        self.mutate('startNavigationBaseline',prior,**fields)
        if self.mode=='double':self.mutate('startNavigationBaseline',prior,**fields)
        if self.mode=='unknown':raise RuntimeError('Lost response')
        if self.mode=='old-terminal':raise NativeError('Admission response lost',prior)
        out=status(kwargs['route_profile'],str(len(self.entries))*32,prior)
        if self.mode=='failed':
            out['navigationBaseline'].update(state='failed',error='recovery_limit_exceeded')
            out['navigationBaseline']['result']['verified']=False
            raise NativeError('recovery_limit_exceeded',out)
        if self.mode=='wrong-predecessor':out['navigationBaseline']['result']['continuation']['predecessorRunId']='b'*32
        if self.mode=='identity':out['instanceNonce']='changed'
        if self.mode=='wrong-profile':out['navigationBaseline']['profileId']=subject.SEED
        return out


class SupervisorCases(unittest.TestCase):
    """Test actual supervisor sequencing/publication/cutoff and explicit unknown outcomes."""
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
        forbidden=patch('subprocess.Popen',side_effect=AssertionError('No process execution in CPU fixture'))
        forbidden.start();self.addCleanup(forbidden.stop)
        self.now=0;self.client=FakeClient();self.previous=status()
        self.binding=dict(child={key:self.previous[key] for key in ('processId','windowsSessionId','instanceNonce')},
            _bindingPin=dict(path='live.json',sha256='d'*64,bytes=1))
        self.plan=dict(admissionSeconds=180,package={'sha256':'a'*64},legs=subject.plan_names(2,4))
        def child(value,binding):
            subject.require(value is not None and all(value.get(k)==v for k,v in binding['child'].items())
                and value.get('taskRunning') is False,'Child identity/idle changed')
        def policy(value,selected):subject.require(value['policy']==selected,'Policy changed')
        self.support=types.SimpleNamespace(require_child=child,require_policy=policy)
        self.checks=types.SimpleNamespace(audit_native=lambda value,profile_id:dict(envelope=True,profileId=profile_id))
    def run_batch(self):
        return subject.run_legs(self.folder,self.plan,self.binding,self.previous,self.client,self.support,self.checks,clock=lambda:self.now)
    def test_four_legs_alternate_exactly_and_restore_mutate(self):
        original=self.client.mutate;result=self.run_batch()
        self.assertEqual(len(self.client.mutations),4);self.assertIs(self.client.mutate,original)
        self.assertEqual([x[2]['routeProfile'] for x in self.client.mutations],[subject.RETURN,subject.FORWARD]*2)
        self.assertEqual([x[2]['continuationFromRunId'] for x in self.client.mutations],['a'*32,'1'*32,'2'*32,'3'*32])
        self.assertTrue(result['nativeOwnerRetirementKnown']);self.assertTrue(result['fullRouteAuditsPending'])
    def test_original_call_arguments_have_no_reset_shadow_or_extra_selector(self):
        self.plan['legs']=subject.plan_names(2,1);self.run_batch();_,timeout,args=self.client.entries[0]
        self.assertEqual(timeout,45);self.assertEqual(args,dict(timing_contract='v4',capture_policy='task_owned_timer',
            route_profile=subject.RETURN,continuation_from_run_id='a'*32))
    def test_dispatch_and_previous_summary_exist_before_next_mutation(self):
        def hook(command,child,fields):
            index=len(self.client.mutations)-1;folder=self.folder/'legs'/self.plan['legs'][index]['name']
            self.assertTrue((folder/'dispatch.json').exists())
            if index:self.assertTrue((self.folder/'legs'/self.plan['legs'][index-1]['name']/'summary.json').exists())
        self.client.hook=hook;self.run_batch()
    def test_preflight_error_has_zero_mutations_and_unknown_retirement(self):
        self.client.mode='preflight-error';out=self.run_batch()
        self.assertEqual(self.client.mutations,[]);self.assertFalse(out['nativeOwnerRetirementKnown'])
        self.assertIsNone(subject.read(self.folder/'legs'/self.plan['legs'][0]['name']/'result.json')['status'])
    def test_unknown_response_stops_after_one_and_preserves_error(self):
        self.client.mode='unknown';out=self.run_batch()
        self.assertEqual(len(self.client.mutations),1);self.assertFalse(out['nativeOwnerRetirementKnown'])
        self.assertEqual(out['legs'][0]['error']['message'],'Lost response')
    def test_old_completed_status_does_not_prove_new_native_retirement(self):
        self.client.mode='old-terminal';out=self.run_batch()
        self.assertFalse(out['nativeOwnerRetirementKnown']);self.assertEqual(len(out['legs']),1)
    def test_native_failure_preserves_status_and_stops(self):
        self.client.mode='failed';out=self.run_batch();row=out['legs'][0]
        self.assertFalse(row['success']);self.assertTrue(row['nativeTerminalObserved']);self.assertEqual(len(out['legs']),1)
        saved=subject.read(row['nativeResult']['path']);self.assertEqual(saved['status']['navigationBaseline']['state'],'failed')
    def test_double_mutation_rejected_before_second_delegate(self):
        self.client.mode='double';out=self.run_batch()
        self.assertEqual(len(self.client.mutations),1);self.assertIn('repeated',out['error']['message'])
    def test_unexpected_fields_rejected_without_delegate(self):
        self.client.mode='wrong-fields';out=self.run_batch()
        self.assertEqual(len(self.client.mutations),0);self.assertIn('selector',out['error']['message'])
    def test_child_drift_stops_after_return(self):
        self.client.mode='identity';out=self.run_batch()
        self.assertEqual(len(self.client.mutations),1);self.assertFalse(out['legs'][0]['success'])
        self.assertFalse(out['legs'][0]['nativeTerminalObserved']);self.assertFalse(out['nativeOwnerRetirementKnown'])
    def test_wrong_profile_does_not_establish_native_retirement(self):
        self.client.mode='wrong-profile';out=self.run_batch()
        self.assertFalse(out['legs'][0]['nativeTerminalObserved']);self.assertFalse(out['nativeOwnerRetirementKnown'])
        self.assertEqual(len(self.client.mutations),1)
    def test_substituted_predecessor_stops_after_return(self):
        self.client.mode='wrong-predecessor';out=self.run_batch()
        self.assertEqual(len(out['legs']),1);self.assertIn('predecessor',out['error']['message'])
    def test_artifact_failure_is_not_native_acceptance(self):
        def fail(*args,**kwargs):raise RuntimeError('hash mismatch')
        self.checks.audit_native=fail;out=self.run_batch()
        self.assertEqual(len(out['legs']),1);self.assertEqual(out['error']['message'],'hash mismatch')
    def test_cutoff_after_completed_leg_prevents_second_call(self):
        self.client.hook=lambda *args:setattr(self,'now',180_000_000_000)
        out=self.run_batch();self.assertEqual(out['stopReason'],'admission_cutoff');self.assertEqual(len(out['legs']),1)
    def test_preflight_time_counts_against_cutoff(self):
        self.now=180_000_000_000
        out=subject.run_legs(self.folder,self.plan,self.binding,self.previous,self.client,self.support,self.checks,
            clock=lambda:self.now,started_at=0)
        self.assertEqual(out['legs'],[]);self.assertEqual(self.client.mutations,[])
    def test_cutoff_after_client_read_only_preflight_prevents_mutation(self):
        original=self.client.run_navigation_baseline
        def delayed(*args,**kwargs):self.now=180_000_000_000;return original(*args,**kwargs)
        self.client.run_navigation_baseline=delayed;out=self.run_batch()
        self.assertEqual(len(self.client.mutations),0);self.assertIn('cutoff',out['error']['message'])
    def test_cutoff_during_marker_publication_prevents_mutation(self):
        original=subject.publish
        def delayed(batch,path,value):
            original(batch,path,value)
            if Path(path).name=='dispatch.json':self.now=180_000_000_000
        with patch.object(subject,'publish',side_effect=delayed):out=self.run_batch()
        self.assertEqual(len(self.client.mutations),0);self.assertEqual(out['legs'][0]['mutationCalls'],0)
    def test_publication_failure_prevents_native_delegate(self):
        original=subject.publish
        def fail(batch,path,value):
            if Path(path).name=='dispatch.json':raise OSError('disk failure')
            original(batch,path,value)
        with patch.object(subject,'publish',side_effect=fail):out=self.run_batch()
        self.assertEqual(len(self.client.mutations),0);self.assertEqual(out['error']['message'],'disk failure')
    def test_per_leg_summary_disclaims_individual_postflight_and_full_audit(self):
        out=self.run_batch()
        for row in out['legs']:
            self.assertIn('batch-level',row['cleanupBasis']);self.assertTrue(row['fullRouteAuditPending'])
            self.assertFalse(row['continuousGameplayProven']);self.assertNotIn('game',row)
    def test_worker_loop_has_no_process_or_cim_or_transport_replacement(self):
        tree=ast.parse(Path(subject.__file__).read_text(encoding='utf-8'))
        loop=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_legs')
        names={ast.unparse(x.func) for x in ast.walk(loop) if isinstance(x,ast.Call)}
        self.assertFalse(names & {'current','game_identity','subprocess.Popen','rc.exchange','rc.refresh','rc.run_command'})
        self.assertIn('rc.run_navigation_baseline',names)
    def test_boundaries_do_not_invent_native_or_control_latency(self):
        out=self.run_batch();row=out['legs'][0]
        self.assertIn('clientCallStartedAtMonotonicNs',row);self.assertIn('terminalReturnedAtMonotonicNs',row)
        self.assertNotIn('controlLatencyMs',row);self.assertFalse(row['physicalInputAcknowledged'])
    def test_exclusive_outputs_cannot_replay_same_batch_legs(self):
        self.run_batch()
        with self.assertRaises(FileExistsError):self.run_batch()
        self.assertEqual(len(self.client.mutations),4)
    def test_fresh_indices_and_exact_limits(self):
        for count in (0,5,True):
            with self.assertRaises(RuntimeError):subject.plan_names(2,count)
        for start in (0,True,100):
            with self.assertRaises(RuntimeError):subject.plan_names(start,4)
        self.assertEqual(subject.plan_names(2,4)[-1]['name'],'leg-05-forward')
    def test_output_size_bound_rejects_before_creation(self):
        with self.assertRaises(RuntimeError):subject.publish(self.folder,self.folder/'big.json',{'x':'a'*subject.MAX_FILE_BYTES})
        self.assertFalse((self.folder/'big.json').exists())
    def test_output_path_escape_rejected(self):
        with self.assertRaises(RuntimeError):subject.publish(self.folder,self.folder.parent/'escape.json',{})
    def test_output_file_count_bound_rejected(self):
        for i in range(subject.MAX_FILES):(self.folder/f'{i}.json').write_text('{}')
        with self.assertRaises(RuntimeError):subject.publish(self.folder,self.folder/'extra.json',{})
    def test_nonfinite_output_rejected(self):
        with self.assertRaises(ValueError):subject.publish(self.folder,self.folder/'bad.json',{'x':float('nan')})
    def test_broker_uncertainty_remains_rejected(self):
        good=dict(returnCode=0,timedOut=False,windowsSessionId=3,remoteDesktop=True,
            outputIncomplete=False,stdoutTruncated=False,stderrTruncated=False)
        subject.require_broker_retired(good,3)
        for key,value in [('returnCode',None),('returnCode',True),('outputIncomplete',True),('windowsSessionId',2)]:
            with self.assertRaises(RuntimeError):subject.require_broker_retired(dict(good,**{key:value}),3)
    def test_joint_proofs_reject_old_runtime_between_links(self):
        chain=[status(subject.SEED,'1'*32)];chain.append(status(subject.RETURN,'2'*32,chain[-1]));chain.append(status(subject.FORWARD,'3'*32,chain[-1]))
        chain[-1]['navigationBaseline']['result']['continuation']['runtimeIdentity']='different'
        with self.assertRaisesRegex(RuntimeError,'Runtime'):subject.require_link(chain[-1],chain[-2])


class ActualClientCases(SupervisorCases):
    """Exercise the actual immutable client under only fake pipe/mutation boundaries."""
    # Avoid inheriting the other cases for duplicate execution; this class is loaded by the runner explicitly.
    def actual_fixture(self):
        snapshot=subject.HERE
        sys.path.insert(0,str(snapshot))
        import rdp_control
        import test_navigation_courtyard_cycle
        self.assertEqual(Path(rdp_control.__file__).resolve(),(snapshot/'rdp_control.py').resolve())
        guard=patch.object(rdp_control.transport,'WinPipeApi',side_effect=AssertionError('No native transport'))
        guard.start();self.addCleanup(guard.stop)
        return rdp_control,test_navigation_courtyard_cycle.HostCourtyardFixture()
    def test_actual_client_full_proof_and_delegate_args_remain_unchanged(self):
        rc,fx=self.actual_fixture();self.previous=fx.prior
        self.binding['child']={key:fx.prior[key] for key in ('processId','windowsSessionId','instanceNonce')}
        self.plan['legs']=subject.plan_names(2,1);self.previous['policy']=subject.HOST_POLICY
        fx.full['policy']=subject.HOST_POLICY;fx.terminal['policy']=subject.HOST_POLICY;fx.prior['policy']=subject.HOST_POLICY
        calls=[]
        def exchange(*args,**kwargs):
            return fx.prior if kwargs['fields']['navigationBaselineRunId']==fx.predecessor else fx.full
        def mutate(*args,**kwargs):calls.append((args,kwargs));return fx.terminal
        with patch.object(rc,'exchange',side_effect=exchange),patch.object(rc,'mutate',side_effect=mutate),\
             patch.object(rc,'refresh',return_value=fx.terminal),patch.object(rc.time,'sleep'):
            out=subject.run_legs(self.folder,self.plan,self.binding,self.previous,rc,self.support,self.checks,clock=lambda:self.now)
        self.assertIsNone(out['error']);self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],dict(timingContract='v4',capturePolicy='task_owned_timer',routeProfile=subject.RETURN,
            continuationFromRunId=fx.predecessor))
    def test_actual_client_wrong_capability_stops_before_mutation(self):
        rc,fx=self.actual_fixture();fx.prior['navigationBaseline']['hostEndpointContinuationVersion']=True
        fx.prior['policy']=subject.HOST_POLICY;self.binding['child']={key:fx.prior[key] for key in ('processId','windowsSessionId','instanceNonce')}
        with patch.object(rc,'exchange',side_effect=AssertionError('No read')),patch.object(rc,'mutate') as mutation:
            out=subject.run_legs(self.folder,self.plan,self.binding,fx.prior,rc,self.support,self.checks,clock=lambda:self.now)
        mutation.assert_not_called();self.assertIsNotNone(out['error'])


def load_tests(loader,tests,pattern):
    """Execute each focused case once, including exactly two actual-client integration cases."""
    suite=loader.loadTestsFromTestCase(SupervisorCases)
    for name in ('test_actual_client_full_proof_and_delegate_args_remain_unchanged',
                 'test_actual_client_wrong_capability_stops_before_mutation'):
        suite.addTest(ActualClientCases(name))
    return suite


if __name__=='__main__':unittest.main(verbosity=2)
