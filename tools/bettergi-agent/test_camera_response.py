"""Causal camera calibration must generalize on an independent lease before live use."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from camera_response import CameraCalibration, fit_response, read_probe


def probe(sequence):
    """Create two independent, time-separated synthetic sequences with yaw wrapping at north."""
    stamp = 1000 if sequence == 'train' else 100000
    counts = ([30,-30,75,-75,125,-125,220,-220]*2 if sequence == 'train' else [45,-45,95,-95,170,-170])
    actions, receipts, frames, yaw = [], [], [], 354.
    for i, dx in enumerate(counts):
        key = f'{sequence}-{i}'
        pres, posts = [], []
        for lag in (-550,-350,-80,-35,30,90,170,260,400,530,595,660,730):
            k = len(frames)+1
            src = dict(captureEpoch='display', timestamp100ns=(stamp+lag)*10000, freshnessAtMs=stamp+lag)
            gate = dict(ready=True, epoch=1, sourceFrameId=k, sourceFrame=src)
            angle = (yaw+dx*.125*min(1,max(0,(lag-60)/120))) % 360
            f = dict(frameId=k, sourceAtMs=stamp+lag, sourceFrame=src, frameWorldReadiness=gate, frameQuality='usable',
                worldReadiness=gate, inputAvailable=True, motionEvidence=dict(status='normal',spaceKeyMatched=False),
                navigationPose=dict(frameId=k, state='valid', layerId='City_102', yawDegrees=angle,
                                    positionConfidence=1, yawConfidence=.7, x=0.,y=0.))
            frames.append(f)
            (pres if lag<0 else posts).append(k)
        step = dict(keys=[],mouseDx=dx,mouseDy=0,durationMs=100)
        accepted = dict(type='accepted',requestId=key,acceptedAtMs=stamp-1)
        a = dict(frameId=pres[-1], requestId=key, modelId='camera-response-probe-v1',mouseDx=dx,step=step,
                 accepted=accepted,preFrameIds=pres,postFrameIds=posts,settledFrameIds=posts[-3:])
        actions.append(a)
        receipts.append(dict(status='completed', requestId=key, modelId=a['modelId'],frameId=a['frameId'],
            acceptedAtMs=stamp-1,endedAtMs=stamp+100,appliedSteps=[dict(step,startedAtMs=stamp)]))
        yaw = (yaw+dx*.125)%360
        stamp+=1800
    return dict(kind='bettergi-camera-response',version=1, sequence=sequence,status='completed',
                hello=dict(sessionId=sequence+'session',ownerEpoch=sequence+'owner'),captureEpoch='display',worldEpoch=1,
                observations=frames,actions=actions,receipts=receipts,stop=dict(type='stopped'))


class CameraResponseTests(unittest.TestCase):
    def test_distinct_heldout_gain_and_bounded_directional_control(self):
        with tempfile.TemporaryDirectory() as folder:
            def get(seq):
                p = Path(folder)/(seq+'.json')
                p.write_text(json.dumps(probe(seq)), encoding='utf-8')
                return read_probe(p, seq)
            train, holdout = get('train'), get('holdout')
            result = fit_response(train,holdout)
            self.assertTrue(result['trialEligible'])
            self.assertAlmostEqual(result['degreesPerCount'],.125)
            self.assertLess(result['heldOut']['maeDegrees'], .001)
            path = Path(folder)/'fit.json'
            path.write_text(json.dumps(result),encoding='utf-8')
            fit = CameraCalibration.load(path)
            self.assertIsNone(fit.suggest(3,ms_since_last_mouse=900))
            self.assertIsNone(fit.suggest(20,ms_since_last_mouse=20))
            self.assertEqual(fit.suggest(-20,ms_since_last_mouse=float('inf')),-160)
            self.assertEqual(fit.suggest(175,ms_since_last_mouse=999),220)
            self.assertIsNone(fit.suggest(20,ms_since_last_mouse=float('nan')))
            self.assertEqual(len(fit.checkpoint_id),64)
            with self.assertRaises(ValueError):
                fit_response(train,dict(holdout,sessionId=train['sessionId']))
            wrong = copy.deepcopy(holdout)
            for row in wrong['rows']:
                row['deltaYaw'] = .1*row['mouseDx']
            self.assertFalse(fit_response(train,wrong)['trialEligible'])
            result['degreesPerCount'] = .5
            path.write_text(json.dumps(result),encoding='utf-8')
            with self.assertRaises(ValueError):
                CameraCalibration.load(path)

    def test_reject_contaminated_or_misjoined_camera_trial(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'wrong.json'
            for corrupt in ('keys','frame','body','unordered','receipt'):
                a = probe('holdout')
                if corrupt == 'keys':
                    a['receipts'][0]['appliedSteps'][0]['keys'] = ['W']
                if corrupt == 'frame':
                    a['observations'][0]['navigationPose']['frameId'] += 1
                if corrupt == 'body':
                    a['observations'][2]['navigationPose']['x'] += 3
                if corrupt == 'unordered':
                    a['actions'][0]['preFrameIds'].reverse()
                if corrupt == 'receipt':
                    a['receipts'][0]['requestId'] = 'foreign'
                p.write_text(json.dumps(a),encoding='utf-8')
                with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                    read_probe(p,'holdout')


if __name__ == '__main__':
    unittest.main()
