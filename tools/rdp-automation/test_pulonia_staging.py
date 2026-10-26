"""Opaque root-store staging in synthetic temporary directories; all live/native entry points are traps."""
import contextlib
import ctypes
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

with patch.object(ctypes, 'WinDLL', side_effect=AssertionError('Native calls are forbidden in staging fixtures')):
    import rdp_control as control


class PuloniaStagingTests(unittest.TestCase):
    """Each case owns its fake published packages; no active profile, endpoint or application is read."""
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='pulonia-stage-test-')))
        self.source, self.target = self.root / 'old', self.root / 'new'
        self.source.mkdir()
        self.target.mkdir()
        (self.target / 'BetterGI.exe').write_bytes(b'inert-package-marker')
        for name in ('discover', 'exchange', 'mutate', 'refresh', 'hot_replace'):
            self.stack.enter_context(patch.object(control, name, side_effect=AssertionError('Live calls are forbidden')))
        self.stack.enter_context(patch.object(control.transport, 'WinPipeApi', side_effect=AssertionError('No pipe API')))
        self.stack.enter_context(patch.object(ctypes, 'WinDLL', side_effect=AssertionError('No native API')))

    def write(self, relative, value=b'synthetic', *, target=False):
        """Create one owned source or target fixture file."""
        path = (self.target if target else self.source) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    def stage(self):
        """The explicit root-upgrade path; the test owns and quiesces both synthetic trees."""
        return control.stage_configuration(str(self.source), str(self.target),
                                           preserve_pulonia=True, source_quiescent=True)

    def assert_not_published(self):
        """Failure may not publish the root store or an acceptance report."""
        self.assertFalse((self.target / 'User/Pulonia').exists())
        self.assertFalse((self.target / 'configuration-staging.json').exists())
        self.assertEqual(list((self.target / 'User').glob('.pulonia-stage-*')), [])

    def test_default_child_staging_does_not_read_pulonia(self):
        self.write('User/Pulonia/state.json', b'private-state')
        with patch.object(control, '_pulonia_inventory', side_effect=AssertionError('Default must not inspect the store')):
            report = control.stage_configuration(str(self.source), str(self.target))
        self.assertNotIn('pulonia', report)
        self.assertFalse((self.target / 'User/Pulonia').exists())

    def test_quiescence_is_required_before_any_directory_read(self):
        for options in ({'preserve_pulonia': True}, {'source_quiescent': True},
                        {'preserve_pulonia': 1, 'source_quiescent': True}):
            with self.subTest(options=options), patch.object(control, 'local_absolute', side_effect=AssertionError('No read')):
                with self.assertRaises(control.ControlError):
                    control.stage_configuration('unused', 'unused', **options)

    def test_complete_opaque_store_keeps_state_history_backups_images_and_empty_directories(self):
        originals = {
            'state.json': b'{"schema_version":2,"uncertain_operations":[{"unknown":"keep"}]}\r\n',
            'state.json.bak': b'older-state\x00',
            'state.json.schema2.original': b'original-hold-data',
            'plans/old.json': b'{"is_expanded":false}',
            'history/plan/0123456789abcdef0123456789abcdef.json': b'{"snapshot_json":"opaque","request_id":"old"}',
            'accounts.json': b'{"image_version":null,"id":"account_original"}',
            'account-images/old.png': b'\x89PNG\r\n\x1a\n\x00\xffsynthetic-image-not-decoded',
            'plan-view-state.json': b'{}',
            '.pending.tmp': b'unknown-partial-bytes',
        }
        for name, data in originals.items():
            self.write('User/Pulonia/' + name, data)
        (self.source / 'User/Pulonia/empty/subdirectory').mkdir(parents=True)
        self.write('User/config.json', b'{"setting":"unchanged"}')
        result = self.stage()
        self.assertEqual(result['pulonia']['outcome'], 'copied')
        self.assertIs(result['pulonia']['sourceQuiescentAsserted'], True)
        self.assertIs(result['pulonia']['activeWriterSnapshotProven'], False)
        self.assertEqual(result['pulonia']['totalBytes'], sum(map(len, originals.values())))
        rows = {row['path']: row for row in result['pulonia']['files']}
        for name, data in originals.items():
            self.assertEqual((self.source / 'User/Pulonia' / name).read_bytes(), data)
            self.assertEqual((self.target / 'User/Pulonia' / name).read_bytes(), data)
            self.assertEqual(rows[name], {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        self.assertTrue((self.target / 'User/Pulonia/empty/subdirectory').is_dir())
        self.assertNotIn('unknown-partial-bytes', json.dumps(result))
        saved = json.loads(Path(result['reportFile']).read_text(encoding='utf-8'))
        self.assertEqual(saved['pulonia'], result['pulonia'])

    def test_absent_source_is_reported_without_creating_a_store(self):
        result = self.stage()
        self.assertEqual(result['pulonia']['outcome'], 'source-absent')
        self.assertFalse(result['pulonia']['present'])
        self.assertFalse((self.target / 'User/Pulonia').exists())

    def test_empty_store_presence_is_preserved(self):
        (self.source / 'User/Pulonia').mkdir(parents=True)
        result = self.stage()
        self.assertTrue(result['pulonia']['present'])
        self.assertEqual(result['pulonia']['files'], [])
        self.assertTrue((self.target / 'User/Pulonia').is_dir())

    def test_identical_target_is_retained_without_rewriting_state(self):
        self.write('User/Pulonia/state.json', b'exact-original')
        self.stage()
        path = self.target / 'User/Pulonia/state.json'
        stamp = path.stat().st_mtime_ns
        with patch.object(control, '_pulonia_file', wraps=control._pulonia_file) as read:
            result = self.stage()
        self.assertEqual(result['pulonia']['outcome'], 'retained-identical')
        self.assertTrue(all(len(call.args) < 3 for call in read.call_args_list))
        self.assertEqual(path.stat().st_mtime_ns, stamp)

    def test_different_target_store_refuses_before_copying_other_settings(self):
        self.write('User/config.json', b'new-config')
        self.write('User/Pulonia/state.json', b'source')
        existing = self.write('User/Pulonia/state.json', b'target', target=True)
        with self.assertRaisesRegex(control.ControlError, 'different User/Pulonia'):
            self.stage()
        self.assertEqual(existing.read_bytes(), b'target')
        self.assertFalse((self.target / 'User/config.json').exists())

    def test_extra_target_file_is_not_silently_merged_or_removed(self):
        self.write('User/Pulonia/state.json')
        self.write('User/Pulonia/state.json', target=True)
        extra = self.write('User/Pulonia/unresolved.tmp', b'keep', target=True)
        with self.assertRaisesRegex(control.ControlError, 'different User/Pulonia'):
            self.stage()
        self.assertEqual(extra.read_bytes(), b'keep')

    def test_source_mutation_during_copy_is_not_published(self):
        path = self.write('User/Pulonia/state.json', b'before')
        original = control._pulonia_file
        def mutate(path, expected, destination=None):
            result = original(path, expected, destination)
            if destination is not None:
                path.write_bytes(b'after!')  # Simulate an unquiesced writer inside the fixture only.
            return result
        with patch.object(control, '_pulonia_file', side_effect=mutate):
            with self.assertRaisesRegex(control.ControlError, 'inventory changed'):
                self.stage()
        self.assertEqual(path.read_bytes(), b'after!')
        self.assert_not_published()

    def test_new_source_file_during_copy_is_not_published(self):
        self.write('User/Pulonia/state.json')
        original = control._pulonia_file
        def mutate(path, expected, destination=None):
            result = original(path, expected, destination)
            if destination is not None:
                self.write('User/Pulonia/later.json', b'new')
            return result
        with patch.object(control, '_pulonia_file', side_effect=mutate):
            with self.assertRaisesRegex(control.ControlError, 'inventory changed'):
                self.stage()
        self.assert_not_published()

    def test_corrupted_private_copy_is_detected_before_publication(self):
        self.write('User/Pulonia/state.json')
        original = control._pulonia_file
        def corrupt(path, expected, destination=None):
            result = original(path, expected, destination)
            if destination is not None:
                destination.write(b'corrupt')
            return result
        with patch.object(control, '_pulonia_file', side_effect=corrupt):
            with self.assertRaisesRegex(control.ControlError, 'inventory changed'):
                self.stage()
        self.assert_not_published()

    def test_copy_failure_cleans_only_its_new_private_tree(self):
        path = self.write('User/Pulonia/state.json')
        original = control._pulonia_file
        def fail(path, expected, destination=None):
            if destination is not None:
                destination.write(b'partial')
                raise OSError('synthetic-copy-failure')
            return original(path, expected)
        with patch.object(control, '_pulonia_file', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'synthetic-copy-failure'):
                self.stage()
        self.assertEqual(path.read_bytes(), b'synthetic')
        self.assert_not_published()

    def test_late_change_is_not_accepted_and_does_not_delete_the_final_tree(self):
        source = self.write('User/Pulonia/state.json', b'before')
        rename = Path.rename
        def late(path, target):
            result = rename(path, target)
            source.write_bytes(b'after!')
            return result
        with patch.object(Path, 'rename', late):
            with self.assertRaisesRegex(control.ControlError, 'final verification changed'):
                self.stage()
        self.assertEqual((self.target / 'User/Pulonia/state.json').read_bytes(), b'before')
        self.assertFalse((self.target / 'configuration-staging.json').exists())

    def test_reparse_attribute_on_source_or_target_ancestor_is_rejected(self):
        self.write('User/Pulonia/state.json')
        self.write('User/Pulonia/state.json', target=True)
        original = Path.lstat
        for blocked in (self.source / 'User', self.source / 'User/Pulonia/state.json', self.target / 'User'):
            def reparse(path, *args, **kwargs):
                info = original(path, *args, **kwargs)
                if path == blocked:
                    return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
                return info
            with self.subTest(path=blocked), patch.object(Path, 'lstat', reparse):
                with self.assertRaisesRegex(control.ControlError, 'filesystem links'):
                    self.stage()

    def test_file_entry_and_total_caps_refuse_before_publication(self):
        self.write('User/Pulonia/a', b'ab')
        self.write('User/Pulonia/b', b'cd')
        for constant, value, message in (('PULONIA_ENTRY_LIMIT', 1, 'entry'),
                                         ('PULONIA_FILE_LIMIT', 1, 'file'),
                                         ('PULONIA_TOTAL_BYTES', 3, 'total')):
            with self.subTest(limit=constant), patch.object(control, constant, value):
                with self.assertRaisesRegex(control.ControlError, message):
                    self.stage()
            self.assert_not_published()
        self.assertEqual(control.PULONIA_FILE_LIMIT, 4096)
        self.assertEqual(control.PULONIA_FILE_BYTES, 16 * 1024 * 1024)
        self.assertEqual(control.PULONIA_TOTAL_BYTES, 256 * 1024 * 1024)

    def test_oversized_file_is_rejected_without_reading_its_payload(self):
        path = self.write('User/Pulonia/oversized')
        with path.open('wb') as stream:
            stream.truncate(control.PULONIA_FILE_BYTES + 1)
        with patch.object(control, '_pulonia_file', side_effect=AssertionError('No oversized read')):
            with self.assertRaisesRegex(control.ControlError, '16 MiB'):
                self.stage()
        self.assert_not_published()

    def test_shortened_stream_is_rejected_by_the_actual_bounded_reader(self):
        path = self.write('User/Pulonia/state.json', b'before')
        expected = path.stat()
        path.write_bytes(b'x')
        with self.assertRaisesRegex(control.ControlError, 'changed before'):
            control._pulonia_file(path, expected)

    def test_nested_installations_are_rejected(self):
        nested = self.source / 'nested'
        nested.mkdir()
        (nested / 'BetterGI.exe').write_bytes(b'fake')
        with self.assertRaisesRegex(control.ControlError, 'non-nested'):
            control.stage_configuration(str(self.source), str(nested), preserve_pulonia=True, source_quiescent=True)

    def test_cli_explicit_flags_use_file_only_staging(self):
        self.write('User/Pulonia/state.json')
        argv = ['rdp_control.py', 'stage-config', '--source-directory', str(self.source),
                '--target-directory', str(self.target), '--preserve-pulonia', '--source-quiescent']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(control.main(), 0)
        self.assertEqual(json.loads(out.getvalue())['pulonia']['outcome'], 'copied')

    def test_default_cli_keeps_the_original_call_shape(self):
        argv = ['rdp_control.py', 'stage-config', '--source-directory', str(self.source), '--target-directory', str(self.target)]
        with patch.object(sys, 'argv', argv), patch.object(control, 'stage_configuration', return_value={}) as stage, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(control.main(), 0)
        stage.assert_called_once_with(str(self.source), str(self.target))


if __name__ == '__main__':
    unittest.main()
