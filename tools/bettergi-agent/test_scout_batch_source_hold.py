"""Portable source-hold authority, real intake and original-receipt replay tests; no GPU or native IO."""
import ast
import copy
from types import SimpleNamespace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scout_batch_source_hold import BatchSourceHold, immutable_frame
from reviewed_scout_route import batch_source_hold_policy, reviewed_batch_policy, batch_policy_matches, validate_reviewed_options
import test_reviewed_scout_route as batch_tests
from test_combat_trial_guard import frame as native_sample
from test_native_ground_control import attach_ground, binding as ground_binding

BATCH=batch_tests.BATCH


def empty_context():
    """Match real aggregate-release uncertainty without claiming physical key-up delivery."""
    return dict(active=None,telemetryComplete=True,evictedEvents=0,
                trackedState=dict(heldKeys=[],executionUncertain=True,releaseOutcome='returned_unverified',telemetryIncomplete=False))


def source(index=187,at=1000,epoch=1,age=10):
    """Use original native schema validators and exact synthetic ground crops."""
    value=attach_ground(native_sample(index,at,candidates=0,epoch=epoch,age=age))
    value.update(navigationPose=dict(state='valid',frameId=index,x=BATCH.points[1][0],y=BATCH.points[1][1],
        yawDegrees=90,positionConfidence=.996,yawConfidence=.6,layerId='MapBack_2'),
        motionEvidence=dict(status='normal',spaceKeyMatched=False),executionContext=empty_context())
    for key in ('worldReadiness','frameWorldReadiness'):
        value[key].update(reason='world_ready',sourceCapturedAtMs=value['capturedAtMs'],checkedAtMs=value['serverNowMs'])
    return value


def unavailable(value,key,reason='world_not_ready'):
    """Clear positive fields exactly as the native unavailable constructors do."""
    evidence=value[key];evidence.update(state='unavailable',reason=reason)
    if key=='combatEvidence':
        evidence.update(playerHealthColor='unknown',playerHealthFractionEstimate=None,
            playerHealthMatchingPixels=0,enemyBarCandidates=[],redMaskOverloaded=False)
    else:
        evidence.update(groundControlsConfirmed=False,swimHintPixels=0,spaceKeyMatched=None,
            xKeyMatched=None,eKey=None,qKey=None,crops=[])


def fixture():
    """Bind a settled W50 predecessor and the exact repeated positive frame becoming stale."""
    lease=dict(sessionId='lease',ownerEpoch='epoch',goalVersion=1)
    machine=BatchSourceHold(batch_source_hold_policy(),BATCH.profile_id,BATCH.sha256,lease,ground_binding())
    healthy=source();machine.remember_healthy(healthy,1_070_000_000,1,dict(state='ready'))
    step=dict(durationMs=50,keys=['W'],mouseDx=0,mouseDy=0)
    request=dict(requestId='prior',frameId=186,modelId='controller',steps=[step],
                 observedAtMs=900,startBeforeMs=1050,expiresAtMs=1150)
    receipt=dict(requestId='prior',frameId=186,modelId='controller',status='completed',reason='horizon_complete',
        acceptedAtMs=940,endedAtMs=990,appliedSteps=[dict(index=0,keys=['W'],mouseDx=0,mouseDy=0,startedAtMs=940)])
    history=dict(beforeFrames=0,afterFrames=1,validFrames=1,beforeIndex=0,afterIndex=12,beforeValidTokens=0,afterValidTokens=12)
    old_source=source(186,900)['sourceFrame']
    settled=dict(outcome='committed',error=None,requestId='prior',frameId=186,sourceFrame=old_source,
        receipt=receipt,arguments=request,acceptance=dict(type='accepted',requestId='prior',acceptedAtMs=940),
        history=history,clientTimeNs=1_060_000_000)
    runtime=dict(lease=lease,routeSpecSha256=BATCH.sha256,phase='walking',target=list(BATCH.points[2]),
        targetName='waypoint-2',completedLegs=1,legStartedAtMs=800,legDeadlineClientNs=36_000_000_000,
        deadlineClientNs=61_000_000_000,lastAcceptedClientNs=1_000_000_000,pendingFeedback=False,
        pendingCandidate=False,unacknowledgedInput=False,acceptedActions=1,terminalReceipts=1,historyCommits=1,
        history=history,settled=settled,predecessor=dict(requestId='prior',frameId=186,endedAtMs=990,sourceFrame=old_source))
    stale=copy.deepcopy(healthy);stale.update(sourceFrameAgeMs=165.6613,serverNowMs=1165.6613,inputAvailable=False)
    stale['worldReadiness'].update(ready=False,reason='world_observation_stale',epoch=2,checkedAtMs=1165.6613)
    ack=dict(type='released',serverNowMs=1170,receipts=[],droppedReceipts=0,executionContext=empty_context(),
        worldReadiness=dict(stale['worldReadiness'],ready=False,reason='client_release',epoch=3,checkedAtMs=1170))
    return machine,healthy,stale,ack,runtime


class BatchSourceHoldTests(unittest.TestCase):
    """Exercise exact immutable-source, ACK and two-source barriers without sleeping."""
    def begin(self):
        """Consume only the pure trigger and exact native-shaped release once."""
        machine,healthy,stale,ack,runtime=fixture()
        self.assertIsNotNone(machine.observe(stale,1_220_000_000,runtime,1))
        machine.acknowledge_release(ack,0,1_230_000_000,runtime)
        return machine,runtime

    def test_two_post_ack_sources_preserve_history_and_original_clocks(self):
        machine,runtime=self.begin();before=copy.deepcopy(runtime)
        first=machine.observe(source(188,1230,3),1_300_000_000,runtime,1)
        self.assertTrue(first['qualified']);self.assertTrue(machine.waiting)
        with self.assertRaises(ValueError):machine.begin_prediction()
        second=machine.observe(source(189,1260,3),1_330_000_000,runtime,1)
        self.assertTrue(second['qualified']);self.assertFalse(machine.waiting)
        self.assertEqual(runtime,before);self.assertEqual(machine.snapshot()['sourceFrameIds'],[188,189])

    def test_exact_native_stale_motion_projection_keeps_original_positive_capture(self):
        """Match R73 MotionForReadiness while rejecting every other mask or source mutation."""
        projected=dict(status='unknown',reason='world_not_ready',method='native_key_tip_templates_v1',
                       recognitionMs=0.0,spaceKeyMatched=None,xKeyMatched=None)
        machine,healthy,stale,ack,runtime=fixture();stale['motionEvidence']=copy.deepcopy(projected)
        event=machine.observe(stale,1_220_000_000,runtime,1)
        self.assertEqual(event['previous']['frame']['motionEvidence'],healthy['motionEvidence'])
        self.assertEqual(event['frame']['motionEvidence'],projected)
        for key,value in (('status','normal'),('reason','recognition_failed'),('method','foreign'),
                          ('recognitionMs',1),('recognitionMs',False),('spaceKeyMatched',False),('xKeyMatched',False)):
            machine,_,stale,_,runtime=fixture();stale['motionEvidence']=dict(projected,**{key:value})
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):machine.observe(stale,1_220_000_000,runtime,1)
        machine,_,stale,_,runtime=fixture();stale['motionEvidence']=projected;stale['frameId']+=1
        with self.assertRaises(ValueError):machine.observe(stale,1_220_000_000,runtime,1)

    def test_native_release_omits_input_availability_and_retains_uncertainty(self):
        machine,runtime=self.begin()
        self.assertNotIn('inputAvailable',machine.release['response'])
        self.assertTrue(machine.release['response']['executionContext']['trackedState']['executionUncertain'])

    def test_pending_prediction_candidate_and_input_never_become_holds(self):
        for key in ('pendingFeedback','pendingCandidate','unacknowledgedInput'):
            machine,_,stale,_,runtime=fixture();runtime[key]=True
            self.assertIsNone(machine.observe(stale,1_220_000_000,runtime));self.assertEqual(machine.used,0)
        machine,_,stale,_,runtime=fixture();machine.begin_prediction()
        self.assertIsNone(machine.observe(stale,1_220_000_000,runtime));self.assertEqual(machine.used,0)

    def test_changed_immutable_capture_or_wrong_stale_cause_refuses(self):
        for key in ('combatEvidence','groundControlEvidence','sourceFrame','navigationPose'):
            machine,_,stale,_,runtime=fixture();stale[key]=dict(stale[key],changed=True)
            with self.subTest(key=key),self.assertRaises(ValueError):machine.observe(stale,1_220_000_000,runtime)
        machine,_,stale,_,runtime=fixture();stale['worldReadiness']['reason']='focus_lost'
        self.assertIsNone(machine.observe(stale,1_220_000_000,runtime))

    def test_unsettled_missing_foreign_receipt_or_history_refuses(self):
        for mutate in (lambda r:r.update(terminalReceipts=0),lambda r:r['settled']['receipt'].update(requestId='foreign'),
                lambda r:r['settled']['receipt'].update(endedAtMs=989),lambda r:r.update(historyCommits=0),
                lambda r:r.update(predecessor=None),lambda r:r['settled'].update(outcome='failed')):
            machine,_,stale,_,runtime=fixture();mutate(runtime)
            with self.assertRaises(ValueError):machine.observe(stale,1_220_000_000,runtime)

    def test_wrong_ack_epoch_owner_source_active_or_lost_receipt_refuses(self):
        for mutate in (lambda a:a['worldReadiness'].update(epoch=4),lambda a:a['worldReadiness'].update(reason='focus_lost'),
                lambda a:a['worldReadiness']['sourceFrame'].update(captureEpoch='foreign'),
                lambda a:a['executionContext'].update(active={'requestId':'foreign'}),
                lambda a:a['executionContext']['trackedState'].update(heldKeys=['W']),
                lambda a:a['executionContext']['trackedState'].update(releaseOutcome='failed'),
                lambda a:a.update(droppedReceipts=1),lambda a:a.update(inputAvailable=True)):
            machine,_,stale,ack,runtime=fixture();machine.observe(stale,1_220_000_000,runtime);mutate(ack)
            with self.assertRaises(ValueError):machine.acknowledge_release(ack,0,1_230_000_000,runtime)
        machine,_,stale,ack,runtime=fixture();machine.observe(stale,1_220_000_000,runtime);runtime['lease']['ownerEpoch']='foreign'
        with self.assertRaises(ValueError):machine.acknowledge_release(ack,0,1_230_000_000,runtime)

    def test_exact_60ms_floor_and_duplicate_first_source_do_not_open_fence(self):
        machine,runtime=self.begin()
        self.assertFalse(machine.observe(source(188,1229.999,3),1_300_000_000,runtime)['qualified'])
        first=source(189,1230,3);self.assertTrue(machine.observe(first,1_310_000_000,runtime)['qualified'])
        self.assertFalse(machine.observe(first,1_320_000_000,runtime)['qualified']);self.assertTrue(machine.waiting)

    def test_valid_owned_confirming_and_invalidation_wait_never_count(self):
        for current_ready,reason,at in ((False,'world_confirming',1180),(True,'world_confirming',1180),
                                       (False,'world_observation_invalidated',1169)):
            machine,runtime=self.begin();value=source(188,at,3)
            value['capturedAtMs']=1173 if at<1170 else value['capturedAtMs']
            value['frameWorldReadiness'].update(ready=False,reason=reason)
            value['worldReadiness'].update(ready=current_ready,reason='world_ready' if current_ready else reason)
            value['inputAvailable']=False
            unavailable(value,'combatEvidence');unavailable(value,'groundControlEvidence')
            self.assertFalse(machine.observe(value,1_260_000_000,runtime)['qualified']);self.assertTrue(machine.waiting)

    def test_unknown_ground_hud_and_input_contradictions_are_terminal_before_floor(self):
        for key in ('groundControlEvidence','combatEvidence'):
            machine,runtime=self.begin();value=source(188,1180,3);unavailable(value,key,'recognition_failed')
            with self.subTest(key=key),self.assertRaises(ValueError):machine.observe(value,1_260_000_000,runtime)
        for ready,available in ((False,True),(True,False),(True,None)):
            machine,runtime=self.begin();value=source(188,1180,3)
            value['worldReadiness'].update(ready=ready,reason='world_ready' if ready else 'world_confirming')
            value['frameWorldReadiness'].update(ready=ready,reason='world_ready' if ready else 'world_confirming')
            value['inputAvailable']=available
            with self.assertRaises(ValueError):machine.observe(value,1_260_000_000,runtime)

    def test_pending_health_enemy_ground_epoch_and_receipt_failures_remain_terminal(self):
        mutations=(lambda v:v['combatEvidence'].update(playerHealthColor='red'),
            lambda v:v['combatEvidence'].update(playerHealthFractionEstimate=.7),
            lambda v:v['combatEvidence'].update(enemyBarCandidates=native_sample()['combatEvidence']['enemyBarCandidates']),
            lambda v:v['worldReadiness'].update(epoch=4),lambda v:v.update(droppedReceipts=1),
            lambda v:v['executionContext'].update(active={'requestId':'foreign'}),
            lambda v:v['sourceFrame'].update(captureEpoch='foreign'))
        for mutate in mutations:
            machine,runtime=self.begin();value=source(188,1180,3);mutate(value)
            with self.assertRaises(ValueError):machine.observe(value,1_260_000_000,runtime)

    def test_original_acceptance_and_leg_batch_deadlines_never_renew(self):
        machine,runtime=self.begin();machine.tick(1_500_000_000,runtime)
        with self.assertRaisesRegex(ValueError,'500ms'):machine.tick(1_500_000_001,runtime)
        for key in ('deadlineClientNs','legDeadlineClientNs','lastAcceptedClientNs','target','history'):
            machine,runtime=self.begin();changed=copy.deepcopy(runtime)
            changed[key]=999999999999 if key.endswith('Ns') else None
            with self.assertRaises(ValueError):machine.tick(1_300_000_000,changed)
        for key in ('deadlineClientNs','legDeadlineClientNs'):
            machine,_,stale,_,runtime=fixture();runtime[key]=1_220_000_000
            with self.assertRaisesRegex(ValueError,'deadline'):machine.observe(stale,1_220_000_000,runtime)

    def test_second_hold_never_consumes_another_release(self):
        machine,runtime=self.begin()
        machine.observe(source(188,1230,3),1_300_000_000,runtime)
        machine.observe(source(189,1260,3),1_330_000_000,runtime)
        _,_,stale,_,_=fixture()
        self.assertIsNone(machine.observe(stale,1_350_000_000,runtime));self.assertEqual(machine.used,1)


class BatchSourceHoldAuthorityTests(unittest.TestCase):
    """An opt-in flag and the exact version2 descriptor are both necessary."""
    def test_old_policy_remains_exact_and_nested_boolean_substitution_refuses(self):
        old=reviewed_batch_policy();self.assertEqual(old['version'],1);self.assertNotIn('sourceHoldPolicy',old)
        new=reviewed_batch_policy(source_hold=True)
        self.assertTrue(batch_policy_matches(new,source_hold=True));self.assertFalse(batch_policy_matches(new))
        new['sourceHoldPolicy']['maximumHolds']=True
        self.assertFalse(batch_policy_matches(new,source_hold=True))

    def test_flag_cannot_authorize_single_leg_or_inspected_successor_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            args=batch_tests.batch_arguments(folder);args.batch_source_hold=True
            self.assertEqual(validate_reviewed_options(args),BATCH)
            for field,value in (('reviewed_scout_batch',False),('batch_source_hold',1),
                                ('allow_inspected_source_gap_recovery',True),('navigation_climb_recovery',True)):
                altered=copy.copy(args);setattr(altered,field,value)
                with self.assertRaises(ValueError):validate_reviewed_options(altered)


class HoldBridge(batch_tests.BatchBridge):
    """Drive the real loop with native-shaped cached pixels and one explicit idle release."""
    def __init__(self,recorder,*,lost_ack=False,delay_second=75,interrupt=None,freeze_action=4):
        super().__init__();self.recorder=recorder;self.lost_ack=lost_ack
        self.delay_second=delay_second;self.interrupt=interrupt;self.frozen=None
        self.hold_releases=0;self.hold_at=None;self.first_post=None;self.frame_calls=[]
        self.last_row=None;self.stale_once=False;self.freeze_action=freeze_action

    def normalize(self,row):
        """Fill only known native readiness/context fields omitted by older transport doubles."""
        for key in ('frameWorldReadiness','worldReadiness'):
            gate=row[key];gate.update(reason='world_ready' if gate['ready'] else 'world_confirming',
                sourceCapturedAtMs=row['capturedAtMs'],checkedAtMs=row['serverNowMs'])
        if 'combatEvidence' not in row:
            row['combatEvidence']=native_sample(row['frameId'],row['sourceFrame']['freshnessAtMs'],candidates=0)['combatEvidence']
            row['combatEvidence']['sourceFrame']=copy.deepcopy(row['sourceFrame'])
            unavailable(row,'combatEvidence');unavailable(row,'groundControlEvidence')
        row['executionContext']=empty_context()
        return row

    def request(self,command,**arguments):
        """Freeze a fully settled second-leg source, preserving every original action and receipt."""
        if command=='frame':
            self.frame_calls.append(time.perf_counter_ns())
            if self.frozen is not None:
                self.commands.append(command);row=copy.deepcopy(self.frozen);now=self.now()
                row.update(serverNowMs=now,sourceFrameAgeMs=now-row['sourceFrame']['freshnessAtMs'],receipts=self.terminal())
                if row['sourceFrameAgeMs']>150:
                    if not self.stale_once:self.epoch+=1;self.stale_once=True
                    row['worldReadiness'].update(ready=False,epoch=self.epoch,reason='world_observation_stale',checkedAtMs=now)
                    row['motionEvidence']=dict(status='unknown',reason='world_not_ready',method='native_key_tip_templates_v1',
                        recognitionMs=0.0,spaceKeyMatched=None,xKeyMatched=None)
                    row['inputAvailable']=False
                else:row['worldReadiness']['checkedAtMs']=now
                self.last_row=copy.deepcopy(row);return row,self.pixels
        row,pixels=super().request(command,**arguments)
        if command=='release':
            previous=self.last_row
            if previous is not None:
                row['worldReadiness'].update(sourceFrameId=previous['frameId'],
                    sourceCapturedAtMs=previous['capturedAtMs'],checkedAtMs=row['serverNowMs'])
                row['executionContext']=empty_context()
            if self.frozen is not None:
                self.hold_releases+=1;self.hold_at=row['serverNowMs'];self.frozen=None
                if self.lost_ack:raise OSError('synthetic recovery ACK lost after release')
            return row,pixels
        if command=='frame':
            row=self.normalize(row)
            if self.hold_at is None and not self.stale_once:
                # Like actual frame187, this cached image starts during W50 and
                # remains older than its eventual receipt, preventing a fifth candidate.
                if len(self.actions)==self.freeze_action and self.pending is not None and not row['receipts']:
                    self.frozen=copy.deepcopy(row)
            if self.hold_at is not None and row['sourceFrame']['freshnessAtMs']>=self.hold_at+60:
                if self.first_post is None:self.first_post=copy.deepcopy(row)
                if self.now()<self.first_post['serverNowMs']+self.delay_second:
                    row=copy.deepcopy(self.first_post);row['serverNowMs']=self.now()
                    row['sourceFrameAgeMs']=row['serverNowMs']-row['sourceFrame']['freshnessAtMs']
                    row['worldReadiness']['checkedAtMs']=row['serverNowMs']
                if self.interrupt:self.interrupt(row)
            self.last_row=copy.deepcopy(row);self.last_source=copy.deepcopy(row['sourceFrame'])
        return row,pixels


def run_hold_fixture(folder,*,bridge=None,policy=None,recorder=None,args=None,control=None):
    """Reuse the established real intake/controller test with only explicit version2 worker authority."""
    recorder=recorder or batch_tests.stream_tests.HistoryRecorder()
    bridge=bridge or HoldBridge(recorder)
    policy=policy or batch_tests.stream_tests.HistoryPolicy()
    args=args or batch_tests.batch_arguments(folder,seconds=4)
    args.batch_source_hold=True;args.fps=40
    with patch.object(batch_tests,'reviewed_batch_policy',lambda profile=BATCH.profile_id:reviewed_batch_policy(profile,source_hold=True)):
        return batch_tests.run_batch_fixture(folder,bridge=bridge,policy=policy,recorder=recorder,args=args,control=control)


def production_method(filename,name,owner=None):
    """Execute the exact selected method body without importing torch or a model constructor."""
    path=Path(__file__).with_name(filename);tree=ast.parse(path.read_text(encoding='utf-8'))
    scope=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==owner) if owner else tree
    matches=[node for node in ast.walk(scope) if isinstance(node,ast.FunctionDef) and node.name==name]
    assert len(matches)==1
    namespace={'deepcopy':copy.deepcopy}
    exec(compile(ast.Module(body=[matches[0]],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name]


class CounterScalar:
    """Supply only the scalar storage operations used by the unchanged adapter lifecycle."""
    def __init__(self,value=0):
        """Create scalar storage, not model state or backup counters."""
        self.value=value
    def item(self):
        """Return the current scalar for the real counter method."""
        return self.value
    def clone(self):
        """Let the actual transaction method create its own independent backup."""
        return CounterScalar(self.value)
    def copy_(self,other):
        """Mirror the in-place scalar copy used by rejection and later predictions."""
        self.value=other.value;return self
    def zero_(self):
        """Allow the actual reset body to clear retained scalar storage."""
        self.value=0;return self


class ColdBackupPolicy(batch_tests.stream_tests.HistoryPolicy):
    """Run real adapter transaction/reset/counter bodies around an inert proposal and receipt."""
    _begin_history_transaction=production_method('model_adapters.py','_begin_history_transaction','OpenP2PAdapter')
    executed_history_counters=production_method('model_adapters.py','executed_history_counters','OpenP2PAdapter')
    actual_reset=production_method('model_adapters.py','reset','OpenP2PAdapter')
    actual_finish=production_method('model_adapters.py','finish_executed_action','OpenP2PAdapter')
    actual_reject=production_method('model_adapters.py','finish_action','OpenP2PAdapter')
    def __init__(self):
        """Match initialized public storage while deliberately leaving all three backup fields absent."""
        super().__init__();self.steps_seen=0;self.idx=CounterScalar();self.state=[]
        self.static_idx=self.idx;self.static_state=self.state;self.graph=object();self.text=CounterScalar()
        self.temporal_cache=SimpleNamespace(valid_tokens=CounterScalar())
        self.temporal_cache.reset=self.temporal_cache.valid_tokens.zero_
        self.config=SimpleNamespace(shared=SimpleNamespace(n_seq_timesteps=41))
        self._pending_feedback=False;self._executed_candidate=None;self._history_backup=None
        self.cold_prediction_entries=[]
    def predict(self,image,size,**kwargs):
        """Only the unchanged real transaction body may create backup attributes before the inert forward."""
        self.cold_prediction_entries.append(not hasattr(self,'_backup_steps'))
        self._begin_history_transaction();result=super().predict(image,size,**kwargs)
        self.steps_seen=self.frames;self.idx.value=self.frames*12
        self.temporal_cache.valid_tokens.value=min(self.frames,41)*12
        return result
    def prepare_executed_action(self,step):
        """Retain the same selected step for the real completed-receipt method, with no tensor forward."""
        encoded=super().prepare_executed_action(step)
        self._executed_candidate=dict(step=copy.deepcopy(step),encodedAction=copy.deepcopy(encoded))
        return encoded
    def finish_executed_action(self,receipt,request,accepted):
        """Exercise the production receipt/candidate join before the existing inert evidence ledger."""
        self.actual_finish(receipt,request,accepted);super().finish_executed_action(receipt,request,accepted)
    def finish_action(self,accepted):
        """Exercise real rollback without fabricating a settled predecessor."""
        self.actual_reject(accepted);super().finish_action(accepted)
    def reset(self):
        """Use the actual reset, including its deliberate retention of previously created backups."""
        self.actual_reset();super().reset()


def runtime_snapshot(policy,events,predecessor):
    """Run the actual nested snapshot with the existing precise source-hold fixture bookkeeping."""
    runtime=fixture()[-1];method=production_method('stream_client.py','source_hold_runtime')
    method.__globals__.update(copy=copy,source_hold_runtime_ready=True,batch_source_hold=SimpleNamespace(inflight=False),
        report=dict(executedHistoryEvents=events,acceptedInputActions=len(policy.commits)),
        bridge=SimpleNamespace(hello=runtime['lease']),args=SimpleNamespace(reviewed_scout_route=BATCH),
        hybrid=SimpleNamespace(phase=runtime['phase'],target=runtime['target'],target_name=runtime['targetName'],
            legs=runtime['completedLegs'],leg_started=runtime['legStartedAtMs'],leg_deadline_ns=runtime['legDeadlineClientNs']),
        deadline=runtime['deadlineClientNs']/1e9,last_accepted_at=runtime['lastAcceptedClientNs']/1e9,
        policy=policy,history_receipts=set(policy.commits),history_predecessor=predecessor)
    return method()


class ColdSourceHoldSnapshotTests(unittest.TestCase):
    """A real cold adapter has no history snapshot until this run has an exact settled predecessor."""
    def test_cold_snapshot_never_reads_or_fabricates_adapter_backup_counters(self):
        policy=ColdBackupPolicy();policy.reset()
        for name in ('_backup_steps','_backup_idx','_backup_valid'):self.assertFalse(hasattr(policy,name))
        with self.assertRaisesRegex(AttributeError,'_backup_steps'):policy.executed_history_counters()
        self.assertIsNone(runtime_snapshot(policy,[],None))
        # Either half missing remains unresolved, even when the other half resembles an old run.
        old=fixture()[-1]
        self.assertIsNone(runtime_snapshot(policy,[],old['predecessor']))
        self.assertIsNone(runtime_snapshot(policy,[old['settled']],None))
        for name in ('_backup_steps','_backup_idx','_backup_valid'):self.assertFalse(hasattr(policy,name))

    def test_real_settlement_counters_survive_and_reset_does_not_forge_a_predecessor(self):
        policy=ColdBackupPolicy();machine,healthy,stale,ack,runtime=fixture();settled=runtime['settled']
        policy.predict(None,(1,1));policy.prepare_executed_action(settled['arguments']['steps'][0])
        policy.finish_executed_action(settled['receipt'],settled['arguments'],settled['acceptance'])
        snapshot=runtime_snapshot(policy,[settled],runtime['predecessor'])
        self.assertEqual(snapshot,runtime);self.assertEqual(snapshot['history'],policy.executed_history_counters())
        machine.observe(stale,1_220_000_000,snapshot,1);machine.acknowledge_release(ack,0,1_230_000_000,snapshot)
        policy.reset();self.assertTrue(hasattr(policy,'_backup_steps'))
        self.assertEqual(policy.executed_history_counters()['afterFrames'],0)
        missing=runtime_snapshot(policy,[settled],None);self.assertIsNone(missing)
        # Loss during an active hold still fails closed; startup omission is never renewed authority.
        with self.assertRaises(AttributeError):machine.tick(1_240_000_000,missing)
        self.assertTrue(machine.waiting);self.assertEqual(machine.used,1)

    def test_cold_real_counter_adapter_reaches_first_prediction_and_two_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            policy=ColdBackupPolicy()
            code,part,recorder,bridge,policy=run_hold_fixture(folder,policy=policy)
            self.assertEqual((code,part['status'],bridge.hold_releases),(0,'completed',1))
            self.assertEqual((len(bridge.actions),len(bridge.completed),len(policy.commits)),(6,6,6))
            self.assertEqual(policy.cold_prediction_entries,[True,False,False,False,False,False])
            self.assertEqual([event['history']['afterFrames'] for event in part['executedHistoryEvents']],[1,2,3,1,2,3])
            self.assertEqual(len([row for row in part['controlTransitions'] if 'executedHistoryReset' in row]),2)
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')


class BatchSourceHoldStreamTests(unittest.TestCase):
    """Retain one model/request across two endpoints, while proving hold and failure fences."""
    def test_one_hold_two_endpoints_retains_history_and_no_prediction_between_confirmations(self):
        with tempfile.TemporaryDirectory() as folder:
            code,part,recorder,bridge,policy=run_hold_fixture(folder)
            self.assertEqual((code,part['status'],bridge.hold_releases),(0,'completed',1))
            self.assertEqual((len(bridge.actions),len(bridge.completed),len(policy.commits)),(6,6,6))
            self.assertEqual([event['history']['afterFrames'] for event in part['executedHistoryEvents']],[1,2,3,1,2,3])
            self.assertEqual(len([row for row in part['controlTransitions'] if 'executedHistoryReset' in row]),2)
            self.assertFalse(any(row.get('reason')=='batchIdleSourceHold' for row in part['controlTransitions']))
            confirmations=[row for row in part['scoutBatchSourceHoldEvents'] if row['type'].endswith('Observation') and row['qualified']]
            self.assertEqual(len(confirmations),2)
            first,last=[row['clientTimeNs'] for row in confirmations]
            self.assertFalse(any(first<row['frameTiming']['predictionStartedAtClientNs']<last for row in part['decisions']))
            calls=sum(first<stamp<=last for stamp in bridge.frame_calls)
            self.assertLessEqual(calls,(last-first)/1e9*40+2)
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')
            self.assertFalse(part['scoutBatchSourceHoldState']['predictionInFlight'])

    def test_lost_release_ack_keeps_primary_failure_and_never_retries_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,lost_ack=True)
            with self.assertRaisesRegex((RuntimeError,OSError),'ACK lost'):
                run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual((len(bridge.actions),len(bridge.completed),bridge.hold_releases),(4,4,1))
            self.assertEqual(part['status'],'failed');self.assertEqual(bridge.commands[-1],'stop')
            self.assertTrue(recorder.closed);self.assertEqual(part['scoutBatchSourceHoldState']['phase'],'awaitingRelease')

    def test_pending_ground_failure_is_terminal_without_any_next_action(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder()
            bridge=HoldBridge(recorder,interrupt=lambda row:unavailable(row,'groundControlEvidence','recognition_failed'))
            with self.assertRaisesRegex((RuntimeError,ValueError),'ground interruption'):
                run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            self.assertEqual((len(bridge.actions),bridge.hold_releases),(4,1))
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')


class BatchSourceHoldAuditTests(unittest.TestCase):
    """Reuse one authentic inert two-endpoint trace for coherent full-audit corruptions."""
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,freeze_action=2)
            code,part,recorder,_,_=run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            if code:raise AssertionError(part)
            cls.trace=(part,{row['frameId']:row for row,_ in recorder.frames},recorder.events)

    def replay(self,trace):
        """Run the complete original history/guard/endpoint audit with only file-proof admission substituted."""
        part,frames,rows=copy.deepcopy(trace)
        part['leaseInitialGoalState']=copy.deepcopy(part['initialGoalState'])
        reuse=dict(routeId=BATCH.route_id,navigationProfile=BATCH.profile_id,routeSpec=BATCH.document(),
            routeSpecSha256=BATCH.sha256,historyCommitMode=batch_tests.stream_tests.MODE,actionHoldMs=50,
            reviewedScoutBatchPolicy=reviewed_batch_policy(source_hold=True),scoutEncounterGuard=part['scoutEncounterGuard'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);recording=root/'recording'/'00001';recording.mkdir(parents=True)
            (recording/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
            (recording/'observations.jsonl').write_text('\n'.join(json.dumps(row) for row in frames.values()))
            (root/'part.json').write_text(json.dumps(part))
            run=dict(part,evidenceComplete=True,modelLoads=0,segments=[dict(number=1,report='part.json')])
            (root/'run.json').write_text(json.dumps(run))
            with patch.object(batch_tests.audit_module,'verify_policy_reuse',return_value=reuse):
                return batch_tests.audit_module.audit(root/'run.json',recording.parent,repository=root,minimum_legs=2,
                    reviewed_scout_route=BATCH,policy_reuse_proof=root/'inert-proof.json')

    def test_complete_two_endpoint_hold_trace_replays_without_history_reset(self):
        result=self.replay(self.trace)
        self.assertEqual((result['verifiedLegs'],result['acceptedActions'],result['batchSourceHold']['holds']),(2,6,1))
        self.assertTrue(result['batchSourceHold']['retainedExecutedHistory'])
        self.assertFalse(result['batchSourceHold']['physicalInputDeliveryVerified'])

    def test_coherent_transaction_removal_cannot_hide_prediction_or_dispatch(self):
        trace=copy.deepcopy(self.trace)
        trace[0]['scoutBatchSourceHoldEvents'][:]=[row for row in trace[0]['scoutBatchSourceHoldEvents'] if not row['type'].endswith('Transaction')]
        trace[2][:]=[row for row in trace[2] if row.get('type')!='scoutBatchSourceHoldTransaction']
        with self.assertRaisesRegex(ValueError,r'^(Source-hold transactions do not cover every original prediction/history result|Source-hold endpoint is missing or repeated)$'):self.replay(trace)

    def test_begin_moved_after_real_prediction_refuses_even_when_report_matches(self):
        trace=copy.deepcopy(self.trace);decision=trace[0]['decisions'][3]
        for rows in (trace[0]['scoutBatchSourceHoldEvents'],trace[2]):
            marker=next(row for row in rows if row.get('type')=='scoutBatchSourceHoldTransaction'
                        and row['phase']=='begin' and row['frameId']==decision['frameId'])
            marker['clientTimeNs']=decision['frameTiming']['predictionStartedAtClientNs']+1
        with self.assertRaisesRegex(ValueError,'precede'):self.replay(trace)

    def test_coherent_wrong_clock_target_receipt_and_confirmation_refuse(self):
        for key,value in (('deadlineClientNs',999999999999999999),('target',list(BATCH.points[2])),
                          ('lastAcceptedClientNs',999999999999999999),('historyCommits',0)):
            trace=copy.deepcopy(self.trace)
            for rows in (trace[0]['scoutBatchSourceHoldEvents'],trace[2]):
                for row in rows:
                    if str(row.get('type','')).startswith('scoutBatchSourceHold') and 'runtime' in row:row['runtime'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.replay(trace)


class SourceHoldEndpointBeforePredictionTests(unittest.TestCase):
    """A hold completing at a waypoint must use the existing verified endpoint, never an arbitrary phase."""
    replay=BatchSourceHoldAuditTests.replay
    @classmethod
    def setUpClass(cls):
        """Retain one cold-adapter action3 trace with both subsequent endpoint and next-leg input."""
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,freeze_action=3)
            code,part,recorder,_,policy=run_hold_fixture(folder,bridge=bridge,recorder=recorder,policy=ColdBackupPolicy())
            if code:raise AssertionError(part)
            cls.trace=(part,{row['frameId']:row for row,_ in recorder.frames},recorder.events)
            cls.closed=recorder.closed;cls.commands=bridge.commands;cls.cold=policy.cold_prediction_entries

    def endpoint_machine(self):
        """Replay the original hold packets up to the exact endpoint marker without a new native call."""
        part,frames,rows=self.trace;events=part['scoutBatchSourceHoldEvents']
        machine=BatchSourceHold(batch_source_hold_policy(),BATCH.profile_id,BATCH.sha256,part['hello'],part['scoutEncounterGuard'])
        trigger=next(row for row in events if row['type']=='scoutBatchSourceHoldTrigger');prior=trigger['previous']
        machine.remember_healthy(prior['frame'],prior['clientTimeNs'],prior['roundTripMs'],dict(state='ready'))
        machine.observe(trigger['frame'],trigger['clientTimeNs'],trigger['runtime'],trigger['roundTripMs'])
        for row in events:
            if row['type']=='scoutBatchSourceHoldRelease':
                machine.acknowledge_release(row['response'],row['payloadBytes'],row['clientTimeNs'],row['runtime'])
            elif row['type']=='scoutBatchSourceHoldObservation':
                machine.observe(row['frame'],row['clientTimeNs'],row['runtime'],row['roundTripMs'])
            elif row['type']=='scoutBatchSourceHoldEndpoint':return machine,copy.deepcopy(row)
        raise AssertionError('Missing real endpoint retirement marker')

    def test_cold_action3_hold_endpoint_and_next_leg_complete_with_full_replay(self):
        part,frames,rows=self.trace;result=self.replay(self.trace)
        self.assertEqual((result['verifiedLegs'],result['acceptedActions'],result['batchSourceHold']['holds']),(2,6,1))
        self.assertEqual(self.cold,[True,False,False,False,False,False])
        self.assertTrue(self.closed);self.assertEqual(self.commands[-1],'stop')
        machine,row=self.endpoint_machine();floors=copy.deepcopy(machine.sources);prior=copy.deepcopy(machine.runtime)
        self.assertTrue(machine.selection_barrier)
        self.assertEqual(machine.verified_endpoint(row['endpoint'],row['transition'],row['frame'],row['clientTimeNs']),row)
        self.assertFalse(machine.selection_barrier);self.assertEqual(machine.used,1)
        self.assertEqual(machine.sources,floors);self.assertEqual(machine.runtime,prior)
        self.assertFalse(machine.selected_after_release(machine.trigger['frame']))
        self.assertTrue(machine.selected_after_release(row['frame']))
        marker_index=rows.index(row);endpoint_index=rows.index(row['endpoint'])
        self.assertLess(endpoint_index,marker_index)
        self.assertEqual([event['history']['afterFrames'] for event in part['executedHistoryEvents']],[1,2,3,1,2,3])

    def test_unmatched_endpoint_old_source_epoch_release_or_reset_cannot_clear_barrier(self):
        def unmatched(row,machine):row['endpoint']['completedLegs']+=1
        def old_source(row,machine):row['frame']=copy.deepcopy(machine.sources[-1]['frame'])
        def foreign_source(row,machine):
            def replace(value):
                if isinstance(value,dict):
                    for key,item in value.items():
                        if key=='captureEpoch':value[key]='foreign-capture'
                        else:replace(item)
                elif isinstance(value,list):
                    for item in value:replace(item)
            replace(row['frame'])
        def old_epoch(row,machine):
            for name in ('worldReadiness','frameWorldReadiness'):row['frame'][name]['epoch']-=1
        def wrong_release(row,machine):row['transition']['executedHistoryReset']['release']['worldReadiness']['epoch']+=1
        def changed_reset(row,machine):row['transition']['executedHistoryReset']['before']['afterFrames']+=1
        def wrong_transition(row,machine):row['transition']['reason']='worldTransition'
        for mutate in (unmatched,old_source,foreign_source,old_epoch,wrong_release,changed_reset,wrong_transition):
            machine,row=self.endpoint_machine();mutate(row,machine)
            with self.subTest(mutation=mutate.__name__),self.assertRaises(ValueError):
                machine.verified_endpoint(row['endpoint'],row['transition'],row['frame'],row['clientTimeNs'])
            self.assertTrue(machine.selection_barrier);self.assertEqual(machine.used,1)

    def test_missing_or_detached_endpoint_marker_fails_complete_audit(self):
        for mutation in ('missing','before-endpoint','unmatched-copy'):
            part,frames,rows=copy.deepcopy(self.trace)
            marker=next(row for row in rows if row.get('type')=='scoutBatchSourceHoldEndpoint')
            if mutation=='missing':
                rows.remove(marker);part['scoutBatchSourceHoldEvents'].remove(marker)
            elif mutation=='before-endpoint':
                rows.remove(marker);rows.insert(rows.index(marker['endpoint']),marker)
            else:
                marker['endpoint']['completedLegs']+=1
                next(row for row in part['scoutBatchSourceHoldEvents'] if row['type']=='scoutBatchSourceHoldEndpoint')['endpoint']['completedLegs']+=1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.replay((part,frames,rows))


class BatchSourceHoldRaceTests(unittest.TestCase):
    """Exercise interruption races through the real intake thread and original teardown."""
    def test_stale_during_prediction_keeps_the_existing_terminal_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder)
            policy=batch_tests.stream_tests.HistoryPolicy()
            def block_second_prediction():
                """Keep the first settled action armed while its next prediction owns the fence."""
                if len(policy.images)==2:
                    bridge.frozen=copy.deepcopy(bridge.last_row);time.sleep(.2)
            policy.during_predict=block_second_prediction
            with self.assertRaises((RuntimeError,ValueError)):
                run_hold_fixture(folder,bridge=bridge,policy=policy,recorder=recorder)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(len(bridge.actions),1);self.assertEqual(part['scoutBatchSourceHoldState']['used'],0)
            self.assertEqual(part['scoutEncounterGuardState']['trip']['reason'],'nativeSensorStale')
            self.assertEqual(bridge.commands[-1],'stop');self.assertTrue(recorder.closed)

    def test_stop_after_first_confirmation_keeps_fence_and_retires(self):
        import threading
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,delay_second=100)
            control=batch_tests.dormant_control(folder,frozen_goal=True);done=threading.Event();sent=threading.Event()
            def request_stop():
                """Use the normal control lock on a separate thread, never from the intake callback."""
                while not done.wait(.002):
                    if any(row.get('type')=='scoutBatchSourceHoldObservation' and row.get('qualified') for row in recorder.events):
                        control._observe(dict(version=1,runId=control.run_id,command='stop'),None);sent.set();return
            watcher=threading.Thread(target=request_stop);watcher.start()
            try:
                run_hold_fixture(folder,bridge=bridge,recorder=recorder,control=control)
            finally:done.set();watcher.join(2)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertTrue(sent.is_set());self.assertFalse(watcher.is_alive())
            self.assertEqual((len(bridge.actions),part['endReason']),(4,'userStop'))
            self.assertEqual(part['scoutBatchSourceHoldState']['sourceFrameIds'],[bridge.first_post['frameId']])
            self.assertEqual(bridge.commands[-1],'stop');self.assertTrue(recorder.closed)

    def test_late_ack_keeps_original_500ms_limit_and_cleanup(self):
        class DelayedAck(HoldBridge):
            def request(self,command,**arguments):
                """Delay only transport return after the simulated aggregate release has completed."""
                delayed=command=='release' and self.frozen is not None
                result=super().request(command,**arguments)
                if delayed:time.sleep(.4)
                return result
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=DelayedAck(recorder)
            with self.assertRaisesRegex((RuntimeError,ValueError),'500ms'):
                run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual((len(bridge.actions),bridge.hold_releases),(4,1))
            self.assertEqual(len(part['scoutBatchSourceHoldReleaseReplies']),1)
            self.assertEqual(bridge.commands[-1],'stop');self.assertTrue(recorder.closed)

    def test_recording_failure_retains_exact_ack_and_attempts_both_cleanup_operations(self):
        class FailingRecorder(batch_tests.stream_tests.HistoryRecorder):
            def event(self,event):
                """Fail only after the native reply has returned and been independently retained."""
                if event.get('type')=='scoutBatchSourceHoldRelease':raise OSError('synthetic source-hold journal failure')
                return super().event(event)
        with tempfile.TemporaryDirectory() as folder:
            recorder=FailingRecorder();bridge=HoldBridge(recorder)
            with self.assertRaisesRegex((RuntimeError,OSError),'journal failure'):
                run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual((len(bridge.actions),bridge.hold_releases),(4,1))
            self.assertEqual(part['scoutBatchSourceHoldReleaseReplies'][0]['response']['type'],'released')
            self.assertGreaterEqual(bridge.commands.count('release'),3)
            self.assertEqual(bridge.commands[-1],'stop');self.assertTrue(recorder.closed)

    def test_hold_completed_during_image_work_discards_pre_ack_selection(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,freeze_action=999,delay_second=0)
            policy=batch_tests.stream_tests.HistoryPolicy();blocked=[]
            # Block only pure image preparation while the receive thread owns
            # the exact stale-source hold and both post-ACK confirmations.
            calls=[]
            def convert(mode,shape,pixels):
                if len(policy.commits)==2 and not calls:
                    calls.append(True);blocked.append(bridge.last_row['frameId'])
                    bridge.frozen=copy.deepcopy(bridge.last_row);time.sleep(.32)
                    calls.append(time.perf_counter_ns())
                return pixels
            args=batch_tests.batch_arguments(folder,seconds=4);args.batch_source_hold=True;args.fps=40
            control=batch_tests.dormant_control(folder,frozen_goal=True)
            control.set_initial_goal(dict(instruction='fixed reviewed batch'),'ground-navigation')
            control.scout_encounter_guard=batch_tests.ScoutEncounterGuard(ground_binding())
            control.scout_batch_policy=reviewed_batch_policy(source_hold=True);control.scout_batch_route_sha256=BATCH.sha256
            from contextlib import ExitStack,redirect_stdout
            import io,sys
            with ExitStack() as stack:
                stack.enter_context(patch.dict(sys.modules,{'PIL':SimpleNamespace(Image=SimpleNamespace(frombytes=convert))}))
                stack.enter_context(patch.object(batch_tests.client_module,'Bridge',return_value=bridge))
                stack.enter_context(patch.object(batch_tests.client_module,'AsyncVideoRecorder',return_value=recorder))
                stack.enter_context(redirect_stdout(io.StringIO()))
                code=batch_tests.client_module.run_episode(args,policy,control)
            part=json.loads(Path(args.output).read_bytes())
            self.assertEqual((code,len(bridge.actions),bridge.hold_releases),(0,6,1))
            self.assertEqual(len(policy.images),6)
            self.assertTrue(calls)
            confirmations=[row for row in part['scoutBatchSourceHoldEvents'] if row['type'].endswith('Observation') and row['qualified']]
            self.assertLess(confirmations[-1]['clientTimeNs'],calls[-1])
            trigger=next(row for row in part['scoutBatchSourceHoldEvents'] if row['type'].endswith('Trigger'))
            later=[row for row in part['decisions'] if row['frameTiming']['predictionStartedAtClientNs']>trigger['clientTimeNs']]
            self.assertTrue(later);self.assertGreater(later[0]['frameId'],trigger['frame']['frameId'])


class BatchSourceHoldConfigurationTests(unittest.TestCase):
    """Bind the real worker configuration/fingerprint and explicit loaded-worker authority."""
    def test_real_configuration_retains_flag_and_conditional_source_archive(self):
        import scout_session as session
        with tempfile.TemporaryDirectory() as folder:
            args=batch_tests.batch_arguments(folder);checkpoint=Path(folder)/'inert.ckpt';checkpoint.write_bytes(b'inert')
            args.checkpoint=str(checkpoint);args.batch_source_hold=True
            original=session.file_sha
            with patch.object(session,'file_sha',side_effect=lambda path:session.OPEN_P2P_SHA256 if Path(path)==checkpoint else original(path)):
                enabled=session.model_contract(args)
                del args.batch_source_hold
                default=session.model_contract(args)
            self.assertIs(enabled['arguments']['batch_source_hold'],True)
            self.assertIn('scout_batch_source_hold.py',enabled['executedHistorySourceSha256'])
            self.assertNotIn('scout_batch_source_hold.py',default['executedHistorySourceSha256'])
            self.assertNotEqual(session.canonical_sha(enabled),session.canonical_sha(default))

    def test_actual_worker_request_and_private_control_keep_v2_authority(self):
        original=batch_tests.reviewed_batch_policy
        with patch.object(batch_tests,'reviewed_batch_policy',lambda profile=BATCH.profile_id:original(profile,source_hold=True)):
            case=batch_tests.ReviewedScoutBatchSessionTests(methodName='runTest')
            try:
                case.setUp();case.fixture.settings.allow_batch_source_hold=True
                result=case.fixture.run_worker()
                self.assertEqual((len(case.fixture.loads),len(case.fixture.starts),len(case.fixture.episodes)),(1,1,1))
                self.assertEqual(result['state'],'stopped')
                manifest=json.loads((case.fixture.settings.directory/'manifest.json').read_bytes())
                request=json.loads(next((case.fixture.settings.directory/'requests').glob('*.json')).read_bytes())
                self.assertIs(manifest['configuration']['arguments']['batch_source_hold'],True)
                self.assertEqual(manifest['reviewedScoutBatchPolicy'],request['reviewedScoutBatchPolicy'])
                self.assertEqual(request['reviewedScoutBatchPolicy']['version'],2)
            finally:case.doCleanups()




class HostTimingTests(unittest.TestCase):
    """Measure actual host boundaries without a GPU, native pipe, new input or altered clocks."""
    def test_actual_poll_separates_wake_intake_rpc_and_processing(self):
        """Run the exact nested poll body with deterministic costs for its existing dependencies."""
        from contextlib import nullcontext
        module=batch_tests.client_module;clock=SimpleNamespace(ns=0)
        def advance(ms):clock.ns+=int(ms*1e6)
        fake_time=SimpleNamespace(perf_counter_ns=lambda:clock.ns,perf_counter=lambda:clock.ns/1e9)
        class Lock:
            def __enter__(self):advance(5)
            def __exit__(self,*args):advance(3)
        class Recorder:
            event_count=0
            put_count=0
            def event(self,row):self.event_count+=1;advance(19);return True
            def put(self,*args):self.put_count+=1;advance(29)
        class Guard:
            def observe(self,*args):advance(17);return dict(state=dict(trip=None))
        def request(command):
            advance(7);return dict(type='frame',frameId=1,width=1,height=1),b'\x01\x02\x03'
        def validate(*args):advance(13)
        def verify(*args):advance(11)
        def collect(*args):advance(31)
        def publish(*args):advance(23)
        report=dict(captureQuality={'usableFrames':0},framesReceived=0)
        recorder=Recorder();observer=module.HostTimingObserver(report,clock=fake_time.perf_counter_ns)
        observer.start_gc();self.addCleanup(observer.stop_gc)
        tree=ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        node=copy.deepcopy(next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='poll_frame'))
        # Rebind the same closed-over variables into this isolated namespace; the poll body is unchanged.
        node.body=[ast.Global(names=n.names) if isinstance(n,ast.Nonlocal) else n for n in node.body]
        namespace=dict(time=fake_time,host_timing=observer,nullcontext=nullcontext,receive_lock=Lock(),
            combat_intake_boundary=nullcontext,bridge=SimpleNamespace(request=request),combat_guard=None,
            batch_source_hold=None,scout_guard=Guard(),report=report,recorder=recorder,host_contract=SimpleNamespace(validate=validate),
            verify_frame=verify,profile_contract={},native_combat_enabled=False,idle_recovery=SimpleNamespace(threshold=None),
            collect_receipts=collect,received_frame_id=None,rgb_frame_quality=lambda pixels:'usable',
            latest=SimpleNamespace(publish=publish),recording_frame_metadata=lambda metadata,*args,**kwargs:metadata,
            execution_mode='off',combat_source_recovery=False)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),module.__file__,'exec'),namespace)
        wake=dict(scheduledWakeNs=10_000_000,sleepStartedNs=0);advance(14);wake['sleepReturnedNs']=clock.ns
        namespace['poll_frame']('reader',wake);observer.finish();row=observer.state['events'][0]
        self.assertEqual(row['sleepReturnedNs']-row['scheduledWakeNs'],4_000_000)
        self.assertEqual(row['intakeAcquiredNs']-row['intakeRequestedNs'],5_000_000)
        self.assertEqual(row['rpcReturnedNs']-row['rpcStartedNs'],7_000_000)
        self.assertEqual(row['guardComputedNs']-row['rpcReturnedNs'],17_000_000)
        self.assertEqual(row['guardJournalQueuedNs']-row['guardComputedNs'],19_000_000)
        self.assertEqual(row['validationFinishedNs']-row['guardJournalQueuedNs'],24_000_000)
        self.assertEqual(row['receiptsCollectedNs']-row['validationFinishedNs'],31_000_000)
        self.assertEqual(row['latestPublishedNs']-row['receiptsCollectedNs'],23_000_000)
        self.assertEqual(row['recorderQueuedNs']-row['latestPublishedNs'],29_000_000)
        self.assertEqual(row['intakeScopeExitedNs']-row['recorderQueuedNs'],3_000_000)
        self.assertEqual(clock.ns,row['intakeScopeExitedNs'])
        self.assertEqual((recorder.event_count,recorder.put_count),(1,1))  # Only original guard/RGB recording.

    def test_receipt_visibility_feedback_aggregates_and_cached_gap_keep_original_history(self):
        """Use the real500ms branch; cached20-frame evidence never calls an adapter counter."""
        module=batch_tests.client_module;clock=SimpleNamespace(ns=1_500_000_000)
        fake_time=SimpleNamespace(perf_counter_ns=lambda:clock.ns,perf_counter=lambda:clock.ns/1e9)
        report=dict(executedHistoryEvents=[dict(history=dict(afterFrames=20,validFrames=20,afterValidTokens=240),
            clientTimeNs=1_328_000_000)])
        observer=module.HostTimingObserver(report,clock=fake_time.perf_counter_ns)
        receipt=dict(requestId='settled',frameId=500,endedAtMs=18065.6043)
        observer.receipt(receipt,dict(type='frame',frameId=511),dict(rpcReturnedNs=1_313_000_000))
        row=observer.new('hostFeedbackTiming',requestId='settled');observer.elapsed(row,'intakeWait',clock.ns-7)
        observer.elapsed(row,'intakeWait',clock.ns-3)
        event=dict(report['executedHistoryEvents'][-1],requestId='settled',outcome='committed')
        observer.feedback(row,event)
        self.assertEqual((row['intakeWaitCount'],row['intakeWaitTotalNs'],row['intakeWaitMaxNs']),(2,10,7))
        self.assertEqual(row['delivery']['replyAtClientNs'],1_313_000_000)
        self.assertEqual(row['history']['validFrames'],20);self.assertEqual(observer.deliveries,{})
        tree=ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        guard=next(n for n in ast.walk(tree) if isinstance(n,ast.If)
                   and 'execution_feedback' in ast.unparse(n.test) and 'last_accepted_at' in ast.unparse(n.test))
        namespace=dict(time=fake_time,host_timing=observer,gap_checked_before=clock.ns,
            policy=SimpleNamespace(execution_feedback=True),last_accepted_at=1.,history_gap_reset=False,
            executed_history=True,report=report,history_predecessor=dict(requestId='settled'),frame=dict(frameId=516))
        code=compile(ast.Module(body=[guard],type_ignores=[]),module.__file__,'exec')
        exec(code,namespace);self.assertNotIn('acceptanceGap',observer.state)
        clock.ns+=1;namespace['gap_checked_before']=clock.ns
        with self.assertRaisesRegex(RuntimeError,'cannot resume with empty history'):exec(code,namespace)
        gap=observer.state['acceptanceGap']
        self.assertEqual(gap['lastAcceptedClientNs'],1_000_000_000)
        self.assertEqual(gap['history'],event['history']);self.assertEqual(gap['predecessorRequestId'],'settled')
        self.assertEqual(namespace['last_accepted_at'],1.)

    def test_gc_observer_is_bounded_and_preserves_callbacks_and_settings(self):
        """Invoke only diagnostic callbacks, never force a real collection or change GC thresholds."""
        module=batch_tests.client_module;gc=module.gc;before=list(gc.callbacks)
        enabled,thresholds=gc.isenabled(),gc.get_threshold();report={}
        observer=module.HostTimingObserver(report,clock=lambda:123)
        foreign=lambda phase,info:None
        try:
            observer.start_gc();observer.start_gc();gc.callbacks.append(foreign)
            self.assertEqual(sum(row is observer._gc_callback for row in gc.callbacks),1)
            observer._gc_callback('start',dict(generation=0));self.assertEqual(len(observer.gc_events),0)
            for _ in range(observer.GC_LIMIT+5):observer._gc_callback('start',dict(generation=1))
            observer._gc_callback('stop',dict(generation=2));observer.stop_gc();observer.stop_gc();observer.finish()
            self.assertEqual(len(observer.state['gcEvents']),observer.GC_LIMIT)
            self.assertTrue(observer.state['gcEventsAtCapacity']);self.assertTrue(observer.state['gcRemoved'])
            self.assertEqual(gc.callbacks,before+[foreign])
            self.assertEqual((gc.isenabled(),gc.get_threshold()),(enabled,thresholds))
            for _ in range(observer.EVENT_LIMIT+5):observer.emit(dict(type='hostTestTiming'))
            observer.finish();self.assertEqual(len(observer.state['events']),observer.EVENT_LIMIT)
            self.assertTrue(observer.state['eventsAtCapacity'])
        finally:
            observer.stop_gc()
            if foreign in gc.callbacks:gc.callbacks.remove(foreign)
        self.assertEqual(gc.callbacks,before)

    def test_observer_clock_failure_preserves_body_error_and_removes_only_own_callback(self):
        """A diagnostic clock exception must not replace the original poll/native failure."""
        module=batch_tests.client_module;before=list(module.gc.callbacks)
        def broken_clock():raise OSError('diagnostic clock failed')
        observer=module.HostTimingObserver({},clock=broken_clock)
        try:
            observer.start_gc()
            with self.assertRaisesRegex(ValueError,'original poll failure'):
                with observer.poll('reader',None):raise ValueError('original poll failure')
            observer._gc_callback('start',dict(generation=1))
        finally:observer.stop_gc();observer.finish()
        self.assertTrue(observer.state['measurementError']);self.assertTrue(observer.state['gcRemoved'])
        self.assertEqual(observer.state['events'][0]['failureType'],'ValueError')
        self.assertEqual(module.gc.callbacks,before)

    def test_default_batch_has_no_observer_or_new_diagnostic_contract(self):
        """The existing opt-out path still completes the original endpoints without installing callbacks."""
        module=batch_tests.client_module;before=list(module.gc.callbacks)
        with tempfile.TemporaryDirectory() as folder:
            code,part,recorder,bridge,policy=batch_tests.run_batch_fixture(folder)
            self.assertEqual((code,len(bridge.actions)),(0,6))
            self.assertNotIn('hostTimingDiagnostics',part)
            self.assertFalse(any(row.get('type','').startswith('host') for row in recorder.events))
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')
        self.assertEqual(module.gc.callbacks,before)

    def test_cold_endpoint_path_retains_timing_receipt_pairs_and_removes_gc_observer(self):
        """Exercise action3 recovery, two real endpoints and the cold counter lifecycle with diagnostics."""
        module=batch_tests.client_module;before=list(module.gc.callbacks)
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,freeze_action=3)
            code,part,recorder,bridge,policy=run_hold_fixture(folder,bridge=bridge,recorder=recorder,policy=ColdBackupPolicy())
            self.assertEqual((code,len(bridge.actions),len(policy.commits)),(0,6,6))
            diagnostics=part['hostTimingDiagnostics'];rows=diagnostics['events']
            self.assertFalse(diagnostics['measurementError']);self.assertTrue(diagnostics['gcRegistered'])
            self.assertTrue(diagnostics['gcRemoved']);self.assertFalse(diagnostics['eventsAtCapacity'])
            polls=[row for row in rows if row['type']=='hostPollTiming'];self.assertTrue(polls)
            self.assertTrue(any(row['origin']=='reader' and 'scheduledWakeNs' in row for row in polls))
            self.assertFalse(any(row.get('type','').startswith('host') for row in recorder.events))
            calls=[row for row in rows if row['type']=='hostNativeCallTiming']
            deliveries=[row for row in rows if row['type']=='hostReceiptDeliveryTiming']
            feedback=[row for row in rows if row['type']=='hostFeedbackTiming']
            self.assertEqual((len(calls),len(deliveries),len(feedback)),(6,6,6))
            self.assertEqual({row['requestId'] for row in calls},{row['requestId'] for row in feedback})
            for row in feedback:
                self.assertEqual(row['delivery']['requestId'],row['requestId'])
                self.assertLessEqual(row['delivery']['startedAtClientNs'],row['receiptMatchedNs'])
                self.assertLessEqual(row['receiptMatchedNs'],row['terminalValidatedNs'])
                self.assertLessEqual(row['counterReadStartedNs'],row['historyRecordedAtClientNs'])
                self.assertLessEqual(row['historyRecordedAtClientNs'],row['counterReadFinishedNs'])
            trace=(part,{row['frameId']:row for row,_ in recorder.frames},recorder.events)
            self.assertEqual(BatchSourceHoldAuditTests.replay(self,trace)['verifiedLegs'],2)
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')
        self.assertEqual(module.gc.callbacks,before)

    def test_diagnostic_buffer_error_cannot_replace_lost_ack_or_prevent_cleanup(self):
        """A failed diagnostic append cannot alter original recording or hide the lost release reply."""
        from collections import deque
        module=batch_tests.client_module;before=list(module.gc.callbacks)
        class FailingBuffer(deque):
            def append(self,row):raise OSError('diagnostic-only memory failure')
        class Observer(module.HostTimingObserver):
            def __init__(self,report):
                super().__init__(report);self.events=FailingBuffer(maxlen=self.EVENT_LIMIT)
        with tempfile.TemporaryDirectory() as folder:
            recorder=batch_tests.stream_tests.HistoryRecorder();bridge=HoldBridge(recorder,lost_ack=True)
            with patch.object(module,'HostTimingObserver',Observer),self.assertRaisesRegex((RuntimeError,OSError),'ACK lost'):
                run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertTrue(part['hostTimingDiagnostics']['measurementError'])
            self.assertTrue(part['hostTimingDiagnostics']['gcRemoved'])
            self.assertIn('ACK lost',part.get('error','')+part.get('streamError',''))
            self.assertEqual((len(bridge.actions),bridge.hold_releases),(4,1))
            self.assertFalse(any(row.get('type','').startswith('host') for row in recorder.events))
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')
        self.assertEqual(module.gc.callbacks,before)

    def test_original_recorder_failure_still_stops_and_retires(self):
        """The original proposal-recorder failure still prevents any later action and cleans up."""
        class RecorderFailure(batch_tests.stream_tests.HistoryRecorder):
            def event(self,row):
                if row.get('type')=='proposal':
                    self.actions_at_failure=len(self.bridge.actions)
                    self.error='original proposal recorder failure';return False
                return super().event(row)
        module=batch_tests.client_module;before=list(module.gc.callbacks)
        with tempfile.TemporaryDirectory() as folder:
            recorder=RecorderFailure();bridge=HoldBridge(recorder);recorder.bridge=bridge
            with self.assertRaises((RuntimeError,ValueError)):
                run_hold_fixture(folder,bridge=bridge,recorder=recorder)
            part=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertFalse(part['hostTimingDiagnostics']['measurementError'])
            self.assertEqual(len(bridge.actions),recorder.actions_at_failure)
            self.assertTrue(recorder.closed);self.assertEqual(bridge.commands[-1],'stop')
        self.assertEqual(module.gc.callbacks,before)


if __name__=='__main__':unittest.main()
