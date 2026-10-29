"""Exercise a warm supervisor using inert broker evidence and an isolated local stop file."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import run_rdp_patrol as patrol
import run_warm_photo_requests as warm


class WarmLauncherTests(unittest.TestCase):
    def setUp(self):
        """Create unique run-scoped plans and outputs without a real RDP or GPU call."""
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        self.flags = ['--request', 'west', '1', 'west-lamp', '--request', 'east', '2', 'stair-front',
                      '--photo-qualification', 'unused/qualified.json', '--landmark-shadow', 'unused/observer.json']
        self.run_id, self.native_id = 'a'*32, 'b'*32
        self.audit = Mock(return_value={'passed': True})
        module = types.SimpleNamespace(audit_photo_handoff=self.audit)
        for override in [patch.dict('sys.modules', {'audit_photo_handoff':module}),
                         patch.object(warm.socket, 'gethostname', return_value='SIREN')]:
            override.start()
            self.addCleanup(override.stop)

    def publish(self, args, folder, *, series):
        """Write the evidence expected from the real launcher's previous route audit."""
        self.assertIsInstance(series, warm.SeriesGuard)
        self.assertEqual(json.loads(args.warm_photo_plan.read_bytes()), args.plan)
        requests = args.plan['requests']
        self.audit.return_value.setdefault('handoffs', [
            dict(oldRequestId=old['id'], newRequestId=new['id'], dispatchGapMs=540)
            for old, new in zip(requests, requests[1:])])
        patrol.atomic_json(folder/'patrol.json.status.json', dict(version=1,runId=self.run_id))
        patrol.atomic_json(folder/'patrol.json.control.json', dict(version=1,runId=self.run_id,command='run'))
        state = dict(runId=self.run_id,verified=True,stopReason=None,stopRequested=False)
        end = 'hybridLegLimit'
        if args.stop_drill:
            patrol.atomic_json(folder/'station-photos'/'warm-status.json', dict(version=1, runId=self.run_id,
                activeOrdinal=2, activeRequestId=args.plan['requests'][1]['id'],
                activeFirstAppliedRequestId=self.native_id, activeFirstAppliedFrameId=17))
            self.assertEqual(series.stop_reason(), 'seriesOperatorStop')
            state['stopCommandPublished'] = patrol.stop_resident(folder,self.run_id,timing=state)
            state.update(verified=False,stopRequested=True,stopReason='seriesOperatorStop',
                         stopRequestedAtMonotonicNs=warm.time.monotonic_ns())
            end = 'userStop'
        patrol.atomic_json(folder/'broker.json', dict(success=True,returnCode=0,timedOut=False))
        patrol.atomic_json(folder/'launcher.json', state)
        patrol.atomic_json(folder/'audit.json', dict(passed=True))
        patrol.atomic_json(folder/'patrol.json', dict(runId=self.run_id,endReason=end))
        if args.stop_drill:
            raise RuntimeError('Patrol stopped')

    def test_distinct_goals_share_one_bounded_pinned_resident(self):
        args = warm.options(self.flags)
        self.assertEqual(args.circuits,3)
        with patch.object(patrol, 'run', side_effect=self.publish) as launch:
            self.assertEqual(warm.run(args,self.folder)['status'],'completed')
            launch.assert_called_once()
        self.assertEqual(self.audit.call_args.kwargs['requests'], args.plan)
        self.assertFalse(self.audit.call_args.kwargs['allow_incomplete'])
        command = patrol.patrol_argv(args, 3, self.folder)
        self.assertEqual(command.count('--resident'),1)
        self.assertIn('--warm-photo-plan='+str(args.warm_photo_plan),command)
        self.assertLessEqual(len(command)+1,65)  # The real supervisor appends the immutable series binding.
        self.assertNotIn('--photo-station',command)

    def test_invalid_goal_pairs_fail_before_dispatch(self):
        photo_flags = ['--landmark-shadow', 'observer.json', '--photo-qualification', 'gate.json']
        for requests in (
                ['--request', 'a', '1', 'west-lamp'],
                ['--request', 'a', '20', 'west-lamp', '--request', 'b', '13', 'stair-front'],
                ['--request', 'a', '1', 'west-lamp', '--request', 'a', '1', 'stair-front'],
                ['--request', 'a', '1', 'west-lamp', '--request', 'b', '1', 'west-lamp'],
                ['--request', 'a', '1', 'west-lamp', '--request', 'b', '1', 'unknown-station']):
            with self.subTest(requests=requests), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                warm.options(requests + photo_flags)

    def test_multiple_requests_verify_every_planned_boundary_in_one_lease(self):
        flags = self.flags + ['--request', 'junction', '1', 'sidewalk-junction',
                              '--request', 'return', '1', 'stair-front', 'west-lamp']
        args = warm.options(flags)
        with patch.object(patrol, 'run', side_effect=self.publish) as launch:
            result = warm.run(args, self.folder)
            launch.assert_called_once()
        self.assertEqual((args.circuits, result['status'], len(result['verifiedHandoffs'])), (5, 'completed', 3))
        self.assertEqual([r['dispatchGapMs'] for r in result['verifiedHandoffs']], [540]*3)
        self.assertEqual(result['plannedHandoffs'][1]['oldRequestId'], args.plan['requests'][1]['id'])
        for invalid in (flags + ['--stop-drill'], flags + ['--request', 'fifth', '1', 'west-lamp', 'sidewalk-junction']):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                warm.options(invalid)

    def test_missing_intermediate_boundary_cannot_claim_completion(self):
        args = warm.options(self.flags + ['--request', 'junction', '1', 'sidewalk-junction'])
        self.audit.return_value['handoffs'] = []
        with patch.object(patrol, 'run', side_effect=self.publish):
            result = warm.run(args, self.folder)
        self.assertEqual((result['status'],len(result['plannedHandoffs']),result['verifiedHandoffs']),
                         ('stopped',2,[]))

    def test_stop_drill_is_separate_and_proves_an_addressed_applied_second_request(self):
        args = warm.options(self.flags+['--stop-drill'])
        self.audit.return_value = {'passed':False,'stopVerified':True}
        with patch.object(patrol,'run',side_effect=self.publish):
            self.assertEqual(warm.run(args,self.folder)['status'],'stopVerified')
        proof = json.loads((self.folder/'operator-stop.json').read_bytes())
        self.assertEqual((proof['requestId'],proof['nativeRequestId'],proof['frameId']),
                         (args.plan['requests'][1]['id'],self.native_id,17))
        self.assertLessEqual(proof['observedAtMonotonicNs'], proof['stopFileCreatedAtMonotonicNs'])
        self.assertLessEqual(proof['stopFileCreatedAtMonotonicNs'],proof['addressedStopAtMonotonicNs'])
        bracket = json.loads((self.folder/'launcher.json').read_bytes())['addressedStopQpc']
        self.assertEqual(proof['addressedStopQpc'],bracket)
        self.assertGreater(bracket['frequencyHz'],0)
        self.assertGreaterEqual(bracket['afterTicks'],bracket['beforeTicks'])
        self.assertTrue(self.audit.call_args.kwargs['allow_incomplete'])

    def test_partial_or_changed_owner_cannot_be_credited_as_stop_drill(self):
        args = warm.options(self.flags+['--stop-drill'])
        self.audit.return_value = {'passed':True,'stopVerified':True}
        with patch.object(patrol,'run',side_effect=self.publish):
            self.assertEqual(warm.run(args,self.folder)['status'],'stopped')
        altered = json.loads((self.folder/'patrol.json').read_bytes())
        altered['runId']='d'*32
        patrol.atomic_json(self.folder/'patrol.json',altered)
        with self.assertRaisesRegex(RuntimeError,'resident identity'):
            warm.audit_result(args,self.folder,warm.WarmGuard(self.folder,args))

    def test_drill_cannot_claim_prior_operator_stop_or_pause(self):
        args = warm.options(self.flags+['--stop-drill'])
        guard = warm.WarmGuard(self.folder,args)
        patrol.atomic_json(self.folder/'patrol.json.status.json',dict(version=1,runId=self.run_id))
        patrol.atomic_json(self.folder/'station-photos'/'warm-status.json', dict(version=1,runId=self.run_id,
            activeOrdinal=2,activeRequestId=guard.second_id,activeFirstAppliedRequestId=self.native_id,
            activeFirstAppliedFrameId=8))
        for command in ('pause','stop'):
            patrol.atomic_json(self.folder/'patrol.json.control.json', dict(version=1,runId=self.run_id,command=command))
            self.assertIsNone(guard.stop_reason())
            self.assertIsNone(guard.stop_observation)
            self.assertFalse((self.folder/'STOP').exists())

    def test_preexisting_stop_foreign_host_and_early_thermal_abort_do_not_start_or_retry(self):
        args = warm.options(self.flags+['--stop-drill'])
        for cause in ('stop','host','thermal'):
            folder = self.folder/cause
            folder.mkdir()
            if cause == 'stop':
                (folder/'STOP').touch()
            with self.subTest(cause=cause), patch.object(warm.socket,'gethostname',return_value='LAPTOP' if cause=='host' else 'SIREN'), \
                    patch.object(patrol,'run',side_effect=RuntimeError('temperatureLimit')) as launch:
                result = warm.run(args,folder)
                self.assertEqual(result['status'],'stopped')
                self.assertEqual(launch.call_count,int(cause=='thermal'))
        self.audit.assert_not_called()


if __name__=='__main__':
    unittest.main()
