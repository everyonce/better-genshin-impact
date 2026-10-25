"""Portable source and inert admission checks; no native/model module is imported."""
import ast
import hashlib
from pathlib import Path
import tempfile
import types
import unittest

import native_action_split as split
import native_history_runtime as history
from native_history_feedback import FeedbackError

HERE = Path(__file__).resolve().parent
DATA = HERE / 'step_application_testdata' / 'preimages'


def constants(name):
    """Read literal module constants without executing the source module."""
    result = {}
    for node in ast.parse((HERE / name).read_bytes()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        result[target.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
    return result


def functions(path):
    """Compare every original function body independently of file pins and comments."""
    found = {}
    for node in ast.parse(path.read_bytes()).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = ast.dump(node)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found[node.name + '.' + child.name] = ast.dump(child)
    return found


class PortCases(unittest.TestCase):
    """Bind the final sources and exercise real qualification rejection before numerical work."""
    def loader(self):
        """Bind compiled whole-source load_model code without executing the loader module."""
        path = HERE / 'p2p_loader.py'
        module = types.ModuleType('inert_port_loader')
        module.__file__ = str(path)
        compiled = compile(path.read_bytes(), str(path), 'exec', dont_inherit=True)
        code = next(c for c in compiled.co_consts if isinstance(c, types.CodeType) and c.co_name == 'load_model')
        module.load_model = types.FunctionType(code, vars(module))
        return module

    def test_final_adapter_pin(self):
        self.assertEqual(history.ADAPTER_SHA, hashlib.sha256((HERE / 'model_adapters.py').read_bytes()).hexdigest())

    def test_final_loader_pin(self):
        self.assertEqual(split.LOADER_SHA, hashlib.sha256((HERE / 'p2p_loader.py').read_bytes()).hexdigest())

    def test_actual_loader_code_reaches_original_source_check(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'elefant/policy_model/stage3_finetune.py'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'changed inert source')
            # Passing the real file/code/namespace guards must not waive the next exact source guard.
            with self.assertRaisesRegex(ValueError, 'original_stage_source'):
                split._loader_stage(None, self.loader(), None, directory, b'pinned inert source')

    def test_foreign_loader_code_rejected(self):
        module = self.loader()
        module.load_model = types.FunctionType(compile('def load_model(): return None', module.__file__, 'exec').co_consts[0], vars(module))
        with self.assertRaisesRegex(ValueError, 'loader_code'):
            split._loader_stage(None, module, None, 'unused-source', b'')

    def test_altered_loader_file_rejected(self):
        module = self.loader()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'p2p_loader.py'
            path.write_bytes(b'altered source')
            module.__file__ = str(path)
            with self.assertRaisesRegex(ValueError, 'loader_source'):
                split._loader_stage(None, module, None, directory, b'')

    def test_foreign_adapter_path_rejected_before_model_access(self):
        runtime = history.TorchRuntime.__new__(history.TorchRuntime)
        runtime.adapter_module = types.SimpleNamespace(__file__=str(HERE / 'p2p_loader.py'))
        with self.assertRaisesRegex(FeedbackError, 'copied_adapter_source'):
            runtime.qualify(None)

    def test_qualified_sources_have_deterministic_lf_bytes(self):
        for name in ('model_adapters.py', 'p2p_loader.py'):
            raw = (HERE / name).read_bytes()
            self.assertNotIn(b'\r', raw)
            self.assertTrue(raw.endswith(b'\n'))

    def test_all_four_activation_flags_remain_false(self):
        for name in ('checkpoint_load_scope.py', 'step_application_history_owner.py',
                     'step_application_native_binding.py', 'step_application_transport.py'):
            with self.subTest(name=name):
                self.assertIs(constants(name)['AVAILABLE'], False)

    def test_qualification_and_split_bodies_unchanged(self):
        for name in ('native_history_runtime.py', 'native_action_split.py'):
            with self.subTest(name=name):
                self.assertEqual(functions(DATA / name), functions(HERE / name))

    def test_public_adapter_bodies_unchanged(self):
        old = functions(DATA / 'model_adapters.py')
        new = functions(HERE / 'model_adapters.py')
        for name in old:
            if name != 'OpenP2PAdapter.__init__':
                self.assertEqual(old[name], new[name], name)

    def test_source_location_is_caller_supplied(self):
        node = next(n for n in ast.parse((HERE / 'native_action_split.py').read_bytes()).body
                    if isinstance(n, ast.ClassDef) and n.name == 'NativeSplit')
        constructor = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
        self.assertIn('source_root', [a.arg for a in constructor.args.kwonlyargs])
        for name in ('native_action_split.py', 'native_history_runtime.py', 'checkpoint_load_scope.py',
                     'step_application_history_owner.py', 'step_application_native_binding.py'):
            self.assertNotIn('artifacts/research', (HERE / name).read_text(encoding='utf-8').replace('\\', '/'))


if __name__ == '__main__':
    unittest.main()
