"""Regression coverage for receipt-backed changed turns and measured native-yaw reversals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from audit_camera_patrol import audit_camera, compare_patrols, yaw_reversals
from audit_hybrid_run import audit_shadow
from camera_response import CameraCalibration, fit_response, read_probe
from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE, route_heading
from test_camera_response import probe
from steering_head import CLASSES, FEATURES, FORMAT, SteeringHead
from test_steering_head import observation


class CameraAuditTests(unittest.TestCase):
    """Check the selector's journal independently of the game and its live controller."""

    def test_changed_turn_can_count_only_with_its_exact_checkpoint_source_journal_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            training = []
            for mode in ('train','holdout'):
                path = base/f'{mode}.json'
                path.write_text(json.dumps(probe(mode)))
                training.append(read_probe(path,mode))
            checkpoint = base/'checkpoint.json'
            checkpoint.write_text(json.dumps(fit_response(*training)))
            head = CameraCalibration.load(checkpoint)
            decisions, receipts, frames = [], [], {}
            for i, t in enumerate((1000,3000,5000), start=1):
                source = dict(captureEpoch='c', timestamp100ns=t*10000, capturedAtMs=t)
                p = dict(frameId=i, x=PATROL_STATIONS['stair-front'][0], y=PATROL_STATIONS['stair-front'][1],
                         layerId='City_102', positionConfidence=.999, yawConfidence=.8, state='valid')
                p['yawDegrees'] = (route_heading(p, PATROL_STATIONS['sidewalk-junction'])-12)%360
                frames[i] = dict(frameId=i, navigationPose=p, inputAvailable=True, sourceFrame=source,
                                 frameWorldReadiness=dict(ready=True, epoch=1, sourceFrameId=i, sourceFrame=source),
                                 motionEvidence=dict(status='normal',spaceKeyMatched=False))
                step = dict(durationMs=100, keys=[],mouseDy=0,mouseDx=96)
                meta = dict(selected=True,checkpointId=head.checkpoint_id,nativeMouseDx=24,proposedMouseDx=96,
                            errorDegrees=12, elapsedUs=4, previousMouseRequestId=str(i-1) if i>1 else None,
                            msSinceLastMouse=1850 if i>1 else None)
                h = dict(owner='calibrated-camera',reason='calibratedHeading',target='sidewalk-junction',
                         toStation='sidewalk-junction',pose=p,step=step)
                ack = dict(type='accepted',requestId=str(i),acceptedAtMs=t+20) if i<3 else dict(type='notSubmitted')
                d = dict(frameId=i,cameraCalibration=meta,hybridNavigation=h,steps=[step],observationTimestampMs=t,acceptance=ack)
                if i<3:
                    d['startBeforeMs']=t+150
                    receipts.append(dict(requestId=str(i),modelId='calibrated-camera',frameId=i,acceptedAtMs=t+20,
                         endedAtMs=t+130,status='completed',appliedSteps=[dict(keys=[],mouseDx=96,mouseDy=0,startedAtMs=t+30)]))
                decisions.append(d)
            (base/'00001').mkdir()
            def check(ds,rs,fs,journal=None):
                if journal is None:
                    journal = [dict(d,type='proposal',model='calibrated-camera',startBeforeMs=d.get('startBeforeMs')) for d in ds]+rs
                (base/'00001/events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in journal))
                return audit_camera([dict(decisions=ds,receipts=rs)],[dict(number=1)],base,fs,STREET_PATROL_ROUTE,checkpoint)
            self.assertEqual(check(decisions,receipts,frames),dict(selected=3,accepted=2,applied=2,checkpointId=head.checkpoint_id))
            for fault in ('wrongId','wrongDx','wrongGap','wrongPrev','wrongError','changedSource','receiptMouse',
                          'tooLate','duplicate','journalOnly','missingEntry','emptyApplied'):
                ds,rs,fs = copy.deepcopy((decisions,receipts,frames))
                if fault=='wrongId': ds[1]['cameraCalibration']['checkpointId']='other'
                if fault=='wrongDx': ds[1]['cameraCalibration']['proposedMouseDx']=95
                if fault=='wrongGap': ds[1]['cameraCalibration']['msSinceLastMouse']=1870
                if fault=='wrongPrev': ds[1]['cameraCalibration']['previousMouseRequestId']=None
                if fault=='wrongError': ds[1]['cameraCalibration']['errorDegrees']=-12
                if fault=='changedSource': fs[2]['frameWorldReadiness']['sourceFrameId']=99
                if fault=='receiptMouse': rs[1]['appliedSteps'][0]['mouseDy']=1
                if fault=='tooLate': rs[1]['appliedSteps'][0]['startedAtMs']=3151
                if fault=='duplicate': rs.append(dict(rs[1]))
                if fault=='emptyApplied':
                    rs[1]['appliedSteps']=[]
                    self.assertEqual(check(ds,rs,fs)['applied'],1)
                    continue
                events = [dict(d,type='proposal',model='calibrated-camera',startBeforeMs=d.get('startBeforeMs')) for d in ds]+rs
                if fault=='journalOnly': events[1]=dict(events[1],cameraCalibration={})
                if fault=='missingEntry': events.pop(1)
                with self.subTest(fault=fault), self.assertRaises(ValueError):
                    check(ds,rs,fs,events)

    def test_measured_yaw_wrap_jitter_and_source_gap(self):
        def frame(i, t, yaw):
            return dict(frameId=i, sourceFrame={'capturedAtMs':t},
                        navigationPose=dict(state='valid',frameId=i,layerId='City_102',yawConfidence=.8,yawDegrees=yaw),
                        frameWorldReadiness=dict(ready=True,epoch=1),motionEvidence={'status':'normal'})
        angles = [(0,355),(100,2),(150,4),(200,2),(250,356),(300,349),(700,50),(750,43),(800,42)]
        self.assertEqual(yaw_reversals([frame(i,t,a) for i,(t,a) in enumerate(angles)]),1)

    def test_shadow_confidence_is_recomputed_from_checkpoint_and_original_frame(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'00001').mkdir()
            path = root/'head.json'
            path.write_text(json.dumps(dict(format=FORMAT,classes=list(CLASSES),features=list(FEATURES),
                            deployment='shadow-only',weights=[[0.]*len(FEATURES) for _ in CLASSES])))
            head = SteeringHead.load(path)
            f = observation()
            target = 'sidewalk-junction'
            raw = [dict(keys=['W'],mouseDx=0,mouseDy=0)]
            h = dict(owner='hybrid-native', target=target, fromStation='stair-front',toStation=target,completedLegs=0)
            s = dict(checkpointId=head.checkpoint_id, prediction=head.predict(f,PATROL_STATIONS[target],raw),elapsedUs=31)
            d = dict(frameId=f['frameId'], hybridNavigation=h, steeringShadow=s,rawPolicySteps=raw,acceptance={'type':'notSubmitted'})
            def check():
                journal = dict(d,type='proposal',model='hybrid-native')
                (root/'00001/events.jsonl').write_text(json.dumps(journal)+'\n')
                return audit_shadow([d],{f['frameId']:f},{},[{'number':1}],root,STREET_PATROL_ROUTE,path)
            self.assertEqual(check()['classified'],1)
            s['prediction']['confidence'] = .99
            with self.assertRaisesRegex(ValueError,'exact checkpoint replay'):
                check()

    def test_compare_pairs_equal_circuit_counts_and_keeps_the_two_junction_legs_separate(self):
        order = ('A','B','C','B','A')
        def report(n):
            legs = [dict(fromStation=a,toStation=b,elapsedMs=100+i,appliedActions=3,yawReversals=0,commandReversals=1)
                    for i,(a,b) in enumerate(zip(order,order[1:]))]
            return dict(routeId=STREET_PATROL_ROUTE,verifiedCircuits=n,cameraCalibration={'selected':0},
                        patrolCircuits=[dict(legs=legs) for _ in range(n)])
        result = compare_patrols(report(6), report(4))
        self.assertEqual(result['pairedCircuits'],4)
        self.assertEqual([r['baseline']['totalLegMs'] for r in result['directedLegs']],[400,404,408,412])
