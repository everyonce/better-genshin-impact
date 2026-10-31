"""Inert tests for separate combat authority, strict dispatch and complete terminal drain."""
import copy
import hashlib
import json
import unittest

from combat_trial_guard import (CombatTrialGuard, CombatTrialStop, PROFILE, REVIEW_KIND,
                               bind_review, canonical, proposal_rejection, trial_policy)
from native_combat import CAPABILITY, METHOD


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


def proposal(duration=100):
    """Represent one unchanged policy normal-attack proposal."""
    return dict(parseValid=True, steps=[dict(keys=['LBUTTON'], mouseDx=0, mouseDy=0, durationMs=duration)])


class CombatTrialGuardTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
