"""Synthetic releases and mocked control only: never launch an application or touch RDP."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import child_reconciliation as reconcile
import rdp_control as control
import test_start_host as host_fixtures
import test_rdp_control as transport_fixtures


class ChildReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.old_path, _ = host_fixtures.HostLauncherTests.package(self, 1)
        self.previous_path, previous_manifest = host_fixtures.HostLauncherTests.package(self, 17)
        self.target, target_manifest = host_fixtures.HostLauncherTests.package(self, 18)
        (self.target / 'BetterGI.dll').write_bytes(b'new synthetic assembly')
        target_manifest['dllSha256'] = hashlib.sha256(b'new synthetic assembly').hexdigest()
        (self.target.parent / 'build-manifest.json').write_text(json.dumps(target_manifest))
        self.old_package = reconcile.verified_package(control, self.old_path, self.root)
        self.package = reconcile.verified_package(control, self.target, self.root)
        self.stack.enter_context(patch.object(reconcile, 'LEGACY_R1_SHA256', self.old_package['dllSha256']))
        for directory in (self.old_path, self.previous_path, self.target):
            (directory / 'User').mkdir()
            (directory / 'User/config.json').write_text('{"synthetic":true}')
        self.host = {'processId': 20, 'windowsSessionId': 2, 'instanceNonce': 'root-epoch',
                     'instanceType': 'Primary', 'remoteDesktop': False, 'automationEnabled': True,
                     'appDirectory': str(self.old_path), 'assemblySha256': self.old_package['dllSha256'],
                     'automationState': 'child_launch_dispatched', 'childConnectedState': 1,
                     'childSessionId': 3, 'childWindowMinimized': True, 'taskRunning': False,
                     'runtimeRunning': False, 'pilotState': 'idle'}
        self.legacy = {**self.host, 'processId': 50, 'windowsSessionId': 3, 'instanceNonce': 'old-child',
                       'instanceType': 'ChildSession', 'remoteDesktop': True,
                       'automationState': 'game_ready', 'runtimeRunning': True}
        self.previous = {**self.legacy, 'appDirectory': str(self.previous_path),
                         'assemblySha256': previous_manifest['dllSha256'], 'uiStatus': 'current',
                         'rootProcessId': 20, 'idleRestartVersion': 2}
        self.ready = {**self.previous, 'processId': 51, 'instanceNonce': 'selected-child',
                      'appDirectory': str(self.target), 'assemblySha256': self.package['dllSha256'],
                      'rootProcessId': 20, 'uiStatus': 'current', 'agentStreamRunning': False}
        self.child = self.ready.copy()
        self.on_start = self.previous.copy()
        self.on_restart = self.ready.copy()
        self.unavailable, self.extra, self.commands = [], [], []
        self.clock = 0.0
        self.sleep_hook = None
        self.mutation_error = None
        self.restart_expectations = []
        self.start_fields = []
        self.original_exchange = control.exchange
        self.stack.enter_context(patch.object(control, 'exchange', side_effect=AssertionError('No live transport.')))
        self.stack.enter_context(patch.object(control, 'discover', side_effect=self.discover))
        self.stack.enter_context(patch.object(control, 'refresh', side_effect=self.refresh))
        self.stack.enter_context(patch.object(control, 'mutate', side_effect=self.mutate))
        self.stack.enter_context(patch.object(control.time, 'monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch.object(control.time, 'sleep', side_effect=self.sleep))

    def discover(self):
        return {'instances': [self.host.copy(), *([] if self.child is None else [self.child.copy()]), *self.extra],
                'unavailable': self.unavailable.copy()}

    def refresh(self, pinned):
        current = self.host if pinned['processId'] == self.host['processId'] else self.child
        if current is None or current['processId'] != pinned['processId'] or current['instanceNonce'] != pinned['instanceNonce']:
            raise control.ControlError('The pinned instance changed.')
        return current.copy()

    def mutate(self, command, status, **fields):
        self.commands.append(command)
        if self.mutation_error:
            raise self.mutation_error
        if command == 'startChildSession':
            self.start_fields.append(fields.copy())
            self.child = self.on_start.copy()
        elif command == 'restartApp':
            expected = fields['idleRestart']
            self.restart_expectations.append(expected.copy())
            self.assertEqual({key: expected[key] for key in self.package if key != 'version'},
                             {key: self.package[key] for key in self.package if key != 'version'})
            self.assertEqual(expected['version'], status['idleRestartVersion'])
            if expected['version'] == 2:
                self.assertIn(expected['startupMode'], ('controlEndpoint', 'gameRuntime'))
            else:
                self.assertNotIn('startupMode', expected)
            self.child = self.on_restart.copy()
        elif command == 'minimizeChildSession':
            self.host['childWindowMinimized'] = True
        elif command == 'startChildGame':
            self.child.update(automationState='game_ready', runtimeRunning=True)
        else:
            raise AssertionError(f'Unexpected mutation: {command}')
        return status.copy()

    def sleep(self, seconds):
        self.clock += seconds
        if self.sleep_hook:
            self.sleep_hook()

    def ensure(self, **kwargs):
        return reconcile.ensure_child(control, self.host.copy(), self.target,
                                      self.package['exeSha256'], self.package['dllSha256'],
                                      'root-epoch', 2, **kwargs)

    def capable_host(self):
        """Use a verified newer primary fixture capable of safely creating/reconciling an endpoint-only child."""
        self.host.update(appDirectory=str(self.previous_path), assemblySha256=self.previous['assemblySha256'],
                         uiStatus='current', childStartupIntentVersion=1, childStartupMode='controlEndpoint',
                         idleRestartVersion=2)

    def test_matching_active_child_reused_in_both_modes_without_any_mutation(self):
        self.child.update(taskRunning=True, agentStreamRunning=True, pilotState='running')
        for game in (False, True):
            result = self.ensure(start_game=game)
            self.assertTrue(result['childReady'])
            self.assertTrue(result['gameReady'])
            self.assertFalse(result['childReplaced'])
            self.assertEqual(result['readinessScope'], 'game_runtime' if game else 'selected_child_control_endpoint')
        self.assertEqual(self.commands, [])

    def test_host_control_readiness_does_not_claim_stopped_game_ready(self):
        self.child.update(automationState='stopped', runtimeRunning=False)
        result = self.ensure()
        self.assertTrue(result['childReady'])
        self.assertFalse(result['gameReady'])
        self.assertEqual(self.commands, [])

    def test_game_starts_only_the_matching_idle_child(self):
        self.child.update(automationState='stopped', runtimeRunning=False)
        self.assertTrue(self.ensure(start_game=True)['gameReady'])
        self.assertEqual(self.commands, ['startChildGame'])

    def test_capable_child_replaced_once_without_stopping_tasks_or_host(self):
        self.child = self.previous.copy()
        result = self.ensure(start_game=True)
        self.assertEqual(self.commands, ['restartApp'])
        self.assertTrue(result['childReplaced'])
        self.assertEqual(result['previousProcessId'], 50)
        self.assertEqual(result['root']['instanceNonce'], 'root-epoch')
        self.assertEqual(result['child']['rootProcessId'], 20)
        self.assertEqual(self.restart_expectations[0]['startupMode'], 'gameRuntime')

    def pinned_upgrade(self, **overrides):
        """Exercise the original-child-only path without allowing startup or profile staging."""
        options = dict(source_process_id=self.previous['processId'],source_nonce=self.previous['instanceNonce'],
                       require_existing_target_config=True,start_game=True)
        options.update(overrides)
        with patch.object(control,'start_child',side_effect=AssertionError('no bootstrap')), \
                patch.object(control,'stage_configuration',side_effect=AssertionError('no staging')):
            return self.ensure(**options)

    def test_pinned_idle_upgrade_reuses_original_and_records_only_new_config_hash(self):
        self.child = self.previous.copy()
        config = self.target/'User/config.json'
        digest = hashlib.sha256(config.read_bytes()).hexdigest()
        original = self.mutate
        def check_lease(command,status,**fields):
            if command == 'restartApp' and sys.platform == 'win32':
                with self.assertRaises(PermissionError):
                    config.unlink()
                with self.assertRaises(PermissionError):
                    config.write_bytes(b'changed while restarting')
            original(command,status,**fields)
        with patch.object(control,'mutate',side_effect=check_lease):
            result = self.pinned_upgrade(target_config_sha256=digest)
        self.assertEqual(self.commands,['restartApp'])
        self.assertFalse(result['childStartDispatched'])
        self.assertTrue(result['gameReady'])
        self.assertEqual(result['replacementEvidence']['existingTargetConfigSha256'],digest)
        config.unlink()  # Once the restart is acknowledged the application owns its new settings.

    def test_pinned_upgrade_rejects_changed_preflight_config_bytes(self):
        self.child = self.previous.copy()
        with self.assertRaisesRegex(control.ControlError,'configuration hash changed'):
            self.pinned_upgrade(target_config_sha256='a'*64)
        self.assertEqual(self.commands,[])
        self.assertFalse((self.previous_path/'User/ExternalControl').exists())

    def test_cli_retains_exact_native_game_handle_until_new_runtime_is_ready(self):
        import root_upgrade
        self.child = self.previous.copy()
        digest = hashlib.sha256((self.target/'User/config.json').read_bytes()).hexdigest()
        argv = ['rdp_control.py','ensure-child','--process-id','20','--windows-session-id','2',
                '--instance-nonce','root-epoch','--source-process-id','50','--source-nonce','old-child',
                '--require-existing-target-config','--target-config-sha256',digest,'--target-directory',str(self.target),
                '--exe-sha256',self.package['exeSha256'],'--dll-sha256',self.package['dllSha256'],'--start-game',
                '--game-process-id','77','--game-started-file-time','98765']
        for birth in (1,98765):
            self.child = self.previous.copy()
            self.commands.clear()
            out = io.StringIO()
            with patch.object(sys,'argv',argv),patch.object(control,'exchange',return_value=self.host), \
                    patch.object(root_upgrade,'OwnedProcess') as original, contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):
                held = original.return_value
                held.identity = dict(processId=77,windowsSessionId=3,startedFileTime=birth,executable='C:/game/GenshinImpact.exe')
                code = control.main()
                original.assert_called_once_with(77)
                held.close.assert_called_once_with()
            if birth == 1:
                self.assertNotEqual(code,0)
                self.assertEqual(self.commands,[])
            else:
                self.assertEqual(code,0)
                self.assertEqual(self.commands,['restartApp'])
                self.assertEqual(held.require_alive.call_count,2)
                self.assertEqual(json.loads(out.getvalue())['protectedGame'],dict(processId=77,windowsSessionId=3,
                    startedFileTime=98765,executable='GenshinImpact.exe'))

    def test_pinned_upgrade_refuses_absence_changed_owner_busy_and_missing_settings(self):
        for child,options in ((None,{}),(dict(self.previous,processId=76),{}),
                              (dict(self.previous,instanceNonce='swapped'),{}),(dict(self.previous,taskRunning=True),{}),
                              (self.previous.copy(),{'source_nonce':None}),(self.previous.copy(),{'require_existing_target_config':False})):
            self.child = child
            with self.subTest(child=child,options=options), self.assertRaises(control.ControlError):
                self.pinned_upgrade(**options)
        self.child = self.previous.copy()
        (self.target/'User/config.json').unlink()
        with self.assertRaisesRegex(control.ControlError,'must already exist'):
            self.pinned_upgrade()
        self.assertEqual(self.commands,[])
        self.assertFalse((self.previous_path/'User/ExternalControl').exists())

    def test_pinned_upgrade_rechecks_source_and_target_before_first_write(self):
        original = control.prepare_replacement
        for change in ('source','target'):
            self.child = self.previous.copy()
            def swap(*args,**kwargs):
                manifest = original(*args,**kwargs)
                if change == 'source':
                    self.child['instanceNonce'] = 'other occupant'
                else:
                    (self.target/'User/config.json').unlink()
                return manifest
            with self.subTest(change=change), patch.object(control,'prepare_replacement',side_effect=swap), \
                    self.assertRaises(control.ControlError):
                self.pinned_upgrade()
            self.assertEqual(self.commands,[])
            self.assertFalse((self.previous_path/'User/ExternalControl').exists())

    def test_host_replacement_is_endpoint_only_even_when_no_runtime_was_started(self):
        self.child = {**self.previous, 'automationState': 'stopped', 'runtimeRunning': False}
        self.on_restart = {**self.ready, 'automationState': 'idle', 'runtimeRunning': False}
        result = self.ensure()
        self.assertEqual(self.commands, ['restartApp'])
        self.assertEqual(self.restart_expectations, [{**self.package, 'version': 2, 'startupMode': 'controlEndpoint'}])
        self.assertTrue(result['childReady'])
        self.assertTrue(result['childReplaced'])
        self.assertFalse(result['gameReady'])
        self.assertEqual(result['readinessScope'], 'selected_child_control_endpoint')
        # The shared manifest still binds only the target; intent is in the pinned request.
        manifest = self.previous_path / 'User/ExternalControl/pending-restart.json'
        self.assertEqual(json.loads(manifest.read_text()), self.package)

    def test_host_v1_fails_before_staging_or_any_restart_files(self):
        self.child = {**self.previous, 'idleRestartVersion': 1}
        (self.target / 'User/config.json').unlink()
        with patch.object(control, 'stage_configuration', side_effect=AssertionError('no staging')):
            with self.assertRaisesRegex(control.ControlError, 'endpoint-only startup'):
                self.ensure()
        self.assertEqual(self.commands, [])
        self.assertFalse((self.target / 'User/config.json').exists())
        self.assertFalse((self.previous_path / 'User/ExternalControl').exists())

    def test_game_upgrade_keeps_v1_compatibility_without_endpoint_downgrade(self):
        self.child = {**self.previous, 'idleRestartVersion': 1}
        result = self.ensure(start_game=True)
        self.assertTrue(result['gameReady'])
        self.assertEqual(self.commands, ['restartApp'])
        self.assertEqual(self.restart_expectations, [self.package])

    def test_host_capability_downgrade_at_final_preflight_does_not_dispatch(self):
        self.child = self.previous.copy()
        original = control.enable_restart
        def changed(*args):
            original(*args)
            self.child['idleRestartVersion'] = 1
        with patch.object(control, 'enable_restart', side_effect=changed):
            with self.assertRaisesRegex(control.ControlError, 'endpoint-only startup'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_host_replacement_does_not_claim_an_incomplete_or_unknown_lifecycle(self):
        for state in ('starting_game', 'changing_capture', 'unresponsive', 'unknown'):
            self.child = self.previous.copy()
            self.on_restart = {**self.ready, 'automationState': state, 'runtimeRunning': False}
            self.commands = []
            with self.subTest(state=state), self.assertRaises(control.ControlError):
                self.ensure()
            self.assertEqual(self.commands, ['restartApp'])

    def test_legacy_without_atomic_capability_fails_before_settings_or_manifest_writes(self):
        self.child = self.legacy.copy()
        (self.target / 'User/config.json').unlink()
        with patch.object(control, 'stage_configuration', side_effect=AssertionError('no staging')):
            with self.assertRaisesRegex(control.ControlError, 'controlled explicit hot-replace'):
                self.ensure()
        self.assertFalse((self.old_path / 'User/ExternalControl/pending-restart.json').exists())
        self.assertFalse((self.target / 'User/config.json').exists())
        self.assertEqual(self.commands, [])

    def test_capability_must_be_exact_version_integer(self):
        for capability in (None, False, True, '1', '2', 0, 3):
            self.child = {**self.previous, 'idleRestartVersion': capability}
            with self.subTest(capability=capability), self.assertRaisesRegex(control.ControlError, 'atomic idle-restart'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_old_host_bootstrap_does_not_implicitly_authorize_nonatomic_upgrade(self):
        self.child = None
        self.on_start = self.legacy.copy()
        with self.assertRaisesRegex(control.ControlError, 'childStartupIntentVersion 1'):
            self.ensure()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.host['processId'], 20)

    def test_lost_capability_at_final_preflight_prevents_dispatch(self):
        self.child = self.previous.copy()
        original = control.enable_restart
        def changed(*args):
            original(*args)
            self.child.pop('idleRestartVersion')
        with patch.object(control, 'enable_restart', side_effect=changed):
            with self.assertRaisesRegex(control.ControlError, 'atomic idle-restart'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_atomic_restart_wire_binds_package_and_legacy_omission_stays_unchanged(self):
        api = transport_fixtures.FakePipe()
        self.original_exchange('restartApp', 123, 2, nonce='instance-a', api=api,
                               fields={'idleRestart': self.package})
        self.assertEqual(api.request['idleRestart'], self.package)
        self.original_exchange('restartApp', 123, 2, nonce='instance-a', api=api)
        self.assertNotIn('idleRestart', api.request)

    def test_v2_wire_keeps_explicit_startup_intent(self):
        for mode in ('controlEndpoint', 'gameRuntime'):
            api = transport_fixtures.FakePipe()
            expected = {**self.package, 'version': 2, 'startupMode': mode}
            self.original_exchange('restartApp', 123, 2, nonce='instance-a', api=api,
                                   fields={'idleRestart': expected})
            self.assertEqual(api.request['idleRestart'], expected)

    def test_invalid_atomic_restart_wire_fails_before_connect(self):
        invalid = [None, {**self.package, 'version': True}, {**self.package, 'version': 2},
                   {**self.package, 'startupMode': 'controlEndpoint'},
                   *({**self.package, 'version': 2, 'startupMode': mode}
                     for mode in (None, False, 'ControlEndpoint', 'unknown', [])),
                   {**self.package, 'targetDirectory': None}, {**self.package, 'targetDirectory': 'relative'},
                   {**self.package, 'dllSha256': 'wrong'}, {**self.package, 'extra': True}]
        for expected in invalid:
            api = transport_fixtures.FakePipe()
            with self.subTest(expected=expected), self.assertRaises(control.ControlError):
                self.original_exchange('restartApp', 123, 2, nonce='instance-a', api=api,
                                       fields={'idleRestart': expected})
            self.assertEqual(api.written, [])

    def test_missing_child_bootstraps_capable_package_then_reconciles_once(self):
        self.capable_host()
        self.child = None
        result = self.ensure()
        self.assertEqual(self.commands, ['startChildSession', 'restartApp'])
        self.assertTrue(result['childStartDispatched'])
        self.assertTrue(result['childReplaced'])
        self.assertEqual(self.start_fields, [{'childStartupMode': 'controlEndpoint'}])

    def test_active_launch_is_joined_and_never_replayed(self):
        self.capable_host()
        self.child = None
        self.host['automationState'] = 'launching_child'
        def finish_launch():
            self.host['automationState'] = 'child_launch_dispatched'
            self.child = self.ready.copy()
        self.sleep_hook = finish_launch
        self.assertTrue(self.ensure()['childReady'])
        self.assertEqual(self.commands, [])

    def test_uncertain_start_is_never_replayed(self):
        self.capable_host()
        self.child = None
        self.mutation_error = control.ControlError('response lost')
        with self.assertRaisesRegex(control.ControlError, 'response lost'):
            self.ensure()
        self.assertEqual(self.commands, ['startChildSession'])

    def test_game_joins_endpoint_bootstrap_then_explicitly_starts_selected_child(self):
        self.capable_host()
        self.child = None
        self.host['automationState'] = 'launching_child'
        def finish_launch():
            self.host['automationState'] = 'child_launch_dispatched'
            self.child = {**self.ready, 'automationState': 'idle', 'runtimeRunning': False}
        self.sleep_hook = finish_launch
        result = self.ensure(start_game=True)
        self.assertTrue(result['gameReady'])
        self.assertEqual(self.commands, ['startChildGame'])

    def test_selected_game_refuses_unupgradeable_old_bootstrap_before_dispatch(self):
        self.child = None
        with self.assertRaisesRegex(control.ControlError, 'atomic idle-restart'):
            self.ensure(start_game=True)
        self.assertEqual(self.commands, [])

    def test_newer_verified_child_is_not_downgraded_to_older_selected_release(self):
        older = reconcile.verified_package(control, self.previous_path, self.root)
        with self.assertRaisesRegex(control.ControlError, 'no downgrade'):
            reconcile.ensure_child(control, self.host.copy(), self.previous_path,
                                   older['exeSha256'], older['dllSha256'], 'root-epoch', 2)
        self.assertEqual(self.commands, [])

    def test_missing_child_with_newer_primary_refuses_older_selection_before_dispatch(self):
        self.capable_host()
        self.host.update(appDirectory=str(self.target), assemblySha256=self.package['dllSha256'])
        self.child = None
        older = reconcile.verified_package(control, self.previous_path, self.root)
        with self.assertRaisesRegex(control.ControlError, 'no downgrade'):
            reconcile.ensure_child(control, self.host.copy(), self.previous_path,
                                   older['exeSha256'], older['dllSha256'], 'root-epoch', 2)
        self.assertEqual(self.commands, [])

    def test_uncertain_restart_is_never_replayed(self):
        self.child = self.previous.copy()
        self.mutation_error = control.ControlError('restart response lost')
        with self.assertRaisesRegex(control.ControlError, 'restart response lost'):
            self.ensure()
        self.assertEqual(self.commands, ['restartApp'])

    def test_missing_or_busy_idle_fields_never_trigger_stop_or_restart(self):
        cases = [('taskRunning', True), ('taskRunning', None), ('pilotState', None),
                 ('automationState', None), ('automationState', 'stopping'), ('agentStreamRunning', True)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.child = {**self.previous, key: value}
                with self.assertRaisesRegex(control.ControlError, 'busy|unknown'):
                    self.ensure()
        self.assertEqual(self.commands, [])

    def test_known_legacy_ui_omission_requires_exact_verified_assembly(self):
        self.child = {**self.ready}
        del self.child['uiStatus']
        with self.assertRaisesRegex(control.ControlError, 'UI status'):
            self.ensure()
        self.child = {**self.legacy, 'uiStatus': 'unresponsive'}
        with self.assertRaisesRegex(control.ControlError, 'UI status'):
            self.ensure()
        self.assertEqual(self.commands, [])

    def test_legacy_missing_backlink_is_upgrade_only_never_matching_ready(self):
        self.child = self.legacy.copy()
        with self.assertRaisesRegex(control.ControlError, 'only be upgraded'):
            reconcile.ensure_child(control, self.host.copy(), self.old_path,
                                   self.old_package['exeSha256'], self.old_package['dllSha256'],
                                   'root-epoch', 2)
        self.assertEqual(self.commands, [])

    def test_wrong_backlink_non_rdp_duplicate_and_unavailable_are_not_absence(self):
        for modification in ({'rootProcessId': 999}, {'remoteDesktop': False}):
            with self.subTest(modification=modification):
                self.child = {**self.ready, **modification}
                with self.assertRaises(control.ControlError):
                    self.ensure()
        self.child = self.ready.copy()
        self.extra = [self.child.copy()]
        with self.assertRaisesRegex(control.ControlError, 'Multiple'):
            self.ensure()
        self.extra = []
        for unavailable in ([{'error': 'Discovery reached its time limit'}], [{'windowsSessionId': 3}]):
            self.unavailable = unavailable
            with self.assertRaisesRegex(control.ControlError, 'unavailable'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_legacy_fallback_rejects_another_connected_primary(self):
        self.child = self.previous.copy()
        self.extra = [{**self.host, 'processId': 22, 'instanceNonce': 'other-root'}]
        with self.assertRaisesRegex(control.ControlError, 'exactly one'):
            self.ensure()
        self.assertEqual(self.commands, [])

    def test_wrapper_nonce_cannot_be_rebound_to_a_new_primary_epoch(self):
        self.host['instanceNonce'] = 'new-root'
        with self.assertRaisesRegex(control.ControlError, 'nonce'):
            self.ensure()
        self.assertEqual(self.commands, [])

    def test_racing_server_busy_response_never_stops_the_winning_task(self):
        self.child = self.previous.copy()
        self.mutation_error = control.ControlError('busy: task won the race')
        with self.assertRaisesRegex(control.ControlError, 'busy'):
            self.ensure()
        self.assertEqual(self.commands, ['restartApp'])

    def test_bad_replacement_identity_fails_after_one_dispatch(self):
        cases = ({'rootProcessId': None}, {'rootProcessId': 999},
                 {'instanceNonce': 'old-child'}, {'assemblySha256': '0' * 64},
                 {'appDirectory': str(self.old_path)})
        for change in cases:
            with self.subTest(change=change):
                self.child, self.commands = self.previous.copy(), []
                self.on_restart = {**self.ready, **change}
                with self.assertRaises(control.ControlError):
                    self.ensure()
                self.assertEqual(self.commands, ['restartApp'])

    def test_partial_replacement_game_attachment_waits_for_complete_lifecycle(self):
        self.child = self.previous.copy()
        self.on_restart = {**self.ready, 'automationState': 'starting_game'}
        self.sleep_hook = lambda: self.child.update(automationState='game_ready')
        result = self.ensure(start_game=True)
        self.assertGreater(self.clock, 0)
        self.assertTrue(result['gameReady'])
        self.assertEqual(self.commands, ['restartApp'])

    def test_failed_replacement_runtime_never_reports_success(self):
        self.child = self.previous.copy()
        self.on_restart = {**self.ready, 'automationState': 'failed', 'automationError': 'fixture failure'}
        with self.assertRaisesRegex(control.ControlError, 'fixture failure'):
            self.ensure()
        self.assertEqual(self.commands, ['restartApp'])

    def test_wait_for_old_automatic_game_start_has_original_deadline(self):
        self.child = {**self.previous, 'automationState': 'starting_game', 'taskRunning': True}
        with self.assertRaisesRegex(control.ControlError, 'timed out'):
            self.ensure()
        self.assertEqual(self.commands, [])

    def test_target_hash_change_after_selection_fails_before_restart(self):
        self.child = self.previous.copy()
        with patch.object(reconcile, '_target_settings', side_effect=lambda *_:
                          (self.target / 'BetterGI.dll').write_bytes(b'changed')):
            with self.assertRaisesRegex(control.ControlError, 'hash'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_existing_target_settings_are_retained_not_replaced_by_legacy_settings(self):
        self.child = self.previous.copy()
        (self.previous_path / 'User/config.json').write_text('{"old":true}')
        (self.target / 'User/config.json').write_text('{"new":true}')
        self.ensure()
        self.assertEqual((self.target / 'User/config.json').read_text(), '{"new":true}')

    def test_absent_target_settings_use_existing_staging_before_restart(self):
        self.child = self.previous.copy()
        (self.target / 'User/config.json').unlink()
        self.ensure()
        self.assertEqual((self.target / 'User/config.json').read_text(), '{"synthetic":true}')
        self.assertTrue((self.target / 'configuration-staging.json').exists())

    def test_default_minimizes_but_preserve_window_leaves_it_shown(self):
        self.host['childWindowMinimized'] = False
        self.assertEqual(self.ensure(preserve_window=True)['windowPolicy'], 'preserve_existing')
        self.assertEqual(self.commands, [])
        self.assertEqual(self.ensure()['windowPolicy'], 'minimized')
        self.assertEqual(self.commands, ['minimizeChildSession'])

    def test_newer_release_does_not_change_invocation_selected_target(self):
        host_fixtures.HostLauncherTests.package(self, 19)
        result = self.ensure()
        self.assertEqual(result['selectedPackage'], self.package)
        self.assertEqual(self.commands, [])

    def test_cli_preserves_exact_root_nonce_target_hashes_and_game_mode(self):
        arguments = ['rdp_control.py', 'ensure-child', '--process-id', '20', '--windows-session-id', '2',
                     '--instance-nonce', 'root-epoch', '--target-directory', str(self.target),
                     '--exe-sha256', self.package['exeSha256'], '--dll-sha256', self.package['dllSha256'],
                     '--start-game', '--preserve-window']
        with patch.object(sys, 'argv', arguments), patch.object(control, 'exchange', return_value=self.host), \
                patch.object(reconcile, 'ensure_child', return_value={'success': True}) as ensure, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(control.main(), 0)
        self.assertEqual(ensure.call_args.args[-4:], ('root-epoch', 120, True, True))

    def test_idle_state_changed_before_restart_is_rejected_without_stop(self):
        self.child = self.previous.copy()
        original = control.enable_restart
        def became_busy(*args):
            original(*args)
            self.child.update(taskRunning=True)
        with patch.object(control, 'enable_restart', side_effect=became_busy):
            with self.assertRaisesRegex(control.ControlError, 'busy'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_configuration_staging_conflict_prevents_restart(self):
        self.child = self.previous.copy()
        (self.target / 'User/config.json').unlink()
        with patch.object(control, 'stage_configuration', side_effect=control.ControlError('staging conflict')):
            with self.assertRaisesRegex(control.ControlError, 'staging conflict'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_other_connected_root_cannot_replace_pinned_legacy_resolution(self):
        self.child = self.previous.copy()
        with patch.object(control, 'resolve_child_root', return_value={**self.host, 'instanceNonce': 'other'}):
            with self.assertRaisesRegex(control.ControlError, 'identity'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_root_disconnect_after_dispatch_never_reports_ready(self):
        self.child = self.previous.copy()
        original = self.mutate
        def disconnect(command, status, **fields):
            answer = original(command, status, **fields)
            if command == 'restartApp':
                self.host['childConnectedState'] = 0
            return answer
        with patch.object(control, 'mutate', side_effect=disconnect):
            with self.assertRaisesRegex(control.ControlError, 'not connected'):
                self.ensure()
        self.assertEqual(self.commands, ['restartApp'])

    def test_retiring_old_endpoint_unavailable_is_the_only_post_dispatch_exception(self):
        self.child = self.previous.copy()
        original = self.mutate
        def old_pipe_closed(command, status, **fields):
            answer = original(command, status, **fields)
            if command == 'restartApp':
                self.unavailable = [{'processId': 50, 'windowsSessionId': 3}]
            return answer
        # Final discovery must be complete again: the old process has exited.
        original_discover = self.discover
        def discovery():
            result = original_discover()
            if self.child and self.child['processId'] == 51:
                self.unavailable = []
            return result
        with patch.object(control, 'mutate', side_effect=old_pipe_closed), \
                patch.object(control, 'discover', side_effect=discovery):
            self.assertTrue(self.ensure()['childReady'])
        self.assertEqual(self.commands, ['restartApp'])

    def test_incomplete_post_dispatch_discovery_never_reports_ready(self):
        self.child = self.previous.copy()
        original = self.mutate
        def incomplete(command, status, **fields):
            answer = original(command, status, **fields)
            if command == 'restartApp':
                self.unavailable = [{'error': 'Discovery reached its time limit'}]
            return answer
        with patch.object(control, 'mutate', side_effect=incomplete):
            with self.assertRaisesRegex(control.ControlError, 'unavailable'):
                self.ensure()
        self.assertEqual(self.commands, ['restartApp'])

    def test_post_restart_degraded_ui_waits_then_reuses_same_authenticated_replacement(self):
        self.child = self.previous.copy()
        self.on_restart.update(uiStatus='timeout', automationState='unresponsive', runtimeRunning=False, taskRunning=True)
        self.sleep_hook = lambda: self.child.update(self.ready)
        result = self.ensure(start_game=True)
        self.assertTrue(result['childReady'])
        self.assertGreaterEqual(self.clock, .5)
        self.assertEqual(self.commands, ['restartApp'])

    def test_post_restart_unavailable_endpoint_must_resolve_even_outside_child_session(self):
        for unavailable in ([{'processId': 51, 'windowsSessionId': 3}],
                            [{'processId': 99, 'windowsSessionId': 4}],
                            [{'error': 'Discovery reached its time limit'}]):
            with self.subTest(unavailable=unavailable):
                self.child, self.commands, self.clock = self.previous.copy(), [], 0
                original = self.mutate
                def incomplete(command, status, **fields):
                    result = original(command, status, **fields)
                    if command == 'restartApp':
                        self.unavailable = unavailable
                    return result
                self.sleep_hook = lambda: self.unavailable.clear()
                with patch.object(control, 'mutate', side_effect=incomplete):
                    self.assertTrue(self.ensure()['childReady'])
                self.assertGreaterEqual(self.clock, .5)
                self.assertEqual(self.commands, ['restartApp'])

    def test_post_restart_retiring_child_must_disappear_before_success(self):
        self.child = self.previous.copy()
        original = self.mutate
        def retiring(command, status, **fields):
            result = original(command, status, **fields)
            if command == 'restartApp':
                self.extra = [self.previous.copy()]
            return result
        self.sleep_hook = lambda: self.extra.clear()
        with patch.object(control, 'mutate', side_effect=retiring):
            self.assertTrue(self.ensure()['childReady'])
        self.assertGreaterEqual(self.clock, .5)
        self.assertEqual(self.commands, ['restartApp'])

    def test_unready_replacement_epoch_cannot_switch_before_becoming_ready(self):
        self.child = self.previous.copy()
        self.on_restart.update(uiStatus='timeout', automationState='unresponsive')
        self.sleep_hook = lambda: self.child.update(self.ready, instanceNonce='another-epoch')
        with self.assertRaisesRegex(control.ReplacementError, 'epoch changed') as failure:
            self.ensure()
        self.assertTrue(failure.exception.evidence['restartAcknowledged'])
        self.assertEqual(failure.exception.evidence['phase'], 'replacement_readiness')
        self.assertEqual(self.commands, ['restartApp'])

    def test_incomplete_discovery_does_not_hide_known_wrong_replacement_hash(self):
        self.child = self.previous.copy()
        self.on_restart['assemblySha256'] = '0' * 64
        original = self.mutate
        def wrong(command, status, **fields):
            result = original(command, status, **fields)
            if command == 'restartApp':
                self.unavailable = [{'error': 'incomplete'}]
            return result
        with patch.object(control, 'mutate', side_effect=wrong):
            with self.assertRaisesRegex(control.ReplacementError, 'different child'):
                self.ensure()
        self.assertEqual(self.clock, 0)
        self.assertEqual(self.commands, ['restartApp'])

    def test_lost_restart_ack_preserves_phase_and_never_polls_or_replays(self):
        self.child = self.previous.copy()
        self.mutation_error = control.ControlError('restart response lost')
        with self.assertRaisesRegex(control.ReplacementError, 'response lost') as failure:
            self.ensure()
        evidence = failure.exception.evidence
        self.assertEqual(evidence['phase'], 'restart_request')
        self.assertTrue(evidence['restartRequestAttempted'])
        self.assertFalse(evidence['restartAcknowledged'])
        self.assertEqual(evidence['readinessPolls'], 0)
        self.assertEqual(self.commands, ['restartApp'])

    def test_status_poll_cannot_return_ready_after_original_deadline(self):
        self.child = self.previous.copy()
        original = self.discover
        def delayed():
            result = original()
            if self.child and self.child['processId'] == self.ready['processId']:
                self.clock += 3
            return result
        with patch.object(control, 'discover', side_effect=delayed):
            with self.assertRaisesRegex(control.ReplacementError, 'deadline elapsed') as failure:
                self.ensure()
        self.assertTrue(failure.exception.evidence['restartAcknowledged'])
        self.assertEqual(self.commands, ['restartApp'])

    def test_cli_serializes_replacement_failure_phase_and_ack_without_losing_message(self):
        arguments = ['rdp_control.py', 'ensure-child', '--process-id', '20', '--windows-session-id', '2',
                     '--instance-nonce', 'root-epoch', '--target-directory', str(self.target),
                     '--exe-sha256', self.package['exeSha256'], '--dll-sha256', self.package['dllSha256']]
        evidence = {'phase': 'replacement_readiness', 'restartRequestAttempted': True,
                    'restartAcknowledged': True, 'readinessPolls': 2}
        output = io.StringIO()
        with patch.object(sys, 'argv', arguments), patch.object(control, 'exchange', return_value=self.host), \
                patch.object(reconcile, 'ensure_child', side_effect=control.ReplacementError('fixture status gap', evidence)), \
                contextlib.redirect_stderr(output):
            self.assertEqual(control.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {'success': False, 'error': 'fixture status gap',
                                                        'replacementEvidence': evidence})

    def test_pinned_target_deadline_expiry_during_preflight_prevents_dispatch(self):
        self.child = self.previous.copy()
        original = control.enable_restart
        def slow_preflight(*args):
            original(*args)
            self.clock += 3
        with patch.object(control, 'enable_restart', side_effect=slow_preflight):
            with self.assertRaisesRegex(control.ControlError, 'deadline expired'):
                self.ensure()
        self.assertEqual(self.commands, [])

    def test_incomplete_independent_root_discovery_prevents_legacy_upgrade(self):
        self.child = self.previous.copy()
        calls = 0
        original = self.discover
        def discovery():
            nonlocal calls
            calls += 1
            result = original()
            if calls > 1:
                result['unavailable'] = [{'processId': 99, 'windowsSessionId': 4}]
            return result
        with patch.object(control, 'discover', side_effect=discovery):
            with self.assertRaisesRegex(control.ControlError, 'discovery is incomplete'):
                self.ensure()
        self.assertEqual(self.commands, [])


if __name__ == '__main__':
    unittest.main()
