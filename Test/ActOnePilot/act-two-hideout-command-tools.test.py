"""Pure regressions for command generation; never imports or starts gameplay."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


class CommandToolsTest(unittest.TestCase):
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
