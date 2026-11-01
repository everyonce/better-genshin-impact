"""Independent replay rejects altered sources, missing drains and inflated combat claims."""
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from audit_combat_trial import audit_episode, replay_events, verify_retirement, verify_temperatures, verify_preparation_chain
from combat_trial_guard import CombatTrialGuard, GROUP_SCOPE, FOUR_SCOPE, scope_fields, trial_policy,scope_maximum
from policy_rgb_archive import write_policy_rgb
from test_combat_trial_guard import HELLO, OWNER, binding, frame, proposal,review_parts,group_review_parts
from native_combat import CAPABILITY,CAPABILITY_V2,capability_for_version


def completed_trace(version=1, *, group=False, scope=GROUP_SCOPE):
    """Produce three deterministic native pulses without a pipe, clock wait or GPU."""
    count=scope_maximum(scope) if group else 1
    parts=group_review_parts(count,count,scope=scope) if group else review_parts();capability=capability_for_version(version)
    if version==2:
        parts[2]['nativeCombatObservation']=copy.deepcopy(capability)
        parts[2]['observations'][0]['combatEvidence'].update(version=2,method=capability['method'])
    authority = binding(parts)
    hello=dict(copy.deepcopy(HELLO),combatObservation=capability)
    guard = CombatTrialGuard(authority, OWNER, hello, 0)
    events, frames, decisions, receipts = [], [], [], []

    def source_frame(*args,**kwargs):
        """Emit one version consistently through the source, native protocol and guard replay."""
        kwargs.setdefault('candidates',count)
        value=frame(*args,**kwargs)
        value['combatEvidence'].update(version=version,method=capability['method'])
        return value

    def observe(source):
        """Retain both the intake event and its original image metadata."""
        frames.append(copy.deepcopy(source))
        events.append(guard.observe(source, int(source['serverNowMs'] * 1e6), round_trip_ms=1))

    observe(source_frame(1, 100))
    current = source_frame(2, 150)
    observe(current)
    for index in range(3):
        at = current['sourceFrame']['freshnessAtMs']
        marker = guard.prepare_action(current, proposal(), 'attack-' + str(index), int((at + 15) * 1e6), owner=OWNER, hello=hello)
        events.append(marker)
        accepted = dict(type='accepted', requestId='attack-' + str(index), receivedAtMs=at + 19, acceptedAtMs=at + 20)
        events.append(guard.admission(accepted, 0, int((at + 30) * 1e6)))
        receipt = dict(requestId='attack-' + str(index), frameId=current['frameId'], modelId='open-p2p',
            status='completed', reason='horizon_complete', acceptedAtMs=at + 20, endedAtMs=at + 120,
            appliedSteps=[dict(index=0, keys=['LBUTTON'], mouseDx=0, mouseDy=0, startedAtMs=at + 21)])
        receipts.append(copy.deepcopy(receipt))
        events.append(guard.receipt(receipt, int((at + 130) * 1e6)))
        released = dict(type='released', serverNowMs=at + 130, worldReadiness=dict(ready=False, epoch=index + 1))
        events.append(guard.acknowledge_release(released, 0, int((at + 140) * 1e6), 'completedCombatPulse'))
        decisions.append(dict(proposal(), rawPolicySteps=proposal(50)['steps'], frameId=current['frameId'],
                              acceptance=accepted, combatTrialGuard=marker,
                              controllerResampling='explicit-bounded-key-hold; mouse applied once'))
        current = source_frame(index + 3, at + 200, epoch=index + 1)
        observe(current)
    events.append(guard.acknowledge_release(dict(type='released', serverNowMs=780,
        worldReadiness=dict(ready=False, epoch=4)), 0, 790_000_000, 'combatTrialTeardown'))
    episode = dict(status='completed', hello=hello, combatTrialGuard=authority,
        combatTrialGuardState=guard.snapshot(), decisions=decisions, receipts=receipts,
        combatTrialReceiptEnvelopes=[dict(type='frame', serverNowMs=item['endedAtMs'] + 10,
            receipts=[copy.deepcopy(item)], droppedReceipts=0) for item in receipts],
        combatTrialReleases=[{key: copy.deepcopy(event[key]) for key in ('response', 'payloadBytes', 'clientTimeNs', 'reason')}
            for event in events if event['type'] == 'combatTrialRelease'],
        acceptedInputActions=3, endReason='combatTrialComplete', stop=dict(type='stopped'),
        residentRunId='a' * 32, combatTrialFinalControl=dict(version=1, runId='a' * 32, command='run'), goalChanges=[],
        recording=dict(complete=True, lossless=True, workerRetired=True, error=None,
            encodedFrames=len(frames), policyRgbFrames=len(frames), recordedObservations=len(frames),
            droppedFrames=0, droppedEvents=0, droppedObservations=0, abandonedFrames=0))
    goal = dict(controlEpoch=0, policyGoalVersion=0, appliedGoalRequestId=None, goalRequestId=None,
                goalRequestStatus=None, goalError=None, goalMetadata=dict(instruction='fixed combat'), goalIntent='stationary')
    episode.update(initialGoalState=copy.deepcopy(goal), finalGoalState=copy.deepcopy(goal))
    if version==2:episode['nativeCombatObservation']=copy.deepcopy(capability)
    return episode, events, frames, authority


class CombatTrialAuditTests(unittest.TestCase):
    """Exercise retained bytes and event ordering independently of live controller code."""

    def setUp(self):
        """Write small exact RGB fixtures only in the test's private temporary directory."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.episode, self.events, self.frames, self.binding = completed_trace()
        for index, row in enumerate(self.frames):
            row.update(width=192, height=192, videoFrameIndex=index,
                       clientReceivedNs=int(row['serverNowMs'] * 1e6), transportRoundTripMs=1)
            row['policyRgb'] = write_policy_rgb(self.folder, index, row, bytes([index]) * (192 * 192 * 3))

    def audit(self):
        """Run the same pure episode audit used for retained native trials."""
        return audit_episode(self.episode, self.events, self.frames, self.folder, self.binding)

    def test_complete_trace_replays_three_drained_pulses(self):
        """A full drain verifies transport without claiming enemy damage or a kill."""
        report = self.audit()
        self.assertTrue(report['trialCompleteVerified'])
        self.assertEqual(report['guardedDispatches'], 3)
        self.assertEqual(report['acceptedProposalJoins'], 3)
        self.assertEqual(report['verifiedRgbFrames'], 5)
        self.assertFalse(report['combatSuccess'])
        self.assertFalse(report['damageVerified'])

    def test_group_trace_replays_and_rejects_scope_or_visible_count_substitution(self):
        """Independent replay binds the group authority and cannot downgrade it to the old contract."""
        for change in ('none','scope','maximum','visible','policy'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                episode,events,frames,authority=completed_trace(2,group=True)
                for index,row in enumerate(frames):
                    row.update(width=192,height=192,videoFrameIndex=index,
                        clientReceivedNs=int(row['serverNowMs']*1e6),transportRoundTripMs=1)
                    row['policyRgb']=write_policy_rgb(Path(folder),index,row,bytes([index])*(192*192*3))
                if change=='scope':authority.pop('combatScope')
                if change=='maximum':authority['maximumEnemyBarCandidates']=4
                if change=='visible':authority['inspectedVisibleEnemyCount']=2
                if change=='policy':authority['policy']=trial_policy()
                invoke=lambda:audit_episode(episode,events,frames,Path(folder),authority)
                if change=='none':self.assertTrue(invoke()['trialCompleteVerified'])
                else:
                    with self.assertRaises(ValueError):invoke()

    def test_four_scope_replay_cannot_downgrade_to_three_or_widen_to_five(self):
        """The additional fixed scope is replayable without changing any pulse or source contract."""
        for changed in (None,'three','five'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as folder:
                episode,events,frames,authority=completed_trace(2,group=True,scope=FOUR_SCOPE)
                for index,row in enumerate(frames):
                    row.update(width=192,height=192,videoFrameIndex=index,
                        clientReceivedNs=int(row['serverNowMs']*1e6),transportRoundTripMs=1)
                    row['policyRgb']=write_policy_rgb(Path(folder),index,row,bytes([index])*(192*192*3))
                if changed=='three':authority.update(scope_fields(GROUP_SCOPE),policy=trial_policy(GROUP_SCOPE))
                if changed=='five':authority['maximumEnemyBarCandidates']=5
                if changed:
                    with self.assertRaises(ValueError):audit_episode(episode,events,frames,Path(folder),authority)
                else:
                    result=audit_episode(episode,events,frames,Path(folder),authority)
                    self.assertTrue(result['trialCompleteVerified'])
                    self.assertEqual(result['acceptedProposalJoins'],3)

    def test_v2_complete_trace_requires_bound_negotiation_and_native_frames(self):
        """Every v2 completion retains its chosen contract; fully valid v1 evidence cannot replace it."""
        for change in ('none','missing','reply','hello','frame'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                episode,events,frames,authority=completed_trace(2)
                for index,row in enumerate(frames):
                    row.update(width=192,height=192,videoFrameIndex=index,
                               clientReceivedNs=int(row['serverNowMs']*1e6),transportRoundTripMs=1)
                    row['policyRgb']=write_policy_rgb(Path(folder),index,row,bytes([index])*(192*192*3))
                if change=='missing':episode.pop('nativeCombatObservation')
                if change=='reply':episode['nativeCombatObservation']=copy.deepcopy(CAPABILITY)
                if change=='hello':episode['hello']['combatObservation']=copy.deepcopy(CAPABILITY)
                if change=='frame':frames[-1]['combatEvidence'].update(version=1,method=CAPABILITY['method'])
                invoke=lambda:audit_episode(episode,events,frames,Path(folder),authority)
                if change=='none':self.assertTrue(invoke()['trialCompleteVerified'])
                else:
                    with self.assertRaises(ValueError):invoke()

    def test_missing_terminal_event_fails_replay(self):
        """A release cannot substitute for the missing terminal execution receipt."""
        self.events = [row for row in self.events if row['type'] != 'combatTrialReceipt']
        with self.assertRaises(ValueError):
            self.audit()

    def test_changed_transport_measurement_fails_replay(self):
        """The replay uses the retained poll's transport cost, not a fabricated zero."""
        self.events[0]['roundTripMs'] = 200
        with self.assertRaises(ValueError):
            self.audit()

    def test_missing_transport_measurement_is_not_inferred(self):
        """A repeated or unavailable poll must still retain its own timing."""
        del self.events[0]['roundTripMs']
        with self.assertRaises(ValueError):
            self.audit()

    def test_changed_rgb_fails_even_with_intact_video_metadata(self):
        """Lossy video or unchanged source labels do not replace exact policy pixels."""
        path = self.folder / self.frames[0]['policyRgb']['file']
        path.write_bytes(bytes([255]) * (192 * 192 * 3))
        with self.assertRaises(ValueError):
            self.audit()

    def test_raw_mixed_action_cannot_be_projected_into_attack(self):
        """A guard-approved action must also match the original model keys."""
        self.episode['decisions'][0]['rawPolicySteps'][0]['keys'].append('W')
        with self.assertRaises(ValueError):
            self.audit()

    def test_missing_post_release_pixels_prevent_completion(self):
        """The final drain requires the actual later policy frame."""
        self.frames.pop()
        with self.assertRaises(ValueError):
            self.audit()

    def test_changed_native_source_does_not_join_by_frame_id_only(self):
        """A reused numerical frame identifier is insufficient source identity."""
        self.frames[1]['capturedAtMs'] += 1
        with self.assertRaises(ValueError):
            self.audit()

    def test_native_receipt_must_be_present_outside_guard_snapshot(self):
        """The copied completion state is cross-checked against original native receipts."""
        self.episode['receipts'].pop()
        with self.assertRaises(ValueError):
            self.audit()

    def test_recorder_must_actually_retire(self):
        """Three valid pulses do not excuse an unresolved writer process."""
        self.episode['recording']['workerRetired'] = False
        with self.assertRaises(ValueError):
            self.audit()

    def test_duplicated_accepted_decision_cannot_fill_missing_joins(self):
        """Three copies of one valid decision do not prove three distinct model inputs."""
        self.episode['decisions'] = [copy.deepcopy(self.episode['decisions'][0]) for _ in range(3)]
        with self.assertRaises(ValueError):
            self.audit()

    def test_changed_acceptance_clock_fails_original_admission_join(self):
        """A summary acceptance must retain the native acknowledgement byte-for-byte."""
        self.episode['decisions'][0]['acceptance']['acceptedAtMs'] += 1
        with self.assertRaises(ValueError):
            self.audit()

    def test_startup_pixels_are_required(self):
        """Initial target admission must have exact pixels just like an applied action."""
        self.frames.pop(0)
        with self.assertRaises(ValueError):
            self.audit()

    def test_unobserved_extra_rgb_frame_is_not_ignored(self):
        """An omitted hazardous intake cannot be hidden among otherwise valid RGB files."""
        source = frame(6, 800, epoch=4, health=.2)
        source.update(width=192, height=192, videoFrameIndex=5, clientReceivedNs=810_000_000, transportRoundTripMs=1)
        source['policyRgb'] = write_policy_rgb(self.folder, 5, source, bytes([6]) * (192 * 192 * 3))
        self.frames.append(source)
        with self.assertRaises(ValueError):
            self.audit()

    def test_policy_rgb_cannot_move_between_native_frames(self):
        """Valid files and hashes still need the recorder's exact frame/index binding."""
        self.frames[0]['policyRgb'], self.frames[1]['policyRgb'] = self.frames[1]['policyRgb'], self.frames[0]['policyRgb']
        with self.assertRaises(ValueError):
            self.audit()

    def test_invalid_raw_hold_cannot_gain_validity_from_resampling(self):
        """Invalid source actions are rejected rather than rewritten into the allowed range."""
        self.episode['decisions'][0]['rawPolicySteps'][0]['durationMs'] = 10000
        with self.assertRaises(ValueError):
            self.audit()

    def test_original_poll_cannot_hide_stale_or_unready_source(self):
        """Immutable pixel identity alone is insufficient for the original dispatch poll."""
        for key, value in (('sourceFrameAgeMs', 400), ('inputAvailable', False), ('droppedReceipts', 1)):
            with self.subTest(key=key):
                original = self.frames[1][key]
                self.frames[1][key] = value
                with self.assertRaises(ValueError):
                    self.audit()
                self.frames[1][key] = original

    def test_extra_native_receipt_cannot_be_ignored(self):
        """Every native action receipt belongs to the complete replayed sequence."""
        extra = copy.deepcopy(self.episode['receipts'][0])
        extra['requestId'] = 'untracked-fourth-action'
        self.episode['receipts'].append(extra)
        with self.assertRaises(ValueError):
            self.audit()

    def test_missing_native_release_cannot_hide_behind_guard_copy(self):
        """The audit checks original release acknowledgements as well as guard state."""
        self.episode['combatTrialReleases'].pop()
        with self.assertRaises(ValueError):
            self.audit()

    def test_receipt_transport_envelope_is_required(self):
        """A derived receipt list is insufficient when original native envelopes are absent."""
        self.episode['combatTrialReceiptEnvelopes'].clear()
        with self.assertRaises(ValueError):
            self.audit()

    def test_late_goal_request_prevents_completion_even_if_summary_is_cleared(self):
        """Raw control evidence remains authoritative after the last pulse has drained."""
        self.episode['combatTrialFinalControl']['goalRequestId'] = 'late-goal'
        self.episode['combatTrialFinalControl']['goalEmbedding'] = 'different.json'
        with self.assertRaises(ValueError):
            self.audit()

    def test_recording_booleans_cannot_override_inconsistent_counters(self):
        """Lossless=True cannot excuse missing frames or explicitly recorded drops."""
        for key, value in (('encodedFrames', 999), ('policyRgbFrames', 999), ('recordedObservations', 999), ('droppedFrames', 1)):
            with self.subTest(key=key):
                original = self.episode['recording'][key]
                self.episode['recording'][key] = value
                with self.assertRaises(ValueError):
                    self.audit()
                self.episode['recording'][key] = original

    def test_final_state_cannot_clear_a_real_trip(self):
        """A derived summary cannot substitute another terminal guard state."""
        self.episode['combatTrialGuardState']['acceptedActions'] = 2
        with self.assertRaises(ValueError):
            self.audit()

    def test_local_refusal_replays_original_proposal(self):
        """A refusal preserves its complete invocation rather than inventing an input receipt."""
        guard = CombatTrialGuard(self.binding, OWNER, HELLO, 0)
        one, two = frame(1, 100), frame(2, 150)
        events = [guard.observe(one, 110_000_000, round_trip_ms=1),
                  guard.observe(two, 160_000_000, round_trip_ms=1)]
        events.append(guard.prepare_action(two, dict(parseValid=True, steps=[]), 'refused', 165_000_000, owner=OWNER, hello=HELLO))
        replay = replay_events(self.binding, HELLO, events)
        self.assertEqual(replay['state']['acceptedActions'], 0)
        self.assertEqual(replay['counts']['combatTrialLocalRefusal'], 1)

    def test_actual_stream_event_order_is_replayable(self):
        """Run the real stream loop against inert resources, then independently replay its output."""
        from test_combat_trial_stream import CombatTrialStreamTests, TrialBridge, TrialPolicy
        from test_stream_client import CapturingRecorder

        class RetiredMemoryRecorder(CapturingRecorder):
            """A synchronous list recorder has no unretired worker or lossy queue."""

            def close(self):
                """Expose its actual synchronous completion for the independent audit."""
                return dict(super().close(), lossless=True, workerRetired=True,
                    policyRgbFrames=len(self.frames), recordedObservations=len(self.frames),
                    droppedFrames=0, droppedEvents=0, droppedObservations=0, abandonedFrames=0)

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            harness = CombatTrialStreamTests()
            recorder = RetiredMemoryRecorder()
            self.assertEqual(harness.run_inert(folder, TrialBridge(), TrialPolicy(), recorder), 0)
            report = json.loads((folder / 'run.json').read_bytes())
            frames = []
            for index, (row, pixels) in enumerate(recorder.frames):
                value = copy.deepcopy(row)
                value['videoFrameIndex'] = index
                value['policyRgb'] = write_policy_rgb(folder, index, value, pixels)
                frames.append(value)
            audited = audit_episode(report, recorder.events, frames, folder, report['combatTrialGuard'])
            self.assertTrue(audited['trialCompleteVerified'])


class CombatTrialRetirementAuditTests(unittest.TestCase):
    """Verify original worker/broker claims and retained telemetry independently of runtime admission."""

    def bundle(self):
        """Provide one ordinary RDP worker and an exact immutable host claim."""
        run_id, plan_sha, manifest_sha = 'a' * 32, 'b' * 64, 'c' * 64
        identity = dict(remoteDesktop=True, elevated=False, integrityRid=8192, windowsSessionId=3)
        worker = dict(identity, processId=44, parentProcessId=33)
        broker = dict(identity, runnerProcessId=33, timedOut=False, outputIncomplete=False, success=True, returnCode=0)
        claim = dict(runId=run_id, planSha256=plan_sha)
        worker_claim = dict(claim, processId=44, parentProcessId=33)
        wrapper = dict(status='completed', planSha256=plan_sha, worker=worker, hostClaim=claim)
        host = dict(status='completed', runId=run_id, planSha256=plan_sha, launchAttempts=1,
            terminalManifestSha256=manifest_sha, broker=broker, hostClaim=claim, worker=worker, ownerIdleMinimizedAfter=True)
        plan = dict(runId=run_id, binding=binding())
        return plan, wrapper, host, broker, claim, worker_claim, manifest_sha

    def test_exact_retired_bundle_passes(self):
        """The launcher claim and broker ancestry agree on exactly one worker."""
        verify_retirement(*self.bundle())

    def test_host_stop_cannot_be_promoted_by_completed_worker(self):
        """A host thermal/operator stop remains terminal even if the child wrote completion."""
        bundle = self.bundle()
        bundle[2]['stopReason'] = 'temperatureLimit'
        with self.assertRaises(ValueError):
            verify_retirement(*bundle)

    def test_changed_worker_parent_fails(self):
        """A different process cannot inherit another broker's successful exit."""
        bundle = self.bundle()
        bundle[5]['parentProcessId'] = 99
        with self.assertRaises(ValueError):
            verify_retirement(*bundle)

    def test_repeated_launch_is_not_one_trial(self):
        """A second launch attempt cannot hide inside an otherwise matching terminal report."""
        bundle = self.bundle()
        bundle[2]['launchAttempts'] = 2
        with self.assertRaises(ValueError):
            verify_retirement(*bundle)

    def test_telemetry_has_fresh_bounded_actual_samples(self):
        """Healthy terminal samples pass while cutoff, gaps and query failures do not."""
        rows = [dict(atUtc='2026-10-31T10:00:00+00:00', temperatureC=60),
                dict(atUtc='2026-10-31T10:00:02+00:00', temperatureC=61)]
        finished = int(datetime.fromisoformat('2026-10-31T10:00:02.5+00:00').timestamp() * 1e9)
        self.assertEqual(verify_temperatures(rows, finished), 61)
        for mutation in ('hot', 'gap', 'error'):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(rows)
                if mutation == 'hot':
                    altered[-1]['temperatureC'] = 78
                elif mutation == 'gap':
                    altered[-1]['atUtc'] = '2026-10-31T10:00:08+00:00'
                else:
                    altered[-1]['error'] = 'query failed'
                with self.assertRaises(ValueError):
                    verify_temperatures(altered, finished)


class CombatPreparedAuditTests(unittest.TestCase):
    """Replay the real inert wrapper's staged proof without its mutable originals or a model."""
    def setUp(self):
        """Produce one complete one-shot handoff through the real artifact writer."""
        from test_combat_trial import CombatPreparedTrialTests
        self.fixture = CombatPreparedTrialTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.begin(claim=False)
        self.fixture.lifecycle.runner = lambda: self.fixture.worker(self.fixture.arm)
        import combat_trial
        from test_combat_trial import FakeWatch
        result=combat_trial.launch(self.fixture.plan_path, lifecycle=self.fixture.lifecycle,
            watch_factory=FakeWatch, paused_preparation=True)
        # Preserve the actual failed phase in the test log before TemporaryDirectory cleanup.
        details={name:json.loads((self.fixture.folder/name).read_bytes()) for name in ('result.json','patrol.json')
                 if (self.fixture.folder/name).is_file()}
        self.assertEqual(result,0,json.dumps(details,sort_keys=True))
        self.folder, self.plan, self.wrapper = self.fixture.folder, self.fixture.plan, self.fixture.report()

    def document(self, name):
        """Read the same immutable phase artifacts required by the full auditor."""
        return json.loads((self.folder / name).read_bytes())

    def audit(self):
        """Reconstruct the independent paused preparation chain only."""
        return verify_preparation_chain(self.folder, self.plan, self.wrapper, self.document)

    def test_exact_preparation_and_broker_retirement_replay(self):
        """The original preparation claim and final armed plan remain distinct and joined."""
        result = self.audit()
        self.assertFalse(result['inputEnabledBeforeArm'])
        import hashlib
        verify_retirement(self.plan, self.wrapper, self.document('result.json'), self.document('broker.json'),
            self.document('CONSUMED.json'), self.document('WORKER-CONSUMED.json'),
            hashlib.sha256((self.folder / 'patrol.json').read_bytes()).hexdigest())

    def test_partial_group_scope_cannot_replace_default_preparation_or_readiness(self):
        """A changed scope/max declaration is independently rejected at every paused handoff phase."""
        for name in ('preparation.json','prepared.json'):
            with self.subTest(name=name):
                original=self.document(name);changed=copy.deepcopy(original)
                changed.update(scope_fields(GROUP_SCOPE))
                def documents(current):
                    """Substitute only one phase while keeping the original immutable archive on disk."""
                    return changed if current==name else self.document(current)
                with self.assertRaises(ValueError):
                    verify_preparation_chain(self.folder,self.plan,self.wrapper,documents)

    def test_group_preparation_replays_exact_scope_and_rejects_each_removed_declaration(self):
        """Replay an actual inert group handoff, then independently remove one phase's opt-in."""
        self._assert_preparation_scope_replay(GROUP_SCOPE)

    def test_four_preparation_replays_exact_scope_and_rejects_each_removed_declaration(self):
        """The fourth-enemy scope must survive every independently replayed preparation boundary."""
        self._assert_preparation_scope_replay(FOUR_SCOPE)

    def _assert_preparation_scope_replay(self,scope):
        """Exercise one named fixed scope through the real inert worker and archived handoff audit."""
        import combat_trial
        from test_combat_trial import CombatPreparedTrialTests,FakeWatch
        fixture=CombatPreparedTrialTests();fixture.setUp()
        try:
            maximum=scope_maximum(scope)
            fixture.configure_group_review(candidates=maximum,visible=maximum,scope=scope)
            fixture.begin(claim=False,scope=scope)
            fixture.lifecycle.runner=lambda:fixture.worker(fixture.arm)
            self.assertEqual(combat_trial.launch(fixture.plan_path,lifecycle=fixture.lifecycle,
                watch_factory=FakeWatch,paused_preparation=True),0)
            def document(name):
                """Use the original separately sealed phase documents produced by the worker."""
                return json.loads((fixture.folder/name).read_bytes())
            plan,wrapper=fixture.plan,fixture.report()
            self.assertIsNotNone(verify_preparation_chain(fixture.folder,plan,wrapper,document))
            for name in ('preparation.json','prepared.json','plan','wrapper'):
                with self.subTest(name=name):
                    changed=copy.deepcopy(plan if name=='plan' else wrapper if name=='wrapper' else document(name))
                    changed.pop('combatScope');changed.pop('maximumEnemyBarCandidates')
                    def substituted(current):
                        """Leave original bytes/hash witnesses intact while exposing the contradictory phase."""
                        return changed if current==name else document(current)
                    with self.assertRaises(ValueError):
                        verify_preparation_chain(fixture.folder,changed if name=='plan' else plan,
                            changed if name=='wrapper' else wrapper,substituted)
        finally:
            fixture.doCleanups()

    def test_archive_replay_does_not_depend_on_current_native_files(self):
        """A later native run may remove originals; the exact retained UI proof still replays."""
        preparation = self.document('preparation.json')
        original = next(Path(name) for name in preparation['pause']['proof']['files'] if name.endswith('after.png'))
        original.unlink()
        self.assertIsNotNone(self.audit())

    def test_missing_retained_png_never_falls_back_to_original(self):
        """A present mutable native PNG cannot repair an absent archived pause witness."""
        preparation = self.document('preparation.json')
        retained = next(Path(target) for name, target in preparation['pause']['retained'].items() if name.endswith('after.png'))
        retained.unlink()
        with self.assertRaises(ValueError):
            self.audit()

    def test_fresh_loading_probe_requires_its_original_pixels_and_receipt(self):
        """A historical pause cannot repair any missing or substituted new passive evidence."""
        record = self.document('prepared.json')['modelPreparation']['inventoryProbe']
        for suffix in ('after.png', '.receipt.json', 'owner-after-stop.json'):
            with self.subTest(suffix=suffix):
                target = next(Path(value) for name, value in record['retained'].items() if name.endswith(suffix))
                original = target.read_bytes()
                target.write_bytes(original + b'changed')
                try:
                    with self.assertRaises(ValueError):
                        self.audit()
                finally:
                    target.write_bytes(original)

    def test_loading_probe_cannot_be_removed_or_substituted_from_another_preparation(self):
        """Version two has no fallback to old timestamps when its no-input handoff is absent."""
        for mutation in ('missing', 'foreign'):
            with self.subTest(mutation=mutation):
                ready = self.document('prepared.json')
                if mutation == 'missing':
                    ready['modelPreparation'].pop('inventoryProbe')
                else:
                    ready['modelPreparation']['inventoryProbe'] = self.document('preparation.json')['pause']
                wrapper = copy.deepcopy(self.wrapper)
                wrapper['modelPreparation'] = ready['modelPreparation']
                def documents(name):
                    """Expose the contradictory readiness phase without touching original source evidence."""
                    return ready if name == 'prepared.json' else self.document(name)
                with self.assertRaises(ValueError):
                    verify_preparation_chain(self.folder, self.plan, wrapper, documents)

    def test_runtime_archive_remnants_cannot_select_old_replay(self):
        """An omitted or null runtime declaration cannot discard the original archived witness."""
        from audit_combat_trial import verify_python_runtime
        for null in (False, True):
            plan = copy.deepcopy(self.plan)
            plan.pop('workerRuntime')
            if null:
                plan['workerRuntime'] = None
            with self.assertRaisesRegex(ValueError, 'Undeclared Python runtime'):
                verify_python_runtime(self.folder, plan)

    def test_terminal_probe_cleanup_or_result_substitution_cannot_complete(self):
        """Successful loading evidence never overrides a contradictory final retained probe result."""
        for mutation in ('error', 'result', 'hash', 'missing'):
            with self.subTest(mutation=mutation):
                wrapper = copy.deepcopy(self.wrapper)
                if mutation == 'error':
                    wrapper['inventoryProbeCleanupError'] = 'lost terminal proof'
                elif mutation == 'result':
                    wrapper['inventoryProbeResult']['inventoryVerified'] = False
                elif mutation == 'hash':
                    wrapper['inventoryProbeResultSha256'] = '0' * 64
                else:
                    wrapper.pop('inventoryProbeResult')
                with self.assertRaisesRegex(ValueError, 'Terminal passive inventory'):
                    verify_preparation_chain(self.folder, self.plan, wrapper, self.document)

    def test_ready_worker_and_arm_claim_changes_are_rejected(self):
        """Each phase is bound to the same actual ordinary process and one immutable claim."""
        for name, field in (('prepared.json', 'worker'), ('ARM.json', 'worker'), ('ARM-CONSUMED.json', 'worker')):
            with self.subTest(name=name):
                path = self.folder / name
                raw = path.read_bytes()
                value = json.loads(raw)
                value[field]['processId'] += 1
                path.write_text(json.dumps(value), encoding='utf-8')
                try:
                    with self.assertRaises(ValueError):
                        self.audit()
                finally:
                    path.write_bytes(raw)

    def test_stripped_declaration_with_retained_evidence_is_not_historical(self):
        """Removing preparation labels cannot downgrade a new run into archived v1 semantics."""
        self.plan.pop('preparedPolicy')
        self.wrapper['kind'] = 'combat-trial-wrapper-v1'
        for name in ('preparationSha256', 'preparedPolicy', 'armSha256', 'inputEnabledBeforeArm', 'modelPreparation'):
            self.wrapper.pop(name, None)
        with self.assertRaisesRegex(ValueError, 'undeclared preparation'):
            self.audit()

    def test_post_resume_source_and_loading_phase_are_independent_checks(self):
        """Consistent terminal counters cannot excuse a pre-resume image or input-enabled load."""
        original = copy.deepcopy(self.plan['binding']['reviewedFrame']['sourceFrame'])
        self.plan['binding']['reviewedFrame']['sourceFrame']['timestamp100ns'] = 1
        with self.assertRaisesRegex(ValueError, 'before resume'):
            self.audit()
        self.plan['binding']['reviewedFrame']['sourceFrame'] = original
        self.wrapper['modelPreparation']['inputEnabled'] = True
        with self.assertRaisesRegex(ValueError, 'preparation phase'):
            self.audit()


if __name__ == '__main__':
    unittest.main()
