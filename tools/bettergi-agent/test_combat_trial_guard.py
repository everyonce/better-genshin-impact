"""Inert tests for separate combat authority, strict dispatch and complete terminal drain."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from combat_trial_guard import (CombatTrialGuard, CombatTrialStop, PROFILE, REVIEW_KIND,
                               bind_review, canonical, proposal_rejection, trial_policy,
                               SINGLE_SCOPE, GROUP_SCOPE, FOUR_SCOPE, scope_fields, combat_scope)
from native_combat import CAPABILITY, CAPABILITY_V2, METHOD


OWNER = dict(root=dict(processId=11, windowsSessionId=1, instanceNonce='root'),
             child=dict(processId=22, windowsSessionId=3, instanceNonce='child'))
HELLO = dict(sessionId='lease', ownerEpoch='epoch', goalVersion=1, inputEnabled=True,
             supportsRelease=True, supportsStartBeforeMs=True, observationProfile=PROFILE,
             allowedKeys=['W', 'LBUTTON'], combatObservation=CAPABILITY)


def frame(index=1, at=100, *, health=.9, candidates=1, epoch=0, capture='live', age=10):
    """Provide a complete native HUD, readiness and immutable compositor source fixture."""
    source = dict(captureEpoch=capture, timestamp100ns=int(at * 10000) + 1, capturedAtMs=at,
                  acquiredAtMs=at + 1, freshnessAtMs=at, freshnessClockKind='reported_compositor_qpc')
    evidence = dict(version=1, method=METHOD, state='valid', reason='native_colors_analyzed',
        frameId=index, sourceFrame=copy.deepcopy(source), sourceWidth=1920, sourceHeight=1080,
        playerHealthColor='green', playerHealthFractionEstimate=health, playerHealthMatchingPixels=200,
        enemyBarCandidates=[dict(x=800 + offset * 200, y=400, width=120, height=6, pixels=720)
                            for offset in range(candidates)], redMaskOverloaded=False,
        recognitionMs=1, authorizesInput=False, enemyIdentityVerified=False, killVerified=False)
    gate = dict(ready=True, epoch=epoch, sourceFrameId=index, sourceFrame=copy.deepcopy(source))
    return dict(type='frame', frameId=index, capturedAtMs=at + 2, sourceFrame=source,
                sourceWidth=1920, sourceHeight=1080, combatEvidence=evidence,
                sourceTimestampKind='wgc_reported_compositor_qpc', sourceFrameAgeMs=age,
                serverNowMs=at + age, inputAvailable=True, worldReadiness=copy.deepcopy(gate),
                frameWorldReadiness=gate, droppedReceipts=0, receipts=[])


def review_parts():
    """Keep PNG frame nine between decimated stable samples five, eight and eleven."""
    selected = frame(9, 100, capture='historical')
    image = b'\x89PNG\r\n\x1a\n' + (13).to_bytes(4, 'big') + b'IHDR' + (1920).to_bytes(4, 'big') + (1080).to_bytes(4, 'big')
    image_sha = hashlib.sha256(image).hexdigest()
    goal = canonical(dict(instruction='Attack the nearby enemy with normal attacks.'))
    sidecar = {key: copy.deepcopy(selected[key]) for key in
               ('frameId', 'capturedAtMs', 'sourceWidth', 'sourceHeight', 'sourceFrame', 'sourceTimestampKind')}
    sidecar.update(freshnessContractVersion=2, evidence='WorldHud', imageSha256=image_sha,
                   worldReadiness=copy.deepcopy(selected['frameWorldReadiness']))
    plan = dict(owner=copy.deepcopy(OWNER), enableInput=False, modelLoaded=False)
    scene = dict(status='completed', inputEnabled=False, modelLoaded=False, ownerIdleMinimizedAfter=True,
                 observations=[selected], stableSamples=[frame(5), frame(8), frame(11)],
                 qualifiedImageFrameId=9, selectedImageName='native-nine.png', selectedImageSha256=image_sha)
    review = dict(kind=REVIEW_KIND, sceneLabel='enemy-visible', attacksAllowed=['LBUTTON'],
                  policy=trial_policy(), inspectionNote='A nearby enemy is visible and the HUD health was inspected.',
                  inspectedHealth=900, inspectedMaximumHealth=1000, owner=copy.deepcopy(OWNER),
                  imageName='native-nine.png', imageSha256=image_sha, goalSha256=hashlib.sha256(goal).hexdigest())
    return [review, plan, scene, sidecar, image, goal]


def binding(parts=None):
    """Bind original JSON bytes without a filesystem, bridge, model or image decoder."""
    parts = review_parts() if parts is None else parts
    return bind_review(*(canonical(value) if index < 4 else value for index, value in enumerate(parts)))


def group_review_parts(candidates=3, visible=3, *, scope=GROUP_SCOPE):
    """Author explicit visual group authority while retaining the same source/image joins."""
    parts = review_parts()
    parts[0].update(scope_fields(scope), policy=trial_policy(scope), inspectedVisibleEnemyCount=visible)
    parts[2]['observations'][0]['combatEvidence']['enemyBarCandidates'] = frame(candidates=candidates)['combatEvidence']['enemyBarCandidates']
    return parts


def proposal(duration=100):
    """Represent one unchanged policy normal-attack proposal."""
    return dict(parseValid=True, steps=[dict(keys=['LBUTTON'], mouseDx=0, mouseDy=0, durationMs=duration)])


class CombatTrialGuardTests(unittest.TestCase):
    def test_earlier_scope_policies_keep_exact_pre_four_canonical_bytes(self):
        """Pins were measured before adding the fourth-enemy scope, independent of current assembly."""
        expected={SINGLE_SCOPE:'cd0aebd5c96097912bac8ea0874a587de862946535933d4d66750b08befb5e1d',
            GROUP_SCOPE:'5a69d8c207ef4fb3390bc9cc214b21a6442bb3da27e4996c9ebc7aeb7bbf6f72',
            FOUR_SCOPE:'8184d519ffe138a290476daf5fcb717ddc9cbc64b84715b74886478a337f1a01'}
        for scope,sha in expected.items():
            self.assertEqual(hashlib.sha256(canonical(trial_policy(scope))).hexdigest(),sha)

    def test_four_scope_requires_explicit_four_review_and_preserves_lower_scope(self):
        """A fourth visible enemy can never be relabeled as the existing three-enemy scope."""
        authority=binding(group_review_parts(4,4,scope=FOUR_SCOPE))
        self.assertEqual(combat_scope(authority),FOUR_SCOPE)
        self.assertEqual(authority['policy']['maximumEnemyBarCandidates'],4)
        with self.assertRaises(ValueError):binding(group_review_parts(4,4))
        for count in (0,5,True):
            with self.subTest(count=count),self.assertRaises(ValueError):
                binding(group_review_parts(4,count,scope=FOUR_SCOPE))
        for scope,maximum in ((FOUR_SCOPE,3),(GROUP_SCOPE,4),('reviewed-group-up-to-five-v1',5),(FOUR_SCOPE,True)):
            changed=group_review_parts(4,4,scope=FOUR_SCOPE)
            changed[0].update(combatScope=scope,maximumEnemyBarCandidates=maximum)
            with self.subTest(scope=scope,maximum=maximum),self.assertRaises(ValueError):binding(changed)
        with self.assertRaises(ValueError):binding(group_review_parts(0,4,scope=FOUR_SCOPE))

    def test_four_scope_keeps_three_pulse_drain_and_terminal_five_or_target_loss(self):
        """Only the named target cap changes; zero/five remain terminal after admission."""
        self.guard=CombatTrialGuard(binding(group_review_parts(4,4,scope=FOUR_SCOPE)),OWNER,HELLO,0)
        self.current=frame(2,150,candidates=4);self.ready()
        for _ in range(3):self.drain()
        self.assertTrue(self.guard.snapshot()['trialComplete'])
        for count,reason in ((0,'targetLost'),(5,'ambiguousTarget')):
            self.guard=CombatTrialGuard(binding(group_review_parts(4,4,scope=FOUR_SCOPE)),OWNER,HELLO,0)
            self.current=frame(2,150,candidates=4);self.ready()
            current=frame(3,200,candidates=count)
            for index,candidate in enumerate(current['combatEvidence']['enemyBarCandidates']):candidate['x']=300+index*200
            self.assertEqual(self.observe(current)['state']['trip']['reason'],reason)

    def test_legacy_policy_remains_exact_and_group_never_inferred(self):
        """The default contract has no opt-in fields and still refuses multiple native candidates."""
        self.assertEqual(trial_policy(), dict(version=1, maximumSeconds=5, maximumActions=3, maximumSourceAgeMs=150,
            minimumHoldMs=33, maximumHoldMs=100, stopTemperatureC=78, healthFractionDrop=.08,
            admissionSources=2, postActionDelayMs=60, allowedKeys=['LBUTTON'], maximumOutstandingActions=1,
            requireSingleEnemyBarCandidate=True, retryAllowed=False, renewAllowed=False, goalFrozen=True,
            enemyIdentityVerified=False, damageVerified=False, killVerified=False))
        self.assertEqual(combat_scope(binding()), SINGLE_SCOPE)
        parts = group_review_parts()
        for key in ('combatScope', 'maximumEnemyBarCandidates', 'inspectedVisibleEnemyCount'):
            parts[0].pop(key)
        parts[0]['policy'] = trial_policy()
        with self.assertRaises(ValueError):binding(parts)

    def test_group_review_needs_explicit_matching_scope_count_and_candidate(self):
        """Neither an observed count nor a partial declaration widens the fixed scope."""
        for count in (1, 2, 3):
            self.assertEqual(combat_scope(binding(group_review_parts(count))), GROUP_SCOPE)
        mutations = [lambda p:p[0].pop('combatScope'), lambda p:p[0].pop('maximumEnemyBarCandidates'),
            lambda p:p[0].pop('inspectedVisibleEnemyCount'), lambda p:p[0].update(maximumEnemyBarCandidates=4),
            lambda p:p[0].update(maximumEnemyBarCandidates=True), lambda p:p[0].update(policy=trial_policy()),
            lambda p:p[0].update(inspectedVisibleEnemyCount=True), lambda p:p[0].update(inspectedVisibleEnemyCount=4),
            lambda p:p[0].update(inspectedVisibleEnemyCount=2),
            lambda p:p[2]['observations'][0]['combatEvidence'].update(enemyBarCandidates=[]),
            lambda p:p[2]['observations'][0]['combatEvidence'].update(enemyBarCandidates=frame(candidates=4)['combatEvidence']['enemyBarCandidates'])]
        for change in mutations:
            with self.subTest(change=change):
                parts=group_review_parts();change(parts)
                with self.assertRaises(ValueError):binding(parts)

    def test_group_drains_exactly_three_unchanged_pulses_across_one_to_three_candidates(self):
        """A bounded group changes only eligible candidate counts, not attack or drain semantics."""
        self.guard=CombatTrialGuard(binding(group_review_parts()),OWNER,HELLO,0)
        self.current=frame(2,150,candidates=3)
        self.ready()
        for _ in range(3):self.drain()
        state=self.guard.snapshot()
        self.assertTrue(state['trialComplete'])
        self.assertEqual((state['acceptedActions'],state['completedActions']),(3,3))
        self.assertTrue(all(row['arguments']['steps']==proposal()['steps'] for row in state['completed']))

    def test_group_preserves_target_loss_ambiguity_health_and_pure_action_refusal(self):
        """Wider reviewed count never relaxes unknown, health, absent-target or mixed-action stops."""
        for fields,reason in ((dict(candidates=0),'targetLost'),(dict(candidates=4),'ambiguousTarget'),
                              (dict(health=.8),'healthFractionDrop')):
            with self.subTest(reason=reason):
                self.guard=CombatTrialGuard(binding(group_review_parts()),OWNER,HELLO,0)
                self.current=frame(2,150,candidates=3);self.ready()
                self.assertEqual(self.observe(frame(3,200,**fields))['state']['trip']['reason'],reason)
        self.guard=CombatTrialGuard(binding(group_review_parts()),OWNER,HELLO,0)
        self.current=frame(2,150,candidates=3);self.ready()
        for step in (dict(keys=['W','LBUTTON'],mouseDx=0,mouseDy=0,durationMs=100),
                     dict(keys=['LBUTTON'],mouseDx=1,mouseDy=0,durationMs=100)):
            self.assertEqual(self.dispatch(proposed=dict(parseValid=True,steps=[step]))['type'],'combatTrialLocalRefusal')
        self.assertEqual(self.guard.snapshot()['acceptedActions'],0)

    def test_retained_three_visible_enemy_camp_with_zero_native_candidates_is_inadmissible(self):
        """The real inspected camp cannot qualify merely by opting into the three-enemy maximum."""
        folder=Path(__file__).resolve().parents[2]/'artifacts/live/2026-10-30-endurance/mondstadt-gate-r64-ground-10'
        if not (folder/'result.json').is_file():self.skipTest('Retained local camp fixture is unavailable')
        plan=(folder/'plan.json').read_bytes();scene=(folder/'result.json').read_bytes()
        selected=json.loads(scene);name=selected['selectedImageName']
        image=(folder/name).read_bytes();sidecar=(folder/(Path(name).stem+'.json')).read_bytes()
        frame_id=json.loads(sidecar)['frameId']
        rows=[row for row in selected['observations'] if row.get('frameId')==frame_id]
        self.assertTrue(rows)
        self.assertEqual(rows[0]['combatEvidence']['enemyBarCandidates'],[])
        goal=review_parts()[-1]
        review=dict(kind=REVIEW_KIND,sceneLabel='enemy-visible',attacksAllowed=['LBUTTON'],
            policy=trial_policy(GROUP_SCOPE),inspectionNote='Three visible level-one enemies were inspected in the retained camp image.',
            inspectedHealth=4015,inspectedMaximumHealth=4015,inspectedVisibleEnemyCount=3,
            owner=json.loads(plan)['owner'],imageName=name,imageSha256=hashlib.sha256(image).hexdigest(),
            goalSha256=hashlib.sha256(goal).hexdigest(),**scope_fields(GROUP_SCOPE))
        with self.assertRaisesRegex(ValueError,'native target evidence'):
            bind_review(canonical(review),plan,scene,sidecar,image,goal)

    def test_v2_review_binds_lease_and_every_later_observation(self):
        """A lower-screen reviewed target cannot silently switch the detector contract."""
        parts=review_parts();parts[2]['nativeCombatObservation']=copy.deepcopy(CAPABILITY_V2)
        selected=parts[2]['observations'][0]['combatEvidence']
        selected.update(version=2,method=CAPABILITY_V2['method'])
        selected['enemyBarCandidates'][0].update(x=469,y=961,width=120,height=8,pixels=923)
        bound=binding(parts)
        hello=dict(copy.deepcopy(HELLO),combatObservation=copy.deepcopy(CAPABILITY_V2))
        guard=CombatTrialGuard(bound,OWNER,hello,0)
        for index in (1,2):
            current=frame(index,100+index*50)
            current['combatEvidence'].update(version=2,method=CAPABILITY_V2['method'])
            guard.observe(current,int(current['serverNowMs']*1e6),round_trip_ms=1)
        self.assertEqual(guard.snapshot()['phase'],'ready')
        wrong=frame(3,300)
        self.assertIsNotNone(guard.observe(wrong,310_000_000,round_trip_ms=1)['state']['trip'])
        with self.assertRaises(ValueError):CombatTrialGuard(bound,OWNER,HELLO,0)
        parts[2].pop('nativeCombatObservation')
        with self.assertRaises(ValueError):binding(parts)

    def setUp(self):
        """Start every test with independent pure authority and no active controller."""
        self.guard = CombatTrialGuard(binding(), copy.deepcopy(OWNER), copy.deepcopy(HELLO), 0)
        self.index, self.epoch = 2, 0
        self.current = frame(self.index, 150)

    def observe(self, value, *, now_ns=None, round_trip_ms=1):
        """Publish a source using its native poll time as an inert monotonic client clock."""
        return self.guard.observe(value, int(value['serverNowMs'] * 1e6) if now_ns is None else now_ns,
                                  round_trip_ms=round_trip_ms)

    def ready(self):
        """Admit only after two distinct healthy candidate-bearing sources."""
        self.observe(frame())
        self.observe(self.current)
        self.assertEqual(self.guard.snapshot()['phase'], 'ready')

    def dispatch(self, *, value=None, proposed=None, request_id=None, now_ns=None, owner=None, hello=None):
        """Exercise the final post-inference check without transmitting any native input."""
        value = self.current if value is None else value
        return self.guard.prepare_action(value, proposal() if proposed is None else proposed,
            request_id or 'action-' + str(self.guard.snapshot()['acceptedActions']),
            int((value['serverNowMs'] + 5) * 1e6) if now_ns is None else now_ns,
            owner=OWNER if owner is None else owner, hello=HELLO if hello is None else hello)

    def accept(self):
        """Bind a timely acceptance and construct its exact one-step terminal receipt."""
        arguments = self.dispatch()['arguments']
        accepted = self.current['sourceFrame']['freshnessAtMs'] + 20
        response = dict(type='accepted', requestId=arguments['requestId'], receivedAtMs=accepted - 1, acceptedAtMs=accepted)
        self.guard.admission(response, 0, int((accepted + 10) * 1e6))
        receipt = dict(requestId=arguments['requestId'], frameId=arguments['frameId'], modelId='open-p2p',
                       status='completed', reason='horizon_complete', acceptedAtMs=accepted,
                       endedAtMs=accepted + arguments['steps'][0]['durationMs'],
                       appliedSteps=[dict(index=0, keys=['LBUTTON'], mouseDx=0, mouseDy=0, startedAtMs=accepted + 1)])
        return receipt

    def release(self, receipt):
        """Disarm after terminal evidence and require the native gate's incremented epoch."""
        self.epoch += 1
        released = dict(type='released', serverNowMs=receipt['endedAtMs'] + 5,
                        worldReadiness=dict(ready=False, epoch=self.epoch))
        event = self.guard.acknowledge_release(released, 0, int((released['serverNowMs'] + 10) * 1e6), 'completedPulse')
        return released, event

    def drain(self):
        """Finish one pulse only after its receipt, release acknowledgement and response frame."""
        receipt = self.accept()
        self.guard.receipt(receipt, int((receipt['endedAtMs'] + 10) * 1e6))
        released, _ = self.release(receipt)
        self.index += 1
        self.current = frame(self.index, released['serverNowMs'] + 60, epoch=self.epoch)
        self.observe(self.current)
        return receipt

    def test_distinct_review_authority_and_exact_image_join_ignore_stable_sample_decimation(self):
        bound = binding()
        self.assertEqual(bound['reviewedFrame']['frameId'], 9)
        self.assertEqual(bound['reviewedFrame']['sourceFrame']['captureEpoch'], 'historical')
        self.ready()
        self.assertEqual(self.dispatch()['type'], 'combatTrialDispatch')

    def test_review_substitution_and_missing_authority_fail_closed(self):
        mutations = [
            lambda p: p[0].update(kind='reviewed-scout-v1'),
            lambda p: p[0].update(attacksAllowed=False),
            lambda p: p[0]['policy'].update(maximumActions=4),
            lambda p: p[0]['policy'].update(renewAllowed=0),
            lambda p: p[0].update(inspectedHealth=True),
            lambda p: p[1]['owner']['child'].update(processId=33),
            lambda p: p[2].update(inputEnabled=True),
            lambda p: p[2]['observations'].append(dict(copy.deepcopy(p[2]['observations'][0]), capturedAtMs=999)),
            lambda p: p[3]['sourceFrame'].update(timestamp100ns=999),
            lambda p: p[3].update(frameId=8),
            lambda p: p[0].update(goalSha256='0' * 64),
            lambda p: p[2]['observations'][0]['combatEvidence'].update(enemyBarCandidates=[]),
        ]
        for change in mutations:
            with self.subTest(change=change):
                parts = copy.deepcopy(review_parts())
                change(parts)
                with self.assertRaises(ValueError):
                    binding(parts)

    def test_review_allows_consistent_repeated_poll_envelopes_for_one_native_image(self):
        parts = review_parts()
        repeated = copy.deepcopy(parts[2]['observations'][0])
        repeated.update(sourceFrameAgeMs=60, serverNowMs=160, receipts=[dict(requestId='telemetry-only')])
        repeated['combatEvidence']['recognitionMs'] = 2
        parts[2]['observations'].append(repeated)
        self.assertEqual(binding(parts)['reviewedFrame']['frameId'], 9)
        repeated['combatEvidence']['playerHealthFractionEstimate'] = .89
        with self.assertRaisesRegex(ValueError, 'contradictory repeated-source'):
            binding(parts)

    def test_binding_and_returned_evidence_are_immutable_snapshots(self):
        bound = binding()
        guard = CombatTrialGuard(bound, OWNER, HELLO, 0)
        bound['policy']['maximumActions'] = 999
        bound['owner']['child']['processId'] = 999
        state = guard.snapshot()
        state['lease']['sessionId'] = 'changed'
        self.assertEqual(guard.snapshot()['lease']['sessionId'], 'lease')
        self.assertEqual(guard.snapshot()['phase'], 'awaitingEvidence')

    def test_cached_binding_rejects_changed_fixed_caps_and_baseline(self):
        for key, value in [('maximumSeconds', 6), ('maximumSourceAgeMs', 151), ('maximumHoldMs', 101),
                           ('stopTemperatureC', 79), ('healthFractionDrop', .09), ('maximumOutstandingActions', 2)]:
            with self.subTest(key=key):
                bound = binding()
                bound['policy'][key] = value
                with self.assertRaises(ValueError):
                    CombatTrialGuard(bound, OWNER, HELLO, 0)
        bound = binding()
        bound['baselineHealthFraction'] = .85
        with self.assertRaises(ValueError):
            CombatTrialGuard(bound, OWNER, HELLO, 0)

    def test_startup_missing_or_target_absent_never_arms_and_waits_within_original_deadline(self):
        for evidence in (None, 'noTarget'):
            with self.subTest(evidence=evidence):
                self.setUp()
                row = frame(candidates=0)
                if evidence is None:
                    row.pop('combatEvidence')
                self.observe(row)
                self.assertEqual(self.dispatch()['type'], 'combatTrialLocalRefusal')
                self.assertIsNone(self.guard.snapshot()['trip'])
                self.assertFalse(self.guard.snapshot()['armed'])
                state = self.guard.tick(5_000_000_000)
                self.assertEqual(state['trip']['reason'], 'trialDeadline')
                self.assertFalse(state['trialComplete'])

    def test_repeated_source_does_not_confirm_or_refresh_age(self):
        first = frame()
        self.observe(first)
        repeated = copy.deepcopy(first)
        repeated.update(sourceFrameAgeMs=60, serverNowMs=160)
        self.observe(repeated)
        self.assertEqual(self.guard.snapshot()['confirmationSources'], 1)
        self.assertEqual(self.dispatch()['type'], 'combatTrialLocalRefusal')
        self.observe(self.current)
        self.assertEqual(self.dispatch(now_ns=299_000_000)['type'], 'combatTrialLocalRefusal')
        self.assertEqual(self.guard.snapshot()['acceptedActions'], 0)

    def test_every_observation_event_retains_exact_poll_and_transport_evidence(self):
        first = frame()
        repeated = copy.deepcopy(first)
        repeated.update(sourceFrameAgeMs=60, serverNowMs=160)
        missing = frame(2, 180)
        missing.pop('combatEvidence')
        hazardous = frame(3, 200, health=.8)
        for offset, row in enumerate((first, repeated, missing, hazardous)):
            with self.subTest(offset=offset):
                event = self.observe(row, round_trip_ms=offset + .5)
                self.assertEqual(event['roundTripMs'], offset + .5)
                self.assertEqual(event['frame']['serverNowMs'], row['serverNowMs'])
                self.assertEqual(event['frame']['droppedReceipts'], row['droppedReceipts'])
        already_stopped = self.observe(frame(4, 250), round_trip_ms=9.5)
        self.assertEqual(already_stopped['roundTripMs'], 9.5)
        self.assertEqual(already_stopped['frame']['serverNowMs'], 260)

    def test_changed_cached_evidence_and_source_identity_are_terminal(self):
        changes = [lambda f: f['combatEvidence'].update(playerHealthFractionEstimate=.89),
                   lambda f: f['sourceFrame'].update(captureEpoch='other'),
                   lambda f: f.update(serverNowMs=500),
                   lambda f: f.update(droppedReceipts=1)]
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                self.observe(frame())
                row = frame()
                change(row)
                event = self.observe(row)
                self.assertEqual(event['state']['phase'], 'stopped')
                self.assertEqual(event['state']['trip']['reason'], 'invalidNativeEvidence')

    def test_valid_health_hazards_and_ambiguous_target_retain_trigger_before_reader_failure(self):
        cases = [('redOrAmbiguousHealth', dict(playerHealthColor='red')),
                 ('redOrAmbiguousHealth', dict(playerHealthColor='unknown', playerHealthFractionEstimate=None, playerHealthMatchingPixels=0)),
                 ('healthFractionDrop', dict(playerHealthFractionEstimate=.82)),
                 ('ambiguousTarget', dict(redMaskOverloaded=True, reason='red_mask_overloaded', enemyBarCandidates=[]))]
        for reason, values in cases:
            with self.subTest(reason=reason):
                self.setUp()
                self.ready()
                hazardous = frame(3, 200)
                hazardous['combatEvidence'].update(values)
                event = self.observe(hazardous)
                self.assertEqual(event['state']['trip']['reason'], reason)
                hazardous['combatEvidence']['playerHealthColor'] = 'modified'
                self.assertNotEqual(self.guard.snapshot()['trip']['frame']['combatEvidence']['playerHealthColor'], 'modified')
                with self.assertRaises(CombatTrialStop):
                    self.dispatch(now_ns=220_000_000)
                self.assertEqual(self.guard.snapshot()['acceptedActions'], 0)

    def test_health_threshold_uses_reviewed_absolute_baseline_not_a_rolling_estimate(self):
        self.ready()
        for index, value in enumerate((.87, .84, .820001), start=3):
            self.observe(frame(index, (index + 1) * 50, health=value))
            self.assertIsNone(self.guard.snapshot()['trip'])
        self.observe(frame(6, 350, health=.81999))
        self.assertEqual(self.guard.snapshot()['trip']['reason'], 'healthFractionDrop')

    def test_inflight_newer_hazard_prevents_dispatch_from_older_healthy_pixels(self):
        self.ready()
        before_inference = copy.deepcopy(self.current)
        self.observe(frame(3, 175, candidates=0))
        with self.assertRaises(CombatTrialStop):
            self.dispatch(value=before_inference, now_ns=190_000_000)
        self.assertEqual(self.guard.snapshot()['trip']['reason'], 'targetLost')
        self.assertIsNone(self.guard.snapshot()['pending'])

    def test_unavailable_while_armed_is_terminal_but_released_waits_for_new_health(self):
        self.ready()
        receipt = self.accept()
        missing = frame(3, 200)
        missing.pop('combatEvidence')
        self.observe(missing)
        self.assertEqual(self.guard.snapshot()['trip']['reason'], 'armedEvidenceUnavailable')
        self.guard.receipt(receipt, 280_000_000)
        _, release = self.release(receipt)
        self.assertFalse(release['state']['armed'])
        self.assertEqual(release['state']['trip']['reason'], 'armedEvidenceUnavailable')
        self.assertFalse(release['state']['trialComplete'])

    def test_missing_released_evidence_cannot_reuse_still_fresh_previous_frame(self):
        self.ready()
        missing = frame(3, 170)
        missing.pop('combatEvidence')
        self.observe(missing)
        self.assertEqual(self.dispatch(now_ns=185_000_000)['type'], 'combatTrialLocalRefusal')
        self.assertIsNone(self.guard.snapshot()['trip'])

    def test_only_an_unchanged_pure_single_attack_is_eligible(self):
        changes = [lambda p: p.update(parseValid=False), lambda p: p.update(scrollUnsupported=True),
                   lambda p: p['steps'].append(copy.deepcopy(p['steps'][0])),
                   lambda p: p['steps'][0].update(keys=[]), lambda p: p['steps'][0].update(keys=['W', 'LBUTTON']),
                   lambda p: p['steps'][0].update(keys=['LBUTTON', 'LBUTTON']),
                   lambda p: p['steps'][0].update(mouseDx=1), lambda p: p['steps'][0].update(mouseDy=False),
                   lambda p: p['steps'][0].update(wheel=1), lambda p: p['steps'][0].update(durationMs=101),
                   lambda p: p['steps'][0].update(durationMs=32), lambda p: p['steps'][0].pop('mouseDy')]
        self.ready()
        for change in changes:
            proposed = proposal()
            change(proposed)
            unchanged = copy.deepcopy(proposed)
            event = self.dispatch(proposed=proposed)
            self.assertEqual(event['type'], 'combatTrialLocalRefusal')
            self.assertEqual(proposed, unchanged)
            self.assertFalse(event['transmissionAttempted'])
            self.assertEqual(event['requestId'], 'action-0')
            self.assertEqual(event['frame']['sourceFrame'], self.current['sourceFrame'])
            self.assertEqual(event['proposal'], proposed)
        for duration in (33, 50, 100):
            self.assertIsNone(proposal_rejection(proposal(duration)))

    def test_changed_owner_or_session_cannot_prepare_a_pulse(self):
        for target in ('owner', 'hello'):
            with self.subTest(target=target):
                self.setUp()
                self.ready()
                owner, hello = copy.deepcopy(OWNER), copy.deepcopy(HELLO)
                if target == 'owner':
                    owner['child']['instanceNonce'] = 'replacement'
                else:
                    hello['sessionId'] = 'replacement'
                with self.assertRaises(CombatTrialStop):
                    self.dispatch(owner=owner, hello=hello)
                self.assertEqual(self.guard.snapshot()['trip']['reason'], 'ownerOrLeaseChanged')

    def test_one_outstanding_pulse_includes_unknown_send_and_terminal_drain(self):
        self.ready()
        first = self.dispatch()
        self.assertEqual(first['arguments']['steps'], proposal()['steps'])
        self.assertEqual(first['arguments']['startBeforeMs'], 300)
        self.assertEqual(first['arguments']['expiresAtMs'], 400)
        self.assertEqual(self.dispatch(request_id='other')['type'], 'combatTrialLocalRefusal')
        self.assertEqual(self.guard.snapshot()['acceptedActions'], 0)
        self.guard.fail('unacknowledgedAction', 180_000_000, request=first['arguments'])
        with self.assertRaises(CombatTrialStop):
            self.dispatch(request_id='retry')

    def test_invalid_admission_and_terminal_receipts_stop_without_losing_metadata(self):
        self.ready()
        self.dispatch()
        response = dict(type='accepted', requestId='other', receivedAtMs=170, acceptedAtMs=170)
        event = self.guard.admission(response, 0, 180_000_000)
        self.assertEqual(event['state']['trip']['reason'], 'invalidActionAdmission')
        self.assertEqual(event['state']['pending']['admission'], response)
        changes = [lambda r: r.update(requestId='other'), lambda r: r.update(frameId=99),
                   lambda r: r.update(status='cancelled'), lambda r: r.update(acceptedAtMs=169),
                   lambda r: r['appliedSteps'][0].update(mouseDy=1),
                   lambda r: r['appliedSteps'][0].update(keys=['W']),
                   lambda r: r.update(endedAtMs=200), lambda r: r['appliedSteps'][0].update(startedAtMs=301)]
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                self.ready()
                receipt = self.accept()
                change(receipt)
                event = self.guard.receipt(receipt, 280_000_000)
                self.assertEqual(event['state']['trip']['reason'], 'invalidActionReceipt')
                self.assertEqual(event['state']['pending']['receipt'], receipt)

    def test_three_accepted_pulses_are_incomplete_until_final_receipt_release_and_response_frame(self):
        self.ready()
        self.drain()
        self.drain()
        receipt = self.accept()
        self.assertEqual(self.guard.snapshot()['acceptedActions'], 3)
        self.assertEqual(self.guard.snapshot()['completedActions'], 2)
        self.assertFalse(self.guard.snapshot()['trialComplete'])
        self.guard.receipt(receipt, int((receipt['endedAtMs'] + 10) * 1e6))
        self.assertEqual(self.guard.snapshot()['phase'], 'awaitingRelease')
        released, event = self.release(receipt)
        self.assertEqual(event['state']['phase'], 'awaitingPostFrame')
        missing = frame(self.index + 1, released['serverNowMs'] + 10, epoch=self.epoch)
        missing.pop('combatEvidence')
        self.observe(missing)
        self.assertIsNone(self.guard.snapshot()['trip'])
        early = frame(self.index + 2, released['serverNowMs'] + 59, epoch=self.epoch)
        self.observe(early)
        self.assertFalse(self.guard.snapshot()['trialComplete'])
        final = frame(self.index + 3, released['serverNowMs'] + 60, epoch=self.epoch)
        self.observe(final)
        state = self.guard.snapshot()
        self.assertTrue(state['trialComplete'])
        self.assertEqual(state['completedActions'], 3)
        self.assertFalse(state['armed'])
        self.assertFalse(state['damageVerified'])
        self.assertFalse(state['killVerified'])
        self.assertEqual(self.dispatch(value=final, request_id='fourth')['type'], 'combatTrialLocalRefusal')

    def test_deadline_with_last_pulse_outstanding_is_incomplete_and_late_ack_is_retained(self):
        self.ready()
        self.drain()
        self.drain()
        self.dispatch()
        self.guard.tick(5_000_000_000)
        pending = self.guard.snapshot()['pending']
        response = dict(type='accepted', requestId=pending['arguments']['requestId'],
                        receivedAtMs=self.current['sourceFrame']['freshnessAtMs'] + 19,
                        acceptedAtMs=self.current['sourceFrame']['freshnessAtMs'] + 20)
        state = self.guard.admission(response, 0, 5_000_000_001)['state']
        self.assertEqual(state['acceptedActions'], 3)
        self.assertEqual(state['completedActions'], 2)
        self.assertEqual(state['trip']['reason'], 'trialDeadline')
        self.assertFalse(state['trialComplete'])
        self.assertEqual(state['pending']['admission'], response)

    def test_invalid_release_does_not_disarm_and_cleanup_never_clears_a_trip(self):
        self.ready()
        receipt = self.accept()
        self.guard.receipt(receipt, 280_000_000)
        response = dict(type='released', serverNowMs=275, worldReadiness=dict(ready=False, epoch=0))
        state = self.guard.acknowledge_release(response, 0, 285_000_000, 'badEpoch')['state']
        self.assertTrue(state['armed'])
        self.assertEqual(state['trip']['reason'], 'invalidReleaseAcknowledgement')
        response['worldReadiness']['epoch'] = 1
        state = self.guard.acknowledge_release(response, 0, 286_000_000, 'cleanup')['state']
        self.assertFalse(state['armed'])
        self.assertEqual(state['trip']['reason'], 'invalidReleaseAcknowledgement')
        self.assertFalse(state['trialComplete'])

    def test_unowned_admission_receipt_and_release_are_retained_fail_closed(self):
        event = self.guard.admission(dict(type='accepted'), 0, 1)
        self.assertEqual(event['state']['trip']['reason'], 'invalidActionAdmission')
        self.assertEqual(event['response']['type'], 'accepted')
        event = self.guard.receipt(dict(requestId='foreign'), 2)
        self.assertEqual(event['state']['trip']['reason'], 'invalidActionAdmission')
        self.assertEqual(event['receipt']['requestId'], 'foreign')



class CombatStaleReacquisitionTests(unittest.TestCase):
    """Replay the retained 08 interruption; added opt-in/ACK successor authority is explicitly synthetic."""

    @staticmethod
    def fixture():
        """Read the portable exact source/receipt projection without ignored workspace dependencies."""
        return json.loads((Path(__file__).parent / 'testdata/combat-source-stale-08.json').read_bytes())

    def setup_guard(self, *, recovery=True, through=12):
        """Preserve the failed original binding unless the test explicitly authors the new policy."""
        self.data = self.fixture()
        self.authority = copy.deepcopy(self.data['binding'])
        if recovery:
            self.authority['policy'] = trial_policy(FOUR_SCOPE, source_stale_recovery=True)
        self.guard = CombatTrialGuard(self.authority, self.authority['owner'], self.data['hello'], self.data['startedNs'])
        self.trace = []
        for row in self.data['events'][:through]:
            self.apply_original(row, recovery=recovery)
        return self.guard.snapshot()

    def apply_original(self, row, *, recovery=True):
        """The historical journal omitted empty receipt envelopes; new-mode tests supply that explicit premise."""
        now = row['clientTimeNs']
        kind = row['type']
        if kind == 'combatTrialObservation':
            current = copy.deepcopy(row['frame'])
            if recovery:
                current.setdefault('receipts', [])
            event = self.guard.observe(current, now, round_trip_ms=row['roundTripMs'])
        elif kind == 'combatTrialDispatch':
            action = row['arguments']
            event = self.guard.prepare_action(self.guard.snapshot()['lastObservation']['frame'],
                dict(parseValid=True, steps=action['steps']), action['requestId'], now,
                owner=self.authority['owner'], hello=self.data['hello'])
        elif kind == 'combatTrialLocalRefusal':
            event = self.guard.prepare_action(row['frame'], row['proposal'], row['requestId'], now,
                owner=self.authority['owner'], hello=self.data['hello'])
        elif kind == 'combatTrialStop':
            trigger = row['trigger']
            event = self.guard.fail(trigger['reason'], now,
                **{key: value for key, value in trigger.items() if key not in ('reason', 'clientTimeNs')})
        elif kind == 'combatTrialAdmission':
            event = self.guard.admission(row['response'], row['payloadBytes'], now)
        elif kind == 'combatTrialReceipt':
            event = self.guard.receipt(row['receipt'], now)
        elif kind == 'combatTrialRelease':
            event = self.guard.acknowledge_release(row['response'], row['payloadBytes'], now, row['reason'])
        else:
            self.fail('Unexpected retained fixture event: ' + kind)
        self.trace.append(event)
        return event

    def release(self, mutate=None, *, request=True):
        """Use the original cleanup ACK as a test response, never relabel the failed live trial."""
        from combat_trial_guard import STALE_RELEASE_REASON
        row = copy.deepcopy(self.data['cleanupRelease'])
        if request:
            self.trace.append(self.guard.request_stale_release(self.authority['owner'], self.data['hello'],
                self.trace[-1]['clientTimeNs'] + 1))
        if mutate:
            mutate(row)
        event = self.guard.acknowledge_release(row['response'], row['payloadBytes'], row['clientTimeNs'], STALE_RELEASE_REASON)
        self.trace.append(event)
        return event

    def successor(self, index=69, *, offset=61, age=10):
        """Create clearly synthetic post-ACK sources with the retained healthy native detector shape."""
        reply = self.data['cleanupRelease']
        current = copy.deepcopy(self.data['events'][-1]['frame'])
        old = current['sourceFrame']
        at = reply['response']['serverNowMs'] + offset
        source = dict(old, timestamp100ns=old['timestamp100ns'] + round((at - old['freshnessAtMs']) * 10000),
                      capturedAtMs=at, acquiredAtMs=at + 1, freshnessAtMs=at)
        current.update(frameId=index, capturedAtMs=at + 1, sourceFrame=source,
            sourceFrameAgeMs=age, serverNowMs=at + age, receipts=[], inputAvailable=True)
        for name in ('frameWorldReadiness', 'worldReadiness'):
            current[name].update(ready=True, epoch=3, reason='world_ready', sourceFrameId=index,
                sourceCapturedAtMs=current['capturedAtMs'], checkedAtMs=at + age, sourceFrame=copy.deepcopy(source))
        current['combatEvidence'].update(frameId=index, sourceFrame=copy.deepcopy(source))
        now = reply['clientTimeNs'] + round((offset + age) * 1e6)
        return current, now

    def observe_successor(self, index=69, *, offset=61, mutate=None, age=10):
        """Retain every admission/refusal in the same replayable event order."""
        current, now = self.successor(index, offset=offset, age=age)
        if mutate:
            mutate(current)
        event = self.guard.observe(current, now, round_trip_ms=.5)
        self.trace.append(event)
        return event

    def test_original_08_remains_failed_and_old_snapshots_have_no_new_fields(self):
        """The real stale66/confirming67/ready68 sequence still fails under its original policy."""
        self.setup_guard(recovery=False, through=0)
        for row in self.data['originalTrace']:
            event = self.apply_original(row, recovery=False)
            self.assertEqual(hashlib.sha256(canonical(event)).hexdigest(), row['originalEventSha256'])
        state = self.guard.snapshot()
        self.assertEqual(state['trip']['reason'], 'invalidNativeEvidence')
        self.assertEqual(state['trip']['validationError'], 'Combat world epoch changed without acknowledged release')
        self.assertEqual((state['acceptedActions'], state['completedActions']), (1, 1))
        self.assertNotIn('sourceStaleRecovery', state)

    def test_exact_08_sequence_requires_owned_release_and_two_distinct_fresh_sources(self):
        """A confirming/ready epoch cannot authorize another action before the separately journaled ACK."""
        state = self.setup_guard()
        self.assertIsNone(state['trip'])
        self.assertEqual(state['phase'], 'awaitingStaleRelease')
        self.assertFalse(state['evidenceReady'])
        deadline = state['deadlineNs']
        self.assertEqual(self.release()['state']['phase'], 'awaitingStaleEvidence')
        first = self.observe_successor()
        self.assertFalse(first['state']['evidenceReady'])
        current, now = self.successor()
        repeated = self.guard.observe(current, now + 1, round_trip_ms=.5)
        self.trace.append(repeated)
        self.assertEqual(repeated['state']['confirmationSources'], 1)
        final = self.observe_successor(70, offset=121)['state']
        self.assertEqual(final['phase'], 'ready')
        self.assertTrue(final['evidenceReady'])
        self.assertEqual(final['deadlineNs'], deadline)
        self.assertEqual((final['acceptedActions'], final['completedActions']), (1, 1))
        self.assertEqual(final['sourceStaleRecovery']['used'], 1)
        self.assertEqual(len(final['sourceStaleRecovery']['completed']), 1)
        from audit_combat_trial import replay_events
        self.assertEqual(replay_events(self.authority, self.data['hello'], self.trace)['state'], final)

    def test_opt_in_policy_is_exact_and_unavailable_to_older_scopes(self):
        """The new policy is explicit, fixed and cannot be selected merely by seeing four targets."""
        from combat_trial_guard import validated_trial_policy
        parts = group_review_parts(4, 4, scope=FOUR_SCOPE)
        original = copy.deepcopy(parts[0]['policy'])
        parts[0]['policy'] = trial_policy(FOUR_SCOPE, source_stale_recovery=True)
        self.assertEqual(binding(parts)['policy'], parts[0]['policy'])
        for mutate in (lambda p:p.update(version=2), lambda p:p.pop('sourceStaleRecoveryPolicy'),
                       lambda p:p['sourceStaleRecoveryPolicy'].update(maximumRecoveries=2),
                       lambda p:p.update(sourceStaleRecoveryPolicy=None), lambda p:p.update(maximumSeconds=6)):
            changed = copy.deepcopy(parts)
            mutate(changed[0]['policy'])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                binding(changed)
        for scope in (SINGLE_SCOPE, GROUP_SCOPE):
            with self.assertRaises(ValueError):
                trial_policy(scope, source_stale_recovery=True)
        self.assertEqual(validated_trial_policy(dict(combatScope=FOUR_SCOPE, maximumEnemyBarCandidates=4,
            policy=original)), original)

    def test_trigger_requires_exact_same_source_drained_history_and_no_contradiction(self):
        """Publication races, dropped/foreign receipts and active native state cannot be erased by a later ACK."""
        mutations = (
            lambda f:f['worldReadiness'].update(epoch=3),
            lambda f:f['worldReadiness'].update(sourceFrameId=67),
            lambda f:f['worldReadiness'].update(sourceFrame=dict(f['sourceFrame'], captureEpoch='foreign')),
            lambda f:f.update(receipts=[dict(requestId='foreign')]),
            lambda f:f.update(droppedReceipts=1),
            lambda f:f.update(executionContext=dict(active=dict(requestId='foreign'), trackedState=dict(heldKeys=[]), telemetryComplete=True, evictedEvents=0)),
            lambda f:f.update(executionContext=dict(active=None, trackedState=dict(heldKeys=['LBUTTON']), telemetryComplete=True, evictedEvents=0)),
            lambda f:f['combatEvidence'].update(playerHealthFractionEstimate=.90),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.setup_guard(through=9)
                row = copy.deepcopy(self.data['events'][9]); mutate(row['frame'])
                state = self.apply_original(row)['state']
                self.assertIsNotNone(state['trip'])
                self.assertFalse(state['evidenceReady'])
        self.setup_guard(through=9)
        row = copy.deepcopy(self.data['events'][9]); row['frame']['worldReadiness']['reason'] = 'game_window_not_foreground'
        state = self.apply_original(row)['state']
        self.assertNotEqual(state['phase'], 'awaitingStaleRelease')
        self.assertFalse(state['evidenceReady'])

    def test_pending_or_armed_gap_cannot_enter_reacquisition(self):
        """A missing terminal receipt or post-release drain never becomes retry authority."""
        for through in (4, 5, 6, 7):
            with self.subTest(through=through):
                self.setup_guard(through=through)
                row = copy.deepcopy(self.data['events'][9])
                state = self.apply_original(row)['state']
                self.assertIsNotNone(state['trip'])
                self.assertEqual(state['sourceStaleRecovery']['used'], 0)

    def test_release_requires_request_owner_lease_exact_epoch_and_empty_native_state(self):
        """All ACK counterexamples stop with no post-release authority, including an omitted request."""
        changes = (
            lambda r:r['response'].update(type='stopped'),
            lambda r:r.update(payloadBytes=1),
            lambda r:r['response']['worldReadiness'].update(epoch=4),
            lambda r:r['response']['worldReadiness'].update(sourceFrameId=1),
            lambda r:r['response']['worldReadiness'].update(sourceCapturedAtMs=r['response']['serverNowMs'] + 1),
            lambda r:r['response']['worldReadiness'].update(reason='game_window_not_foreground'),
            lambda r:r['response']['worldReadiness']['sourceFrame'].update(captureEpoch='foreign'),
            lambda r:r['response'].update(receipts=[dict(requestId='lost')]),
            lambda r:r['response'].update(droppedReceipts=1),
            lambda r:r['response']['executionContext'].update(active=dict(requestId='other')),
            lambda r:r['response']['executionContext']['trackedState'].update(heldKeys=['LBUTTON']),
            lambda r:r['response']['executionContext']['trackedState'].update(releaseOutcome='failed'),
            lambda r:r['response']['executionContext'].update(telemetryComplete=False),
        )
        for mutate in changes:
            with self.subTest(mutate=mutate):
                self.setup_guard()
                state = self.release(mutate)['state']
                self.assertIsNotNone(state['trip'])
                self.assertFalse(state['evidenceReady'])
        self.setup_guard()
        self.assertIsNotNone(self.release(request=False)['state']['trip'])
        for identity in ('owner', 'lease'):
            self.setup_guard()
            owner, hello = copy.deepcopy(self.authority['owner']), copy.deepcopy(self.data['hello'])
            if identity == 'owner': owner['child']['instanceNonce'] = 'foreign'
            else: hello['sessionId'] = 'foreign'
            event = self.guard.request_stale_release(owner, hello, self.trace[-1]['clientTimeNs'] + 1)
            self.assertEqual(event['state']['trip']['reason'], 'invalidReacquisitionReleaseRequest')

    def test_unknown_menu_source_health_and_target_failures_remain_terminal(self):
        """Only known own-release confirmation may wait; unknown observations are never skipped."""
        changes = (
            lambda f:f.pop('worldReadiness'),
            lambda f:f['worldReadiness'].update(epoch=4),
            lambda f:f['worldReadiness'].update(reason='menu_open'),
            lambda f:f['worldReadiness']['sourceFrame'].update(captureEpoch='foreign'),
            lambda f:f['combatEvidence'].update(state='unavailable', reason='recognition_failed',
                playerHealthColor='unknown', playerHealthFractionEstimate=None, playerHealthMatchingPixels=0, enemyBarCandidates=[]),
            lambda f:f['combatEvidence'].update(playerHealthColor='unknown', playerHealthFractionEstimate=None),
            lambda f:f['combatEvidence'].update(enemyBarCandidates=[]),
            lambda f:f.update(receipts=[dict(requestId='foreign')]),
        )
        for mutate in changes:
            with self.subTest(mutate=mutate):
                self.setup_guard(); self.release()
                state = self.observe_successor(mutate=mutate)['state']
                self.assertIsNotNone(state['trip'])
                self.assertFalse(state['evidenceReady'])

    def test_well_formed_unknown_native_evidence_cannot_be_skipped_during_recovery(self):
        """Reach the pending recovery rule with a valid native unavailable shape, not malformed positive fields."""
        self.setup_guard(); self.release()
        def unavailable(current):
            current['combatEvidence'].update(state='unavailable', reason='recognition_failed',
                playerHealthColor='unknown', playerHealthFractionEstimate=None, playerHealthMatchingPixels=0, enemyBarCandidates=[])
        event = self.observe_successor(mutate=unavailable)
        self.assertEqual(event['state']['trip']['validationError'], 'Combat reacquisition lost known native HUD evidence')

    def test_ack_barrier_and_stale_health_do_not_count_as_fresh_confirmation(self):
        """Neither an old positive HUD nor the release's in-flight capture satisfies the two-source barrier."""
        self.setup_guard(); self.release()
        self.assertEqual(self.observe_successor(offset=59)['state']['confirmationSources'], 0)
        self.assertEqual(self.observe_successor(70, offset=121, age=151)['state']['confirmationSources'], 0)
        self.assertFalse(self.guard.snapshot()['evidenceReady'])
        self.setup_guard(); self.release()
        current, now = self.successor(offset=0)
        barrier = self.data['cleanupRelease']['response']['serverNowMs']
        current['capturedAtMs'] = barrier + 5
        current['worldReadiness'].update(ready=False, reason='world_observation_invalidated', sourceCapturedAtMs=barrier + 5)
        current['frameWorldReadiness'] = copy.deepcopy(current['worldReadiness'])
        current['inputAvailable'] = False
        current['combatEvidence'].update(state='unavailable', reason='world_not_ready',
            playerHealthColor='unknown', playerHealthFractionEstimate=None, playerHealthMatchingPixels=0, enemyBarCandidates=[])
        event = self.guard.observe(current, now, round_trip_ms=.5)
        self.assertIsNone(event['state']['trip'])
        self.assertFalse(event['state']['evidenceReady'])
        current['worldReadiness']['sourceFrame']['freshnessAtMs'] = barrier + 1
        self.assertIsNotNone(self.guard.observe(current, now + 1, round_trip_ms=.5)['state']['trip'])

    def test_positive_ready_gates_cannot_hide_observed_input_unavailability(self):
        """The separately sampled native focus/window availability cannot disappear during reacquisition."""
        for value in (False, None, 0, 'false', 'missing'):
            with self.subTest(value=value):
                self.setup_guard(); self.release()
                def unavailable(current):
                    if value == 'missing':
                        current.pop('inputAvailable')
                    else:
                        current['inputAvailable'] = value
                event = self.observe_successor(mutate=unavailable)
                self.assertEqual(event['state']['trip']['reason'], 'invalidNativeEvidence')
                self.assertIn('availability', event['state']['trip']['validationError'])
                self.assertEqual(event['state']['sourceStaleRecovery']['completed'], [])

    def test_frame_specific_confirmation_can_wait_behind_newer_current_readiness(self):
        """The native capture/resize race has no input authority and cannot count as fresh positive HUD."""
        self.setup_guard(); self.release()
        current, now = self.successor()
        current['frameWorldReadiness'].update(ready=False, reason='world_confirming')
        current['inputAvailable'] = False
        current['combatEvidence'].update(state='unavailable', reason='world_not_ready',
            playerHealthColor='unknown', playerHealthFractionEstimate=None, playerHealthMatchingPixels=0, enemyBarCandidates=[])
        event = self.guard.observe(current, now, round_trip_ms=.5)
        self.assertIsNone(event['state']['trip'])
        self.assertEqual(event['state']['confirmationSources'], 0)
        self.assertFalse(event['state']['evidenceReady'])
        current['frameWorldReadiness']['reason'] = 'world_hud_missing'
        self.assertIsNotNone(self.guard.observe(current, now + 1, round_trip_ms=.5)['state']['trip'])

    def test_second_gap_and_original_deadline_never_renew_authority(self):
        """One recovery is spent on its first attempt; no source can refresh the original five-second clock."""
        self.setup_guard(); self.release(); self.observe_successor(); self.observe_successor(70, offset=121)
        current = copy.deepcopy(self.guard.snapshot()['lastObservation']['frame'])
        at = current['sourceFrame']['freshnessAtMs']
        current.update(serverNowMs=at + 160, sourceFrameAgeMs=160, inputAvailable=False)
        current['worldReadiness'].update(ready=False, epoch=4, reason='world_observation_stale', checkedAtMs=at + 151)
        event = self.guard.observe(current, self.trace[-1]['clientTimeNs'] + 160_000_000, round_trip_ms=.5)
        self.assertIsNotNone(event['state']['trip'])
        self.setup_guard(); deadline = self.guard.snapshot()['deadlineNs']
        self.guard.tick(deadline)
        with self.assertRaises(CombatTrialStop):
            self.release(lambda row: row.update(clientTimeNs=deadline + 1))
        self.assertEqual(self.guard.snapshot()['trip']['reason'], 'trialDeadline')
        self.assertEqual(self.guard.snapshot()['deadlineNs'], deadline)

    def test_replay_rejects_missing_request_changed_ack_or_deleted_history_reset(self):
        """Recovery and the existing history heuristic are explicit independently replayed transitions."""
        from audit_combat_trial import replay_events
        self.setup_guard(); self.release(); self.observe_successor(); self.observe_successor(70, offset=121)
        now = self.trace[-1]['clientTimeNs'] + 1
        accepted = self.data['events'][4]['clientTimeNs'] + 1
        self.trace.append(self.guard.record_existing_history_reset(accepted, now))
        state = replay_events(self.authority, self.data['hello'], self.trace)['state']
        self.assertTrue(state['sourceStaleRecovery']['existingHistoryResets'][0]['afterReacquisition'])
        for kind in ('combatTrialReacquisitionRequest', 'combatTrialHistoryGapReset'):
            changed = [copy.deepcopy(row) for row in self.trace if row['type'] != kind]
            if kind == 'combatTrialHistoryGapReset':
                current, after = self.successor(71, offset=181)
                changed.append(self.guard.observe(current, after, round_trip_ms=.5))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                replay_events(self.authority, self.data['hello'], changed)
        changed = copy.deepcopy(self.trace)
        next(row for row in changed if row['type'] == 'combatTrialRelease' and row['reason'] == 'sourceStaleReacquisition')['response']['worldReadiness']['epoch'] = 4
        with self.assertRaises(ValueError): replay_events(self.authority, self.data['hello'], changed)




def ground_review_parts():
    """Use real synthetic PNG/crops and explicit offline corridor review, never live authority."""
    from test_encounter_approach import review_parts as corridor_parts
    from native_ground_control import CAPABILITY as GROUND
    from combat_trial_guard import GROUND_PROFILE
    parts = list(corridor_parts())
    goal = canonical(dict(instruction='Attack the nearby enemy with normal attacks.'))
    parts[0].update(kind=REVIEW_KIND, sceneLabel='enemy-visible', attacksAllowed=['LBUTTON'],
        policy=trial_policy(FOUR_SCOPE, ground_combat=True), controlProfile=GROUND_PROFILE,
        goalSha256=hashlib.sha256(goal).hexdigest(), **scope_fields(FOUR_SCOPE))
    parts[2]['nativeGroundControlGate'] = dict(type='groundControlLayout', requiredForInput=True,
                                              capability=copy.deepcopy(GROUND))
    return parts + [goal]


def ground_hello():
    """Declare the actual native read-only geometry/ground protocol with no bridge construction."""
    from native_ground_control import CAPABILITY as GROUND
    from navigation_profiles import SCOUT_PROFILE
    value = copy.deepcopy(HELLO)
    value.update(allowedKeys=['W', 'A', 'S', 'D', 'LBUTTON'],
                 navigationProfiles=[SCOUT_PROFILE], groundControlObservation=copy.deepcopy(GROUND))
    return value


def ground_proposal(keys=('W',), dx=0, dy=0, hold=50):
    """Keep the exact raw proposal; no test or controller normalizes it into allowed input."""
    return dict(parseValid=True, steps=[dict(keys=list(keys), mouseDx=dx, mouseDy=dy, durationMs=hold)])


class GroundCombatGuardTests(unittest.TestCase):
    """Exercise the explicit microtrial without model, native, UI or operating-system input."""

    @classmethod
    def setUpClass(cls):
        """Pin the common inert reviewed source before each isolated guard case."""
        cls.authority = binding(ground_review_parts())

    def setUp(self):
        """Anchor the original outer deadline before the later guard starts."""
        from test_encounter_approach import sample
        self.sample = sample
        self.guard = CombatTrialGuard(copy.deepcopy(self.authority), OWNER, ground_hello(), 50_000_000,
                                      outer_deadline_ns=5_000_000_000)
        self.current = sample(2, 200)
        self.guard.observe(sample(1, 100), 110_000_000, round_trip_ms=1)
        event = self.guard.observe(self.current, 210_000_000, round_trip_ms=1)
        self.assertEqual(event['state']['phase'], 'ready', event['state'])
        self.index, self.epoch = 2, 0

    def dispatch(self, proposed=None, now=None):
        """Reserve the exact inert request at a still-fresh current source."""
        now = int((self.current['serverNowMs'] + 5) * 1e6) if now is None else now
        return self.guard.prepare_action(self.current, ground_proposal() if proposed is None else proposed,
            'ground-' + str(self.guard.snapshot()['acceptedActions']), now, owner=OWNER, hello=ground_hello())

    def drain(self, proposed=None):
        """Retain exact keys/camera, terminal ACK, release and a fresh post-response source."""
        event = self.dispatch(proposed)
        args, at = event['arguments'], self.current['sourceFrame']['freshnessAtMs'] + 20
        self.guard.transmitting(event['clientTimeNs'] + 1)
        response = dict(type='accepted', requestId=args['requestId'], receivedAtMs=at - 1, acceptedAtMs=at)
        self.guard.admission(response, 0, int((at + 1) * 1e6))
        receipt = dict(requestId=args['requestId'], frameId=args['frameId'], modelId='open-p2p',
            status='completed', reason='horizon_complete', acceptedAtMs=at, endedAtMs=at + 50,
            appliedSteps=[dict(index=0, startedAtMs=at + 1,
                **{key:args['steps'][0][key] for key in ('keys', 'mouseDx', 'mouseDy')})])
        self.guard.receipt(receipt, int((at + 55) * 1e6))
        self.epoch += 1
        release = dict(type='released', serverNowMs=at + 55, worldReadiness=dict(ready=False, epoch=self.epoch))
        self.guard.acknowledge_release(release, 0, int((at + 56) * 1e6), 'completedCombatPulse')
        self.index += 1
        self.current = self.sample(self.index, at + 115, epoch=self.epoch)
        self.guard.observe(self.current, int(self.current['serverNowMs'] * 1e6), round_trip_ms=1)
        self.assertIsNone(self.guard.snapshot()['trip'])
        return args, receipt

    def test_explicit_review_and_legacy_policies_remain_separate(self):
        """No observation count or missing half of the descriptor can confer movement authority."""
        from combat_trial_guard import validate_binding, ground_combat_enabled
        self.assertTrue(ground_combat_enabled(self.authority))
        for scope in (SINGLE_SCOPE, GROUP_SCOPE, FOUR_SCOPE):
            self.assertEqual(trial_policy(scope)['maximumActions'], 3)
            self.assertNotIn('groundCombatPolicy', trial_policy(scope))
        for mutate in (lambda x:x.pop('controlProfile'), lambda x:x['policy'].pop('groundCombatPolicy'),
                       lambda x:x.pop('groundCombat'), lambda x:x['policy'].update(maximumActions=21),
                       lambda x:x.update(controlProfile='anything-else')):
            changed = copy.deepcopy(self.authority); mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): validate_binding(changed)
        with self.assertRaises(ValueError): trial_policy(FOUR_SCOPE, ground_combat=True, source_stale_recovery=True)
        with self.assertRaises(ValueError): trial_policy(GROUP_SCOPE, ground_combat=True)

    def test_numeric_admission_and_existing_eight_point_drop(self):
        """Admission is90%; native color/estimate still has the same8-point combat stop."""
        parts = ground_review_parts(); parts[0].update(inspectedHealth=900, inspectedMaximumHealth=1000)
        self.assertEqual(binding(parts)['baselineHealthFraction'], .9)
        parts[0]['inspectedHealth'] = 899
        with self.assertRaises(ValueError): binding(parts)
        event = self.guard.observe(self.sample(3, 250, health=.92), 260_000_000, round_trip_ms=1)
        self.assertEqual(event['state']['trip']['reason'], 'healthFractionDrop')

    def test_shape_is_exact_and_never_rewrites_raw_proposals(self):
        """Only nonopposing movement, pure attack, or isolated horizontal camera is admitted."""
        allowed = [ground_proposal(('W',)), ground_proposal(('W','A')), ground_proposal(('S','D')),
                   ground_proposal(('LBUTTON',)), ground_proposal((), dx=50), ground_proposal((), dx=-50)]
        for item in allowed:
            self.assertIsNone(proposal_rejection(item, ground_combat=True))
            if item['steps'][0]['keys'] != ['LBUTTON']:
                self.assertIsNotNone(proposal_rejection(item))
        denied = [ground_proposal(('SPACE',)), ground_proposal(('E',)), ground_proposal(('Q',)),
                  ground_proposal(('W','S')), ground_proposal(('A','D')), ground_proposal(('W','A','D')),
                  ground_proposal(('W','LBUTTON')), ground_proposal(('LBUTTON',), dx=1),
                  ground_proposal(('W',), dx=1), ground_proposal((), dy=1), ground_proposal((), dx=51),
                  ground_proposal(()), ground_proposal(hold=49), ground_proposal(hold=100)]
        for item in denied:
            before=canonical(item)
            with self.subTest(item=item):
                self.assertIsNotNone(proposal_rejection(item, ground_combat=True))
                self.assertEqual(canonical(item), before)

    def test_one_pending_and_exact_camera_receipt_and_cumulative_reservation(self):
        """A nonzero horizontal footprint is retained exactly and all attempts consume finite budget."""
        for index in range(4):
            args, receipt=self.drain(ground_proposal((), dx=50 if index % 2 == 0 else -50))
            self.assertEqual(receipt['appliedSteps'][0]['mouseDx'], args['steps'][0]['mouseDx'])
        self.assertEqual(self.guard.snapshot()['groundCombat']['cumulativeAbsoluteMouseDxReserved'], 200)
        self.assertEqual(self.dispatch(ground_proposal((), dx=1))['reason'], 'groundCameraBudgetExceeded')
        self.dispatch()
        self.assertEqual(self.dispatch()['reason'], 'awaitingTerminalOrEvidence')

    def test_maximum_twenty_and_completion_requires_real_drain(self):
        """Twenty is an upper bound; completion follows actual terminal/release/post-source joins."""
        for _ in range(20): self.drain()
        now=int(self.current['serverNowMs'] * 1e6)
        self.assertFalse(self.guard.snapshot()['trialComplete'])
        end=self.guard.complete_ground_window(now)
        self.assertEqual(end['state']['completedActions'],20)
        self.assertTrue(end['state']['trialComplete'])
        self.assertIsNone(end['state']['pending'])
        self.assertFalse(end['state']['armed'])

    def test_window_can_end_drained_with_zero_without_claiming_attacks(self):
        """The original cutoff ends a fresh safe window without inventing an action or damage."""
        self.current=self.sample(3, 4350)
        self.guard.observe(self.current,4_360_000_000,round_trip_ms=1)
        end=self.guard.complete_ground_window(4_360_000_000)
        self.assertEqual(end['state']['acceptedActions'],0)
        self.assertFalse(end['state']['damageVerified'])
        self.assertFalse(end['state']['killVerified'])
        self.assertEqual(end['state']['deadlineNs'],5_000_000_000)

    def test_final_send_rechecks_original_headroom_after_preparation(self):
        """A fresh proposal can lose drain headroom before the wire call; it must stop locally."""
        self.current=self.sample(3,4330)
        self.guard.observe(self.current,4_340_000_000,round_trip_ms=1)
        self.dispatch(now=4_345_000_000)
        with self.assertRaises(CombatTrialStop): self.guard.transmitting(4_351_000_000)
        self.assertEqual(self.guard.snapshot()['trip']['reason'],'groundDrainHeadroomExpired')
        self.assertEqual(self.guard.snapshot()['acceptedActions'],0)
        self.assertNotIn('transmittedAtNs',self.guard.snapshot()['pending'])

    def test_pending_or_stale_final_drain_cannot_be_declared_success(self):
        """The650ms reserve is conservative, never a guarantee or deadline extension."""
        self.dispatch();self.guard.transmitting(216_000_000)
        self.assertIsNone(self.guard.complete_ground_window(4_400_000_000))
        self.assertEqual(self.guard.tick(5_000_000_000)['trip']['reason'],'trialDeadline')

    def test_ground_pose_target_and_foreign_source_fail_closed(self):
        """Positive danger, missing localization and route escape cannot become idle authority."""
        mutations=[lambda x:x['motionEvidence'].update(status='climbing',spaceKeyMatched=True),
            lambda x:x['navigationPose'].update(x=x['navigationPose']['x']+7),
            lambda x:x['navigationPose'].update(layerId='City_102'),
            lambda x:x['navigationPose'].update(frameId=99),lambda x:x.pop('groundControlEvidence'),
            lambda x:x['combatEvidence'].update(enemyBarCandidates=[])]
        for mutate in mutations:
            self.setUp(); row=self.sample(3,250);mutate(row)
            with self.subTest(mutate=mutate):
                self.assertIsNotNone(self.guard.observe(row,260_000_000,round_trip_ms=1)['state']['trip'])
        self.setUp();row=self.sample(3,250,age=150)
        event=self.guard.observe(row,400_000_000,round_trip_ms=1)
        self.assertFalse(event['state']['evidenceReady'])
        self.assertEqual(self.dispatch()['reason'],'awaitingTerminalOrEvidence')

    def test_review_cannot_strip_ground_gate_or_fabricate_crops_corridor(self):
        """Exact pixels, passive source evidence and fixed geometry are required before runtime."""
        changes=[lambda p:p[2].pop('nativeGroundControlGate'),lambda p:p[0].update(clearSurfaceCorridor=False),
            lambda p:p[0]['route']['points'][1].__setitem__(0,p[0]['route']['points'][0][0]+6.01),
            lambda p:p[1].update(inspectionMode='current-scene'),
            lambda p:p[2]['stableSamples'][0]['executionContext'].update(lastSequence=1)]
        for mutate in changes:
            parts=ground_review_parts();mutate(parts)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):binding(parts)



    def test_completed_projection_is_cached_without_losing_private_causal_proofs(self):
        """Only recurring public snapshots shrink; the original private release/frame/receipt stays complete."""
        from unittest.mock import patch
        import combat_trial_guard as module
        with patch.object(module,'ground_release_reference',wraps=module.ground_release_reference) as release_hash, \
                patch.object(module,'ground_frame_reference',wraps=module.ground_frame_reference) as frame_hash:
            self.drain()
            self.assertEqual((release_hash.call_count,frame_hash.call_count),(1,2))
            for _ in range(5):self.guard.snapshot()
            self.guard.observe(self.sample(self.index+1,self.current['capturedAtMs']+50,epoch=self.epoch),
                int((self.current['serverNowMs']+50)*1e6),round_trip_ms=1)
            self.assertEqual((release_hash.call_count,frame_hash.call_count),(1,2))
        private=self.guard._completed[0];public=self.guard.snapshot()['completed'][0]
        self.assertIn('combatEvidence',private['frame']);self.assertIn('groundControlEvidence',private['postFrame'])
        self.assertIn('response',private['release']);self.assertEqual(private['receipt'],public['receipt'])
        self.assertEqual(public['frame']['kind'],'ground-combat-frame-reference-v1')
        self.assertEqual(public['release']['kind'],'ground-combat-release-reference-v1')
        public['frame']['sha256']='0'*64
        self.assertNotEqual(public['frame'],self.guard.snapshot()['completed'][0]['frame'])

    def test_reviewed_anchor_cannot_drift_before_the_first_owned_request(self):
        """Earlier valid polls do not permit unowned displacement before any model input."""
        from test_encounter_approach import START
        shifted=self.sample(3,250,point=(START[0]+1,START[1]))
        self.assertEqual(self.guard.observe(shifted,260_000_000,round_trip_ms=1)['state']['trip']['reason'],'invalidNativeEvidence')
        self.setUp();self.drain()
        moved=self.sample(self.index+1,self.current['capturedAtMs']+50,epoch=self.epoch,point=(START[0]+1,START[1]))
        self.assertIsNone(self.guard.observe(moved,int(moved['serverNowMs']*1e6),round_trip_ms=1)['state']['trip'])

    def test_camera_terminal_footprint_cannot_be_substituted_with_a_key(self):
        """The actual receipt must repeat the admitted horizontal-only step exactly."""
        event=self.dispatch(ground_proposal((),dx=50));args=event['arguments']
        self.guard.transmitting(216_000_000)
        response=dict(type='accepted',requestId=args['requestId'],receivedAtMs=219,acceptedAtMs=220)
        self.guard.admission(response,0,221_000_000)
        wrong=dict(requestId=args['requestId'],frameId=args['frameId'],modelId='open-p2p',status='completed',
            reason='horizon_complete',acceptedAtMs=220,endedAtMs=270,
            appliedSteps=[dict(index=0,keys=['W'],mouseDx=50,mouseDy=0,startedAtMs=221)])
        state=self.guard.receipt(wrong,275_000_000)['state']
        self.assertIsNotNone(state['trip']);self.assertEqual(state['completedActions'],0)

    def test_no_native_target_cannot_become_a_successful_idle_ground_window(self):
        """The zero-action outcome still requires fresh positive target/ground/pose admission."""
        self.guard=CombatTrialGuard(copy.deepcopy(self.authority),OWNER,ground_hello(),50_000_000,outer_deadline_ns=5_000_000_000)
        for index,at in ((1,100),(2,4350)):
            self.guard.observe(self.sample(index,at,candidates=0),int((at+10)*1e6),round_trip_ms=1)
        self.assertIsNone(self.guard.complete_ground_window(4_360_000_000))
        self.assertEqual(self.guard.tick(5_000_000_000)['trip']['reason'],'trialDeadline')

    def test_actual_combat07_raw_shapes_remain_unedited_and_not_live_authority(self):
        """Replay37 retained raw proposals only: no old pixels acquire new ground/corridor authority."""
        # Exact decision-summary SHA543813ba24e5c34426c78e5b9981cff486f7e5a04b2bc6e6d20f49b021e1e1f3.
        steps=[[{'durationMs': 50, 'keys': ['D', 'W'], 'mouseDx': 0, 'mouseDy': 3}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['A', 'W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': -34, 'mouseDy': 41}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['SPACE'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': -10, 'mouseDy': 3}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['SPACE'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': -3, 'mouseDy': -1}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 1, 'mouseDy': -1}], [{'durationMs': 50, 'keys': ['A', 'W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['SPACE', 'W'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 23, 'mouseDy': -31}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['SPACE', 'W'], 'mouseDx': -2, 'mouseDy': -2}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 10, 'mouseDy': 1}], [{'durationMs': 50, 'keys': ['A'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['A'], 'mouseDx': 0, 'mouseDy': 0}], [{'durationMs': 50, 'keys': ['LBUTTON'], 'mouseDx': 0, 'mouseDy': 0}]]
        before=canonical(steps)
        results=[proposal_rejection(dict(parseValid=True,steps=row),ground_combat=True) for row in steps]
        self.assertEqual((len(results),results.count(None)),(37,10))
        self.assertEqual(sum(proposal_rejection(dict(parseValid=True,steps=row)) is None for row in steps),1)
        self.assertEqual(canonical(steps),before)
        # Combat07 has no reviewed ground/pose corridor; the old binding itself remains legacy-only.
        self.assertNotIn('groundCombat',binding())


if __name__ == '__main__':
    unittest.main()
