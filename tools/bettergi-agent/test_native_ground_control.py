"""Inert control-layout protocol, retained-image, reader-race and post-release endpoint regressions."""
import base64
import copy
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_ground_control as ground
from scout_encounter_guard import ScoutEncounterGuard,ScoutEncounterStop,binding_from_review
from test_scout_encounter_guard import sample,release_ack,GuardBridge,binding as old_binding
import test_scout_encounter_guard as guard_tests
from test_stream_client import CapturingRecorder,FakePolicy


@lru_cache(maxsize=2)
def crop_fixture(water=False):
    """Create only two tiny native RGB regions, retaining distinguishable E/Q masks or the exact swim marker."""
    crops=[]
    for name,pattern,anchor in (('eRegion',ground.E_PATTERN,1684),('qRegion',ground.Q_PATTERN,1804)):
        region=ground.CAPABILITY[name];data=bytearray([30,45,65]*region['width']*region['height'])
        if not water:
            for y,row in enumerate(pattern):
                for x,kind in enumerate(row):
                    i=((1027+y-region['y'])*region['width']+anchor+x-region['x'])*3
                    data[i:i+3]=bytes([50 if kind=='#' else 240 if kind=='.' else 180]*3)
        elif name=='qRegion':
            for y in range(1028,1035):
                for x in range(1819,1828):
                    i=((y-region['y'])*region['width']+x-region['x'])*3;data[i:i+3]=bytes((250,228,42))
        crops.append(dict(region,format='rgb24',rgbBase64=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest()))
    e,q=crops
    measurements=dict(eKey=ground.match_crop(base64.b64decode(e['rgbBase64']),e,ground.E_PATTERN,1684),
                      qKey=ground.match_crop(base64.b64decode(q['rgbBase64']),q,ground.Q_PATTERN,1804),
                      swimHintPixels=ground.swim_pixels(base64.b64decode(q['rgbBase64']),q))
    return crops,measurements


def attach_ground(frame,water=False):
    """Attach faithful same-source evidence to an existing inert frame without changing its pose or input result."""
    result=copy.deepcopy(frame);source=result['sourceFrame'];at=source['freshnessAtMs'] if 'freshnessAtMs' in source else source['capturedAtMs']
    source.setdefault('capturedAtMs',at);source.setdefault('acquiredAtMs',at+1)
    source.setdefault('freshnessAtMs',min(source['capturedAtMs'],source['acquiredAtMs']))
    source.setdefault('freshnessClockKind','reported_compositor_qpc')
    for key in ('combatEvidence','frameWorldReadiness','worldReadiness'):
        if isinstance(result.get(key),dict) and 'sourceFrame' in result[key]:result[key]['sourceFrame']=copy.deepcopy(source)
    crops,measurements=copy.deepcopy(crop_fixture(water))
    result.update(type='frame',sourceWidth=1920,sourceHeight=1080)
    result['groundControlEvidence']=dict(version=1,method=ground.CAPABILITY['method'],authorizesInput=False,
        physicallyGrounded=False,state='valid',reason='swim_control_hint' if water else 'ground_control_layout',
        frameId=result['frameId'],sourceFrame=copy.deepcopy(source),sourceWidth=1920,sourceHeight=1080,
        groundControlsConfirmed=not water,spaceKeyMatched=False,xKeyMatched=False,crops=crops,recognitionMs=.2,**measurements)
    return result


def ground_png():
    """Produce a genuine native-size synthetic PNG whose exact crops match the inert evidence."""
    from PIL import Image
    image=Image.new('RGB',(1920,1080),(30,45,65))
    for crop in crop_fixture()[0]:
        image.paste(Image.frombytes('RGB',(crop['width'],crop['height']),base64.b64decode(crop['rgbBase64'])),(crop['x'],crop['y']))
    out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()


def binding(version=1):
    """Keep the old health descriptor intact and add separately bound ground-control authority."""
    old=old_binding(version)
    return binding_from_review(old,old['reviewSha256'],old.get('nativeCombatObservation'),ground.CAPABILITY)


class GroundProtocolTests(unittest.TestCase):
    """Validate closed negotiation, source binding and replayable small RGB evidence."""
    def test_native_masks_are_exact_and_glyphs_distinct(self):
        path=Path(__file__).resolve().parents[2]/'BetterGenshinImpact/GameTask/AutoAgent/AgentGroundControlRecognizer.cs'
        source=path.read_text(encoding='utf-8')
        for name,pattern in (('EPattern',ground.E_PATTERN),('QPattern',ground.Q_PATTERN)):
            rows=re.findall(r'"([.+#]+)"',source.split(name+' =',1)[1].split('];',1)[0])
            self.assertEqual(tuple(rows),pattern);self.assertEqual(len(rows),25)
            self.assertTrue(all(len(row)==30 for row in rows))
        frame=attach_ground(sample())
        self.assertTrue(ground.validate_frame(frame,replay_pixels=True)['groundControlsConfirmed'])
        changed=copy.deepcopy(frame);changed['groundControlEvidence']['qKey']=copy.deepcopy(changed['groundControlEvidence']['eKey'])
        with self.assertRaises(ValueError):ground.validate_frame(changed,replay_pixels=True)

    def test_exact_geometry_hash_source_and_decision_mutations_refuse(self):
        changes={
            'geometry':lambda e:e.update(sourceWidth=1280),
            'hash':lambda e:e['crops'][0].update(sha256='0'*64),
            'crop':lambda e:e['crops'][0].update(x=1661),
            'source':lambda e:e['sourceFrame'].update(timestamp100ns=9),
            'decision':lambda e:e.update(groundControlsConfirmed=False),
            'boolean':lambda e:e.update(swimHintPixels=False),
            'authority':lambda e:e.update(physicallyGrounded=True),
            'glyph':lambda e:e['eKey'].update(darkMatches=0),
            'extra':lambda e:e['crops'][0].update(anotherCapture=True)}
        for label,change in changes.items():
            value=attach_ground(sample());change(value['groundControlEvidence'])
            with self.subTest(label=label),self.assertRaises(ValueError):ground.validate_frame(value,replay_pixels=True)

    def test_pixel_replay_rejects_resealed_wrong_crop(self):
        value=attach_ground(sample());crop=value['groundControlEvidence']['crops'][0]
        raw=bytes([255])*75*42*3;crop.update(rgbBase64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())
        ground.validate_frame(value)
        with self.assertRaisesRegex(ValueError,'replay'):ground.validate_frame(value,replay_pixels=True)

    def test_swim_is_positive_negative_evidence_and_no_swim_does_not_prove_ground(self):
        value=attach_ground(sample(),True)
        self.assertEqual(ground.validate_frame(value,replay_pixels=True)['swimHintPixels'],63)
        with self.assertRaises(ValueError):ground.require_ground_frame(value)
        value['groundControlEvidence'].update(swimHintPixels=0,reason='ground_controls_unconfirmed')
        with self.assertRaises(ValueError):ground.require_ground_frame(value)

    def test_negotiation_requires_matching_hello_reply_and_empty_payload(self):
        good=dict(type='groundControlLayout',requiredForInput=True,capability=copy.deepcopy(ground.CAPABILITY))
        calls=[]
        bridge=SimpleNamespace(hello=dict(groundControlObservation=copy.deepcopy(ground.CAPABILITY)),
            request=lambda name:(calls.append(name) or copy.deepcopy(good),b''))
        self.assertEqual(ground.negotiate(bridge),(ground.CAPABILITY,good))
        self.assertEqual(calls,['requireGroundControlLayout'])
        for reply,payload in ((dict(good,requiredForInput=False),b''),(good,b'x'),
                              (dict(good,capability=dict(ground.CAPABILITY,sourceWidth=1280)),b'')):
            bridge.request=lambda name:(reply,payload)
            with self.assertRaises(ValueError):ground.negotiate(bridge)

    def test_retained_actual_dry_and_water_pngs(self):
        from PIL import Image
        root=Path(__file__).resolve().parents[2]/'artifacts/live/2026-10-30-endurance'
        cases=(('north-starfell-r63-statue-departure-01/01-frame-000000000024.png',0,True,
                'e2d586be955c79eafbf84fec522dac925e571122f93bc81ef21566952109efb8'),
               ('north-starfell-r63-water-return-01/01-frame-000000000008.png',40,False,
                '9787ab4ad4233567015e5290a4c07f4be00803e7635e0129f1967ecbed8aaa5a'))
        if not all((root/name).is_file() for name,*_ in cases):self.skipTest('Retained R63 PNGs are not present')
        for name,count,positive,digest in cases:
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
            with Image.open(root/name) as image:
                crops=[]
                for region in (ground.CAPABILITY['eRegion'],ground.CAPABILITY['qRegion']):
                    x,y,w,h=(region[k] for k in ('x','y','width','height'))
                    raw=image.convert('RGB').crop((x,y,x+w,y+h)).tobytes()
                    crops.append(dict(region,format='rgb24',rgbBase64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest()))
            value=attach_ground(sample(),not positive);e=value['groundControlEvidence'];e['crops']=crops
            for key,crop,pattern,x in zip(('eKey','qKey'),crops,(ground.E_PATTERN,ground.Q_PATTERN),(1684,1804)):
                e[key]=ground.match_crop(base64.b64decode(crop['rgbBase64']),crop,pattern,x)
            e['swimHintPixels']=ground.swim_pixels(base64.b64decode(crops[1]['rgbBase64']),crops[1])
            self.assertEqual(e['swimHintPixels'],count)
            self.assertEqual(ground.validate_frame(value,replay_pixels=True)['groundControlsConfirmed'],positive)
            if positive:ground.verify_image_crops(root/name,value)


class GroundGuardTests(unittest.TestCase):
    """Exercise startup, release, newer hazards and endpoint accounting with no input backend."""
    def test_missing_startup_never_arms_and_missing_armed_trips(self):
        guard=ScoutEncounterGuard(binding());self.assertEqual(guard.observe(sample(),1)['state']['state'],'waiting')
        with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(sample(),2)
        frame=attach_ground(sample(2));guard.observe(frame,3);guard.check_dispatch(frame,4)
        self.assertEqual(guard.observe(sample(3),5)['state']['trip']['reason'],'groundControlEvidenceUnavailable')

    def test_swim_hint_trips_even_after_native_gate_makes_health_unavailable(self):
        guard=ScoutEncounterGuard(binding());frame=attach_ground(sample());guard.observe(frame,1);guard.check_dispatch(frame,2)
        value=attach_ground(sample(2),True)
        value['combatEvidence'].update(state='unavailable',reason='world_not_ready',playerHealthColor='unknown',
                                      playerHealthFractionEstimate=None,playerHealthMatchingPixels=0)
        event=guard.observe(value,3)
        self.assertEqual(event['state']['trip']['reason'],'swimControlHint')
        self.assertIn('rgbBase64',event['frame']['groundControlEvidence']['crops'][0])
        self.assertNotIn('rgbBase64',event['state']['trip']['frame']['groundControlEvidence']['crops'][0])
        with self.assertRaises(ScoutEncounterStop):guard.check_dispatch(frame,4)

    def test_acknowledged_release_preserves_trip_and_newer_ground_requirement(self):
        guard=ScoutEncounterGuard(binding());frame=attach_ground(sample());guard.observe(frame,1);guard.check_dispatch(frame,2)
        guard.acknowledge_release(release_ack(),0,3,'hybridEndpoint')
        self.assertEqual(guard.observe(sample(2),4)['state']['state'],'waiting')
        hazard=attach_ground(sample(3),True);self.assertEqual(guard.observe(hazard,5)['state']['trip']['reason'],'swimControlHint')
        guard.acknowledge_release(release_ack(301),0,6,'scoutEncounterGuard')
        with self.assertRaises(ScoutEncounterStop):guard.observe(attach_ground(sample(4)),7)

    def test_repeated_pixels_cannot_change_their_ground_evidence(self):
        guard=ScoutEncounterGuard(binding());value=attach_ground(sample());guard.observe(value,1)
        self.assertEqual(guard.observe(copy.deepcopy(value),2)['state']['distinctSources'],1)
        changed=attach_ground(sample(),True)
        self.assertIsNotNone(guard.observe(changed,3)['state']['trip'])

    def test_frame200_style_post_release_water_cannot_verify_endpoint(self):
        from hybrid_navigation import HybridNavigation
        from test_hybrid_navigation import capability,frame,END
        nav=HybridNavigation(capability(),require_ground_controls=True)
        for i in range(3):nav.prepare(attach_ground(frame(i+1,100+i*100)))
        self.assertEqual(nav.prepare(attach_ground(frame(4,1000,END))),'releaseRequired')
        nav.released(dict(type='released',serverNowMs=1010))
        nav.prepare(attach_ground(frame(5,1100,END)))
        with self.assertRaisesRegex(RuntimeError,'ground_controls_unconfirmed'):
            nav.prepare(attach_ground(frame(200,1200,END),True))
        self.assertEqual(nav.legs,0)
        self.assertFalse(any(e['type']=='hybridEndpointVerified' for e in nav.drain_events()))


class GroundBridge(GuardBridge):
    """A memory transport exposes the one-way ground gate while leaving all game APIs absent."""
    def __init__(self,transform=lambda frame:frame):
        super().__init__(lambda frame:transform(attach_ground(frame)))
        self.hello['groundControlObservation']=copy.deepcopy(ground.CAPABILITY)

    def request(self,command,**arguments):
        """Acknowledge only the exact new gate, preserving the existing action/release receipt stub."""
        if command=='requireGroundControlLayout':
            self.commands.append(command)
            return dict(type='groundControlLayout',requiredForInput=True,capability=copy.deepcopy(ground.CAPABILITY)),b''
        return super().request(command,**arguments)


class GroundStreamTests(unittest.TestCase):
    """Use the real receive/inference/dispatch loop with CPU stubs and retained inline crop evidence."""
    def run_inert(self,*args,**kwargs):
        """Reuse the established no-native/no-GPU loop fixture with this separately bound contract."""
        with patch('test_scout_encounter_guard.binding',binding):
            return guard_tests.StreamGuardTests.run_inert(self,*args,**kwargs)

    def test_normal_ground_navigation_keeps_exact_gate_acknowledgement(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=GroundBridge()
            self.assertEqual(self.run_inert(folder,bridge,FakePolicy(),CapturingRecorder()),0)
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(len(bridge.actions),2)
            self.assertEqual(report['nativeGroundControlObservation'],ground.CAPABILITY)
            self.assertTrue(report['nativeGroundControlGate']['requiredForInput'])

    def test_inflight_swim_trip_retains_pixels_releases_and_prevents_dispatch(self):
        entered=threading.Event()
        def transform(frame):
            """A newer swimming observation arrives while the old dry prediction is in flight."""
            return attach_ground(frame,True) if entered.is_set() else frame
        with tempfile.TemporaryDirectory() as folder:
            bridge=GroundBridge(transform);recorder=CapturingRecorder()
            def predicting():
                """Wait only for the background reader's bounded synthetic release."""
                entered.set();self.assertTrue(bridge.released.wait(2))
            with self.assertRaisesRegex(ScoutEncounterStop,'swimControlHint'):
                self.run_inert(folder,bridge,FakePolicy(during_predict=predicting),recorder)
            report=json.loads((Path(folder)/'run.json').read_bytes())
            self.assertEqual(bridge.actions,[])
            self.assertTrue(report['scoutEncounterGuardTriggerRecorded'])
            self.assertEqual(report['scoutEncounterGuardState']['trip']['reason'],'swimControlHint')
            self.assertTrue(any(e.get('type')=='scoutEncounterGuardObservation' and
                e['frame'].get('groundControlEvidence',{}).get('swimHintPixels')==63 for e in recorder.events))

    def test_recording_failure_cannot_continue_ground_input(self):
        class RefusingRecorder(CapturingRecorder):
            """Simulate a bounded metadata queue refusing its first otherwise valid crop frame."""
            def put(self,metadata,pixels):
                super().put(metadata,pixels);return False
        with tempfile.TemporaryDirectory() as folder:
            bridge=GroundBridge();policy=FakePolicy()
            with self.assertRaisesRegex(RuntimeError,'Ground-control scout RGB retention failed'):
                self.run_inert(folder,bridge,policy,RefusingRecorder())
            self.assertEqual(bridge.actions,[])


class GroundAuditTests(unittest.TestCase):
    """Replay original inline crops and refusal transitions independently of success-shaped reports."""
    @staticmethod
    def ground_proof(path,run):
        """Upgrade the original v2 fixture with an exact native image, scene, policy and archived source chain."""
        from test_audit_hybrid_run import CachedPolicyAuditTests as fixture
        proof,reuse=fixture.v2_guarded_proof(path,run)
        source=Path(reuse['sessionProof']);session=json.loads(source.read_bytes())
        manifest_path=source.parent/'manifest.json';manifest=json.loads(manifest_path.read_bytes())
        request=json.loads(Path(reuse['requestFile']).read_bytes())
        review_path=Path(request['reviewFile']);review=json.loads(review_path.read_bytes())
        endpoint=Path(review['nativeEndpoint']);scene=json.loads((endpoint/'result.json').read_bytes())
        plan=json.loads((endpoint/'plan.json').read_bytes());plan['scoutGroundControlPolicy']=ground.policy()
        for key in ('observations','stableSamples'):scene[key]=[attach_ground(frame) for frame in scene[key]]
        scene.update(nativeGroundControlObservation=copy.deepcopy(ground.CAPABILITY),
            nativeGroundControlGate=dict(type='groundControlLayout',requiredForInput=True,capability=copy.deepcopy(ground.CAPABILITY)))
        image=endpoint/review['imageName'];image.write_bytes(ground_png())
        review['imageSha256']=request['imageSha256']=hashlib.sha256(image.read_bytes()).hexdigest()
        metadata_path=image.with_suffix('.json');metadata=json.loads(metadata_path.read_bytes())
        metadata.update(imageSha256=review['imageSha256'],sourceFrame=scene['observations'][1]['sourceFrame'])
        request.update(reviewSha256=fixture.write(review_path,review),nativePlanSha256=fixture.write(endpoint/'plan.json',plan),
            nativeResultSha256=fixture.write(endpoint/'result.json',scene),imageMetadataSha256=fixture.write(metadata_path,metadata))
        configuration=session['configuration'];configuration['arguments']['require_ground_control_layout']=True
        configuration.update(groundControlPolicy=ground.policy(),groundControlSourceSha256=ground.source_contract())
        archive=source.parent.parent/'source-snapshot'
        for name in ground.SOURCE_NAMES:
            (archive/name).write_bytes((Path(__file__).parent/name).read_bytes())
            if name in configuration['executedHistorySourceSha256']:
                configuration['executedHistorySourceSha256'][name]=configuration['groundControlSourceSha256'][name]
        fingerprint=hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        manifest['configuration']=copy.deepcopy(configuration)
        for value in (manifest,session,request,reuse):value['modelConfigurationSha256']=fingerprint
        for value in (manifest,session):value['scoutGroundControlPolicy']=ground.policy()
        bound=binding_from_review(review,request['reviewSha256'],scene['nativeCombatObservation'],ground.CAPABILITY)
        for value in (request,reuse,run):value['scoutEncounterGuard']=copy.deepcopy(bound)
        fixture.write(manifest_path,manifest);reuse['sessionProofSha256']=fixture.write(source,session)
        fixture.reseal_request(run,proof,reuse,request)
        return proof,reuse

    def test_original_policy_manifest_sources_and_scene_cannot_downgrade(self):
        """Resealing a proof does not erase its original ground contract or turn a historical scene into authority."""
        from test_audit_hybrid_run import CachedPolicyAuditTests as fixture
        from audit_hybrid_run import verify_policy_reuse
        for change in ('none','proof-declaration','both-declarations','source-bytes','scene-declaration','ack-type'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session/legs'/('e'*32)/'run.json'
                proof,reuse=self.ground_proof(path,run)
                source=Path(reuse['sessionProof']);session=json.loads(source.read_bytes())
                manifest_path=source.parent/'manifest.json';manifest=json.loads(manifest_path.read_bytes())
                request=json.loads(Path(reuse['requestFile']).read_bytes())
                review=json.loads(Path(request['reviewFile']).read_bytes());scene_path=Path(review['nativeEndpoint'])/'result.json'
                scene=json.loads(scene_path.read_bytes())
                if change in ('proof-declaration','both-declarations'):session.pop('scoutGroundControlPolicy')
                if change=='both-declarations':manifest.pop('scoutGroundControlPolicy')
                if change=='source-bytes':
                    archived=source.parent.parent/'source-snapshot/native_ground_control.py'
                    archived.write_bytes(archived.read_bytes()+b'\n# changed\n')
                if change=='scene-declaration':scene.pop('nativeGroundControlObservation')
                if change=='ack-type':scene['nativeGroundControlGate']['type']='accepted'
                request['nativeResultSha256']=fixture.write(scene_path,scene)
                fixture.write(manifest_path,manifest);reuse['sessionProofSha256']=fixture.write(source,session)
                fixture.reseal_request(run,proof,reuse,request)
                if change=='none':
                    self.assertEqual(verify_policy_reuse(run,path,proof)['scoutEncounterGuard']['groundControlPolicy'],ground.policy())
                else:
                    with self.assertRaises(ValueError):verify_policy_reuse(run,path,proof)

    def test_historical_scene_cannot_retain_undeclared_ground_gate_or_stable_pixels(self):
        for scene in ({'nativeGroundControlGate':{}},{'stableSamples':[attach_ground(sample())]}):
            with self.subTest(scene=list(scene)),self.assertRaisesRegex(ValueError,'declaration is missing'):
                ground.scene_capability(scene)
        self.assertIsNone(ground.scene_capability({'observations':[sample()]}))

    def fixture(self,folder):
        """Create a complete source/journal/dispatch join without a native service or model."""
        guard=ScoutEncounterGuard(binding());frames={i:attach_ground(sample(i)) for i in (1,2)}
        events=[guard.observe(frames[i],i*100) for i in frames]
        marker=guard.check_dispatch(frames[2],201)
        events.append(dict(type='scoutEncounterGuardDispatch',requestId='inert',marker=marker,
            frame=copy.deepcopy(frames[2]),state=guard.snapshot()))
        part=dict(scoutEncounterGuard=binding(),scoutEncounterGuardState=guard.snapshot(),
            nativeGroundControlObservation=copy.deepcopy(ground.CAPABILITY),
            nativeGroundControlGate=dict(type='groundControlLayout',requiredForInput=True,capability=copy.deepcopy(ground.CAPABILITY)),
            hello=dict(groundControlObservation=copy.deepcopy(ground.CAPABILITY)),hybridNavigation=dict(requireGroundControls=True),
            decisions=[dict(frameId=2,acceptance=dict(type='accepted',requestId='inert'),scoutEncounterGuard=marker)])
        path=Path(folder)/'00001/events.jsonl';path.parent.mkdir()
        return dict(scoutEncounterGuardState=guard.snapshot()),part,frames,events,path,guard

    def test_replay_binds_native_gate_pixels_and_historical_declarations(self):
        from audit_hybrid_run import verify_scout_guard
        for change in ('none','ack','hello','pixels','stripped'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                run,part,frames,events,path,guard=self.fixture(folder)
                reuse={'scoutEncounterGuard':binding()}
                if change=='ack':part['nativeGroundControlGate']['requiredForInput']=False
                if change=='hello':part['hello']['groundControlObservation']['sourceWidth']=1280
                if change=='stripped':reuse={}
                if change=='pixels':
                    crop=events[0]['frame']['groundControlEvidence']['crops'][0]
                    raw=bytes(75*42*3);crop.update(rgbBase64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())
                path.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
                invoke=lambda:verify_scout_guard(run,[part],frames,[{'number':1}],folder,reuse)
                if change=='none':self.assertEqual(invoke()['observations'],2)
                else:
                    with self.assertRaises((ValueError,ScoutEncounterStop)):invoke()

    def test_unavailable_post_release_sample_cannot_prove_endpoint(self):
        from audit_hybrid_run import verify_scout_guard
        with tempfile.TemporaryDirectory() as folder:
            run,part,frames,events,path,guard=self.fixture(folder)
            events.append(guard.acknowledge_release(release_ack(201),0,202,'hybridEndpoint'))
            frames[3]=sample(3)
            events.append(guard.observe(frames[3],203))
            self.assertIsNone(guard.trip)
            run['scoutEncounterGuardState']=part['scoutEncounterGuardState']=guard.snapshot()
            part['hybridNavigationEvents']=[dict(type='hybridEndpointVerified',samples=[dict(frameId=3)])]
            path.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'ground-control layout'):
                verify_scout_guard(run,[part],frames,[{'number':1}],folder,{'scoutEncounterGuard':binding()})


if __name__=='__main__':unittest.main()
