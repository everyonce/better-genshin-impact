"""CPU-only package identity, path relocation and historical-evidence boundaries."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import p2p_replay_forward_sequential as runner


class PackageIdentityTests(unittest.TestCase):
    """Keep the executed numerical source distinct from portable orchestration."""

    def test_validated_function_bodies_are_unchanged(self):
        folder = Path(runner.__file__).parent
        provenance = json.loads((folder/'historical-provenance.json').read_text(encoding='utf-8'))
        for filename, functions in provenance['unchangedSourceSegments'].items():
            source = (folder/filename).read_text(encoding='utf-8')
            definitions = {node.name: node for node in ast.parse(source).body
                           if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
            for name, expected in functions.items():
                with self.subTest(filename=filename, name=name):
                    text = ast.get_source_segment(source, definitions[name])
                    self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), expected)
        sequential = 'p2p_replay_sequential_sensitivity.py'
        self.assertEqual(runner.base.digest(folder/sequential)['sha256'],
                         provenance['originalSourceFiles'][sequential]['sha256'])

    def test_historical_failure_is_explicitly_not_a_current_gate(self):
        history = runner.historical_provenance()
        self.assertTrue(history['historicalOnly'])
        self.assertFalse(history['newRunValidation'])
        self.assertEqual(history['runName'], 'p2p-replay-sensitivity-run-001')
        self.assertTrue(any(not gate['passed'] for gate in history['parityGates']))

    def test_source_only_copy_imports_without_ignored_research_tree(self):
        # This new root contains tracked source only, no historical report or model.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tools = root/'tools/bettergi-agent'
            package = tools/'experiments'
            package.mkdir(parents=True)
            for name in ('p2p_replay_sensitivity.py', 'p2p_replay_sequential_sensitivity.py',
                         'p2p_replay_forward_sequential.py', 'historical-provenance.json'):
                shutil.copyfile(Path(runner.__file__).parent/name, package/name)
            for name in ('prepare_replay.py', 'prepare_replay_forward.py'):
                shutil.copyfile(runner.base.TOOLS/name, tools/name)
            command = [sys.executable, '-c',
                       'import p2p_replay_forward_sequential as r; '
                       'assert not (r.base.ROOT/"artifacts").exists(); '
                       'assert r.historical_provenance()["newRunValidation"] is False; '
                       'assert "torch" not in __import__("sys").modules; print(r.base.ROOT)']
            result = subprocess.run(command, cwd=package, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(root), result.stdout)

    def test_gpu_requires_explicit_opt_in_and_unknown_decoder_fails(self):
        args = runner.base.parse_args(['--case', 'plan.json', '2392', '--negative-control-probe', '2392',
                                       '--output', 'output'])
        self.assertFalse(args.execute_gpu)
        self.assertEqual(args.goal_artifact, [])
        self.assertEqual(args.ffmpeg, 'ffmpeg')
        with self.assertRaisesRegex(runner.base.GateFailure, 'decoder executable unavailable'):
            runner.resolve_decoder('missing-bgi-replay-decoder-3d6d17b4')


class GoalRelocationTests(unittest.TestCase):
    """A path change needs explicit byte identity and unchanged recorded metadata."""

    def fixture(self, folder):
        from goal_embedding import ENCODER, POOLING
        path = Path(folder)/'moved-goal.json'
        document = {'version': 1, 'encoder': ENCODER, 'pooling': POOLING, 'maxLength': 128,
                    'instruction': 'Walk along the open street.', 'embedding': [[1.0]*768]}
        path.write_text(json.dumps(document), encoding='utf-8')
        metadata = {key: value for key, value in document.items() if key != 'embedding'}
        metadata['file'] = 'Z:/original-machine/goal.json'
        case = {'window': {'goalProvenance': {'source': 'initialGoalState', 'goalMetadata': metadata}}}
        mapping = [metadata['file'], str(path), runner.base.digest(path)['sha256']]
        return case, path, document, mapping

    def test_explicit_mapping_preserves_original_provenance_and_new_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            case, path, _, mapping = self.fixture(folder)
            original = copy.deepcopy(case)
            relocations = runner.goal_artifact_relocations([mapping], [case])
            embedding, evidence = runner.base.load_case_goal(case, relocations)
            self.assertEqual(embedding.shape, (1, 768))
            self.assertEqual(case, original)
            self.assertEqual(evidence['provenance'], case['window']['goalProvenance'])
            self.assertEqual(evidence['fileEvidence']['path'], str(path.resolve()))
            self.assertEqual(evidence['relocation']['expectedSha256'], mapping[2])
            self.assertFalse(evidence['relocation']['recordingAttestsArtifactHash'])
            self.assertEqual(evidence['relocation']['identitySource'], 'caller-supplied-sha256')

    def test_same_metadata_with_changed_embedding_fails_original_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            case, path, document, mapping = self.fixture(folder)
            relocations = runner.goal_artifact_relocations([mapping], [case])
            document['embedding'][0][0] = 2.0
            path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(runner.base.GateFailure, 'hash mismatch'):
                runner.base.load_case_goal(case, relocations)
            with self.assertRaisesRegex(runner.base.GateFailure, 'hash mismatch'):
                runner.goal_artifact_relocations([mapping], [case])

    def test_new_digest_cannot_override_changed_recorded_instruction(self):
        with tempfile.TemporaryDirectory() as folder:
            case, path, document, mapping = self.fixture(folder)
            document['instruction'] = 'Stand still.'
            path.write_text(json.dumps(document), encoding='utf-8')
            mapping[2] = runner.base.digest(path)['sha256']
            relocations = runner.goal_artifact_relocations([mapping], [case])
            with self.assertRaisesRegex(runner.base.GateFailure, 'metadata differs'):
                runner.base.load_case_goal(case, relocations)

    def test_unknown_duplicate_missing_digest_and_no_text_remaps_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            case, _, _, mapping = self.fixture(folder)
            invalid = [([['wrong', mapping[1], mapping[2]]], [case]),
                       ([mapping, mapping], [case]), ([mapping[:2] + ['']], [case]),
                       ([mapping], [{'window': {'goalProvenance': {'goalMetadata': None}}}])]
            for entries, cases in invalid:
                with self.subTest(entries=entries), self.assertRaises(runner.base.GateFailure):
                    runner.goal_artifact_relocations(entries, cases)


if __name__ == '__main__':
    unittest.main()
