"""CPU-only lifecycle tests for immutable, single-use reviewed combat launch plans."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import combat_trial as trial
from combat_trial_guard import canonical
from episode_split import read_split
from test_combat_trial_guard import OWNER, review_parts, proposal


class FakeLifecycle:
    """Model only ownership and a single listener; every actual platform operation is absent."""
    def __init__(self):
        """Begin with the exact fixture owner idle and minimized."""
        self.root = dict(OWNER['root'], instanceType='Primary', uiStatus='current', childWindowMinimized=True)
        self.child = dict(OWNER['child'], instanceType='ChildSession', runtimeRunning=True,
            automationState='game_ready', taskRunning=False, agentStreamRunning=False,
            pilotState='idle', serviceOwnsPilot=False, agentPipeName='inert-pipe')
        self.starts = 0
        self.launches = 0
        self.start_error = None
        self.command = None
        self.runner = None

    def discover(self):
        """Return independent inert endpoint snapshots."""
        return dict(unavailable=[], instances=copy.deepcopy([self.root, self.child]))

    def require_role(self, value, role):
        """Reject role substitution without a native call."""
        if value['instanceType'] != role:
            raise RuntimeError('role changed')

    def _require_connected_root(self, root, child):
        """Keep both fixture identities joined."""
        if root['processId'] != OWNER['root']['processId'] or child['processId'] != OWNER['child']['processId']:
            raise RuntimeError('owner changed')

    def start_agent(self, child, timeout, **kwargs):
        """Record exactly one input-lease attempt without opening a pipe."""
        self.starts += 1
        if self.start_error:
            raise self.start_error
        self.child.update(taskRunning=True, agentStreamRunning=True)
        return copy.deepcopy(self.child)

    def stop_agent(self, *args, **kwargs):
        """A broad child-level stop is forbidden even during error cleanup."""
        raise AssertionError('Unexpected child-level stop')

    def run_command(self, root, command, workdir, python, timeout, jobs, limit):
        """Invoke an injected inert worker once and retain its ordinary-broker envelope."""
        self.launches += 1
        self.command = command
        code = self.runner()
        return dict(windowsSessionId=3, remoteDesktop=True, elevated=False, integrityRid=8192,
            timedOut=False, outputIncomplete=False, success=code == 0, returnCode=code,
            runnerProcessId=os.getppid(), stdout='', stderr='', timeoutSeconds=timeout)


class FakeWatch:
    """Exercise stop/deadline delivery without NVIDIA queries, threads or owner RPCs."""
    def __init__(self, folder, plan, claim, lifecycle, control=None):
        """Keep only the exact trial's marker and deadline."""
        self.folder, self.plan, self.claim = Path(folder), plan, claim
        self.closed = False

    def start(self):
        """Validate admission synchronously."""
        self.check()

    def check(self):
        """A stop or expired shared host deadline cannot be cleared."""
        if (Path(self.plan['directory']) / 'STOP').exists():
            raise RuntimeError('seriesOperatorStop')
        if time.monotonic_ns() >= self.claim['deadlineMonotonicNs']:
            raise RuntimeError('seriesTimeLimit')

    def close(self):
        """Record monitor retirement."""
        self.closed = True


class CombatTrialTests(unittest.TestCase):
    def setUp(self):
        """Build a tiny isolated repository and source-bound native review, with no model files."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.live = self.root / 'artifacts/live'
        self.agent = self.root / 'artifacts/agent'
        self.live.mkdir(parents=True)
        self.goal = self.agent / 'goals/combat-isolated-enemy-v1.json'
        self.checkpoint = self.agent / 'models/checkpoint.ckpt'
        self.model_source = self.agent / 'sources/open-p2p'
        self.gpu = self.agent / 'envs/gamescaling/Scripts/python.exe'
        self.code = self.root / 'tools/bettergi-agent/combat_trial.py'
        for path in (self.goal, self.checkpoint, self.gpu, self.code, self.model_source / 'model.py',
                     self.root / 'tools/rdp-automation/rdp_control.py', self.root / 'runner.exe',
                     self.root / 'ffmpeg.exe', self.root / 'nvidia-smi.exe'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'inert fixture')
        parts = review_parts()
        captured = time.perf_counter_ns() // 100 - 100_000

        def update_source(value):
            """Make all repeated native-source joins current without changing their relative clocks."""
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == 'timestamp100ns':
                        value[key] = captured
                    else:
                        update_source(item)
            elif isinstance(value, list):
                for item in value:
                    update_source(item)

        update_source(parts)
        parts[0]['reviewedAtUnixNs'] = time.time_ns()
        self.goal.write_bytes(parts[-1])
        self.evidence = {}
        for name, value in zip(trial.EVIDENCE_NAMES[:-1], parts[:-1]):
            path = self.live / (name + ('.png' if name == 'image' else '.json'))
            path.write_bytes(value if isinstance(value, bytes) else canonical(value))
            self.evidence[name] = path
        self.owner_file = self.live / 'map-owner-lineage.json'
        self.owner_file.write_bytes(canonical(OWNER))
        self.resources = dict(gpuPython=str(self.gpu), runnerPython=str(self.root / 'runner.exe'),
            ffmpeg=str(self.root / 'ffmpeg.exe'), nvidiaSmi=str(self.root / 'nvidia-smi.exe'),
            checkpoint=str(self.checkpoint), modelSource=str(self.model_source), goal=str(self.goal))
        for target, values in ((trial, dict(ROOT=self.root, LIVE=self.live, AGENT=self.agent, GOAL=self.goal,
                GOAL_SHA256=trial.digest(parts[-1]), CHECKPOINT=self.checkpoint, MODEL_SOURCE=self.model_source, GPU_PYTHON=self.gpu)),
                (trial.runtime, dict(OPEN_P2P_SHA256=trial.digest(self.checkpoint.read_bytes())))):
            active = patch.multiple(target, **values)
            active.start()
            self.addCleanup(active.stop)
        for name, value in (('load_map_owner', lambda path: copy.deepcopy(OWNER)),
                            ('installed_resources', lambda: copy.deepcopy(self.resources))):
            active = patch.object(trial, name, value)
            active.start()
            self.addCleanup(active.stop)
        self.folder = self.live / 'trial'
        self.lifecycle = FakeLifecycle()
        self.loads = self.episodes = 0
        self.load_action = self.episode_action = None
        self.last_args = self.last_policy = None

    def prepare(self):
        """Prepare one immutable fixture plan through the real review/source admission path."""
        self.plan = trial.prepare(self.folder, self.owner_file, self.evidence)
        self.plan_path = self.folder / 'plan.json'
        return self.plan

    def claim(self):
        """Create the same finite host consumption evidence without launching a process."""
        plan, sha = trial.load_plan(self.plan_path)
        now = time.monotonic_ns()
        trial.exclusive_json(self.folder / 'CONSUMED.json', dict(runId=plan['runId'], planSha256=sha,
            startedMonotonicNs=now, deadlineMonotonicNs=now + trial.HOST_SECONDS * 1_000_000_000))

    def identity(self, session):
        """Return ordinary-token fixture metadata, never the machine's native session."""
        return dict(processId=os.getpid(), parentProcessId=os.getppid(), windowsSessionId=session,
                    remoteDesktop=True, elevated=False, integrityRid=8192)

    def loader(self, args):
        """Return metadata for a prepared synthetic policy without importing Torch or CUDA."""
        self.loads += 1
        self.last_args = args
        policy = SimpleNamespace(execution_feedback=True, _pending_feedback=False,
            metadata=dict(precision='float16', historyFrames=41, cudaGraph=True, graphCaptureValidated=True,
                historyCommit='accepted-proposals-only', goal=dict(file=str(self.goal)),
                startupGraphPreparation=dict(graphPrepared=True, controllerActionsEmitted=0, historyFramesAfterPreparation=0)))
        self.last_policy = policy
        if self.load_action:
            self.load_action(policy)
        return policy

    def episode(self, args, policy, control):
        """Publish a synthetic drained episode; detailed native replay is covered by stream/guard tests."""
        self.episodes += 1
        self.assertTrue(control.frozen_goal)
        self.assertEqual(policy.combat_trial_goal_sha256, self.plan['binding']['goalSha256'])
        self.assertEqual((args.history, args.fps, args.decision_hz, args.seconds, args.action_hold_ms), (41, 20, 10, 5, 100))
        self.assertFalse(args.resident)
        self.assertIsNone(getattr(args, 'lease_output', None))
        self.assertEqual(args.execution_context, 'off')
        self.assertFalse(any(getattr(args, key, None) for key in ('navigation_progress', 'hybrid_navigation',
            'navigation_guidance', 'navigation_climb_recovery', 'navigation_idle_reset_seconds', 'combat_shadow')))
        self.assertLessEqual(args.lease_deadline - time.monotonic(), 5)
        pulses = [{key: {'fixture': True} for key in ('arguments', 'frame', 'admission', 'receipt', 'release', 'postFrame')}
                  for _ in range(3)]
        native = dict(status='completed', endReason='combatTrialComplete', combatTrialGuard=copy.deepcopy(self.plan['binding']),
            combatTrialGuardState=dict(phase='complete', trialComplete=True, trip=None, acceptedActions=3,
                completedActions=3, completed=pulses, pending=None, armed=False), acceptedInputActions=3,
            decisions=[proposal(), proposal(), proposal()], framesReceived=5,
            recording=dict(error=None, closed=True, complete=True, lossless=True, workerRetired=True,
                droppedFrames=0, droppedEvents=0, droppedObservations=0, abandonedFrames=0,
                encodedFrames=5, recordedObservations=5, policyRgbEnabled=True,
                policyRgbFrames=5, policyRgbBytes=5 * trial.RGB192_BYTES),
            stop=dict(type='stopped', heldKeys=[], active=None))
        self.lifecycle.child.update(taskRunning=False, agentStreamRunning=False)
        Path(args.record_dir).mkdir()
        # Two admission sources plus three later post-action sources are retained
        # as inert RGB payloads; no decoder or GPU participates in this fixture.
        for index in range(5):
            (Path(args.record_dir) / f'retained-{index}.rgb').write_bytes(bytes(trial.RGB192_BYTES))
        if self.episode_action:
            self.episode_action(native)
        Path(args.output).write_bytes(canonical(native))
        return 0 if native['status'] == 'completed' else 1

    def worker(self, **kwargs):
        """Run the real wrapper with inert dependencies only."""
        return trial.run_worker(self.plan_path, lifecycle=self.lifecycle, loader=self.loader,
            episode=self.episode, identity_reader=kwargs.pop('identity_reader', self.identity), watch_factory=FakeWatch, **kwargs)

    def report(self):
        """Read the final immutable wrapper."""
        return json.loads((self.folder / 'patrol.json').read_bytes())

    def test_success_loads_and_starts_once_and_reserves_terminal_diagnostic(self):
        """One prewarm, lease and episode retain source identity, accounting and split."""
        self.prepare()
        self.claim()
        self.assertEqual(self.worker(), 0)
        report = self.report()
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 1, 1))
        self.assertEqual(report['status'], 'completed')
        self.assertTrue(report['cleanupVerified'])
        self.assertTrue(report['recordedBytesComplete'])
        self.assertEqual(report['recordedBytes'], 5 * trial.RGB192_BYTES)
        self.assertEqual(read_split(self.folder, self.plan['runId'])['split'], 'diagnostic')
        self.assertFalse(report['combatSuccess'])
        with self.assertRaises(FileExistsError):
            self.worker()
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 1))

    def test_host_launch_binds_worker_parent_and_cannot_replay_plan(self):
        """The host submits one ordinary command and requires its exact terminal identity."""
        self.prepare()
        self.lifecycle.runner = self.worker
        self.assertEqual(trial.launch(self.plan_path, lifecycle=self.lifecycle, watch_factory=FakeWatch), 0)
        result = json.loads((self.folder / 'result.json').read_bytes())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['worker']['parentProcessId'], result['broker']['runnerProcessId'])
        self.assertEqual(result['broker']['timeoutSeconds'], 90)
        self.assertEqual(self.lifecycle.launches, 1)
        with self.assertRaises(FileExistsError):
            trial.launch(self.plan_path, lifecycle=self.lifecycle, watch_factory=FakeWatch)
        self.assertEqual(self.lifecycle.launches, 1)

    def test_stale_review_is_refused_before_plan_creation(self):
        """A recent file modification cannot refresh an old visual review."""
        review = json.loads(self.evidence['review'].read_bytes())
        review['reviewedAtUnixNs'] -= 121_000_000_000
        self.evidence['review'].write_bytes(canonical(review))
        with self.assertRaisesRegex(ValueError, 'review is stale'):
            self.prepare()
        self.assertFalse(self.folder.exists())

    def test_stale_native_capture_is_refused_with_a_fresh_review(self):
        """Review time cannot substitute for the original compositor timestamp."""
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'Native reviewed scene is stale'):
            trial.recent_review(self.plan['binding'], json.loads(self.evidence['review'].read_bytes()), 120,
                qpc_ns=time.perf_counter_ns() + 121_000_000_000)

    def test_review_age_cannot_exceed_fixed_maximum(self):
        """A prepared plan cannot widen the freshness contract."""
        with self.assertRaisesRegex(ValueError, 'review age bound'):
            trial.prepare(self.folder, self.owner_file, self.evidence, maximum_review_age=121)

    def test_zero_native_candidates_do_not_qualify_for_combat(self):
        """The current distant camp type of view cannot become attack authority."""
        scene = json.loads(self.evidence['scene'].read_bytes())
        scene['observations'][0]['combatEvidence']['enemyBarCandidates'] = []
        self.evidence['scene'].write_bytes(canonical(scene))
        with self.assertRaisesRegex(ValueError, 'native target evidence'):
            self.prepare()

    def test_each_original_or_retained_input_substitution_blocks_loading(self):
        """All six original byte bindings are checked again inside the worker."""
        self.prepare()
        for name in trial.EVIDENCE_NAMES:
            for location in ('path', 'retained'):
                with self.subTest(name=name, location=location):
                    path = Path(self.plan['evidence'][name][location])
                    original = path.read_bytes()
                    path.write_bytes(original + b' ')
                    with self.assertRaisesRegex(ValueError, 'changed'):
                        trial.verify_plan(self.plan, self.folder)
                    path.write_bytes(original)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_source_edit_or_source_addition_invalidates_snapshot(self):
        """Neither replaced code nor a newly importable module can inherit the source pin."""
        self.prepare()
        original = self.code.read_bytes()
        self.code.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'Source bytes changed'):
            trial.verify_plan(self.plan, self.folder)
        self.code.write_bytes(original)
        (self.code.parent / 'new_module.py').write_text('changed inventory')
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            trial.verify_plan(self.plan, self.folder)

    def test_empty_package_source_is_pinned_but_empty_evidence_is_rejected(self):
        """An empty __init__ remains part of the immutable source inventory, not missing evidence."""
        package = self.model_source / '__init__.py'
        package.write_bytes(b'')
        self.prepare()
        relative = package.relative_to(self.root).as_posix()
        archived = self.folder / 'source-snapshot' / relative
        self.assertEqual(self.plan['sourceFiles'][relative], trial.digest(b''))
        self.assertEqual(archived.read_bytes(), b'')
        trial.verify_plan(self.plan, self.folder)
        with self.assertRaises(ValueError):
            trial.read_bytes(package)
        package.write_bytes(b'x = 1\n')
        with self.assertRaisesRegex(ValueError, 'Source bytes changed'):
            trial.verify_plan(self.plan, self.folder)
        package.write_bytes(b'')
        archived.write_bytes(b'# changed\n')
        with self.assertRaisesRegex(ValueError, 'Source bytes changed'):
            trial.verify_plan(self.plan, self.folder)

    def test_source_edit_during_prewarm_prevents_the_only_start(self):
        """The post-load source check catches code changes while the GPU would be loading."""
        self.prepare()
        self.claim()
        self.load_action = lambda policy: self.code.write_bytes(b'edited during loading')
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertIn('Source bytes changed', self.report()['error'])

    def test_goal_edit_during_prewarm_is_not_stamped(self):
        """A cached-looking metadata object never authorizes a changed embedding file."""
        self.prepare()
        self.claim()
        self.load_action = lambda policy: self.goal.write_bytes(self.goal.read_bytes() + b' ')
        self.assertEqual(self.worker(), 1)
        self.assertFalse(hasattr(self.last_policy, 'combat_trial_goal_sha256'))
        self.assertEqual(self.lifecycle.starts, 0)

    def test_stop_during_load_preserves_failure_without_opening_a_lease(self):
        """The worker observes terminal STOP immediately after prewarm."""
        self.prepare()
        self.claim()
        self.load_action = lambda policy: (self.folder / 'STOP').write_text('operator stop')
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertIn('seriesOperatorStop', self.report()['error'])
        self.assertEqual(read_split(self.folder, self.plan['runId'])['split'], 'diagnostic')

    def test_elevated_console_or_wrong_session_worker_cannot_load(self):
        """Each ordinary-RDP requirement is independently enforced before model allocation."""
        for key, value in (('elevated', True), ('remoteDesktop', False), ('windowsSessionId', 1), ('integrityRid', 12288)):
            with self.subTest(key=key):
                self.folder = self.live / ('trial-' + key)
                self.prepare()
                self.claim()
                identity = self.identity(3)
                identity[key] = value
                self.assertEqual(self.worker(identity_reader=lambda session: identity), 1)
                self.assertIn('ordinary RDP session', self.report()['error'])
                self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_changed_loaded_model_configuration_is_refused(self):
        """The actual adapter metadata must prove FP16, H41 and validated prewarm."""
        for key, value in (('precision', 'float32'), ('historyFrames', 40), ('graphCaptureValidated', False)):
            with self.subTest(key=key):
                self.folder = self.live / ('trial-' + key)
                self.prepare()
                self.claim()
                self.load_action = lambda policy: policy.metadata.update({key: value})
                self.assertEqual(self.worker(), 1)
                self.assertIn('fixed prewarmed FP16 H41', self.report()['error'])
                self.assertEqual(self.lifecycle.starts, 0)

    def test_loader_failure_preserves_attempt_and_elapsed_time(self):
        """A failed allocation is retained without falsely counting a completed model load."""
        self.prepare()
        self.claim()
        def fail(policy):
            """Fail before the injected loader can return a usable policy."""
            raise RuntimeError('synthetic allocation failure')
        self.load_action = fail
        self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual((report['modelLoadAttempts'], report['modelLoads'], self.lifecycle.starts), (1, 0, 0))
        self.assertGreater(report['modelLoadSeconds'], 0)

    def test_expired_host_deadline_is_terminal_before_loading(self):
        """A delayed worker cannot establish a new ninety-second budget."""
        self.prepare()
        self.claim()
        path = self.folder / 'CONSUMED.json'
        value = json.loads(path.read_bytes())
        value['deadlineMonotonicNs'] = time.monotonic_ns() - 1
        path.write_bytes(canonical(value))
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_busy_original_child_refuses_the_single_plan_without_starting(self):
        """A passive observer or other task cannot share the first combat lease."""
        self.prepare()
        self.claim()
        self.lifecycle.child['agentStreamRunning'] = True
        with patch.object(trial, 'await_idle', side_effect=RuntimeError('original child remains busy')):
            self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_changed_owner_is_terminal_without_model_or_listener(self):
        """The sealed pair cannot silently select a later child in the same RDP session."""
        self.prepare()
        self.claim()
        self.lifecycle.child['instanceNonce'] = 'substituted-child'
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_recording_error_never_becomes_inconclusive_completion(self):
        """No-action expiry cannot conceal a failed recorder."""
        self.prepare()
        self.claim()
        def fail_recording(native):
            """Retain an interrupted recorder and a zero-action terminal guard."""
            native.update(status='failed', acceptedInputActions=0, decisions=[], recording=dict(error='disk error'))
            native['combatTrialGuardState'].update(phase='stopped', trialComplete=False, acceptedActions=0,
                completedActions=0, completed=[], trip=dict(reason='trialDeadline'))
        self.episode_action = fail_recording
        self.assertEqual(self.worker(), 1)
        self.assertEqual(self.report()['status'], 'failed')

    def test_incomplete_lossy_or_unretired_recording_cannot_complete(self):
        """A fully drained combat guard cannot override incomplete asynchronous recording."""
        mutations = [('complete', False), ('lossless', False), ('workerRetired', False),
            ('droppedFrames', 1), ('droppedEvents', 1), ('droppedObservations', 1), ('abandonedFrames', 1)]
        for key, value in mutations:
            with self.subTest(key=key):
                self.folder = self.live / ('trial-recording-' + key)
                self.prepare()
                self.claim()
                self.episode_action = lambda native: native['recording'].update({key: value})
                self.assertEqual(self.worker(), 1)
                report = self.report()
                self.assertEqual(report['status'], 'failed')
                self.assertTrue(report['combatTrialGuardState']['trialComplete'])
                self.assertEqual(report['recordedBytes'], 5 * trial.RGB192_BYTES)
                self.assertEqual(read_split(self.folder, self.plan['runId'])['split'], 'diagnostic')

    def test_missing_zero_or_mismatched_frame_counts_cannot_complete(self):
        """Completion needs nonzero joined encoded, RGB and observation counts."""
        mutations = [('encodedFrames', 0), ('recordedObservations', 0), ('policyRgbFrames', 0),
            ('policyRgbBytes', 0), ('encodedFrames', 4), ('policyRgbFrames', 4),
            ('policyRgbBytes', 4 * trial.RGB192_BYTES), ('droppedFrames', False), ('workerRetired', None)]
        for index, (key, value) in enumerate(mutations):
            with self.subTest(key=key, value=value):
                self.folder = self.live / ('trial-counts-' + str(index))
                self.prepare()
                self.claim()
                self.episode_action = lambda native: native['recording'].update({key: value})
                self.assertEqual(self.worker(), 1)
                self.assertEqual(self.report()['status'], 'failed')

    def test_real_watch_binds_only_known_control_uuid_and_shared_deadline(self):
        """The reused supervisor receives no scout input/route binding and never discovers a UUID."""
        self.prepare()
        self.claim()
        claim = json.loads((self.folder / 'CONSUMED.json').read_bytes())
        class WatchShell:
            """Capture constructor/admission wiring without starting monitoring threads."""
            def __init__(self, folder, settings, owner, lifecycle):
                self.series = SimpleNamespace(deadline_ns=claim['deadlineMonotonicNs'] + 10_000)
                self.settings, self.owner, self.run_id = settings, owner, None
            def activate(self, folder):
                self.active = folder
        with patch.object(trial, 'SessionWatch', WatchShell):
            watch = trial.make_watch(self.folder, self.plan, claim, self.lifecycle, object())
        self.assertEqual(watch.run_id, self.plan['runId'])
        self.assertEqual(watch.series.deadline_ns, claim['deadlineMonotonicNs'])
        self.assertEqual(watch.series.stop_file, self.folder / 'STOP')
        self.assertEqual(watch.owner, self.plan['owner'])

    def test_failed_start_stays_unresolved_and_is_not_retried(self):
        """Unknown listener outcome cannot be reconciled by start or a broad stop."""
        self.prepare()
        self.claim()
        self.lifecycle.start_error = RuntimeError('start acknowledgement lost')
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (1, 0))
        self.assertEqual(self.report()['nativeStartOutcome'], 'unresolved')
        self.assertEqual(self.report()['status'], 'unresolved')

    def test_failed_episode_keeps_recording_guard_and_original_manifest_split(self):
        """An applied partial trial remains diagnostic evidence, never a retry opportunity."""
        self.prepare()
        self.claim()
        def fail(native):
            """Retain a terminal health trip after one action."""
            native.update(status='failed', endReason='error', error='health hazard', acceptedInputActions=1)
            native['combatTrialGuardState'].update(phase='stopped', trialComplete=False,
                trip=dict(reason='healthFractionDrop'), acceptedActions=1, completedActions=0, completed=[])
        self.episode_action = fail
        self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['combatTrialGuardState']['trip']['reason'], 'healthFractionDrop')
        self.assertEqual(report['acceptedInputActions'], 1)
        self.assertGreater(report['recordedBytes'], 0)
        self.assertEqual(read_split(self.folder, self.plan['runId'])['sourceManifestSha256'],
                         trial.digest((self.folder / 'patrol.json').read_bytes()))

    def test_zero_eligible_proposals_is_inconclusive_not_success(self):
        """A policy that never emits an eligible attack earns no combat completion."""
        self.prepare()
        self.claim()
        def inconclusive(native):
            """Preserve an ordinary bounded expiry with no candidate action."""
            native.update(status='failed', endReason='durationElapsed', acceptedInputActions=0, decisions=[])
            native['combatTrialGuardState'].update(phase='stopped', trialComplete=False, acceptedActions=0,
                completedActions=0, completed=[], trip=dict(reason='trialEndedBeforeDrain'))
        self.episode_action = inconclusive
        self.assertEqual(self.worker(), 1)
        self.assertEqual(self.report()['status'], 'inconclusive')

    def test_missing_third_post_frame_cannot_complete(self):
        """Three admissions are insufficient without the final release-to-frame drain."""
        self.prepare()
        self.claim()
        self.episode_action = lambda native: native['combatTrialGuardState']['completed'][-1].pop('postFrame')
        self.assertEqual(self.worker(), 1)
        self.assertIn('drain evidence', self.report()['finalizationError'])

    def test_unresolved_cleanup_preserves_the_completed_native_episode(self):
        """Native trial completion cannot hide an unresolved owner/lease retirement."""
        self.prepare()
        self.claim()
        with patch.object(trial, 'await_idle', side_effect=RuntimeError('cleanup unresolved')):
            self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual(report['status'], 'unresolved')
        self.assertEqual(report['nativeEpisode']['endReason'], 'combatTrialComplete')
        self.assertGreater(report['recordedBytes'], 0)

    def test_unpublished_episode_failure_keeps_retained_recording_and_unknown_outcome(self):
        """A raised episode cannot lose bytes just because its JSON finalizer never ran."""
        self.prepare()
        self.claim()
        def fail(native):
            """Fail after recording bytes exist and before the native report is written."""
            raise RuntimeError('native report publication failed')
        self.episode_action = fail
        self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual(report['status'], 'unresolved')
        self.assertIsNone(report['nativeEpisode'])
        self.assertEqual(report['episodeCalls'], 1)
        self.assertGreater(report['recordedBytes'], 0)
        self.assertEqual(read_split(self.folder, self.plan['runId'])['split'], 'diagnostic')

    def test_goal_request_during_cleanup_is_retained_and_refused(self):
        """The immutable final wrapper includes goal changes arriving after native teardown."""
        self.prepare()
        self.claim()
        def late_goal(lifecycle, owner):
            """Introduce a late request while the wrapper waits for ordinary owner retirement."""
            path = self.folder / 'patrol.json.control.json'
            value = json.loads(path.read_bytes())
            value.update(goalRequestId='b' * 32, goalEmbedding=str(self.goal), goalIntent='stationary')
            trial.runtime.atomic_json(path, value)
            return True
        with patch.object(trial, 'await_idle', side_effect=late_goal):
            self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['finalControlDocument']['goalRequestId'], 'b' * 32)
        self.assertIn('frozen goal changed', report['terminalControlError'])

    def test_host_interrupt_stops_loading_before_waiting_for_broker_retirement(self):
        """Ctrl-C consumes the plan and publishes STOP before the worker can open input."""
        self.prepare()
        def loading(policy):
            """Wait briefly for the host's injected interruption, without a model or native action."""
            until = time.monotonic() + 2
            while not (self.folder / 'STOP').exists() and time.monotonic() < until:
                time.sleep(.01)
        class InterruptWatch(FakeWatch):
            """Interrupt host supervision after admission and command dispatch."""
            def __init__(self, *args):
                super().__init__(*args)
                self.checks = 0
            def check(self):
                self.checks += 1
                if self.checks == 3:
                    raise KeyboardInterrupt()
                super().check()
        self.load_action = loading
        self.lifecycle.runner = self.worker
        self.assertEqual(trial.launch(self.plan_path, lifecycle=self.lifecycle, watch_factory=InterruptWatch), 1)
        self.assertTrue((self.folder / 'STOP').exists())
        self.assertEqual(self.lifecycle.starts, 0)
        result = json.loads((self.folder / 'result.json').read_bytes())
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['stopReason'], 'KeyboardInterrupt')

    def test_late_raw_goal_request_is_rejected_without_waiting_for_monitor(self):
        """The final exact-control read catches a goal mutation between monitor polls."""
        self.prepare()
        self.claim()
        def mutate_goal(native):
            """Write a well-formed but forbidden late goal request into this run's control."""
            path = self.folder / 'patrol.json.control.json'
            value = json.loads(path.read_bytes())
            value.update(goalRequestId='a' * 32, goalEmbedding=str(self.goal), goalIntent='stationary')
            trial.runtime.atomic_json(path, value)
        self.episode_action = mutate_goal
        self.assertEqual(self.worker(), 1)
        self.assertIn('frozen goal changed', self.report()['finalizationError'])

    def test_unknown_broker_outcome_keeps_plan_consumed_and_requests_only_its_stop(self):
        """Lost command outcome never starts a second worker."""
        self.prepare()
        def unknown():
            """Simulate a lost broker response without running a worker."""
            raise RuntimeError('broker outcome unknown')
        self.lifecycle.runner = unknown
        self.assertEqual(trial.launch(self.plan_path, lifecycle=self.lifecycle, watch_factory=FakeWatch), 1)
        self.assertEqual(self.lifecycle.launches, 1)
        self.assertTrue((self.folder / 'CONSUMED.json').exists())
        self.assertTrue((self.folder / 'STOP').exists())
        self.assertEqual(json.loads((self.folder / 'result.json').read_bytes())['status'], 'unresolved')

    def test_stop_does_not_readdress_a_foreign_control_uuid(self):
        """A substituted file remains evidence and receives no stop authority."""
        self.prepare()
        path = self.folder / 'patrol.json.control.json'
        original = canonical(dict(version=1, runId='f' * 32, command='run'))
        path.write_bytes(original)
        trial.request_stop(self.folder, self.plan, 'operatorStop')
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
