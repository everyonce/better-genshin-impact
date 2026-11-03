"""Inert movement-only approach admission, dispatch, obstacle and exact cleanup tests."""
import copy
from contextlib import ExitStack
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import encounter_approach as approach
from hybrid_navigation import START as NATIVE_START, END as NATIVE_END
from hybrid_routes import SCOUT_GRASS_ROUTE, route_heading
from native_combat import CAPABILITY
from native_ground_control import CAPABILITY as GROUND
from test_combat_trial_guard import OWNER, HELLO, frame as hud_frame
from test_native_ground_control import attach_ground, ground_png
from test_navigation_profiles import route_capability


# Synthetic offline geometry; these coordinates are never a reviewed live route.
START = (-1172.7, 2209.6)
END = (-1167.7, 2209.6)


def sample(index=1, at=100, *, point=START, yaw=None, **options):
    """Combine faithful native HUD/ground fixtures with independent map bearings."""
    frame = attach_ground(hud_frame(index, at, health=options.pop('health', 1),
                                    candidates=options.pop('candidates', 4), **options))
    for offset, bar in enumerate(frame['combatEvidence']['enemyBarCandidates']):
        bar['x'] = 300 + offset * 200
    pose = dict(state='valid', frameId=index, x=point[0], y=point[1], positionConfidence=.996,
                yawConfidence=.6, layerId='MapBack_2', mouseToStart=350, mouseToEnd=0)
    pose.update(yawDegrees=route_heading(pose, END) if yaw is None else yaw,
                headingToStartDegrees=int(route_heading(pose, NATIVE_START)),
                headingToEndDegrees=int(route_heading(pose, NATIVE_END)))
    frame.update(navigationPose=pose, motionEvidence=dict(status='normal', spaceKeyMatched=False),
                 executionContext=dict(lastSequence=0), width=192, height=192, pixelFormat='rgb24',
                 payloadBytes=192 * 192 * 3)
    return frame


def review_parts():
    """Construct an explicit synthetic review bound to a real inert PNG and original source samples."""
    frames = [sample(index, index * 100) for index in (1, 2, 3)]
    selected = frames[1]
    image = ground_png()
    sha = approach.digest(image)
    route = dict(version=1, profileId=approach.SCOUT_PROFILE, points=[list(START), list(END)])
    review = dict(kind=approach.REVIEW_KIND, policy=approach.policy(), owner=copy.deepcopy(OWNER),
                  clearSurfaceCorridor=True, fenceOpeningReviewed=True, inspectionNote='Synthetic inert open corridor.',
                  attacksAllowed=False, inspectedHealth=4015, inspectedMaximumHealth=4015,
                  inspectedVisibleEnemyCount=4, route=route, imageName='source.png', imageSha256=sha,
                  reviewedAtUnixNs=1_000_000_000)
    plan = dict(owner=copy.deepcopy(OWNER), enableInput=False, modelLoaded=False, anchor=list(START),
                navigationProfile=approach.SCOUT_PROFILE)
    scene = dict(status='completed', inputEnabled=False, modelLoaded=False, ownerIdleMinimizedAfter=True,
                 nativeCombatObservation=copy.deepcopy(CAPABILITY), nativeGroundControlObservation=copy.deepcopy(GROUND),
                 capability=route_capability(SCOUT_GRASS_ROUTE), selectedImageName='source.png', selectedImageSha256=sha,
                 qualifiedImageFrameId=2, observations=copy.deepcopy(frames), stableSamples=copy.deepcopy(frames))
    sidecar = {key: copy.deepcopy(selected[key]) for key in ('frameId', 'sourceFrame', 'sourceWidth', 'sourceHeight',
                                                          'capturedAtMs', 'sourceTimestampKind')}
    sidecar.update(imageSha256=sha, worldReadiness=copy.deepcopy(selected['frameWorldReadiness']),
                   freshnessContractVersion=2, evidence='WorldHud')
    return review, plan, scene, sidecar, image


def binding():
    """Create only inert authority; no runtime, process, files or model are touched."""
    return approach.bind_review(*review_parts(), expected_owner=OWNER)


def release_ack(at=810, epoch=1):
    """Model aggregate release honestly: held state empty, physical execution still uncertain."""
    return dict(type='released', serverNowMs=at, worldReadiness=dict(ready=False, epoch=epoch, sourceFrame=dict(captureEpoch='live')),
                executionContext=dict(telemetryComplete=True, active=None, trackedState=dict(heldKeys=[],
                    executionUncertain=True, telemetryIncomplete=False, releaseOutcome='returned_unverified')),
                receipts=[], droppedReceipts=0)


def complete(controller, request, *, accepted_offset=10):
    """Join one exact fake accepted response and applied50ms terminal receipt."""
    source_at = request['startBeforeMs'] - 150
    controller.transmitting(controller.pending['preparedAtClientNs'])
    accepted = dict(type='accepted', requestId=request['requestId'], acceptedAtMs=source_at + accepted_offset)
    controller.admission(accepted, b'')
    receipt = dict(requestId=request['requestId'], modelId=approach.MODEL_ID, frameId=request['frameId'],
                   status='completed', reason='horizon_complete', acceptedAtMs=accepted['acceptedAtMs'],
                   endedAtMs=accepted['acceptedAtMs'] + 50,
                   appliedSteps=[dict(index=0, startedAtMs=accepted['acceptedAtMs'],
                                      **{key: request['steps'][0][key] for key in ('keys', 'mouseDx', 'mouseDy')})])
    controller.intake_receipts(dict(receipts=[receipt], droppedReceipts=0))
    return receipt


class Clock:
    """Deterministic inert client clock, advanced only by simulated RPC/sleep."""
    def __init__(self):
        self.now = 1_000_000_000

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += round(seconds * 1e9)


class FakeBridge:
    """No OS handle or input; synthetic positions move only after recorded fake W dispatches."""
    def __init__(self, clock, *, stuck=False, change=None):
        self.hello = copy.deepcopy(HELLO)
        self.clock, self.stuck, self.change = clock, stuck, change
        self.number = 0
        self.position = 0
        self.pending = []
        self.epoch = 0
        self.calls = []

    def request(self, command, **arguments):
        self.calls.append((command, copy.deepcopy(arguments)))
        if command == 'frame':
            self.clock.sleep(.1)
            self.number += 1
            frame = sample(self.number, self.number * 100, point=(START[0] + self.position, START[1]), epoch=self.epoch)
            frame['receipts'], self.pending = self.pending, []
            if self.change:
                self.change(frame, self)
            return frame, bytes([30, 45, 65]) * (192 * 192)
        if command == 'action':
            step = arguments['steps'][0]
            at = self.number * 100 + 10
            self.pending.append(dict(requestId=arguments['requestId'], modelId=approach.MODEL_ID,
                frameId=arguments['frameId'], status='completed', reason='horizon_complete', acceptedAtMs=at,
                endedAtMs=at + 50, appliedSteps=[dict(index=0, startedAtMs=at,
                    **{key: step[key] for key in ('keys', 'mouseDx', 'mouseDy')})]))
            if step['keys'] == ['W'] and not self.stuck:
                self.position += .8
            return dict(type='accepted', requestId=arguments['requestId'], acceptedAtMs=at), b''
        if command == 'release':
            self.epoch += 1
            response = release_ack(self.number * 100 + 20, self.epoch)
            response['receipts'], self.pending = self.pending, []
            return response, b''
        if command == 'stop':
            return dict(type='stopped', receipts=[]), b''
        raise AssertionError(command)


class ApproachTests(unittest.TestCase):
    """Verify independent approach limits without changing old scout/combat/navigation contracts."""

    @classmethod
    def setUpClass(cls):
        cls.bound = binding()

    def ready(self):
        controller = approach.ApproachController(self.bound, HELLO, 0)
        for index in (1, 2, 3):
            controller.observe(sample(index, index * 100), index * 100_000_000, 1)
        self.assertEqual(controller.navigation.phase, 'walking')
        return controller

    def test_policy_is_fixed_detached_and_movement_only(self):
        policy = approach.policy()
        policy['allowedKeys'].append('LBUTTON')
        self.assertEqual(approach.policy()['allowedKeys'], ['W'])
        self.assertEqual(approach.policy()['sourceFreshnessMs'], 150)
        self.assertEqual(approach.policy()['maximumHealthFractionDrop'], .02)

    def test_geometry_rejects_overlap_long_route_and_surface_boundary(self):
        for points in ((START, (START[0] + 4, START[1])), (START, (START[0] + 6.01, START[1])),
                       ((-1349.5, 2200), (-1344.5, 2200))):
            route = dict(version=1, profileId=approach.SCOUT_PROFILE, points=points)
            with self.subTest(points=points), self.assertRaises(ValueError):
                approach.route_geometry(route)

    def test_review_requires_clear_opening_and_exact_original_pixels(self):
        for key, value in (('fenceOpeningReviewed', False), ('clearSurfaceCorridor', False),
                           ('attacksAllowed', True), ('inspectedVisibleEnemyCount', 5)):
            parts = list(review_parts())
            parts[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                approach.bind_review(*parts)
        parts = list(review_parts())
        parts[3]['sourceFrame']['captureEpoch'] = 'substituted'
        with self.assertRaises(ValueError):
            approach.bind_review(*parts)

    def test_repeated_selected_row_cannot_change_pose_hud_ground_or_readiness(self):
        for key in ('navigationPose', 'combatEvidence', 'groundControlEvidence', 'frameWorldReadiness'):
            parts = list(review_parts())
            duplicate = copy.deepcopy(parts[2]['observations'][1])
            if key == 'navigationPose':
                duplicate[key]['x'] += .1
            elif key == 'combatEvidence':
                duplicate[key]['playerHealthFractionEstimate'] = .99
            elif key == 'groundControlEvidence':
                duplicate[key]['groundControlsConfirmed'] = False
            else:
                duplicate[key]['ready'] = False
            parts[2]['observations'].append(duplicate)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'immutable evidence'):
                approach.bind_review(*parts)
        parts = list(review_parts())
        duplicate = copy.deepcopy(parts[2]['observations'][1])
        duplicate.update(serverNowMs=duplicate['serverNowMs'] + 5, sourceFrameAgeMs=duplicate['sourceFrameAgeMs'] + 5)
        parts[2]['observations'].append(duplicate)
        approach.bind_review(*parts)

    def test_inspection_only_capture_cannot_be_promoted(self):
        parts = list(review_parts())
        parts[1].update(inspectionMode='current-scene-inspection-v1', navigationReviewAllowed=False)
        with self.assertRaises(ValueError):
            approach.bind_review(*parts)

    def test_review_freshness_uses_original_clocks(self):
        review = review_parts()[0]
        source = self.bound['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100
        approach.recent_review(review, self.bound, now_ns=review['reviewedAtUnixNs'] + 1, qpc_ns=source + 1)
        with self.assertRaises(ValueError):
            approach.recent_review(review, self.bound, now_ns=review['reviewedAtUnixNs'] + 121_000_000_000, qpc_ns=source + 1)

    def test_original_review_deadline_preserves_both_absolute_expiries(self):
        source = self.bound['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100
        review = self.bound['reviewedAtUnixNs']
        result = approach.original_review_deadline(self.bound, client_ns=source + 119_000_000_000,
                                                    wall_ns=review + 119_000_000_000)
        self.assertEqual(result, source + 120_000_000_000)
        later = approach.original_review_deadline(self.bound, client_ns=source + 121_000_000_000,
                                                   wall_ns=review + 121_000_000_000)
        self.assertEqual(result, later)

    def test_one_outstanding_exact_fifty_ms_and_native_start_deadline(self):
        controller = self.ready()
        request = controller.next_action(301_000_000)
        self.assertEqual(request['steps'], [dict(keys=['W'], mouseDx=0, mouseDy=0, durationMs=50)])
        self.assertEqual(request['startBeforeMs'], 450)
        self.assertIsNone(controller.next_action(302_000_000))
        complete(controller, request)
        self.assertIsNone(controller.pending)

    def test_dispatch_includes_transport_and_post_observation_delay(self):
        controller = self.ready()
        with self.assertRaisesRegex(RuntimeError, 'dispatch_source_stale'):
            controller.next_action(440_000_000)
        with self.assertRaises(RuntimeError):
            controller.observe(sample(4, 400), 441_000_000, 1)

    def test_deadline_cannot_be_renewed_by_waiting(self):
        controller = self.ready()
        with self.assertRaisesRegex(RuntimeError, 'approach_deadline'):
            controller.observe(dict(type='waiting'), 10_000_000_000, 0)

    def test_last_action_cannot_extend_the_ten_second_horizon(self):
        controller = self.ready()
        with self.assertRaisesRegex(RuntimeError, 'approach_dispatch_budget'):
            controller.next_action(9_900_000_000)

    def test_health_drop_at_exact_boundary_allowed_beyond_stops(self):
        controller = self.ready()
        controller.observe(sample(4, 400, health=.98), 400_000_000, 1)
        with self.assertRaisesRegex(RuntimeError, 'health_stop'):
            controller.observe(sample(5, 500, health=.9799), 500_000_000, 1)

    def test_candidate_count_and_red_health_fail_closed(self):
        for changed in (sample(4, 400, candidates=5), sample(4, 400)):
            if len(changed['combatEvidence']['enemyBarCandidates']) == 4:
                changed['combatEvidence']['playerHealthColor'] = 'red'
            with self.subTest(changed=changed['combatEvidence']['playerHealthColor']), self.assertRaises(RuntimeError):
                self.ready().observe(changed, 400_000_000, 1)

    def test_missing_ground_water_and_pose_are_terminal_while_armed(self):
        for changed in (sample(4, 400), attach_ground(sample(4, 400), water=True), sample(4, 400)):
            if changed['groundControlEvidence']['groundControlsConfirmed']:
                if changed['navigationPose']['state'] == 'valid' and changed is not None:
                    changed.pop('groundControlEvidence')
            with self.assertRaises(RuntimeError):
                self.ready().observe(changed, 400_000_000, 1)
        changed = sample(4, 400)
        changed['navigationPose']['state'] = 'unavailable'
        with self.assertRaises(RuntimeError):
            self.ready().observe(changed, 400_000_000, 1)

    def test_approach_corridor_is_narrower_than_native_planner(self):
        changed = sample(4, 400, point=(START[0] + 1, START[1] + 1.01))
        with self.assertRaisesRegex(RuntimeError, 'outside_reviewed_approach_corridor'):
            self.ready().observe(changed, 400_000_000, 1)

    def test_capture_world_epoch_and_same_frame_evidence_changes_stop(self):
        for changed in (sample(4, 400, capture='new'), sample(4, 400, epoch=1), sample(3, 300, health=.99)):
            with self.assertRaises(RuntimeError):
                self.ready().observe(changed, 400_000_000, 1)

    def test_short_target_absence_only_within_known_corridor(self):
        controller = self.ready()
        controller.observe(sample(4, 400, candidates=0), 400_000_000, 1)
        controller.observe(sample(5, 1000, candidates=0), 1_000_000_000, 1)
        with self.assertRaisesRegex(RuntimeError, 'target_absence_deadline'):
            controller.observe(sample(6, 1100, candidates=0), 1_100_000_000, 1)

    def test_duplicate_frame_cannot_hide_expiry_or_malformed_receipt(self):
        controller = self.ready()
        duplicate = sample(3, 300, age=151)
        with self.assertRaises(RuntimeError):
            controller.observe(duplicate, 400_000_000, 1)
        with self.assertRaises(ValueError):
            self.ready().intake_receipts(dict(receipts=[], droppedReceipts=1))

    def test_wrong_late_or_duplicate_receipt_rejected(self):
        controller = self.ready()
        request = controller.next_action(301_000_000)
        receipt = complete(controller, request)
        with self.assertRaises(ValueError):
            controller.intake_receipts(dict(receipts=[receipt]))
        controller = self.ready()
        request = controller.next_action(301_000_000)
        with self.assertRaises(ValueError):
            complete(controller, request, accepted_offset=150)

    def test_zero_duration_completed_and_backward_cancelled_receipts_rejected(self):
        for status, ended, steps in (('completed', 310, True), ('cancelled', 309, False)):
            controller = self.ready()
            request = controller.next_action(301_000_000)
            controller.transmitting(301_000_000)
            controller.admission(dict(type='accepted', requestId=request['requestId'], acceptedAtMs=310), b'')
            receipt = dict(requestId=request['requestId'], modelId=approach.MODEL_ID, frameId=3,
                           acceptedAtMs=310, endedAtMs=ended, status=status,
                           reason='horizon_complete' if status == 'completed' else 'client_release',
                           appliedSteps=[dict(index=0, startedAtMs=310, keys=['W'], mouseDx=0, mouseDy=0)] if steps else [])
            with self.subTest(status=status), self.assertRaises(ValueError):
                controller.intake_receipts(dict(receipts=[receipt]), final=True)

    def test_valid_native_cancellation_is_retained_before_terminal_stop(self):
        controller = self.ready()
        request = controller.next_action(301_000_000)
        controller.transmitting(301_000_000)
        controller.admission(dict(type='accepted', requestId=request['requestId'], acceptedAtMs=310), b'')
        receipt = dict(requestId=request['requestId'], modelId=approach.MODEL_ID, frameId=3,
                       acceptedAtMs=310, endedAtMs=320, status='cancelled', reason='world_source_expired', appliedSteps=[])
        with self.assertRaisesRegex(RuntimeError, 'cancelled_before_complete'):
            controller.intake_receipts(dict(receipts=[receipt]))
        self.assertEqual(list(controller.receipts), [request['requestId']])
        self.assertIsNone(controller.pending)

    def test_native_camera_is_horizontal_and_no_movement_chord(self):
        controller = self.ready()
        controller.observe(sample(4, 400, yaw=200), 400_000_000, 1)
        request = controller.next_action(401_000_000)
        self.assertEqual(request['steps'][0]['keys'], [])
        self.assertNotEqual(request['steps'][0]['mouseDx'], 0)
        self.assertEqual(request['steps'][0]['mouseDy'], 0)

    def test_action_cap_stops_before_eighty_first(self):
        controller = self.ready()
        controller.actions = 80
        with self.assertRaisesRegex(RuntimeError, 'action_limit'):
            controller.next_action(301_000_000)

    def test_endpoint_requires_acknowledged_exact_epoch_release(self):
        controller = self.ready()
        self.assertEqual(controller.observe(sample(4, 400, point=(END[0] - .8, END[1])), 400_000_000, 1), 'releaseRequired')
        with self.assertRaises(ValueError):
            controller.released(release_ack(420, 2), b'', endpoint=True)

    def test_fake_route_completes_once_with_release_and_original_receipts(self):
        clock = Clock()
        bridge = FakeBridge(clock)
        with tempfile.TemporaryDirectory() as temporary:
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
            self.assertEqual(report['status'], 'completed', report)
            self.assertTrue(report['navigationVerified'])
            self.assertTrue(report['receiptsComplete'])
            self.assertEqual(report['acceptedActions'], 5)
            self.assertEqual(report['navigation']['completedLegs'], 1)
            self.assertFalse(report['meleeArrivalVerified'])
            self.assertFalse(report['physicalInputDeliveryVerified'])
            from audit_encounter_approach import audit_recording
            checked = audit_recording(Path(temporary) / 'recording', self.bound, report)
            self.assertEqual(checked['acceptedActions'], 5)
        self.assertEqual([call[0] for call in bridge.calls].count('release'), 2)
        self.assertEqual(bridge.calls[-1][0], 'stop')

    def test_stuck_route_stops_without_recovery_attack_or_jump(self):
        clock = Clock()
        bridge = FakeBridge(clock, stuck=True)
        with tempfile.TemporaryDirectory() as temporary:
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('survey_obstacle_requires_inspection', report['error'])
        self.assertTrue(report['releaseAcknowledged'])
        self.assertTrue(report['stopAcknowledged'])
        self.assertTrue(all(args['steps'][0]['keys'] == ['W'] for command, args in bridge.calls if command == 'action'))

    def test_hazard_on_receipt_frame_stops_before_any_next_dispatch(self):
        def danger(frame, bridge):
            if bridge.position:
                frame['combatEvidence']['playerHealthColor'] = 'red'
        clock = Clock()
        bridge = FakeBridge(clock, change=danger)
        with tempfile.TemporaryDirectory() as temporary:
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['acceptedActions'], 1)
        self.assertEqual(report['terminalReceipts'], 1)
        self.assertTrue(report['releaseAcknowledged'])

    def test_native_cancellation_frame_is_retained_and_auditable_as_a_failed_attempt(self):
        from audit_encounter_approach import audit_recording
        def cancelled(frame, bridge):
            if frame['receipts']:
                receipt = frame['receipts'][0]
                receipt.update(status='cancelled', reason='world_source_expired', endedAtMs=receipt['acceptedAtMs'] + 10)
        clock = Clock()
        bridge = FakeBridge(clock, change=cancelled)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'recording'
            report = approach.run_episode(bridge, self.bound, folder, clock=clock, sleep=clock.sleep)
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['terminalReceipts'], 1)
            self.assertEqual(report['recordedFrames'], 4)
            checked = audit_recording(folder, self.bound, report)
            self.assertEqual(checked['episodeStatus'], 'failed')
            self.assertEqual(checked['terminalReceipts'], 1)

    def test_recording_failure_still_attempts_release_and_stop(self):
        clock = Clock()
        bridge = FakeBridge(clock)
        with tempfile.TemporaryDirectory() as temporary, patch.object(approach.EvidenceJournal, 'event', side_effect=OSError('disk full')):
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual([call[0] for call in bridge.calls], ['release', 'stop'])

    def test_recorder_failure_after_acceptance_retains_terminal_accounting(self):
        clock = Clock()
        bridge = FakeBridge(clock)
        original = approach.EvidenceJournal.event
        def failing(journal, event):
            if event.get('type') == 'admission':
                raise OSError('admission disk failure')
            return original(journal, event)
        with tempfile.TemporaryDirectory() as temporary, patch.object(approach.EvidenceJournal, 'event', failing):
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['acceptedActions'], 1)
        self.assertEqual(report['terminalReceipts'], 1)
        self.assertEqual(len(report['actionResponses']), 1)
        self.assertTrue(report['receiptsComplete'])
        self.assertTrue(report['releaseAcknowledged'])
        self.assertEqual(len([row for row in bridge.calls if row[0] == 'action']), 1)

    def test_recording_close_failure_keeps_known_input_receipts_and_cleanup(self):
        clock = Clock()
        bridge = FakeBridge(clock)
        original = approach.EvidenceJournal.close
        def close_then_fail(journal):
            original(journal)
            raise OSError('final flush failed')
        with tempfile.TemporaryDirectory() as temporary, patch.object(approach.EvidenceJournal, 'close', close_then_fail):
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['recordingCloseError'], 'final flush failed')
        self.assertEqual(report['acceptedActions'], 5)
        self.assertEqual(report['terminalReceipts'], 5)
        self.assertTrue(report['releaseAcknowledged'])
        self.assertTrue(report['stopAcknowledged'])
        self.assertTrue(report['receiptsComplete'])

    def test_stop_check_delay_cannot_make_an_old_proposal_fresh(self):
        clock = Clock()
        bridge = FakeBridge(clock)
        def delayed():
            if bridge.number == 3:
                clock.sleep(.16)
        with tempfile.TemporaryDirectory() as temporary:
            report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording',
                                          clock=clock, sleep=clock.sleep, check=delayed)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(any(command == 'action' for command, _ in bridge.calls))

    def test_changed_duplicate_rgb_stops_immediately_and_retains_drained_receipt(self):
        for mutate in (False, True):
            clock = Clock()
            class DuplicateBridge(FakeBridge):
                def request(self, command, **arguments):
                    frame, pixels = super().request(command, **arguments)
                    if command == 'frame' and self.number == 3:
                        self.saved = copy.deepcopy(frame)
                    elif command == 'frame' and self.number == 4:
                        repeated = copy.deepcopy(self.saved)
                        repeated['receipts'] = frame['receipts']
                        repeated.update(serverNowMs=320, sourceFrameAgeMs=20)
                        self.clock.now -= 99_000_000
                        return repeated, bytes([pixels[0] ^ 1]) + pixels[1:] if mutate else pixels
                    return frame, pixels
            bridge = DuplicateBridge(clock)
            with tempfile.TemporaryDirectory() as temporary:
                report = approach.run_episode(bridge, self.bound, Path(temporary) / 'recording', clock=clock, sleep=clock.sleep)
            if mutate:
                self.assertEqual(report['status'], 'failed')
                self.assertIn('exact RGB payload', report['error'])
                self.assertEqual(report['acceptedActions'], 1)
                self.assertEqual(report['terminalReceipts'], 1)
                self.assertTrue(report['receiptsComplete'])
                self.assertTrue(report['releaseAcknowledged'])
            else:
                self.assertEqual(report['status'], 'completed', report)

    def test_independent_audit_rejects_mutated_pixels_and_completed_horizon(self):
        from audit_encounter_approach import audit_recording
        for mutation in ('pixels', 'duration'):
            clock = Clock()
            bridge = FakeBridge(clock)
            with tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary) / 'recording'
                report = approach.run_episode(bridge, self.bound, folder, clock=clock, sleep=clock.sleep)
                if mutation == 'pixels':
                    path = folder / 'frames/00000001.rgb'
                    data = bytearray(path.read_bytes()); data[0] ^= 1; path.write_bytes(data)
                else:
                    path = folder / 'events.jsonl'
                    events = [json.loads(line) for line in path.read_bytes().splitlines()]
                    for event in events:
                        response = event.get('frame', event.get('response', {}))
                        if response.get('receipts'):
                            response['receipts'][0]['endedAtMs'] = response['receipts'][0]['acceptedAtMs']
                            break
                    path.write_bytes(b''.join(approach.canonical(event) + b'\n' for event in events))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    audit_recording(folder, self.bound, report)

    def test_audit_replays_hazardous_nonproposal_polls_and_target_absence(self):
        from audit_encounter_approach import audit_recording
        for mutation in ('startupRed', 'startupFive', 'armedUnavailable', 'targetAbsence'):
            clock = Clock()
            bridge = FakeBridge(clock)
            with tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary) / 'recording'
                report = approach.run_episode(bridge, self.bound, folder, clock=clock, sleep=clock.sleep)
                path = folder / 'events.jsonl'
                events = [json.loads(line) for line in path.read_bytes().splitlines()]
                for event in events:
                    if event['type'] != 'observation':
                        continue
                    frame = event['frame']
                    if mutation == 'startupRed' and frame['frameId'] == 2:
                        frame['combatEvidence']['playerHealthColor'] = 'red'
                    elif mutation == 'startupFive' and frame['frameId'] == 2:
                        frame['combatEvidence']['enemyBarCandidates'] = sample(2, 200, candidates=5)['combatEvidence']['enemyBarCandidates']
                    elif mutation == 'armedUnavailable' and frame['frameId'] == 8:
                        frame['inputAvailable'] = False
                    elif mutation == 'targetAbsence' and frame['frameId'] >= 4:
                        frame['combatEvidence']['enemyBarCandidates'] = []
                path.write_bytes(b''.join(approach.canonical(event) + b'\n' for event in events))
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'terminal|outcome|guard'):
                    audit_recording(folder, self.bound, report)

    def test_never_transmitted_proposal_has_explicit_abandonment_not_fabricated_rejection(self):
        from audit_encounter_approach import audit_recording
        clock = Clock()
        bridge = FakeBridge(clock)
        original = approach.EvidenceJournal.event
        def delay_after_proposal(journal, event):
            original(journal, event)
            if event['type'] == 'proposal':
                clock.sleep(.16)
        with tempfile.TemporaryDirectory() as temporary, patch.object(approach.EvidenceJournal, 'event', delay_after_proposal):
            folder = Path(temporary) / 'recording'
            report = approach.run_episode(bridge, self.bound, folder, clock=clock, sleep=clock.sleep)
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['actionProposals'], 1)
            self.assertEqual(report['actionsAttempted'], 0)
            self.assertTrue(report['receiptsComplete'])
            checked = audit_recording(folder, self.bound, report)
            self.assertEqual(checked['acceptedActions'], 0)
            events = [json.loads(line) for line in (folder / 'events.jsonl').read_bytes().splitlines()]
            self.assertEqual(sum(row['type'] == 'proposalAbandoned' for row in events), 1)
            self.assertFalse(any(row['type'] == 'admission' for row in events))
            # Removing the only proof that this was never sent cannot become a verified failed run.
            events = [row for row in events if row['type'] != 'proposalAbandoned']
            (folder / 'events.jsonl').write_bytes(b''.join(approach.canonical(event) + b'\n' for event in events))
            with self.assertRaisesRegex((ValueError, RuntimeError), 'pending|unresolved'):
                audit_recording(folder, self.bound, report)


class OwnerDiscoveryTests(unittest.TestCase):
    """Exercise the real discovery parser and original guards with inert pipe names/status replies."""

    @classmethod
    def setUpClass(cls):
        """Import only transport definitions; every OS identity and endpoint operation is replaced below."""
        from resident_runtime import control_module
        cls.control = control_module()

    def fixture(self):
        """Provide one exact original pair and an injectable same-user advertisement snapshot."""
        sid = 'S-1-5-21-inert-approach-owner-tests'
        prefix = 'BetterGI.ExternalControl.' + approach.hashlib.sha256(sid.encode()).hexdigest()[:16].upper() + '.'
        names = {role: prefix + str(value['windowsSessionId']) + '.' + str(value['processId'])
                 for role, value in OWNER.items()}
        packages = {role: dict(assemblySha256=letter * 64, appDirectory=str((approach.ROOT / ('inert-' + role)).resolve()))
                    for role, letter in (('root', 'a'), ('child', 'b'))}
        root = dict(OWNER['root'], instanceType='Primary', automationEnabled=True, uiStatus='current',
                    childWindowMinimized=True, childSessionId=OWNER['child']['windowsSessionId'], childConnectedState=1,
                    **packages['root'])
        child = dict(OWNER['child'], instanceType='ChildSession', automationEnabled=True, remoteDesktop=True,
                     runtimeRunning=True, automationState='game_ready', taskRunning=False, agentStreamRunning=False,
                     serviceOwnsPilot=False, pilotState='idle', **packages['child'])
        plan = dict(owner=copy.deepcopy(OWNER), originalOwner=dict(nativePackages=packages))
        snapshot, calls, discoveries, errors = list(names.values()), [], [], {}
        states = {state['processId']: state for state in (root, child)}

        def exchange(command, process_id, session_id):
            """Return a bounded fixture status without opening a native endpoint."""
            calls.append((command, process_id, session_id))
            if process_id in errors:
                raise self.control.ControlError(errors[process_id])
            return copy.deepcopy(states[process_id])

        def discover(**arguments):
            """Use the production same-user parser, connection-error collection and candidate cap."""
            discoveries.append(copy.deepcopy(arguments))
            return self.control.discover(names=arguments.get('names', snapshot),
                                         user_sid=arguments.get('user_sid', sid), exchange_fn=exchange)

        lifecycle = SimpleNamespace(discover=discover, require_role=self.control.require_role,
            _require_connected_root=self.control._require_connected_root,
            transport=SimpleNamespace(WinPipeApi=lambda: SimpleNamespace(current_user_sid=lambda: sid)))
        return SimpleNamespace(plan=plan, lifecycle=lifecycle, snapshot=snapshot, names=names, prefix=prefix,
                               root=root, child=child, calls=calls, discoveries=discoveries, errors=errors)

    def test_missing_original_advertisements_use_one_pinned_discovery(self):
        """A transiently absent name still receives exactly one authenticated status request."""
        for missing_both in (False, True):
            with self.subTest(missing_both=missing_both):
                item = self.fixture()
                item.snapshot[:] = [] if missing_both else [item.names['child']]
                with patch.object(approach.os, 'listdir', return_value=item.snapshot):
                    actual = approach.owner_pair(item.lifecycle, item.plan, idle=True)
                self.assertEqual(actual, (item.root, item.child))
                self.assertEqual(len(item.discoveries), 1)
                self.assertEqual(set(item.discoveries[0]['names']), set(item.names.values()))
                self.assertEqual(len(item.calls), 2)
                self.assertTrue(all(command == 'status' for command, _, _ in item.calls))

    def test_default_scout_discovery_still_refuses_a_missing_advertisement(self):
        """The optional approach path does not change any existing scout caller's behavior."""
        import scout_session
        item = self.fixture()
        item.snapshot[:] = [item.names['child']]
        with self.assertRaisesRegex(ValueError, 'Incomplete or ambiguous scout ownership'):
            scout_session.owner_pair(item.lifecycle, item.plan['owner'])
        self.assertEqual(item.discoveries, [{}])
        self.assertEqual(len(item.calls), 1)

    def test_all_extra_same_user_advertisements_fail_before_candidate_cap(self):
        """No additional advertised identity can disappear behind the existing 32-candidate cap."""
        for count in (1, 40):
            with self.subTest(count=count):
                item = self.fixture()
                item.snapshot.extend(item.prefix + '99.' + str(9000 + index) for index in range(count))
                with patch.object(approach.os, 'listdir', return_value=item.snapshot), \
                     self.assertRaises(approach.OwnerDiscoveryError) as caught:
                    approach.owner_pair(item.lifecycle, item.plan)
                self.assertEqual(caught.exception.diagnostics['extraCount'], count)
                self.assertEqual(caught.exception.diagnostics['advertisedCount'], count + 2)
                self.assertEqual(item.discoveries, [])
                self.assertEqual(item.calls, [])

    def test_other_user_advertisements_remain_outside_this_users_discovery(self):
        """The same-user boundary remains exactly the existing hashed-SID pipe-name rule."""
        item = self.fixture()
        item.snapshot.append('BetterGI.ExternalControl.OTHERUSER.99.9999')
        with patch.object(approach.os, 'listdir', return_value=item.snapshot):
            self.assertEqual(approach.owner_pair(item.lifecycle, item.plan), (item.root, item.child))
        self.assertEqual(len(item.calls), 2)

    def test_changed_nonce_and_original_state_guards_still_refuse(self):
        """Seeding advertisements never relaxes identity, package, minimized, role or connection checks."""
        mutations = (('child', 'instanceNonce', 'replacement'), ('child', 'instanceType', 'Primary'),
                     ('child', 'assemblySha256', 'c' * 64), ('child', 'remoteDesktop', False),
                     ('child', 'runtimeRunning', False), ('root', 'childWindowMinimized', False),
                     ('root', 'childConnectedState', 0))
        for role, key, value in mutations:
            with self.subTest(role=role, key=key):
                item = self.fixture()
                getattr(item, role)[key] = value
                with patch.object(approach.os, 'listdir', return_value=item.snapshot), \
                     self.assertRaises(approach.OwnerDiscoveryError) as caught:
                    approach.owner_pair(item.lifecycle, item.plan)
                self.assertEqual(len(caught.exception.diagnostics['instances']), 2)
                self.assertEqual(len(item.discoveries), 1)

    def test_actual_connection_error_is_retained_without_generic_retry(self):
        """A genuinely unavailable pinned endpoint still stops and preserves its exact query error."""
        item = self.fixture()
        item.errors[OWNER['root']['processId']] = 'Control pipe connection timed out after at most 2 seconds: inert-root'
        with patch.object(approach.os, 'listdir', return_value=item.snapshot), \
             self.assertRaises(approach.OwnerDiscoveryError) as caught:
            approach.owner_pair(item.lifecycle, item.plan)
        evidence = caught.exception.diagnostics
        self.assertEqual(len(item.discoveries), 1)
        self.assertEqual(len(item.calls), 2)
        self.assertEqual(evidence['unavailable'], [dict(processId=OWNER['root']['processId'],
            windowsSessionId=OWNER['root']['windowsSessionId'], error=item.errors[OWNER['root']['processId']])])
        self.assertIn('inert-root', str(caught.exception))
        report = {}
        approach.retain_owner_failure(report, caught.exception)
        self.assertEqual(report['ownerDiscoveryFailure'], evidence)

    def test_snapshot_error_retains_its_phase_and_original_targets(self):
        """A namespace failure is distinguishable from an endpoint identity or status failure."""
        item = self.fixture()
        with patch.object(approach.os, 'listdir', side_effect=OSError('inert namespace failure')), \
             self.assertRaises(approach.OwnerDiscoveryError) as caught:
            approach.owner_pair(item.lifecycle, item.plan)
        self.assertEqual(caught.exception.diagnostics['phase'], 'same_user_snapshot')
        self.assertEqual(caught.exception.diagnostics['expected'], OWNER)
        self.assertEqual(caught.exception.diagnostics['error'], 'inert namespace failure')
        self.assertEqual(item.calls, [])


class WorkerBoundaryTests(unittest.TestCase):
    """Exercise the actual Bridge interface without opening an OS pipe, process or model."""

    @classmethod
    def setUpClass(cls):
        cls.bound = binding()

    def simulate(self, *, reject_identity=False, stop_on_discovery=False, expire_during_start=False,
                 close_failure=False, review_expiry_during_discovery=False, host_expiry_during_discovery=False,
                 owner_failure_after_start=False):
        """Run the broker-worker wrapper solely with faithful file-handle and lifecycle stand-ins."""
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            folder = Path(temporary)
            clock = Clock()
            plan = dict(runId='a' * 32, owner=copy.deepcopy(OWNER), binding=copy.deepcopy(self.bound),
                        runtime=dict(executable='C:/inert/python.exe'), originalOwner=dict(protectedGame=dict(processId=77)))
            original_wall = plan['binding']['reviewedAtUnixNs']
            sha = 'b' * 64
            approach.exclusive_json(folder / 'CONSUMED.json', dict(runId=plan['runId'], planSha256=sha,
                hostProcessId=55, startedMonotonicNs=clock(), startedAtUnixNs=original_wall + 1,
                deadlineMonotonicNs=clock() + 40_000_000_000))
            child = dict(OWNER['child'], agentPipeName='BetterGI.Agent.inert', taskRunning=False,
                         agentStreamRunning=False, serviceOwnsPilot=False, pilotState='idle')
            class Handle:
                def __init__(self):
                    self.close_calls = 0
                def close(self):
                    self.close_calls += 1
                    if close_failure:
                        raise OSError('close failed')
            handle = Handle()
            requests = []
            def request(command, **arguments):
                requests.append(command)
                if command == 'enableNavigationGuidance':
                    return dict(enabled=True, capability=copy.deepcopy(self.bound['navigationCapability'])), b''
                if command == 'release':
                    return release_ack(), b''
                if command == 'stop':
                    return dict(type='stopped', receipts=[]), b''
                raise AssertionError(command)
            bridge = SimpleNamespace(handle=handle, hello=copy.deepcopy(HELLO), request=request)
            bridge.hello['mapInspection'] = dict(gameProcessId=77, gameWindowHandle=123, wgcOnly=True, maximumSourceAgeMs=150)
            starts, discoveries = [], []
            def start(*args, **kwargs):
                starts.append((args, kwargs))
                if expire_during_start:
                    clock.sleep(11)
                return copy.deepcopy(child)
            lifecycle = SimpleNamespace(start_agent=start)
            def owners(*args, **kwargs):
                discoveries.append(len(discoveries) + 1)
                if stop_on_discovery and len(discoveries) == 2:
                    (folder / 'STOP').write_text('inert stop', encoding='utf-8')
                if review_expiry_during_discovery and len(discoveries) == 2:
                    clock.sleep(2)
                if host_expiry_during_discovery and len(discoveries) == 2:
                    clock.sleep(41)
                if owner_failure_after_start and len(discoveries) == 3:
                    raise approach.OwnerDiscoveryError('inert owner read failure',
                        dict(phase='pinned_status_reads', unavailable=[dict(error='inert connect timeout')]))
                return {}, copy.deepcopy(child)
            def identity(*args):
                if reject_identity:
                    raise ValueError('wrong native pipe owner')
            success = dict(status='completed', releaseAcknowledged=True, stopAcknowledged=True, receiptsComplete=True)
            def episode(*args, **kwargs):
                """Match the episode's error-to-report conversion after the worker records its ownership evidence."""
                if owner_failure_after_start:
                    clock.sleep(.3)
                    try:
                        kwargs['check']()
                    except approach.OwnerDiscoveryError as error:
                        return dict(success, status='failed', error=str(error))
                    raise AssertionError('Expected the inert owner failure')
                return copy.deepcopy(success)
            stack.enter_context(patch.object(approach, 'verify_plan', return_value=(plan, folder, sha)))
            stack.enter_context(patch.object(approach, 'ordinary_identity', return_value=dict(processId=44, parentProcessId=33)))
            stack.enter_context(patch.object(approach, 'owner_pair', side_effect=owners))
            stack.enter_context(patch.object(approach, 'run_episode', side_effect=episode))
            stack.enter_context(patch.object(approach, 'original_review_deadline', return_value=clock() +
                (1_000_000_000 if review_expiry_during_discovery else 120_000_000_000)))
            stack.enter_context(patch('resident_runtime.control_module', return_value=lifecycle))
            stack.enter_context(patch('resident_runtime.verify_bridge_identity', side_effect=identity))
            stack.enter_context(patch('stream_client.Bridge', return_value=bridge))
            stack.enter_context(patch('native_combat.negotiate', return_value=copy.deepcopy(CAPABILITY)))
            stack.enter_context(patch('native_ground_control.negotiate', return_value=(copy.deepcopy(GROUND), {})))
            stack.enter_context(patch('encounter_approach.time.perf_counter_ns', side_effect=clock))
            stack.enter_context(patch('encounter_approach.time.time_ns', return_value=original_wall + 119_000_000_000
                                      if review_expiry_during_discovery else original_wall + 1))
            report = approach.worker(folder / 'plan.json')
            retained = json.loads((folder / 'worker-result.json').read_bytes())
            self.assertEqual(retained, report)
            return report, requests, starts, handle.close_calls

    def test_real_bridge_has_only_owned_handle_close_and_wrapper_uses_it(self):
        from stream_client import Bridge
        self.assertFalse(hasattr(Bridge, 'close'))
        report, requests, starts, closed = self.simulate()
        self.assertEqual(report['status'], 'completed', report)
        self.assertTrue(report['cleanupVerified'])
        self.assertEqual(closed, 1)
        self.assertEqual(requests, ['enableNavigationGuidance'])
        self.assertEqual(len(starts), 1)

    def test_unverified_pipe_gets_no_negotiation_release_or_stop(self):
        report, requests, starts, closed = self.simulate(reject_identity=True)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['cleanupVerified'])
        self.assertEqual(requests, [])
        self.assertEqual(closed, 1)
        self.assertIn('wrong native pipe owner', report['error'])

    def test_stop_arriving_inside_discovery_prevents_native_start(self):
        report, requests, starts, closed = self.simulate(stop_on_discovery=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(starts, [])
        self.assertEqual(requests, [])
        self.assertEqual(closed, 0)
        self.assertIn('after owner discovery', report['error'])

    def test_expired_start_retires_only_authenticated_lease_without_negotiation(self):
        report, requests, starts, closed = self.simulate(expire_during_start=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(requests, ['release', 'stop'])
        self.assertEqual(closed, 1)
        self.assertEqual(len(starts), 1)

    def test_local_handle_close_error_is_retained_without_duplicate_cleanup(self):
        report, requests, starts, closed = self.simulate(close_failure=True)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['cleanupVerified'])
        self.assertEqual(report['pipeCloseError'], 'close failed')
        self.assertEqual(closed, 1)
        self.assertEqual(requests, ['enableNavigationGuidance'])

    def test_original_review_expiry_during_discovery_prevents_start(self):
        report, requests, starts, closed = self.simulate(review_expiry_during_discovery=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(starts, [])
        self.assertEqual(requests, [])
        self.assertEqual(closed, 0)

    def test_original_host_expiry_during_discovery_prevents_start(self):
        """A blocking owner read cannot renew the original host deadline before listener creation."""
        report, requests, starts, closed = self.simulate(host_expiry_during_discovery=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(starts, [])
        self.assertEqual(requests, [])
        self.assertEqual(closed, 0)
        self.assertIn('after owner discovery', report['error'])

    def test_owner_error_evidence_survives_episode_error_conversion(self):
        """An episode can catch the exception while the worker still retains its actual discovery evidence."""
        report, requests, starts, closed = self.simulate(owner_failure_after_start=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['ownerDiscoveryFailure']['unavailable'], [dict(error='inert connect timeout')])
        self.assertTrue(report['cleanupVerified'])
        self.assertEqual(len(starts), 1)
        self.assertEqual(closed, 1)


class HostBoundaryTests(unittest.TestCase):
    """Keep a monitor's actual discovery failure through STOP and final host accounting without a broker launch."""

    def test_host_monitor_retains_discovery_evidence_and_one_stop(self):
        """A completed inert future models one worker while the host monitor fails its ownership check."""
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            folder = Path(temporary)
            clock = Clock()
            plan = dict(runId='a' * 32, owner=copy.deepcopy(OWNER), runtime=dict(executable='C:/inert/python.exe'))
            sha = 'b' * 64
            terminal = dict(runId=plan['runId'], planSha256=sha, worker=dict(processId=22),
                            status='failed', cleanupVerified=True)
            approach.exclusive_json(folder / 'worker-result.json', terminal)
            broker = dict(windowsSessionId=OWNER['child']['windowsSessionId'], remoteDesktop=True,
                          elevated=False, integrityRid=8192, timedOut=False, outputIncomplete=False,
                          success=False, returnCode=2)
            failure = approach.OwnerDiscoveryError('inert monitor failure',
                dict(phase='pinned_status_reads', unavailable=[dict(error='inert root status failure')]))
            submissions = []
            states = iter((False, True))
            future = SimpleNamespace(done=lambda: next(states), result=lambda: copy.deepcopy(broker))
            class Pool:
                """Expose the executor interface without starting a thread or invoking a submitted function."""
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    return False
                def submit(self, function, *args):
                    submissions.append((function, args))
                    return future
            def no_broker_call(*_):
                raise AssertionError('No native broker operation is permitted in this test')
            lifecycle = SimpleNamespace(run_command=no_broker_call)
            stack.enter_context(patch.object(approach, 'verify_plan', return_value=(plan, folder, sha)))
            stack.enter_context(patch.object(approach, 'owner_pair', side_effect=[({}, {}), failure, ({}, {})]))
            stack.enter_context(patch('resident_runtime.control_module', return_value=lifecycle))
            verify = stack.enter_context(patch('combat_process_identity.verify_worker_broker'))
            stack.enter_context(patch('concurrent.futures.ThreadPoolExecutor', return_value=Pool()))
            stack.enter_context(patch('encounter_approach.time.perf_counter_ns', side_effect=clock))
            stack.enter_context(patch('encounter_approach.time.time_ns', return_value=1_000_000_000))
            stack.enter_context(patch('encounter_approach.time.sleep', side_effect=clock.sleep))
            report = approach.launch(folder / 'plan.json')
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['ownerDiscoveryFailure'], failure.diagnostics)
            self.assertEqual((folder / 'STOP').read_text(), str(failure))
            self.assertEqual(json.loads((folder / 'result.json').read_bytes()), report)
            self.assertEqual(len(submissions), 1)
            verify.assert_called_once()


class SourceClosureTests(unittest.TestCase):
    """Seal the broker's explicit dynamic transport and only its reachable local dependencies."""

    def test_installed_contract_pins_dynamic_transport(self):
        """The real transport is a source dependency before its module can execute."""
        path = approach.ROOT / 'tools/quest-pilot/controller-control.py'
        contract = approach.source_contract()
        self.assertEqual(contract[str(path.relative_to(approach.ROOT))], approach.digest(approach.read_bytes(path)))

    def test_dynamic_transport_local_imports_without_directory_enumeration(self):
        """A tiny inert source tree proves transitive imports, cycles and excluded unrelated scripts."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            agent = root / 'tools/bettergi-agent'
            broker = root / 'tools/rdp-automation'
            transport = root / 'tools/quest-pilot'
            for path in (agent, broker, transport):
                path.mkdir(parents=True)
            seeds = ('encounter_approach.py', 'stream_client.py', 'resident_runtime.py', 'scout_session.py',
                     'map_owner.py', 'combat_process_identity.py', 'capture_scout_scene.py', 'audit_encounter_approach.py')
            for name in seeds:
                (agent / name).write_text('# Inert source fixture.\n', encoding='utf-8')
            (broker / 'rdp_control.py').write_text('# Dynamic transport is a path, not an import.\n', encoding='utf-8')
            (transport / 'controller-control.py').write_text('import local_transport_helper\n', encoding='utf-8')
            (transport / 'local_transport_helper.py').write_text('from transport_leaf import marker\n', encoding='utf-8')
            (transport / 'transport_leaf.py').write_text('import local_transport_helper\nmarker = 1\n', encoding='utf-8')
            unrelated = transport / 'unrelated.py'
            unrelated.write_text('This unrelated file is intentionally not valid Python.\n', encoding='utf-8')
            with patch.object(approach, 'ROOT', root), patch.object(approach, '__file__', str(agent / seeds[0])):
                found = set(approach.source_files())
            expected = {agent / name for name in seeds} | {broker / 'rdp_control.py'}
            expected |= {transport / name for name in ('controller-control.py', 'local_transport_helper.py', 'transport_leaf.py')}
            self.assertEqual(found, expected)
            self.assertNotIn(unrelated, found)


class PrepareTests(unittest.TestCase):
    """Prepare/verify touch only bounded inert files and refuse every changed authority boundary."""

    def prepare_fixture(self, temporary, stack):
        """Seal synthetic review bytes with a tiny dependency contract and no live discovery."""
        root = Path(temporary)
        live = root / 'artifacts/live'
        scene_dir = live / 'scene'
        scene_dir.mkdir(parents=True)
        review, native_plan, scene, sidecar, image = review_parts()
        helper = Path(approach.__file__).with_name('capture_scout_scene.py').read_bytes()
        native_plan['captureHelperSha256'] = approach.digest(helper)
        for name, value in (('plan.json', native_plan), ('result.json', scene), ('source.json', sidecar), ('review.json', review)):
            (scene_dir / name).write_bytes(approach.canonical(value))
        (scene_dir / 'source.png').write_bytes(image)
        (scene_dir / 'capture-helper.py').write_bytes(helper)
        owner_path = live / 'owner.json'
        owner_path.write_text('{}', encoding='utf-8')
        pins = dict(ownerFrom=str(owner_path), ownerFromSha256=approach.digest(b'{}'),
                    nativePackages={}, protectedGame=dict(processId=77))
        relative = str(Path('tools/bettergi-agent/encounter_approach.py'))
        dependency = root / relative
        dependency.parent.mkdir(parents=True)
        dependency.write_bytes(b'# inert dependency fixture\n')
        sources = {relative: approach.digest(dependency.read_bytes())}
        runtime = dict(version=1, kind='direct-python-v1', executable='C:/inert/python.exe', files={})
        stack.enter_context(patch.object(approach, 'ROOT', root))
        stack.enter_context(patch.object(approach, 'LIVE', live))
        stack.enter_context(patch.object(approach, 'original_owner', return_value=(copy.deepcopy(OWNER), pins)))
        stack.enter_context(patch.object(approach, 'runtime_contract', return_value=runtime))
        stack.enter_context(patch.object(approach, 'source_contract', return_value=sources))
        stack.enter_context(patch.object(approach, 'recent_review'))
        stack.enter_context(patch('resident_runtime.control_module', side_effect=AssertionError('Offline preparation contacted live control')))
        folder = live / 'approach'
        plan = approach.prepare(folder, scene_dir / 'review.json', scene_dir, owner_path, 'C:/inert/python.exe')
        return folder, scene_dir, plan

    def test_prepare_and_verify_are_offline_and_preserve_exact_originals(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            folder, scene, plan = self.prepare_fixture(temporary, stack)
            actual, checked_folder, sha = approach.verify_plan(folder / 'plan.json')
            self.assertEqual(actual, plan)
            self.assertEqual(checked_folder, folder)
            self.assertEqual(sha, approach.digest((folder / 'plan.json').read_bytes()))
            self.assertFalse(plan['preparationStartsInput'])
            self.assertTrue(plan['explicitLaunchRequired'])
            self.assertFalse((folder / 'CONSUMED.json').exists())
            with self.assertRaises(ValueError):
                approach.prepare(folder, scene / 'review.json', scene, Path(plan['originalOwner']['ownerFrom']), 'C:/inert/python.exe')

    def test_changed_original_copy_binding_or_fixed_policy_is_rejected(self):
        for mutation in ('original', 'copy', 'binding', 'policy', 'source'):
            with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                folder, scene, plan = self.prepare_fixture(temporary, stack)
                if mutation == 'original':
                    (scene / 'review.json').write_bytes(b'{}')
                elif mutation == 'copy':
                    (folder / 'review-evidence/image.png').write_bytes(b'changed')
                elif mutation == 'source':
                    source = folder / 'sources' / next(iter(plan['sourceContract']))
                    source.write_bytes(b'# changed dependency\n')
                else:
                    if mutation == 'binding':
                        plan['binding']['baselineHealthFraction'] = .5
                    else:
                        plan['policy']['maximumDistance'] = 7
                    (folder / 'plan.json').write_bytes(approach.canonical(plan))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    approach.verify_plan(folder / 'plan.json')


class AuditClockTests(unittest.TestCase):
    """Episode clocks cannot be independently extended beyond their original host/source/review claim."""

    def fixture(self):
        bound = binding()
        claim = dict(startedMonotonicNs=1_000_000_000, startedAtUnixNs=bound['reviewedAtUnixNs'] + 1,
                     deadlineMonotonicNs=41_000_000_000)
        reviewed = approach.original_review_deadline(bound, client_ns=claim['startedMonotonicNs'], wall_ns=claim['startedAtUnixNs'])
        worker = dict(originalReviewDeadlineClientNs=reviewed, leaseStartedMonotonicNs=2_000_000_000,
                      leaseDeadlineMonotonicNs=12_000_000_000)
        episode = dict(startedAtClientNs=3_000_000_000, deadlineClientNs=12_000_000_000)
        return bound, claim, worker, episode

    def test_exact_original_clock_join_passes(self):
        from audit_encounter_approach import verify_episode_clocks
        verify_episode_clocks(*self.fixture())

    def test_independently_extended_episode_worker_or_host_clock_is_rejected(self):
        from audit_encounter_approach import verify_episode_clocks
        for index, key in ((1, 'deadlineMonotonicNs'), (2, 'leaseDeadlineMonotonicNs'),
                           (2, 'originalReviewDeadlineClientNs'), (3, 'deadlineClientNs')):
            parts = list(self.fixture())
            parts[index][key] += 1_000_000_000
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_episode_clocks(*parts)

    def test_review_age_uses_retained_host_wall_pair_and_original_source(self):
        from audit_encounter_approach import verify_episode_clocks
        parts = list(self.fixture())
        parts[1]['startedAtUnixNs'] += 119_000_000_000
        with self.assertRaises(ValueError):
            verify_episode_clocks(*parts)


class InitialTargetAcquisitionTests(unittest.TestCase):
    """Explicit v2 permits one bounded acquisition opportunity, never blind arrival or renewed input."""

    def parts(self):
        """Construct v2-only synthetic review data without changing shared v1 fixtures."""
        review, plan, scene, sidecar, image = review_parts()
        review.update(kind=approach.ACQUISITION_REVIEW_KIND, policy=approach.policy(initial_target_acquisition=True))
        for frame in scene['observations'] + scene['stableSamples']:
            frame['combatEvidence']['enemyBarCandidates'] = []
        return review, plan, scene, sidecar, image

    def ready(self):
        """Spend the original three-frame alignment interval with genuine zero-candidate fixtures."""
        bound = approach.bind_review(*self.parts(), expected_owner=OWNER)
        controller = approach.ApproachController(bound, HELLO, 0)
        for index in (1, 2, 3):
            controller.observe(sample(index, index * 100, candidates=0), index * 100_000_000, 1)
        self.assertEqual(controller.navigation.phase, 'walking')
        return controller

    def test_v2_is_explicit_and_changes_only_fixed_initial_acquisition_policy(self):
        v1, v2 = approach.policy(), approach.policy(initial_target_acquisition=True)
        self.assertEqual(v2.pop('initialTargetAcquisitionMs'), 1500)
        v2['version'] = 1
        self.assertEqual(v2, v1)
        parts = list(self.parts())
        bound = approach.bind_review(*parts)
        self.assertEqual(bound['version'], 2)
        self.assertEqual(bound['reviewedFrame']['combatEvidence']['enemyBarCandidates'], [])
        for change in ('oldKind', 'oldPolicy', 'longer', 'automatic', 'bindingVersion'):
            changed = copy.deepcopy(parts)
            if change == 'oldKind':
                changed[0]['kind'] = approach.REVIEW_KIND
            elif change == 'oldPolicy':
                changed[0]['policy'] = approach.policy()
            elif change == 'longer':
                changed[0]['policy']['initialTargetAcquisitionMs'] = 1501
            elif change == 'automatic':
                changed[0]['policy']['automaticRecovery'] = True
            else:
                invalid = copy.deepcopy(bound)
                invalid['version'] = 1
                with self.assertRaisesRegex(ValueError, 'policy changed'):
                    approach.ApproachController(invalid, HELLO, 0)
                continue
            with self.subTest(change=change), self.assertRaises(ValueError):
                approach.bind_review(*changed)

    def test_zero_initial_review_still_requires_one_to_four_visually_inspected_enemies(self):
        for count in (0, 5, True, None):
            parts = list(self.parts())
            parts[0]['inspectedVisibleEnemyCount'] = count
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'enemy-group'):
                approach.bind_review(*parts)
        old_parts = list(self.parts())
        old_parts[0].update(kind=approach.REVIEW_KIND, policy=approach.policy())
        with self.assertRaisesRegex(ValueError, 'start/group'):
            approach.bind_review(*old_parts)

    def test_startup_idle_and_duplicate_polls_cannot_extend_the_original_window(self):
        for mode in ('bootstrap', 'duplicate', 'noObservation'):
            controller = self.ready() if mode == 'duplicate' else approach.ApproachController(approach.bind_review(*self.parts()), HELLO, 0)
            self.assertEqual(controller.initial_target_acquisition()['deadlineClientNs'], 1_500_000_000)
            controller.check(1_499_999_999)
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, 'initial_target_acquisition_deadline'):
                if mode == 'noObservation':
                    controller.check(1_500_000_000)
                else:
                    frame = sample(3, 300, candidates=0) if mode == 'duplicate' else dict(type='waiting')
                    controller.observe(frame, 1_500_000_000, 0)
            with self.assertRaisesRegex(RuntimeError, 'initial_target_acquisition_deadline'):
                controller.observe(sample(4, 1501), 1_501_000_000, 0)

    def test_camera_and_zero_frames_do_not_restart_the_acquisition_clock(self):
        controller = self.ready()
        for index in (4, 5):
            controller.observe(sample(index, index * 100, candidates=0, yaw=200), index * 100_000_000, 1)
            request = controller.next_action(index * 100_000_000 + 1_000_000)
            self.assertEqual(request['steps'][0]['keys'], [])
            self.assertNotEqual(request['steps'][0]['mouseDx'], 0)
            complete(controller, request)
        self.assertIsNone(controller.initial_target_acquisition()['firstObservedFrameId'])
        with self.assertRaisesRegex(RuntimeError, 'initial_target_acquisition_deadline'):
            controller.check(1_500_000_000)

    def test_first_qualified_bar_retires_only_initial_clock_and_preserves_target_loss(self):
        controller = self.ready()
        controller.observe(sample(4, 400, candidates=1), 400_000_000, 1)
        self.assertEqual(controller.initial_target_acquisition(), dict(startedAtClientNs=0,
            deadlineClientNs=1_500_000_000, firstObservedAtClientNs=400_000_000, firstObservedFrameId=4))
        controller.observe(sample(5, 1100, candidates=0), 1_100_000_000, 1)
        with self.assertRaisesRegex(RuntimeError, 'target_absence_deadline'):
            controller.observe(sample(6, 1200, candidates=0), 1_200_000_000, 1)
        late = self.ready()
        with self.assertRaisesRegex(RuntimeError, 'initial_target_acquisition_deadline'):
            late.observe(sample(4, 1490, candidates=1), 1_500_000_000, 1)

    def test_zero_bar_mode_keeps_positive_danger_source_pose_and_corridor_guards(self):
        for change in ('red', 'loss', 'fiveBars', 'missingGround', 'stale', 'capture', 'world', 'pose', 'corridor'):
            controller = self.ready()
            frame = sample(4, 400, candidates=0)
            if change == 'red': frame['combatEvidence']['playerHealthColor'] = 'red'
            elif change == 'loss': frame['combatEvidence']['playerHealthFractionEstimate'] = .97
            elif change == 'fiveBars': frame = sample(4, 400, candidates=5)
            elif change == 'missingGround': frame.pop('groundControlEvidence')
            elif change == 'stale': frame = sample(4, 400, candidates=0, age=151)
            elif change == 'capture': frame = sample(4, 400, candidates=0, capture='foreign')
            elif change == 'world': frame = sample(4, 400, candidates=0, epoch=1)
            elif change == 'pose': frame['navigationPose']['state'] = 'unavailable'
            else: frame = sample(4, 400, candidates=0, point=(START[0] + 1, START[1] + 1.01))
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                controller.observe(frame, 400_000_000, 1)
            self.assertEqual(controller.actions, 0)

    def test_original_dispatch_headroom_pending_and_final_transmission_checks_remain(self):
        controller = self.ready()
        request = controller.next_action(301_000_000)
        self.assertEqual(request['steps'], [dict(keys=['W'], mouseDx=0, mouseDy=0, durationMs=50)])
        self.assertIsNone(controller.next_action(302_000_000))
        with self.assertRaisesRegex(RuntimeError, 'initial_target_acquisition_deadline'):
            controller.transmitting(1_500_000_000)
        self.assertFalse(controller.pending['transmissionAttempted'])
        headroom = self.ready()
        headroom.observe(sample(4, 1350, candidates=0), 1_350_000_000, 1)
        with self.assertRaisesRegex(RuntimeError, 'approach_dispatch_budget'):
            headroom.next_action(1_351_000_000)

    def episode(self, *, acquire_at=4, bootstrap_bar=False, camera_until=0):
        """Use the real episode writer and auditor with only native RPC/pixels/clock injected."""
        clock = Clock()
        def change(frame, bridge):
            if bridge.number < acquire_at:
                frame['combatEvidence']['enemyBarCandidates'] = []
            if bootstrap_bar and bridge.number == 1:
                frame['combatEvidence']['enemyBarCandidates'] = sample(1, 100)['combatEvidence']['enemyBarCandidates']
                frame['worldReadiness']['ready'] = False
                frame['inputAvailable'] = False
            if 5 <= bridge.number < camera_until:
                frame['navigationPose']['yawDegrees'] = 200
        bound = approach.bind_review(*self.parts())
        bridge = FakeBridge(clock, change=change)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder = Path(temp.name) / 'recording'
        report = approach.run_episode(bridge, bound, folder, clock=clock, sleep=clock.sleep)
        return bound, bridge, folder, report

    def test_real_episode_and_audit_acquire_once_then_complete_without_attack(self):
        from audit_encounter_approach import audit_recording
        bound, bridge, folder, report = self.episode()
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['acceptedActions'], 5)
        self.assertEqual(report['initialTargetAcquisition']['firstObservedFrameId'], 4)
        self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'completed')
        for field in ('deadlineClientNs', 'firstObservedAtClientNs', 'firstObservedFrameId'):
            altered = copy.deepcopy(report)
            altered['initialTargetAcquisition'][field] += 1
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'acquisition clock'):
                audit_recording(folder, bound, altered)
        self.assertTrue(all(set(args['steps'][0]['keys']) <= {'W'} for command, args in bridge.calls if command == 'action'))

    def test_early_endpoint_without_any_native_bar_is_failed_and_cleanup_is_auditable(self):
        from audit_encounter_approach import audit_recording
        bound, bridge, folder, report = self.episode(acquire_at=999)
        self.assertEqual(report['status'], 'failed')
        self.assertIn(report['error'], ('initial_target_not_acquired', 'initial_target_acquisition_deadline', 'approach_dispatch_budget'))
        self.assertFalse(report['navigationVerified'])
        self.assertIsNone(report['initialTargetAcquisition']['firstObservedFrameId'])
        self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'failed')
        self.assertEqual(bridge.calls[-1][0], 'stop')

    def test_auditor_independently_refuses_a_zero_bar_proposal_after_initial_expiry(self):
        from audit_encounter_approach import audit_recording
        bound, _, folder, report = self.episode()
        path = folder / 'events.jsonl'
        events = [json.loads(row) for row in path.read_bytes().splitlines()]
        proposal = next(row for row in events if row['type'] == 'proposal')
        proposal['clientTimeNs'] = report['initialTargetAcquisition']['deadlineClientNs']
        path.write_bytes(b''.join(approach.canonical(row) + b'\n' for row in events))
        with self.assertRaisesRegex(ValueError, 'Initial target acquisition exceeded'):
            audit_recording(folder, bound, report)

    def test_actual_v2_prepare_verify_round_trip_refuses_mixed_outer_authority(self):
        """The stored plan and reconstructed reviewed binding must declare the same finite policy."""
        parts = self.parts()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch(__name__ + '.review_parts', return_value=parts))
            folder, _, plan = PrepareTests().prepare_fixture(temporary, stack)
            self.assertEqual(plan['version'], 2)
            self.assertEqual(plan['policy'], plan['binding']['policy'])
            self.assertEqual(approach.verify_plan(folder / 'plan.json')[0], plan)
            for change in ('outerVersion', 'outerPolicy', 'bothOuter', 'innerVersion'):
                altered = copy.deepcopy(plan)
                if change in ('outerVersion', 'bothOuter'): altered['version'] = 1
                if change in ('outerPolicy', 'bothOuter'): altered['policy'] = approach.policy()
                if change == 'innerVersion': altered['binding']['version'] = 1
                (folder / 'plan.json').write_bytes(approach.canonical(altered))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    approach.verify_plan(folder / 'plan.json')


    def test_fresh_prepared_action_losing_initial_headroom_is_abandoned_before_native_send(self):
        """Real episode and audit must reject a late send even though its source is still fresh."""
        from audit_encounter_approach import audit_recording
        clock = Clock()
        clock.now = 0
        calls = []
        class FreshBridge:
            def __init__(self):
                self.hello, self.number = copy.deepcopy(HELLO), 0
            def request(self, command, **arguments):
                calls.append(command)
                if command == 'frame':
                    clock.sleep(.01)
                    self.number += 1
                    frame = sample(self.number, clock() / 1e6, candidates=0)
                    return frame, bytes([30, 45, 65]) * (192 * 192)
                if command == 'release':
                    return release_ack(clock() / 1e6), b''
                if command == 'stop':
                    return dict(type='stopped', receipts=[]), b''
                raise AssertionError('No native action may be called after losing initial headroom')
        bridge = FreshBridge()
        def before_work():
            # Three fresh low-RTT sources qualify at1090/1190/1290ms. No clock moves backward.
            clock.now = max(clock.now, (1080, 1180, 1280, 1300)[min(bridge.number, 3)] * 1_000_000)
        original_event = approach.EvidenceJournal.event
        def delayed_event(journal, event):
            original_event(journal, event)
            if event['type'] == 'proposal': clock.sleep(.05)
        bound = approach.bind_review(*self.parts())
        with tempfile.TemporaryDirectory() as temporary, patch.object(approach.EvidenceJournal, 'event', delayed_event):
            folder = Path(temporary) / 'recording'
            report = approach.run_episode(bridge, bound, folder, clock=clock, sleep=clock.sleep, check=before_work)
            self.assertEqual(report['error'], 'approach_dispatch_budget')
            self.assertEqual(report['actionProposals'], 1)
            self.assertEqual(report['actionsAttempted'], 0)
            self.assertNotIn('action', calls)
            self.assertEqual(next(iter(report['actionAttempts'].values()))['state'], 'abandoned_before_transmission')
            self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'failed')
            path = folder / 'events.jsonl'
            events = [json.loads(row) for row in path.read_bytes().splitlines()]
            observation = next(row for row in reversed(events) if row['type'] == 'observation')
            age = observation['frame']['sourceFrameAgeMs'] + observation['roundTripMs'] + (1_350_000_000 - observation['clientReceivedNs']) / 1e6
            self.assertLess(age, 150)
            # A deliberately forged late admission must hit the real replayed transmitting gate.
            proposal = next(row for row in events if row['type'] == 'proposal')
            at = next(i for i, row in enumerate(events) if row['type'] == 'proposalAbandoned')
            events[at] = dict(type='admission', requestId=proposal['request']['requestId'], payloadBytes=0,
                response=dict(type='accepted', requestId=proposal['request']['requestId'], acceptedAtMs=1350),
                clientTimeNs=1_350_000_000, dispatchedAtClientNs=1_350_000_000, sourceAgeAtDispatchMs=age)
            path.write_bytes(b''.join(approach.canonical(row) + b'\n' for row in events))
            with self.assertRaisesRegex(RuntimeError, 'approach_dispatch_budget'):
                audit_recording(folder, bound, report)


    def test_unready_bootstrap_bar_never_satisfies_acquisition_or_audit_target_history(self):
        from audit_encounter_approach import audit_recording
        bound, _, folder, report = self.episode(acquire_at=12, bootstrap_bar=True, camera_until=12)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['initialTargetAcquisition']['firstObservedFrameId'], 12)
        self.assertLess(report['initialTargetAcquisition']['firstObservedAtClientNs'] - report['startedAtClientNs'], 1_500_000_000)
        self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'completed')


def settled_release(controller, at, epoch=None):
    """Build a typed inert native ledger for all settled calls and this one client release."""
    rows = []
    call_id = 0
    def pair(origin, identity, operation, key, mouse_x, begin, end, terminal):
        nonlocal call_id
        call_id += 1
        for stage, stamp in (('started', begin), (terminal, end)):
            rows.append(dict(sequence=len(rows) + 1, atMs=stamp, requestId=identity[0], modelId=identity[1],
                frameId=identity[2], stepIndex=identity[3], origin=origin,
                call=dict(callId=call_id, operation=operation, stage=stage, key=key,
                          mouseDx=mouse_x, mouseDy=0, error=None)))
    for receipt in sorted(controller.receipts.values(), key=lambda row: row['acceptedAtMs']):
        step = receipt['appliedSteps'][0]
        identity = (receipt['requestId'], receipt['modelId'], receipt['frameId'], 0)
        if step['keys']:
            pair('dispatch', identity, 'keyDown', 'W', 0, step['startedAtMs'], step['startedAtMs'] + .001, 'returned')
        if step['mouseDx']:
            pair('dispatch', identity, 'mouseMove', None, step['mouseDx'], step['startedAtMs'], step['startedAtMs'] + .001, 'returned')
        pair('release:horizon_complete', identity, 'releaseAll', None, 0,
             receipt['endedAtMs'], receipt['endedAtMs'] + .001, 'returned_unverified')
    pair('release:client_release', (None, None, None, None), 'releaseAll', None, 0, at - .2, at - .1, 'returned_unverified')
    response = release_ack(at, controller.world_epoch + 1 if epoch is None else epoch)
    response['worldReadiness']['reason'] = 'client_release'
    response['executionContext'].update(version=1, clock='monotonic milliseconds since session start',
        observesBlockedCallConcurrently=False, physicalExecutionProven=False, sampledAtMs=at + .001,
        firstSequence=1, lastSequence=len(rows), evictedEvents=0, events=rows, lastInputEvent=copy.deepcopy(rows[-1]))
    return response


def readiness_projection(frame):
    """Model the exact native response mask; it never changes the captured source or HUD."""
    current, gate = frame['worldReadiness'], frame['frameWorldReadiness']
    frame['inputAvailable'] = current['ready'] and gate['ready'] and current['epoch'] == gate['epoch']
    if not frame['inputAvailable']:
        frame['motionEvidence'] = dict(status='unknown', reason='world_not_ready',
            method='native_key_tip_templates_v1', recognitionMs=0, spaceKeyMatched=None, xKeyMatched=None)
    return frame


def confirming_source(index=4, at=500, *, current_ready=False, reason='world_confirming', unavailable=False):
    """Retain source-bound native confirmation evidence, optionally with its unavailable HUD schema."""
    frame = sample(index, at, candidates=0, epoch=1)
    frame['worldReadiness'].update(ready=current_ready, reason='world_ready' if current_ready else reason)
    frame['frameWorldReadiness'].update(ready=False, reason=reason)
    if unavailable:
        frame['combatEvidence'].update(state='unavailable', reason='world_not_ready', playerHealthColor='unknown',
            playerHealthFractionEstimate=None, playerHealthMatchingPixels=0, enemyBarCandidates=[], redMaskOverloaded=False)
        frame['groundControlEvidence'].update(state='unavailable', reason='world_not_ready', groundControlsConfirmed=False,
            swimHintPixels=0, spaceKeyMatched=None, xKeyMatched=None, eKey=None, qKey=None, crops=[])
    return readiness_projection(frame)



class SourceReacquisitionTests(unittest.TestCase):
    """A repeated stale source permits one idle wait, never stale movement or a renewed lease."""

    def ready(self, *, first_acquisition=False, target=False, enabled=True, started=0, deadline=None):
        """Use the original v2 review and real planner alignment before one settled fake action."""
        bound = approach.bind_review(*InitialTargetAcquisitionTests().parts())
        controller = approach.ApproachController(bound, HELLO, started, deadline_ns=deadline,
                                                  source_reacquisition=enabled)
        for index in (1, 2, 3):
            frame = sample(index, index * 100, candidates=int(target))
            if index == 3 and first_acquisition:
                source = copy.deepcopy(frame['sourceFrame'])
                source.update(acquiredAtMs=284.1965, freshnessAtMs=284.1965, freshnessClockKind='first_acquisition_qpc')
                def bind_source(value):
                    if isinstance(value, dict):
                        if 'sourceFrame' in value: value['sourceFrame'] = copy.deepcopy(source)
                        for child in value.values(): bind_source(child)
                    elif isinstance(value, list):
                        for child in value: bind_source(child)
                bind_source(frame)
                frame.update(serverNowMs=304.1965, sourceFrameAgeMs=20)
            controller.observe(frame, started + index * 100_000_000, 1)
        request = controller.next_action(started + 300_000_000)
        complete(controller, request)
        return controller

    def trigger(self, controller, *, now=470_000_000, age=163.0292, rtt=.9615):
        """Repeat exactly the retained source while current readiness advances independently."""
        frame = copy.deepcopy(controller.last_distinct)
        frame.update(serverNowMs=frame['sourceFrame']['freshnessAtMs'] + age, sourceFrameAgeMs=age)
        frame['worldReadiness'] = sample(4, 400, epoch=controller.world_epoch)['worldReadiness']
        outcome = controller.observe(frame, now, rtt)
        return frame, outcome

    def release(self, controller, *, at=470, now=475_000_000):
        """A successful software release is retained without claiming physical delivery."""
        ack = settled_release(controller, at)
        controller.source_reacquisition_released(ack, b'', now)
        return ack

    def test_original_acquisition_clock_not_fresher_compositor_drives_hold(self):
        controller = self.ready(first_acquisition=True)
        frame, outcome = self.trigger(controller)
        self.assertEqual(outcome, 'sourceReacquisitionReleaseRequired')
        self.assertAlmostEqual(frame['serverNowMs'] - frame['sourceFrame']['capturedAtMs'], 147.2257)
        self.assertAlmostEqual(controller.source_hold['triggerAgeUpperMs'], 163.9907)
        self.assertIsNone(controller.last)
        self.assertIsNone(controller.next_action(471_000_000))
        self.release(controller)
        fresh = sample(4, 540, candidates=1, epoch=1)
        controller.observe(fresh, 550_000_000, 1)
        self.assertEqual(controller.source_hold['phase'], 'completed')
        self.assertEqual(controller.initial_target_deadline_ns, 1_500_000_000)
        self.assertEqual(controller.next_action(550_000_000)['frameId'], 4)

    def test_pending_unknown_or_unsettled_action_never_enters_hold(self):
        for state in ('prepared', 'transmitted', 'accepted', 'cancelled'):
            controller = self.ready()
            if state == 'cancelled':
                next(iter(controller.receipts.values()))['status'] = 'cancelled'
            else:
                controller.observe(sample(4, 400, candidates=0), 400_000_000, 1)
                request = controller.next_action(400_000_000)
                if state in ('transmitted', 'accepted'): controller.transmitting(400_000_000)
                if state == 'accepted': controller.admission(dict(type='accepted', requestId=request['requestId'], acceptedAtMs=410), b'')
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, 'settled idle hold'):
                self.trigger(controller, now=570_000_000)
            self.assertIsNone(controller.source_hold)

    def test_stale_identity_clock_and_immutable_changes_remain_terminal(self):
        for change in ('capture', 'timestampType', 'clockArithmetic', 'frameId', 'pose', 'crop', 'worldEpoch'):
            controller = self.ready()
            frame = copy.deepcopy(controller.last_distinct)
            frame.update(sourceFrameAgeMs=163, serverNowMs=463)
            if change == 'capture': frame['sourceFrame']['captureEpoch'] = 'foreign'
            elif change == 'timestampType': frame['sourceFrame']['timestamp100ns'] = True
            elif change == 'clockArithmetic': frame['serverNowMs'] += 1
            elif change == 'frameId': frame['frameId'] = 4
            elif change == 'pose': frame['navigationPose']['x'] += .01
            elif change == 'crop': frame['combatEvidence']['playerHealthMatchingPixels'] += 1
            else: frame['worldReadiness']['epoch'] += 1
            with self.subTest(change=change), self.assertRaises(RuntimeError): controller.observe(frame, 470_000_000, 1)
            self.assertIsNone(controller.source_hold)

    def test_positive_hazards_win_during_reacquisition(self):
        for change in ('health', 'enemy', 'motion', 'readiness', 'ground'):
            controller = self.ready()
            self.trigger(controller); self.release(controller)
            frame = sample(4, 500, candidates=0, epoch=1)
            if change == 'health': frame['combatEvidence']['playerHealthFractionEstimate'] = .5
            elif change == 'enemy': frame['combatEvidence']['redMaskOverloaded'] = True
            elif change == 'motion': frame['motionEvidence']['spaceKeyMatched'] = True
            elif change == 'readiness': frame['worldReadiness'].update(ready=False, reason='foreign_pause')
            else: frame['groundControlEvidence']['groundControlsConfirmed'] = False
            with self.subTest(change=change), self.assertRaises(RuntimeError): controller.observe(frame, 510_000_000, 1)
            self.assertEqual(controller.actions, 1)

    def test_release_requires_owned_tail_empty_state_and_exact_next_epoch(self):
        for change in ('active', 'held', 'tail', 'foreignReceipt', 'epoch', 'capture', 'earlyRelease', 'earlyClient', 'duplicate'):
            controller = self.ready(); self.trigger(controller)
            ack = settled_release(controller, 470)
            now = 475_000_000
            if change == 'active': ack['executionContext']['active'] = {}
            elif change == 'held': ack['executionContext']['trackedState']['heldKeys'] = ['W']
            elif change == 'tail': ack['executionContext']['events'] = []
            elif change == 'foreignReceipt': ack['executionContext']['events'][0]['requestId'] = 'foreign'
            elif change == 'epoch': ack['worldReadiness']['epoch'] += 1
            elif change == 'capture': ack['worldReadiness']['sourceFrame']['captureEpoch'] = 'foreign'
            elif change == 'earlyRelease': ack['executionContext']['events'][-2]['atMs'] = 460
            elif change == 'earlyClient': now = 469_000_000
            else: controller.source_reacquisition_released(ack, b'', now)
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError, TypeError)):
                controller.source_reacquisition_released(ack, b'', now)
            self.assertEqual(controller.actions, 1)

    def test_post_release_floor_never_promotes_old_or_pre_margin_pixels(self):
        controller = self.ready(); original, _ = self.trigger(controller); self.release(controller)
        original.update(serverNowMs=480, sourceFrameAgeMs=180)
        original['worldReadiness'] = sample(4, 470, epoch=1)['worldReadiness']
        readiness_projection(original)
        for frame, now in ((original, 485_000_000), (sample(4, 530, candidates=0, epoch=1), 540_000_000)):
            self.assertEqual(controller.observe(frame, now, 1), 'waitingForReacquiredSource')
            self.assertIsNone(controller.next_action(now))
            self.assertIsNone(controller.target_seen_at)
            self.assertEqual(controller.last_distinct['frameId'], 3)
        controller.observe(sample(5, 531, candidates=1, epoch=1), 541_000_000, 1)
        self.assertEqual(controller.source_hold['reacquiredFrameId'], 5)

    def test_pre_margin_frame_cannot_change_or_reuse_held_source_identity(self):
        for change in ('sameIdChangedTime', 'newIdSameTime', 'regressedId', 'regressedClient', 'regressedServer'):
            controller = self.ready(); old, _ = self.trigger(controller); self.release(controller)
            frame = sample(4, 500, candidates=0, epoch=1)
            now = 510_000_000
            if change == 'sameIdChangedTime': frame['frameId'] = 3
            elif change == 'newIdSameTime': frame['sourceFrame']['timestamp100ns'] = old['sourceFrame']['timestamp100ns']
            elif change == 'regressedId': frame['frameId'] = 2
            elif change == 'regressedClient': now = 474_000_000
            else: frame.update(serverNowMs=460, sourceFrameAgeMs=-40)
            with self.subTest(change=change), self.assertRaises(RuntimeError): controller.observe(frame, now, 1)
            self.assertEqual(controller.actions, 1)

    def test_fresh_source_still_requires_complete_pose_ground_and_150ms_age(self):
        for change in ('pose', 'ground', 'freshness', 'timestamp', 'capture'):
            controller = self.ready(); self.trigger(controller); self.release(controller)
            frame = sample(4, 540, candidates=1, epoch=1)
            if change == 'pose': frame['navigationPose']['positionConfidence'] = .5
            elif change == 'ground': frame['groundControlEvidence']['groundControlsConfirmed'] = False
            elif change == 'freshness': frame.update(serverNowMs=690, sourceFrameAgeMs=150)
            elif change == 'timestamp': frame['sourceFrame']['timestamp100ns'] = controller.last_distinct['sourceFrame']['timestamp100ns']
            else: frame['sourceFrame']['captureEpoch'] = 'foreign'
            with self.subTest(change=change), self.assertRaises(RuntimeError): controller.observe(frame, 700_000_000, 1)
            self.assertEqual(controller.actions, 1)

    def test_hold_clips_original_acquisition_lease_and_target_loss_deadlines(self):
        for kind in ('500ms', 'acquisition', 'lease', 'targetLoss'):
            controller = self.ready(target=kind == 'targetLoss', deadline=800_000_000 if kind == 'lease' else None)
            now = 1_200_000_000 if kind == 'acquisition' else 470_000_000
            age = 600 if kind == 'targetLoss' else 163.0292
            self.trigger(controller, now=now, age=age, rtt=1)
            expected = {'500ms': 970_000_000, 'acquisition': 1_500_000_000,
                        'lease': 800_000_000, 'targetLoss': 619_000_000}[kind]
            self.assertEqual(controller.source_hold['deadlineClientNs'], expected)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError): controller.check(expected)

    def test_waiting_duplicate_and_unavailable_polls_never_renew_hold(self):
        controller = self.ready(); original, _ = self.trigger(controller); self.release(controller)
        deadline = controller.source_hold['deadlineClientNs']
        for index in range(3):
            frame = copy.deepcopy(original)
            frame.update(serverNowMs=480 + index * 20, sourceFrameAgeMs=180 + index * 20)
            frame['worldReadiness'] = sample(4, 470, epoch=1)['worldReadiness']
            readiness_projection(frame)
            controller.observe(frame, 485_000_000 + index * 20_000_000, 1)
            controller.observe(dict(type='waiting'), 495_000_000 + index * 20_000_000, 1)
            self.assertEqual(controller.source_hold['deadlineClientNs'], deadline)
        with self.assertRaisesRegex(RuntimeError, 'source_reacquisition_deadline'):
            controller.observe(dict(type='waiting'), deadline, 1)

    def test_second_stale_hold_is_refused_and_first_use_is_retained(self):
        controller = self.ready(); self.trigger(controller); self.release(controller)
        controller.observe(sample(4, 540, candidates=1, epoch=1), 550_000_000, 1)
        with self.assertRaisesRegex(RuntimeError, 'settled idle hold'): self.trigger(controller, now=710_000_000)
        self.assertEqual(controller.source_reacquisition()['used'], 1)
        self.assertEqual(controller.source_hold['reacquiredFrameId'], 4)

    def test_historical_and_v1_stale_behavior_is_unchanged(self):
        for kind in ('historicalV2', 'v1'):
            controller = self.ready(enabled=False) if kind == 'historicalV2' else approach.ApproachController(binding(), HELLO, 0, source_reacquisition=True)
            if kind == 'v1':
                for index in (1, 2, 3): controller.observe(sample(index, index * 100), index * 100_000_000, 1)
                request = controller.next_action(300_000_000); complete(controller, request)
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, 'Native source stale or malformed'):
                self.trigger(controller)
            self.assertIsNone(controller.source_hold)

    def test_reacquisition_does_not_reset_final_dispatch_headroom(self):
        controller = self.ready(); self.trigger(controller, now=1_100_000_000)
        self.release(controller, now=1_105_000_000)
        controller.observe(sample(4, 540, candidates=0, epoch=1), 1_250_000_000, 1)
        request = controller.next_action(1_250_000_000)
        self.assertIsNotNone(request)
        with self.assertRaisesRegex(RuntimeError, 'approach_dispatch_budget'): controller.transmitting(1_301_000_000)
        self.assertFalse(controller.pending['transmissionAttempted'])
        self.assertEqual(controller.abandon_prepared('budget')['transmissionAttempted'], False)

    def episode(self, *, timeout=False, stop=False, producer_wait=False):
        """Run the real recorder/controller/auditor boundary with only a synthetic bridge and clock."""
        clock = Clock()
        bound = approach.bind_review(*InitialTargetAcquisitionTests().parts())
        captured = {}
        base_controller = approach.ApproachController
        def construct(*args, **kwargs):
            captured['controller'] = base_controller(*args, **kwargs)
            return captured['controller']
        class HoldBridge(FakeBridge):
            def __init__(self):
                super().__init__(clock)
                self.last_frame = None
                self.held = False
            def request(self, command, **arguments):
                if command == 'frame' and (self.number == 3 or timeout and self.held):
                    self.calls.append((command, {}))
                    clock.sleep(.1)
                    self.number += 1
                    frame = copy.deepcopy(self.last_frame)
                    frame.update(serverNowMs=self.number * 100 + 63, sourceFrameAgeMs=self.number * 100 + 63 - 300)
                    frame['worldReadiness'] = sample(self.number, self.number * 100, epoch=self.epoch)['worldReadiness']
                    frame['receipts'], self.pending = self.pending, []
                    if self.held: readiness_projection(frame)
                    return frame, bytes([30, 45, 65]) * (192 * 192)
                if command == 'release' and captured['controller'].waiting_for_source() and not self.held:
                    self.calls.append((command, {}))
                    clock.sleep(.001)
                    self.epoch += 1
                    self.held = True
                    return settled_release(captured['controller'], self.number * 100 + 70, self.epoch), b''
                frame, pixels = super().request(command, **arguments)
                if command == 'frame':
                    if self.number <= 5: frame['combatEvidence']['enemyBarCandidates'] = []
                    if producer_wait and self.held and self.number in (5, 6):
                        frame['frameWorldReadiness'].update(ready=False, reason='world_confirming')
                        frame['worldReadiness'].update(ready=self.number == 6,
                            reason='world_ready' if self.number == 6 else 'world_confirming')
                        readiness_projection(frame)
                    self.last_frame = copy.deepcopy(frame)
                return frame, pixels
        bridge = HoldBridge()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name) / 'recording'
        def check():
            if stop and bridge.held: raise RuntimeError('external_STOP')
        with patch.object(approach, 'ApproachController', construct):
            report = approach.run_episode(bridge, bound, folder, clock=clock, sleep=clock.sleep, check=check)
        return bound, bridge, folder, report

    def test_real_episode_reacquires_and_full_audit_preserves_all_receipts(self):
        from audit_encounter_approach import audit_recording
        bound, bridge, folder, report = self.episode()
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['sourceReacquisition']['hold']['reacquiredFrameId'], 6)
        self.assertEqual(report['acceptedActions'], report['terminalReceipts'])
        self.assertEqual(sum(name == 'release' for name, _ in bridge.calls), 3)
        self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'completed')

    def test_real_episode_timeout_and_stop_never_send_after_hold(self):
        from audit_encounter_approach import audit_recording
        for kind in ('timeout', 'STOP'):
            bound, bridge, folder, report = self.episode(timeout=kind == 'timeout', stop=kind == 'STOP')
            self.assertEqual(report['status'], 'failed', report)
            self.assertEqual(report['acceptedActions'], 1)
            self.assertEqual(report['terminalReceipts'], 1)
            self.assertTrue(report['releaseAcknowledged'] and report['stopAcknowledged'])
            self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'failed')

    def test_audit_refuses_changed_hold_clocks_proofs_and_coherent_marker_removal(self):
        from audit_encounter_approach import audit_recording
        bound, _, folder, report = self.episode()
        self.assertEqual(report['status'], 'completed', report)
        original = (folder / 'events.jsonl').read_bytes()
        rows = [json.loads(row) for row in original.splitlines()]
        for change in ('deadline', 'releaseClock', 'releaseEpoch', 'summaryRemoved', 'bothRemoved'):
            altered, events = copy.deepcopy(report), copy.deepcopy(rows)
            if change == 'deadline': altered['sourceReacquisition']['hold']['deadlineClientNs'] += 1
            elif change == 'releaseClock': next(row for row in events if row['type'] == 'sourceReacquisitionRelease')['clientReceivedNs'] = 1
            elif change == 'releaseEpoch': next(row for row in events if row['type'] == 'sourceReacquisitionRelease')['response']['worldReadiness']['epoch'] += 1
            else:
                altered.pop('sourceReacquisition')
                if change == 'bothRemoved':
                    events = [row for row in events if row['type'] != 'sourceReacquisitionRelease'
                              and not (row['type'] == 'navigation' and row.get('outcome') in
                                       ('sourceReacquisitionReleaseRequired', 'waitingForReacquiredSource'))]
            (folder / 'events.jsonl').write_bytes(b''.join(approach.canonical(row) + b'\n' for row in events))
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)):
                audit_recording(folder, bound, altered)
        (folder / 'events.jsonl').write_bytes(original)

    def test_owned_release_old_cached_motion_projection_is_wait_only(self):
        controller = self.ready(); old, _ = self.trigger(controller); ack = self.release(controller)
        old.update(serverNowMs=480, sourceFrameAgeMs=180)
        old['worldReadiness'] = copy.deepcopy(ack['worldReadiness'])
        readiness_projection(old)
        original = copy.deepcopy(controller.last_distinct)
        self.assertEqual(controller.observe(old, 485_000_000, 1), 'waitingForReacquiredSource')
        self.assertEqual(controller.last_distinct, original)
        self.assertIsNone(controller.next_action(485_000_000))
        self.assertEqual(controller.actions, 1)

    def test_native_two_confirmation_states_wait_without_promoting_health_pose_or_bars(self):
        controller = self.ready(); self.trigger(controller); self.release(controller)
        deadline = controller.source_hold['deadlineClientNs']
        for frame in (confirming_source(unavailable=True), confirming_source(current_ready=True)):
            self.assertEqual(controller.observe(frame, 510_000_000, 1), 'waitingForReacquiredSource')
            self.assertEqual(controller.last_distinct['frameId'], 3)
            self.assertIsNone(controller.target_seen_at)
            self.assertIsNone(controller.next_action(510_000_000))
            self.assertEqual(controller.source_hold['deadlineClientNs'], deadline)
        controller.observe(sample(5, 540, candidates=1, epoch=1), 550_000_000, 1)
        self.assertEqual(controller.source_hold['reacquiredFrameId'], 5)
        self.assertEqual(controller.next_action(550_000_000)['frameId'], 5)

    def test_invalidated_source_must_be_at_or_before_exact_owned_ack(self):
        for at in (460, 470):
            controller = self.ready(); self.trigger(controller); self.release(controller)
            frame = confirming_source(at=at, reason='world_observation_invalidated')
            frame.update(serverNowMs=480, sourceFrameAgeMs=480-at)
            self.assertEqual(controller.observe(frame, 490_000_000, 1), 'waitingForReacquiredSource')
        for location in ('current', 'frame'):
            controller = self.ready(); self.trigger(controller); self.release(controller)
            frame = confirming_source(reason='world_observation_invalidated')
            if location == 'current':
                frame['frameWorldReadiness']['reason'] = 'world_confirming'
            else:
                frame['worldReadiness']['reason'] = 'world_confirming'
            with self.subTest(location=location), self.assertRaisesRegex(RuntimeError, 'invalidation'):
                controller.observe(frame, 510_000_000, 1)

    def test_confirmation_foreign_epoch_capture_reason_or_identity_stays_terminal(self):
        for change in ('currentEpoch', 'frameEpoch', 'capture', 'currentReason', 'frameReason',
                       'frameSource', 'frameId', 'available', 'oldEpochNewSource'):
            controller = self.ready(); self.trigger(controller); self.release(controller)
            frame = confirming_source()
            if change == 'currentEpoch': frame['worldReadiness']['epoch'] += 1
            elif change == 'frameEpoch': frame['frameWorldReadiness']['epoch'] += 1
            elif change == 'capture': frame['worldReadiness']['sourceFrame']['captureEpoch'] = 'foreign'
            elif change == 'currentReason': frame['worldReadiness']['reason'] = 'world_observation_stale'
            elif change == 'frameReason': frame['frameWorldReadiness']['reason'] = 'foreign_pause'
            elif change == 'frameSource': frame['frameWorldReadiness']['sourceFrame']['timestamp100ns'] += 1
            elif change == 'frameId': frame['frameWorldReadiness']['sourceFrameId'] += 1
            elif change == 'available': frame['inputAvailable'] = True
            else: frame['frameWorldReadiness'].update(epoch=0, ready=True, reason='world_ready')
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                controller.observe(frame, 510_000_000, 1)
            self.assertEqual(controller.actions, 1)

    def test_confirmation_cannot_mask_positive_hazards_or_arbitrary_unavailable_evidence(self):
        for change in ('health', 'enemy', 'ground', 'motion', 'projectionExtra', 'projectionBool',
                       'hudReason', 'groundReason', 'missingHud'):
            controller = self.ready(); self.trigger(controller); self.release(controller)
            frame = confirming_source(unavailable=change in ('hudReason', 'groundReason'))
            if change == 'health': frame['combatEvidence']['playerHealthFractionEstimate'] = .5
            elif change == 'enemy': frame['combatEvidence']['redMaskOverloaded'] = True
            elif change == 'ground': frame['groundControlEvidence']['groundControlsConfirmed'] = False
            elif change == 'motion': frame['motionEvidence']['status'] = 'climbing'
            elif change == 'projectionExtra': frame['motionEvidence']['extra'] = True
            elif change == 'projectionBool': frame['motionEvidence']['recognitionMs'] = False
            elif change == 'hudReason': frame['combatEvidence']['reason'] = 'recognition_failed'
            elif change == 'groundReason': frame['groundControlEvidence']['reason'] = 'recognition_failed'
            else: frame.pop('combatEvidence')
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                controller.observe(frame, 510_000_000, 1)
            self.assertEqual(controller.actions, 1)

    def test_masked_old_frame_still_requires_every_other_immutable_byte(self):
        for change in ('pose', 'hud', 'ground', 'frameGate'):
            controller = self.ready(); old, _ = self.trigger(controller); ack = self.release(controller)
            old.update(serverNowMs=480, sourceFrameAgeMs=180)
            old['worldReadiness'] = copy.deepcopy(ack['worldReadiness'])
            readiness_projection(old)
            if change == 'pose': old['navigationPose']['x'] += .01
            elif change == 'hud': old['combatEvidence']['playerHealthMatchingPixels'] += 1
            elif change == 'ground': old['groundControlEvidence']['recognitionMs'] += .01
            else: old['frameWorldReadiness']['epoch'] = 1
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                controller.observe(old, 485_000_000, 1)

    def test_confirmation_polls_do_not_extend_original_clipped_clocks(self):
        for kind in ('hold', 'acquisition', 'lease', 'targetLoss'):
            controller = self.ready(target=kind == 'targetLoss', deadline=800_000_000 if kind == 'lease' else None)
            now = 1_200_000_000 if kind == 'acquisition' else 470_000_000
            self.trigger(controller, now=now, age=600 if kind == 'targetLoss' else 163.0292, rtt=1)
            # The synthetic native clock must remain later than the triggering envelope.
            ack_at = 910 if kind == 'targetLoss' else 470
            self.release(controller, at=ack_at, now=now+5_000_000)
            deadline = controller.source_hold['deadlineClientNs']
            frame = confirming_source(at=ack_at+30)
            self.assertEqual(controller.observe(frame, now+10_000_000, 1), 'waitingForReacquiredSource')
            self.assertEqual(controller.source_hold['deadlineClientNs'], deadline)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError): controller.observe(frame, deadline, 1)
            self.assertEqual(controller.actions, 1)

    def test_real_episode_and_auditor_accept_only_complete_post_confirmation_source(self):
        from audit_encounter_approach import audit_recording
        bound, bridge, folder, report = self.episode(producer_wait=True)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['sourceReacquisition']['hold']['reacquiredFrameId'], 7)
        self.assertEqual(report['acceptedActions'], report['terminalReceipts'])
        rows = [json.loads(line) for line in (folder / 'events.jsonl').read_bytes().splitlines()]
        waiting = [row for row in rows if row.get('type') == 'observation'
                   and row['frame'].get('motionEvidence', {}).get('reason') == 'world_not_ready']
        self.assertEqual([row['frame']['frameId'] for row in waiting], [5, 6])
        self.assertEqual(audit_recording(folder, bound, report)['episodeStatus'], 'completed')
        original = (folder / 'events.jsonl').read_bytes()
        waiting[0]['frame']['worldReadiness']['reason'] = 'foreign_pause'
        (folder / 'events.jsonl').write_bytes(b''.join(approach.canonical(row)+b'\n' for row in rows))
        with self.assertRaises((RuntimeError, ValueError)): audit_recording(folder, bound, report)
        (folder / 'events.jsonl').write_bytes(original)


if __name__ == '__main__':
    unittest.main()
