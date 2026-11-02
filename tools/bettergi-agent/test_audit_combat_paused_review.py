"""Archive-only replay and mutation cases for the explicit paused-review combat protocol."""
import copy
import hashlib
import tempfile
from contextlib import nullcontext
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import audit_combat_trial as audit
import combat_paused_review_proof as proof
import combat_trial as trial
from combat_trial_guard import canonical
import test_combat_paused_review as lifecycle_fixtures
from test_combat_trial import FakeWatch


class PausedReviewAuditTests(unittest.TestCase):
    """Use production artifact writers and fake native/model dependencies, never a live session."""
    def produce(self, mode='complete'):
        """Create one ordinary inert worker with a complete or deliberately interrupted new handoff."""
        fixture = lifecycle_fixtures.PausedReviewTrialTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        # The full no-listener auditor requires exact current replay implementations.
        for name in ('combat_trial.py', 'combat_trial_guard.py', 'stream_client.py', 'native_combat.py',
                     'model_adapters.py', 'resident_runtime.py', 'episode_split.py', 'combat_pause_proof.py',
                     'combat_process_identity.py', 'combat_paused_review_proof.py', 'combat_paused_file_admission.py'):
            (fixture.root / 'tools/bettergi-agent' / name).write_bytes(Path(__file__).with_name(name).read_bytes())
        fixture.capture_and_pause()
        fixture.prepare(claim=False)
        def stop_ready(_ready):
            """Retire before any resume helper or attack listener can be invoked."""
            trial.request_stop(fixture.folder, fixture.preparation, 'inert-stop-before-resume')
        def stop_arm(ready):
            """Publish one exact ARM but stop before its worker consumes it."""
            fixture.arm(ready)
            trial.request_stop(fixture.folder, fixture.preparation, 'inert-stop-after-arm-publication')
        def failed_model(_policy):
            """A failed inert prewarm leaves its positive input-free loading probe intact."""
            raise RuntimeError('inert model preparation failure')
        if mode == 'loadFailure':
            fixture.load_action = failed_model
        elif mode == 'postLoadFailure':
            fixture.load_action = lambda policy: policy.metadata.update(precision='invalid-inert-policy')
        elif mode == 'beforeModel':
            def failed_probe(*_args):
                """Fail the inert pre-load probe before any model intent or attempt exists."""
                raise RuntimeError('inert probe failure before model intent')
            fixture.probe = failed_probe
        fixture.lifecycle.runner = lambda: fixture.worker(
            arm=stop_arm if mode == 'unconsumedArm' else None,
            resume=stop_ready if mode == 'precheckedStop' else None)
        original_publish = trial.runtime.ResidentControl.publish
        def loading_stop(control, *args, **kwargs):
            """Exercise actual cancellation between the load intent and the first attempted model call."""
            value = original_publish(control, *args, **kwargs)
            if kwargs.get('state') == 'loading':
                trial.request_stop(fixture.folder, fixture.preparation, 'inert-load-intent-stop')
            return value
        context = patch.object(trial.runtime.ResidentControl, 'publish', loading_stop) if mode == 'loadIntentStop' else nullcontext()
        with context:
            code = trial.launch(fixture.plan_path, lifecycle=fixture.lifecycle, watch_factory=FakeWatch, reviewed_paused=True)
        self.assertEqual(code, 0 if mode == 'complete' else 1, fixture.report().get('error'))
        self.fixture, self.folder, self.wrapper = fixture, fixture.folder, fixture.report()
        self.plan = self.document('plan.json') if (self.folder / 'plan.json').exists() else None
        return fixture

    def document(self, name):
        """Read one original phase artifact without normalizing its recorded bytes."""
        return json.loads((self.folder / name).read_bytes())

    def chain(self, *, documents=None, wrapper=None, require_admission=True):
        """Run the same separate phase replay used before actual native-episode audit."""
        return audit.verify_reviewed_preparation_chain(self.folder, self.plan, wrapper or self.wrapper,
                                                       documents or self.document, require_admission=require_admission)

    def test_exact_new_chain_and_ordinary_retirement_replay(self):
        """Pre-resume nativeScene authority is valid only after the entire differently versioned chain."""
        self.produce()
        result = self.chain()
        self.assertTrue(result['finalAdmissionVerified'])
        self.assertEqual(result['lastVerifiedPhase'], 'finalAdmission')
        audit.verify_retirement(self.plan, self.wrapper, self.document('result.json'), self.document('broker.json'),
            self.document('CONSUMED.json'), self.document('WORKER-CONSUMED.json'),
            audit.digest((self.folder / 'patrol.json').read_bytes()))

    def test_archive_replay_does_not_read_mutable_native_or_scene_originals(self):
        """Retained UI, review, model-ready and process bytes suffice after outside originals disappear."""
        fixture = self.produce()
        before = self.chain()
        original_names = set()
        preparation, ready, resumed = (self.document(name) for name in ('preparation.json', 'prepared.json', 'RESUMED.json'))
        for record in (preparation['pause'], preparation['pausedReview']['baselinePause'],
                       ready['modelPreparation']['inventoryProbe'], resumed['resume']):
            original_names.update(record['proof']['files'])
        for records in (preparation['reviewedCombat']['evidence'], preparation['pausedReview']['records']):
            original_names.update(record['path'] for record in records.values())
        for name in original_names:
            path = Path(name).resolve()
            self.assertTrue(path.is_relative_to(fixture.root))
            if not path.is_relative_to(self.folder):
                path.unlink(missing_ok=True)
        self.assertEqual(self.chain(), before)

    def test_precheck_cannot_precede_its_exact_arm_even_with_other_joins_unchanged(self):
        """The new phase's own ordering is checked, independently of later resume hash references."""
        self.produce()
        value = self.document('READY-TO-RESUME.json')
        value['checkedAtClientNs'] = self.document('ARM.json')['createdAtClientNs'] - 1
        with self.assertRaisesRegex(ValueError, 'precheck changed inputs or chronology'):
            self.chain(documents=lambda name: value if name == 'READY-TO-RESUME.json' else self.document(name))

    def test_manifest_cannot_omit_one_original_and_reseal_its_declared_digest(self):
        """Rebuild the expected census from all phases instead of trusting a self-consistent short list."""
        self.produce()
        inputs = self.document('prechecked-inputs.json')
        inputs.pop(self.plan['evidence']['review']['path'])
        prechecked = self.document('READY-TO-RESUME.json')
        prechecked['verifiedInputsSha256'] = audit.digest(canonical(inputs))
        def changed(name):
            """Substitute a resealed short census without changing the immutable underlying proof phases."""
            return inputs if name == 'prechecked-inputs.json' else prechecked if name == 'READY-TO-RESUME.json' else self.document(name)
        with self.assertRaisesRegex(ValueError, 'precheck changed inputs or chronology'):
            self.chain(documents=changed)

    def test_final_admission_cannot_renew_original_source_deadline(self):
        """A matching wrapper/admission timestamp beyond the source expiry is still rejected."""
        self.produce()
        admission = self.document('FINAL-ADMISSION.json')
        admission['admittedAtClientNs'] = self.plan['pausedReview']['chain']['originalSceneDeadlineClientNs'] + 1
        wrapper = copy.deepcopy(self.wrapper)
        wrapper['finalPausedReviewAdmission'] = admission
        with self.assertRaisesRegex(ValueError, 'original clocks'):
            self.chain(wrapper=wrapper, documents=lambda name: admission if name == 'FINAL-ADMISSION.json' else self.document(name))

    def test_dispatch_clocks_cannot_extend_the_source_worker_or_shorter_lease(self):
        """Use the actual new wrapper's clock pair; cleanup may be later, but no new dispatch may cross its cap."""
        self.produce()
        pair = self.wrapper['leaseClockPair']
        started = max(pair['clientNs'], self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs']) + 1
        episode = dict(combatTrialGuardState=dict(startedNs=started))
        cutoff = min(pair['effectiveClientDeadlineNs'],
            pair['clientNs'] + self.wrapper['leaseDeadlineMonotonicNs'] - pair['monotonicNs'])
        cleanup = dict(type='combatTrialRelease', clientTimeNs=cutoff + 1_000_000)
        audit.verify_reviewed_episode_clocks(self.plan, self.wrapper, episode,
            [dict(type='combatTrialDispatch', clientTimeNs=cutoff - 1), cleanup])
        for moment in (cutoff, pair['effectiveClientDeadlineNs']):
            with self.subTest(moment=moment), self.assertRaisesRegex(ValueError, 'dispatch exceeded'):
                audit.verify_reviewed_episode_clocks(self.plan, self.wrapper, episode,
                    [dict(type='combatTrialDispatch', clientTimeNs=moment)])
        changed = copy.deepcopy(self.wrapper)
        changed['leaseDeadlineMonotonicNs'] = pair['monotonicNs'] + 5_000_000_001
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            audit.verify_reviewed_episode_clocks(self.plan, changed, episode)

    def test_review_age_uses_the_explicit_qpc_claim_without_mixing_monotonic_origins(self):
        """Independent clock origins remain valid, while a genuinely expired actual review is rejected."""
        self.produce()
        episode = dict(combatTrialGuardState=dict(startedNs=max(self.wrapper['leaseClockPair']['clientNs'],
            self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs']) + 1))
        shifted = copy.deepcopy(self.wrapper)
        for key in ('startedMonotonicNs', 'deadlineMonotonicNs'):
            shifted['hostClaim'][key] += 500_000_000_000
        shifted['leaseClockPair']['monotonicNs'] += 500_000_000_000
        shifted['leaseDeadlineMonotonicNs'] += 500_000_000_000
        audit.verify_reviewed_episode_clocks(self.plan, shifted, episode)
        changed = copy.deepcopy(self.plan)
        changed['pausedReview']['chain']['reviewedAtUnixNs'] -= 121_000_000_000
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            audit.verify_reviewed_episode_clocks(changed, shifted, episode)

    def test_failed_prechecked_worker_remains_failed_with_zero_attack_accounting(self):
        """Full offline audit joins a STOP before resume, exact retirement and diagnostic-only split."""
        self.produce('precheckedStop')
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['wrapperStatus'], 'failed')
        self.assertTrue(result['attackListenerNeverStartedVerified'])
        self.assertEqual(result['pausedPreparation']['lastVerifiedPhase'], 'precheckedPaused')
        self.assertEqual((result['guardedDispatches'], result['acceptedProposalJoins']), (0, 0))
        self.assertFalse(result['trialCompleteVerified'])

    def test_unconsumed_published_arm_is_distinct_from_worker_authority(self):
        """An ARM file alone cannot turn an interrupted preparation into an armed listener."""
        self.produce('unconsumedArm')
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['pausedPreparation']['lastVerifiedPhase'], 'pausedArmPublished')
        self.assertFalse(result['pausedPreparation']['finalAdmissionVerified'])
        self.assertTrue(result['attackListenerNeverStartedVerified'])

    def test_model_failure_replays_positive_loading_probe_without_inventing_readiness(self):
        """A prewarm exception preserves its failed phase and cannot be represented as model-ready."""
        self.produce('loadFailure')
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['pausedPreparation']['lastVerifiedPhase'], 'modelLoadAttempt')
        self.assertFalse(result['pausedPreparation']['finalAdmissionVerified'])
        self.assertEqual(result['wrapperStatus'], 'failed')

    def test_no_listener_cleanup_requires_the_raw_original_minimized_idle_owner(self):
        """Missing or contradictory final owner snapshots cannot inherit cleanup summary booleans."""
        self.produce('precheckedStop')
        path = self.folder / 'worker-owner-after.json'
        original = path.read_bytes()
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['artifactSha256']['worker-owner-after.json'], audit.digest(original))
        for change in ('missing', 'foreign', 'busy', 'unknown', 'visible', 'session', 'root', 'running'):
            with self.subTest(change=change):
                value = json.loads(original)
                if change == 'missing':
                    path.unlink()
                else:
                    if change == 'foreign': value['child']['instanceNonce'] = 'foreign-child'
                    if change == 'busy': value['child']['taskRunning'] = True
                    if change == 'unknown': value['root'].pop('serviceOwnsPilot')
                    if change == 'visible': value['root']['childWindowMinimized'] = False
                    if change == 'session': value['root']['childSessionId'] += 1
                    if change == 'root': value['child']['rootProcessId'] += 1
                    if change == 'running': value['child']['pilotState'] = 'running'
                    path.write_bytes(canonical(value))
                try:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        audit.audit_trial(self.folder)
                finally:
                    path.write_bytes(original)
        released = json.loads(original)
        released['child']['pilotState'] = 'faulted'
        path.write_bytes(canonical(released))
        self.assertTrue(audit.audit_trial(self.folder)['attackListenerNeverStartedVerified'])

    def test_failed_model_prefix_rejects_multiple_loads_and_invalid_duration(self):
        """A failed load remains one actual attempt with finite, matching completion timing."""
        self.produce('loadFailure')
        for change in ('attempts', 'loads', 'boolean', 'negative', 'infinite', 'nan', 'duration', 'backwards', 'unfinished'):
            with self.subTest(change=change):
                value = copy.deepcopy(self.wrapper)
                if change == 'attempts': value['modelLoadAttempts'] = 2
                if change == 'loads': value['modelLoads'] = 2
                if change == 'boolean': value['modelLoadAttempts'] = True
                if change == 'negative': value['modelLoadSeconds'] = -1
                if change == 'infinite': value['modelLoadSeconds'] = float('inf')
                if change == 'nan': value['modelLoadSeconds'] = float('nan')
                if change == 'duration': value['modelPreparation']['modelLoadSeconds'] = value['modelLoadSeconds'] + 1
                if change == 'backwards': value['modelPreparation']['finishedAtUnixNs'] = value['modelPreparation']['startedAtUnixNs'] - 1
                if change == 'unfinished': value['modelPreparation'].pop('finishedAtUnixNs')
                with self.assertRaisesRegex(ValueError, 'load'):
                    self.chain(wrapper=value, require_admission=False)

    def test_absent_model_intent_cannot_claim_loads(self):
        """A failed inventory probe predates model intent and must retain zero attempts and duration."""
        self.produce('beforeModel')
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['pausedPreparation']['lastVerifiedPhase'], 'reviewedPaused')
        self.assertNotIn('modelPreparation', self.wrapper)
        changed = copy.deepcopy(self.wrapper)
        changed.update(modelLoadAttempts=1, modelLoads=1, modelLoadSeconds=1)
        with self.assertRaisesRegex(ValueError, 'Absent paused model preparation'):
            self.chain(wrapper=changed, require_admission=False)

    def test_cancelled_load_intent_replays_without_inventing_an_attempt(self):
        """STOP during status publication records an intent, zero loads and no invented finish time."""
        fixture = self.produce('loadIntentStop')
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['pausedPreparation']['lastVerifiedPhase'], 'modelLoadIntent')
        self.assertEqual((fixture.loads, self.wrapper['modelLoadAttempts'], self.wrapper['modelLoads']), (0, 0, 0))
        changed = copy.deepcopy(self.wrapper)
        changed['modelPreparation']['finishedAtUnixNs'] = changed['modelPreparation']['startedAtUnixNs']
        with self.assertRaisesRegex(ValueError, 'Unattempted paused model load'):
            self.chain(wrapper=changed, require_admission=False)

    def test_successful_load_then_failed_pre_readiness_remains_a_failed_prefix(self):
        """A returned policy can fail validation before readiness without becoming a second or unrecorded load."""
        self.produce('postLoadFailure')
        result = audit.audit_trial(self.folder)
        self.assertEqual(result['pausedPreparation']['lastVerifiedPhase'], 'modelLoadAttempt')
        self.assertEqual((self.wrapper['modelLoadAttempts'], self.wrapper['modelLoads']), (1, 1))
        self.assertEqual(result['wrapperStatus'], 'failed')
        self.assertFalse(result['trialCompleteVerified'])


class HeldClockAuditTests(unittest.TestCase):
    """Keep source, host, lease and dispatch caps independent of admission ordering."""

    def setUp(self):
        """Use different QPC and monotonic origins and a source-clipped four-second lease."""
        self.qpc, self.mono, self.wall = 1_000_000_000_000, 2_000_000_000_000, 3_000_000_000_000
        self.plan = {
            'sourceFiles': {'tools/bettergi-agent/combat_paused_file_admission.py': 'a' * 64},
            'pausedReview': {'chain': {
                'originalSceneDeadlineClientNs': self.qpc + 64_000_000_000,
                'reviewedAtUnixNs': self.wall - 10_000_000_000}}}
        self.wrapper = {
            'hostClaim': {
                'startedAtUnixNs': self.wall, 'startedAtClientNs': self.qpc,
                'startedMonotonicNs': self.mono, 'deadlineMonotonicNs': self.mono + 90_000_000_000},
            'leaseClockPair': {
                'monotonicNs': self.mono + 60_000_000_000, 'clientNs': self.qpc + 60_000_000_000,
                'originalSceneDeadlineClientNs': self.qpc + 64_000_000_000,
                'effectiveClientDeadlineNs': self.qpc + 64_000_000_000},
            'leaseDeadlineMonotonicNs': self.mono + 64_000_000_000,
            'finalPausedReviewAdmission': {'admittedAtClientNs': self.qpc + 60_500_000_000},
            'pausedImmutableAdmission': {
                'version': 1, 'kind': 'per-worker-held-immutable-admission-v1',
                'denyWriteDelete': True, 'checkpointContentHeld': False,
                'freshHashReadRequired': True, 'consumed': True, 'closed': True, 'closeErrors': [],
                'maximumFiles': 2304, 'maximumBytes': 384 * 1024 * 1024,
                'maximumFileBytes': 32 * 1024 * 1024, 'fileCount': 1,
                'immutableFiles': {'retained-source.py': 'a' * 64},
                'freshHashBytes': 10, 'freshHashMilliseconds': 450.0}}
        self.episode = {'combatTrialGuardState': {'startedNs': self.qpc + 61_000_000_000}}

    def verify(self, events=None):
        """Call the real auditor without altering its inputs or predicates."""
        return audit.verify_reviewed_episode_clocks(self.plan, self.wrapper, self.episode, events)

    def test_historical_budget_cannot_inherit_the_larger_ceiling(self):
        """A 384 MiB declaration still fails at its own next byte, regardless of the newer contract."""
        held=self.wrapper['pausedImmutableAdmission']
        held['freshHashBytes']=384*1024*1024
        self.verify()
        held['freshHashBytes']+=1
        with self.assertRaisesRegex(ValueError,'source declaration'):self.verify()

    def test_new_budget_measured_shape_boundary_and_overrun(self):
        """The finite 448 MiB declaration admits the measured run39 size, its boundary, but no more."""
        held=self.wrapper['pausedImmutableAdmission'];held['maximumBytes']=448*1024*1024
        held['freshHashBytes']=427529818
        self.verify()
        held['freshHashBytes']=448*1024*1024
        self.verify()
        held['freshHashBytes']+=1
        with self.assertRaisesRegex(ValueError,'source declaration'):self.verify()

    def test_unknown_or_non_integer_budget_declarations_refuse(self):
        """Only the two explicit integer ceilings exist; unknown or numeric-lookalike values refuse."""
        held=self.wrapper['pausedImmutableAdmission']
        for value in (0,True,False,None,'469762048',float(384*1024*1024),float(448*1024*1024),
                      384*1024*1024-1,384*1024*1024+1,448*1024*1024+1,512*1024*1024):
            with self.subTest(value=value):
                held['maximumBytes']=value
                with self.assertRaisesRegex(ValueError,'source declaration'):self.verify()

    def test_new_budget_cannot_relax_clock_or_source_mode(self):
        """The larger file bound cannot introduce later admission or an undeclared held mode."""
        self.wrapper['pausedImmutableAdmission']['maximumBytes']=448*1024*1024
        self.verify()
        admitted=self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs']
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs']=self.qpc+61_000_000_001
        with self.assertRaisesRegex(ValueError,'lease widened'):self.verify()
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs']=admitted
        self.plan['sourceFiles']={}
        with self.assertRaisesRegex(ValueError,'Historical'):self.verify()

    def test_held_admission_after_pair_before_start_passes(self):
        """A real final read may finish after sampling, while every deadline stays fixed."""
        self.verify()

    def test_historical_order_remains_unchanged(self):
        """Old plans cannot adopt the held ordering without the archived source declaration."""
        self.plan['sourceFiles'] = {}
        self.wrapper.pop('pausedImmutableAdmission')
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs'] = self.qpc + 59_999_999_999
        self.verify()
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs'] = self.qpc + 60_000_000_001
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_source_and_witness_cannot_be_removed_independently(self):
        """Neither an undeclared witness nor a missing new-mode witness can pick an easier order."""
        held = self.wrapper.pop('pausedImmutableAdmission')
        with self.assertRaisesRegex(ValueError, 'source declaration'):
            self.verify()
        self.wrapper['pausedImmutableAdmission'] = held
        self.plan['sourceFiles'] = {}
        with self.assertRaisesRegex(ValueError, 'Historical'):
            self.verify()

    def test_held_descriptor_and_cleanup_mutations_refuse(self):
        """A failed, partial or widened held-file phase cannot authorize the new chronology."""
        original = copy.deepcopy(self.wrapper['pausedImmutableAdmission'])
        mutations = {
            'version': True, 'kind': 'unknown-held-mode', 'denyWriteDelete': False,
            'checkpointContentHeld': True, 'freshHashReadRequired': False,
            'consumed': False, 'closed': False, 'closeErrors': ['unretired handle'],
            'maximumFiles': 2305, 'maximumBytes': 384 * 1024 * 1024 + 1,
            'maximumFileBytes': 32 * 1024 * 1024 + 1, 'fileCount': 2,
            'immutableFiles': {}, 'freshHashBytes': 0, 'freshHashMilliseconds': float('nan')}
        for key, value in mutations.items():
            with self.subTest(key=key):
                self.wrapper['pausedImmutableAdmission'] = copy.deepcopy(original)
                self.wrapper['pausedImmutableAdmission'][key] = value
                with self.assertRaisesRegex(ValueError, 'source declaration'):
                    self.verify()

    def test_held_admission_cannot_precede_lease_sample(self):
        """The named held flow must retain its actual sample-then-consume order."""
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs'] = self.qpc + 59_999_999_999
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_admission_must_precede_native_episode_start(self):
        """Late admission remains invalid even if it still fits the source deadline."""
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs'] = self.qpc + 61_000_000_001
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_native_episode_cannot_start_at_original_source_expiry(self):
        """The original scene boundary is exclusive for starting the native episode."""
        self.episode['combatTrialGuardState']['startedNs'] = self.qpc + 64_000_000_000
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_source_cap_cannot_be_extended_one_nanosecond(self):
        """Isolate the four-second source cap below the five- and ninety-second bounds."""
        self.wrapper['leaseDeadlineMonotonicNs'] += 1
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_five_second_cap_cannot_be_extended_one_nanosecond(self):
        """A later scene deadline never turns the five-second ceiling into a renewable budget."""
        source = self.qpc + 80_000_000_000
        self.plan['pausedReview']['chain']['originalSceneDeadlineClientNs'] = source
        self.wrapper['leaseClockPair'].update(originalSceneDeadlineClientNs=source, effectiveClientDeadlineNs=source)
        self.wrapper['leaseDeadlineMonotonicNs'] = self.mono + 65_000_000_000
        self.verify()
        self.wrapper['leaseDeadlineMonotonicNs'] += 1
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_ninety_second_host_cap_remains_independent(self):
        """An earlier host deadline clips a later scene deadline and a late five-second lease."""
        source = self.qpc + 150_000_000_000
        self.plan['pausedReview']['chain']['originalSceneDeadlineClientNs'] = source
        self.wrapper['leaseClockPair'].update(monotonicNs=self.mono + 89_000_000_000,
            clientNs=self.qpc + 89_000_000_000, originalSceneDeadlineClientNs=source,
            effectiveClientDeadlineNs=self.qpc + 90_000_000_000)
        self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs'] = self.qpc + 89_200_000_000
        self.episode['combatTrialGuardState']['startedNs'] = self.qpc + 89_500_000_000
        self.wrapper['leaseDeadlineMonotonicNs'] = self.mono + 90_000_000_000
        self.verify()
        self.wrapper['leaseDeadlineMonotonicNs'] += 1
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_original_review_age_is_not_renewed(self):
        """A source-bounded lease still cannot use an over-age actual review."""
        self.plan['pausedReview']['chain']['reviewedAtUnixNs'] -= 50_000_000_000
        with self.assertRaisesRegex(ValueError, 'lease widened'):
            self.verify()

    def test_dispatch_cutoff_stays_exclusive_while_release_can_be_later(self):
        """The final safe dispatch and later cleanup are distinct from a late input."""
        cutoff = self.qpc + 64_000_000_000
        self.verify([{'type': 'combatTrialDispatch', 'clientTimeNs': cutoff - 1},
                     {'type': 'combatTrialRelease', 'clientTimeNs': cutoff + 1_000_000}])
        for timestamp in (self.qpc + 61_000_000_000 - 1, cutoff, cutoff + 1):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(ValueError, 'dispatch exceeded'):
                self.verify([{'type': 'combatTrialDispatch', 'clientTimeNs': timestamp}])

    def test_sampling_origin_can_change_without_changing_qpc_authority(self):
        """Do not conflate the worker monotonic deadline with QPC frame/admission clocks."""
        shift = 500_000_000_000
        self.wrapper['hostClaim']['startedMonotonicNs'] += shift
        self.wrapper['hostClaim']['deadlineMonotonicNs'] += shift
        self.wrapper['leaseClockPair']['monotonicNs'] += shift
        self.wrapper['leaseDeadlineMonotonicNs'] += shift
        self.verify()

    def test_unknown_clock_types_refuse(self):
        """A boolean, absent or nonintegral admission is not an observed clock."""
        for value in (True, None, self.qpc + 60_500_000_000.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'lease widened'):
                self.wrapper['finalPausedReviewAdmission']['admittedAtClientNs'] = value
                self.verify()

    def test_archived_held_implementation_must_match_replay_source(self):
        """Resealing a changed helper cannot retain the new-mode interpretation."""
        names = ('combat_trial.py', 'combat_trial_guard.py', 'stream_client.py', 'native_combat.py',
                 'model_adapters.py', 'resident_runtime.py', 'episode_split.py', 'combat_pause_probe.py',
                 'combat_pause_proof.py', 'combat_paused_review_proof.py', 'combat_paused_file_admission.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'source-snapshot/tools/bettergi-agent'
            archive.mkdir(parents=True)
            pins = {}
            relative_paths = ['tools/bettergi-agent/' + name for name in names]
            relative_paths.append('tools/quest-pilot/controller-control.py')
            for relative in relative_paths:
                raw = (Path(audit.__file__).parents[2] / relative).read_bytes()
                destination = root / 'source-snapshot' / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                pins[relative] = hashlib.sha256(raw).hexdigest()
            plan = {'sourceFiles': pins}
            audit.verify_source_archive(root, plan, prepared=True, reviewed=True)
            target = archive / 'combat_paused_file_admission.py'
            raw = target.read_bytes() + b'\n# changed archived implementation\n'
            target.write_bytes(raw)
            pins['tools/bettergi-agent/combat_paused_file_admission.py'] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'Replay implementation differs'):
                audit.verify_source_archive(root, plan, prepared=True, reviewed=True)


if __name__ == '__main__':
    unittest.main()
