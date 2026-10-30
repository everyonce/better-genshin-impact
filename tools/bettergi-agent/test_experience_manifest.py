"""Prevent fabricated actor, image or terminal evidence when indexing original game experience."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from experience_manifest import action_record,photo_inputs,verify_video


class OriginalObserverTests(unittest.TestCase):
    """An experimental recording must retain its actual permission rather than inheriting the default observer."""
    def setUp(self):
        """Create inert saved-command artifacts, without loading either observer or using a broker."""
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo=Path(temp.name).resolve()
        self.folder=self.repo/'artifacts/live/episode'
        (self.folder/'jobs').mkdir(parents=True)
        self.checkpoint=self.repo/'artifacts/scene.json'
        self.qualification=self.folder/'scene-endurance-permit.json'
        self.checkpoint.write_text('{}')
        self.qualification.write_text('{}')
        self.job=self.folder/'jobs/original.job.json'
        self.argv=['python.exe',str(self.repo/'tools/bettergi-agent/stream_client.py'),
            '--output',str(self.folder/'patrol.json'),'--photo-directory='+str(self.folder/'station-photos'),
            '--landmark-shadow='+str(self.checkpoint),'--photo-qualification',str(self.qualification)]
        self.save()

    def save(self):
        """Persist only the synthetic command used by this case."""
        self.job.write_text(json.dumps(dict(argv=self.argv)))

    def test_selects_the_actual_experimental_checkpoint_and_permission(self):
        self.assertEqual(photo_inputs(self.folder,self.repo),(self.checkpoint,self.qualification))

    def test_missing_duplicate_and_redirected_arguments_are_rejected(self):
        original=list(self.argv)
        for changed in [original[:-2],original+['--landmark-shadow',str(self.checkpoint)],
                        [value.replace('patrol.json','different.json') for value in original]]:
            with self.subTest(argv=changed):
                self.argv=changed
                self.save()
                with self.assertRaises(ValueError):photo_inputs(self.folder,self.repo)

    def test_external_or_missing_observer_files_are_not_read(self):
        outside=self.repo/'unrelated.json'
        outside.write_text('{}')
        self.argv[-1]=str(outside)
        self.save()
        with self.assertRaisesRegex(ValueError,'retained local artifacts'):photo_inputs(self.folder,self.repo)
        self.argv[-1]=str(self.qualification)
        self.save()
        self.checkpoint.unlink()
        with self.assertRaisesRegex(ValueError,'retained local artifacts'):photo_inputs(self.folder,self.repo)


class ActionProvenanceTests(unittest.TestCase):
    """Each labeled action needs its actual admission, controller, source and terminal receipt."""
    def setUp(self):
        self.source=dict(captureEpoch='capture',sourceId=1,freshnessAtMs=100.0)
        self.proposal=dict(frameId=7,observationTimestampMs=100.0,warmRequestId='goal',
            acceptance=dict(type='accepted',requestId='request',acceptedAtMs=110.0),
            hybridNavigation=dict(owner='hybrid-native'),steps=[dict(keys=['W'])],rawPolicySteps=[dict(keys=[])])
        self.receipt=dict(requestId='request',frameId=7,modelId='hybrid-native',acceptedAtMs=110.0,
            endedAtMs=210.0,status='completed',appliedSteps=[dict(keys=['W'],startedAtMs=111.0)])
        self.observation=dict(frame=dict(frameId=7,sourceFrame=self.source,sourceTimestampKind='native',observationProfile='rgb192'),
            reference=dict(path='observations.jsonl',line=8))
        self.video=dict(frameId=7,sourceFrame=self.source,path='frames.mp4',videoFrameIndex=6)

    def record(self,**kwargs):
        return action_record(self.proposal,self.receipt,self.observation,self.video,**kwargs)

    def test_native_override_never_becomes_a_policy_or_expert_demonstration(self):
        row=self.record()
        self.assertEqual(row['actor'],'native-controller')
        self.assertFalse(row['humanExpertDemonstration'])
        self.assertFalse(row['physicalExecutionProven'])
        self.assertNotEqual(row['rawPolicyPrediction'],row['proposedSteps'])
        self.assertEqual(row['appliedSteps'],self.receipt['appliedSteps'])

    def test_receipt_model_cannot_override_the_actual_controller(self):
        self.receipt['modelId']='open-p2p'
        with self.assertRaisesRegex(ValueError,'controller'):
            self.record()

    def test_missing_image_stays_missing(self):
        row=action_record(self.proposal,self.receipt,self.observation,None)
        self.assertTrue(row['hasAppliedInput'])
        self.assertFalse(row['hasOriginalEncodedImage'])
        self.assertIsNone(row['encodedObservation'])

    def test_different_image_frame_or_native_source_is_rejected(self):
        for update in ({'frameId':8},{'sourceFrame':dict(self.source,sourceId=2)}):
            with self.subTest(update=update),self.assertRaisesRegex(ValueError,'Encoded image'):
                action_record(self.proposal,self.receipt,self.observation,dict(self.video,**update))

    def test_receipt_and_source_clock_must_be_exact(self):
        for change in ({'requestId':'other'},{'frameId':8},{'acceptedAtMs':111.0}):
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'matching original'):
                action_record(self.proposal,dict(self.receipt,**change),self.observation,self.video)
        self.proposal['observationTimestampMs']=101.0
        with self.assertRaisesRegex(ValueError,'source clock'):
            self.record()

    def test_recovery_uses_its_real_native_identity(self):
        self.proposal['arguments']=dict(modelId='navigation-climb-drop-v1',observationTimestampMs=100.0,steps=[dict(keys=['X'])])
        self.receipt['modelId']='navigation-climb-drop-v1'
        row=self.record(recovery=True)
        self.assertEqual(row['actor'],'recovery-controller')
        self.assertEqual(row['controllerId'],'navigation-climb-drop-v1')
        self.proposal['arguments']['modelId']='open-p2p'
        self.receipt['modelId']='open-p2p'
        with self.assertRaisesRegex(ValueError,'controller'):
            self.record(recovery=True)

    def test_empty_terminal_steps_are_not_counted_as_applied(self):
        self.receipt['status']='expired'
        self.receipt['appliedSteps']=[]
        self.assertFalse(self.record()['hasAppliedInput'])


class OriginalVideoCoverageTests(unittest.TestCase):
    """An encoded index cannot stand in for frames missing from the actual video file."""
    def test_real_decoder_requires_exact_frame_count_and_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'two-frames.mp4'
            subprocess.run(['C:/Programs/ffmpeg.exe','-nostdin','-v','error','-f','rawvideo','-pixel_format','rgb24',
                '-video_size','192x192','-framerate','12','-i','pipe:0','-c:v','libx264','-threads','1',str(path)],
                input=b''.join(bytes([value])*(192*192*3) for value in (40,180)),capture_output=True,check=True,timeout=30)
            index=[dict(width=192,height=192,videoPtsSeconds=i/12) for i in range(2)]
            self.assertEqual(verify_video(path,index)['decodedFrames'],2)
            with self.assertRaisesRegex(ValueError,'truncated'):
                verify_video(path,index+[index[0]])
            with self.assertRaisesRegex(ValueError,'coverage'):
                verify_video(path,[dict(row,width=64,height=64) for row in index])
            with self.assertRaisesRegex(ValueError,'timestamps'):
                verify_video(path,[dict(row,videoPtsSeconds=2) for row in index])
