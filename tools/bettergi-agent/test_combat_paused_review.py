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

    def prepare(self, *, claim=True):
        """Create the reviewed zero-input preparation only after actual paused review."""
        self.preparation = trial.prepare_reviewed_paused(self.folder, self.owner_file,
            self.capture_folder / 'paired-pause.json', self.evidence)
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


if __name__ == '__main__':
    unittest.main()
