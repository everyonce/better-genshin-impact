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

    def quest_navigation_from_inventory(self, objective, points):
        # Read the same installed mission as the real pilot, without a Windows input endpoint.
        client = types.SimpleNamespace(command=command_tool, root=SCRIPT.parents[2] /
            'BetterGenshinImpact/User/JsScript/ActOnePilot')
        return route_tool.GuardedPilot.quest_navigation_from_inventory(client, objective, points)

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
        frame = self.source['frameId'] + item.get('frames', 1)
        self.source = copy.deepcopy(item.get('source', self.source))
        self.source.update(session=self.session, frameId=frame, timestamp=self.clock.milliseconds())
        if (mission == 'observe' or fields.get('step') == 'namedWaypointRelook') and self.source['hud'].get('groundControls'):
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

    def test_city_stair_bootstrap_releases_once_then_uses_surveyed_landing(self):
        field = controller_scene(objective='')
        field['map'].update(x=-836.08, y=2198.67)
        field['hud']['health'] = dict(current=3649, max=4015)
        climb = copy.deepcopy(field)
        climb['hud'].update(climbing=True, groundControls=False)
        climb['ocr'].extend([dict(text='X', x=1594, y=1022), dict(text='Space', x=1680, y=1024)])
        self.route = dict(objective=route_tool.EXPLORATION_OBJECTIVE,
                          waypoints=[dict(map='Teyvat', x=-836, y=2204.5)])
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', frames=3, source=field,
            result=dict(status='completed', step='cityStairRelease', sourceFrameId=2, groundedFrames=[3, 4], frameId=4)),
            dict(mission='questStep', source=controller_scene('inventory'), result=dict(pausedInventory=True)),
            self.arrival(1)], source=climb)
        report = self.run_controller(pilot)
        self.assertEqual(report['cityStairRelease']['groundedFrames'], [3, 4])
        self.assertEqual([r.get('step',r['mission']) for r in pilot.calls if r['mission'] != 'observe'],
                         ['cityStairRelease', 'worldInventory', 'navigation'])
        self.assertEqual(pilot.calls[1]['step'], 'cityStairRelease')

    def test_city_stair_requires_local_pose_original_uid_and_both_controls(self):
        climb = controller_scene(objective='')
        climb['map'].update(x=-836.08, y=2198.67)
        climb['hud'].update(health=dict(current=3649, max=4015), climbing=True, groundControls=False)
        climb['ocr'].extend([dict(text='X', x=1594, y=1022), dict(text='Space', x=1680, y=1024)])
        ready = lambda o: route_tool.city_stair_climb(o, 'route-session', '693306810')
        self.assertTrue(ready(climb))
        for patch in [dict(map=dict(climb['map'], y=2204)), dict(ocr=climb['ocr'][:-1]),
                      dict(ocr=climb['ocr'][1:]), dict(hud=dict(climb['hud'], enemyBars=[{}])),
                      dict(hud=dict(climb['hud'], groundControls=True))]:
            self.assertFalse(ready(dict(climb, **patch)))

    def test_named_npc_after_arrival_joins_both_frames_then_parks(self):
        self.route['talkTo'] = 'Amber'
        inventory, field = controller_scene('inventory'), controller_scene()
        pilot = ReplayPilot(self.clock, [
            self.arrival(3, inventory),
            dict(mission='questStep', source=field, result=dict(status='completed')),
            dict(mission='dialogue', source=field, frames=3, result=dict(status='completed', reason='world_returned',
                talkTo='Amber', interactionFrameId=7, greetingFrameId=8, worldFrameId=9)),
            dict(mission='questStep', source=inventory, result=dict(pausedInventory=True))])
        report = self.run_controller(pilot)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('arrived', 3))
        self.assertEqual(report['conversation']['npc'], 'Amber')
        self.assertEqual([q.get('step') or q['mission'] for q in pilot.calls if q['mission'] != 'observe'],
            ['navigation', 'worldInventoryClose', 'dialogue', 'worldInventory'])
        navigation = next(q for q in pilot.calls if q['mission'] == 'navigation')
        self.assertEqual((navigation['talkTo'], navigation['expectedUid']), ('Amber', '693306810'))
        conversation = next(q for q in pilot.calls if q['mission'] == 'dialogue')
        self.assertEqual((conversation['talkTo'], conversation['expectedUid']), ('Amber', '693306810'))
        self.assertLessEqual(conversation['deadlineMs'], 60000)

    def test_quest_guild_navigation_visits_inventory_after_measuring_the_actual_objective(self):
        objective = "Go to the Adventurers' Guild and listen to their report"
        self.route.update(objective=objective, talkTo='Cyrus')
        inventory = controller_scene('inventory')
        field = controller_scene(objective=objective)
        pilot = ReplayPilot(self.clock, [
            dict(mission='questStep', source=field, result=dict(status='completed')),
            dict(mission='questStep', source=inventory, result=dict(pausedInventory=True)),
            self.arrival(3, inventory),
            dict(mission='questStep', source=field, result=dict(status='completed')),
            dict(mission='dialogue', source=field, frames=3, result=dict(status='completed',
                reason='world_returned', talkTo='Cyrus', greetingFrameId=12, worldFrameId=13)),
            dict(mission='questStep', source=inventory, result=dict(pausedInventory=True))], source=inventory)
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        actions = [q.get('step') or q['mission'] for q in pilot.calls if q['mission'] != 'observe']
        self.assertEqual(actions, ['worldInventoryClose', 'worldInventory', 'navigation',
                                  'worldInventoryClose', 'dialogue', 'worldInventory'])
        navigation = next(q for q in pilot.calls if q['mission'] == 'navigation')
        self.assertEqual(navigation['objective'], objective)

    def test_open_named_menu_discovers_farewell_closes_without_travel_and_checks_the_return_pose(self):
        self.route.update(objective=route_tool.EXPLORATION_OBJECTIVE, talkTo='Katheryne', resumeNamedDialogue=True,
            waypoints=[dict(map='Teyvat',x=-913.51,y=2232.67)],startNear=dict(map='Teyvat',x=-913.51,y=2232.67,radius=5))
        fixture = Path(__file__).with_name('katheryne-keyboard-menu-35.fixture.json')
        menu = json.loads(fixture.read_bytes())
        clear=controller_scene(objective='')
        clear['map'].update(x=-913.332,y=2233.676)
        inv=controller_scene('inventory')
        for i,offset in enumerate((0,20)):
            self.progress=Path(self.temp.name)/f'menu-{i}.json'
            world=copy.deepcopy(clear);world['map']['x']+=offset
            pilot=ReplayPilot(self.clock,[dict(mission='dialogue',source=world,frames=6,result=dict(status='completed',
                reason='world_returned',talkTo='Katheryne',interactionFrameId=None,greetingFrameId=4,worldFrameId=8,
                farewell=dict(label='Goodbye.',frameId=5))),dict(mission='questStep',source=inv,result=dict(pausedInventory=True))],
                source=dict(menu,frameId=1))
            report=self.run_controller(pilot)
            self.assertEqual([x.get('step',x['mission']) for x in pilot.calls if x['mission']!='observe'],['dialogue','worldInventory'])
            self.assertTrue(next(r for r in pilot.calls if r['mission']=='dialogue')['resumeMenuOnly'])
            self.assertEqual(report['status']=='arrived',offset==0)
            self.assertEqual(report['nextWaypointIndex'],1 if offset==0 else 0)
        self.progress=Path(self.temp.name)/'closed.json'
        pilot=ReplayPilot(self.clock,[],source=clear)
        result=self.run_controller(pilot)
        self.assertNotEqual(result['status'],'arrived')
        self.assertEqual([r['mission'] for r in pilot.calls],['observe','observe'])

    def test_named_npc_missing_prompt_keeps_arrival_cursor_without_a_second_interaction(self):
        self.route['talkTo'] = 'Amber'
        pilot = ReplayPilot(self.clock, [
            self.arrival(3), dict(mission='dialogue', status='failed', source=controller_scene(),
                                 result=dict(status='stopped', reason='Named NPC is not selected on clear ground')),
            dict(mission='questStep', source=controller_scene('inventory'), result=dict(pausedInventory=True))])
        report = self.run_controller(pilot, allow_dialogue=True)
        self.assertEqual((report['status'], report['nextWaypointIndex']), ('stopped', 3))
        self.assertNotIn('conversation', report)
        self.assertEqual([q['mission'] for q in pilot.calls].count('dialogue'), 1)

    def test_legacy_route_cannot_ignore_a_named_npc_and_bad_names_are_rejected(self):
        self.route['talkTo'] = 'Amber'
        pilot = ReplayPilot(self.clock)
        with self.assertRaisesRegex(route_tool.RouteError, 'controller mode'):
            route_tool.run_route(Path(self.temp.name), self.route, pilot.session)
        self.assertEqual(pilot.calls, [])
        for value in ('', ' Amber', 'Amber\n', 7):
            with self.assertRaises(route_tool.RouteError):
                route_tool.validate_route(dict(self.route, talkTo=value))

    def test_generic_world_return_without_a_later_named_greeting_cannot_finish_arrival(self):
        self.route['talkTo'] = 'Amber'
        pilot = ReplayPilot(self.clock, [
            self.arrival(3), dict(mission='dialogue', source=controller_scene(), result=dict(
                status='completed', reason='world_returned', talkTo='Amber', greetingFrameId=2, worldFrameId=4)),
            dict(mission='questStep', source=controller_scene('inventory'), result=dict(pausedInventory=True))])
        report = self.run_controller(pilot, allow_dialogue=True)
        self.assertEqual(report['status'], 'stopped')
        self.assertNotIn('conversation', report)

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

    def test_named_deadline_suffix_keeps_the_same_original_final_point_and_contact(self):
        self.route['talkTo'] = 'Katheryne'
        pilot = ReplayPilot(self.clock, [dict(mission='navigation',status='failed',seconds=10,
            result=dict(status='stopped',reason='Navigation deadline reached',nextWaypointIndex=1)),
            dict(mission='navigation',status='failed',result=dict(status='stopped',reason='Map coordinates stalled',nextWaypointIndex=0))])
        self.run_controller(pilot)
        plans = [r for r in pilot.calls if r['mission'] == 'navigation']
        self.assertEqual([r['waypoints'] for r in plans], [self.points, self.points[1:]])
        self.assertEqual([(p['talkTo'],p['expectedUid']) for p in plans], [('Katheryne','693306810')]*2)

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

    def reacquisition_pilot(self, scans, script=()):
        """Replay fresh capture identities with the actual unanchored-fragment contract."""
        pilot = ReplayPilot(self.clock, script, source=controller_scene(objective=''))
        original = pilot.execute
        pilot.observation_deadlines = []
        previous_capture = None

        def execute(mission, source, fields, deadline, save_pending, **kwargs):
            """Only passive sensor outcomes are substituted; no hidden input is produced."""
            nonlocal previous_capture
            outcome = original(mission, source, fields, deadline, save_pending)
            if mission == 'observe' and pilot.source['hud'].get('groundControls'):
                pilot.observation_deadlines.append(deadline)
                kind = scans.pop(0) if scans else 'clear'
                scan = pilot.source['hud']['enemyBarObservation']
                if kind != 'clear':
                    scan.update(state='ambiguous', reason='unanchored_bar_shaped_components',
                                candidateCount=1, acceptedCount=0)
                if kind == 'threat':
                    pilot.source['hud']['enemyBars'] = [dict(x=950, y=300, width=100, height=8)]
                    scan.update(state='threat', acceptedCount=1, reason='outdoor_bar_candidates')
                elif kind in ('unavailable', 'overloaded'):
                    scan.update(state=kind, reason='detector_overloaded' if kind == 'overloaded' else 'detector_unavailable')
                elif kind == 'low':
                    pilot.source['hud']['health']['current'] = 800
                elif kind == 'foreign':
                    pilot.source['ocr'][0]['text'] = 'UID: 111111111'
                elif kind == 'duplicate':
                    scan['capturedAt'] = previous_capture
                    pilot.source['hud']['captureStamp']['capturedAt'] = previous_capture
                elif kind == 'late':
                    self.clock.advance(2)
                elif kind == 'stale':
                    scan['capturedAt'] -= 1001
                    pilot.source['hud']['captureStamp']['capturedAt'] = scan['capturedAt']
                previous_capture = scan['capturedAt']
                outcome['observation'] = copy.deepcopy(pilot.source)
            return outcome

        pilot.execute = execute
        return pilot

    def test_named_relook_needs_an_independent_clear_capture_before_travel(self):
        target = dict(map='Teyvat', x=-913.51, y=2232.67)
        self.route = dict(objective=route_tool.EXPLORATION_OBJECTIVE,talkTo='Katheryne',waypoints=[target])
        for follow, should_walk in [('clear',True), ('ambiguous',False), ('threat',False)]:
            with self.subTest(follow=follow):
                self.progress = Path(self.temp.name) / (follow + '.json')
                field = controller_scene(objective='')
                field['map'].update(x=-908.1582,y=2242.0254,cameraAngle=59)
                result=dict(status='completed',step='namedWaypointRelook',talkTo='Katheryne',waypoint=target,turnSent=True,
                            measuredClear=True,sourceFrameId=6,frameId=7)
                script=[dict(mission='questStep',source=field,frames=3,result=result)]
                if should_walk:
                    script.extend([dict(mission='questStep',source=controller_scene('inventory'),result=dict(pausedInventory=True)),
                                   dict(mission='navigation',pending=True)])
                pilot=self.reacquisition_pilot(['ambiguous']*4+[follow],script)
                pilot.source['map'].update(x=-908.1582,y=2242.0254,cameraAngle=27)
                report=self.run_controller(pilot,allow_dialogue=True)
                turns=[q for q in pilot.calls if q.get('step')=='namedWaypointRelook']
                self.assertEqual(len(turns),1)
                self.assertEqual(turns[0]['waypoints'],[target])
                self.assertEqual(turns[0]['talkTo'],'Katheryne')
                self.assertEqual(any(q['mission']=='navigation' for q in pilot.calls),should_walk,
                                 (report.get('reason'), [(q['mission'],q.get('step')) for q in pilot.calls]))
                self.assertEqual('verifiedFrameId' in report['namedWaypointRelook'], should_walk)

    def test_stationary_fragments_then_clear_allows_only_existing_navigation_entry(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv = controller_scene('inventory')
        pilot = self.reacquisition_pilot(['ambiguous', 'ambiguous', 'clear'], [
            dict(mission='questStep', source=inv, result=dict(pausedInventory=True)), self.arrival(3, inv)])
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        self.assertEqual([r.get('step', r['mission']) for r in pilot.calls],
                         ['observe', 'observe', 'observe', 'worldInventory', 'observe', 'navigation'])
        proof = report['groundReacquisition']
        self.assertEqual([r['state'] for r in proof['frames']], ['ambiguous', 'ambiguous', 'clear'])
        self.assertTrue(proof['measuredClear'])
        self.assertLessEqual(proof['elapsedMilliseconds'], 2000)
        self.assertEqual(pilot.observation_deadlines[1], pilot.observation_deadlines[2])

    def test_stationary_observe_reserves_one_second_before_the_next_request(self):
        """A completed slow refresh cannot trigger another capture with under one second left."""
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        for remaining, expected_count in ((.999, 2), (1.0, 3)):
            with self.subTest(remaining=remaining):
                self.progress = Path(self.temp.name) / ('reserve-' + str(remaining) + '.json')
                pilot = self.reacquisition_pilot(['ambiguous'] * 5)
                original = pilot.execute

                def delayed(mission, source, fields, deadline, save_pending, **kwargs):
                    """Model capture work before its new publication, retaining a fresh exact source."""
                    outcome = original(mission, source, fields, deadline, save_pending, **kwargs)
                    if len(pilot.calls) == 2:
                        self.clock.value = deadline - remaining
                        pilot.source['timestamp'] = self.clock.milliseconds()
                        for name in ('captureStamp', 'enemyBarObservation'):
                            pilot.source['hud'][name]['capturedAt'] = pilot.source['timestamp']
                        outcome['observation'] = copy.deepcopy(pilot.source)
                    return outcome

                pilot.execute = delayed
                report = self.run_controller(pilot)
                self.assertEqual(report['status'], 'waiting')
                self.assertEqual([r['mission'] for r in pilot.calls], ['observe'] * expected_count)
                self.assertIsNone(report['pending'])
                self.assertIsNone(pilot.pending)
                self.assertFalse(report['groundReacquisition']['measuredClear'])

    def test_terminal_observe_settlement_does_not_extend_stationary_action_window(self):
        """A retired receipt after the scan deadline remains recorded but cannot grant movement."""
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        pilot = self.reacquisition_pilot(['ambiguous', 'clear'])
        original = pilot.execute

        def after_window(mission, source, fields, deadline, save_pending, **kwargs):
            """Represent read-only settlement finishing after the original scan deadline."""
            outcome = original(mission, source, fields, deadline, save_pending, **kwargs)
            if len(pilot.calls) == 2:
                self.clock.value = deadline + .1
                pilot.source['timestamp'] = self.clock.milliseconds()
                record_ground_scan(pilot.source)
                outcome['observation'] = copy.deepcopy(pilot.source)
            return outcome

        pilot.execute = after_window
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'waiting')
        self.assertIn('expired', report['reason'])
        self.assertEqual([r['mission'] for r in pilot.calls], ['observe', 'observe'])
        self.assertEqual(report['records'][-1]['receipt']['status'], 'completed')
        self.assertIsNone(report['pending'])
        self.assertFalse(report['groundReacquisition']['measuredClear'])

    def test_stationary_reacquisition_stops_at_four_distinct_ambiguous_frames(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        pilot = self.reacquisition_pilot(['ambiguous'] * 5)
        report = self.run_controller(pilot)
        self.assertEqual(report['status'], 'waiting')
        self.assertEqual([r['mission'] for r in pilot.calls], ['observe'] * 4)
        self.assertEqual(len(report['groundReacquisition']['frames']), 4)
        self.assertFalse(report['groundReacquisition']['measuredClear'])

    def test_reacquisition_stops_immediately_on_threat_or_other_ambiguity(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        for kind in ('threat', 'unavailable', 'overloaded', 'low', 'foreign', 'duplicate', 'stale', 'late'):
            with self.subTest(kind=kind):
                self.progress = Path(self.temp.name) / ('scan-' + kind + '.json')
                pilot = self.reacquisition_pilot(['ambiguous', kind, 'clear'])
                report = self.run_controller(pilot, allow_field_combat=kind != 'threat')
                self.assertIn(report['status'], ('waiting', 'stopped'))
                self.assertEqual([r['mission'] for r in pilot.calls], ['observe', 'observe'])
                self.assertFalse(report['groundReacquisition'].get('measuredClear', False))

    def test_reacquired_hostile_prepares_opted_in_combat_instead_of_walking(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv = controller_scene('inventory')
        pilot = self.reacquisition_pilot(['ambiguous', 'threat'], [
            dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            dict(mission='questStep', status='stopped', source=inv, result=dict(nativeAttempted=False))])
        report = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual(report['groundReacquisition']['frames'][-1]['state'], 'threat')
        self.assertFalse(report['groundReacquisition']['measuredClear'])
        self.assertEqual([r.get('step',r['mission']) for r in pilot.calls],
            ['observe','observe','worldInventory','observe','actTwoFieldCombat'])

    def test_non_fragment_initial_failures_never_enter_reacquisition(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        for kind in ('unavailable', 'overloaded', 'low', 'foreign', 'stale'):
            with self.subTest(kind=kind):
                self.progress = Path(self.temp.name) / ('initial-' + kind + '.json')
                pilot = self.reacquisition_pilot([kind, 'clear'])
                report = self.run_controller(pilot)
                self.assertEqual(report['status'], 'waiting')
                self.assertEqual([r['mission'] for r in pilot.calls], ['observe'])
                self.assertNotIn('groundReacquisition', report)

    def test_reacquisition_budget_is_clipped_to_original_outer_deadline(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        start = self.clock.monotonic()
        pilot = self.reacquisition_pilot(['ambiguous'] * 4)
        report = self.run_controller(pilot, deadline_ms=1000)
        self.assertEqual(report['status'], 'waiting')
        self.assertTrue(all(value <= start + 1 for value in pilot.observation_deadlines))

    def test_actual_camp_fragment_geometry_is_ambiguous_not_clear(self):
        # Actual retained mw3mq547/76, mw3mwa08/5 and mw3n18xv/2 observations:
        # these tiny unanchored red components authorize observation only.
        for x, y, width, height, rectangularity in (
                (1375.5, 180.5, 11, 9, .05625), (1374.5, 184, 9, 6, .25),
                (1352, 188, 12, 14, .03146853146853147)):
            source = controller_scene(objective='')
            source['timestamp'] = self.clock.milliseconds(); record_ground_scan(source)
            source['hud']['enemyBarObservation'].update(state='ambiguous',
                reason='unanchored_bar_shaped_components', candidateCount=1, acceptedCount=0)
            source['hud']['enemyBarDiagnostic'] = dict(fieldCandidates=[dict(
                x=x, y=y, width=width, height=height, rectangularity=rectangularity)])
            self.assertTrue(route_tool.unanchored_ground_scan(source, '693306810', self.clock.milliseconds()))
            self.assertFalse(route_tool.ground_scan_is_clear(source, self.clock.milliseconds()))

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
                         ['worldInventory','actTwoFieldCombat','worldInventoryClose','worldInventory','navigation'])
        self.assertFalse(returned['result']['defeatConfirmed'])

    def test_capable_pilot_enters_measured_world_pack_without_inventory_round_trip(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        enemy = controller_scene(objective='', enemies=True)
        inv, clear = controller_scene('inventory'), controller_scene(objective='')
        proof = dict(verified=True, kind='inventory', session='route-session')
        returned = dict(mission='questStep', status='stopped', source=inv, result=dict(
            nativeGroup=False, nativeAttempted=True, nativeReturned=True, beforeFrameId=3,
            afterFrameId=4, pauseVerified=True, pauseProof=proof, defeatConfirmed=False))
        pilot = ReplayPilot(self.clock, [returned, dict(mission='questStep', source=clear,
            result=dict(worldVisible=True)), dict(mission='questStep', source=inv, result=dict(pausedInventory=True)),
            self.arrival(3, inv)], source=enemy)
        pilot.supports_field_combat_world_entry = mock.Mock(return_value=True)
        report = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        active = [r for r in pilot.calls if r['mission'] != 'observe']
        self.assertEqual([r.get('step', r['mission']) for r in active],
                         ['actTwoFieldCombat','worldInventoryClose','worldInventory','navigation'])
        self.assertEqual((active[0]['entryScene'], active[0]['expectedUid']), ('world', '693306810'))
        pilot.supports_field_combat_world_entry.assert_called_once()

    def combat_reward_frames(self):
        # Same sequence as Temple public09: attack, disappearing bar, reappearance, then the parking frame.
        frames = {}
        for frame in range(19, 25):
            o = controller_scene(objective='', enemies=frame in (19, 21))
            o.update(frameId=frame, timestamp=frame * 100)
            record_ground_scan(o)
            frames[frame] = o
        request = dict(mission='questStep', step='actTwoFieldCombat', expectedFrameId=11,
                       id='battle', session='route-session')
        key = dict(type='pauseProtectionKey', key='VK_B', frameId=24, startedAt=2401)
        event = dict(type='actTwoNativeCombat', actionId='battle:rotation:0', frameId=19,
                     startedAt=1901, finishedAt=1990)
        proof = dict(verified=True, kind='inventory', session='route-session', sourceFrameId=24, pauseFrameId=26)
        chunk = dict(nativeReturned=True, actionId=event['actionId'], beforeFrameId=19, afterFrameId=20)
        result = dict(nativeReturned=True, pauseVerified=True, pauseProof=proof, chunks=[chunk])
        receipt = dict(id='battle', status='stopped', session='route-session', frameId=27,
                       details=dict(inputEvents=[event, key], result=result))
        return dict(request=request, receipt=receipt), frames

    def test_late_combat_exp_is_joined_to_attack_and_clear_parking_frame(self):
        record, frames = self.combat_reward_frames()
        frames[23]['ocr'].append(dict(text='Character EXP × 15', x=160, y=465))
        def feedback():
            return route_tool.field_combat_feedback(record, '693306810', frames.__getitem__)
        self.assertEqual(feedback(), dict(requestId='battle', attackFrameId=19, rewardFrameId=23,
            rewardText='Character EXP × 15', minimumDefeated=1, pauseSourceFrameId=24, measuredClear=True))
        # A single reward neither establishes an empty pack nor overrides a missing/stale scan.
        for state in ('threat', 'ambiguous', 'unavailable'):
            frames[24]['hud']['enemyBarObservation']['state'] = state
            self.assertFalse(feedback()['measuredClear'])
        del frames[24]['hud']['enemyBarObservation']
        self.assertFalse(feedback()['measuredClear'])

    def test_combat_defeat_excludes_disappearance_currency_old_exp_and_foreign_sources(self):
        cases = ('missing', 'currency', 'rank', 'no quantity', 'outside', 'preexisting', 'foreign', 'foreign action',
                 'early capture', 'missing target', 'wrong original frame')
        for case in cases:
            with self.subTest(case=case):
                record, frames = self.combat_reward_frames()
                row = dict(text='Character EXP +16', x=155, y=478)
                if case != 'missing':
                    frames[22]['ocr'].append(row)
                if case == 'currency':
                    row['text'] = 'Mora × 28'
                if case == 'rank':
                    row['text'] = 'Adventure EXP +10'
                if case == 'no quantity':
                    row['text'] = 'Character EXP'
                if case == 'outside':
                    row['y'] = 180
                if case == 'preexisting':
                    frames[19]['ocr'].append(dict(text='Character EXP +12', x=180, y=470))
                if case == 'foreign':
                    frames[22]['session'] = 'different-session'
                if case == 'foreign action':
                    record['receipt']['details']['inputEvents'][0]['actionId'] = 'other:rotation:0'
                if case == 'early capture':
                    frames[20]['hud']['captureStamp']['capturedAt'] = 1900
                if case == 'missing target':
                    frames[19]['hud']['enemyBars'] = []
                if case == 'wrong original frame':
                    frames[22]['frameId'] = 23
                self.assertIsNone(route_tool.field_combat_feedback(record, '693306810', frames.__getitem__))

    def test_verified_combat_reward_resumes_suffix_in_the_existing_inventory(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        clear, enemy, inv = controller_scene(objective=''), controller_scene(objective='', enemies=True), controller_scene('inventory')
        pause = dict(mission='questStep', source=inv, result=dict(pausedInventory=True))
        proof = dict(verified=True, kind='inventory', session='route-session')
        interruption = dict(mission='navigation', status='failed', source=inv, result=dict(status='stopped',
            reason='Enemy observed during exploration', nextWaypointIndex=1, pauseVerified=True, pauseProof=proof))
        action = dict(mission='questStep', status='stopped', source=inv, result=dict(nativeGroup=False,
            nativeAttempted=True, nativeReturned=True, beforeFrameId=19, afterFrameId=23,
            pauseVerified=True, pauseProof=proof, chunks=[{}]))
        pilot = ReplayPilot(self.clock, [pause, interruption, dict(mission='questStep', source=enemy,
            result=dict(worldVisible=True)), pause, action, self.arrival(2, inv)], source=clear)
        pilot.archived_frame = mock.Mock()
        witness = dict(minimumDefeated=1, measuredClear=True, rewardFrameId=23)
        with mock.patch.object(route_tool, 'field_combat_feedback', return_value=witness):
            report = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual(report['status'], 'arrived')
        self.assertEqual(report['fieldCombatRewards'], [witness])
        self.assertEqual([r['waypoints'] for r in pilot.calls if r['mission']=='navigation'],
                         [self.points, self.points[1:]])
        combat_index = next(i for i,r in enumerate(pilot.calls) if r.get('step') == 'actTwoFieldCombat')
        self.assertEqual([r['mission'] for r in pilot.calls[combat_index + 1:]], ['observe', 'navigation'])

    def test_extended_controller_leg_bounds_each_native_request_and_keeps_legacy_limit(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        clear = controller_scene(objective='')
        enemy = controller_scene(objective='', enemies=True)
        inv = controller_scene('inventory')
        pause = dict(mission='questStep', source=inv, seconds=6, result=dict(pausedInventory=True))
        proof = dict(verified=True, kind='inventory', session='route-session')
        interrupted = dict(mission='navigation', seconds=40, status='failed', source=inv, result=dict(
            status='stopped', reason='Enemy observed during exploration', nextWaypointIndex=1,
            pauseVerified=True, pauseProof=proof))
        combat = dict(mission='questStep', status='stopped', source=inv, seconds=33, result=dict(nativeGroup=False,
            nativeAttempted=True, nativeReturned=True, beforeFrameId=19, afterFrameId=23,
            pauseVerified=True, pauseProof=proof, chunks=[{}]))
        pilot = ReplayPilot(self.clock, [pause, interrupted, dict(mission='questStep', source=enemy, seconds=10,
            result=dict(worldVisible=True)), pause, combat, self.arrival(2, inv)], source=clear)
        pilot.archived_frame = mock.Mock()
        budget = []
        execute = pilot.execute
        def bounded(mission, source, fields, deadline, save_pending):
            budget.append(deadline - self.clock.monotonic())
            return execute(mission, source, fields, deadline, save_pending)
        pilot.execute = bounded
        before = self.clock.monotonic()
        with mock.patch.object(route_tool, 'field_combat_feedback', return_value=dict(minimumDefeated=1, measuredClear=True)):
            report = self.run_controller(pilot, allow_field_combat=True, deadline_ms=150000)
        self.assertEqual((report['status'], report['originalDeadlineMs']), ('arrived', 150000))
        self.assertGreater(self.clock.monotonic() - before, 90)
        self.assertLessEqual(max(budget), 90)
        self.assertEqual([r['deadlineMs'] for r in pilot.calls if r['mission']=='navigation'], [45000,45000])
        self.assertEqual([r['deadlineMs'] for r in pilot.calls if r.get('step')=='actTwoFieldCombat'], [35000])
        with self.assertRaises(route_tool.RouteError):
            self.run_controller(pilot, deadline_ms=300001)
        with self.assertRaises(route_tool.RouteError):
            route_tool.run_route(self.progress.parent, self.route, pilot.session, deadline_ms=150000)
        self.assertEqual(route_tool.run_controller.__kwdefaults__['deadline_ms'], 90000)
        self.assertEqual(route_tool.run_route.__kwdefaults__['deadline_ms'], 90000)

    def test_initial_arrow_is_camera_only_and_requires_new_measured_bars(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        for enabled, changed, after_bars in ((False, True, False), (True, False, False),
                                              (True, True, False), (True, True, True)):
            self.progress = Path(self.temp.name) / ('entry-%s-%s-%s.json' % (enabled,changed,after_bars))
            arrow = controller_scene(objective='')
            marker = dict(kind='single-hostile-direction-arrow', side='right', x=1451, y=428.5)
            arrow['hud'].update(hostileDirectionArrow=marker,
                                enemyBarDiagnostic=dict(fieldCandidates=[dict(x=1451, y=428.5)]))
            post = controller_scene(objective='', enemies=True) if after_bars else arrow
            turn = dict(mission='questStep', source=post, frames=2,
                        result=dict(turnSent=True,viewChanged=changed,side='right',sourceFrameId=3,frameId=4))
            steps = [turn] if enabled else []
            if after_bars:
                # Stop once the real controller requests combat from its later independent sample.
                steps.append(dict(mission='questStep', status='failed'))
            pilot = ReplayPilot(self.clock, steps, source=arrow)
            execute = pilot.execute
            def measure(mission, source, fields, deadline, save_pending):
                result = execute(mission, source, fields, deadline, save_pending)
                if fields.get('step') == 'actTwoFaceFieldEnemy':
                    result['receipt']['details']['result']['capturedAt'] = self.clock.milliseconds()
                if mission == 'observe' and pilot.source['hud'].get('hostileDirectionArrow'):
                    pilot.source['hud']['enemyBarObservation'].update(state='ambiguous', candidateCount=1,
                        acceptedCount=0, reason='unanchored_bar_shaped_components')
                    result['observation'] = pilot.current()
                return result
            pilot.execute = measure
            result = self.run_controller(pilot, allow_field_combat=enabled)
            calls = [r.get('step', r['mission']) for r in pilot.calls]
            self.assertEqual(calls.count('actTwoFaceFieldEnemy'), int(enabled))
            self.assertNotIn('actTwoFaceRemainingEnemy',calls)
            self.assertNotIn('navigation',calls)
            self.assertFalse(result.get('fieldCombatRewards'))
            if enabled:
                self.assertEqual(calls[:2], ['observe','actTwoFaceFieldEnemy'])
                self.assertEqual(calls[2:], ['observe','worldInventory'] if after_bars else ['observe'] if changed else [])
                self.assertEqual(result['fieldEntryCamera']['viewChanged'], changed)
            else:
                self.assertEqual(set(calls), {'observe'})

    def test_post_defeat_arrow_requests_only_one_camera_turn_and_rechecks_ground(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        enemy, inv = controller_scene(objective='', enemies=True), controller_scene('inventory')
        arrow = controller_scene(objective='')
        marker = dict(kind='single-hostile-direction-arrow', side='right', x=1431.5, y=659.5)
        arrow['hud'].update(hostileDirectionArrow=marker,
                            enemyBarDiagnostic=dict(fieldCandidates=[dict(x=1431.5, y=659.5)]))
        pause = dict(mission='questStep', source=inv, result=dict(pausedInventory=True))
        action = dict(mission='questStep', status='stopped', source=inv, frames=5, result=dict(nativeGroup=False,
            nativeAttempted=True, nativeReturned=True, beforeFrameId=4, afterFrameId=5,
            pauseVerified=True, pauseProof=dict(session='route-session', verified=True, kind='inventory'), chunks=[{}]))
        pilot = ReplayPilot(self.clock, [pause, action, dict(mission='questStep', source=arrow,
            result=dict(worldVisible=True)), dict(mission='questStep', source=arrow, result=dict(turnSent=True))],
            source=enemy)
        pilot.archived_frame = mock.Mock()
        execute = pilot.execute

        def measured(mission, source, fields, deadline, save_pending):
            outcome = execute(mission, source, fields, deadline, save_pending)
            outcome['receipt']['timestamp'] = self.clock.milliseconds()
            if mission == 'observe' and pilot.source['hud'].get('hostileDirectionArrow'):
                pilot.source['hud']['enemyBarObservation'].update(state='ambiguous', candidateCount=1,
                    acceptedCount=0, reason='unanchored_bar_shaped_components')
                outcome['observation'] = pilot.current()
            return outcome

        pilot.execute = measured
        def earned(record, uid, archived):
            return dict(requestId=record['request']['id'], rewardFrameId=5, pauseSourceFrameId=6,
                        minimumDefeated=1, measuredClear=False)
        with mock.patch.object(route_tool, 'field_combat_feedback', side_effect=earned):
            result = self.run_controller(pilot, allow_field_combat=True)
        self.assertEqual(result['status'], 'waiting')
        self.assertEqual([r.get('step', r['mission']) for r in pilot.calls],
            ['observe', 'worldInventory', 'observe', 'actTwoFieldCombat', 'observe', 'worldInventoryClose',
             'observe', 'actTwoFaceRemainingEnemy', 'observe'])
        self.assertEqual(len(result['fieldCameraSearches']), 1)
        self.assertIs(result['fieldCameraSearches'][0]['turnSent'], True)

    def test_threat_interrupt_preserves_completed_waypoints_before_reinspection(self):
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        inv, clear = controller_scene('inventory'), controller_scene(objective='')
        pause = dict(mission='questStep', source=inv, result=dict(pausedInventory=True))
        for index, reason in enumerate(('Enemy observed during exploration', 'Ground enemy scan did not establish clear ground')):
            self.progress = Path(self.temp.name) / ('field-interrupt-%d.json' % index)
            interruption = dict(mission='navigation', status='failed', source=inv, result=dict(
                status='stopped', reason=reason, nextWaypointIndex=1, pauseVerified=True,
                pauseProof=dict(verified=True, kind='inventory', session='route-session')))
            pilot = ReplayPilot(self.clock, [pause, interruption, dict(mission='questStep', source=clear,
                result=dict(worldVisible=True)), pause, self.arrival(2, inv)], source=clear)
            report = self.run_controller(pilot, allow_field_combat=True)
            self.assertEqual((report['status'],report['fieldRotations']), ('arrived',0))
            self.assertEqual([r['waypoints'] for r in pilot.calls if r['mission'] == 'navigation'],
                             [self.points,self.points[1:]])

    def test_exploration_pack_requires_matching_counts_without_a_candidate_list_and_opt_in(self):
        now = self.clock.milliseconds()
        base = controller_scene(objective='', enemies=True)
        base['timestamp'] = now
        def phase(source, enabled):
            return route_tool.route_phase(source, '693306810', [route_tool.EXPLORATION_OBJECTIVE],
                allow_dialogue=False, journal_resume=False, now_ms=now, allow_field_combat=enabled)[0]
        for count in (1, 2, 3, 4):
            sample = copy.deepcopy(base)
            sample['hud']['enemyBars'] = [dict(x=1069-i*33,y=412-i*34,width=64,height=3,
                                                rectangularity=.95) for i in range(count)]
            record_ground_scan(sample)
            self.assertEqual(phase(sample, True), 'fieldCombat' if count <= 3 else 'wait')
            self.assertEqual(phase(sample, False), 'wait')
            sample['hud']['enemyBarObservation']['candidateCount'] += 1
            self.assertEqual(phase(sample, True), 'wait')

    def test_temple_accepted_hostiles_survive_rejected_field_fragments(self):
        now = self.clock.milliseconds()
        # Slime clearing frames 25 and 26. The small red pieces below the acceptance threshold
        # remain in the ground diagnostic, but they are not separate hostile targets.
        for geometry, accepted in (
                ([(1344,440,64,6),(1538,446,52,4),(1506,446,8,4),(1498,446,4,4)], 2),
                ([(1535.5,446,57,4),(1498,446,4,4)], 1)):
            source = controller_scene(objective='')
            source['timestamp'] = now
            components = [dict(x=x,y=y,width=w,height=h) for x,y,w,h in geometry]
            hud = source['hud']
            hud['enemyBars'] = components[:accepted]
            record_ground_scan(source)
            scan = hud['enemyBarObservation']
            scan.update(candidateCount=len(components), reason='outdoor_bar_candidates')
            hud['enemyBarDiagnostic'] = dict(level='any', fieldCandidates=components)
            def phase(at=now):
                return route_tool.route_phase(source, '693306810', [route_tool.EXPLORATION_OBJECTIVE],
                    allow_dialogue=False, journal_resume=False, now_ms=at, allow_field_combat=True)[0]
            self.assertEqual(phase(), 'fieldCombat')
            self.assertEqual(phase(now + 2001), 'wait')
            self.assertFalse(route_tool.ground_scan_is_clear(source, now))
            scan['candidateCount'] -= 1
            self.assertEqual(phase(), 'wait')
            scan['candidateCount'] = len(components)
            hud['enemyBarDiagnostic']['overloaded'] = True
            self.assertEqual(phase(), 'wait')
            hud['enemyBarDiagnostic']['overloaded'] = False
            scan['acceptedCount'] = 0
            self.assertEqual(phase(), 'wait')
            hud['enemyBars'] = []
            scan['state'] = 'ambiguous'
            self.assertEqual(phase(), 'wait')
            self.assertFalse(route_tool.ground_scan_is_clear(source, now))

    def test_recent_positive_scan_can_park_for_native_remeasurement_under_capture_load(self):
        now = self.clock.milliseconds()
        source = controller_scene(objective='', enemies=True)
        source['timestamp'] = now - 1316
        record_ground_scan(source)
        source['timestamp'] += 949  # Measured native OCR and publication on Temple frame 36.
        def phase(at):
            return route_tool.route_phase(source, '693306810', [route_tool.EXPLORATION_OBJECTIVE],
                allow_dialogue=False, journal_resume=False, now_ms=at, allow_field_combat=True)[0]
        self.assertEqual(phase(now), 'fieldCombat')
        self.assertEqual(phase(now + 685), 'wait')
        source['hud']['enemyBars'] = []
        source['timestamp'] = now - 1316
        record_ground_scan(source)
        self.assertEqual(phase(now), 'wait')

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
        self.assertEqual(pilot.calls[-1]['step'], 'actTwoFieldCombat')

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

    def test_world_entry_capability_belongs_to_this_idle_session_and_frame(self):
        path = self.root / 'controller-status.json'
        self.assertFalse(self.pilot.supports_field_combat_world_entry(self.source))
        heartbeat = read_json(path)
        heartbeat['fieldCombatWorldEntry'] = True
        path.write_text(json.dumps(heartbeat))
        self.assertTrue(self.pilot.supports_field_combat_world_entry(self.source))
        for change in (dict(session='changed-session'), dict(frameId=2), dict(heartbeatAt=heartbeat['heartbeatAt'] - 10000),
                       dict(processId=111), dict(state='running')):
            path.write_text(json.dumps(dict(heartbeat, **change)))
            with self.assertRaises(RuntimeError):
                self.pilot.supports_field_combat_world_entry(self.source)
        self.assertEqual(self.writes, [])

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

    def test_terminal_observe_gets_read_only_grace_and_releases_its_lease(self):
        """Use the real quiescence loop with a valid receipt but delayed native idle publication."""
        original = self.terminal
        began = self.clock.monotonic()
        deadline = began + .2

        def terminal_before_idle(request, status='completed'):
            """Publish exact terminal evidence before the corresponding idle heartbeat."""
            original(request, status)
            self.write_heartbeat('running', self.source['frameId'], request['id'])

        def settle(seconds):
            """Only advance the inert clock and publish the same owner's idle status."""
            self.clock.advance(seconds)
            if self.clock.monotonic() >= began + .4:
                self.write_heartbeat('idle', self.source['frameId'])

        self.terminal = terminal_before_idle
        self.fake_time.sleep = settle
        outcome = self.pilot.execute('observe', self.source, {}, deadline, lambda _: None)
        self.assertEqual(outcome['receipt']['status'], 'completed')
        self.assertGreater(self.clock.monotonic(), deadline)
        self.assertLessEqual(self.clock.monotonic(), began + 1.1)
        self.assertEqual([name for name, _ in self.writes], ['request.json'])
        self.assertIsNone(self.pilot.pending)
        self.pilot.close()
        self.assertFalse(self.pilot.lock.exists())
        # Grace does not renew publication authority for a subsequent input.
        with self.assertRaisesRegex(route_tool.RouteError, 'deadline expired'):
            self.pilot.execute('keyPress', self.source, {'key': 'VK_ESCAPE'}, deadline, lambda _: None)
        self.assertEqual([name for name, _ in self.writes], ['request.json'])

    def test_terminal_observe_grace_is_bounded_and_keeps_unsettled_lease(self):
        """A still-active heartbeat cannot acquire an unlimited retirement wait."""
        original = self.terminal

        def never_idle(request, status='completed'):
            """Retain the valid receipt while keeping the exact controller active."""
            original(request, status)
            self.write_heartbeat('running', self.source['frameId'], request['id'])

        self.terminal = never_idle
        self.fake_time.sleep = self.clock.advance
        began = self.clock.monotonic()
        with mock.patch.object(self.command, 'wait_for_controller_quiescence',
                               wraps=self.command.wait_for_controller_quiescence) as wait:
            with self.assertRaisesRegex(route_tool.RouteError, 'no settled controller'):
                self.pilot.execute('observe', self.source, {}, began + .05, lambda _: None)
        self.assertEqual(wait.call_args.kwargs['timeout_seconds'], 1.0)
        self.assertLessEqual(self.clock.monotonic() - began, 1.11)
        self.assertIsNotNone(self.pilot.pending)
        self.pilot.close()
        self.assertTrue(self.pilot.lock.exists())
        self.assertEqual([name for name, _ in self.writes], ['request.json'])

    def test_terminal_input_mission_receives_no_passive_grace(self):
        """The original input deadline still bounds its 400 ms settlement requirement."""
        began = self.clock.monotonic()
        with mock.patch.object(self.command, 'wait_for_controller_quiescence',
                               wraps=self.command.wait_for_controller_quiescence) as wait:
            with self.assertRaisesRegex(route_tool.RouteError, 'no settled controller'):
                self.pilot.execute('combat', self.source,
                    dict(objective='Defeat the nearby hilichurls', deadlineMs=1000), began + .05, lambda _: None)
        self.assertLessEqual(wait.call_args.kwargs['timeout_seconds'], .051)
        self.assertIsNotNone(self.pilot.pending)
        self.assertEqual([name for name, _ in self.writes], ['request.json'])

    def test_missing_terminal_observe_has_no_grace_or_replay(self):
        """An unresolved request takes the original cancellation path and retains uncertainty."""
        self.pending_mode = True
        self.fake_time.sleep = self.clock.advance
        with mock.patch.object(self.command, 'wait_for_controller_quiescence') as wait:
            with self.assertRaisesRegex(route_tool.RouteError, 'terminal outcome is unresolved'):
                self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + .05, lambda _: None)
        wait.assert_not_called()
        self.assertIsNotNone(self.pilot.pending)
        self.assertEqual([name for name, _ in self.writes], ['request.json', 'stop.json'])

    def test_foreign_terminal_observe_cannot_enter_settlement_grace(self):
        """Receipt identity remains mandatory before any additional read-only wait."""
        original = self.terminal

        def foreign(request, status='completed'):
            """Mutate only the retained terminal envelope's session."""
            original(request, status)
            path = self.command.request_receipt_path(self.root, self.pilot.session, request['id'])
            receipt = read_json(path); receipt['session'] = 'foreign-session'
            path.write_text(json.dumps(receipt), encoding='utf-8')

        self.terminal = foreign
        with mock.patch.object(self.command, 'wait_for_controller_quiescence') as wait:
            with self.assertRaisesRegex(route_tool.RouteError, 'receipt identity differs'):
                self.pilot.execute('observe', self.source, {}, self.clock.monotonic() + .05, lambda _: None)
        wait.assert_not_called()
        self.assertIsNotNone(self.pilot.pending)
        self.assertEqual([name for name, _ in self.writes], ['request.json'])

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




class RouteStartNearTests(unittest.TestCase):
    """A retained failure location is never a substitute for a fresh route start."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = ControllerClock()
        self.progress = Path(self.temp.name)/'progress.json'
        self.route = dict(objective=route_tool.EXPLORATION_OBJECTIVE,
            waypoints=[dict(map='Teyvat', x=-1134, y=2266)],
            startNear=dict(map='Teyvat', x=-1141.85, y=2274.03, radius=3))

    def world(self, *, far=False, enemies=False):
        """Use ordinary measured native-shaped world data at or away from the rock."""
        source = controller_scene(enemies=enemies)
        source['hud']['objectives'] = []
        source['map'].update(x=-1100 if far else -1141.8515625, y=2274.033203125)
        return source

    def run_route(self, pilot, **kwargs):
        """Run the actual controller with only its process/input boundary replaced."""
        return route_tool.run_controller(pilot, self.route, self.progress, '693306810',
            monotonic=self.clock.monotonic, clock_ms=self.clock.milliseconds, emit=lambda _:None, **kwargs)

    def test_exact_optional_start_shape_and_finite_positive_radius(self):
        route_tool.validate_route(self.route)
        invalid = [None, {}, dict(self.route['startNear'], extra=1), dict(self.route['startNear'], map='City_102')]
        invalid += [dict(self.route['startNear'], **{key:value}) for key,value in
            [('x',True),('y',float('nan')),('radius',False),('radius',0),('radius',-1),('radius',float('inf'))]]
        for start in invalid:
            with self.subTest(start=start), self.assertRaises(route_tool.RouteError):
                route_tool.validate_route(dict(self.route, startNear=start))
        with self.assertRaisesRegex(route_tool.RouteError, 'controller mode'):
            route_tool.run_route(Path(self.temp.name), self.route, 'route-session')
        self.assertFalse((Path(self.temp.name)/'request.json').exists())

    def test_near_world_records_its_actual_measurement_before_navigation(self):
        inventory = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=inventory, result=dict(pausedInventory=True)),
            dict(mission='navigation', source=inventory, result=dict(status='arrived', nextWaypointIndex=1))], source=self.world())
        result = self.run_route(pilot)
        self.assertEqual(result['status'], 'arrived')
        self.assertEqual(result['route']['startNear'], self.route['startNear'])
        witness = result['startNearVerified']
        self.assertEqual((witness['session'], witness['frameId']), ('route-session', 2))
        self.assertLess(witness['distance'], .01)
        self.assertEqual([p.get('step',p['mission']) for p in pilot.calls if p['mission']!='observe'], ['worldInventory','navigation'])

    def test_far_world_refuses_before_navigation_or_opted_in_combat(self):
        for index, enemy in enumerate((False, True)):
            self.progress = Path(self.temp.name)/f'far-{index}.json'
            pilot = ReplayPilot(self.clock, source=self.world(far=True, enemies=enemy))
            result = self.run_route(pilot, allow_field_combat=True)
            self.assertEqual(result['status'], 'stopped')
            self.assertIn('outside startNear', result['reason'])
            self.assertEqual([p['mission'] for p in pilot.calls], ['observe'])
            self.assertNotIn('startNearVerified', result)

    def test_inventory_close_requires_a_new_eligible_world_start(self):
        inventory = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [
            dict(mission='questStep', source=self.world(), result=dict(resumedWorld=True)),
            dict(mission='questStep', source=inventory, result=dict(pausedInventory=True)),
            dict(mission='navigation', source=inventory, result=dict(status='arrived', nextWaypointIndex=1))], source=inventory)
        result = self.run_route(pilot)
        self.assertEqual(result['status'], 'arrived')
        self.assertEqual(result['startNearVerified']['frameId'], 4)
        self.assertEqual([p.get('step',p['mission']) for p in pilot.calls if p['mission']!='observe'],
            ['worldInventoryClose','worldInventory','navigation'])

    def test_wrong_start_after_inventory_close_has_no_second_key_or_movement(self):
        inventory = controller_scene('inventory')
        pilot = ReplayPilot(self.clock, [dict(mission='questStep', source=self.world(far=True),
            result=dict(resumedWorld=True))], source=inventory)
        result = self.run_route(pilot)
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual([p.get('step',p['mission']) for p in pilot.calls if p['mission']!='observe'], ['worldInventoryClose'])

    def test_foreign_account_or_unlocated_dialogue_cannot_grant_the_start(self):
        foreign = self.world(); foreign['ocr'][0]['text'] = 'UID: 123456789'
        for index, source in enumerate((foreign, controller_scene('dialogue'))):
            self.progress = Path(self.temp.name)/f'foreign-{index}.json'
            pilot = ReplayPilot(self.clock, source=source)
            result = self.run_route(pilot, allow_dialogue=True)
            self.assertEqual(result['status'], 'waiting')
            self.assertEqual([p['mission'] for p in pilot.calls], ['observe'])
            self.assertNotIn('startNearVerified', result)

    def test_start_measurement_refuses_stale_foreign_and_boolean_position(self):
        source = self.world(); source['timestamp'] = self.clock.milliseconds()
        for mutate in (lambda s:s.update(timestamp=s['timestamp']-1001), lambda s:s.update(session='old'),
                       lambda s:s['map'].update(x=True)):
            value = copy.deepcopy(source); mutate(value)
            with self.assertRaises(route_tool.RouteError):
                route_tool.require_start_near(value, 'route-session', '693306810', self.route['startNear'], self.clock.milliseconds())


class ParkingReplayPilot(ReplayPilot):
    """Exercise the real controller exit path with explicit idle-owner and receipt boundaries."""
    def __init__(self, clock, script=(), source=None):
        super().__init__(clock, script, source)
        self.owner_error = None
        self.after_observe = None
        self.observations = 0
        self.deadlines = []

    def _owner(self, frame=None, *, idle=False):
        """A fresh owned idle frame is required before any protection request."""
        if self.owner_error:
            raise route_tool.RouteError(self.owner_error)
        if idle and (self.pending is not None or frame != self.source['frameId']):
            raise route_tool.RouteError('Active request or mismatched frame')
        return dict(scriptSession=self.session, activeRequestId=None, serviceOwnsPilot=True)

    def execute(self, mission, source, fields, deadline, save_pending):
        """Use the existing receipt replay and expose only passive source changes."""
        self.deadlines.append(deadline)
        outcome = super().execute(mission, source, fields, deadline, save_pending)
        if mission == 'observe':
            self.observations += 1
            if self.after_observe:
                self.after_observe(self)
                outcome['observation'] = copy.deepcopy(self.source)
        return outcome


class RouteFailureProtectionTests(unittest.TestCase):
    """Keep failed/waiting route status while qualifying one bounded inventory park."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = ControllerClock()
        self.progress = Path(self.temp.name) / 'progress.json'
        self.route = dict(objective='Go to Mondstadt', waypoints=[dict(map='Teyvat', x=-1170, y=2208)])

    def tearDown(self):
        self.temp.cleanup()

    def park(self, **changes):
        """Provide a settled existing worldInventory outcome without a simulated raw-key API."""
        return dict(mission='questStep', source=controller_scene('inventory'),
                    result=dict(pausedInventory=True), **changes)

    def run_route(self, pilot, **options):
        """Execute production controller logic on its original clock."""
        return route_tool.run_controller(pilot, self.route, self.progress, '693306810',
            monotonic=self.clock.monotonic, clock_ms=self.clock.milliseconds, emit=lambda _: None, **options)

    def waiting(self, script=()):
        """A live field with an unapproved objective creates a normal passive waiting outcome."""
        return ParkingReplayPilot(self.clock, script, controller_scene(objective='Other quest'))

    def test_waiting_field_parks_once_and_keeps_original_outcome(self):
        pilot = self.waiting([self.park()])
        report = self.run_route(pilot, deadline_ms=10000)
        protection = report['exitProtection']
        self.assertEqual(report['status'], 'waiting')
        self.assertEqual(report['reason'], protection['originalReason'])
        self.assertEqual(report['nextWaypointIndex'], 0)
        self.assertTrue(protection['protectionVerified'])
        self.assertEqual(protection['originalRecordCount'], 1)
        self.assertEqual([r['mission'] for r in pilot.calls], ['observe', 'observe', 'questStep'])
        self.assertEqual(pilot.calls[-1]['step'], 'worldInventory')
        self.assertEqual(protection['requestIds'], [r['id'] for r in pilot.calls[1:]])
        self.assertEqual(pilot.deadlines[1], pilot.deadlines[2])
        self.assertLessEqual(pilot.deadlines[1], pilot.deadlines[0])
        self.assertLessEqual(pilot.deadlines[1], 108.1)
        self.assertEqual(read_json(self.progress), report)

    def test_settled_failure_keeps_its_original_receipt_and_reason(self):
        failed = dict(mission='navigation', status='stopped', result=dict(status='stopped', reason='Obstacle', nextWaypointIndex=0))
        pilot = ParkingReplayPilot(self.clock, [failed, self.park()], controller_scene(objective='Go to Mondstadt'))
        report = self.run_route(pilot)
        self.assertEqual(report['status'], 'stopped')
        self.assertIn('Mission did not complete', report['reason'])
        self.assertEqual(report['records'][1]['receipt']['status'], 'stopped')
        self.assertTrue(report['exitProtection']['protectionVerified'])
        self.assertEqual([r.get('step') for r in pilot.calls if r['mission'] == 'questStep'], ['worldInventory'])

    def test_stop_pending_unknown_owner_ui_and_elapsed_clock_have_no_exit_input(self):
        for case in ('stop', 'pending', 'active', 'foreign_owner', 'foreign_uid', 'unknown_ui', 'elapsed'):
            with self.subTest(case=case):
                self.progress = Path(self.temp.name) / (case + '.json')
                pilot = self.waiting()
                if case == 'active':
                    pilot.owner_error = 'Active request'
                if case == 'foreign_owner':
                    pilot.owner_error = 'Foreign owner'
                if case == 'foreign_uid':
                    pilot.source['ocr'][0]['text'] = 'UID: 123456789'
                if case == 'unknown_ui':
                    pilot.source['hud']['dialogueReady'] = True
                def mutate(p):
                    """Change only the declared failure boundary after its ordinary passive frame."""
                    if case == 'stop':
                        p.stop = True
                    elif case == 'pending':
                        p.pending = dict(id='unresolved')
                    elif case == 'elapsed':
                        self.clock.advance(91)
                pilot.after_observe = mutate
                report = self.run_route(pilot)
                self.assertFalse(report.get('exitProtection', {}).get('protectionVerified', False))
                self.assertEqual([r['mission'] for r in pilot.calls], ['observe'])

    def test_bad_refreshed_field_or_stop_never_sends_B(self):
        for case in ('foreign_uid', 'unknown_ui', 'stale', 'stop', 'active', 'budget'):
            with self.subTest(case=case):
                self.progress = Path(self.temp.name) / (case + '.json')
                pilot = self.waiting()
                def changed(p):
                    """The one exit refresh may remove authority but cannot renew it artificially."""
                    if p.observations != 2:
                        return
                    if case == 'foreign_uid':
                        p.source['ocr'][0]['text'] = 'UID: 123456789'
                    elif case == 'unknown_ui':
                        p.source['hud']['world'] = False
                    elif case == 'stale':
                        p.source['timestamp'] -= 1001
                    elif case == 'active':
                        p.owner_error = 'Active request appeared during refresh'
                    elif case == 'budget':
                        self.clock.advance(8)
                        p.source['timestamp'] = self.clock.milliseconds()
                    else:
                        p.stop = True
                pilot.after_observe = changed
                report = self.run_route(pilot)
                self.assertEqual(report['status'], 'waiting')
                self.assertFalse(report['exitProtection']['protectionVerified'])
                self.assertEqual([r['mission'] for r in pilot.calls], ['observe', 'observe'])

    def test_failed_or_pending_pause_is_never_repeated(self):
        for pending in (False, True):
            with self.subTest(pending=pending):
                self.progress = Path(self.temp.name) / (str(pending) + '.json')
                item = self.park()
                item.update(pending=pending, result=dict(pausedInventory=False))
                pilot = self.waiting([item])
                report = self.run_route(pilot)
                self.assertEqual(report['status'], 'waiting')
                self.assertFalse(report['exitProtection']['protectionVerified'])
                self.assertEqual(len([r for r in pilot.calls if r['mission'] == 'questStep']), 1)
                self.assertEqual(report['pending'] is not None, pending)

    def test_previous_inventory_preparation_is_not_retried(self):
        source = controller_scene(enemies=True)
        source['hud']['objectives'] = []
        self.route['objective'] = route_tool.EXPLORATION_OBJECTIVE
        pilot = ParkingReplayPilot(self.clock, [dict(mission='questStep', status='stopped',
            result=dict(pausedInventory=False))], source)
        report = self.run_route(pilot, allow_field_combat=True)
        self.assertEqual(report['status'], 'stopped')
        self.assertIn('not repeated', report['exitProtection']['reason'])
        self.assertEqual([r['mission'] for r in pilot.calls], ['observe', 'questStep'])

    def test_arrived_route_has_no_exit_protection_or_extra_request(self):
        pilot = ParkingReplayPilot(self.clock, [dict(mission='navigation', result=dict(status='arrived', nextWaypointIndex=1))],
            controller_scene(objective='Go to Mondstadt'))
        report = self.run_route(pilot)
        self.assertEqual(report['status'], 'arrived')
        self.assertNotIn('exitProtection', report)
        self.assertEqual([r['mission'] for r in pilot.calls], ['observe', 'navigation'])


if __name__ == '__main__':
    unittest.main()

