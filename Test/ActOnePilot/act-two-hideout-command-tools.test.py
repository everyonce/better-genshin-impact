"""Pure regressions for command generation; never imports or starts gameplay."""
import ast
import json,os,shutil,subprocess,sys,tempfile,time
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


class CommandToolsTest(unittest.TestCase):
    def test_active_event_map_fallback_requires_recent_same_session_counter(self):
        tree = ast.parse((ROOT / 'tools/quest-pilot/act-two-field-plan.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'active_event_witness')
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<event>', 'exec'), scope)
        check = scope['active_event_witness']
        witness = {'session': 's', 'timestamp': 1000, 'hud': {'objectives': ['Defeat all opponents 6/7']}}
        self.assertTrue(check(witness, 's', 1100))
        self.assertTrue(check({**witness, 'hud': {'objectives': ['Defeat all opponents 3/9']}}, 's', 1100))
        for count in ['9/9', '8/7', '0/8']:
            self.assertFalse(check({**witness, 'hud': {'objectives': ['Defeat all opponents '+count]}}, 's', 1100))
        for patch, session, now in [({}, 'other', 1100), ({}, 's', 999), ({}, 's', 601001),
                                    ({'hud': {'objectives': ['Defeat all opponents 7/7']}}, 's', 1100),
                                    ({'hud': {'objectives': []}}, 's', 1100)]:
            self.assertFalse(check({**witness, **patch}, session, now))

    def test_planner_preflight_rejects_recorded_nonworld_before_writing(self):
        fixtures=json.loads((ROOT/'Test/ActOnePilot/act-two-hideout-witness-handoff.fixture.json').read_text())
        with tempfile.TemporaryDirectory(prefix="witness-test-",dir=ROOT/"artifacts",delete=False) as d:
            app=Path(d);r=app/'User/JsScript/ActOnePilot';r.mkdir(parents=True)
            shutil.copyfile(ROOT/'BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js',r/'act-two-field.js')
            env={**os.environ,'BETTERGI_PILOT_APP_DIR':str(app)}
            for f,valid in [(17762,True),(17767,False),(17768,False)]:
                w=fixtures[str(f)];w['timestamp']=int(time.time()*1000)
                obs=r/'observations'/w['session'];obs.mkdir(parents=True,exist_ok=True)
                (obs/f'frame-{f:04}.json').write_text(json.dumps(w))
                (obs/'frame-0001.json').write_text('{}')
                (r/'controller-status.json').write_text(json.dumps(dict(state='idle',frameId=f+2,session=w['session'])))
                q=subprocess.run([sys.executable,str(ROOT/'tools/quest-pilot/act-two-field-plan.py'),'--frame',str(f+2),'--witness',str(f),'--mode','actions','--actions','[{"type":"look","dx":-250,"dy":0}]','--region-map-witness','1','--visual-position-reviewed','--event-reposition','--validate-only'],env=env,capture_output=True,text=True)
                self.assertEqual(q.returncode==0,valid,q.stdout+q.stderr)
                if valid:self.assertTrue(json.loads(q.stdout)['validationPassed'])
                else:self.assertIn('witness_not_verified_world',q.stderr)
                self.assertFalse((r/'act-two-field-request.json').exists())

    def test_regional_heading_without_fog_coordinates(self):
        tree = ast.parse((ROOT / 'tools/quest-pilot/act-two-reviewed-replay.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'observed_heading')
        scope = {'math': math}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<heading>', 'exec'), scope)
        heading = scope['observed_heading']
        self.assertEqual(heading({'hud': {'compassAngle': 97}, 'map': None}), 97)
        self.assertEqual(heading({'hud': {}, 'map': {'cameraAngle': 68}}), 68)
        for value in [None, float('nan'), float('inf'), -1, 360]:
            with self.assertRaises(RuntimeError):
                heading({'hud': {'compassAngle': value}, 'map': None})

    def test_native_window_option_matches_runtime_plan_contract(self):
        tree = ast.parse((ROOT / 'tools/quest-pilot/act-two-field-plan.py').read_text())
        block = next(n for n in tree.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'a.native_combat')
        code = compile(ast.Module(body=[block], type_ignores=[]), '<native-plan>', 'exec')
        for level, windows, accepted in [('10', 1, True), ('13', 1, True), ('13', 3, True), ('10', 2, False)]:
            scope = {'a': SimpleNamespace(native_combat=True, mode='combat', enemy_level=level,
                       region_map_witness=100, native_windows=windows, native_search=False,
                       native_avatar='Kaeya'), 'plan': {'actions': []}}
            if accepted:
                exec(code, scope)
                self.assertEqual(scope['plan'].get('nativeWindows'), windows if level == '13' else None)
                self.assertTrue(scope['plan']['nativeCombat'])
            else:
                with self.assertRaises(SystemExit):
                    exec(code, scope)


if __name__ == '__main__':
    unittest.main()
