"""Reject silent endurance escalation and mismatched native job budgets without opening the game."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import time
import unittest

from destination_queue_limits import ENDURANCE, STANDARD, queue_limits
import run_destination_batches as batches
import run_rdp_patrol as patrol
import stream_client
from audit_hybrid_run import batch_edges
from destination_batch_sender import create_plan


class QueueLimitsTests(unittest.TestCase):
    """Exercise the actual launcher-to-worker command and the opt-in caps."""
    def flags(self, **overrides):
        """Provide a complete inert open-queue request with an explicit native gameplay target."""
        values = dict(batches=40, leg_limit=256, seconds=900, target_gameplay_seconds=600,
                      owner_from='prior.json', start_station='sidewalk-junction',
                      landmark_shadow='head.json', photo_qualification='qualified.json')
        values.update(overrides)
        return ['--open-queue', '--endurance', *[item for key,value in values.items()
                for item in ('--'+key.replace('_','-'), str(value))]]

    def refused(self, flags):
        """Require validation to stop before any owner discovery or live command."""
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            batches.launch_options(flags)

    def test_historical_profile_keeps_original_limits(self):
        self.assertEqual(queue_limits(), STANDARD)
        self.assertEqual((STANDARD.seconds,STANDARD.batches,STANDARD.legs,STANDARD.recording_mib),(600,12,96,160))
        self.assertEqual((ENDURANCE.seconds,ENDURANCE.batches,ENDURANCE.legs,ENDURANCE.recording_mib),(900,40,256,384))
        for value in (True, 'unbounded', 'ENDURANCE-V1'):
            with self.subTest(profile=value), self.assertRaises(ValueError):
                queue_limits(value)

    def test_endurance_must_be_explicit_and_automatic(self):
        self.refused([x for x in self.flags() if x!='--endurance'])
        self.refused(self.flags()+['--manual'])
        self.refused([x for x in self.flags() if x!='--open-queue'])
        self.assertTrue(batches.launch_options(self.flags()).endurance)

    def test_endurance_caps_remain_finite(self):
        for update in (dict(seconds=901),dict(batches=41),dict(leg_limit=257),dict(target_gameplay_seconds=900)):
            with self.subTest(update=update):
                self.refused(self.flags(**update))

    def test_independent_route_expansion_requires_the_declared_larger_bound(self):
        plans=[create_plan('sidewalk-junction',[(f'out-{i}','west-lamp'),(f'back-{i}','sidewalk-junction')]) for i in range(40)]
        with self.assertRaisesRegex(ValueError,'batch budget'):
            batch_edges(plans)
        self.assertEqual(len(batch_edges(plans,max_batches=40)),80)
        with self.assertRaisesRegex(ValueError,'batch budget'):
            batch_edges(plans+[plans[0]],max_batches=40)

    def test_worker_receives_the_explicit_profile_and_unchanged_input_guards(self):
        args=batches.launch_options(self.flags())
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            args.warm_photo_plan=folder/'photo-requests.json'
            command=patrol.patrol_argv(args,3,folder)
            command.append('--patrol-series-binding=1:'+'a'*32+':2:'+'b'*32+':'+str(time.monotonic_ns()+10**12))
            start=next(i for i,value in enumerate(command) if value.endswith('stream_client.py'))+1
            worker=stream_client.parse_arguments(command[start:])
            self.assertTrue(worker.warm_endurance)
            self.assertEqual((worker.seconds,worker.warm_batch_count,worker.hybrid_legs),(900,40,256))
            self.assertEqual(worker.record_max_mib,384)
            self.assertEqual((worker.max_observation_age_ms,worker.action_hold_ms,worker.decision_hz),(150,100,10))
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                stream_client.parse_arguments([x for x in command[start:] if x!='--warm-endurance'])


if __name__=='__main__':
    unittest.main()
