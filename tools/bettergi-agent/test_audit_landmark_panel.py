"""Source-domain and episode-level accounting for paired station replays."""
import unittest

from audit_landmark_panel import exclude_development, screen_reference, summarize


class LandmarkPanelTests(unittest.TestCase):
    """A correlated set of views is still a single lease, and original PNG coverage is explicit."""

    def test_original_pixel_regression_and_correlated_decoded_gains(self):
        rows=[]
        for frame in (1,2):
            rows.append(dict(runId='first',segment=1,frameId=frame,station='stair-front',
                             decoded=['sidewalk-junction','stair-front']))
        rows.append(dict(runId='second',segment=1,frameId=3,station='stair-front',
                         decoded=['stair-front','sidewalk-junction'],exact=['stair-front','sidewalk-junction']))
        rows.append(dict(runId='second',segment=1,frameId=4,station='west-lamp',
                         decoded=['west-lamp','west-lamp'],exact=['west-lamp','west-lamp']))
        compressed=summarize(rows,'decoded')
        exact=summarize(rows,'exact')
        self.assertEqual(compressed['correct'],[2,3])
        self.assertEqual(compressed['completelyCorrectLeases'],[1,1])
        self.assertEqual(exact['correct'],[2,1])
        self.assertEqual(exact['completelyCorrectLeases'],[1,0])
        self.assertEqual(exact['perClass']['sidewalk-junction'][1]['falsePositive'],1)
        self.assertEqual(exact['perClass']['stair-front'][1]['falseNegative'],1)
        self.assertEqual(exact['pairedChanges'][0]['frameId'],3)

    def test_newly_exposed_goal_excludes_whole_lease_by_id_or_folder(self):
        corpus=dict(leases=[dict(runId=k,path=f'archive/folder-{k}/patrol.json') for k in ('a','b','c')],
                    excluded=[dict(runId='d',reason='training')])
        freeze=dict(excludedWholeLeases=['a','folder-b'],developmentOriginals={'a/1':'pixel-a','b/1':'pixel-b'},
                    checkpointSha256='candidate')
        result=exclude_development(corpus,freeze,'parent')
        self.assertEqual([v['runId'] for v in result['leases']],['c'])
        self.assertEqual([v['runId'] for v in result['excluded']],['d','a','b'])
        self.assertEqual(result['excludedDevelopmentRgbSha256'],['pixel-a','pixel-b'])
        self.assertEqual(len(corpus['leases']),3)

    def test_decoded_mean_gain_cannot_override_new_error_in_clean_episode(self):
        rows=[dict(runId=r,frameId=f,station='stair-front',decoded=pred) for r,f,pred in
              [('a',1,['sidewalk-junction','stair-front']),('a',2,['sidewalk-junction','stair-front']),
               ('b',3,['stair-front','sidewalk-junction'])]]
        old=dict(rows=rows,rejectedBeforeScoring=[])
        plan=dict(eligibleWholeRunIds=['a','b'],rejectedBeforeScoring=[])
        result=screen_reference(rows,old,plan,[],[dict(runId='a'),dict(runId='b')])
        self.assertTrue(result['withholdAdditionalLiveTest'])
        self.assertEqual(len(result['decoded']['correctedErrors']),2)
        self.assertEqual([r['frameId'] for r in result['decoded']['newErrorsInFormerlyPerfectLeases']],[3])


if __name__=='__main__':
    unittest.main()
