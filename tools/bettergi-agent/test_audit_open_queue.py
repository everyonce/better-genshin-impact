"""Adversarial policy and terminal packet checks for open destination queues."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_open_queue import best_destinations, finish_packet, route_stats, verify_decision, verify_terminal_boundary, STATIONS
from audit_queue_failure import starvation_outcome
from hybrid_routes import PATROL_STATIONS


class OpenQueueTests(unittest.TestCase):
    """A positive native witness and immutable sender intent are required before a finish or another batch."""

    def test_expired_slot_classification_needs_native_publication_clocks(self):
        clock=dict(frequency=10,sessionId='s',ownerEpoch='o')
        prior=dict(batchOrdinal=1,plan=dict(requests=[dict(id='a')]))
        groups={'a':[dict(frameId=5,nativeRequestId='n',terminalEndTicks=7)]}
        env=dict(sessionId='s',ownerEpoch='o',witness=dict(requestId='a',nativeRequestId='n',frameId=5,batchOrdinal=1))
        def slot(begin,end):
            return dict(envelope=env,publication=dict(publicationQpc=dict(clock='windows-query-performance-counter',
                                                      frequencyHz=10,beforeTicks=begin,afterTicks=end)))
        def check(slots):
            return starvation_outcome(slots,10,clock,groups,prior)
        self.assertEqual(check([]),'missing-successor')
        self.assertEqual(check([slot(11,12)]),'late-successor')
        self.assertEqual(check([slot(9,10)]),'published-unconsumed')
        self.assertEqual(check([slot(9,11)]),'publication-crossed-deadline')
        with self.assertRaises(ValueError):
            check([slot(6,12)])
        with self.assertRaises(ValueError):
            check([dict(slot(11,12),envelope=dict(env,ownerEpoch='another'))])

    def test_terminal_finish_requires_scoped_bytes_no_late_action_and_fresh_stationary_frame(self):
        station='stair-front';x,y=PATROL_STATIONS[station]
        done=dict(runId='r',sessionId='s',ownerEpoch='o',ordinal=2,warmRequestId='b',planSha256='p',
                  goalEmbeddingSha256='g',batchOrdinal=1,batchSha256='bs',batchPlanSha256='bp',name='photo',targets=[station],
                  destination=station,frameId=80,sourceEpoch='source',completedLegs=3,
                  release=dict(serverNowMs=6,readinessEpoch=9),lastAcceptedRequestId='lat')
        slot=dict(batchOrdinal=2,batchSha256='terminal',intentSha256='intent',publicationSha256='pub',bytes=50,
                  envelope=dict(witness={'frameId':1}),publication=dict(publicationQpc=dict(clock='windows-query-performance-counter',afterTicks=8)))
        qpc=dict(clock='windows-query-performance-counter',frequencyHz=1000,ticks=12)
        mark=dict(done,consumedQpc=qpc,admissionFrameId=80,pendingActionIds=[],decisionOrdinal=2,decisionSha256='terminal',
                  intentSha256='intent',publicationSha256='pub',decisionBytes=50,publicationWitness={'frameId':1})
        src=dict(capturedAtMs=10,captureEpoch='source')
        f=dict(inputAvailable=True,sourceFrame=src,frameWorldReadiness=dict(ready=True,sourceFrameId=80,sourceFrame=src,epoch=9),
               motionEvidence=dict(status='normal',spaceKeyMatched=False),navigationPose=dict(frameId=80,state='valid',layerId='City_102',
               positionConfidence=1,yawConfidence=.99,x=x,y=y,yawDegrees=3))
        def verify(m=mark,frame=f,last_end=4):
            verify_terminal_boundary(m,done,slot,station,[[{'terminalEndTicks':last_end}]],{80:frame},
                                     dict(originTicks=0,frequency=1000),2000)
        verify()
        for field in ('decisionSha256','intentSha256','publicationSha256','ownerEpoch','warmRequestId'):
            with self.subTest(field=field),self.assertRaises(ValueError):
                verify(dict(mark,**{field:'tampered'}))
        for field,val in [('ticks',1011),('frequencyHz',2)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                verify(dict(mark,consumedQpc=dict(qpc,**{field:val})))
        with self.assertRaises(ValueError):
            verify(last_end=13)
        with self.assertRaises(ValueError):
            verify(dict(mark,pendingActionIds=['native']))
        with self.assertRaises(ValueError):
            verify(frame=dict(f,inputAvailable=False))

    def test_wrong_counts_early_finish_and_wrong_witness(self):
        specs=[dict(id='a',destination='sidewalk-junction'),dict(id='b',destination='west-lamp')]
        batch=dict(batchOrdinal=1,plan=dict(start='stair-front',requests=specs))
        recv=lambda rid,t,f:dict(nativeRequestId=rid,frameId=f,firstDispatchTicks=t,terminalEndTicks=t+5)
        groups=[[recv('native-a',100,1)],[recv('native-b',112,4)]]
        w=dict(batchOrdinal=1,requestId='b',nativeRequestId='native-b',frameId=4)
        binding=dict(version=1,runId='r',sessionId='s',ownerEpoch='o',batchOrdinal=2,previousSha256='p',witness=w)
        bracket=dict(clock='windows-query-performance-counter',frequencyHz=1,beforeTicks=119,afterTicks=120)
        slot=dict(batchOrdinal=2,batchSha256='current',publication=dict(publicationQpc=bracket,observedAtMonotonicNs=10),
                  envelope=dict(binding,kind='finish'))
        clock=dict(sessionId='s',ownerEpoch='o',frequency=1)
        policy=dict(mode='balanced-native-visits-v1',maxLegs=50,maxBatches=8,targetGameplaySeconds=10)
        _,approaches=route_stats('stair-front',['sidewalk-junction','west-lamp'])
        doc=dict(binding,type='destinationQueueDecision',batchSha256='current',policySha256='policy',observedAtMonotonicNs=10,
                 activeOrdinal=2,completedRequestIds=['a'],gameplayClock=dict(frequencyHz=1,firstAppliedTicks=100,
                 witnessAppliedTicks=112,firstNativeRequestId='native-a',firstFrameId=1),
                 requestedCounts=dict(zip(STATIONS,(0,1,1))),verifiedCounts=dict(zip(STATIONS,(0,1,0))),
                 approachCounts=dict(approaches),usedLegs=2,predecessorEnd='west-lamp',selectedStations=[],reason='gameplayTargetReached')
        def check(d=doc,s=slot,p=policy):
            return verify_decision(d,s,[batch],groups,p,'policy',clock)
        self.assertEqual(check()['elapsedGameplaySeconds'],12)
        for reason,params in [('batchLimitReached',dict(maxBatches=1)),('legLimitReached',dict(maxLegs=3))]:
            with self.subTest(reason=reason):
                cap=dict(policy,targetGameplaySeconds=15,**params)
                self.assertEqual(check(dict(doc,reason=reason),p=cap)['reason'],reason)
                with self.assertRaises(ValueError):
                    check(p=cap)
        manual=dict(policy,targetGameplaySeconds=None,mode='manual')
        self.assertEqual(check(dict(doc,reason='operatorFinish'),p=manual)['reason'],'operatorFinish')
        for field,value in [('activeOrdinal',1),('completedRequestIds',[]),('reason','batchLimitReached'),('usedLegs',0),
                            ('gameplayClock',dict(doc['gameplayClock'],witnessAppliedTicks=900))]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                check(dict(doc,**{field:value}))
        with self.assertRaises(ValueError):
            check(p=dict(policy,targetGameplaySeconds=15))
        tampered=copy.deepcopy(slot);tampered['publication']['publicationQpc']['beforeTicks']=115
        with self.assertRaises(ValueError):
            check(s=tampered)

    def test_station_and_terminal_approach_accounting_and_short_budget(self):
        costs,approaches=route_stats('stair-front',['west-lamp','stair-front'])
        self.assertEqual(costs,4)
        self.assertEqual(approaches['sidewalk-junction>stair-front'],1)
        counts=dict.fromkeys(STATIONS,0)
        seq=best_destinations('stair-front',2,counts,counts,approaches,5)
        self.assertEqual(route_stats('stair-front',seq)[0],2)
        self.assertEqual(best_destinations('stair-front',1,counts,counts,approaches,5),[])

    def test_changed_finish_bytes_and_substituted_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);q=folder/'batches';q.mkdir()
            b=dict(batchOrdinal=1,batchSha256='x')
            shared=dict(version=1,runId='r',sessionId='s',ownerEpoch='o',batchOrdinal=2,previousSha256='x',
                        witness=dict(batchOrdinal=1,requestId='q',nativeRequestId='n',frameId=3))
            wire=dict(shared,kind='finish',mode='destination-batch')
            raw=json.dumps(wire,sort_keys=True,separators=(',',':')).encode()
            (q/'00002.json').write_bytes(raw)
            (q/'00002.decision.json').write_bytes(b'{}')
            common=dict(shared,batchSha256=hashlib.sha256(raw).hexdigest(),observedAtMonotonicNs=1,
                        policyDecisionSha256=hashlib.sha256(b'{}').hexdigest())
            (q/'00002.intent.json').write_text(json.dumps(dict(common,kind='finish',type='destinationBatchIntent')))
            (q/'00002.publication.json').write_text(json.dumps(dict(common,type='destinationBatchPublished',
                                                   publishedAtMonotonicNs=2,publicationQpc={})))
            self.assertEqual(finish_packet(folder,b,'r')['bytes'],len(raw))
            (q/'00002.json').write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'Finish bytes'):
                finish_packet(folder,b,'r')
            (q/'00002.json').write_bytes(raw)
            (q/'00002.decision.json').write_bytes(b'{ }')
            with self.assertRaisesRegex(ValueError,'policy bytes'):
                finish_packet(folder,b,'r')


if __name__=='__main__':
    unittest.main()
