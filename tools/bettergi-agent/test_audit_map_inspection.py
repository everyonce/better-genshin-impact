"""Exercise the independent map UI, its native source/receipt joins and the resumed walking requirement."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

import audit_map_inspection as audit


REPO=Path(__file__).resolve().parents[2]
ORIGIN=100_000_000
HZ=10_000_000


def tick(ms):
    return ORIGIN+ms*10_000


def frame(frame_id, ms, epoch=1, menu=False):
    """Create native coordinates and two independently represented clocks for a single original frame."""
    src=dict(captureEpoch='capture',timestamp100ns=tick(ms),capturedAtMs=ms,acquiredAtMs=ms+3,
             freshnessAtMs=ms,freshnessClockKind='reported_compositor_qpc')
    x,y=audit.PATROL_STATIONS[audit.JUNCTION]
    return dict(frameId=frame_id,width=1920,height=1080,captureEpoch='capture',timestamp100ns=tick(ms),
                acquiredAtMs=ms+3,knownMap=menu,sha256='d'*64,
                worldReadiness=dict(ready=not menu,reason='world_hud_missing' if menu else 'world_ready',
                                    epoch=epoch,sourceFrameId=frame_id,sourceFrame=src),
                navigationPose=dict(state='valid',frameId=frame_id,layerId='City_102',positionConfidence=.998,
                                    yawConfidence=.8,x=x,y=y,yawDegrees=12.0),
                motionEvidence=dict(status='normal',spaceKeyMatched=False))


def fixture():
    """Menu key and source records are synthetic; no game, controller or native call is executed."""
    hello=dict(sessionId='lease',ownerEpoch='owner',inputTelemetry=dict(sessionOriginAtStopwatchTicks=ORIGIN,stopwatchFrequency=HZ),
               inputEnabled=True,mapInspection=dict(version=1))
    before=[frame(i+1,m) for i,m in enumerate((100,190,280))]
    menu=[frame(i+4,m,2,True) for i,m in enumerate((430,515))]
    returned=[frame(i+6,m,2) for i,m in enumerate((680,770,860))]
    inputs=[dict(action=action,key=key,frameId=source['frameId'],requestedTicks=tick(down),releasedTicks=tick(up),outcome='released')
            for action,key,source,down,up in [('openMap','M',before[-1],290,343),('closeMap','ESCAPE',menu[-1],528,581)]]
    events=[]
    for idx,(op,key,at) in enumerate([('keyDown','M',291),('keyUp','M',341),('releaseAll',None,350),
                                        ('keyDown','ESCAPE',529),('keyUp','ESCAPE',579),('releaseAll',None,872)]):
        for stage in ('started','returned_unverified' if op=='releaseAll' else 'returned'):
            events.append(dict(sequence=len(events)+1,atMs=at+int(stage!='started'),requestId=None,
                               origin='release:client_release' if op=='releaseAll' else 'mapInspection',
                               call=dict(callId=idx+1,operation=op,stage=stage,key=key,mouseDx=0,mouseDy=0,error=None)))
    initial=dict(telemetryComplete=True,active=None,trackedState=dict(heldKeys=[],telemetryIncomplete=False,
                 releaseOutcome='returned_unverified'),lastSequence=0,events=[],lastInputEvent=dict(
                     call=dict(operation='releaseAll',stage='returned_unverified',error=None)))
    final=dict(copy.deepcopy(initial),events=events,lastSequence=len(events),lastInputEvent=events[-1])
    proof=dict(version=1,requestId='a'*32,phase='completed',reason=None,sessionId='lease',ownerEpoch='owner',
               originTicks=ORIGIN,frequency=HZ,startedTicks=tick(80),deadlineTicks=tick(12_080),before=before,
               map=menu,returned=returned,inputs=inputs,initialExecutionContext=initial,finalExecutionContext=final,pendingActions=0,
               finalReadiness=dict(ready=False,epoch=3,reason='client_release'),finalReleaseAtMs=874,ordinaryRequestsWhileFenced=0)
    return proof,hello


class MapTransactionTests(unittest.TestCase):
    def test_normal_r59_targets_original_game_and_rejects_recovery_or_identity_substitution(self):
        """The ordinary two-pulse path must retain the original R59 game lifetime as well as the input HWND."""
        proof,hello=fixture()
        hello['mapInspection'].update(recoveryVersion=1,wgcOnly=True,inputChannel='original-game-hwnd',gameProcessId=123,gameWindowHandle=456)
        proof.update(mode='inspection',priorEvidenceSha256=None,gameProcessId=123,gameWindowHandle=456)
        game=dict(processId=123,windowsSessionId=3,startedFileTime=789,executable='GenshinImpact.exe')
        tx=dict(mode='inspection',inspection=proof,hello=hello,protectedGame=game,identity=dict(child=dict(windowsSessionId=3)))
        lineage=dict(protectedGame=game,priorLineageSha256='c'*64)
        self.assertEqual(audit.validate_native_transaction(proof,hello)[0],proof['before'][0])
        self.assertEqual(audit.inspection_game_lineage(tx,hello,lineage,game),dict(gameProcessId=123,gameWindowHandle=456))
        for label,change in [
                ('another PID',lambda t:t['inspection'].update(gameProcessId=333)),
                ('another HWND',lambda t:t['inspection'].update(gameWindowHandle=777)),
                ('recovery substitution',lambda t:t['inspection'].update(mode='recovery')),
                ('absent mode',lambda t:t['inspection'].pop('mode')),
                ('foreign origin',lambda t:t['inspection'].update(priorEvidenceSha256='b'*64)),
                ('empty game window',lambda t:t['inspection'].update(gameWindowHandle=0))]:
            other=copy.deepcopy(tx)
            change(other)
            with self.subTest(label),self.assertRaises(ValueError): audit.validate_native_transaction(other['inspection'],other['hello'])
        def matching_wrong_pid(t,h,l,p):
            for row in (t['inspection'],t['hello']['mapInspection'],h['mapInspection']): row.update(gameProcessId=333)
        def stripped_headers(t,h,l,p):
            for row in (t['hello']['mapInspection'],h['mapInspection']):
                for k in ('recoveryVersion','gameProcessId','gameWindowHandle'): row.pop(k)
            for k in ('mode','gameProcessId','gameWindowHandle'): t['inspection'].pop(k)
        for label,change in [
                ('matching foreign process',matching_wrong_pid),('R59 downgraded to R58',stripped_headers),
                ('another protected lifetime',lambda t,h,l,p:p.update(startedFileTime=900)),
                ('walking aimed elsewhere',lambda t,h,l,p:h['mapInspection'].update(gameWindowHandle=777)),
                ('wrong game record',lambda t,h,l,p:t['protectedGame'].update(processId=333)),
                ('unbound lineage',lambda t,h,l,p:l.pop('protectedGame'))]:
            args=[copy.deepcopy(v) for v in (tx,hello,lineage,game)]
            change(*args)
            with self.subTest(label),self.assertRaises(ValueError): audit.inspection_game_lineage(*args)

    def test_complete_native_witness(self):
        proof,hello=fixture()
        self.assertEqual(len(audit.validate_native_transaction(proof,hello)),8)

    def test_wgc_lead_uses_first_acquisition_and_never_bypasses_a_response_barrier(self):
        proof,hello=fixture()
        trigger=proof['before'][-1]
        source=trigger['worldReadiness']['sourceFrame']
        # Already-acquired pixels can be delivered before WinRT's reported compositor timestamp.
        source.update(capturedAtMs=296,timestamp100ns=tick(296),freshnessClockKind='first_acquisition_qpc',freshnessAtMs=283)
        trigger['timestamp100ns']=source['timestamp100ns']
        self.assertEqual(len(audit.validate_native_transaction(proof,hello)),8)
        for label,mutate in [
                ('wrong anchor',lambda s:s.update(freshnessAtMs=296)),
                ('wrong clock kind',lambda s:s.update(freshnessClockKind='reported_compositor_qpc')),
                ('incorrect native origin',lambda s:s.update(capturedAtMs=298))]:
            other=copy.deepcopy(proof)
            mutate(other['before'][-1]['worldReadiness']['sourceFrame'])
            with self.subTest(label), self.assertRaises(ValueError): audit.validate_native_transaction(other,hello)
        menu=proof['map'][0]
        menu['acquiredAtMs']=390
        menu['worldReadiness']['sourceFrame'].update(acquiredAtMs=390,freshnessAtMs=390,freshnessClockKind='first_acquisition_qpc')
        with self.assertRaises(ValueError): audit.validate_native_transaction(proof,hello)

    def test_missing_stopped_duplicate_late_wrong_or_stale_native_receipt(self):
        def changed(duplicate): duplicate['inputs'].append(copy.deepcopy(duplicate['inputs'][0]))
        cases=[
            ('map absent',lambda p:p['map'].clear()),
            ('cancelled',lambda p:p.update(phase='failed',reason='userStop')),
            ('extra press',changed),
            ('late close',lambda p:p['inputs'][1].update(requestedTicks=tick(800),releasedTicks=tick(850))),
            ('wrong session',lambda p:p.update(sessionId='another')),
            ('substituted WGC',lambda p:p['map'][1].update(timestamp100ns=tick(519))),
            ('stale HUD',lambda p:p['returned'][0]['worldReadiness'].update(ready=False)),
            ('early HUD',lambda p:p['inputs'][1].update(releasedTicks=tick(650))),
            ('other binding',lambda p:p['inputs'][0].update(key='F')),
            ('wrong UI epoch',lambda p:[r['worldReadiness'].update(epoch=1) for r in p['returned']]),
            ('ordinary proposal',lambda p:p['finalExecutionContext']['events'][0].update(origin='dispatch')),
            ('rejected proposal',lambda p:p.update(ordinaryRequestsWhileFenced=1)),
            ('hidden events',lambda p:p['finalExecutionContext']['events'].pop(2)),
            ('extra input',lambda p:p['finalExecutionContext']['events'][5]['call'].update(operation='mouseMove')),
            ('pending',lambda p:p.update(pendingActions=1)),
            ('held',lambda p:p['finalExecutionContext']['trackedState']['heldKeys'].append('W')),
            ('old rearm',lambda p:p['finalReadiness'].update(epoch=1)),
            ('wrong release clock',lambda p:p.update(finalReleaseAtMs=870)),
        ]
        for label,alter in cases:
            with self.subTest(label):
                p,h=fixture()
                alter(p)
                with self.assertRaises(ValueError): audit.validate_native_transaction(p,h)

    def test_source_geometry_and_encoded_digest_are_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'sample.png'
            Image.new('RGB',(12,12)).save(p)
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): audit.original_png(p,digest,(13,12))
            with self.assertRaises(ValueError): audit.original_png(p,'a'*64,(12,12))

    def test_original_pixels_require_two_different_map_markers_in_their_own_rois(self):
        image=Image.new('RGB',audit.NATIVE_SIZE,color=(93,99,110))
        def place(name):
            roi,digest=audit.MAP_ASSETS[name]
            tile=audit.original_png(REPO/'BetterGenshinImpact/GameTask/QuickTeleport/Assets/1920x1080'/(name+'.png'),digest,None)
            image.paste(tile,(roi[0]+2,roi[1]+2))
        self.assertFalse(audit.known_map(audit.map_scores(image,REPO)))
        place('MapCloseButton')
        self.assertFalse(audit.known_map(audit.map_scores(image,REPO)))
        place('MapScaleButton')
        self.assertTrue(audit.known_map(audit.map_scores(image,REPO)))
        image=Image.new('RGB',audit.NATIVE_SIZE,color=(93,99,110))
        place('MapSettingsButton')
        self.assertFalse(audit.known_map(audit.map_scores(image,REPO)))
        place('MapCloseButton')
        self.assertTrue(audit.known_map(audit.map_scores(image,REPO)))

    def test_returned_g4_requires_original_bytes_and_three_sources_after_terminal_release(self):
        proof,_=fixture()
        release=dict(atMs=874,epoch=3)
        contract=dict(profile=audit.P2P_NATIVE,serverAdvertised=True)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            im=Image.new('RGB',(192,192),(67,88,122))
            im.save(folder/'returned.png')
            frames=[]
            for i,m in enumerate((980,1070,1160)):
                row=frame(i+11,m,epoch=3)
                frames.append(dict(frameId=row['frameId'],sourceFrame=row['worldReadiness']['sourceFrame'],
                                   frameWorldReadiness=row['worldReadiness'],worldReadiness=row['worldReadiness'],
                                   navigationPose=row['navigationPose'],motionEvidence=row['motionEvidence'],
                                   inputAvailable=True,serverNowMs=m+10,width=192,height=192,sourceWidth=1920,sourceHeight=1080,
                                   pixelFormat='rgb24',observationProfile=audit.P2P_NATIVE))
            good=dict(png='returned.png',frame=frames[-1],samples=frames,
                      sha256=hashlib.sha256((folder/'returned.png').read_bytes()).hexdigest(),
                      rgbSha256=hashlib.sha256(im.tobytes()).hexdigest())
            fixed=Mock()
            fixed.predict.return_value=dict(station=audit.JUNCTION)
            def run(snapshot):
                return audit.g4_witness(snapshot,folder,fixed,proof,'returned',release,contract)
            self.assertEqual(run(good)['capturedTicks'],tick(1160))
            fixed.predict.assert_called_once_with(im.tobytes())
            for name,alter in [('stale',lambda s:s['samples'][1].update(serverNowMs=1600)),
                               ('source digest',lambda s:s.update(rgbSha256='b'*64)),
                               ('pre-release epoch',lambda s:s['samples'][0]['worldReadiness'].update(epoch=2)),
                               ('extra action',lambda s:s['samples'][0].update(receipts=[dict(requestId='unowned')])),
                               ('too few poses',lambda s:s['samples'].pop(1))]:
                with self.subTest(name):
                    changed=copy.deepcopy(good)
                    alter(changed)
                    with self.assertRaises(ValueError): run(changed)

    def test_lamp_requires_an_actual_resumed_request_and_independent_photo(self):
        proof,hello=fixture()
        clock=audit.bridge_clock([{'hello':hello}])
        goal=dict(start=audit.JUNCTION,destination=audit.LAMP,verifiedLegs=1,plannedLegs=1,actions=1,
                  complete=True,photos=dict(complete=True,decodedStation=audit.LAMP,checkpointId=audit.G4_SHA256,frameId=30),
                  first=dict(firstDispatchTicks=tick(1120),frameId=12))
        good=dict(passed=True,stopVerified=False,start=audit.JUNCTION,requests=[goal],clock=clock)
        last=dict(frameId=10,capturedTicks=tick(990))
        self.assertEqual(audit.resumed_goal(good,proof,last),30)
        for label,alter in [('no lamp',lambda p:p.update(requests=[])),('no motion',lambda p:p['requests'][0].update(actions=0)),
                            ('early motion',lambda p:p['requests'][0]['first'].update(firstDispatchTicks=tick(900))),
                            ('other photo',lambda p:p['requests'][0]['photos'].update(decodedStation=audit.JUNCTION))]:
            with self.subTest(label):
                bad=copy.deepcopy(good)
                alter(bad)
                with self.assertRaises(ValueError): audit.resumed_goal(bad,proof,last)


if __name__=='__main__':
    unittest.main()
