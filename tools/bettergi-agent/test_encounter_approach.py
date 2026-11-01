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


class WorkerBoundaryTests(unittest.TestCase):
    """Exercise the actual Bridge interface without opening an OS pipe, process or model."""

    @classmethod
    def setUpClass(cls):
        cls.bound = binding()

    def simulate(self, *, reject_identity=False, stop_on_discovery=False, expire_during_start=False,
                 close_failure=False, review_expiry_during_discovery=False):
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
                return {}, copy.deepcopy(child)
            def identity(*args):
                if reject_identity:
                    raise ValueError('wrong native pipe owner')
            success = dict(status='completed', releaseAcknowledged=True, stopAcknowledged=True, receiptsComplete=True)
            stack.enter_context(patch.object(approach, 'verify_plan', return_value=(plan, folder, sha)))
            stack.enter_context(patch.object(approach, 'ordinary_identity', return_value=dict(processId=44, parentProcessId=33)))
            stack.enter_context(patch.object(approach, 'owner_pair', side_effect=owners))
            stack.enter_context(patch.object(approach, 'run_episode', return_value=success))
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


if __name__ == '__main__':
    unittest.main()
