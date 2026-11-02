"""Inert current-scene captures; no native process, GPU query, model or game input is used."""
import copy
from contextlib import ExitStack,redirect_stderr,redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import capture_scout_scene as capture
import scout_session as scout
from combat_trial_guard import bind_review,canonical
from hybrid_routes import SCOUT_GRASS_ROUTE
from native_combat import CAPABILITY
from navigation_profiles import NORTH_SCOUT_PROFILE,SCOUT_PROFILE,scout_scope
from reviewed_scout_route import CURRENT_SCENE_INSPECTION,ReviewedScoutRoute,reviewed_route_policy
from test_combat_trial_guard import OWNER,frame,review_parts
from test_navigation_profiles import route_capability


def scene_frame(index,point=(-1200,2450),candidates=1):
    """Join a stable in-scope native pose to the existing full HUD/source fixture."""
    value=frame(index,index*100,candidates=candidates)
    value.update(executionContext=dict(lastSequence=0),motionEvidence=dict(status='normal',spaceKeyMatched=False),
        navigationPose=dict(state='valid',frameId=index,x=point[0],y=point[1],layerId='MapBack_2',
            positionConfidence=.999,yawConfidence=.8,yawDegrees=197.))
    return value


class PassiveSceneBridge:
    """Expose only passive stream commands and retain a synthetic native PNG plus exact sidecar."""
    def __init__(self,app,frames):
        """Keep all artifacts inside the isolated test application tree."""
        self.frames,self.index,self.commands=copy.deepcopy(frames),0,[]
        self.handle=SimpleNamespace(close=Mock())
        self.hello=dict(inputEnabled=False,combatObservation=copy.deepcopy(CAPABILITY))
        from native_ground_control import CAPABILITY as GROUND_CAPABILITY
        self.hello['groundControlObservation']=copy.deepcopy(GROUND_CAPABILITY)
        self.ground_required=False
        self.native=app/'diagnostics'
        self.native.mkdir()
        self.diagnostics=dict(directory=str(self.native),failed=0,dropped=0,written=0,pending=0,enabled=False)
        self.image=review_parts()[4]

    def request(self,command,**arguments):
        """Reject any unplanned command, especially input, while imitating diagnostic retention."""
        self.commands.append((command,arguments))
        if command=='enableNavigationGuidance':
            profile=arguments['navigationProfile']
            bounds,anchor=scout_scope(profile)
            capability=route_capability(SCOUT_GRASS_ROUTE)
            capability.update(profileId=profile,bounds=bounds,searchAnchor=anchor)
            return dict(enabled=True,capability=capability),b''
        if command=='enableCombatObservation':
            return dict(type='combatObservation',enabled=True,capability=copy.deepcopy(CAPABILITY)),b''
        if command=='requireGroundControlLayout':
            from native_ground_control import CAPABILITY as GROUND_CAPABILITY
            from test_native_ground_control import ground_png
            self.ground_required=True;self.image=ground_png()
            return dict(type='groundControlLayout',requiredForInput=True,capability=copy.deepcopy(GROUND_CAPABILITY)),b''
        if command=='frame':
            value=copy.deepcopy(self.frames[min(self.index,len(self.frames)-1)])
            if self.ground_required:
                from test_native_ground_control import attach_ground
                value=attach_ground(value)
            self.index+=1
            if self.diagnostics['enabled'] and not self.diagnostics['written']:
                name=f"native-frame-{value['frameId']:04d}"
                (self.native/(name+'.png')).write_bytes(self.image)
                metadata={key:copy.deepcopy(value[key]) for key in
                    ('frameId','capturedAtMs','sourceWidth','sourceHeight','sourceFrame','sourceTimestampKind')}
                metadata.update(freshnessContractVersion=2,evidence='WorldHud',
                    imageSha256=hashlib.sha256(self.image).hexdigest(),worldReadiness=value['frameWorldReadiness'])
                (self.native/(name+'.json')).write_bytes(canonical(metadata))
                self.diagnostics['written']=1
            return value,b''
        if command=='configureDiagnostics':
            self.diagnostics['enabled']=True
            return dict(diagnostics=copy.deepcopy(self.diagnostics)),b''
        if command=='status':return dict(diagnostics=copy.deepcopy(self.diagnostics)),b''
        raise AssertionError('Unexpected native command: '+command)


class PassiveSceneTests(unittest.TestCase):
    """Exercise the actual capture entry point and downstream review boundaries with inert adapters."""
    def setUp(self):
        """Substitute every external lifecycle, identity, clock and temperature operation."""
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.live=self.root/'artifacts/live'
        self.live.mkdir(parents=True)
        self.app=self.root/'artifacts/release/BetterGI-English-win-x64'
        self.app.mkdir(parents=True)
        self.output=self.live/'inspection'
        self.owner_file=self.live/'owner.json'
        self.owner_file.write_bytes(canonical(OWNER))
        def owner_inputs(path,artifacts,validate):
            """Keep the real held-file primitive while isolating the finite ancestry semantic replay."""
            return validate(path),{str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest()},{}
        self.stack.enter_context(patch.object(capture,'owner_inputs',owner_inputs))
        self.addCleanup(lambda:[capture.close_prepared_capture(token) for token in list(capture._PREPARED_CAPTURES)])
        self.child=dict(OWNER['child'],appDirectory=str(self.app),agentPipeName='inert')
        self.lifecycle=SimpleNamespace(start_agent=Mock(return_value=self.child),stop_agent=Mock())
        self.bridge=PassiveSceneBridge(self.app,[scene_frame(i) for i in range(1,6)])
        self.clock=0.
        def sleep(_):
            """Expire a refused capture without any wall-clock wait or repeated native launch."""
            self.clock+=1.
        fake_time=SimpleNamespace(monotonic=lambda:self.clock,monotonic_ns=lambda:int(self.clock*1e9),sleep=sleep)
        for module,name,value in ((capture,'repo',self.root),(capture,'load_map_owner',lambda _:copy.deepcopy(OWNER)),
                (capture,'control_module',lambda:self.lifecycle),(capture,'ready_session',lambda _:(OWNER['root'],self.child)),
                (capture,'verify_bridge_identity',Mock()),(capture,'Bridge',lambda _:self.bridge),
                (capture,'time',fake_time),(scout,'LIVE',self.live)):
            self.stack.enter_context(patch.object(module,name,value))
        self.stack.enter_context(patch.object(capture.subprocess,'check_output',return_value='50'))

    def run_capture(self,*options):
        """Invoke the real parser and finally cleanup, without touching the real owner file."""
        argv=['capture_scout_scene.py',str(self.output),'--owner-from',str(self.live/'owner.json'),*options]
        with patch.object(capture.sys,'argv',argv),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            capture.main()
        return (json.loads((self.output/'plan.json').read_bytes()),
                json.loads((self.output/'result.json').read_bytes()))

    def assert_passive_cleanup(self):
        """Successful and failed captures must close the same input-disabled lease exactly once."""
        self.lifecycle.start_agent.assert_called_once()
        self.assertIs(self.lifecycle.start_agent.call_args.kwargs['enable_input'],False)
        self.lifecycle.stop_agent.assert_called_once_with(self.child,12)
        self.bridge.handle.close.assert_called_once()
        self.assertFalse(any(name in ('action','release') for name,_ in self.bridge.commands))

    def test_anchor_is_required_unless_current_inspection_is_explicit(self):
        for options in ((),('--anchor','-1200','2450','--inspect-current')):
            with self.subTest(options=options),self.assertRaises(SystemExit):self.run_capture(*options)
        self.lifecycle.start_agent.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_anchored_capture_keeps_its_existing_output_and_displacement_gate(self):
        plan,result=self.run_capture('--anchor','-1200','2450')
        self.assertEqual(plan['anchor'],[-1200.,2450.])
        self.assertNotIn('inspectionMode',plan)
        self.assertNotIn('navigationReviewAllowed',result)
        self.assertEqual(result['status'],'completed')
        self.assert_passive_cleanup()

    def test_wrong_anchor_still_fails_without_input_and_retains_failure(self):
        with self.assertRaisesRegex(RuntimeError,'expected endpoint'):
            self.run_capture('--anchor','-1220','2450')
        self.assertEqual(json.loads((self.output/'result.json').read_bytes())['status'],'failed')
        self.assert_passive_cleanup()

    def test_current_north_scene_retains_exact_png_sidecar_and_no_navigation_authority(self):
        self.bridge.frames=[scene_frame(i,(-1216.876953125,2508.087890625)) for i in range(1,6)]
        plan,result=self.run_capture('--inspect-current','--navigation-profile',NORTH_SCOUT_PROFILE,'--require-single-enemy')
        for document in (plan,result):
            self.assertEqual(document['inspectionMode'],CURRENT_SCENE_INSPECTION)
            self.assertIs(document['navigationReviewAllowed'],False)
            self.assertIs(document['enemyIdentityVerified'],False)
            self.assertIs(document['requireSingleEnemyBarCandidate'],True)
        self.assertNotIn('anchor',plan)
        self.assertNotIn('scoutGroundControlPolicy',plan)
        self.assertFalse(any(command=='requireGroundControlLayout' for command,_ in self.bridge.commands))
        self.assertNotIn('nativeGroundControlGate',result)
        self.assertEqual(plan['navigationProfile'],NORTH_SCOUT_PROFILE)
        self.assertEqual(len(result['stableSamples']),3)
        image=self.output/result['selectedImageName']
        self.assertEqual(image.read_bytes(),self.bridge.image)
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(),result['selectedImageSha256'])
        sidecar=json.loads(image.with_suffix('.json').read_bytes())
        selected=next(row for row in result['observations'] if row['frameId']==sidecar['frameId'])
        self.assertEqual(selected['sourceFrame'],sidecar['sourceFrame'])
        self.assertEqual(hashlib.sha256((self.output/'capture-helper.py').read_bytes()).hexdigest(),plan['captureHelperSha256'])
        self.assert_passive_cleanup()

        # Capture is only evidence. The existing separate combat binder still
        # requires the exact PNG, a visual review and its fixed three-pulse policy.
        review,_,_,_,_,goal=review_parts()
        review.update(imageName=image.name,imageSha256=result['selectedImageSha256'])
        bound=bind_review(canonical(review),canonical(plan),canonical(result),canonical(sidecar),image.read_bytes(),goal)
        self.assertIs(bound['policy']['enemyIdentityVerified'],False)
        with self.assertRaisesRegex(ValueError,'separate bounded combat authority'):
            bind_review(canonical(dict(review,sceneLabel='unreviewed')),canonical(plan),canonical(result),
                canonical(sidecar),image.read_bytes(),goal)

        route=ReviewedScoutRoute(((-1216.876953125,2508.087890625),(-1220,2510)),NORTH_SCOUT_PROFILE)
        nav_review=dict(routeId=route.route_id,routeSpec=route.document(),routeSpecSha256=route.sha256,
            points=route.document()['points'],attacksAllowed=False,maximumLegs=1,inspectedHealth=900,
            inspectedMaximumHealth=1000,visualReview='Synthetic stable view',nativeEndpoint=str(self.output),
            imageName=image.name,imageSha256=result['selectedImageSha256'])
        path=self.output/'navigation-review.json'
        path.write_bytes(canonical(nav_review))
        manifest=dict(owner=copy.deepcopy(OWNER),navigationProfile=NORTH_SCOUT_PROFILE,routes={},
                      reviewedScoutRoutePolicy=reviewed_route_policy(NORTH_SCOUT_PROFILE))
        with self.assertRaisesRegex(ValueError,'cannot authorize'):scout.review_evidence(path,manifest,0)

    def test_current_inspection_preserves_scope_grounding_freshness_and_stability_gates(self):
        def source_change(row,epoch=False):
            """Keep each same-frame join consistent while preventing a stable increasing source sequence."""
            for source in (row['sourceFrame'],row['combatEvidence']['sourceFrame'],
                           row['frameWorldReadiness']['sourceFrame'],row['worldReadiness']['sourceFrame']):
                source.update(captureEpoch=str(row['frameId'])) if epoch else source.update(timestamp100ns=1)
        changes=dict(outside=lambda row:row['navigationPose'].update(x=-1501),
            airborne=lambda row:row['motionEvidence'].update(spaceKeyMatched=True),
            stale=lambda row:row.update(sourceFrameAgeMs=151),
            low_confidence=lambda row:row['navigationPose'].update(positionConfidence=.98),
            moving=lambda row:row['navigationPose'].update(x=-1200+row['frameId']),
            turning=lambda row:row['navigationPose'].update(yawDegrees=row['frameId']*10),
            not_ready=lambda row:row['frameWorldReadiness'].update(ready=False),
            repeated_source=source_change,changed_source_epoch=lambda row:source_change(row,True))
        for name,change in changes.items():
            with self.subTest(name=name):
                self.output=self.live/name
                self.clock=0.
                self.bridge.frames=[scene_frame(i) for i in range(1,6)]
                self.bridge.index=0
                for row in self.bridge.frames:change(row)
                with self.assertRaisesRegex(RuntimeError,'No stationary native scene'):
                    self.run_capture('--inspect-current')
                result=json.loads((self.output/'result.json').read_bytes())
                self.assertEqual(result['status'],'failed')
                self.assertIs(result['navigationReviewAllowed'],False)

    def test_single_candidate_filter_rejects_zero_multiple_and_unqualified_png(self):
        for counts in ([0]*5,[2]*5,[1,1,1,0,0]):
            with self.subTest(counts=counts):
                self.output=self.live/('candidates-'+''.join(map(str,counts)))
                self.clock=0.
                self.bridge.frames=[scene_frame(i,candidates=count) for i,count in enumerate(counts,1)]
                self.bridge.index=0
                with self.assertRaisesRegex(RuntimeError,'No stationary native scene'):
                    self.run_capture('--inspect-current','--require-single-enemy')
                result=json.loads((self.output/'result.json').read_bytes())
                self.assertEqual(result['status'],'failed')
                self.assertNotIn('selectedImageName',result)
        self.assertTrue(list(self.output.glob('*.png')))

    def test_unexpected_input_enabled_bridge_is_closed_before_observation(self):
        self.bridge.hello['inputEnabled']=True
        with self.assertRaisesRegex(RuntimeError,'input unexpectedly enabled'):self.run_capture('--inspect-current')
        self.assertEqual(self.bridge.commands,[])
        self.assert_passive_cleanup()

    def test_native_input_history_cannot_be_hidden_by_inspection_mode(self):
        self.bridge.frames[0]['executionContext']['lastSequence']=1
        with self.assertRaisesRegex(RuntimeError,'Unexpected native input history'):self.run_capture('--inspect-current')
        self.assert_passive_cleanup()

    def test_changed_owner_is_rejected_before_starting_any_stream(self):
        with patch.object(capture,'ready_session',return_value=(dict(OWNER['root'],processId=99),self.child)):
            with self.assertRaisesRegex(RuntimeError,'owner changed'):self.run_capture('--inspect-current')
        self.lifecycle.start_agent.assert_not_called()
        self.assertEqual(self.bridge.commands,[])


    def prepare(self,run_id='inert-capture',stop_paths=()):
        """Create only the private file capability; every native and GPU boundary remains mocked."""
        args=capture.parse_args([str(self.output),'--owner-from',str(self.owner_file),'--inspect-current'])
        return capture.prepare_capture(args,run_id=run_id,stop_paths=stop_paths)

    def test_prepare_is_file_only_and_run_consumes_once(self):
        with patch.object(capture,'ready_session',side_effect=AssertionError('discovery during preparation')):
            token=self.prepare()
        self.lifecycle.start_agent.assert_not_called()
        capture.subprocess.check_output.assert_not_called()
        self.assertEqual(self.bridge.commands,[])
        with redirect_stdout(io.StringIO()):
            capture.run_capture(token,run_id='inert-capture')
        retained=(self.output/'result.json').read_bytes()
        self.assertNotIn(token,capture._PREPARED_CAPTURES)
        with self.assertRaisesRegex(RuntimeError,'retired'):
            capture.run_capture(token,run_id='inert-capture')
        self.assertEqual((self.output/'result.json').read_bytes(),retained)
        self.assertEqual(capture.close_prepared_capture(token),[])
        self.assert_passive_cleanup()

    def test_foreign_run_and_mutated_context_never_start(self):
        token=self.prepare()
        with self.assertRaisesRegex(RuntimeError,'foreign'):
            capture.run_capture(token,run_id='another-run')
        state=capture._PREPARED_CAPTURES[token]
        self.assertFalse(state['admission'].consumed)
        state['args'].navigation_profile='foreign'
        with self.assertRaisesRegex(RuntimeError,'context changed'):
            capture.run_capture(token,run_id='inert-capture')
        self.lifecycle.start_agent.assert_not_called()

    def test_actual_held_owner_file_denies_write_until_close(self):
        token=self.prepare()
        before=self.owner_file.read_bytes()
        with self.assertRaises(PermissionError):self.owner_file.write_bytes(b'changed')
        self.assertEqual(self.owner_file.read_bytes(),before)
        self.assertEqual(capture.close_prepared_capture(token),[])
        self.owner_file.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'retired'):
            capture.run_capture(token,run_id='inert-capture')
        self.lifecycle.start_agent.assert_not_called()

    def test_stop_during_paused_owner_replay_closes_without_native_start(self):
        stop=self.live/'STOP'
        original=capture.owner_inputs
        def stopped_owner(*args):
            result=original(*args)
            stop.write_text('stop')
            return result
        with patch.object(capture,'owner_inputs',stopped_owner),self.assertRaisesRegex(RuntimeError,'Operator stop'):
            self.prepare()
        self.assertEqual(capture._PREPARED_CAPTURES,{})
        self.owner_file.write_bytes(b'unlocked after refusal')
        self.lifecycle.start_agent.assert_not_called()

    def test_stop_after_blocking_discovery_or_temperature_prevents_start(self):
        for phase in ['discovery','temperature']:
            with self.subTest(phase=phase):
                self.output=self.live/phase
                stop=self.output/'STOP'
                token=self.prepare()
                def discover(_):
                    stop.write_text('stop')
                    return OWNER['root'],self.child
                def temperature(*args,**kwargs):
                    stop.write_text('stop')
                    return '50'
                target=('ready_session',discover) if phase=='discovery' else ('check_output',temperature)
                module=capture if phase=='discovery' else capture.subprocess
                with patch.object(module,target[0],side_effect=target[1]),self.assertRaisesRegex(RuntimeError,'Operator stop'):
                    capture.run_capture(token,run_id='inert-capture')
                self.lifecycle.start_agent.assert_not_called()
                stop.unlink()

    def test_independent_pause_handles_overlap_before_capture_retirement(self):
        from combat_paused_file_admission import HeldFiles
        token=self.prepare()
        with self.assertRaisesRegex(RuntimeError,'another owner file'):
            capture.prepared_capture_owner(token,run_id='inert-capture',owner_file=self.live/'foreign.json')
        owner=capture.prepared_capture_owner(token,run_id='inert-capture',owner_file=self.owner_file)
        second=HeldFiles(capture._PREPARED_CAPTURES[token]['pins'])
        self.addCleanup(second.close)
        self.bridge.hello['inputEnabled']=True
        with self.assertRaisesRegex(RuntimeError,'input unexpectedly enabled'):
            capture.run_capture(token,run_id='inert-capture')
        self.assertNotIn(token,capture._PREPARED_CAPTURES)
        self.assertEqual(owner,OWNER)
        with self.assertRaises(PermissionError):self.owner_file.write_bytes(b'changed')
        second.verify()
        self.assertEqual(second.close(),[])
        self.assertEqual(json.loads((self.output/'result.json').read_bytes())['status'],'failed')
        self.assert_passive_cleanup()

    def test_fresh_held_hash_failure_never_starts(self):
        token=self.prepare()
        files=capture._PREPARED_CAPTURES[token]['admission'].files
        with patch.object(files,'verify',side_effect=ValueError('held source mutation')),self.assertRaisesRegex(ValueError,'mutation'):
            capture.run_capture(token,run_id='inert-capture')
        self.assertTrue(files.closed)
        self.lifecycle.start_agent.assert_not_called()

    def test_handle_close_failure_preserves_native_error_and_unresolved_status(self):
        token=self.prepare()
        files=capture._PREPARED_CAPTURES[token]['admission'].files
        original=files.close
        def failed_close():
            original()
            return ['inert close failure']
        self.bridge.hello['inputEnabled']=True
        with patch.object(files,'close',side_effect=failed_close),self.assertRaises(BaseExceptionGroup) as raised:
            capture.run_capture(token,run_id='inert-capture')
        self.assertIn('input unexpectedly enabled',str(raised.exception.exceptions[0]))
        result=json.loads((self.output/'result.json').read_bytes())
        self.assertEqual(result['status'],'unresolved')
        self.assertIn('input unexpectedly enabled',result['error'])
        self.assertIn('inert close failure',result['immutableHandleCleanupError'])
        self.assert_passive_cleanup()

    def test_historical_package_selection_change_refuses_before_start(self):
        original=capture.owner_inputs
        release=self.root/'artifacts/release-r69'
        def package_owner(*args):
            owner,pins,_=original(*args)
            return owner,pins,{str(release):dict(originalPresent=False,selected='retained witness')}
        with patch.object(capture,'owner_inputs',package_owner):token=self.prepare()
        release.mkdir()
        with self.assertRaisesRegex(ValueError,'package selection changed'):
            capture.run_capture(token,run_id='inert-capture')
        self.lifecycle.start_agent.assert_not_called()


    def test_owner_change_between_collection_and_held_replay_never_starts(self):
        """The semantic owner must still agree after all original evidence files are locked."""
        changed=copy.deepcopy(OWNER)
        changed['child']['processId']+=1
        with patch.object(capture,'load_map_owner',side_effect=[copy.deepcopy(OWNER),changed]),self.assertRaisesRegex(RuntimeError,'no longer replays'):
            self.prepare()
        self.assertFalse(capture._PREPARED_CAPTURES)
        self.lifecycle.start_agent.assert_not_called()
        self.owner_file.write_text('owner handles released',encoding='utf-8')


if __name__=='__main__':unittest.main()
