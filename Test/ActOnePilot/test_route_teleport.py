"""Exercise the native travel prelude through the normal route controller entry point."""
import tempfile
import unittest
from pathlib import Path

from test_route_resume import ControllerClock, ReplayPilot, controller_scene, route_tool


class TeleportRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.progress = Path(self.temp.name) / 'progress.json'
        self.clock = ControllerClock()
        self.field = controller_scene()
        self.inventory = controller_scene('inventory')
        self.map_screen = controller_scene('modal')
        self.map_screen['hud']['bigMap'] = True
        self.route = dict(objective=self.field['hud']['objectives'][0], teleportTo='temple-of-the-lion',
                          waypoints=[dict(map='Teyvat', x=-1178, y=2208)])

    def step(self, source, **result):
        return dict(mission='questStep', source=source, result=result)

    def landed(self, step):
        return self.step(self.inventory, step=step, destinationReached=True, teleportAttempted=True,
                         pauseVerified=True, pauseProof=dict(kind='inventory', session='route-session', verified=True),
                         fieldFrameId=4, fieldPosition=dict(map='Teyvat', x=-1178, y=2208))

    def run_route(self, source, script):
        pilot = ReplayPilot(self.clock, script, source=source)
        report = route_tool.run_controller(pilot, self.route, self.progress, '693306810',
            monotonic=self.clock.monotonic, clock_ms=self.clock.milliseconds, emit=lambda _: None)
        return report, [row.get('step', row['mission']) for row in pilot.calls if row['mission'] != 'observe']

    def test_world_opens_inventory_and_map_then_walks_after_verified_landing(self):
        script = [self.step(self.inventory), self.step(self.map_screen), self.landed('actTwoLionTeleport'),
                  self.step(self.field), dict(mission='navigation', source=self.field,
                                              result=dict(status='arrived', nextWaypointIndex=1))]
        report, calls = self.run_route(self.field, script)
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        self.assertEqual(report['teleportArrival']['destination'], 'temple-of-the-lion')
        self.assertEqual(calls, ['worldInventory', 'actTwoWorldMap', 'actTwoLionTeleport', 'worldInventoryClose', 'navigation'])

    def test_expired_inventory_before_publication_recaptures_without_replaying_map_input(self):
        original = ReplayPilot.inventory_ready
        seen = []
        def cold(pilot,source,*args,**kwargs):
            seen.append(source['frameId'])
            if len(seen) == 1:
                return False
            return original(pilot,source,*args,**kwargs)
        from unittest.mock import patch
        with patch.object(ReplayPilot,'inventory_ready',cold):
            result,calls = self.run_route(self.inventory,[self.step(self.map_screen),self.landed('actTwoLionTeleport'),
                self.step(self.field),dict(mission='navigation',source=self.field,result=dict(status='arrived',nextWaypointIndex=1))])
        self.assertEqual(result['status'],'arrived',result.get('reason'))
        self.assertGreater(seen[1],seen[0])
        self.assertEqual(calls.count('actTwoWorldMap'),1)

    def test_expired_unpublished_inventory_exit_refreshes_and_publishes_once(self):
        from unittest.mock import patch
        execute=ReplayPilot.execute
        expired=[]
        def delayed(pilot,mission,source,fields,*args,**kwargs):
            if fields.get('step')=='worldInventoryClose' and not expired:
                expired.append(source['frameId'])
                raise route_tool.ExpiredInputSource('expired before rename')
            return execute(pilot,mission,source,fields,*args,**kwargs)
        with patch.object(ReplayPilot,'execute',delayed):
            report,calls=self.run_route(self.map_screen,[self.landed('actTwoLionTeleport'),self.step(self.field),
                dict(mission='navigation',source=self.field,result=dict(status='arrived',nextWaypointIndex=1))])
        self.assertEqual(report['status'],'arrived',report.get('reason'))
        self.assertEqual(calls.count('worldInventoryClose'),1)
        self.assertGreater(next(r['request']['expectedFrameId'] for r in report['records'] if r['request'].get('step')=='worldInventoryClose'),expired[0])

    def test_open_map_requires_no_extra_menu_transitions(self):
        report, calls = self.run_route(self.map_screen, [self.landed('actTwoLionTeleport'), self.step(self.field),
            dict(mission='navigation', source=self.field, result=dict(status='arrived', nextWaypointIndex=1))])
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        self.assertEqual(calls[0], 'actTwoLionTeleport')

    def test_mondstadt_city_uses_the_existing_city_waypoint(self):
        self.route['teleportTo'] = 'mondstadt-city'
        report, calls = self.run_route(self.map_screen, [self.landed('actTwoCityTeleport'), self.step(self.field),
            dict(mission='navigation', source=self.field, result=dict(status='arrived', nextWaypointIndex=1))])
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        self.assertEqual(calls[0], 'actTwoCityTeleport')

    def test_direct_starfell_inventory_travel(self):
        self.route['teleportTo'] = 'starfell-lake'
        report, calls = self.run_route(self.inventory, [self.landed('actTwoStarfellInventoryTeleport'), self.step(self.field),
            dict(mission='navigation', source=self.field, result=dict(status='arrived', nextWaypointIndex=1))])
        self.assertEqual(report['status'], 'arrived', report.get('reason'))
        self.assertEqual(calls[0], 'actTwoStarfellInventoryTeleport')

    def test_wrong_account_sends_no_travel_input(self):
        self.map_screen['ocr'][0]['text'] = 'UID: 123456789'
        report, calls = self.run_route(self.map_screen, [])
        self.assertEqual((report['status'], calls), ('stopped', []))

    def test_unverified_native_landing_does_not_start_navigation(self):
        landing = self.landed('actTwoLionTeleport')
        landing['result']['destinationReached'] = False
        report, calls = self.run_route(self.map_screen, [landing])
        self.assertEqual((report['status'], calls), ('stopped', ['actTwoLionTeleport']))
        self.assertNotIn('teleportArrival', report)

    def test_invalid_destination_cannot_be_used_as_a_native_step(self):
        for invalid in ('actTwoLionTeleport', None, [], 'unknown'):
            with self.subTest(invalid=invalid), self.assertRaises(route_tool.RouteError):
                route_tool.validate_route(dict(self.route, teleportTo=invalid))


if __name__ == '__main__':
    unittest.main()
