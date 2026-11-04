"""Inert native artifacts exercise capture/pause/review/load/precheck/resume ordering without a GPU or pipe."""
import copy
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import combat_trial as trial
import combat_paused_review_proof as proof
import test_combat_trial as fixtures
from combat_trial_guard import FOUR_SCOPE, canonical


class PausedReviewTrialTests(unittest.TestCase):
    """Run the real new protocol with ordinary synthetic identity and input-free lifecycle fixtures."""
    loader = fixtures.CombatTrialTests.loader
    identity = fixtures.CombatTrialTests.identity
    episode = fixtures.CombatTrialTests.episode
    report = fixtures.CombatTrialTests.report
    configure_group_review = fixtures.CombatTrialTests.configure_group_review
    fresh_scene = fixtures.CombatPreparedTrialTests.fresh_scene
    probe = fixtures.CombatPreparedTrialTests.probe

    def setUp(self):
        """Give each trial its own small source tree, original baseline and real-shaped native image."""
        fixtures.CombatPreparedTrialTests.setUp(self)
        def fixture_owner_inputs(path, artifacts, validate_owner):
            """Only this synthetic lifecycle owner is abbreviated; the held-module suite replays real-shaped lineage."""
            self.assertEqual(Path(path), self.owner_file)
            self.assertEqual(json.loads(Path(path).read_bytes()), fixtures.OWNER)
            return validate_owner(path), {str(Path(path).absolute()): trial.digest(Path(path).read_bytes())}, {}
        owner_inputs = patch.object(trial.file_admission, 'owner_inputs', side_effect=fixture_owner_inputs)
        owner_inputs.start()
        self.addCleanup(owner_inputs.stop)
        # Match the raw current native status relationship, so independent cleanup replay need not trust booleans.
        self.lifecycle.root.update(taskRunning=False, agentStreamRunning=False, serviceOwnsPilot=False,
            childConnectedState=1, childSessionId=self.lifecycle.child['windowsSessionId'])
        self.lifecycle.child['rootProcessId'] = self.lifecycle.root['processId']
        self.configure_group_review(candidates=4, visible=4, scope=FOUR_SCOPE)
        self.capture_folder = self.live / 'capture-pause'
        self.scene_folder = self.live / 'native-scene'
        self.pause_folder = fixtures.ui_transition_fixture(self, 'pause', '-baseline')
        review = json.loads(self.evidence['review'].read_bytes())
        self.baseline_health, self.maximum_health = review['inspectedHealth'], review['inspectedMaximumHealth']
        self.request = trial.begin_review_capture(self.capture_folder, self.owner_file, self.pause_folder,
            self.scene_folder, self.baseline_health, self.maximum_health)
        self.request_path = self.capture_folder / 'capture-request.json'
        self.plan_path = self.folder / 'preparation.json'
        self.prepared_seen = self.prechecked_seen = None

    def capture_and_pause(self, *, later_pause_health=None):
        """Retain actual nativeScene-shaped bytes and immediately pair a later positive inventory proof."""
        self.fresh_scene()
        self.scene_folder.mkdir()
        review = json.loads(self.evidence['review'].read_bytes())
        names = dict(plan='plan.json', scene='result.json', sidecar=str(Path(review['imageName']).with_suffix('.json')),
                     image=review['imageName'])
        for name, filename in names.items():
            path = self.scene_folder / filename
            path.write_bytes(self.evidence[name].read_bytes())
            self.evidence[name] = path
        trial.complete_review_capture(self.request_path)
        self.clock_offset += 500_000_000
        self.paired_pause = fixtures.ui_transition_fixture(self, 'pause', '-paired')
        if later_pause_health is not None:
            report_path = self.paired_pause / 'result.json'
            report = json.loads(report_path.read_bytes())
            row = next(item for item in report['observations'] if item['label'] == 'after')
            path = self.paired_pause / 'after.json'
            value = json.loads(path.read_bytes())
            value['hud']['health'] = dict(hpFraction=later_pause_health / self.maximum_health)
            raw = canonical(value)
            path.write_bytes(raw)
            Path(row['source']).with_suffix('.json').write_bytes(raw)
            row['jsonSha256'] = trial.digest(raw)
            report_path.write_bytes(canonical(report))
        trial.record_review_pause(self.request_path, self.paired_pause)
        self.clock_offset += 500_000_000
        review['reviewedAtUnixNs'] = time.time_ns()
        self.evidence['review'].write_bytes(canonical(review))

    def prepare(self, *, claim=True, source_stale_recovery=False):
        """Create the reviewed zero-input preparation only after actual paused review."""
        self.preparation = trial.prepare_reviewed_paused(self.folder, self.owner_file,
            self.capture_folder / 'paired-pause.json', self.evidence, source_stale_recovery=source_stale_recovery)
        self.plan = self.preparation
        if claim:
            client_started = time.perf_counter_ns()
            now = time.monotonic_ns()
            trial.exclusive_json(self.folder / 'CONSUMED.json', dict(runId=self.preparation['runId'],
                planSha256=trial.digest(self.plan_path.read_bytes()), startedMonotonicNs=now,
                startedAtUnixNs=time.time_ns(), startedAtClientNs=client_started,
                deadlineMonotonicNs=now + 90_000_000_000))
        return self.preparation

    def arm(self, ready):
        """Consume a sealed review after one inert model load, while no listener exists."""
        self.prepared_seen = copy.deepcopy(ready)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertFalse(self.last_args.enable_input)
        self.assertFalse(hasattr(self.last_args, 'combat_trial_binding'))
        self.plan = trial.arm_reviewed_paused(self.plan_path)

    def resume(self, prechecked):
        """Retain a single post-precheck Escape proof; this fixture never issues physical keys."""
        self.prechecked_seen = copy.deepcopy(prechecked)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.clock_offset += 500_000_000
        self.resume_folder = fixtures.ui_transition_fixture(self, 'resume', '-final')
        return trial.record_reviewed_resume(self.plan_path, self.resume_folder)

    def worker(self, *, arm=None, resume=None, **kwargs):
        """Execute the shared worker and its private precheck with inert model/native dependencies."""
        return trial.run_worker(self.plan_path, lifecycle=self.lifecycle, loader=self.loader, episode=self.episode,
            identity_reader=self.identity, watch_factory=fixtures.FakeWatch, reviewed_paused=True,
            prepared_callback=arm or self.arm, reviewed_resume_callback=resume or self.resume,
            pause_probe=self.probe, **kwargs)

    def test_stale_recovery_requires_the_explicit_cli_or_api_selection(self):
        """Neither a new review alone nor a flag on an old review silently changes the selected policy."""
        from combat_trial_guard import trial_policy
        self.capture_and_pause()
        with self.assertRaisesRegex(ValueError, 'explicitly selected'):
            self.prepare(source_stale_recovery=True)
        self.assertFalse(self.folder.exists())
        review = json.loads(self.evidence['review'].read_bytes())
        review['policy'] = trial_policy(FOUR_SCOPE, source_stale_recovery=True)
        self.evidence['review'].write_bytes(canonical(review))
        with self.assertRaisesRegex(ValueError, 'explicitly selected'):
            self.prepare()
        self.assertFalse(self.folder.exists())
        argv = ['prepare-reviewed-paused', '--directory', str(self.folder), '--owner-from', str(self.owner_file),
                '--paired-pause', str(self.capture_folder / 'paired-pause.json'), '--source-stale-recovery']
        for name, value in self.evidence.items():
            argv += ['--native-plan' if name == 'plan' else '--native-scene' if name == 'scene' else '--' + name, str(value)]
        with patch.object(trial, 'prepare_reviewed_paused', return_value=dict(runId='a' * 32)) as prepare:
            self.assertEqual(trial.main(argv), 0)
            self.assertIs(prepare.call_args.kwargs['source_stale_recovery'], True)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (0, 0, 0))

    def test_stale_recovery_is_bound_through_reviewed_preparation_and_worker(self):
        """The new recovery is reviewed while paused and stamped only after the exact ARM is verified."""
        from combat_trial_guard import trial_policy
        self.capture_and_pause()
        review = json.loads(self.evidence['review'].read_bytes())
        review['policy'] = trial_policy(FOUR_SCOPE, source_stale_recovery=True)
        self.evidence['review'].write_bytes(canonical(review))
        self.prepare(source_stale_recovery=True)
        self.assertEqual(self.worker(), 0, self.report().get('error'))
        policy = self.plan['binding']['policy']
        self.assertEqual(self.plan['policy'], policy)
        self.assertEqual(self.preparation['reviewedCombat']['binding']['policy'], policy)
        self.assertEqual(self.last_episode_args.combat_trial_source_stale_recovery_policy, policy['sourceStaleRecoveryPolicy'])
        self.assertEqual(self.last_policy.combat_trial_source_stale_recovery_policy, policy['sourceStaleRecoveryPolicy'])
        self.assertFalse(hasattr(self.last_args, 'combat_trial_source_stale_recovery_policy'))
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 1, 1))

    def test_stale_recovery_substitution_and_legacy_entry_refuse_before_input(self):
        """A new descriptor cannot be inserted/removed across preparation, ARM, plan or direct-launch scope."""
        from combat_trial_guard import trial_policy
        self.capture_and_pause()
        review = json.loads(self.evidence['review'].read_bytes())
        review['policy'] = trial_policy(FOUR_SCOPE, source_stale_recovery=True)
        self.evidence['review'].write_bytes(canonical(review))
        legacy_folder = self.live / 'legacy-recovery-refused'
        with self.assertRaisesRegex(ValueError, 'reviewed-paused preparation'):
            trial.prepare(legacy_folder, self.owner_file, self.evidence, scope=FOUR_SCOPE)
        self.assertFalse(legacy_folder.exists())
        self.prepare(source_stale_recovery=True)
        def inspect(ready):
            """Use the real worker ARM, then corrupt only in-memory candidate authority."""
            self.arm(ready)
            for field in ('policy', 'binding'):
                changed = copy.deepcopy(self.plan)
                target = changed['binding']['policy'] if field == 'binding' else changed['policy']
                target.pop('sourceStaleRecoveryPolicy')
                with self.subTest(field=field), self.assertRaises(ValueError):
                    trial.verify_reviewed_plan(changed, self.folder)
            changed = copy.deepcopy(self.plan)
            changed['kind'] = 'combat-trial-plan-v1'
            with self.assertRaisesRegex(ValueError, 'reviewed-paused plan'):
                trial.episode_arguments(changed)
            raise ValueError('inert recovery-substitution check finished')
        self.assertEqual(self.worker(arm=inspect), 1)
        self.assertEqual(self.report()['error'], 'inert recovery-substitution check finished')
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertTrue(self.report()['cleanupVerified'])


    def test_review_then_model_then_precheck_then_resume_keeps_original_native_binding(self):
        """A pre-resume image is admitted only by this complete new chain and the unchanged live policy."""
        self.capture_and_pause()
        self.prepare()
        self.assertEqual(self.loads, 0)
        self.assertEqual(self.worker(), 0, self.report())
        report = self.report()
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 1, 1))
        self.assertTrue(report['cleanupVerified'])
        self.assertEqual(report['kind'], proof.WRAPPER_KIND)
        self.assertEqual(self.plan['binding'], self.preparation['reviewedCombat']['binding'])
        self.assertLess(self.plan['binding']['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100,
                        self.prechecked_seen['checkedAtClientNs'])
        self.assertEqual(self.prechecked_seen['hostClaim']['deadlineMonotonicNs']
            - self.prechecked_seen['hostClaim']['startedMonotonicNs'], 90_000_000_000)
        self.assertIn('finalPausedReviewAdmission', report)
        self.assertTrue((self.folder / 'RESUME-CONSUMED.json').exists())

    def inspect_reviewed_plan_before_resume(self, inspect):
        """Inspect a genuinely armed fixture while paused, then retire without a resume or listener."""
        self.capture_and_pause()
        self.prepare()
        inspected = []
        def armed(ready):
            """Keep every assertion inside the real readiness/arm chain, before held acquisition."""
            self.arm(ready)
            inspect(self.plan)
            inspected.append(True)
            raise ValueError('inert reviewed-plan inspection finished')
        self.assertEqual(self.worker(arm=armed), 1, self.report().get('error'))
        self.assertEqual(inspected, [True], self.report().get('error'))
        self.assertEqual(self.report()['error'], 'inert reviewed-plan inspection finished')
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertFalse((self.folder / 'READY-TO-RESUME.json').exists())
        self.assertTrue(self.report()['cleanupVerified'])

    def assert_reviewed_file_corruption_refused(self, plan, path, *, common=True):
        """Both shared evidence paths must reject changed bytes, including unchanged JSON meaning."""
        path = Path(path)
        raw, stamp = path.read_bytes(), path.stat()
        try:
            path.write_bytes(raw + b'\n')
            verifiers = (trial.verify_plan_evidence, trial.verify_reviewed_plan) if common else (trial.verify_reviewed_plan,)
            for verify in verifiers:
                with self.subTest(file=str(path), verifier=verify.__name__):
                    with self.assertRaises(ValueError):
                        verify(plan, self.folder)
        finally:
            path.write_bytes(raw)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    def test_reviewed_arm_has_one_final_fresh_preparation_replay(self):
        """The real ARM call retains its last full replay before any plan or ARM is published."""
        self.capture_and_pause()
        self.prepare()
        observed = []
        def armed(ready):
            """Count only this API call; independent worker admission remains outside the patch."""
            with patch.object(trial, 'verify_reviewed_preparation', wraps=trial.verify_reviewed_preparation) as full:
                self.arm(ready)
            observed.append(full.call_count)
            self.assertEqual(full.call_count, 1)
            self.assertTrue((self.folder / 'plan.json').exists())
            self.assertTrue((self.folder / 'ARM.json').exists())
            raise ValueError('inert ARM replay count finished')
        self.assertEqual(self.worker(arm=armed), 1)
        self.assertEqual(observed, [1], self.report().get('error'))
        self.assertEqual(self.report()['error'], 'inert ARM replay count finished')
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))

    def assert_arm_construction_mutation_refused(self, mutate, message):
        """Change synthetic evidence during pure plan construction, immediately before the retained replay."""
        self.capture_and_pause()
        self.prepare()
        original_scope_fields = trial.scope_fields
        changes = []
        def changed(scope):
            """The scope hook models a concurrent change without replacing the actual verifier."""
            result = original_scope_fields(scope)
            mutate()
            changes.append(True)
            return result
        def armed(ready):
            """Keep the mutation inside this ARM call and let the real worker preserve its failure."""
            with patch.object(trial, 'scope_fields', side_effect=changed):
                self.arm(ready)
        self.assertEqual(self.worker(arm=armed), 1)
        self.assertEqual(changes, [True], self.report().get('error'))
        self.assertRegex(self.report()['error'], message)
        self.assertTrue((self.folder / 'ARM-REQUESTED.json').exists())
        self.assertFalse((self.folder / 'plan.json').exists())
        self.assertFalse((self.folder / 'ARM.json').exists())
        self.assertFalse((self.folder / 'READY-TO-RESUME.json').exists())
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))

    def test_reviewed_arm_final_replay_refuses_changed_source_bytes(self):
        """Removing the earlier replay cannot admit a current source changed before final verification."""
        def mutate():
            """Change only this fixture's unimported source copy."""
            self.code.write_bytes(self.code.read_bytes() + b'\n')
        self.assert_arm_construction_mutation_refused(mutate, 'Source bytes changed')

    def test_reviewed_arm_final_replay_refuses_foreign_preparation_snapshot(self):
        """A substituted preparation cannot reuse the earlier ready witness or the in-memory plan."""
        def mutate():
            """Keep the JSON well formed but replace its exact original owner identity."""
            value = json.loads(self.plan_path.read_bytes())
            value['owner']['child']['processId'] += 1
            self.plan_path.write_bytes(canonical(value))
        self.assert_arm_construction_mutation_refused(mutate, 'Prepared worker identity or authority changed')

    def test_reviewed_arm_final_replay_keeps_stop_after_plan_construction(self):
        """A STOP arriving between the early liveness check and final replay still prevents publication."""
        self.assert_arm_construction_mutation_refused(
            lambda: (self.folder / 'STOP').write_text('inert stop', encoding='utf-8'), 'was stopped')

    def test_reviewed_arm_final_replay_keeps_original_scene_expiry(self):
        """The original scene clock is never reset when in-memory construction consumes its budget."""
        def expire():
            """Advance only the existing fixture clock past its original scene deadline."""
            self.clock_offset = self.preparation['pausedReview']['chain']['originalSceneDeadlineClientNs'] + 1 - self.qpc_ns
        self.assert_arm_construction_mutation_refused(expire, 'Native reviewed scene is stale or future-dated')

    def test_reviewed_plan_uses_one_complete_preparation_replay(self):
        """Only this exact paused format skips duplicate common I/O; its complete verifier still runs."""
        def inspect(plan):
            with patch.object(trial, 'verify_reviewed_preparation', wraps=trial.verify_reviewed_preparation) as full, \
                    patch.object(trial, 'verify_plan_evidence', side_effect=AssertionError('duplicate common replay')) as common:
                self.assertEqual(trial.verify_reviewed_plan(plan, self.folder), plan['binding'])
            self.assertEqual(full.call_count, 1)
            common.assert_not_called()
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_keeps_original_owner_goal_and_checkpoint_refusals(self):
        """The surviving complete replay retains identity, fixed-goal and checkpoint-stamp admission."""
        def inspect(plan):
            for path in (self.owner_file, self.goal, self.checkpoint):
                self.assert_reviewed_file_corruption_refused(plan, path)
            foreign = copy.deepcopy(fixtures.OWNER)
            foreign['child']['processId'] += 1
            with patch.object(trial, 'load_map_owner', return_value=foreign):
                for verify in (trial.verify_plan_evidence, trial.verify_reviewed_plan):
                    with self.subTest(verifier=verify.__name__), self.assertRaisesRegex(ValueError, 'owner evidence changed'):
                        verify(plan, self.folder)
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_keeps_current_and_archived_runtime_refusals(self):
        """A changed interpreter or its retained counterpart cannot use the shared preparation proof."""
        def inspect(plan):
            for original, archived in plan['workerRuntime']['retained'].items():
                self.assert_reviewed_file_corruption_refused(plan, original)
                self.assert_reviewed_file_corruption_refused(plan, archived)
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_keeps_exact_source_bytes_and_census(self):
        """Current/archive source corruption and an additional importable module remain refusals."""
        def inspect(plan):
            for name in ('tools/bettergi-agent/combat_trial.py', 'tools/quest-pilot/controller-control.py'):
                self.assert_reviewed_file_corruption_refused(plan, self.root / name)
                self.assert_reviewed_file_corruption_refused(plan, self.folder / 'source-snapshot' / name)
            extra = self.code.with_name('unexpected_local_import.py')
            try:
                extra.write_bytes(b'raise AssertionError("must never be imported")\n')
                for verify in (trial.verify_plan_evidence, trial.verify_reviewed_plan):
                    with self.subTest(verifier=verify.__name__), self.assertRaisesRegex(ValueError, 'Source inventory changed'):
                        verify(plan, self.folder)
            finally:
                extra.unlink()
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_keeps_all_original_and_archived_review_evidence(self):
        """Every separately reviewed image, scene, sidecar, goal and review stays byte-bound."""
        def inspect(plan):
            for record in plan['evidence'].values():
                self.assert_reviewed_file_corruption_refused(plan, record['path'])
                self.assert_reviewed_file_corruption_refused(plan, record['retained'])
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_keeps_both_pause_proofs_and_capture_chain(self):
        """The complete preparation still independently replays both historical UI proofs and their chain."""
        def inspect(plan):
            for record in (self.preparation['pause'], self.preparation['pausedReview']['baselinePause']):
                original = str(Path(record['directory']) / 'after.json')
                self.assert_reviewed_file_corruption_refused(plan, original, common=False)
                self.assert_reviewed_file_corruption_refused(plan, record['retained'][original], common=False)
            for record in self.preparation['pausedReview']['records'].values():
                self.assert_reviewed_file_corruption_refused(plan, record['path'], common=False)
                self.assert_reviewed_file_corruption_refused(plan, record['retained'], common=False)
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_refuses_substitution_before_shared_replay(self):
        """The optimization applies only after exact preparation, scope, policy and phase-link equality."""
        def inspect(plan):
            replacements = {name: None for name in proof.COMMON_PLAN_FIELDS}
            replacements.update(version=True, kind='combat-trial-plan-v1', combatScope='single-enemy-v1',
                maximumEnemyBarCandidates=3, maximumHostSeconds=91, maximumReviewAgeSeconds=121,
                recordingMaximumBytes=160 * 1024 * 1024 + 1, policy={}, binding={}, evidence={},
                preparedPolicy={}, pausedReview={})
            for name, value in replacements.items():
                changed = copy.deepcopy(plan)
                changed[name] = value
                with self.subTest(field=name), \
                        patch.object(trial, 'verify_reviewed_preparation', side_effect=AssertionError('equality was bypassed')):
                    with self.assertRaises(ValueError):
                        trial.verify_reviewed_plan(changed, self.folder)
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_keeps_original_stop_and_scene_deadline(self):
        """Removing duplicate immutable reads cannot renew the source clock or ignore a current STOP."""
        def inspect(plan):
            stop = self.folder / 'STOP'
            try:
                stop.write_text('inert stop', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'was stopped'):
                    trial.verify_reviewed_plan(plan, self.folder)
            finally:
                stop.unlink()
            offset = self.clock_offset
            try:
                self.clock_offset = self.preparation['pausedReview']['chain']['originalSceneDeadlineClientNs'] + 1 - self.qpc_ns
                with self.assertRaisesRegex(ValueError, 'Native reviewed scene is stale or future-dated'):
                    trial.verify_reviewed_plan(plan, self.folder)
            finally:
                self.clock_offset = offset
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_reviewed_plan_preserves_canonical_binding_types(self):
        """Python-equal boolean/integer/float substitutions still differ from the exact reviewed binding."""
        def inspect(plan):
            mutations = (('goalFrozen', 1), ('retryAllowed', 0), ('maximumOutstandingActions', True))
            candidates = []
            for key, value in mutations:
                changed = copy.deepcopy(plan)
                changed['binding']['policy'][key] = value
                candidates.append((key, changed))
            changed = copy.deepcopy(plan)
            changed['binding']['inspectedVisibleEnemyCount'] = float(plan['binding']['inspectedVisibleEnemyCount'])
            candidates.append(('inspectedVisibleEnemyCount', changed))
            for field, changed in candidates:
                self.assertEqual(changed['binding'], plan['binding'])
                self.assertNotEqual(canonical(changed['binding']), canonical(plan['binding']))
                for verify in (trial.verify_plan_evidence, trial.verify_reviewed_plan):
                    with self.subTest(field=field, verifier=verify.__name__), self.assertRaises(ValueError):
                        verify(changed, self.folder)
        self.inspect_reviewed_plan_before_resume(inspect)

    def test_original_baseline_is_not_replaced_by_later_pause_health(self):
        """Normal damage after capture cannot reverse the original-baseline no-increase comparison."""
        self.capture_and_pause(later_pause_health=self.baseline_health - 500)
        self.prepare()
        self.assertEqual(self.preparation['pausedReview']['chain']['baselineHealth'], self.baseline_health)
        self.assertNotEqual(self.preparation['pause']['directory'], self.preparation['pausedReview']['baselinePause']['directory'])
        self.assertEqual(self.worker(), 0, self.report())

    def test_actual_review_before_paired_pause_is_refused_without_loading(self):
        """A later file write cannot turn a pre-pause human timestamp into a paused review."""
        self.capture_and_pause()
        review = json.loads(self.evidence['review'].read_bytes())
        review['reviewedAtUnixNs'] = self.request['createdAtUnixNs']
        self.evidence['review'].write_bytes(canonical(review))
        with self.assertRaisesRegex(ValueError, 'review preceded'):
            self.prepare()
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_long_human_wait_expires_original_scene_before_model_or_worker_claim(self):
        """Human review may occur while paused but cannot renew the 120-second source clock."""
        self.capture_and_pause()
        self.clock_offset += 121_000_000_000
        review = json.loads(self.evidence['review'].read_bytes())
        review['reviewedAtUnixNs'] = time.time_ns()
        self.evidence['review'].write_bytes(canonical(review))
        with self.assertRaisesRegex(ValueError, 'Native reviewed scene is stale'):
            self.prepare()
        self.assertFalse(self.plan_path.exists())
        self.assertEqual((self.loads, self.lifecycle.starts), (0, 0))

    def test_source_changed_after_paused_precheck_still_prevents_the_only_listener(self):
        """A held original source cannot be rewritten after the paused precheck or start a listener on error."""
        self.capture_and_pause()
        self.prepare()
        original_bytes = self.code.read_bytes()
        blocked_writes = []
        def resumed_then_changed(ready):
            """Change one exact original source only after a valid final native resume is retained."""
            self.resume(ready)
            try:
                self.code.write_bytes(b'changed after precheck')
            except PermissionError as error:
                blocked_writes.append(str(error))
                raise
        self.assertEqual(self.worker(resume=resumed_then_changed), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertEqual(blocked_writes, [self.report()['error']])
        self.assertEqual(self.code.read_bytes(), original_bytes)
        self.assertTrue(self.report()['cleanupVerified'])


    def test_review_changed_after_paused_precheck_is_caught_by_fresh_byte_hashes(self):
        """Already-replayed original review bytes remain write-protected until worker cleanup."""
        self.capture_and_pause()
        self.prepare()
        original_bytes = self.evidence['review'].read_bytes()
        blocked_writes = []
        def resumed_then_changed(ready):
            """Keep the JSON meaning but change the exact separately authored review artifact."""
            self.resume(ready)
            try:
                with self.evidence['review'].open('ab') as stream:
                    stream.write(b'\n')
            except PermissionError as error:
                blocked_writes.append(str(error))
                raise
        self.assertEqual(self.worker(resume=resumed_then_changed), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertEqual(blocked_writes, [self.report()['error']])
        self.assertEqual(self.evidence['review'].read_bytes(), original_bytes)


    def test_stop_during_starting_status_write_remains_an_unattempted_native_start(self):
        """A blocking final status publication is followed by original liveness before issuing any start command."""
        self.capture_and_pause()
        self.prepare()
        original = trial.runtime.ResidentControl.publish
        def publish(control, *args, **kwargs):
            """Deliver a file-only STOP exactly when the final starting status finishes writing."""
            result = original(control, *args, **kwargs)
            if kwargs.get('state') == 'starting':
                trial.request_stop(self.folder, self.preparation, 'inert-stop-during-start-status')
            return result
        with patch.object(trial.runtime.ResidentControl, 'publish', publish):
            self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertFalse(report['nativeStartAttempted'])
        self.assertEqual(report['nativeStartOutcome'], 'notAttempted')
        self.assertTrue(report['cleanupVerified'])

    def test_source_expiry_during_model_load_stops_while_paused(self):
        """Even a successfully loaded model cannot publish final-resume readiness for an expired image."""
        self.capture_and_pause()
        self.prepare()
        self.load_action = lambda _policy: setattr(self, 'clock_offset', self.clock_offset + 121_000_000_000)
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertFalse((self.folder / 'READY-TO-RESUME.json').exists())
        self.assertIn('stale', self.report()['error'].lower())

    def test_exact_dynamic_transport_is_snapshotted_and_rechecked_after_precheck(self):
        """Seal only the known dynamic transport and deny its later mutation before native start."""
        transport = self.root / 'tools/quest-pilot/controller-control.py'
        unrelated = transport.with_name('unrelated.py')
        unrelated.write_bytes(b'not a transitive import')
        self.capture_and_pause()
        self.prepare()
        key = 'tools/quest-pilot/controller-control.py'
        self.assertEqual(self.preparation['sourceFiles'][key], trial.digest(transport.read_bytes()))
        self.assertEqual((self.folder / 'source-snapshot' / key).read_bytes(), transport.read_bytes())
        self.assertNotIn('tools/quest-pilot/unrelated.py', self.preparation['sourceFiles'])
        original_bytes = transport.read_bytes()
        blocked_writes = []
        def resumed_then_changed(ready):
            """Mutation occurs after all paused source checks, without touching any real transport."""
            self.resume(ready)
            try:
                transport.write_bytes(b'changed dynamic transport')
            except PermissionError as error:
                blocked_writes.append(str(error))
                raise
        self.assertEqual(self.worker(resume=resumed_then_changed), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (1, 0, 0))
        self.assertEqual(blocked_writes, [self.report()['error']])
        self.assertEqual(transport.read_bytes(), original_bytes)


    def test_legacy_plan_loader_refuses_new_phase_records(self):
        """The old post-resume contract cannot silently consume this different ordering."""
        self.capture_and_pause()
        self.prepare()
        self.assertEqual(self.worker(), 0, self.report())
        with self.assertRaises(ValueError):
            trial.load_plan(self.folder / 'plan.json')

    def test_stop_during_final_owner_discovery_prevents_native_start(self):
        """A blocking owner read cannot hide a STOP that arrived after the final source checks."""
        self.capture_and_pause()
        self.prepare()
        def resume_then_discovery_stop(ready):
            """Inject STOP only on the next original-owner read, after valid final resume publication."""
            self.resume(ready)
            original = self.lifecycle.discover
            def discover():
                """Return valid identity while retaining the concurrently delivered stop."""
                value = original()
                trial.request_stop(self.folder, self.preparation, 'inert-stop-during-owner-read')
                return value
            self.lifecycle.discover = discover
        self.assertEqual(self.worker(resume=resume_then_discovery_stop), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertTrue(self.report()['cleanupVerified'])
        self.assertFalse((self.folder / 'FINAL-ADMISSION.json').exists())

    def test_changed_child_nonce_after_precheck_is_not_retired_as_original_owner(self):
        """A changed endpoint cannot authorize input or falsely confirm original-owner cleanup."""
        self.capture_and_pause()
        self.prepare()
        def resume_then_changed_owner(ready):
            """The valid historical proof does not replace a fresh current-owner comparison."""
            self.resume(ready)
            self.lifecycle.child['instanceNonce'] = 'foreign-child'
        self.assertEqual(self.worker(resume=resume_then_changed_owner), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertEqual(self.report()['status'], 'unresolved')
        self.assertFalse(self.report()['cleanupVerified'])

    def test_foreign_early_resume_proof_cannot_replace_post_precheck_escape(self):
        """Even a structurally complete resume must come after the actual worker's final paused readiness."""
        self.capture_and_pause()
        self.prepare()
        def arm_with_prior_resume(ready):
            """Create inert early evidence, never actual UI input, before arming the waiting worker."""
            self.clock_offset += 500_000_000
            self.early_resume = fixtures.ui_transition_fixture(self, 'resume', '-early')
            self.arm(ready)
        def submit_early_resume(_ready):
            """Publication now cannot renew the earlier native request's time."""
            trial.record_reviewed_resume(self.plan_path, self.early_resume)
        self.assertEqual(self.worker(arm=arm_with_prior_resume, resume=submit_early_resume), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertIn('preceded readiness', self.report()['error'])
        self.assertTrue((self.folder / 'resume-candidate.json').exists())
        self.assertFalse((self.folder / 'RESUMED.json').exists())

    def test_existing_ready_file_cannot_construct_worker_capability(self):
        """A disk marker from another attempt is refused before the model or listener exists."""
        self.capture_and_pause()
        self.prepare()
        trial.exclusive_json(self.folder / 'READY-TO-RESUME.json', dict(inputEnabled=False, state='precheckedPaused'))
        self.assertEqual(self.worker(), 1)
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (0, 0, 0))

    def test_original_worker_qpc_budget_cannot_restart_at_final_resume(self):
        """The unchanged ninety-second worker limit remains independent of the longer scene budget."""
        self.capture_and_pause()
        self.prepare()
        def resume_then_expire_worker(ready):
            """Keep the source below120 seconds but advance beyond the original worker's90 seconds."""
            self.resume(ready)
            self.clock_offset = ready['hostClaim']['startedAtClientNs'] + 90_000_000_001 - self.qpc_ns
        self.assertEqual(self.worker(resume=resume_then_expire_worker), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertIn('worker budget expired', self.report()['error'])

    def test_original_source_expiry_wins_before_longer_worker_budget(self):
        """Review consumes existing source lifetime, and final resume never resets it."""
        self.capture_and_pause()
        self.clock_offset += 45_000_000_000
        review = json.loads(self.evidence['review'].read_bytes())
        review['reviewedAtUnixNs'] = time.time_ns()
        self.evidence['review'].write_bytes(canonical(review))
        self.prepare()
        def resume_then_expire_source(ready):
            """Advance to the original source boundary while the worker still has time left."""
            self.resume(ready)
            self.clock_offset = ready['originalSceneDeadlineClientNs'] + 1 - self.qpc_ns
        self.assertEqual(self.worker(resume=resume_then_expire_source), 1)
        self.assertEqual((self.lifecycle.starts, self.episodes), (0, 0))
        self.assertIn('scene or review budget expired', self.report()['error'])


    def test_stop_during_loading_publication_prevents_model_and_listener(self):
        """A STOP delivered by the last pre-load status write must avoid even the cold GPU load."""
        self.capture_and_pause()
        self.prepare()
        original = trial.runtime.ResidentControl.publish
        def publish(control, *args, **kwargs):
            """Retain the status and then deliver an independent file-only stop."""
            result = original(control, *args, **kwargs)
            if kwargs.get('state') == 'loading':
                trial.request_stop(self.folder, self.preparation, 'inert-stop-during-loading-status')
            return result
        with patch.object(trial.runtime.ResidentControl, 'publish', publish):
            self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual((self.loads, self.lifecycle.starts, self.episodes), (0, 0, 0))
        self.assertEqual((report['modelLoadAttempts'], report['modelLoads'], report['modelLoadSeconds']), (0, 0, 0))
        self.assertNotIn('finishedAtUnixNs', report['modelPreparation'])
        self.assertTrue(report['cleanupVerified'])

    def test_original_expiry_during_loading_publication_prevents_model(self):
        """The source clock can expire during a blocking status write without authorizing a late load."""
        self.capture_and_pause()
        self.prepare()
        original = trial.runtime.ResidentControl.publish
        def publish(control, *args, **kwargs):
            """Advance only the fixture QPC/Unix pair after the real local publication."""
            result = original(control, *args, **kwargs)
            if kwargs.get('state') == 'loading':
                self.clock_offset = self.preparation['pausedReview']['chain']['originalSceneDeadlineClientNs'] + 1 - self.qpc_ns
            return result
        with patch.object(trial.runtime.ResidentControl, 'publish', publish):
            self.assertEqual(self.worker(), 1)
        report = self.report()
        self.assertEqual((self.loads, self.lifecycle.starts, report['modelLoadAttempts']), (0, 0, 0))
        self.assertIn('budget expired', report['error'])
        self.assertTrue(report['cleanupVerified'])


class PrivatePrecheckTests(unittest.TestCase):
    """Exercise one-use private authority without files, processes or synthetic native operations."""
    def test_private_inputs_are_detached_and_consumption_cannot_be_replayed(self):
        """Changing a caller-owned object cannot mutate the sealed in-memory plan or hash census."""
        inputs = {'an-original-artifact': '1' * 64}
        ready = dict(verifiedInputsSha256=proof.sha(canonical(inputs)))
        plan = dict(policy=dict(maximumActions=3))
        authority = proof.PrecheckedAdmission(plan, ready, '2' * 64, inputs)
        plan['policy']['maximumActions'] = 99
        inputs['an-original-artifact'] = '3' * 64
        self.assertEqual(authority.plan['policy']['maximumActions'], 3)
        with self.assertRaisesRegex(ValueError, 'immutable inputs changed'):
            authority.compare(inputs)
        authority.compare({'an-original-artifact': '1' * 64})
        authority.consume()
        with self.assertRaisesRegex(ValueError, 'already consumed'):
            authority.consume()
        with self.assertRaisesRegex(ValueError, 'immutable inputs changed'):
            authority.compare({'an-original-artifact': '1' * 64})

    def test_new_protocol_version_does_not_accept_boolean_alias(self):
        """Keep the new opt-in schema distinct even under Python's bool/int equality."""
        self.assertFalse(proof.version_one(dict(version=True)))
        self.assertTrue(proof.version_one(dict(version=1)))




class GroundPausedReviewTests(unittest.TestCase):
    """Qualify the explicit profile through actual preparation/ARM APIs, with inert native/model resources."""
    loader=PausedReviewTrialTests.loader
    identity=PausedReviewTrialTests.identity
    report=PausedReviewTrialTests.report
    configure_group_review=PausedReviewTrialTests.configure_group_review
    capture_and_pause=PausedReviewTrialTests.capture_and_pause
    arm=PausedReviewTrialTests.arm
    resume=PausedReviewTrialTests.resume
    worker=PausedReviewTrialTests.worker
    probe=PausedReviewTrialTests.probe

    def setUp(self):
        """Reuse original UI/provenance fixtures, adding only an explicit independently reviewed ground scene."""
        from test_combat_trial_guard import ground_review_parts
        PausedReviewTrialTests.setUp(self)
        parts=ground_review_parts()
        self.assertEqual(trial.digest(parts[-1]),trial.GOAL_SHA256)
        parts[0].update(inspectedHealth=self.baseline_health,inspectedMaximumHealth=self.maximum_health)
        for name,value in zip(trial.EVIDENCE_NAMES[:-1],parts[:-1]):
            self.evidence[name].write_bytes(value if isinstance(value,bytes) else canonical(value))

    def fresh_scene(self):
        """Move all original source clocks by one fixed offset, preserving stable-sample identity/order."""
        self.clock_offset+=500_000_000
        scene=json.loads(self.evidence['scene'].read_bytes())
        selected=next(row for row in scene['observations'] if row['frameId']==scene['qualifiedImageFrameId'])
        offset=time.perf_counter_ns()//100-1_100_000-selected['sourceFrame']['timestamp100ns']
        def advance(value):
            """Preserve exact repeated frame/source joins while making the last stable sample already past."""
            if isinstance(value,dict):
                for key,item in value.items():
                    if key=='timestamp100ns':value[key]+=offset
                    else:advance(item)
            elif isinstance(value,list):
                for item in value:advance(item)
        for name in ('review','plan','scene','sidecar'):
            value=json.loads(self.evidence[name].read_bytes());advance(value)
            if name=='review':value['reviewedAtUnixNs']=time.time_ns()
            self.evidence[name].write_bytes(canonical(value))

    def prepare(self, *, claim=True, ground_combat=True, source_stale_recovery=False):
        """Select the fixed profile explicitly; no flag is inferred from image contents."""
        self.preparation=trial.prepare_reviewed_paused(self.folder,self.owner_file,
            self.capture_folder/'paired-pause.json',self.evidence,ground_combat=ground_combat,
            source_stale_recovery=source_stale_recovery)
        self.plan=self.preparation
        if claim:
            now=time.monotonic_ns()
            trial.exclusive_json(self.folder/'CONSUMED.json',dict(runId=self.preparation['runId'],
                planSha256=trial.digest(self.plan_path.read_bytes()),startedMonotonicNs=now,
                startedAtUnixNs=time.time_ns(),startedAtClientNs=time.perf_counter_ns(),deadlineMonotonicNs=now+90_000_000_000))
        return self.preparation

    def episode(self,args,policy,control):
        """Inspect actual prepared arguments; detailed receipts are covered by the separate real stream/audit cases."""
        from combat_trial_guard import GROUND_PROFILE
        from navigation_profiles import SCOUT_PROFILE
        self.episodes+=1;self.last_episode_args=args
        self.assertEqual((args.history,args.fps,args.decision_hz,args.seconds,args.action_hold_ms),(41,20,10,5,50))
        self.assertEqual((args.max_input_actions,args.input_keys),(20,'W,A,S,D,LBUTTON'))
        self.assertEqual((args.navigation_guidance,args.navigation_profile,args.require_ground_control_layout),(True,SCOUT_PROFILE,True))
        self.assertEqual((args.combat_trial_control_profile,policy.combat_trial_control_profile),(GROUND_PROFILE,GROUND_PROFILE))
        self.assertLessEqual(args.lease_deadline-time.monotonic(),5)
        native=dict(status='completed',endReason='combatGroundWindowDrained',combatTrialGuard=copy.deepcopy(self.plan['binding']),
            combatTrialGuardState=dict(phase='complete',trialComplete=True,trip=None,acceptedActions=0,
                completedActions=0,completed=[],pending=None,armed=False),acceptedInputActions=0,decisions=[],framesReceived=5,
            recording=dict(error=None,closed=True,complete=True,lossless=True,workerRetired=True,
                droppedFrames=0,droppedEvents=0,droppedObservations=0,abandonedFrames=0,encodedFrames=5,
                recordedObservations=5,policyRgbEnabled=True,policyRgbFrames=5,policyRgbBytes=5*trial.RGB192_BYTES),
            stop=dict(type='stopped',heldKeys=[],active=None))
        self.lifecycle.child.update(taskRunning=False,agentStreamRunning=False)
        Path(args.record_dir).mkdir()
        for index in range(5):(Path(args.record_dir)/f'retained-{index}.rgb').write_bytes(bytes(trial.RGB192_BYTES))
        Path(args.output).write_bytes(canonical(native));return 0

    def test_ground_flag_is_explicit_and_cli_preserves_separate_recovery_selection(self):
        """A reviewed profile or a flag alone cannot change the default trial."""
        self.capture_and_pause()
        with self.assertRaisesRegex(ValueError,'explicitly selected'):self.prepare(ground_combat=False)
        self.assertFalse(self.folder.exists())
        argv=['prepare-reviewed-paused','--directory',str(self.folder),'--owner-from',str(self.owner_file),
            '--paired-pause',str(self.capture_folder/'paired-pause.json'),'--ground-combat']
        for name,value in self.evidence.items():
            argv+=['--native-plan' if name=='plan' else '--native-scene' if name=='scene' else '--'+name,str(value)]
        with patch.object(trial,'prepare_reviewed_paused',return_value=dict(runId='a'*32)) as prepare:
            self.assertEqual(trial.main(argv),0)
            self.assertIs(prepare.call_args.kwargs['ground_combat'],True)
            self.assertIs(prepare.call_args.kwargs['source_stale_recovery'],False)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(0,0,0))

    def test_profile_50ms_config_survives_real_prepare_arm_precheck_and_worker(self):
        """The model generation/configuration path selects50ms before loading; raw outputs stay untouched."""
        from combat_trial_guard import GROUND_PROFILE
        self.capture_and_pause();self.prepare()
        self.assertEqual(trial.load_reviewed_preparation(self.plan_path)[0],self.preparation)
        self.assertEqual(trial.verify_reviewed_preparation(self.preparation,self.folder),self.preparation['reviewedCombat']['binding'])
        self.assertEqual(self.preparation['modelConfiguration']['holdMs'],50)
        self.assertEqual(self.worker(),0,self.report().get('error'))
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(1,1,1))
        self.assertEqual((self.last_args.action_hold_ms,self.last_args.max_input_actions,self.last_args.enable_input),(50,0,False))
        self.assertFalse(hasattr(self.last_args,'combat_trial_binding'))
        self.assertEqual(self.last_policy.combat_trial_control_profile,GROUND_PROFILE)
        self.assertEqual(self.plan['policy']['maximumActions'],20)
        self.assertEqual(self.plan['binding'],self.preparation['reviewedCombat']['binding'])
        self.assertTrue(self.report()['cleanupVerified'])

    def test_preparation_substitution_refuses_without_model_or_native_start(self):
        """Rehashing outer JSON cannot silently change the selected policy or50ms configuration."""
        self.capture_and_pause();self.prepare()
        for mutate in (lambda x:x['modelConfiguration'].update(holdMs=100),
            lambda x:x['reviewedCombat']['binding'].pop('controlProfile'),
            lambda x:x['reviewedCombat']['binding']['policy'].update(sourceStaleRecoveryPolicy={})):
            changed=copy.deepcopy(self.preparation);mutate(changed)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                trial.verify_reviewed_preparation(changed,self.folder)
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(0,0,0))

    def test_legacy_direct_entry_and_stale_recovery_cannot_adopt_ground_profile(self):
        """This first profile is paused-review-only and grants no stale-source recovery authority."""
        self.capture_and_pause()
        with self.assertRaisesRegex(ValueError,'reviewed-paused'):
            trial.prepare(self.live/'legacy-ground-refused',self.owner_file,self.evidence,scope=FOUR_SCOPE)
        with self.assertRaises(ValueError):self.prepare(source_stale_recovery=True)
        self.assertFalse(self.folder.exists())
        self.assertEqual((self.loads,self.lifecycle.starts,self.episodes),(0,0,0))


if __name__ == '__main__':
    unittest.main()
