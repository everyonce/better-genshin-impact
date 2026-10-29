"""Exercise the open-queue producer from immutable plans and synthetic native receipt milestones."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import destination_batch_sender as sender
from destination_queue_policy import BALANCED, least_visited
from hybrid_routes import PATROL_SEGMENTS
import run_destination_batches as batches
import run_rdp_patrol as patrol
import run_warm_photo_requests as warm
import test_destination_batch_sender as existing


class QueueProducerTests(unittest.TestCase):
    """Use the same inert resident and pinned control files as the existing GUI-free sender tests."""
    setUp = existing.SenderTests.setUp
    witnessed = existing.SenderTests.witnessed

    def open(self,manual=False,cap=3,legs=24,target=8):
        self.witnessed()
        planner = dict(version=1,mode='manual' if manual else BALANCED,targetGameplaySeconds=None if manual else target,goalsPerBatch=4)
        data = dict(**planner,maxLegs=legs,maxBatches=cap,initialPlanSha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
                    requiredOwnerManifestSha256='a'*64)
        raw = sender.encode(data)
        (self.folder/'queue-policy.json').write_bytes(raw)
        self.summary.update(batchCount=cap,maxLegs=legs,manualSubmission=manual,openQueue=True,planner=planner,
                            queuePolicySha256=hashlib.sha256(raw).hexdigest())
        (self.folder/'warm-launcher.json').write_bytes(sender.encode(self.summary))
        self.warm['gameplayClock'] = dict(frequencyHz=1000,firstAppliedTicks=51,witnessAppliedTicks=51,
                                         firstNativeRequestId=self.warm['activeFirstAppliedRequestId'],firstFrameId=8)
        self.status.write_bytes(sender.encode(self.warm))

    def issue(self,batch,goals=None,finish=False):
        with patch.object(patrol,'native_qpc_sample',side_effect=[(1000,20000),(1000,20001)]):
            return sender.submit(self.folder,batch,goals,finish=finish)

    def current(self,batch,elapsed):
        """Simulate the current lease actually admitting the published plan, then applying one step."""
        plans = sender.admitted_plans(self.folder)
        base = self.folder/'batches'/f'{batch:05d}.json'
        self.warm.update(activeRequestId=plans[-1]['requests'][0]['id'],batchOrdinal=batch,
                         activeOrdinal=1+sum(len(p['requests']) for p in plans[:-1]),activeFirstAppliedFrameId=batch*10,
                         activeFirstAppliedRequestId=f'{batch:032x}',batchSha256=hashlib.sha256(base.read_bytes()).hexdigest())
        self.warm['gameplayClock']['witnessAppliedTicks']=51+elapsed*1000
        self.status.write_bytes(sender.encode(self.warm))

    def test_goal_selection_then_native_elapsed_finish_before_cap(self):
        self.open()
        self.issue(2)
        base = self.folder/'batches'
        walking = sender.read_json(base/'00002.decision.json')
        digest=hashlib.sha256((base/'00002.decision.json').read_bytes()).hexdigest()
        for suffix in ('.intent.json','.publication.json'):
            self.assertEqual(sender.read_json(base/('00002'+suffix))['policyDecisionSha256'],digest)
        self.assertEqual(walking['reason'],'balancedVisits')
        self.assertEqual(walking['usedLegs'],len(self.first['requests']))
        self.assertEqual(walking['completedRequestIds'],[])
        self.assertEqual(len(walking['selectedStations']),4)
        self.current(2,8)
        self.issue(3)
        finish = sender.read_json(base/'00003.json')
        decision = sender.read_json(base/'00003.decision.json')
        self.assertNotIn('plan',finish)
        self.assertEqual(finish['kind'],'finish')
        self.assertEqual(decision['reason'],'gameplayTargetReached')
        self.assertEqual(decision['completedRequestIds'],[r['id'] for r in self.first['requests']])
        self.assertEqual(decision['selectedStations'],[])
        self.assertEqual(len(sender.admitted_plans(self.folder)),2)

    def test_standalone_finish_uses_the_same_slot_and_rejects_a_later_submit(self):
        self.open(manual=True)
        with patch.object(batches,'verify_manual_lease') as admit,patch.object(batches.socket,'gethostname',return_value='SIREN'),\
                patch.object(patrol,'native_qpc_sample',side_effect=[(1000,100),(1000,101)]):
            self.assertEqual(batches.main(['finish','--folder',str(self.folder),'--batch','2','--wait-seconds','0']),0)
            admit.assert_called_once()
        self.assertEqual(sender.read_json(self.folder/'batches/00002.decision.json')['reason'],'operatorFinish')
        with self.assertRaisesRegex(ValueError,'already claimed'):
            self.issue(2,self.goals)
        with self.assertRaisesRegex(ValueError,'predecessor'):
            self.issue(3,self.goals)

    def test_automatic_finish_is_allowed_at_the_thirteenth_slot_but_cannot_walk(self):
        self.open(cap=12,legs=96,target=500)
        for batch in range(2,13):
            self.issue(batch)
            self.current(batch,batch)
        self.issue(13)
        final = sender.read_json(self.folder/'batches/00013.decision.json')
        self.assertEqual((final['reason'],final['selectedStations']),('batchLimitReached',[]))
        self.assertEqual(len(sender.admitted_plans(self.folder)),12)

    def test_missing_witness_refuses_early_selection_and_stop_wins(self):
        self.open()
        self.warm['activeFirstAppliedRequestId']=None
        self.status.write_bytes(sender.encode(self.warm))
        with patch.object(sender,'choose',side_effect=AssertionError('planned before a positive witness')):
            self.assertIsNone(self.issue(2))
        (self.folder/'STOP').touch()
        with self.assertRaisesRegex(ValueError,'closed'):
            self.issue(2)

    def test_leg_cap_and_inspection_based_selection(self):
        self.open(legs=3)
        self.issue(2)
        self.assertEqual(sender.read_json(self.folder/'batches/00002.decision.json')['reason'],'legLimitReached')
        counts = dict.fromkeys(('stair-front','sidewalk-junction','west-lamp'),0)
        approaches = {a+'>'+b:0 for a,b in PATROL_SEGMENTS}
        alternatives = [least_visited('stair-front',dict(counts,**{s:9}),counts,approaches,8,12) for s in counts]
        self.assertGreater(len(set(map(tuple,alternatives))),1)

    def test_owner_pin_and_policy_precede_any_broker_dispatch(self):
        owner = self.folder/'prior.json'
        pair = {name:dict(processId=pid,instanceNonce='a'*32,windowsSessionId=pid) for name,pid in (('root',1),('child',2))}
        owner.write_bytes(sender.encode(dict(status='completed',identity=pair)))
        args = batches.launch_options(['--open-queue','--batches','12','--leg-limit','96','--target-gameplay-seconds','210',
              '--seconds','400','--owner-from',str(owner),'--start-station','stair-front','--landmark-shadow','m','--photo-qualification','q'])
        fresh = self.folder/'launch'
        fresh.mkdir()
        def stopped(args,folder,series):
            self.assertEqual(series.required_identity,pair)
            self.assertEqual((folder/'required-owner.json').read_bytes(),owner.read_bytes())
            summary = sender.read_json(folder/'warm-launcher.json')
            self.assertEqual(summary['queuePolicySha256'],hashlib.sha256((folder/'queue-policy.json').read_bytes()).hexdigest())
            self.assertIn('--warm-open-queue',patrol.patrol_argv(args,3,folder))
            raise RuntimeError('offline boundary')
        with patch.object(warm.socket,'gethostname',return_value='SIREN'),patch.object(patrol,'run',side_effect=stopped):
            result = warm.run(args,fresh,guard_type=batches.BatchGuard)
        self.assertEqual(result['reason'],'offline boundary')
