"""A stationary recheck must preserve the original release, image, controller ownership and deadlines."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image

from audit_destination_retries import (RELEASE_REJECTED, RELEASE_RETRY, RETRY, verify_release_order, verify_release_reissues,
                                      verify_retry_images, verify_retry_poses)
from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE


class StationaryRetryAuditTests(unittest.TestCase):
    """Exercise a synthetic, source-backed single release with zero game or controller access."""
    def evidence(self, reason='classificationMiss', count=1):
        a,b='stair-front','sidewalk-junction'
        frames={}
        def sample(fid):
            x,y=PATROL_STATIONS[b]
            s=dict(frameId=fid,atMs=100*fid,x=x,y=y,yawDegrees=32)
            src=dict(captureEpoch='wgc',timestamp100ns=fid*1000000,capturedAtMs=100*fid)
            frames[fid]=dict(frameId=fid,sourceFrame=src,inputAvailable=True,motionEvidence=dict(status='normal',spaceKeyMatched=False),
                frameWorldReadiness=dict(ready=True,epoch=2,sourceFrameId=fid,sourceFrame=src),
                navigationPose=dict(frameId=fid,x=x,y=y,yawDegrees=32,state='valid',layerId='City_102',
                                    positionConfidence=1,yawConfidence=.9))
            return s
        binding=dict(routeId=STREET_PATROL_ROUTE,releaseAtMs=100,releaseEpoch=2,arrivalFrameId=1,sourceEpoch='wgc',
            navigationMode='itinerary',segmentIndex=0,destinationOrdinal=1,requestedDestination=b,
            fromStation=a,toStation=b,station=b,completedLegs=1,warmRequestId='first')
        poses=[sample(n) for n in (2,3,4)]
        end=dict(type='hybridEndpointVerified',samples=poses,photoSurveyVisit=dict(outcome=reason),**binding)
        events=[end,dict(type='hybridDestinationVerified',frameId=4,**binding)]
        for i in range(count):
            stop=7+3*i
            poses=[sample(n) for n in range(stop-2,stop+1)]
            events.append(dict(type=RETRY,samples=poses,frameId=stop,atMs=stop*100,initialEndpointFrameId=4,
                               retryOrdinal=i+1,photoSurveyVisit=dict(outcome='classificationMiss'),**binding))
        return events,frames,[dict(decisions=[],controlTransitions=[])],{}

    def test_every_retry_binds_three_new_stable_sources_and_the_same_release(self):
        for case in ('valid','valid-confirm','undeclared-confirm','wrong-request','wrong-release','wrong-source','old-frame',
                     'gap','different-pose','old-clock','too-late','too-many','early-retry','after-success','input',
                     'proposal','extra-release','unready','pose-drift','duplicate-source','wrong-target'):
            with self.subTest(case=case):
                why='confirmationPending' if 'confirm' in case else 'classificationMiss'
                events,frames,parts,receipts=self.evidence(why,4 if case=='too-many' else 2)
                retry=events[-1]
                if case=='wrong-request':
                    retry['warmRequestId']='second'
                elif case=='wrong-release':
                    retry['releaseEpoch']=3
                elif case=='wrong-source':
                    frames[9]['sourceFrame']['captureEpoch']='other'
                elif case=='old-frame':
                    retry['samples'][0]=deepcopy(events[-2]['samples'][-1])
                elif case=='gap':
                    retry['samples'][0]['atMs']-=30
                elif case=='different-pose':
                    retry['samples'][0]['yawDegrees']+=2
                elif case=='old-clock':
                    frames[9]['sourceFrame']['capturedAtMs']-=3
                elif case=='too-late':
                    retry['atMs']=2100
                    retry['samples'][-1]['atMs']=2100
                elif case=='early-retry':
                    events.insert(-1,dict(type='unexpected'))
                elif case=='after-success':
                    events[-2]['photoSurveyVisit']['outcome']='collected'
                elif case=='input':
                    receipts['x']=dict(acceptedAtMs=500,endedAtMs=600,appliedSteps=[dict(startedAtMs=510)])
                elif case=='proposal':
                    parts[0]['decisions'].append(dict(frameId=6))
                elif case=='extra-release':
                    parts[0]['controlTransitions'].append(dict(frameId=6,state='held'))
                elif case=='unready':
                    frames[6]['frameWorldReadiness']['ready']=False
                elif case=='pose-drift':
                    frames[9]['navigationPose']['yawDegrees']+=6
                    retry['samples'][1]['yawDegrees']+=6
                elif case=='duplicate-source':
                    frames[6]['sourceFrame']['timestamp100ns']=frames[5]['sourceFrame']['timestamp100ns']
                elif case=='wrong-target':
                    events[0]['requestedDestination']='west-lamp'
                def check():
                    return verify_retry_poses(events,frames,parts,receipts,case=='valid-confirm')
                if case in ('valid','valid-confirm'):
                    self.assertEqual(len(check()[4]),2)
                else:
                    with self.assertRaises(ValueError):
                        check()

    def test_true_miss_and_predeclared_confirmation_reproduce_exact_saved_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            directory=root/'retry-evidence'
            directory.mkdir()
            path=directory/'west-lamp-frame-9.png'
            im=Image.new('RGB',(192,192),(30,60,90))
            im.save(path)
            pixels=im.tobytes()
            for case in ('real-miss','confirmation','false-miss','unplanned-confirmation','wrong-file','different-pixels'):
                with self.subTest(case=case):
                    confirm=case in ('confirmation','unplanned-confirmation')
                    predicted='west-lamp' if confirm or case=='false-miss' else 'sidewalk-junction'
                    head=Mock()
                    head.predict.return_value=dict(station=predicted,squaredDistance=1.5)
                    row=dict(frameId=9,station='west-lamp',outcome='confirmationPending' if confirm else 'classificationMiss',
                             retryEvidenceFile='retry-evidence/'+path.name,
                             retryEvidencePngSha256=hashlib.sha256(path.read_bytes()).hexdigest())
                    source=dict(frameId=9,native='west-lamp',live=predicted,liveSquaredDistance=1.5,
                                liveRgbSha256=hashlib.sha256(pixels).hexdigest())
                    if case=='wrong-file':
                        row['retryEvidenceFile']='another/'+path.name
                    elif case=='different-pixels':
                        source['liveRgbSha256']='0'*64
                    def checked():
                        return verify_retry_images(root,[row],[source],head,case=='confirmation')
                    if case in ('real-miss','confirmation'):
                        self.assertEqual(checked()[0]['outcome'],row['outcome'])
                        head.predict.assert_called_once_with(pixels)
                    else:
                        with self.assertRaises(ValueError):
                            checked()

    def test_rejected_release_needs_its_original_telemetry_then_a_fresh_accepted_release(self):
        for case in ('valid','unearned','wrong-reason','bad-telemetry','wrong-release','one-frame','stale',
                     'late','moving','epoch','input','proposal','fabricated','missing','another-release'):
            with self.subTest(case=case):
                base,frames,parts,receipts=self.evidence()
                binding={k:v for k,v in base[0].items() if k in ('routeId','station','sourceEpoch','navigationMode',
                    'segmentIndex','fromStation','toStation','destinationOrdinal','requestedDestination','warmRequestId')}
                done=dict(binding,type='hybridEndpointVerified',firstArrivalFrameId=4,arrivalFrameId=6,
                          completedLegs=1,releaseEpoch=4,releaseAtMs=625)
                for fid in (5,6):
                    frames[fid]['frameWorldReadiness']['epoch']=3
                gate=dict(epoch=3,ready=False,reason='world_observation_invalidated',sourceFrame=frames[4]['sourceFrame'])
                execution=dict(telemetryComplete=True,active=None,sampledAtMs=425,trackedState=dict(heldKeys=[],
                    telemetryIncomplete=False,releaseOutcome='returned_unverified'),lastInputEvent=dict(atMs=420,
                    origin='release:client_release',call=dict(operation='releaseAll',stage='returned_unverified',error=None)))
                bad=dict(binding,type=RELEASE_REJECTED,completedLegs=0,firstArrivalFrameId=4,arrivalEpoch=2,
                         rejectedAtMs=425,rejectedReadiness=gate,rejectedExecution=execution)
                ready=dict(binding,type=RELEASE_RETRY,completedLegs=0,firstArrivalFrameId=4,retryArrivalFrameId=6,
                           samples=deepcopy(base[2]['samples'][:2]))
                events=[bad,ready,done]
                def held(fid,reason,at,epoch):
                    return dict(state='held',reason='hybridEndpoint',frameId=fid,warmRequestId='first',
                        warmRelease=dict(type='released',arrivalFrameId=fid,serverNowMs=at,readinessEpoch=epoch,
                            captureEpoch='wgc',readinessReason=reason,readinessReady=False,policyHistoryReset=True))
                first=held(4,'world_observation_invalidated',425,3)
                first.update(rejectedReadiness=deepcopy(gate),rejectedExecution=deepcopy(execution))
                last=held(6,'client_release',625,4)
                parts[0]['controlTransitions']=[first,last]
                if case=='unearned':
                    events.pop(1)
                elif case=='wrong-reason':
                    bad['rejectedReadiness']['reason']='client_release'
                elif case=='bad-telemetry':
                    first['rejectedExecution']['trackedState']['heldKeys']=['W']
                elif case=='wrong-release':
                    last['warmRelease']['readinessReason']='world_observation_invalidated'
                elif case=='one-frame':
                    ready['samples'][1]=ready['samples'][0]
                elif case=='stale':
                    ready['samples'][0]['atMs']=420
                elif case=='late':
                    ready['samples'][1]['atMs']=1300
                elif case=='moving':
                    frames[6]['navigationPose']['x']+=3
                elif case=='epoch':
                    frames[5]['frameWorldReadiness']['epoch']=2
                elif case=='input':
                    receipts['bad']=dict(acceptedAtMs=490,endedAtMs=520,appliedSteps=[dict(startedAtMs=500)])
                elif case=='proposal':
                    parts[0]['decisions'].append(dict(frameId=5))
                elif case=='fabricated':
                    first['rejectedReadiness']['sourceFrame']={}
                elif case=='missing':
                    events[:]=[]
                elif case=='another-release':
                    parts[0]['controlTransitions'].insert(1,held(5,'client_release',550,3))
                if case=='valid':
                    proof,=verify_release_reissues(events,frames,parts,receipts)
                    self.assertEqual((proof['rejectedEpoch'],proof['acceptedEpoch']),(3,4))
                else:
                    with self.assertRaises(ValueError):
                        verify_release_reissues(events,frames,parts,receipts)

    def test_ready_source_must_precede_second_ack_in_the_original_mixed_event_journal(self):
        end=dict(type='hybridEndpointVerified',firstArrivalFrameId=4,arrivalFrameId=6)
        trace=[('held',4),(RELEASE_REJECTED,4),(RELEASE_RETRY,6),('held',6),('hybridEndpointVerified',6)]
        verify_release_order(trace,[end])
        trace[2],trace[3]=trace[3],trace[2]
        with self.assertRaises(ValueError):
            verify_release_order(trace,[end])
