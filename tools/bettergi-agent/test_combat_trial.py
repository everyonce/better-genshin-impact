"""CPU-only lifecycle tests for immutable, single-use reviewed combat launch plans."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import combat_trial as trial
from combat_trial_guard import canonical, SINGLE_SCOPE, GROUP_SCOPE, FOUR_SCOPE, scope_fields, trial_policy, combat_scope
from episode_split import read_split
from test_combat_trial_guard import OWNER, review_parts, proposal


def ui_transition_fixture(test, operation, suffix=''):
    """Retain a complete synthetic native UI run without calling its platform implementation."""
    from PIL import Image
    from combat_pause_proof import CORE_REVISIONS, revision
    folder = test.live / (operation + '-native' + suffix)
    folder.mkdir()
    app = test.root / 'artifacts/release/BetterGI-English-win-x64'
    pilot = app / 'User/JsScript/ActOnePilot'
    pilot.mkdir(parents=True, exist_ok=True)
    sources, revisions = {}, {}
    for name in sorted(CORE_REVISIONS | {'world-inventory.js', 'manifest.json', 'settings.json'}):
        raw = ('// exact inert native source ' + name).encode()
        (pilot / name).write_bytes(raw)
        target = folder / 'source-snapshot' / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
        sources[name], revisions[name] = trial.digest(raw), revision(raw)
    group = dict(index=1, projects=[dict(folderName='ActOnePilot', type='Javascript', runNum=1,
        jsScriptSettingsObject=dict(enableInput=True, autoEnterGame=False))],
        config=dict(pathingConfig={key: False for key in ('enabled', 'autoPickEnabled', 'autoSkipEnabled',
            'autoRunEnabled', 'autoFightEnabled', 'jsScriptUseEnabled', 'soloTaskUseFightEnabled')}))
    (folder / 'group.json').write_bytes(canonical(group))
    (folder / 'group-after-stop.json').write_bytes(canonical(dict(group, index=0)))
    plan = dict(owner=copy.deepcopy(OWNER), sourceFiles=sources, groupSha256=trial.digest(canonical(group)),
        modelLoaded=False, autoEnterGame=False, walkingAllowed=False, attacksAllowed=False)
    if operation == 'resume':
        plan.update(allowedPilotOperations=['observe', 'worldInventoryClose'], maximumInventoryCloseRequests=1)
    (folder / 'plan.json').write_bytes(canonical(plan))
    session, now = 'inert-' + operation + suffix, time.time_ns() // 1_000_000 - 300
    rows = []
    for frame_id, label, paused, stamp in ((1, 'before', operation == 'resume', now),
            (3 if operation == 'pause' else 4, 'after', operation == 'pause', now + 150)):
        image = io.BytesIO()
        Image.new('RGB', (1920, 1080), (frame_id, 0, 0)).save(image, 'PNG')
        raw_image = image.getvalue()
        hud = {key: False for key in ('world', 'dialogueReady', 'choice', 'journal', 'bigMap', 'climbing', 'auto')}
        hud['world'] = not paused
        ocr = [dict(text='Weapons', x=144, y=32, width=115, height=37),
            dict(text='Weapons 13/2000', x=1604, y=33, width=195, height=30),
            dict(text="Traveler's Handy Sword", x=1338, y=133, width=405, height=35)] if paused else []
        relative = Path('observations') / session / f'frame-{frame_id:04d}.png'
        observation = dict(session=session, frameId=frame_id, timestamp=stamp, screenshotPath=relative.as_posix(),
            hud=hud, ocr=ocr, map=None if paused else dict(x=-1217, y=2508))
        native = pilot / relative
        native.parent.mkdir(parents=True, exist_ok=True)
        native.write_bytes(raw_image)
        native.with_suffix('.json').write_bytes(canonical(observation))
        (folder / (label + '.png')).write_bytes(raw_image)
        (folder / (label + '.json')).write_bytes(canonical(observation))
        rows.append(dict(label=label, frameId=frame_id, source=str(native), imageSha256=trial.digest(raw_image),
                         jsonSha256=trial.digest(canonical(observation))))
    if operation == 'resume':
        # Match the retained live run: native frame two is captured for Escape,
        # between the helper's retained request frame one and terminal frame four.
        input_frame = json.loads((folder / 'before.json').read_bytes())
        input_frame.update(frameId=2, timestamp=now + 15,
            screenshotPath=(Path('observations') / session / 'frame-0002.png').as_posix())
        native = pilot / input_frame['screenshotPath']
        native.write_bytes((folder / 'before.png').read_bytes())
        native.with_suffix('.json').write_bytes(canonical(input_frame))
    step = 'worldInventory' if operation == 'pause' else 'worldInventoryClose'
    request = dict(id='request-' + operation + suffix, session=session, expectedFrameId=1,
        createdAt=now + 1, mission='questStep', step=step)
    revision_names = CORE_REVISIONS | ({'world-inventory.js'} if operation == 'resume' else set())
    events = [dict(type='controllerRevision', files={name: revisions[name] for name in revision_names}, startedAt=now + 2)]
    key = dict(type='key', key='VK_B' if operation == 'pause' else 'VK_ESCAPE', durationMs=60,
               startedAt=now + 20, finishedAt=now + 80)
    if operation == 'resume':
        events.append(dict(type='worldInventoryClose', frameId=2, startedAt=now + 18, finishedAt=now + 100))
        key['frameId'] = 2
    events.append(key)
    result = dict(status='completed', step=step, frameId=2 if operation == 'pause' else 3)
    result.update(pausedInventory=True) if operation == 'pause' else result.update(worldVisible=True)
    receipt = dict(session=session, id=request['id'], mission='questStep', status='completed', timestamp=now + 151,
        frameId=3 if operation == 'pause' else 4, details=dict(result=result, inputEvents=events))
    for kind, value in (('request', request), ('receipt', receipt)):
        (folder / (request['id'] + '.' + kind + '.json')).write_bytes(canonical(value))
    flags = dict(taskRunning=False, agentStreamRunning=False, serviceOwnsPilot=False)
    child = dict(OWNER['child'], **flags, rootProcessId=OWNER['root']['processId'], scriptSession=session,
        runtimeRunning=True, automationState='game_ready', pilotState='faulted', appDirectory=str(app))
    parent = dict(OWNER['root'], **flags, uiStatus='current', childWindowMinimized=True, childConnectedState=1,
                  childSessionId=OWNER['child']['windowsSessionId'])
    (folder / 'owner-after-stop.json').write_bytes(canonical(dict(root=parent, child=child)))
    report = dict(status='completed', modelLoaded=False, scriptSession=session, ownerIdleMinimizedAfter=True,
        temporaryGroupRemoved=True, ownTerminalRequestRemoved=True, observations=rows,
        controls=[dict(command=name, receivedAtUnixNs=(now + offset) * 1_000_000, status=copy.deepcopy(child))
            for name, offset in (('startPilot', -10), ('stopPilot', 200))], requests=[dict(request=request, receipt=receipt)])
    if operation == 'pause':
        report.update(pauseVerified=True, pauseFrameId=3)
    (folder / 'result.json').write_bytes(canonical(report))
    return folder


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

    def configure_group_review(self, *, candidates=3, visible=3, scope=GROUP_SCOPE):
        """Opt in through the original review, never by changing only an observed candidate count."""
        review=json.loads(self.evidence['review'].read_bytes())
        review.update(scope_fields(scope),policy=trial_policy(scope),inspectedVisibleEnemyCount=visible)
        self.evidence['review'].write_bytes(canonical(review))
        scene=json.loads(self.evidence['scene'].read_bytes())
        from test_combat_trial_guard import frame
        scene['observations'][0]['combatEvidence']['enemyBarCandidates']=frame(candidates=candidates)['combatEvidence']['enemyBarCandidates']
        self.evidence['scene'].write_bytes(canonical(scene))

    def prepare(self, *, scope=SINGLE_SCOPE):
        """Prepare one immutable fixture plan through the real review/source admission path."""
        self.plan = trial.prepare(self.folder, self.owner_file, self.evidence, scope=scope)
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
        self.last_episode_args = args
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

    def test_group_scope_is_explicit_through_plan_worker_and_request(self):
        """The separate scope survives an actual inert worker lifecycle with every bound unchanged."""
        self.configure_group_review()
        self.prepare(scope=GROUP_SCOPE)
        self.claim()
        self.assertEqual(self.worker(),0)
        self.assertEqual(combat_scope(self.report()),GROUP_SCOPE)
        self.assertEqual(combat_scope(self.plan['binding']),GROUP_SCOPE)
        self.assertEqual(self.last_args.combat_trial_scope,GROUP_SCOPE)
        self.assertEqual(self.last_args.combat_trial_maximum_enemy_candidates,3)
        self.assertEqual(self.last_policy.combat_trial_scope,GROUP_SCOPE)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,1,1))

    def test_group_review_cannot_widen_an_ordinary_prepare(self):
        """The named CLI/preparation choice is required in addition to a reviewed image."""
        self.configure_group_review()
        with self.assertRaisesRegex(ValueError,'explicitly selected combat scope'):self.prepare()
        self.assertFalse(self.folder.exists())

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


class CombatPreparedTrialTests(unittest.TestCase):
    """Exercise the real preparation/arm lifecycle with native artifact fixtures and inert policy hooks."""
    loader = CombatTrialTests.loader
    identity = CombatTrialTests.identity
    episode = CombatTrialTests.episode
    report = CombatTrialTests.report
    configure_group_review = CombatTrialTests.configure_group_review

    def setUp(self):
        """Reuse the isolated repository and advance only evidence clocks, never platform state."""
        CombatTrialTests.setUp(self)
        self.wall_ns, self.qpc_ns, self.clock_offset = time.time_ns(), time.perf_counter_ns(), 0
        for name, method in (('time_ns', lambda: self.wall_ns + self.clock_offset),
                             ('perf_counter_ns', lambda: self.qpc_ns + self.clock_offset)):
            active = patch.object(trial.time, name, method)
            active.start()
            self.addCleanup(active.stop)

    def begin(self, *, claim=True, scope=SINGLE_SCOPE):
        """Freeze an actual-shaped positive pause without an encounter or attack plan."""
        self.pause_folder = ui_transition_fixture(self, 'pause')
        self.preparation = trial.prepare_paused(self.folder, self.owner_file, self.pause_folder, scope=scope)
        self.plan = self.preparation
        self.plan_path = self.folder / 'preparation.json'
        if claim:
            now = time.monotonic_ns()
            trial.exclusive_json(self.folder / 'CONSUMED.json', dict(runId=self.preparation['runId'],
                planSha256=trial.digest(self.plan_path.read_bytes()), startedMonotonicNs=now,
                startedAtUnixNs=time.time_ns(), deadlineMonotonicNs=now + 90_000_000_000))

    def worker(self, callback=None, **kwargs):
        """Run the production waiting loop with no native, process or GPU implementation."""
        return trial.run_worker(self.plan_path, lifecycle=self.lifecycle, loader=self.loader, episode=self.episode,
            identity_reader=self.identity, watch_factory=kwargs.pop('watch_factory', FakeWatch),
            paused_preparation=True, prepared_callback=callback, **kwargs)

    def resume(self):
        """Retain one post-readiness Escape proof and establish its independent QPC floor."""
        self.clock_offset += 500_000_000
        self.resume_folder = ui_transition_fixture(self, 'resume')
        return trial.record_resume(self.plan_path, self.resume_folder)

    def fresh_scene(self):
        """Author a separate review whose exact compositor source follows the resume marker."""
        self.clock_offset += 500_000_000
        def advance(value):
            """Update all repeated native source identities together."""
            if isinstance(value, dict):
                for name, item in value.items():
                    if name == 'timestamp100ns':
                        value[name] = time.perf_counter_ns() // 100 - 100_000
                    else:
                        advance(item)
            elif isinstance(value, list):
                for item in value:
                    advance(item)
        for name in ('review', 'plan', 'scene', 'sidecar'):
            value = json.loads(self.evidence[name].read_bytes())
            advance(value)
            if name == 'review':
                value['reviewedAtUnixNs'] = time.time_ns()
            self.evidence[name].write_bytes(canonical(value))

    def arm(self, ready=None):
        """Simulate only host artifact publication after independently retained native UI evidence."""
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertFalse(self.last_args.enable_input)
        self.assertEqual(self.last_args.max_input_actions, 0)
        self.assertFalse(hasattr(self.last_args, 'combat_trial_binding'))
        self.resume()
        self.fresh_scene()
        self.plan = trial.arm_prepared(self.plan_path, self.evidence)
        return self.plan

    def test_loads_once_while_paused_then_consumes_exact_arm_without_relabeling_history(self):
        """Only the separately reviewed post-resume scene can create one unchanged attack lease."""
        self.begin()
        self.assertNotIn('binding', self.preparation)
        self.assertNotIn('policy', self.preparation)
        self.assertEqual(self.worker(self.arm), 0)
        report = self.report()
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 1, 1))
        self.assertEqual(report['kind'], 'combat-trial-prepared-wrapper-v1')
        self.assertFalse(report['inputEnabledBeforeArm'])
        self.assertEqual(report['preparedPolicy'], self.plan['preparedPolicy'])
        self.assertEqual(report['policyMetadata']['historyCommit'], 'accepted-proposals-only')
        resumed = json.loads((self.folder / 'RESUMED.json').read_bytes())['resume']['proof']
        self.assertEqual((resumed['transition']['requestSourceFrameId'], resumed['transition']['inputSourceFrameId']), (1, 2))
        self.assertTrue(any(name.endswith('frame-0002.png') for name in resumed['files']))
        self.assertTrue(any(name.endswith('frame-0002.json') for name in resumed['files']))
        self.assertEqual(json.loads((self.folder / 'ARM-CONSUMED.json').read_bytes())['armSha256'], report['armSha256'])
        with self.assertRaises(FileExistsError):
            self.worker()
        with self.assertRaises(ValueError):
            trial.arm_prepared(self.plan_path, self.evidence)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 1))

    def test_group_preparation_readiness_review_and_worker_match(self):
        """A zero-input group preparation cannot become authority before its fresh matching arm."""
        self.configure_group_review();self.begin(scope=GROUP_SCOPE)
        self.assertFalse(self.preparation['attacksAllowed'])
        self.assertEqual(self.worker(self.arm),0)
        ready=json.loads((self.folder/'prepared.json').read_bytes())
        for value in (self.preparation,ready,self.plan,self.plan['binding'],self.report()):
            self.assertEqual(combat_scope(value),GROUP_SCOPE)
        self.assertEqual(self.plan['binding']['inspectedVisibleEnemyCount'],3)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,1,1))

    def test_four_scope_preparation_worker_and_request_keep_exact_fixed_maximum(self):
        """The additional name survives the real inert paused handoff without changing its action budget."""
        self.configure_group_review(candidates=4,visible=4,scope=FOUR_SCOPE);self.begin(scope=FOUR_SCOPE)
        self.assertEqual(self.worker(self.arm),0)
        for value in (self.preparation,json.loads((self.folder/'prepared.json').read_bytes()),
                      self.plan,self.plan['binding'],self.report()):
            self.assertEqual(combat_scope(value),FOUR_SCOPE)
            self.assertEqual(value['maximumEnemyBarCandidates'],4)
        self.assertEqual(self.last_policy.combat_trial_scope,FOUR_SCOPE)
        self.assertFalse(hasattr(self.last_args,'combat_trial_maximum_enemy_candidates'))
        self.assertEqual(self.last_episode_args.combat_trial_maximum_enemy_candidates,4)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,1,1))

    def test_three_preparation_cannot_arm_a_four_enemy_review(self):
        """A separately prepared smaller scope cannot inherit the later larger review."""
        self.begin(scope=GROUP_SCOPE);self.configure_group_review(candidates=4,visible=4,scope=FOUR_SCOPE)
        self.assertEqual(self.worker(self.arm),1)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,0,0))
        self.assertIn('explicitly selected combat scope',self.report()['error'])

    def test_default_preparation_rejects_later_group_review_before_lease(self):
        """A fresh image cannot widen the scope fixed before model loading."""
        self.begin();self.configure_group_review()
        self.assertEqual(self.worker(self.arm),1)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,0,0))
        self.assertIn('explicitly selected combat scope',self.report()['error'])

    def test_group_preparation_rejects_omitted_review_scope_before_lease(self):
        """A default single-enemy review cannot silently satisfy a prepared group scope."""
        self.begin(scope=GROUP_SCOPE)
        self.assertEqual(self.worker(self.arm),1)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,0,0))

    def test_group_readiness_scope_removal_preserves_failure_without_arm(self):
        """The ready worker's scope is part of the immutable handoff, not an inferred model setting."""
        self.configure_group_review();self.begin(scope=GROUP_SCOPE)
        def remove_scope(ready):
            """Tamper only a retained readiness declaration before any resume or arm."""
            path=self.folder/'prepared.json';value=json.loads(path.read_bytes())
            value.pop('combatScope');value.pop('maximumEnemyBarCandidates')
            path.write_bytes(canonical(value))
            self.arm()
        self.assertEqual(self.worker(remove_scope),1)
        self.assertEqual((self.lifecycle.starts,self.episodes),(0,0))

    def test_ordinary_host_keeps_preparation_claim_and_final_plan_distinct(self):
        """The broker launches one waiting worker and retires against the final armed plan."""
        self.begin(claim=False)
        self.lifecycle.runner = lambda: self.worker(self.arm)
        self.assertEqual(trial.launch(self.plan_path, lifecycle=self.lifecycle, watch_factory=FakeWatch,
                                     paused_preparation=True), 0)
        host = json.loads((self.folder / 'result.json').read_bytes())
        self.assertIn('worker-prepared', self.lifecycle.command)
        self.assertIn('--preparation', self.lifecycle.command)
        self.assertNotEqual(host['preparationSha256'], host['planSha256'])
        self.assertEqual(host['hostClaim']['planSha256'], host['preparationSha256'])
        self.assertEqual(self.lifecycle.launches, 1)

    def test_missing_or_altered_native_pause_proof_never_loads(self):
        """Summary booleans cannot replace original pixels, receipts or released ownership."""
        for index, name in enumerate(('after.png', 'request-pause.receipt.json', 'owner-after-stop.json')):
            with self.subTest(name=name):
                pause = ui_transition_fixture(self, 'pause', str(index))
                target = pause / (name.replace('request-pause', 'request-pause' + str(index)))
                target.write_bytes(b'changed')
                with self.assertRaises((ValueError, OSError)):
                    trial.prepare_paused(self.live / ('rejected-' + str(index)), self.owner_file, pause)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_unretired_native_owner_refuses_pause_preparation(self):
        """A terminal-looking pilot state with actual ownership remains inadmissible."""
        pause = ui_transition_fixture(self, 'pause')
        path = pause / 'owner-after-stop.json'
        value = json.loads(path.read_bytes())
        value['child']['serviceOwnsPilot'] = True
        path.write_bytes(canonical(value))
        with self.assertRaisesRegex(ValueError, 'ownership'):
            trial.prepare_paused(self.folder, self.owner_file, pause)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_arm_before_ready_or_precreated_handoff_has_no_input_authority(self):
        """A host cannot declare its own ready worker or queue an arm before loading."""
        self.begin()
        with self.assertRaises(FileNotFoundError):
            trial.arm_prepared(self.plan_path, self.evidence)
        trial.exclusive_json(self.folder / 'ARM.json', dict(kind='premature'))
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))
        self.assertIn('before worker admission', self.report()['error'])

    def test_stop_while_awaiting_arm_retires_loaded_policy_without_listener(self):
        """The preparation has the same STOP latch and cannot resume or renew it."""
        self.begin()
        self.assertEqual(self.worker(lambda ready: trial.request_stop(self.folder, self.preparation, 'testStop')), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertTrue(self.report()['cleanupVerified'])
        self.assertIn('seriesOperatorStop', self.report()['error'])

    def test_thermal_trip_while_waiting_never_starts_a_lease(self):
        """Waiting preserves the unchanged temperature latch without reconnecting."""
        self.begin()
        class TerminalWatch(FakeWatch):
            """Inject a latched supervision event only after real readiness publication."""
            reason = None
            def check(self):
                """Preserve all ordinary STOP/deadline checks before the injected thermal event."""
                super().check()
                if self.reason:
                    raise RuntimeError(self.reason)
        def expire(ready):
            """Model a temperature sample reaching the unchanged 78-degree limit."""
            TerminalWatch.reason = 'gpuTemperatureLimit:78'
        self.assertEqual(self.worker(expire, watch_factory=TerminalWatch), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('gpuTemperatureLimit:78', self.report()['error'])

    def test_original_deadline_expires_while_waiting_without_renewal(self):
        """The existing supervisor's deadline check also covers the input-disabled arm wait."""
        self.begin()
        watches = []
        class ExpiringWatch(FakeWatch):
            """Expose only the existing deadline to the inert timeout fixture."""
            def __init__(self, *args):
                """Keep the same claim object the real wrapper passed to supervision."""
                super().__init__(*args)
                watches.append(self)
        def expire(ready):
            """Move the inert supervisor across its original terminal boundary."""
            watches[0].claim['deadlineMonotonicNs'] = time.monotonic_ns() - 1
        self.assertEqual(self.worker(expire, watch_factory=ExpiringWatch), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('seriesTimeLimit', self.report()['error'])

    def test_changed_arm_worker_is_consumed_and_rejected_before_input(self):
        """An otherwise valid arm cannot be moved to another loaded process."""
        self.begin()
        def change(ready):
            """Replace only the submitted worker PID after the valid arm was frozen."""
            self.arm(ready)
            path = self.folder / 'ARM.json'
            value = json.loads(path.read_bytes())
            value['worker']['processId'] += 1
            path.write_bytes(canonical(value))
        self.assertEqual(self.worker(change), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertTrue((self.folder / 'ARM-CONSUMED.json').exists())

    def test_changed_native_owner_after_arm_cannot_receive_the_lease(self):
        """A replacement child cannot inherit an arm prepared for the original sealed pair."""
        self.begin()
        def replaced(ready):
            """Change only the inert discovered child after a valid arm is retained."""
            self.arm(ready)
            self.lifecycle.child['processId'] += 1
        self.assertEqual(self.worker(replaced), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertFalse(self.report()['cleanupVerified'])

    def test_phase_publication_is_atomic_and_exclusive(self):
        """A repeated publisher cannot overwrite a prior complete handoff document."""
        path = self.live / 'atomic-phase.json'
        trial.publish_once(path, dict(original=True))
        with self.assertRaises(FileExistsError):
            trial.publish_once(path, dict(replayed=True))
        self.assertEqual(json.loads(path.read_bytes()), dict(original=True))
        self.assertFalse(list(self.live.glob('.atomic-phase.json.*.tmp')))

    def test_scene_from_before_resume_cannot_arm_the_loaded_model(self):
        """The native QPC source and separate review must both follow the exact resume marker."""
        self.begin()
        def stale(ready):
            """Retain a valid resume but deliberately reuse the older reviewed scene."""
            self.resume()
            trial.arm_prepared(self.plan_path, self.evidence)
        self.assertEqual(self.worker(stale), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertFalse((self.folder / 'ARM.json').exists())
        self.assertIn('before the recorded resume', self.report()['error'])

    def test_source_change_after_readiness_prevents_arm(self):
        """The loaded bytes cannot be silently rebound during the inventory-to-world handoff."""
        self.begin()
        def changed(ready):
            """Mutate source bytes while keeping every old authority document intact."""
            self.code.write_bytes(b'changed worker source')
            self.resume()
        self.assertEqual(self.worker(changed), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('Source bytes changed', self.report()['error'])

    def test_goal_change_after_readiness_prevents_arm(self):
        """A new embedding cannot inherit the already loaded combat model's preparation."""
        self.begin()
        def changed(ready):
            """Alter the pinned embedding before attempting the separate resume record."""
            self.goal.write_bytes(self.goal.read_bytes() + b' ')
            self.resume()
        self.assertEqual(self.worker(changed), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('model or goal changed', self.report()['error'])

    def test_owner_file_change_after_readiness_prevents_arm(self):
        """A replacement lineage cannot reuse the original ordinary worker."""
        self.begin()
        def changed(ready):
            """Keep the apparent child tuple but replace its sealed owner evidence bytes."""
            self.owner_file.write_bytes(self.owner_file.read_bytes() + b' ')
            self.resume()
        self.assertEqual(self.worker(changed), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('owner evidence changed', self.report()['error'])

    def test_resume_before_readiness_cannot_be_relabelled_as_fresh(self):
        """Retaining a genuine Escape run from before prewarm does not authorize this phase."""
        self.begin()
        early_resume = ui_transition_fixture(self, 'resume')
        self.assertEqual(self.worker(lambda ready: trial.record_resume(self.plan_path, early_resume)), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('Resume preceded preparation', self.report()['error'])

    def test_review_age_is_not_renewed_by_the_arm(self):
        """A post-resume marker cannot refresh an expired human review."""
        self.begin()
        def stale(ready):
            """Use a new compositor source with an independently stale review timestamp."""
            self.resume()
            self.fresh_scene()
            path = self.evidence['review']
            value = json.loads(path.read_bytes())
            value['reviewedAtUnixNs'] -= 121_000_000_000
            path.write_bytes(canonical(value))
            trial.arm_prepared(self.plan_path, self.evidence)
        self.assertEqual(self.worker(stale), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('review is stale', self.report()['error'])

    def test_pause_witness_must_still_be_recent_when_loading_starts(self):
        """A delayed launch cannot start a cold load against a stale inventory snapshot."""
        self.begin()
        self.clock_offset += 31_000_000_000
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))
        self.assertIn('no longer recent', self.report()['error'])

    def test_checkpoint_validation_cannot_age_the_pause_past_model_admission(self):
        """A slow read-only checkpoint hash does not extend the positive-pause loading gate."""
        self.begin()
        expected = trial.runtime.OPEN_P2P_SHA256
        def slow_hash(path):
            """Advance only the fixture clock while returning the exact pinned checkpoint digest."""
            self.clock_offset += 31_000_000_000
            return expected
        with patch.object(trial, 'file_sha', slow_hash):
            self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.report()['modelLoadAttempts']), (0, 0, 0))
        self.assertIn('expired before model loading', self.report()['error'])

    def test_stop_during_final_source_validation_prevents_listener_creation(self):
        """Long artifact verification cannot hide STOP between arm consumption and native start."""
        self.begin()
        original, checked = trial.verify_plan, []
        def stopping(plan, folder):
            """Latch STOP on the final independently reopened source/goal boundary."""
            value = original(plan, folder)
            checked.append(True)
            if len(checked) == 2:
                trial.request_stop(folder, plan, 'stopDuringFinalVerification')
            return value
        with patch.object(trial, 'verify_plan', stopping):
            self.assertEqual(self.worker(self.arm), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('seriesOperatorStop', self.report()['error'])

    def test_missing_actual_escape_input_image_prevents_resume_record(self):
        """Host before/after PNGs cannot replace the native frame actually named by Escape."""
        self.begin()
        def missing(ready):
            """Remove the exact intermediate native image while preserving both helper captures."""
            self.clock_offset += 500_000_000
            resume = ui_transition_fixture(self, 'resume')
            report = json.loads((resume / 'result.json').read_bytes())
            Path(report['observations'][0]['source']).with_name('frame-0002.png').unlink()
            trial.record_resume(self.plan_path, resume)
        self.assertEqual(self.worker(missing), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertFalse((self.folder / 'RESUMED.json').exists())

    def test_stale_actual_escape_input_frame_cannot_inherit_fresh_host_frame(self):
        """The exact intermediate native frame keeps the existing 1000-ms UI freshness gate."""
        self.begin()
        def stale(ready):
            """Make only the actual input observation stale while keeping the request source fresh."""
            self.clock_offset += 500_000_000
            resume = ui_transition_fixture(self, 'resume')
            report = json.loads((resume / 'result.json').read_bytes())
            path = Path(report['observations'][0]['source']).with_name('frame-0002.json')
            value = json.loads(path.read_bytes())
            value['timestamp'] = report['requests'][0]['receipt']['details']['inputEvents'][1]['startedAt'] - 1001
            path.write_bytes(canonical(value))
            trial.record_resume(self.plan_path, resume)
        self.assertEqual(self.worker(stale), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('Inventory Escape source changed', self.report()['error'])

    def test_stripped_preparation_declaration_cannot_use_the_legacy_worker(self):
        """Historical admission remains available only for genuinely historical clean plans."""
        self.begin()
        def stripped(ready):
            """Remove only the prepared authority after a valid arm was published."""
            self.arm(ready)
            path = self.folder / 'plan.json'
            value = json.loads(path.read_bytes())
            value.pop('preparedPolicy')
            path.write_bytes(canonical(value))
        self.assertEqual(self.worker(stripped), 1)
        self.assertEqual((self.loads, self.lifecycle.starts), (1, 0))
        self.assertIn('stripped or invented', self.report()['error'])


if __name__ == '__main__':
    unittest.main()
