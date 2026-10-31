"""Inert native-HUD guard, stream-race and independent replay tests; no game/model/process starts."""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import stream_client as client
from audit_hybrid_run import verify_scout_guard
from native_combat import CAPABILITY
from scout_encounter_guard import ScoutEncounterGuard,ScoutEncounterStop,binding_from_review,validate_binding
from test_native_combat import native_frame
from test_resident_goals import dormant_control
from test_stream_client import CapturingRecorder,FakePolicy,ScriptedBridge


def binding():
    """Use a fixed reviewed 90 percent health baseline independent of the sensor estimate."""
    return binding_from_review(dict(inspectedHealth=900,inspectedMaximumHealth=1000),'a'*64)


def sample(index=1, *, health=.9, candidates=False):
    """Create a complete same-source sensor result without image recognition or native capture."""
    frame=native_frame()
    source=dict(frame['sourceFrame'],timestamp100ns=index*1_000_000,
                capturedAtMs=index*100,acquiredAtMs=index*100+1,freshnessAtMs=index*100)
    frame.update(frameId=index,sourceFrame=source,sourceFrameAgeMs=1)
    frame['combatEvidence'].update(frameId=index,sourceFrame=copy.deepcopy(source),
        playerHealthFractionEstimate=health,enemyBarCandidates=frame['combatEvidence']['enemyBarCandidates'] if candidates else [])
    return frame


def release_ack(stamp=101,epoch=2):
    """Keep the exact native response and post-release readiness barrier available to replay."""
    return dict(type='released',serverNowMs=stamp,worldReadiness=dict(ready=False,epoch=epoch),receipts=[])


class GuardTests(unittest.TestCase):
    """Exercise stable baseline and terminal decisions across exact native source identities."""
    def test_binding_rejects_changed_settings_numeric_types_and_baseline(self):
        self.assertEqual(validate_binding(binding()),binding())
        for change in ('threshold','baseline','health','boolean','extra'):
            value=binding()
            if change=='threshold':value['policy']['maximumHealthFractionDrop']=.09
            if change=='baseline':value['baselineHealthFraction']=.8
            if change=='health':value['inspectedHealth']=True
            if change=='boolean':value['policy']['attacksAllowed']=0
            if change=='extra':value['renew']=True
            with self.subTest(change=change),self.assertRaises(ValueError):validate_binding(value)

    def test_startup_missing_evidence_waits_without_authorizing_dispatch(self):
        guard=ScoutEncounterGuard(binding())
        missing=sample();missing.pop('combatEvidence')
        state=guard.observe(missing,1)['state']
        self.assertEqual(state['state'],'waiting')
        with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(missing,2)
        guard.observe(sample(2),3)
        self.assertEqual(guard.check_dispatch(sample(2),4)['observationIndex'],2)

    def test_valid_candidates_red_ambiguous_and_health_drop_are_terminal(self):
        variants=[sample(2,candidates=True),sample(2,health=.82),sample(2),sample(2),sample(2)]
        variants[2]['combatEvidence']['playerHealthColor']='red'
        variants[3]['combatEvidence'].update(playerHealthColor='unknown',playerHealthFractionEstimate=None,
                                            playerHealthMatchingPixels=0)
        variants[4]['combatEvidence'].update(redMaskOverloaded=True,reason='red_mask_overloaded')
        for frame,reason in zip(variants,('enemyBarCandidate','reviewedHealthFractionDrop','redHealth',
                                         'ambiguousHealth','ambiguousEnemyBarEvidence')):
            guard=ScoutEncounterGuard(binding());guard.observe(sample(),1)
            event=guard.observe(frame,2)
            self.assertEqual(event['state']['trip']['reason'],reason)
            self.assertEqual(event['state']['trip']['frame']['combatEvidence'],frame['combatEvidence'])
            with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(sample(),3)
            with self.assertRaises(ScoutEncounterStop):guard.observe(sample(3),4)
            self.assertEqual(guard.snapshot(),event['state'])
        guard=ScoutEncounterGuard(binding());guard.observe(sample(health=.82001),1)
        self.assertEqual(guard.snapshot()['state'],'ready')

    def test_missing_unavailable_invalid_and_stale_after_admission_stop(self):
        variants=[sample(2) for _ in range(4)]
        variants[0].pop('combatEvidence')
        variants[1]['combatEvidence'].update(state='unavailable',reason='world_not_ready',
            playerHealthColor='unknown',playerHealthFractionEstimate=None,playerHealthMatchingPixels=0)
        variants[2]['combatEvidence']['frameId']=33
        variants[3]['sourceFrameAgeMs']=151
        for frame,reason in zip(variants,('nativeSensorUnavailable','nativeSensorUnavailable',
                                         'invalidNativeSensorEvidence','nativeSensorStale')):
            guard=ScoutEncounterGuard(binding());guard.observe(sample(),1);guard.check_dispatch(sample(),1)
            self.assertEqual(guard.observe(frame,2)['state']['trip']['reason'],reason)

    def test_repeated_sources_do_not_become_distinct_or_allow_changed_evidence(self):
        guard=ScoutEncounterGuard(binding());guard.observe(sample(),1)
        repeated=sample();repeated['frameId']=2;repeated['combatEvidence']['frameId']=2
        guard.observe(repeated,2)
        self.assertEqual(guard.distinct_sources,1)
        repeated['combatEvidence']['playerHealthFractionEstimate']=.89
        self.assertEqual(guard.observe(repeated,3)['state']['trip']['reason'],'nativeSensorEvidenceChanged')

    def test_source_generation_or_clock_regression_is_terminal(self):
        for frame in (sample(),sample(3)):
            guard=ScoutEncounterGuard(binding());guard.observe(sample(2),1)
            if frame['frameId']==3:
                frame['sourceFrame']['captureEpoch']='new'
                frame['combatEvidence']['sourceFrame']=copy.deepcopy(frame['sourceFrame'])
            self.assertEqual(guard.observe(frame,2)['state']['trip']['reason'],'nativeSensorSourceChanged')


    def test_acknowledged_release_waits_on_missing_sensor_and_requires_new_healthy_source(self):
        guard=ScoutEncounterGuard(binding());guard.observe(sample(),1);guard.check_dispatch(sample(),2)
        event=guard.acknowledge_release(release_ack(),0,3,'hybridEndpoint')
        self.assertFalse(event['state']['armed']);self.assertTrue(event['state']['admitted'])
        missing=sample(2);missing.pop('combatEvidence')
        self.assertIsNone(guard.observe(missing,4)['state']['trip'])
        self.assertEqual(guard.observe(sample(),5)['state']['state'],'waiting')
        with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(sample(),6)
        guard.observe(sample(3),7)
        with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(sample(),8)
        guard.check_dispatch(sample(3),9)
        self.assertTrue(guard.armed)
        self.assertEqual(guard.observe(missing,10)['state']['trip']['reason'],'nativeSensorUnavailable')

    def test_release_never_clears_hazards_or_accepts_an_unacknowledged_disarm(self):
        for change in ('type','payload','clock','readiness'):
            guard=ScoutEncounterGuard(binding());guard.observe(sample(),1);guard.check_dispatch(sample(),2)
            ack=release_ack();payload=0
            if change=='type':ack['type']='rejected'
            if change=='payload':payload=1
            if change=='clock':ack['serverNowMs']=99
            if change=='readiness':ack['worldReadiness']['ready']=True
            with self.subTest(change=change),self.assertRaises(ScoutEncounterStop):guard.acknowledge_release(ack,payload,3,'test')
            self.assertTrue(guard.armed)
        for hazardous in (sample(2,candidates=True),sample(2,health=.8)):
            guard=ScoutEncounterGuard(binding());guard.observe(sample(),1)
            guard.acknowledge_release(release_ack(),0,2,'hybridEndpoint')
            trigger=guard.observe(hazardous,3)['state']['trip']
            self.assertIsNotNone(trigger)
            guard.acknowledge_release(release_ack(201,3),0,4,'scoutEncounterGuard')
            self.assertEqual(guard.trip,trigger)
            with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(sample(3),5)

    def test_release_and_disarm_exclude_concurrent_sensor_intake(self):
        guard=ScoutEncounterGuard(binding());guard.observe(sample(),1);guard.check_dispatch(sample(),2)
        returned,finish,reading,read_done=threading.Event(),threading.Event(),threading.Event(),threading.Event()
        errors=[];recorder=CapturingRecorder();report={}
        def request(command):
            """Hold the simulated native reply after release while a reader attempts intake."""
            returned.set();self.assertTrue(finish.wait(1));return release_ack(),b''
        def release():
            """Exercise the runtime release/disarm wrapper, capturing worker failures."""
            try:client.scout_release(SimpleNamespace(request=request),guard,report,recorder,'hybridEndpoint')
            except Exception as error:errors.append(error)
        def intake():
            """A readiness-reset frame cannot observe the guard's old armed state."""
            reading.set()
            with guard.intake_lock:
                frame=sample(2);frame.pop('combatEvidence')
                recorder.event(guard.observe(frame,sys.maxsize));read_done.set()
        writer=threading.Thread(target=release);reader=threading.Thread(target=intake)
        writer.start();self.assertTrue(returned.wait(1));reader.start();self.assertTrue(reading.wait(1))
        try:self.assertFalse(read_done.wait(.03))
        finally:finish.set();writer.join(1);reader.join(1)
        self.assertFalse(errors);self.assertTrue(read_done.is_set());self.assertIsNone(guard.trip)
        self.assertFalse(guard.armed)
        self.assertEqual([event['type'] for event in recorder.events],['scoutEncounterGuardRelease','scoutEncounterGuardObservation'])

    def test_malformed_nonfinite_sensor_keeps_serializable_terminal_metadata(self):
        guard=ScoutEncounterGuard(binding());frame=sample(health=float('nan'))
        event=guard.observe(frame,1)
        self.assertEqual(event['state']['trip']['reason'],'invalidNativeSensorEvidence')
        self.assertIn('invalidNativeNumber',event['frame']['combatEvidence']['playerHealthFractionEstimate'])
        json.dumps(event,allow_nan=False)


class GuardBridge(ScriptedBridge):
    """Provide native metadata alongside tiny inert policy pixels and observable release acknowledgements."""
    def __init__(self, transform=lambda frame:frame):
        super().__init__([bytes(range(12))])
        self.transform=transform
        self.actions=[]
        self.released=threading.Event()
        self.epoch=1
        self.hello.update(supportsRelease=True,combatObservation=copy.deepcopy(CAPABILITY))

    def request(self,command,**kwargs):
        if command=='enableCombatObservation':
            self.commands.append(command)
            return dict(type='combatObservation',enabled=True,capability=copy.deepcopy(CAPABILITY)),b''
        if command=='release':
            self.commands.append(command);self.released.set()
            self.epoch+=1
            return dict(type='released',serverNowMs=self.count*100+1,
                        worldReadiness=dict(ready=False,epoch=self.epoch),receipts=[]),b''
        if command=='action':self.actions.append(copy.deepcopy(kwargs))
        frame,pixels=super().request(command,**kwargs)
        if command=='frame':
            native=sample(self.count)
            frame.update(native)
            frame.update(capturedAtMs=native['sourceFrame']['capturedAtMs'],
                         serverNowMs=native['sourceFrame']['capturedAtMs']+1)
            frame=self.transform(frame)
        return frame,pixels


class StreamGuardTests(unittest.TestCase):
    """Run the actual intake/inference/dispatch loop against only memory transports and a CPU policy stub."""
    def run_inert(self,folder,bridge,policy,recorder, *, seconds=.12,control=None):
        control=control or dormant_control(folder,frozen_goal=True)
        control.set_initial_goal({'instruction':'fixed scout'},'ground-navigation')
        control.scout_encounter_guard=ScoutEncounterGuard(binding())
        args=client.parse_arguments(['--seconds',str(seconds),'--fps','100','--decision-hz','100',
            '--model','open-p2p','--source','inert','--checkpoint','inert','--enable-input',
            '--native-combat-observation','--action-hold-ms','100','--max-input-actions','2',
            '--record-dir',str(Path(folder)/'recording'),'--output',str(Path(folder)/'run.json')])
        args.scout_encounter_guard=binding()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{'PIL':SimpleNamespace(
                Image=SimpleNamespace(frombytes=lambda mode,shape,pixels:pixels))}))
            stack.enter_context(patch.object(client,'Bridge',return_value=bridge))
            stack.enter_context(patch.object(client,'AsyncVideoRecorder',return_value=recorder))
            stack.enter_context(redirect_stdout(io.StringIO()))
            return client.run_episode(args,policy,control)

    def test_normal_navigation_stays_bounded_and_binds_dispatches(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge,policy,recorder=GuardBridge(),FakePolicy(),CapturingRecorder()
            self.assertEqual(self.run_inert(folder,bridge,policy,recorder),0)
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(len(bridge.actions),2)
            self.assertTrue(all(action['steps'][0]['keys']==['W'] and action['steps'][0]['durationMs']==100
                                for action in bridge.actions))
            self.assertTrue(all('scoutEncounterGuard' in row for row in report['decisions']))
            self.assertIsNone(report['scoutEncounterGuardState']['trip'])

    def test_missing_startup_sensor_never_calls_policy_or_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            def absent(frame):
                """Keep the native stream otherwise healthy while omitting its optional sensor."""
                frame.pop('combatEvidence');return frame
            bridge,policy=GuardBridge(absent),FakePolicy()
            self.assertEqual(self.run_inert(folder,bridge,policy,CapturingRecorder(),seconds=.06),1)
            self.assertEqual((policy.images,bridge.actions),([],[]))
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertFalse(report['scoutEncounterGuardState']['admitted'])

    def test_explicit_pause_release_waits_for_healthy_reconfirmation_before_next_action(self):
        with tempfile.TemporaryDirectory() as folder:
            control=dormant_control(folder,frozen_goal=True)
            class PausingBridge(GuardBridge):
                """Return two readiness-reset frames after the acknowledged operator release."""
                missing=0
                def request(self,command,**kwargs):
                    frame,pixels=super().request(command,**kwargs)
                    if command=='release':
                        self.missing=2
                        with control._lock:control._command='run';control._epoch+=1
                    elif command=='frame' and self.missing:
                        frame.pop('combatEvidence');self.missing-=1
                    return frame,pixels
            bridge=PausingBridge();recorder=CapturingRecorder();policy=FakePolicy()
            policy.execution_feedback=True;policy.reset=lambda:None
            feedback=[]
            def finish_action(accepted):
                """Pause after the first acknowledged action, outside the resident's submission lock."""
                feedback.append(accepted)
                if accepted and len(feedback)==1:
                    with control._lock:control._command='pause';control._epoch+=1
            policy.finish_action=finish_action
            self.assertEqual(self.run_inert(folder,bridge,policy,recorder,seconds=.4,control=control),0)
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(len(bridge.actions),2);self.assertEqual(report['scoutEncounterGuardState']['releases'],1)
            self.assertIsNone(report['scoutEncounterGuardState']['trip'])
            waiting=[event for event in recorder.events if event.get('type')=='scoutEncounterGuardObservation'
                     and event['state']['reason']=='nativeSensorUnavailable']
            self.assertEqual(len(waiting),2)
            self.assertTrue(all(event['state']['admitted'] and not event['state']['armed'] for event in waiting))

    def test_hazard_during_inference_releases_before_return_and_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            entered=threading.Event()
            def hazard(frame):
                """The next independently ingested frame changes only after inference starts."""
                if entered.is_set():frame['combatEvidence']['enemyBarCandidates']=sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                return frame
            bridge=GuardBridge(hazard)
            def during_predict():
                """Block a CPU prediction until the reader has latched the hazard and released."""
                entered.set()
                self.assertTrue(bridge.released.wait(2))
            recorder=CapturingRecorder()
            with self.assertRaisesRegex(ScoutEncounterStop,'enemyBarCandidate'):
                self.run_inert(folder,bridge,FakePolicy(during_predict),recorder,seconds=.3)
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(bridge.actions,[])
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['endReason'],'scoutEncounterGuard')
            self.assertEqual(report['scoutEncounterGuardRelease']['type'],'released')
            self.assertEqual(report['scoutEncounterGuardState']['trip']['reason'],'enemyBarCandidate')
            trigger=report['scoutEncounterGuardState']['trip']['frame']
            saved=[(frame,pixels) for frame,pixels in recorder.frames if frame['frameId']==trigger['frameId']]
            self.assertEqual(len(saved),1)
            self.assertEqual(saved[0][1],bytes(range(12)))
            self.assertEqual(saved[0][0]['sourceFrame'],trigger['sourceFrame'])
            self.assertEqual(saved[0][0]['combatEvidence'],trigger['combatEvidence'])
            self.assertTrue(report['scoutEncounterGuardTriggerRecorded'])
            self.assertEqual(bridge.commands[-1],'stop')
            self.assertTrue(any(event.get('state',{}).get('trip') for event in recorder.events))

    def test_trigger_metadata_survives_an_unrelated_frame_validation_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            def malformed(frame):
                """A dangerous frame also has broken RGB dimensions, so its trigger must be stored first."""
                frame['combatEvidence']['enemyBarCandidates']=sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                frame['width']=999
                return frame
            bridge=GuardBridge(malformed)
            with self.assertRaisesRegex(ScoutEncounterStop,'enemyBarCandidate'):
                self.run_inert(folder,bridge,FakePolicy(),CapturingRecorder())
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(report['scoutEncounterGuardState']['trip']['frame']['frameId'],1)
            self.assertIn('scoutEncounterGuardTriggerCaptureError',report)
            self.assertEqual(bridge.actions,[])

    def test_trigger_receipt_failure_cannot_skip_release_or_erase_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            def hazardous(frame):
                """Cause receipt processing to fail only after the hazardous pixels are retained."""
                frame['combatEvidence']['enemyBarCandidates']=sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                frame['receipts']=[None]
                return frame
            bridge=GuardBridge(hazardous);recorder=CapturingRecorder()
            policy=FakePolicy();policy.execution_feedback=True
            with self.assertRaisesRegex(ScoutEncounterStop,'enemyBarCandidate'):
                self.run_inert(folder,bridge,policy,recorder)
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertIn('scoutEncounterGuardTriggerReceiptError',report)
            self.assertTrue(report['scoutEncounterGuardTriggerRecorded'])
            self.assertIn('release',bridge.commands)
            self.assertEqual(bridge.actions,[])

    def test_trigger_journal_failure_still_releases_and_retains_terminal_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            class FailingRecorder(CapturingRecorder):
                """Fail the first hazard journal append before any pixel retention is possible."""
                def event(self,event):
                    if event.get('type')=='scoutEncounterGuardObservation' and event['state']['trip']:
                        raise RuntimeError('inert hazard recorder failure')
                    super().event(event)
            def hazardous(frame):
                """Produce a valid candidate without contacting native capture."""
                frame['combatEvidence']['enemyBarCandidates']=sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                return frame
            bridge=GuardBridge(hazardous)
            with self.assertRaisesRegex(ScoutEncounterStop,'enemyBarCandidate'):
                self.run_inert(folder,bridge,FakePolicy(),FailingRecorder())
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(report['scoutEncounterGuardState']['trip']['reason'],'enemyBarCandidate')
            self.assertIn('inert hazard recorder failure',report['scoutEncounterGuardTriggerCaptureError'])
            self.assertEqual(report['scoutEncounterGuardRelease']['type'],'released')
            self.assertEqual(bridge.actions,[])


class ClimbGuardTests(unittest.TestCase):
    """Gate the existing X recovery without loading a model, bridge or capture device."""
    def fixture(self):
        """Compose the actual recovery coordinator with a guarded inert resident control."""
        from test_navigation_climb_stream import Control,Fixture
        control=Control();control.scout_encounter_guard=ScoutEncounterGuard(binding())
        fixture=Fixture(control);fixture.value.recorder=CapturingRecorder()
        return fixture

    def tick(self,fixture,stamp,motion='climb',receipts=(),available=True):
        """Deliver native sensor intake before the exact recovery tick, under its normal source clock."""
        def intake(frame):
            """Attach validated source-bound HUD evidence to the existing synthetic climb observation."""
            evidence=sample()['combatEvidence']
            evidence.update(frameId=frame['frameId'],sourceFrame=copy.deepcopy(frame['sourceFrame']))
            frame.update(type='frame',sourceWidth=evidence['sourceWidth'],sourceHeight=evidence['sourceHeight'],
                         sourceFrameAgeMs=10,combatEvidence=evidence)
            if not available:frame.pop('combatEvidence')
            fixture.value.recorder.event(fixture.control.scout_encounter_guard.observe(frame,fixture.clock.ns))
        return fixture.tick(stamp,motion,receipts=receipts,mutate=intake)

    def test_x_dispatch_and_both_acknowledged_releases_share_guard_journal(self):
        fixture=self.fixture();guard=fixture.control.scout_encounter_guard
        self.tick(fixture,1000);self.tick(fixture,1060)
        self.assertFalse(guard.armed);self.assertEqual(guard.releases,1)
        self.assertTrue(self.tick(fixture,1100,available=False))
        self.assertIsNone(guard.trip)
        self.assertFalse(any(command=='action' for command,_,_ in fixture.bridge.calls))
        self.tick(fixture,1130)
        self.assertTrue(guard.armed)
        row=fixture.report['navigationClimbActions'][0]
        self.assertEqual(row['arguments']['steps'][0]['keys'],['X'])
        self.assertEqual(row['scoutEncounterGuard']['frameId'],row['frameId'])
        fixture.clock.ns=1_270_000_000
        self.tick(fixture,1260,receipts=fixture.bridge.terminal())
        self.assertFalse(guard.armed);self.assertEqual(guard.releases,2)
        self.tick(fixture,1330,'normal');self.tick(fixture,1390,'normal')
        self.assertFalse(fixture.value.helper.blocks_model);self.assertIsNone(guard.trip)
        self.assertEqual(sum(event['type']=='scoutEncounterGuardDispatch' for event in fixture.value.recorder.events),1)

    def test_hazard_latched_at_final_x_submit_prevents_input_and_preserves_cleanup_trip(self):
        fixture=self.fixture();guard=fixture.control.scout_encounter_guard
        self.tick(fixture,1000);self.tick(fixture,1060)
        original=fixture.control.guarded_submit
        def trip_before_submit(token,submit):
            """Represent a newer producer trip after recovery selection but before its final transmission."""
            hazardous=copy.deepcopy(guard.last['frame'])
            hazardous['combatEvidence']['enemyBarCandidates']=sample(candidates=True)['combatEvidence']['enemyBarCandidates']
            # A distinct newer source must win over the selected healthy frame.
            source=hazardous['sourceFrame'];source['timestamp100ns']+=10000
            for key in ('capturedAtMs','acquiredAtMs','freshnessAtMs'):source[key]+=1
            hazardous['combatEvidence']['sourceFrame']=copy.deepcopy(source)
            guard.observe(hazardous,fixture.clock.ns+1)
            return original(token,submit)
        fixture.control.guarded_submit=trip_before_submit
        with self.assertRaisesRegex(RuntimeError,'enemyBarCandidate|recovery_failed'):
            self.tick(fixture,1130)
        self.assertFalse(any(command=='action' for command,_,_ in fixture.bridge.calls))
        self.assertEqual(guard.trip['reason'],'enemyBarCandidate')
        self.assertFalse(guard.armed)
        self.assertEqual(guard.releases,2)


class GuardAuditTests(unittest.TestCase):
    """Replay the exact guard journal and reject source, dispatch-boundary and policy substitutions."""
    def fixture(self,folder):
        guard=ScoutEncounterGuard(binding())
        frames={index:sample(index) for index in (1,2)}
        events=[guard.observe(frames[index],index*100) for index in frames]
        marker=guard.check_dispatch(frames[2],201)
        events.append(dict(type='scoutEncounterGuardDispatch',requestId='inert-action',marker=marker,
                           frame=copy.deepcopy(frames[2]),state=guard.snapshot()))
        part=dict(scoutEncounterGuard=binding(),scoutEncounterGuardState=guard.snapshot(),
                  decisions=[dict(frameId=2,acceptance={'type':'accepted','requestId':'inert-action'},scoutEncounterGuard=marker)])
        path=Path(folder)/'00001'/'events.jsonl';path.parent.mkdir()
        path.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
        return dict(scoutEncounterGuardState=guard.snapshot()),part,frames,events,path

    def test_normal_intake_replays_and_changed_source_or_dispatch_cannot_pass(self):
        for change in ('none','sensor','source','dispatch','missing','policy','trip'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                run,part,frames,events,path=self.fixture(folder)
                if change=='sensor':events[0]['frame']['combatEvidence']['playerHealthFractionEstimate']=.7
                if change=='source':frames[1]['sourceFrame']['timestamp100ns']+=1
                if change=='dispatch':part['decisions'][0]['scoutEncounterGuard']['observationIndex']=1
                if change=='missing':events.pop(0)
                if change=='policy':part['scoutEncounterGuard']['policy']['maximumHealthFractionDrop']=.2
                if change=='trip':run['scoutEncounterGuardState']['trip']={'reason':'enemyBarCandidate'}
                path.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
                invoke=lambda:verify_scout_guard(run,[part],frames,[{'number':1}],folder,{'scoutEncounterGuard':binding()})
                if change=='none':self.assertEqual(invoke()['observations'],2)
                else:
                    with self.assertRaises((ValueError,ScoutEncounterStop)):invoke()

    def test_historical_recordings_are_not_reinterpreted_as_guarded(self):
        self.assertIsNone(verify_scout_guard({},[{}],{},[],'unused',{}))
        with self.assertRaises(ValueError):verify_scout_guard({},[{'scoutEncounterGuard':binding()}],{},[],'unused',{})

    def test_historical_downgrade_rejects_state_release_dispatch_and_journal_remnants(self):
        """Stripping declarations cannot hide a trip or a guard gate retained elsewhere in the recording."""
        cases=('clean','runTrip','partTrip','runRelease','partRelease','decision','climb','nullBinding',
               'frameMarker','endReason','observationEvent','releaseEvent','dispatchEvent','proposalMarker')
        for change in cases:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                run={};part={};reuse={};frames={1:sample()}
                events=[dict(type='combatObserverFrame',combatEvidence=sample(candidates=True)['combatEvidence'])]
                if change=='runTrip':run['scoutEncounterGuardState']=dict(trip=dict(reason='enemyBarCandidate'))
                if change=='partTrip':part['scoutEncounterGuardState']=dict(trip=dict(reason='enemyBarCandidate'))
                if change=='runRelease':run['scoutEncounterGuardRelease']=release_ack()
                if change=='partRelease':part['scoutEncounterGuardRelease']=release_ack()
                if change=='decision':part['decisions']=[dict(scoutEncounterGuard={'bindingSha256':'a'*64})]
                if change=='climb':part['navigationClimbActions']=[dict(scoutEncounterGuard={'bindingSha256':'a'*64})]
                if change=='nullBinding':reuse['scoutEncounterGuard']=None
                if change=='frameMarker':frames[1]['scoutEncounterGuardState']=None
                if change=='endReason':run['endReason']='scoutEncounterGuard'
                if change.endswith('Event'):
                    events.append(dict(type='scoutEncounterGuard'+change.removesuffix('Event').capitalize()))
                if change=='proposalMarker':events.append(dict(type='proposal',decision=dict(scoutEncounterGuard=None)))
                path=Path(folder)/'00001'/'events.jsonl';path.parent.mkdir()
                path.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
                invoke=lambda:verify_scout_guard(run,[part],frames,[{'number':1}],folder,reuse)
                if change=='clean':self.assertIsNone(invoke())
                else:
                    with self.assertRaisesRegex(ValueError,'undeclared encounter guard'):invoke()

    def test_released_wait_rearm_and_x_dispatch_replay_with_exact_acknowledgements(self):
        for change in ('none','missingRelease','changedAck','climbMarker','preReleaseSource'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                guard=ScoutEncounterGuard(binding());frames={index:sample(index) for index in (1,2,3)}
                frames[2].pop('combatEvidence')
                events=[guard.observe(frames[1],100)]
                def dispatch(index,request_id,at):
                    """Use the same journal shape for ordinary W and existing bounded X recovery."""
                    marker=guard.check_dispatch(frames[index],at)
                    events.append(dict(type='scoutEncounterGuardDispatch',requestId=request_id,marker=copy.deepcopy(marker),
                                       frame=copy.deepcopy(frames[index]),state=guard.snapshot()))
                    return dict(frameId=index,acceptance=dict(type='accepted',requestId=request_id),scoutEncounterGuard=marker)
                decision=dispatch(1,'walk',101)
                events.append(guard.acknowledge_release(release_ack(),0,102,'hybridEndpoint'))
                events.extend(guard.observe(frames[index],index*100) for index in (2,3))
                climb=dispatch(3,'drop',301)
                events.append(guard.acknowledge_release(release_ack(301,3),0,302,'climbRecovery'))
                part=dict(scoutEncounterGuard=binding(),scoutEncounterGuardState=guard.snapshot(),
                          decisions=[decision],navigationClimbActions=[climb])
                run=dict(scoutEncounterGuardState=guard.snapshot())
                if change=='missingRelease':events.pop(2)
                if change=='changedAck':events[2]['response']['worldReadiness']['ready']=True
                if change=='climbMarker':climb.pop('scoutEncounterGuard')
                if change=='preReleaseSource':events[-2]['frame']=copy.deepcopy(frames[1])
                path=Path(folder)/'00001'/'events.jsonl';path.parent.mkdir()
                path.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
                invoke=lambda:verify_scout_guard(run,[part],frames,[{'number':1}],folder,{'scoutEncounterGuard':binding()})
                if change=='none':self.assertEqual(invoke()['releases'],2)
                else:
                    with self.assertRaises((ValueError,ScoutEncounterStop)):invoke()


if __name__=='__main__':unittest.main()
