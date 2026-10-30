"""Separate bounded endurance admission from both ordinary shadow and four-goal permissions."""
import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from destination_batch_sender import create_plan,encode,qualification_goals
from destination_queue_policy import BALANCED
from patrol_photo_survey import require_open_queue_photo_authority
from scene_photo_trial import admit as dispatch_admission,digest
import scene_endurance_trial as trial
import test_scene_photo_trial as short_fixture


class SceneEnduranceTests(unittest.TestCase):
    """Use synthetic review evidence to exercise immutable limits and exclusive claims without opening a game."""
    def setUp(self):
        """Reuse only the inert owner/model fixture; replace its plan with the real initial queue shape."""
        short_fixture.ScenePhotoTrialTests.setUp(self)
        self.plan=create_plan('stair-front',qualification_goals('stair-front',1,0))
        raw=encode(self.plan)
        (self.folder/'photo-requests.json').write_bytes(raw)
        owner=encode(dict(status='completed',identity=self.identity))
        self.previous=self.folder/'previous.json'
        self.previous.write_bytes(owner)
        (self.folder/'required-owner.json').write_bytes(owner)
        self.policy=dict(version=1,mode=BALANCED,targetGameplaySeconds=600,goalsPerBatch=4,maxBatches=40,maxLegs=256,
            initialPlanSha256=digest(raw),requiredOwnerManifestSha256=digest(owner),queueLimitsProfile='endurance-v1')
        (self.folder/'queue-policy.json').write_bytes(encode(self.policy))
        mocked=patch.object(trial,'reviewed_owner',return_value=(self.identity,self.previous))
        mocked.start()
        self.addCleanup(mocked.stop)
        self.path=self.folder/'scene-endurance-permit.json'
        self.permit=trial.issue(self.path,self.folder,self.identity,time.monotonic_ns()+899_000_000_000,self.folder/'goal.json')
        self.args.seconds=900
        self.args.hybrid_legs=256
        self.args.warm_open_queue=True
        self.args.warm_endurance=True
        self.args.warm_batch_count=40
        self.args.patrol_series_binding=tuple(self.permit['binding'])

    def test_exact_endurance_admits_once_through_the_common_dispatch(self):
        result=dispatch_admission(self.path,self.head,self.args)
        self.assertEqual(result['scope'],trial.SCOPE)
        require_open_queue_photo_authority(self.head)
        with self.assertRaises(FileExistsError):
            dispatch_admission(self.path,self.head,self.args)

    def test_short_trial_and_unadmitted_shadow_cannot_authorize_a_queue(self):
        with self.assertRaisesRegex(ValueError,'shadow-only'):
            require_open_queue_photo_authority(self.head)
        self.head._scene_photo_admission=dict(checkpointId=trial.CHECKPOINT,scope='four-goal-photo-trial')
        with self.assertRaisesRegex(ValueError,'no reviewed endurance'):
            require_open_queue_photo_authority(self.head)

    def test_policy_target_caps_and_identity_cannot_change_after_issue(self):
        for key,value in [('targetGameplaySeconds',601),('maxBatches',41),('maxLegs',257),('mode','manual'),
                          ('queueLimitsProfile','standard-v1')]:
            with self.subTest(field=key):
                changed=dict(self.policy,**{key:value})
                (self.folder/'queue-policy.json').write_bytes(encode(changed))
                with self.assertRaises(ValueError):
                    dispatch_admission(self.path,self.head,self.args)
                self.assertFalse((self.folder/'scene-photo-claim.json').exists())
        (self.folder/'queue-policy.json').write_bytes(encode(self.policy))
        (self.folder/'required-owner.json').write_bytes(self.previous.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'reviewed four-photo'):
            dispatch_admission(self.path,self.head,self.args)

    def test_closed_mode_larger_bounds_and_missing_endurance_flag_are_rejected(self):
        for key,value in [('seconds',901),('hybrid_legs',257),('warm_batch_count',41),
                          ('warm_open_queue',False),('warm_endurance',False),('max_observation_age_ms',151)]:
            with self.subTest(option=key):
                args=copy.copy(self.args)
                setattr(args,key,value)
                with self.assertRaises(ValueError):
                    dispatch_admission(self.path,self.head,args)
                self.assertFalse((self.folder/'scene-photo-claim.json').exists())

    def resident(self,**changes):
        """Construct the real request state with inert native identity and no model or input channel."""
        from warm_photo_requests import WarmPhotoRequests
        options=dict(batch_count=40,open_queue=True,limits_profile='endurance-v1',observer=self.head)
        options.update(changes)
        hello=dict(sessionId='lease',ownerEpoch='owner',inputTelemetry=dict(stopwatchFrequency=1000,sessionOriginAtStopwatchTicks=10))
        return WarmPhotoRequests(self.folder/'photo-requests.json',self.folder/'station-photos',trial.CHECKPOINT,
            self.folder/'goal.json',hello,'c'*32,256,**options)

    def test_resident_consumes_only_the_same_experimental_plan_and_scope(self):
        dispatch_admission(self.path,self.head,self.args)
        resident=self.resident()
        self.assertTrue(resident.open_queue)
        self.assertEqual(resident.identity['planSha256'],self.permit['planSha256'])

    def test_changed_plan_during_model_warmup_is_refused(self):
        dispatch_admission(self.path,self.head,self.args)
        path=self.folder/'photo-requests.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'consumed scene permission'):
            self.resident()
        self.assertFalse((self.folder/'station-photos').exists())

    def test_missing_observer_or_modified_queue_policy_is_refused(self):
        dispatch_admission(self.path,self.head,self.args)
        with self.assertRaisesRegex(ValueError,'bound scene experiment'):
            self.resident(observer=None)
        path=self.folder/'queue-policy.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'during model warm-up'):
            self.resident()
        self.assertFalse((self.folder/'station-photos').exists())


if __name__=='__main__':
    unittest.main()
