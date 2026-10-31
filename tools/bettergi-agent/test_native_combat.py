"""Inert contract tests for native HUD metadata, exact frame joins, and ordinary recording."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock,patch

from native_combat import (CAPABILITY,CAPABILITY_V2,METHOD,capability_for_version,negotiate,
                           scene_capability,validate_capability,validate_frame)
from stream_client import recording_frame_metadata,validate_navigation_scope_options
from types import SimpleNamespace
from navigation_profiles import SCOUT_PROFILE
from hybrid_routes import SCOUT_ENTRY_ROUTE


def native_frame(version=1):
    """Use a complete immutable WGC clock and one native-size red bar candidate."""
    source=dict(captureEpoch='native-epoch',timestamp100ns=1000000,capturedAtMs=100,acquiredAtMs=101,
                freshnessAtMs=100,freshnessClockKind='reported_compositor_qpc')
    evidence=dict(version=version,method=capability_for_version(version)['method'],state='valid',reason='native_colors_analyzed',frameId=42,
        sourceFrame=copy.deepcopy(source),sourceWidth=1920,sourceHeight=1080,playerHealthColor='green',
        playerHealthFractionEstimate=275/304,playerHealthMatchingPixels=200,
        enemyBarCandidates=[dict(x=800,y=400,width=120,height=6,pixels=720)],redMaskOverloaded=False,
        recognitionMs=1.5,authorizesInput=False,enemyIdentityVerified=False,killVerified=False)
    return dict(type='frame',frameId=42,sourceFrame=source,sourceWidth=1920,sourceHeight=1080,combatEvidence=evidence)


class NativeCombatTests(unittest.TestCase):
    def test_v1_roi_and_boundary_semantics_remain_unchanged(self):
        frame=native_frame()
        frame['combatEvidence']['enemyBarCandidates'][0].update(y=894)
        self.assertIsNotNone(validate_frame(frame,CAPABILITY))
        frame['combatEvidence']['enemyBarCandidates'][0].update(y=961)
        with self.assertRaises(ValueError):validate_frame(frame,CAPABILITY)
        self.assertEqual(CAPABILITY['enemyRegion'],dict(x=200,y=100,width=1400,height=800))

    def test_v2_lower_roi_and_clipped_boundary_at_both_native_scales(self):
        for width in (1280,1920):
            scale=width/1920
            for y,height,allowed in ((961,8,True),(981,8,True),(982,8,False),(984,12,False),(1008,5,False)):
                with self.subTest(width=width,y=y):
                    frame=native_frame(2)
                    frame.update(sourceWidth=width,sourceHeight=width*9//16)
                    evidence=frame['combatEvidence']
                    evidence.update(sourceWidth=width,sourceHeight=width*9//16,playerHealthMatchingPixels=round(133*scale))
                    w,h=round(120*scale),round(height*scale)
                    evidence['enemyBarCandidates']=[dict(x=round(469*scale),y=round(y*scale),width=w,height=h,pixels=w*h)]
                    if allowed:self.assertIsNotNone(validate_frame(frame,CAPABILITY_V2))
                    else:
                        with self.assertRaises(ValueError):validate_frame(frame,CAPABILITY_V2)

    def test_negotiated_versions_cannot_mix_methods_replies_or_frames(self):
        for version in (1,2):
            capability=capability_for_version(version)
            bridge=Mock(hello=dict(combatObservation=capability,inputEnabled=False))
            bridge.request.return_value=(dict(type='combatObservation',enabled=True,capability=copy.deepcopy(capability)),b'')
            self.assertEqual(negotiate(bridge),capability)
            other=capability_for_version(3-version)
            bridge.request.return_value=(dict(type='combatObservation',enabled=True,capability=other),b'')
            with self.assertRaises(ValueError):negotiate(bridge)
            with self.assertRaises(ValueError):validate_frame(native_frame(3-version),capability)
            frame=native_frame(version);frame['combatEvidence']['method']=other['method']
            with self.assertRaises(ValueError):validate_frame(frame)
        for change in (dict(version=True),dict(version=3),dict(method=METHOD),
                       dict(enemyRegion=CAPABILITY['enemyRegion']),dict(rejectsLowerBoundaryComponents=False)):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_capability(dict(CAPABILITY_V2,**change))
        missing=copy.deepcopy(CAPABILITY_V2);del missing['rejectsLowerBoundaryComponents']
        with self.assertRaises(ValueError):validate_capability(missing)

    def test_scene_contract_cannot_be_stripped_or_silently_upgraded(self):
        self.assertEqual(scene_capability(dict(observations=[native_frame()])),CAPABILITY)
        self.assertEqual(scene_capability(dict(nativeCombatObservation=CAPABILITY_V2,
            observations=[native_frame(2)])),CAPABILITY_V2)
        for scene in (dict(observations=[native_frame(2)]),dict(nativeCombatObservation=CAPABILITY_V2,observations=[]),
                      dict(nativeCombatObservation=CAPABILITY_V2,observations=[native_frame()])):
            with self.subTest(scene=scene),self.assertRaises(ValueError):scene_capability(scene)

    def test_actual_read_only_stream_binds_v2_and_rejects_a_v1_frame(self):
        import stream_client as client
        from test_stream_segments import ContinuousBridge,Recorder
        for frame_version in (2,1):
            class NativeBridge(ContinuousBridge):
                def request(self,command,**kwargs):
                    if command=='enableCombatObservation':
                        self.commands.append((command,kwargs))
                        return dict(type='combatObservation',enabled=True,capability=copy.deepcopy(CAPABILITY_V2)),b''
                    result,pixels=super().request(command,**kwargs)
                    if command=='frame':
                        now=result['capturedAtMs'];evidence=native_frame(frame_version)['combatEvidence']
                        source=dict(captureEpoch='native-epoch',timestamp100ns=int((now+10000)*10000),
                            capturedAtMs=now-1,acquiredAtMs=now,freshnessAtMs=now-1,freshnessClockKind='reported_compositor_qpc')
                        evidence.update(frameId=result['frameId'],sourceFrame=copy.deepcopy(source))
                        result.update(sourceWidth=1920,sourceHeight=1080,sourceFrame=source,combatEvidence=evidence)
                    return result,pixels
            with self.subTest(frame_version=frame_version),tempfile.TemporaryDirectory() as folder:
                args=client.parse_arguments(['--model','observe','--seconds','.15','--fps','20',
                    '--native-combat-observation','--record-dir',str(Path(folder)/'recording'),
                    '--output',str(Path(folder)/'run.json')])
                bridge=NativeBridge('inert');bridge.hello.update(inputEnabled=False,combatObservation=copy.deepcopy(CAPABILITY_V2))
                with patch.object(client,'Bridge',return_value=bridge),patch.object(client,'AsyncVideoRecorder',Recorder),redirect_stdout(io.StringIO()):
                    if frame_version==2:self.assertEqual(client.run_episode(args),0)
                    else:
                        with self.assertRaisesRegex(ValueError,'negotiation changed'):client.run_episode(args)
                report=json.loads(Path(args.output).read_bytes())
                self.assertEqual(report['nativeCombatObservation'],CAPABILITY_V2)
                self.assertNotIn('action',[command for command,_ in bridge.commands])
                self.assertEqual([command for command,_ in bridge.commands].count('stop'),1)

    def test_live_stream_negotiates_and_records_native_metadata_without_enabling_input(self):
        import stream_client as client
        from test_stream_segments import ContinuousBridge,Recorder
        class NativeBridge(ContinuousBridge):
            def request(self,command,**kwargs):
                if command=='enableCombatObservation':
                    self.commands.append((command,kwargs))
                    return dict(type='combatObservation',enabled=True,capability=copy.deepcopy(CAPABILITY)),b''
                result,pixels=super().request(command,**kwargs)
                if command=='frame':
                    now=result['capturedAtMs']
                    source=dict(captureEpoch='native-epoch',timestamp100ns=int((now+10000)*10000),
                        capturedAtMs=now-1,acquiredAtMs=now,freshnessAtMs=now-1,freshnessClockKind='reported_compositor_qpc')
                    evidence=native_frame()['combatEvidence']
                    evidence.update(frameId=result['frameId'],sourceFrame=copy.deepcopy(source))
                    result.update(sourceWidth=1920,sourceHeight=1080,sourceFrame=source,combatEvidence=evidence)
                return result,pixels
        with tempfile.TemporaryDirectory() as folder:
            args=client.parse_arguments(['--model','observe','--seconds','1','--segment-seconds','.15','--fps','20',
                '--native-combat-observation','--record-dir',str(Path(folder)/'recording'),
                '--output',str(Path(folder)/'run.json')])
            args.lease_output=str(Path(folder)/'lease.json')
            bridge=NativeBridge('inert')
            bridge.hello.update(inputEnabled=False,combatObservation=copy.deepcopy(CAPABILITY))
            recorders=[]
            def recorder_factory(*values,**kwargs):
                recorder=Recorder(*values,**kwargs)
                recorders.append(recorder)
                return recorder
            with patch.object(client,'Bridge',return_value=bridge), \
                    patch.object(client,'AsyncVideoRecorder',side_effect=recorder_factory),redirect_stdout(io.StringIO()):
                self.assertEqual(client.run_episode(args),0)
            manifest=json.loads(Path(args.lease_output).read_bytes())
            parts=[json.loads(Path(part['report']).read_bytes()) for part in manifest['segments']]
            self.assertGreater(len(parts),1)
            self.assertEqual(sum(part['nativeCombatEvidenceFrames'] for part in parts),manifest['nativeCombatEvidenceFrames'])
            self.assertEqual(manifest['nativeCombatEvidenceFrames'],manifest['framesReceived'])
            self.assertGreater(manifest['nativeCombatEvidenceFrames'],0)
            self.assertEqual(manifest['acceptedInputActions'],0)
            recorded=[row for recorder in recorders for row in recorder.items]
            self.assertTrue(recorded)
            self.assertTrue(all(validate_frame(row) for row in recorded))
            commands=[name for name,_ in bridge.commands]
            self.assertNotIn('action',commands)
            self.assertEqual(commands.count('enableCombatObservation'),1)
            self.assertEqual(commands.count('stop'),1)

    def test_negotiation_has_no_input_or_launch_authority(self):
        bridge=Mock(hello={'combatObservation':copy.deepcopy(CAPABILITY),'inputEnabled':False})
        bridge.request.return_value=({'type':'combatObservation','enabled':True,'capability':copy.deepcopy(CAPABILITY)},b'')
        self.assertEqual(negotiate(bridge),CAPABILITY)
        bridge.request.assert_called_once_with('enableCombatObservation')
        self.assertFalse(bridge.hello['inputEnabled'])
        for change in (dict(authorizesInput=True),dict(sameFrame=False),dict(version=True),dict(maxWidth=3840)):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_capability(dict(CAPABILITY,**change))

    def test_valid_metadata_is_retained_without_becoming_an_execution_claim(self):
        frame=native_frame()
        self.assertEqual(validate_frame(frame),frame['combatEvidence'])
        recorded=recording_frame_metadata(frame,'off')
        self.assertEqual(recorded['combatEvidence'],frame['combatEvidence'])
        self.assertFalse(recorded['combatEvidence']['authorizesInput'])
        self.assertIsNone(validate_frame(dict(frame,combatEvidence=None)))

    def test_cross_frame_source_geometry_and_freshness_substitutions_fail(self):
        changes=(dict(frameId=43),dict(sourceWidth=1280),dict(sourceFrame={'captureEpoch':'other'}),
                 dict(enemyIdentityVerified=True),dict(killVerified=True),dict(recognitionMs=float('nan')),
                 dict(playerHealthFractionEstimate=1.1),dict(playerHealthMatchingPixels=305))
        for change in changes:
            frame=native_frame()
            frame['combatEvidence'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_frame(frame)
        frame=native_frame()
        frame['sourceFrame']['freshnessAtMs']=101
        frame['combatEvidence']['sourceFrame']=copy.deepcopy(frame['sourceFrame'])
        with self.assertRaises(ValueError):validate_frame(frame)

    def test_unavailable_or_overloaded_evidence_cannot_keep_candidates(self):
        frame=native_frame()
        frame['combatEvidence'].update(state='unavailable',reason='world_not_ready')
        with self.assertRaises(ValueError):validate_frame(frame)
        frame['combatEvidence'].update(playerHealthColor='unknown',playerHealthFractionEstimate=None,
                                      playerHealthMatchingPixels=0,enemyBarCandidates=[])
        self.assertEqual(validate_frame(frame)['state'],'unavailable')
        frame=native_frame()
        frame['combatEvidence'].update(redMaskOverloaded=True,reason='red_mask_overloaded')
        with self.assertRaises(ValueError):validate_frame(frame)
        frame['combatEvidence']['enemyBarCandidates']=[]
        self.assertTrue(validate_frame(frame)['redMaskOverloaded'])

    def test_candidate_geometry_is_bounded_in_native_coordinates(self):
        for change in (dict(x=199),dict(y=99),dict(width=321),dict(height=30),dict(pixels=721),dict(width=True)):
            frame=native_frame()
            frame['combatEvidence']['enemyBarCandidates'][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_frame(frame)

    def test_read_only_scouting_does_not_require_or_select_a_walking_route(self):
        args=SimpleNamespace(navigation_profile=SCOUT_PROFILE,navigation_guidance=True,hybrid_navigation=False,hybrid_route=None)
        self.assertEqual(validate_navigation_scope_options(args),SCOUT_PROFILE)
        args.hybrid_navigation=True
        with self.assertRaises(ValueError):validate_navigation_scope_options(args)
        args.hybrid_route=SCOUT_ENTRY_ROUTE
        self.assertEqual(validate_navigation_scope_options(args),SCOUT_PROFILE)


if __name__=='__main__':unittest.main()
