"""A dynamic route needs independent staged bytes, earlier movement, a held boundary and a single new owner."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_warm_batches import read_batches, verify_batch_events
from hybrid_routes import PATROL_STATIONS


class BatchEvidenceTests(unittest.TestCase):
    """Build independent sender, bridge and resident fixtures without accessing an input device."""
    def queue(self,folder,change):
        a,b,c='stair-front','sidewalk-junction','west-lamp'
        def plan(start,goals):
            return dict(version=2,mode='destinations',start=start,
                        requests=[dict(id=f'{n:032x}',name=f'photo-{n}',targets=[s],destination=s) for n,s in goals])
        plans=[plan(a,[(1,b),(2,c)]),plan(c,[(3,b),(4,a)])]
        if change=='wrong-start':
            plans[1]['start']=a
        if change=='duplicate-id':
            plans[1]['requests'][0]['id']=plans[0]['requests'][0]['id']
        initial=json.dumps(plans[0]).encode()
        common=dict(version=1,runId='run',sessionId='session',ownerEpoch='owner',batchOrdinal=2,
                    previousSha256=hashlib.sha256(initial).hexdigest(),
                    witness=dict(batchOrdinal=1,requestId=plans[0]['requests'][0]['id'],nativeRequestId='w',frameId=10))
        if change=='bad-hash-chain':
            common['previousSha256']='a'*64
        env=dict(common,mode='destination-batch',plan=plans[1])
        raw=json.dumps(env,sort_keys=True,separators=(',',':')).encode()
        common.update(batchSha256=hashlib.sha256(raw).hexdigest(),observedAtMonotonicNs=100)
        intent=dict(common,type='destinationBatchIntent',plan=plans[1])
        pub=dict(common,type='destinationBatchPublished',publishedAtMonotonicNs=110,
                 publicationQpc=dict(clock='windows-query-performance-counter',frequencyHz=1000,beforeTicks=1190,afterTicks=1195))
        if change=='bytes':
            raw+=b' '
        if change=='ambiguous-resealed':
            raw=raw.replace(b'"batchOrdinal":2',b'"batchOrdinal":1,"batchOrdinal":2',1)
            intent['batchSha256']=pub['batchSha256']=hashlib.sha256(raw).hexdigest()
        if change=='intent':
            intent['plan']=plans[0]
        if change=='future-witness':
            pub['witness']=dict(common['witness'],batchOrdinal=2)
        q=folder/'batches'
        q.mkdir()
        (q/'00002.json').write_bytes(raw)
        (q/'00002.intent.json').write_text(json.dumps(intent))
        (q/'00002.publication.json').write_text(json.dumps(pub))
        if change=='orphan':
            (q/'00003.json').write_bytes(raw)
        admission=dict(batchCount=2,maxLegs=4 if change!='budget' else 2,stopInBatch=None,stopRule=None)
        batches=read_batches(folder,plans,initial,admission,dict(runId='run'),False)
        return plans,batches

    def test_immutable_source_envelopes_and_budgets(self):
        for case in ('valid','wrong-start','duplicate-id','bad-hash-chain','bytes','intent','future-witness','orphan','budget',
                     'ambiguous-resealed'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                if case=='valid':
                    self.assertEqual(self.queue(Path(folder),case)[1][1]['firstRequestOrdinal'],3)
                else:
                    with self.assertRaises(ValueError):
                        self.queue(Path(folder),case)

    def test_only_a_live_published_admission_can_open_a_new_request(self):
        for change in ('valid','released-wait','stopped-prefix','unfinished-claim','wrong-lease','wrong-frame','wrong-receipt','before-walk','late',
                       'early-consume','early-proposal','wrong-digest','wrong-length','wrong-first','unreleased','orphan-accept',
                       'moved','stale-admission','wrong-batch-scope','wrong-policy','forged-frequency','wrong-source'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                plans,batches=self.queue(Path(folder),'valid')
                specs=[r for p in plans for r in p['requests']]
                first,second=batches
                old,new=specs[1]['id'],specs[2]['id']
                def event(kind,scope,i,fid):
                    return dict(type=kind,**{k:scope[k] for k in ('batchOrdinal','batchSha256','batchPlanSha256')},
                                ordinal=i,warmRequestId=specs[i-1]['id'],frameId=fid)
                done=event('warmPhotoRequestCompleted',first,2,20)
                done.update(release=dict(serverNowMs=200,readinessEpoch=3),completedLegs=2,
                            sourceEpoch='capture',lastAcceptedRequestId='final',goalEmbeddingSha256='g',planSha256='h',
                            name=specs[1]['name'],targets=specs[1]['targets'],destination='west-lamp')
                marker=dict(done,type='warmBatchAccepted',runId='run',sessionId='session',ownerEpoch='owner',
                            nextBatchOrdinal=2,nextBatchBytes=second['bytes'],nextBatchSha256=second['batchSha256'],
                            nextBatchPlanSha256=second['batchPlanSha256'],nextRequestId=new,pendingActionIds=[],
                            publicationWitness=second['envelope']['witness'],admissionFrameId=20,
                            consumedQpc=dict(clock='windows-query-performance-counter',frequencyHz=1000,ticks=1610))
                events=[done,marker,dict(done,type='warmPhotoHandoff',nextRequestId=new),event('warmPhotoRequestStarted',second,3,20)]
                groups=[[dict(nativeRequestId='w',frameId=10,terminalEndTicks=1180)],[],[dict(frameId=21,acceptedAtMs=700)],[]]
                clock=dict(originTicks=1000,frequency=1000,sessionId='session',ownerEpoch='owner')
                src=dict(capturedAtMs=600,captureEpoch='capture')
                x,y=PATROL_STATIONS['west-lamp']
                frames={20:dict(frameId=20,navigationPose=dict(frameId=20,state='valid',layerId='City_102',positionConfidence=1,
                                 yawConfidence=.8,x=x,y=y,yawDegrees=38),sourceFrame=src,inputAvailable=True,
                                 frameWorldReadiness=dict(sourceFrameId=20,sourceFrame=src,ready=True,epoch=3),
                                 motionEvidence=dict(status='normal',spaceKeyMatched=False))}
                decisions=[dict(frameId=21,warmRequestId=new,acceptance=dict(type='accepted',acceptedAtMs=700))]
                bracket=second['publication']['publicationQpc']
                if change=='released-wait':
                    bracket.update(beforeTicks=1510,afterTicks=1550)
                elif change=='wrong-lease':
                    second['envelope']['ownerEpoch']='other'
                elif change=='wrong-frame':
                    second['envelope']['witness']['frameId']=12
                elif change=='wrong-receipt':
                    groups[0][0]['nativeRequestId']='other'
                elif change=='before-walk':
                    bracket['beforeTicks']=1175
                elif change=='late':
                    bracket['afterTicks']=1620
                elif change=='early-consume':
                    marker['consumedQpc']['ticks']=1590
                elif change=='early-proposal':
                    decisions[0]['frameId']=20
                elif change=='wrong-digest':
                    marker['nextBatchSha256']='0'*64
                elif change=='wrong-length':
                    marker['nextBatchBytes']+=1
                elif change=='wrong-first':
                    marker['nextRequestId']=specs[3]['id']
                elif change=='unreleased':
                    marker['pendingActionIds']=['still-running']
                elif change=='orphan-accept':
                    events.insert(1,dict(marker))
                elif change=='moved':
                    frames[20]['navigationPose']['y']+=5
                elif change=='stale-admission':
                    marker['consumedQpc']['ticks']=1800
                elif change=='wrong-batch-scope':
                    events[-1]['batchOrdinal']=1
                elif change=='wrong-policy':
                    marker['goalEmbeddingSha256']='changed'
                elif change=='forged-frequency':
                    bracket['frequencyHz']=10000
                elif change=='wrong-source':
                    frames[20]['frameWorldReadiness']['epoch']=4
                elif change in ('stopped-prefix','unfinished-claim'):
                    specs=specs[:3]
                    groups=groups[:3]
                def replay():
                    return verify_batch_events(events,batches,groups,frames,clock,specs,change=='stopped-prefix',decisions)
                if change in ('valid','released-wait','stopped-prefix'):
                    proof,=replay()
                    self.assertEqual(proof['status'],'accepted')
                    self.assertEqual(proof['stagedBeforeRelease'],change!='released-wait')
                else:
                    with self.assertRaises(ValueError):
                        replay()
