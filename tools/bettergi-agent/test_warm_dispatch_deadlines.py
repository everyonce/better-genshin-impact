"""Replay both deadline constraints from independent original dispatches, not the runtime's claimed bound."""
import copy
import math
import unittest

from audit_photo_handoff import verify_action_start_deadlines


class WarmDispatchDeadlineTests(unittest.TestCase):
    """A short first window is admissible; equality, source extensions and cleared-noop bounds are not."""
    def evidence(self, *, first_applied=True):
        """Model a prior dispatch at 100 ms and an endpoint released before a 978 ms successor source."""
        events=[dict(type='warmBatchAccepted',frameId=9,nextRequestId='new',release=dict(serverNowMs=300))]
        frames={fid:dict(sourceTimestampKind='wgc_reported_compositor_qpc',sourceFrame=dict(capturedAtMs=at,
                        acquiredAtMs=at,freshnessAtMs=at,freshnessClockKind='reported_compositor_qpc'))
                for fid,at in ((10,978),(11,1080))}
        limit=math.nextafter(1100,-math.inf)
        decisions=[dict(frameId=10,warmRequestId='new',startBeforeMs=limit,acceptance=dict(type='accepted',requestId='first')),
                   dict(frameId=11,warmRequestId='new',startBeforeMs=1230 if first_applied else limit,
                        acceptance=dict(type='accepted',requestId='next'))]
        receipts=dict(old=dict(frameId=2,appliedSteps=[dict(startedAtMs=100)]),
                      first=dict(frameId=10,appliedSteps=[dict(startedAtMs=1040)] if first_applied else []),
                      next=dict(frameId=11,appliedSteps=[dict(startedAtMs=1090)]))
        return events,decisions,receipts,frames

    def test_short_window_then_full_source_window_after_actual_dispatch(self):
        verify_action_start_deadlines(*self.evidence())

    def test_unapplied_acceptance_does_not_clear_the_handoff(self):
        evidence=self.evidence(first_applied=False)
        verify_action_start_deadlines(*evidence)
        evidence[1][1]['startBeforeMs']=1230
        with self.assertRaisesRegex(ValueError,'deadline'):
            verify_action_start_deadlines(*evidence)

    def test_actual_recovery_input_also_settles_the_first_dispatch(self):
        events,decisions,receipts,frames=self.evidence()
        frames[10]['sourceFrame'].update(capturedAtMs=900,acquiredAtMs=900,freshnessAtMs=900)
        receipts['first']['appliedSteps'][0]['startedAtMs']=1000
        recovery=dict(decisions[0],arguments=dict(startBeforeMs=1050))
        del recovery['startBeforeMs']
        verify_action_start_deadlines(events,decisions[1:],receipts,frames,[recovery])

    def test_wrong_declared_bound_or_actual_late_dispatch_is_rejected(self):
        for mutation in ('fullSource','equalBoundary','earlierUnbound','lateDispatch','missingPrior'):
            evidence=copy.deepcopy(self.evidence())
            if mutation=='fullSource': evidence[1][0]['startBeforeMs']=1128
            elif mutation=='equalBoundary': evidence[1][0]['startBeforeMs']=1100
            elif mutation=='earlierUnbound': evidence[1][0]['startBeforeMs']=1090
            elif mutation=='lateDispatch': evidence[2]['first']['appliedSteps'][0]['startedAtMs']=1100
            else: evidence[2]['old']['appliedSteps']=[]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                verify_action_start_deadlines(*evidence)


if __name__=='__main__':
    unittest.main()
