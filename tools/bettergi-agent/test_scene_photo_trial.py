"""Exercise the short photo exception with synthetic evidence, without GPU allocation or game control."""
import copy
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gpu_landmark_observer import FORMAT as SCENE_FORMAT
from hybrid_routes import STREET_PATROL_ROUTE
from patrol_photo_survey import require_photo_metric
from scene_photo_trial import CHECKPOINT,DESTINATIONS,admit,issue,require_admission,validate_context


class ScenePhotoTrialTests(unittest.TestCase):
    """A shadow score alone never becomes an unrestricted photography or controller permission."""
    def setUp(self):
        """Use synthetic owner identities and a temporary plan; prerequisite evidence is explicitly mocked."""
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name).resolve()
        self.identity=dict(root=dict(processId=10,instanceNonce='a'*32,windowsSessionId=1),
            child=dict(processId=20,instanceNonce='b'*32,windowsSessionId=3))
        mock=patch('scene_photo_trial.prerequisites',return_value=self.identity)
        mock.start()
        self.addCleanup(mock.stop)
        self.plan=dict(version=2,mode='destinations',start='stair-front',requests=[
            dict(id=f'{i:032x}',name=f'trial-{i}',destination=s,targets=[s]) for i,s in enumerate(DESTINATIONS,1)])
        (self.folder/'photo-requests.json').write_text(json.dumps(self.plan))
        (self.folder/'goal.json').write_text('{"synthetic":true}')
        self.path=self.folder/'scene-photo-permit.json'
        self.permit=issue(self.path,self.folder,self.folder/'photo-requests.json',self.identity,
            time.monotonic_ns()+89_000_000_000,self.folder/'goal.json')
        (self.folder/'patrol.json.control.json').write_text(json.dumps(dict(version=1,runId='c'*32,command='run')))
        self.head=SimpleNamespace(checkpoint_id=CHECKPOINT,data=dict(format=SCENE_FORMAT))
        self.args=SimpleNamespace(output=str(self.folder/'patrol.json'),photo_directory=str(self.folder/'station-photos'),
            warm_photo_plan=str(self.folder/'photo-requests.json'),model='open-p2p',resident=True,enable_input=True,
            hybrid_navigation=True,hybrid_route=STREET_PATROL_ROUTE,hybrid_legs=8,seconds=90,fps=20,decision_hz=10,
            max_observation_age_ms=150,action_hold_ms=100,rdp_session_id=3,patrol_series_binding=tuple(self.permit['binding']),
            control_file=None,goal_intent='ground-navigation',history=41,cuda_graph=True,p2p_fast_start=True,p2p_prewarm=True,
            observation_profile='p2p-native-hamming-192-v1',goal_embedding=str(self.folder/'goal.json'))

    def test_shadow_rejected_until_exact_single_use_admission(self):
        with self.assertRaisesRegex(ValueError,'shadow-only'):
            require_photo_metric(self.head)
        result=admit(self.path,self.head,self.args)
        self.assertEqual(result['recommendation'],'bounded-photo-trial-only')
        require_photo_metric(self.head,self.folder/'station-photos'/self.plan['requests'][0]['id'])
        with self.assertRaises(FileExistsError):
            admit(self.path,self.head,self.args)

    def test_another_goal_mode_or_relaxed_bound_is_rejected_before_claim(self):
        for key,value in [('warm_open_queue',True),('warm_endurance',True),('warm_batch_count',2),
                ('seconds',91),('hybrid_legs',9),('max_observation_age_ms',151),('action_hold_ms',101),
                ('rdp_session_id',4),('history',42),('goal_intent','stationary'),('control_file','other.json')]:
            with self.subTest(option=key):
                changed=copy.copy(self.args)
                setattr(changed,key,value)
                with self.assertRaises(ValueError):
                    admit(self.path,self.head,changed)
                self.assertFalse((self.folder/'scene-photo-claim.json').exists())

    def test_changed_request_bytes_or_instruction_are_rejected(self):
        for name in ('photo-requests.json','goal.json'):
            with self.subTest(file=name):
                path=self.folder/name
                raw=path.read_bytes()
                path.write_bytes(raw+b' ')
                with self.assertRaises(ValueError):
                    admit(self.path,self.head,self.args)
                path.write_bytes(raw)

    def test_copied_permit_does_not_authorize_another_directory(self):
        other=self.folder/'copied'
        other.mkdir()
        path=other/self.path.name
        path.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(ValueError,'Copied'):
            admit(path,self.head,self.args)

    def test_expired_permit_and_operator_stop_do_not_get_a_claim(self):
        with patch('scene_photo_trial.time.monotonic_ns',return_value=self.permit['binding'][4]+1):
            with self.assertRaisesRegex(ValueError,'expired'):
                admit(self.path,self.head,self.args)
        path=self.folder/'patrol.json.control.json'
        path.write_text(json.dumps(dict(version=1,runId='c'*32,command='stop')))
        with self.assertRaisesRegex(ValueError,'run command'):
            admit(self.path,self.head,self.args)
        self.assertFalse((self.folder/'scene-photo-claim.json').exists())

    def test_admitted_head_cannot_authenticate_foreign_photo_output(self):
        admit(self.path,self.head,self.args)
        with self.assertRaisesRegex(ValueError,'outside'):
            require_admission(self.head,self.folder/'station-photos'/'foreign-goal')

    def test_wrong_observer_never_gets_the_exception(self):
        self.head.checkpoint_id='d'*64
        with self.assertRaisesRegex(ValueError,'Wrong'):
            admit(self.path,self.head,self.args)

    def test_saved_claim_replays_after_deadline_without_issuing_another_permission(self):
        admit(self.path,self.head,self.args)
        (self.folder/'patrol.json').write_text(json.dumps(dict(runId='c'*32,windowsSessionId=3)))
        jobs=self.folder/'jobs'
        jobs.mkdir()
        worker=Path(__file__).with_name('stream_client.py')
        argv=['python.exe','-B',str(worker),'--model=open-p2p','--source','synthetic-source',
            '--checkpoint','synthetic-checkpoint','--history=41','--cuda-graph','--p2p-fast-start','--p2p-prewarm',
            '--goal-embedding',self.args.goal_embedding,'--goal-intent=ground-navigation','--hybrid-navigation',
            '--navigation-climb-recovery','--hybrid-route',STREET_PATROL_ROUTE,'--hybrid-legs=8','--fps=20',
            '--decision-hz=10','--max-observation-age-ms=150','--action-hold-ms=100','--enable-input','--resident',
            '--rdp-session-id=3','--observation-profile=p2p-native-hamming-192-v1','--seconds=90',
            '--output',self.args.output,'--warm-photo-plan',self.args.warm_photo_plan,
            '--record-dir',str(self.folder/'patrol-recording'),
            '--photo-directory',self.args.photo_directory,'--photo-qualification',str(self.path),
            '--landmark-shadow',str(self.folder/'head.json'),
            '--patrol-series-binding='+':'.join(map(str,self.permit['binding']))]
        (jobs/'one.job.json').write_text(json.dumps(dict(argv=argv)))
        raw=(self.folder/'scene-photo-claim.json').read_bytes()
        with patch('scene_photo_trial.time.monotonic_ns',return_value=self.permit['binding'][4]+1000):
            self.assertEqual(admit(self.path,self.head)['runId'],'c'*32)
        self.assertEqual(raw,(self.folder/'scene-photo-claim.json').read_bytes())
        argv[argv.index('--seconds=90')]='--seconds=91'
        (jobs/'one.job.json').write_text(json.dumps(dict(argv=argv)))
        with self.assertRaisesRegex(ValueError,'limits'):
            admit(self.path,self.head)


if __name__=='__main__':
    unittest.main()
