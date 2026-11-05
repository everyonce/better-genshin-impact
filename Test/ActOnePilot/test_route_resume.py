import importlib.util
import copy
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'quest-pilot' / 'act-one-route.py'
spec = importlib.util.spec_from_file_location('act_one_route', SCRIPT)
route_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route_tool)
command_spec = importlib.util.spec_from_file_location('route_test_command', SCRIPT.with_name('act-one-command.py'))
command_tool = importlib.util.module_from_spec(command_spec)
command_spec.loader.exec_module(command_tool)


class FakeClock:
    def __init__(self, root, on_poll=None):
        self.root = root
        self.value = 0.0
        self.on_poll = on_poll
        self.handled = set()

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds
        if self.on_poll is None:
            return
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        if request['id'] in self.handled:
            return
        self.handled.add(request['id'])
        self.on_poll(request)


class ActOneRouteResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = 'session-5-test'
        self.waypoints = [
            {'map': 'Teyvat', 'x': -1200, 'y': 2200},
            {'map': 'Teyvat', 'x': -1180, 'y': 2240},
            {'map': 'Teyvat', 'x': -1160, 'y': 2280},
        ]
        self.route = {'objective': 'Go to Mondstadt', 'waypoints': self.waypoints}
        self.write_observation(1)

    def tearDown(self):
        self.temp.cleanup()

    def write_observation(self, frame):
        (self.root / 'observation.json').write_text(json.dumps({'session': self.session, 'frameId': frame}), encoding='utf-8')

    def write_receipt(self, request, status, result, frame):
        self.write_observation(frame)
        receipt = {'session': self.session, 'id': request['id'], 'mission': 'navigation', 'status': status,
                   'frameId': frame, 'details': {'result': result}}
        (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')

    def test_pending_existing_request_is_refused_before_any_write(self):
        previous = {'id': 'already-running', 'session': self.session, 'mission': 'navigation'}
        (self.root / 'request.json').write_text(json.dumps(previous), encoding='utf-8')
        (self.root / 'receipt.json').write_text(json.dumps({'id': 'already-running', 'session': self.session,
                                                             'mission': 'navigation', 'status': 'started'}), encoding='utf-8')
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            with self.assertRaises(route_tool.RouteError):
                route_tool.run_route(self.root, self.route, self.session, emit=lambda _: None)
        self.assertEqual(write_request.call_count, 0)
        self.assertEqual(json.loads((self.root / 'request.json').read_text()), previous)

    def test_matching_terminal_prior_request_allows_new_route(self):
        previous = {'id': 'already-finished', 'session': self.session, 'mission': 'navigation'}
        (self.root / 'request.json').write_text(json.dumps(previous), encoding='utf-8')
        (self.root / 'receipt.json').write_text(json.dumps({'id': 'already-finished', 'session': self.session,
                                                             'mission': 'navigation', 'status': 'completed'}), encoding='utf-8')

        def on_poll(request):
            self.write_receipt(request, 'completed', {'status': 'arrived',
                                                       'nextWaypointIndex': len(request['waypoints'])}, 2)

        clock = FakeClock(self.root, on_poll)
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=lambda _: None)
        self.assertEqual(result, 'arrived')
        self.assertEqual(write_request.call_count, 1)
    def test_deadline_checkpoint_resumes_exact_remaining_sequence_with_fresh_id_and_frame(self):
        seen = []

        def on_poll(request):
            seen.append(request)
            if len(seen) == 1:
                self.write_receipt(request, 'failed', {'status': 'stopped', 'reason': 'Navigation deadline reached',
                                                       'nextWaypointIndex': 1}, 2)
            else:
                self.write_receipt(request, 'completed', {'status': 'arrived',
                                                          'nextWaypointIndex': len(request['waypoints'])}, 3)

        clock = FakeClock(self.root, on_poll)
        writes = []
        atomic = route_tool.atomic

        def count_atomic(path, value):
            writes.append(value)
            atomic(path, value)

        output = []
        with mock.patch.object(route_tool, 'atomic', side_effect=count_atomic):
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(result, 'arrived')
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0]['id'], seen[1]['id'])
        self.assertEqual(seen[0]['expectedFrameId'], 1)
        self.assertEqual(seen[1]['expectedFrameId'], 2)
        self.assertEqual(seen[1]['waypoints'], self.waypoints[1:])
        self.assertEqual(len(writes), 2)

    def test_stale_terminal_observation_stops_without_submitting_resume(self):
        def on_poll(request):
            receipt = {'session': self.session, 'id': request['id'], 'mission': 'navigation', 'status': 'failed',
                       'frameId': 2, 'details': {'result': {'status': 'stopped', 'reason': 'Navigation deadline reached',
                                                            'nextWaypointIndex': 1}}}
            (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
            self.write_observation(1)

        clock = FakeClock(self.root, on_poll)
        output = []
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            with self.assertRaises(route_tool.RouteError):
                route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                     monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(write_request.call_count, 1)

    def test_client_timeout_reports_pending_and_never_replays(self):
        clock = FakeClock(self.root)
        output = []
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(result, 'pending')
        self.assertEqual(write_request.call_count, 1)
        self.assertTrue(any('pending' in line and 'Do not replay' in line for line in output))


    def test_non_deadline_stop_is_terminal_and_never_resumes(self):
        def on_poll(request):
            self.write_receipt(request, 'failed', {'status': 'stopped', 'reason': 'Map coordinates stalled',
                                                   'nextWaypointIndex': 1}, 2)

        clock = FakeClock(self.root, on_poll)
        output = []
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(result, 'stopped')
        self.assertEqual(write_request.call_count, 1)
class ControllerClock:
    """Keep all simulated mission time on one original controller clock."""

    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def milliseconds(self):
        return int(1_700_000_000_000 + self.value * 1000)

    def advance(self, seconds):
        self.value += seconds


def controller_scene(kind='world', objective='Defeat the nearby hilichurls', *, enemies=False):
    """Use the normal native observation layout, including account and numeric HP."""
    value = {'session': 'route-session', 'frameId': 1, 'timestamp': 0,
             'screenshotPath': 'observations/route-session/frame-0001.png',
             'ocr': [{'text': 'UID: 693306810', 'x': 1720, 'y': 1050}],
             'map': {'map': 'Teyvat', 'x': -1178.0, 'y': 2208.0, 'cameraAngle': 90},
             'hud': {'world': True, 'groundControls': True, 'auto': False,
                     'health': {'current': 900, 'max': 1000}, 'lowHealth': False,
                     'enemyBars': [{'x': 900, 'y': 300, 'width': 100}] if enemies else [],
                     'objectives': [objective]}}
    if kind in ('dialogue', 'journal', 'modal'):
        value['map'] = None
        value['hud'].update(world=False, groundControls=False, health=None)
    if kind == 'dialogue':
        value['hud'].update(auto=True, dialogueReady=True)
        value['ocr'].append({'text': 'Auto', 'x': 45, 'y': 47})
    if kind == 'journal':
        value['hud']['journal'] = True
        value['ocr'].append({'text': 'Going Upon the Breeze', 'x': 130, 'y': 170})
    if kind == 'inventory':
        value['map'] = None
        value['hud'].update(world=False, groundControls=False, health=None,
                            dialogueReady=False, choice=False, journal=False, bigMap=False, climbing=False)
        value['ocr'].extend([
            {'text': 'Food', 'x': 120, 'y': 30, 'width': 90, 'height': 30},
            {'text': 'Inventory capacity 12/2000', 'x': 1500, 'y': 30, 'width': 250, 'height': 30},
            {'text': 'Sweet Madame', 'x': 1400, 'y': 130, 'width': 250, 'height': 40}])
    return value


def record_ground_scan(source):
    """Represent the same-frame measurement produced by an explicit native ground observation."""
    stamp = dict(session=source['session'], frameId=source['frameId'], capturedAt=source['timestamp'])
    hud = source['hud']
    count = len(hud['enemyBars'])
    hud['captureStamp'] = dict(stamp, source='game-capture-start')
    hud['enemyBarObservation'] = dict(stamp, version=1, kind='normal-ground-enemy-observation-v1',
        state='threat' if count else 'clear', candidateCount=count, acceptedCount=count)


class ReplayPilot:
    """Replay serial native-shaped results without any process or input calls."""

    def __init__(self, clock, script=(), source=None):
        self.clock, self.script = clock, list(script)
        self.session, self.pending, self.stop = 'route-session', None, False
        self.source = copy.deepcopy(source or controller_scene())
        self.source['timestamp'] = clock.milliseconds()
        self.calls = []

    def stopped(self):
        return self.stop

    def validate_route(self, route, deadline_ms):
        command_tool.validate_navigation_plan(route, min(45000, deadline_ms))

    def inventory_ready(self, source):
        return source.get('map') is None and any(row.get('text') == 'Food' for row in source['ocr'])

    def deadline_resume(self, route, start, receipt, request):
        return command_tool.resume_navigation_route(route, dict(session=self.session,
            requestId=request['id'], startIndex=start, routeHash=command_tool.navigation_route_hash(route)),
            receipt, request, self.session)

    def current(self):
        return copy.deepcopy(self.source)

    def execute(self, mission, source, fields, deadline, save_pending):
        if self.pending is not None:
            raise AssertionError('Overlapping mission')
        request = dict(id='mission-' + format(len(self.calls) + 1, '032x'),
                       session=self.session, expectedFrameId=source['frameId'],
                       createdAt=self.clock.milliseconds(), mission=mission, **copy.deepcopy(fields))
        self.calls.append(copy.deepcopy(request))
        self.pending = request
        save_pending(request)
        if mission == 'observe':
            item = dict(status='completed', result=None)
        else:
            if not self.script:
                raise AssertionError('Unexpected additional input mission: ' + mission)
            item = self.script.pop(0)
            if item['mission'] != mission:
                raise AssertionError((item['mission'], mission))
        self.clock.advance(item.get('seconds', .02))
        if item.get('pending'):
            raise route_tool.RouteError('Exact request remains unresolved')
        frame = self.source['frameId'] + 1
        self.source = copy.deepcopy(item.get('source', self.source))
        self.source.update(session=self.session, frameId=frame, timestamp=self.clock.milliseconds())
        if mission == 'observe' and self.source['hud'].get('groundControls'):
            record_ground_scan(self.source)
        receipt = dict(id=request['id'], session=self.session, mission=mission,
                       status=item.get('status', 'completed'), frameId=frame,
                       details=dict(result=copy.deepcopy(item.get('result')), inputEvents=[]))
        if item.get('foreign'):
            receipt['session'] = 'other-session'
        self.pending = None
        return dict(request=request, receipt=receipt, observation=copy.deepcopy(self.source), cancelled=False)


class SupervisedRouteControllerTests(unittest.TestCase):
    """Cover actual handoff shapes, fresh replanning, limits and durable failures."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = ControllerClock()
        self.progress = Path(self.temp.name) / 'progress.json'
        self.points = [{'map': 'Teyvat', 'x': x, 'y': 2208} for x in (-1178, -1173, -1168)]
        self.route = dict(objective='Defeat the nearby hilichurls', waypoints=self.points)

    def tearDown(self):
        self.temp.cleanup()

    def run_controller(self, pilot, **kwargs):
        return route_tool.run_controller(pilot, self.route, self.progress, '693306810',
            monotonic=self.clock.monotonic, clock_ms=self.clock.milliseconds, emit=lambda _: None, **kwargs)

    def handoff(self, source=None):
        return dict(mission='navigation', source=source or controller_scene(), result=dict(
            status='completed', outcome='objective_completed', localHandoff=True,
            navigation=dict(status='stopped', reason='Enemy acquired', nextWaypointIndex=1)))

    def arrival(self, count=2, source=None):
        return dict(mission='navigation', source=source or controller_scene(),
                    result=dict(status='arrived', nextWaypointIndex=count))

    def test_completed_native_handoff_resumes_only_remaining_waypoints(self):
        pilot = ReplayPilot(self.clock, [self.handoff(), self.arrival()])
        report = self.run_controller(pilot)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('arrived', 3))
        navigation = [r for r in pilot.calls if r['mission'] == 'navigation']
        self.assertEqual(navigation[0]['waypoints'], self.points)
        self.assertEqual(navigation[1]['waypoints'], self.points[1:])
        self.assertGreater(navigation[1]['expectedFrameId'], navigation[0]['expectedFrameId'])
        self.assertEqual(read_json(self.progress), report)

    def test_combat_dialogue_new_objective_and_route_keep_one_cursor(self):
        world = controller_scene(objective='Go to Mondstadt')
        pilot = ReplayPilot(self.clock, [self.handoff(controller_scene('dialogue')),
            dict(mission='dialogue', result=dict(status='completed', reason='world_returned'), source=world),
            self.arrival(source=world)])
        report = self.run_controller(pilot, allow_dialogue=True, continuation_objectives=['Go to Mondstadt'])
        self.assertEqual(report['status'], 'arrived')
        inputs = [r for r in pilot.calls if r['mission'] != 'observe']
        self.assertEqual([r['mission'] for r in inputs], ['navigation', 'dialogue', 'navigation'])
        self.assertEqual(inputs[-1]['objective'], 'Go to Mondstadt')
        self.assertEqual(inputs[-1]['waypoints'], self.points[1:])

    def test_completed_combat_journal_has_one_fixed_escape_then_fresh_observe(self):
        pilot = ReplayPilot(self.clock, [self.handoff(controller_scene('journal')),
            dict(mission='keyPress', result=None, source=controller_scene()), self.arrival()])
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'arrived')
        keys = [r for r in pilot.calls if r['mission'] == 'keyPress']
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]['key'], 'VK_ESCAPE')
        index = pilot.calls.index(keys[0])
        self.assertEqual(pilot.calls[index + 1]['mission'], 'observe')

    def test_initial_journal_does_not_grant_escape(self):
        pilot = ReplayPilot(self.clock, source=controller_scene('journal'))
        self.assertEqual(self.run_controller(pilot)['status'], 'waiting')
        self.assertEqual([x['mission'] for x in pilot.calls], ['observe'])

    def test_direct_enemy_uses_existing_bounded_combat_then_route(self):
        pilot = ReplayPilot(self.clock, [dict(mission='combat', source=controller_scene(),
            result=dict(status='completed', outcome='objective_completed')), self.arrival(3)],
            source=controller_scene(enemies=True))
        self.assertEqual(self.run_controller(pilot)['status'], 'arrived')
        combat = [x for x in pilot.calls if x['mission'] == 'combat'][0]
        self.assertEqual(combat['deadlineMs'], 20000)
        self.assertEqual(combat['objective'], self.route['objective'])

    def test_failed_navigation_retains_cursor_without_retry(self):
        pilot = ReplayPilot(self.clock, [dict(mission='navigation', status='failed',
            result=dict(status='stopped', reason='Map coordinates stalled', nextWaypointIndex=1))])
        report = self.run_controller(pilot)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('stopped', 1))
        self.assertEqual(len(pilot.calls), 2)
        self.assertEqual(report['records'][-1]['receipt']['status'], 'failed')
        self.assertIsNone(report['pending'])

    def test_positive_deadline_checkpoint_resumes_bounded_remaining_route(self):
        pilot = ReplayPilot(self.clock, [dict(mission='navigation', status='failed', seconds=10,
            result=dict(status='stopped', reason='Navigation deadline reached', nextWaypointIndex=1)),
            self.arrival()])
        report = self.run_controller(pilot)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('arrived', 3))
        navigation = [r for r in pilot.calls if r['mission'] == 'navigation']
        self.assertEqual(navigation[-1]['waypoints'], self.points[1:])
        self.assertEqual(report['records'][1]['receipt']['status'], 'failed')
        self.assertLess(self.clock.value - 100, 90)

    def test_zero_progress_deadline_never_retries(self):
        pilot = ReplayPilot(self.clock, [dict(mission='navigation', status='failed',
            result=dict(status='stopped', reason='Navigation deadline reached', nextWaypointIndex=0))])
        self.assertEqual(self.run_controller(pilot)['status'], 'stopped')
        self.assertEqual(len(pilot.calls), 2)

    def test_uid_expected_plus_conflicting_or_duplicate_is_ambiguous(self):
        for index, text in enumerate(['UID: 111111111', '693306810']):
            self.progress = Path(self.temp.name) / ('uid-' + str(index) + '.json')
            source = controller_scene()
            source['ocr'].append(dict(text=text, x=1710, y=1040))
            pilot = ReplayPilot(self.clock, source=source)
            self.assertEqual(self.run_controller(pilot)['status'], 'waiting')
            self.assertEqual([r['mission'] for r in pilot.calls], ['observe'])

    def test_exploration_empty_objectives_uses_owned_inventory_entry(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        source = controller_scene(); source['hud']['objectives'] = []
        inventory = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=inventory,
            result=dict(status='completed', step='worldInventory', pausedInventory=True)),
            self.arrival(3, inventory)], source=source)
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'arrived')
        inputs = [r for r in pilot.calls if r['mission'] != 'observe']
        self.assertEqual([r['mission'] for r in inputs], ['questStep', 'navigation'])
        self.assertEqual(inputs[0]['step'], 'worldInventory')
        self.assertEqual(inputs[1]['objective'], route_tool.EXPLORATION_OBJECTIVE)
        self.assertIs(inputs[1]['requireMeasuredGround'], True)
        self.assertLessEqual(inputs[1]['deadlineMs'], 45000)

    def test_exploration_begins_from_the_inventory_left_by_travel(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv = controller_scene('inventory')
        ground = controller_scene(objective='')
        pilot = ReplayPilot(self.clock, [
            dict(mission='questStep', source=ground, result=dict(worldVisible=True)),
            dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            self.arrival(3, inv)], source=inv)
        result = self.run_controller(pilot)
        self.assertEqual(result['status'], 'arrived')
        self.assertEqual([r.get('step', r['mission']) for r in pilot.calls],
                         ['observe', 'worldInventoryClose', 'observe', 'worldInventory',
                          'observe', 'navigation'])

    def test_unsettled_inventory_close_stops_without_repeating_escape(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=inv,
                                             result=dict(worldVisible=False))], source=inv)
        self.assertEqual(self.run_controller(pilot)['status'], 'waiting')
        self.assertEqual([r.get('step', r['mission']) for r in pilot.calls],
                         ['observe', 'worldInventoryClose', 'observe'])

    def test_invalid_progress_falls_back_to_existing_inventory_bootstrap(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv, ground = controller_scene('inventory'), controller_scene(objective='')
        pilot = ReplayPilot(self.clock, [
            dict(mission='questStep', source=ground, result=dict(worldVisible=True)),
            dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            self.arrival(3, inv)], source=inv)
        pilot.exploration_continuation = mock.Mock(return_value=None)
        result = self.run_controller(pilot, continue_from_progress=Path(self.temp.name) / 'missing.json')
        self.assertEqual(result['status'], 'arrived')
        self.assertEqual([r.get('step', r['mission']) for r in pilot.calls],
                         ['observe', 'worldInventoryClose', 'observe', 'worldInventory', 'observe', 'navigation'])
        self.assertNotIn('continuedFromProgress', result)

    def test_new_start_near_never_borrows_previous_route_position(self):
        self.route.update(objective=route_tool.EXPLORATION_OBJECTIVE,
                          startNear=dict(map='Teyvat', x=-1178, y=2208, radius=3))
        inv, ground = controller_scene('inventory'), controller_scene(objective='')
        pilot = ReplayPilot(self.clock, [
            dict(mission='questStep', source=ground, result=dict(worldVisible=True)),
            dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            self.arrival(3, inv)], source=inv)
        pilot.exploration_continuation = mock.Mock(side_effect=AssertionError('startNear cannot reuse old world'))
        result = self.run_controller(pilot, continue_from_progress=Path(self.temp.name) / 'prior.json')
        self.assertEqual(result['status'], 'arrived')
        pilot.exploration_continuation.assert_not_called()
        self.assertEqual(pilot.calls[1]['step'], 'worldInventoryClose')

    def test_lone_field_encounter_can_return_to_measured_navigation(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        enemy = controller_scene(objective='', enemies=True)
        inv = controller_scene('inventory')
        clear = controller_scene(objective='')
        pause = dict(mission='questStep', source=inv, result=dict(pausedInventory=True))
        proof = dict(verified=True, kind='inventory', session='route-session')
        returned = dict(mission='questStep', status='stopped', source=inv, result=dict(
            nativeGroup=False, nativeAttempted=True, nativeReturned=True, beforeFrameId=4,
            afterFrameId=5, pauseVerified=True, pauseProof=proof, defeatConfirmed=False))
        pilot = ReplayPilot(self.clock, [pause, returned, dict(mission='questStep', source=clear,
            result=dict(worldVisible=True)), pause, self.arrival(3, inv)], source=enemy)
        report = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual((report['status'], report['fieldRotations'], report['nextWaypointIndex']), ('arrived', 1, 3))
        self.assertEqual([r.get('step', r['mission']) for r in pilot.calls if r['mission'] != 'observe'],
                         ['worldInventory','actTwoNativeCombat','worldInventoryClose','worldInventory','navigation'])
        self.assertFalse(returned['result']['defeatConfirmed'])

    def test_threat_interrupt_preserves_completed_waypoints_before_reinspection(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv, clear = controller_scene('inventory'), controller_scene(objective='')
        pause = dict(mission='questStep', source=inv, result=dict(pausedInventory=True))
        interruption = dict(mission='navigation', status='failed', source=inv, result=dict(
            status='stopped', reason='Enemy observed during exploration', nextWaypointIndex=1, pauseVerified=True,
            pauseProof=dict(verified=True, kind='inventory', session='route-session')))
        pilot = ReplayPilot(self.clock, [pause, interruption, dict(mission='questStep', source=clear,
            result=dict(worldVisible=True)), pause, self.arrival(2, inv)], source=clear)
        report = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual((report['status'],report['fieldRotations']), ('arrived',0))
        self.assertEqual([r['waypoints'] for r in pilot.calls if r['mission'] == 'navigation'],
                         [self.points,self.points[1:]])

    def test_field_encounter_rejects_ambiguous_scan_or_failed_rotation(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        now = self.clock.milliseconds()
        enemy = controller_scene(objective='', enemies=True)
        enemy['timestamp'] = now
        record_ground_scan(enemy)
        for key, value in [('candidateCount',2), ('capturedAt',now-1), ('state','clear')]:
            sample = copy.deepcopy(enemy)
            sample['hud']['enemyBarObservation'][key] = value
            phase, _ = route_tool.route_phase(sample, '693306810', [self.route['objective']],
                allow_dialogue=False, journal_resume=False, now_ms=now, allow_field_combat=True)
            self.assertEqual(phase, 'wait')
        inv = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            dict(mission='questStep', status='stopped', source=inv, result=dict(nativeAttempted=False,
                nativeReturned=False, pauseVerified=True))], source=enemy)
        report = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual((report['status'],report['fieldRotations']), ('stopped',0))
        self.assertEqual(pilot.calls[-1]['step'], 'actTwoNativeCombat')

    def test_exploration_threat_low_health_and_oversized_route_refuse(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        for index, mutation in enumerate([
            lambda x: x['hud'].update(enemyBars=[{}]),
            lambda x: x['hud']['health'].update(current=849),
            lambda x: x['hud'].update(objectives=['Defeat all opponents 1/3'])]):
            self.progress = Path(self.temp.name) / ('explore-' + str(index) + '.json')
            source = controller_scene(); source['hud']['objectives'] = []; mutation(source)
            pilot = ReplayPilot(self.clock, source=source)
            self.assertEqual(self.run_controller(pilot)['status'], 'waiting')
            self.assertEqual([r['mission'] for r in pilot.calls], ['observe'])
        self.route['waypoints'] = self.points * 2
        pilot = ReplayPilot(self.clock)
        with self.assertRaisesRegex(ValueError, '1..4'):
            self.run_controller(pilot)
        self.assertEqual(pilot.calls, [])

    def test_only_same_capture_measured_clear_allows_exploration(self):
        now = self.clock.milliseconds()
        source = controller_scene()
        source.update(timestamp=now)
        source['hud']['objectives'] = []

        def phase(observation, at=now):
            return route_tool.route_phase(observation, '693306810', [route_tool.EXPLORATION_OBJECTIVE],
                allow_dialogue=False, journal_resume=False, now_ms=at)[0]

        # Older reports seeded enemyBars=[] even when the detector never ran.
        self.assertEqual(phase(source), 'wait')
        record_ground_scan(source)
        self.assertEqual(phase(source), 'navigation')
        self.assertEqual(phase(source, now + 1001), 'wait')
        for fields in ({'state': 'ambiguous'}, {'state': 'unavailable'}, {'state': 'overloaded'},
                       {'candidateCount': 1}, {'acceptedCount': 1}, {'candidateCount': False},
                       {'session': 'different'}, {'frameId': 2}, {'capturedAt': now - 1}):
            with self.subTest(fields=fields):
                changed = copy.deepcopy(source)
                changed['hud']['enemyBarObservation'].update(fields)
                self.assertEqual(phase(changed), 'wait')

    def test_climb_time_reserve_resumes_only_unreached_waypoints(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv, clear = controller_scene('inventory'), controller_scene(objective='')
        stopped = dict(status='stopped', reason='Navigation stopped before movement to reserve incidental-climb recovery time',
                       nextWaypointIndex=2, pauseVerified=True,
                       pauseProof=dict(verified=True, kind='inventory', session='route-session'))
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            dict(mission='navigation', status='failed', source=inv, result=stopped),
            self.arrival(1, inv)], source=clear)
        self.assertEqual(self.run_controller(pilot)['status'], 'arrived')
        self.assertEqual([r['waypoints'] for r in pilot.calls if r['mission'] == 'navigation'],
                         [self.points,self.points[2:]])

    def test_exploration_deadline_uses_exact_inventory_pause_proof(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        source = controller_scene(); source['hud']['objectives'] = []
        inventory = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=inventory,
            result=dict(status='completed', pausedInventory=True)),
            dict(mission='navigation', status='failed', source=inventory, result=dict(status='stopped',
                reason='Navigation deadline reached', nextWaypointIndex=1, pauseVerified=True,
                pauseProof=dict(verified=True, kind='inventory', session='route-session'))),
            self.arrival(2, inventory)], source=source)
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'arrived')
        self.assertEqual([r['mission'] for r in pilot.calls if r['mission'] != 'observe'],
                         ['questStep', 'navigation', 'navigation'])

    def test_unknown_terminal_outcome_keeps_pending_and_never_replays(self):
        pilot = ReplayPilot(self.clock, [dict(mission='navigation', pending=True)])
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'pending')
        self.assertEqual(report['pending'], pilot.calls[-1])
        self.assertEqual(len(pilot.calls), 2)

    def test_foreign_receipt_is_not_a_retired_mission(self):
        item = self.arrival(3)
        item['foreign'] = True
        pilot = ReplayPilot(self.clock, [item])
        self.assertEqual(self.run_controller(pilot)['status'], 'pending')
        self.assertEqual(len(pilot.calls), 2)

    def test_malformed_cursor_does_not_advance_or_submit_again(self):
        item = self.handoff()
        item['result']['navigation']['nextWaypointIndex'] = True
        pilot = ReplayPilot(self.clock, [item])
        report = self.run_controller(pilot)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('stopped', 0))
        self.assertEqual(len(pilot.calls), 2)

    def test_account_health_modal_and_objective_refusals_are_passive(self):
        variants = []
        wrong = controller_scene(); wrong['ocr'][0]['text'] = 'UID: 111111111'; variants.append(wrong)
        low = controller_scene(); low['hud']['health']['current'] = 599; variants.append(low)
        variants.extend([controller_scene('modal'), controller_scene(objective='Unreviewed objective')])
        bad = controller_scene(); bad['ocr'].append(None); variants.append(bad)
        for index, source in enumerate(variants):
            with self.subTest(index=index):
                self.progress = Path(self.temp.name) / (str(index) + '.json')
                pilot = ReplayPilot(self.clock, source=source)
                self.assertEqual(self.run_controller(pilot)['status'], 'waiting')
                self.assertEqual([x['mission'] for x in pilot.calls], ['observe'])

    def test_completed_phase_with_unchanged_enemy_is_not_retried(self):
        pilot = ReplayPilot(self.clock, [dict(mission='combat', source=controller_scene(enemies=True),
            result=dict(status='completed', outcome='objective_completed'))], source=controller_scene(enemies=True))
        self.assertEqual(self.run_controller(pilot)['status'], 'waiting')
        self.assertEqual(len([x for x in pilot.calls if x['mission'] == 'combat']), 1)

    def test_unapproved_objective_after_handoff_does_not_continue(self):
        pilot = ReplayPilot(self.clock, [self.handoff(controller_scene(objective='Go to Liyue'))])
        report = self.run_controller(pilot)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('waiting', 1))
        self.assertEqual(len([x for x in pilot.calls if x['mission'] == 'navigation']), 1)

    def test_original_deadline_is_not_reset_for_dialogue(self):
        item = self.handoff(controller_scene('dialogue')); item['seconds'] = 30
        pilot = ReplayPilot(self.clock, [item])
        report = self.run_controller(pilot, allow_dialogue=True)
        self.assertEqual(report['status'], 'stopped')
        self.assertIn('original deadline', report['reason'])
        self.assertFalse(any(x['mission'] == 'dialogue' for x in pilot.calls))

    def test_stop_before_first_request_has_no_mission(self):
        pilot = ReplayPilot(self.clock); pilot.stop = True
        self.assertEqual(self.run_controller(pilot)['status'], 'stopped')
        self.assertEqual(pilot.calls, [])

    def test_existing_progress_is_never_restarted(self):
        self.progress.write_text('{"pending":"original"}', encoding='utf-8')
        pilot = ReplayPilot(self.clock)
        with self.assertRaises(FileExistsError):
            self.run_controller(pilot)
        self.assertEqual(pilot.calls, [])

    def test_freshness_rejects_old_future_and_foreign_sources(self):
        source = controller_scene(); source['timestamp'] = self.clock.milliseconds()
        for patch in ({'timestamp': source['timestamp'] - 1001}, {'timestamp': source['timestamp'] + 1},
                      {'session': 'foreign-session'}, {'frameId': True}):
            with self.subTest(patch=patch), self.assertRaises(route_tool.RouteError):
                route_tool.require_fresh_source(dict(source, **patch), 'route-session', self.clock.milliseconds())

    def test_real_cli_help_and_controller_entrypoint(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--controller', result.stdout)
        self.assertIn('--continue-objective', result.stdout)
        route = Path(self.temp.name) / 'route.json'; route.write_text(json.dumps(self.route), encoding='utf-8')
        pilot = ReplayPilot(self.clock, [self.arrival(3)])
        pilot.close = mock.Mock()
        args = [str(SCRIPT), str(route), '--controller', '--session', pilot.session,
                '--app-dir', str(Path(self.temp.name) / 'app'), '--process-id', '42',
                '--expected-windows-session-id', '3', '--expected-uid', '693306810', '--progress', str(self.progress)]
        actual = route_tool.run_controller
        def run(*args, **kwargs):
            return actual(*args, **kwargs, monotonic=self.clock.monotonic, clock_ms=self.clock.milliseconds, emit=lambda _: None)
        with mock.patch.object(sys, 'argv', args), mock.patch.object(route_tool, 'GuardedPilot', return_value=pilot), \
                mock.patch.object(route_tool, 'run_controller', side_effect=run), mock.patch('builtins.print'):
            route_tool.main()
        pilot.close.assert_called_once()
        self.assertEqual(read_json(self.progress)['status'], 'arrived')


class GuardedPilotProtocolTests(unittest.TestCase):
    """Exercise real file publication/receipt helpers with only OS/native calls replaced."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Path(self.temp.name) / 'app'
        self.root = self.app / 'User/JsScript/ActOnePilot'; self.root.mkdir(parents=True)
        self.clock = ControllerClock(); self.stop = Path(self.temp.name) / 'STOP'
        self.source = controller_scene(); self.source['timestamp'] = self.clock.milliseconds()
        self.writes = []; self.pending_mode = False; self.foreign_on_stop = False
        self.save_frame(self.source)
        self.write_heartbeat('idle', 1)
        with mock.patch.object(route_tool.GuardedPilot, '_owner', return_value={}):
            self.pilot = route_tool.GuardedPilot(self.app, 'route-session', 42, 3, [self.stop])
        self.pilot.nonce = 'a' * 32
        self.command = self.pilot.command
        self.command.query_verified_service_status = mock.Mock(side_effect=self.owner)
        require = self.command.require_live_controller
        self.command.require_live_controller = lambda *args, **kwargs: require(*args, **kwargs,
            now_ms=self.clock.milliseconds(), process_verifier=lambda *_: None,
            service_status_query=self.command.query_verified_service_status)
        self.command.maintain_receipts_for_controller = mock.Mock(return_value={'status': 'unchanged'})
        actual_atomic = self.command.atomic
        def publish(path, value, **kwargs):
            actual_atomic(path, value, **kwargs)
            self.writes.append((path.name, copy.deepcopy(value)))
            if path.name == 'request.json':
                if self.pending_mode:
                    self.write_heartbeat('running', self.source['frameId'], value['id'])
                else:
                    self.terminal(value)
            elif path.name == 'stop.json':
                self.terminal(read_json(self.root / 'request.json'), status='stopped')
        self.command.atomic = publish
        self.fake_time = types.SimpleNamespace(time=lambda: self.clock.milliseconds() / 1000,
            monotonic=self.clock.monotonic, sleep=self.sleep)
        self.route_time = mock.patch.object(route_tool, 'time', self.fake_time); self.route_time.start()
        self.command.time = self.fake_time

    def tearDown(self):
        self.route_time.stop()
        self.temp.cleanup()

    def save_frame(self, source):
        path = self.root / 'observations' / source['session'] / ('frame-' + str(source['frameId']).zfill(4) + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(source), encoding='utf-8')
        (self.root / 'observation.json').write_text(json.dumps(source), encoding='utf-8')
        self.source = source

    def write_heartbeat(self, state, frame, active=None):
        value = dict(version=1, processId=42, windowsSessionId=3, remoteDesktop=True,
            heartbeatAt=self.clock.milliseconds(), state=state, session='route-session',
            frameId=frame, activeRequestId=active)
        (self.root / 'controller-status.json').write_text(json.dumps(value), encoding='utf-8')

    def owner(self, *_):
        heartbeat = read_json(self.root / 'controller-status.json')
        return dict(processId=42, windowsSessionId=3, instanceType='ChildSession',
            remoteDesktop=True, serviceOwnsPilot=True, scriptSession='route-session',
            scriptState=heartbeat['state'], pilotState=heartbeat['state'], heartbeatFresh=True,
            heartbeatAtUnixMs=self.clock.milliseconds(), frameId=heartbeat['frameId'],
            activeRequestId=heartbeat['activeRequestId'], instanceNonce='a' * 32, appDirectory=str(self.app))

    def terminal(self, request, status='completed'):
        source = copy.deepcopy(self.source)
        source.update(frameId=source['frameId'] + 1, timestamp=self.clock.milliseconds())
        self.save_frame(source); self.write_heartbeat('idle', source['frameId'])
        receipt = dict(id=request['id'], session=request['session'], mission=request['mission'],
            status=status, frameId=source['frameId'], details=dict(result=None, inputEvents=[]))
        path = self.command.request_receipt_path(self.root, request['session'], request['id'])
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(receipt), encoding='utf-8')

    def sleep(self, seconds):
        self.clock.advance(seconds)
        if self.pending_mode and not self.stop.exists():
            self.stop.write_text('stop', encoding='utf-8')
            if self.foreign_on_stop:
                request = read_json(self.root / 'request.json'); request['id'] = 'mission-' + 'f' * 32
                (self.root / 'request.json').write_text(json.dumps(request), encoding='utf-8')

    def test_real_atomic_terminal_and_quiescence_retire_before_next_request(self):
        saved = []
        started = self.clock.monotonic()
        outcome = self.pilot.execute('observe', self.source, {}, started + 5, saved.append)
        self.assertGreaterEqual(self.clock.monotonic() - started, 0.05)
        self.assertLess(self.clock.monotonic() - started, 0.4)
        self.assertEqual(outcome['receipt']['status'], 'completed')
        self.assertIsNone(self.pilot.pending)
        self.assertEqual(saved, [outcome['request']])
        self.pilot.close(); self.assertFalse(self.pilot.lock.exists())

    def completed_exploration(self):
        """Retain a native-shaped arrived route with field, B, pause and terminal frames."""
        native = SCRIPT.parents[2] / 'BetterGenshinImpact/User/JsScript/ActOnePilot'
        for name in ('world-inventory.js', 'navigation-safety.js'):
            (self.root / name).write_bytes((native / name).read_bytes())
        now = self.clock.milliseconds()
        field = controller_scene(objective='')
        field.update(frameId=2, timestamp=now - 400)
        record_ground_scan(field)
        self.save_frame(field)
        pause = controller_scene('inventory'); pause.update(frameId=3, timestamp=now - 150)
        self.save_frame(pause)
        terminal = copy.deepcopy(pause); terminal.update(frameId=4, timestamp=now - 50)
        self.save_frame(terminal); self.write_heartbeat('idle', 4)
        request = dict(id='mission-' + 'e' * 32, session=self.pilot.session, expectedFrameId=1,
            createdAt=now - 1000, mission='navigation', objective=route_tool.EXPLORATION_OBJECTIVE,
            waypoints=[dict(map='Teyvat', x=-1178, y=2208)], deadlineMs=10000, requireMeasuredGround=True)
        proof = dict(verified=True, kind='inventory', session=self.pilot.session, sourceFrameId=2,
            pauseFrameId=3, timestamp=pause['timestamp'], evidence=[pause['ocr'][1]])
        key = dict(type='pauseProtectionKey', key='VK_B', durationMs=60, frameId=2,
            startedAt=now - 350, finishedAt=now - 290)
        receipt = dict(id=request['id'], session=self.pilot.session, mission='navigation',
            status='completed', frameId=4, timestamp=now,
            details=dict(result=dict(status='arrived', nextWaypointIndex=1, pauseVerified=True, pauseProof=proof),
                inputEvents=[key, dict(key, type='key'),
                    dict(type='pauseProtectionVerified', kind='inventory', frameId=3, startedAt=now - 100)]))
        path = self.command.request_receipt_path(self.root, self.pilot.session, request['id'])
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(receipt), encoding='utf-8')
        (self.root / 'request.json').write_text(json.dumps(request), encoding='utf-8')
        progress = dict(version=1, kind='supervised-route-controller-v1', status='arrived', pending=None,
            session=self.pilot.session, expectedUid='693306810', nextWaypointIndex=1,
            route=dict(objective=request['objective'], waypoints=request['waypoints']),
            records=[dict(request=request, receipt=receipt, observation=terminal)])
        output = Path(self.temp.name) / 'prior.json'; output.write_text(json.dumps(progress), encoding='utf-8')
        return output, progress, field, pause, terminal

    def test_completed_progress_joins_original_pause_and_unchanged_evidence(self):
        path, _, field, _, _ = self.completed_exploration()
        witness = self.pilot.exploration_continuation(path, '693306810', self.clock.milliseconds())
        self.assertEqual((witness['sourceFrameId'], witness['pauseFrameId'], witness['terminalFrameId']), (2, 3, 4))
        self.assertTrue(self.pilot.continuation_unchanged(witness))
        field['hud']['health']['current'] = 899
        self.command.observation_path(self.root, self.pilot.session, 2).write_text(json.dumps(field), encoding='utf-8')
        self.assertFalse(self.pilot.continuation_unchanged(witness))

    def test_progress_mutations_and_foreign_current_state_cannot_supply_reuse(self):
        mutations = [
            lambda p: p.update(status='stopped'),
            lambda p: p.update(pending=p['records'][0]['request']),
            lambda p: p.update(session='foreign-session'),
            lambda p: p.update(expectedUid='111111111'),
            lambda p: p.update(nextWaypointIndex=0),
            lambda p: p['records'][0]['request'].update(requireMeasuredGround=False),
            lambda p: p['records'][0]['receipt']['details']['result'].update(pauseVerified=False),
            lambda p: p['records'][0]['receipt']['details']['result']['pauseProof'].update(sourceFrameId=3),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                path, progress, *_ = self.completed_exploration()
                mutation(progress); path.write_text(json.dumps(progress), encoding='utf-8')
                self.assertIsNone(self.pilot.exploration_continuation(path, '693306810', self.clock.milliseconds()))
        for target in ('slot', 'current', 'receipt', 'source'):
            with self.subTest(target=target):
                path, progress, field, _, terminal = self.completed_exploration()
                if target == 'slot':
                    changed = dict(progress['records'][0]['request'], id='mission-' + 'f' * 32)
                    (self.root / 'request.json').write_text(json.dumps(changed), encoding='utf-8')
                elif target == 'current':
                    terminal['frameId'] = 5; self.save_frame(terminal)
                elif target == 'receipt':
                    receipt = progress['records'][0]['receipt']; receipt['status'] = 'failed'
                    self.command.request_receipt_path(self.root, self.pilot.session, receipt['id']).write_text(json.dumps(receipt), encoding='utf-8')
                else:
                    field['hud']['enemyBarObservation']['state'] = 'unavailable'
                    self.command.observation_path(self.root, self.pilot.session, 2).write_text(json.dumps(field), encoding='utf-8')
                self.assertIsNone(self.pilot.exploration_continuation(path, '693306810', self.clock.milliseconds()))

    def test_historical_source_requires_real_clear_healthy_capture_at_original_pause(self):
        mutations = [
            lambda f: f['hud']['health'].update(current=849),
            lambda f: f.update(mapPositionInherited=True),
            lambda f: f['ocr'].append(dict(text='UID: 111111111', x=1720, y=1050)),
            lambda f: f['hud']['captureStamp'].update(capturedAt=f['timestamp'] - 1001),
            lambda f: f['hud']['enemyBarObservation'].update(candidateCount=1),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                path, _, field, *_ = self.completed_exploration(); mutation(field)
                self.command.observation_path(self.root, self.pilot.session, 2).write_text(json.dumps(field), encoding='utf-8')
                self.assertIsNone(self.pilot.exploration_continuation(path, '693306810', self.clock.milliseconds()))
        path, *_ = self.completed_exploration()
        self.assertIsNone(self.pilot.exploration_continuation(path, '693306810', self.clock.milliseconds() + 600001))

    def test_opt_in_performs_only_passive_observe_then_guarded_navigation(self):
        path, *_ = self.completed_exploration()
        original = self.terminal

        def terminal(request, status='completed'):
            """Use real publication/retirement while substituting only native execution."""
            original(request, status)
            if request['mission'] == 'navigation':
                receipt_path = self.command.request_receipt_path(self.root, self.pilot.session, request['id'])
                receipt = read_json(receipt_path)
                receipt['details']['result'] = dict(status='arrived', nextWaypointIndex=1)
                receipt_path.write_text(json.dumps(receipt), encoding='utf-8')

        self.terminal = terminal
        route = dict(objective=route_tool.EXPLORATION_OBJECTIVE,
            waypoints=[dict(map='Teyvat', x=-1170, y=2208)])
        report = route_tool.run_controller(self.pilot, route, Path(self.temp.name) / 'next.json', '693306810',
            continue_from_progress=path, deadline_ms=10000, monotonic=self.clock.monotonic,
            clock_ms=self.clock.milliseconds, emit=lambda _: None)
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        self.assertEqual([r['request']['mission'] for r in report['records']], ['observe', 'navigation'])
        self.assertEqual(report['continuedFromProgress']['sourceFrameId'], 2)
        self.assertIs(report['records'][-1]['request']['requireMeasuredGround'], True)

    def test_passive_refresh_reports_changed_predecessor_without_granting_shortcut(self):
        path, *_ = self.completed_exploration()
        witness = self.pilot.exploration_continuation(path, '693306810', self.clock.milliseconds())
        outcome = self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + 5,
            lambda _: None, expected_previous=witness['requestBytes'] + b' ')
        self.assertIs(outcome['predecessorMatched'], False)

    def test_owner_nonce_changes_before_rename_without_request_publication(self):
        first = self.owner(); changed = dict(first, instanceNonce='b' * 32)
        self.command.query_verified_service_status.side_effect = [first, changed]
        with self.assertRaisesRegex(route_tool.RouteError, 'lifetime changed'):
            self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + 5, lambda _: None)
        self.assertFalse((self.root / 'request.json').exists())
        self.assertEqual(self.writes, [])

    def test_stop_cancels_only_owned_pending_request_then_waits_for_retirement(self):
        self.pending_mode = True
        outcome = self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + 5, lambda _: None)
        self.assertTrue(outcome['cancelled'])
        self.assertEqual(outcome['receipt']['status'], 'stopped')
        self.assertEqual([name for name, _ in self.writes], ['request.json', 'stop.json'])
        self.assertIsNone(self.pilot.pending)

    def test_foreign_request_is_never_cancelled_or_overwritten(self):
        self.pending_mode = self.foreign_on_stop = True
        with self.assertRaisesRegex(route_tool.RouteError, 'foreign request'):
            self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + 5, lambda _: None)
        self.assertEqual([name for name, _ in self.writes], ['request.json'])
        self.assertFalse((self.root / 'stop.json').exists())
        self.pilot.close(); self.assertTrue(self.pilot.lock.exists())

    def test_global_stop_refuses_before_any_protocol_write(self):
        self.stop.write_text('stop', encoding='utf-8')
        with self.assertRaisesRegex(route_tool.RouteError, 'Operator STOP'):
            self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + 5, lambda _: None)
        self.assertEqual(self.writes, [])

    def test_real_installed_exploration_and_inventory_predicates(self):
        native = SCRIPT.parents[2] / 'BetterGenshinImpact/User/JsScript/ActOnePilot'
        for name in ('world-inventory.js', 'navigation-safety.js'):
            (self.root / name).write_bytes((native / name).read_bytes())
        source = controller_scene('inventory'); source.update(frameId=2, timestamp=self.clock.milliseconds())
        self.save_frame(source)
        self.assertTrue(self.pilot.inventory_ready(source))
        changed = copy.deepcopy(source); changed['ocr'].append(dict(text='Confirm', x=1100, y=900))
        self.assertFalse(self.pilot.inventory_ready(changed))
        request = dict(id='mission-' + 'c' * 32, session='route-session', expectedFrameId=2,
            createdAt=self.clock.milliseconds(), objective=route_tool.EXPLORATION_OBJECTIVE,
            waypoints=[dict(map='Teyvat', x=-1170, y=2208)])
        self.pilot._prepare_exploration(request)
        safety = read_json(self.root / 'navigation-safety-request.json')
        self.assertEqual((safety['requestId'], safety['witnessFrameId'], safety['frameId']), (request['id'], 1, 2))
        actual = subprocess.run(['node', '-e',
            'const g=require(process.argv[1]);process.exit(g.plan(...JSON.parse(process.argv[2]))?0:2)',
            str(self.root / 'navigation-safety.js'), json.dumps([safety, request,
                read_json(self.command.observation_path(self.root, 'route-session', 1)), self.clock.milliseconds()])],
            capture_output=True, text=True)
        self.assertEqual(actual.returncode, 0, actual.stderr)

        self.write_heartbeat('idle', source['frameId'])
        fields = dict(objective=request['objective'], waypoints=request['waypoints'], deadlineMs=10000,
                      requireMeasuredGround=True)
        deadline = self.clock.monotonic() + 5
        with self.assertRaisesRegex(route_tool.RouteError, 'measured ground'):
            self.pilot.execute('navigation', source, dict(fields, requireMeasuredGround=False), deadline, lambda _: None)
        self.pilot.execute('navigation', source, fields, deadline, lambda _: None)
        self.assertIs(read_json(self.root / 'request.json')['requireMeasuredGround'], True)

    def test_actual_engine_retains_native_navigation_handoff_cursor(self):
        engine = SCRIPT.parents[2] / 'BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js'
        script = """
const engine=require(process.argv[1]), source=JSON.parse(process.argv[2]);let now=1700000100000,writes=[];
const api={now:()=>now,sleep:async ms=>{now+=ms},beginMission:()=>{},events:()=>[],
 checkStop:()=>{},requireInputReady:()=>{},release:()=>{},
 observe:async()=>({...source,timestamp:now}),write:(p,v)=>writes.push([p,JSON.parse(v)])};
(async()=>{const runner=engine.create(api,{session:'route-session',enableInput:true});await runner.observe();
 await runner.process({session:'route-session',id:'mission-'+ 'd'.repeat(32),createdAt:now,
 expectedFrameId:1,mission:'navigation',objective:'Defeat the nearby hilichurls',deadlineMs:1000,
 waypoints:[{map:'Teyvat',x:-1178,y:2208},{map:'Teyvat',x:-1170,y:2208}]},()=>({
 runNavigation:async()=>({status:'stopped',reason:'Enemy acquired',nextWaypointIndex:1}),
 run:async()=>({status:'completed',outcome:'objective_completed'})}));
 console.log(JSON.stringify(writes.filter(x=>x[0]==='receipt.json').at(-1)[1]));})().catch(e=>{console.error(e);process.exit(1)});
"""
        completed = subprocess.run(['node', '-e', script, str(engine), json.dumps(controller_scene())],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt['status'], 'completed')
        self.assertTrue(receipt['details']['result']['localHandoff'])
        self.assertEqual(receipt['details']['result']['navigation']['nextWaypointIndex'], 1)


def read_json(path):
    """Read a retained test result without substituting its object identity."""
    return json.loads(path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

