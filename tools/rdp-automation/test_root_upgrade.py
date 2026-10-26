"""Inactive files and fake owned lifetimes only; every native/pipe/launcher entry is trapped."""
import contextlib
import ctypes
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

with patch.object(ctypes, 'WinDLL', side_effect=AssertionError('No native API in fixtures')):
    import rdp_control as control
    import root_upgrade as upgrade
    import test_start_host as host_fixtures


class RootUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='root-upgrade-test-')))
        self.old, old = host_fixtures.HostLauncherTests.package(self, 1)
        self.bootstrap, new = host_fixtures.HostLauncherTests.package(self, 2)
        self.target, _ = host_fixtures.HostLauncherTests.package(self, 3)
        for directory, text in ((self.old, 'root config'), (self.bootstrap, 'child config')):
            (directory / 'User/Pulonia').mkdir(parents=True)
            (directory / 'User/config.json').write_text(text)
            (directory / 'User/Pulonia/state.json').write_text('opaque retained legacy bytes')
            (directory / 'User/ExternalControl').mkdir()
            (directory / 'User/ExternalControl/enable-quest-control.json').write_text('{"version":1,"enabled":true,"allowAppRestart":true}')
        (self.target / 'User/AutoFight').mkdir(parents=True)
        self.shipped = self.target / 'User/AutoFight/shipped.txt'
        self.shipped.write_text('shipped default')
        common = dict(automationEnabled=True, uiStatus='current', taskRunning=False, runtimeRunning=False,
                      agentStreamRunning=False, pilotState='idle', automationState='idle', childWindowMinimized=True,
                      childConnectedState=1, childSessionId=3, windowMinimized=True)
        self.before = dict(common, processId=10, windowsSessionId=2, instanceNonce='old-root', instanceType='Primary',
                           remoteDesktop=False, appDirectory=str(self.old), assemblySha256=old['dllSha256'])
        self.child = dict(common, processId=20, windowsSessionId=3, instanceNonce='bootstrap', instanceType='ChildSession',
                          remoteDesktop=True, appDirectory=str(self.bootstrap), assemblySha256=new['dllSha256'],
                          rootProcessId=10, rootUpgradeVersion=1, childStartupMode='controlEndpoint', controlEndpointReady=True)
        self.after = dict(self.before, processId=30, instanceNonce='new-root', appDirectory=str(self.target),
                          puloniaSchedulingHeld=True, upgradeSessionId=3, upgradeGameProcessId=50, upgradeGameStartedFileTime=500)
        self.final_child = dict(self.child, processId=40, instanceNonce='final-child', rootProcessId=30, appDirectory=str(self.target))
        self.args = SimpleNamespace(process_id=20, windows_session_id=3, instance_nonce='bootstrap', game_process_id=50,
                                    game_started_file_time=500, target_directory=str(self.target), job_dir=str(self.root / 'result'), timeout=30)
        self.events, self.owners = [], []
        self.fail_verify = self.fail_mutation = self.fail_launch = self.fail_close = False
        self.stack.enter_context(patch.object(ctypes, 'WinDLL', side_effect=AssertionError('No native API')))
        self.stack.enter_context(patch.object(control.transport, 'WinPipeApi', side_effect=AssertionError('No pipe API')))
        self.stack.enter_context(patch.object(upgrade.subprocess, 'run', side_effect=AssertionError('No launcher process')))
        self.stack.enter_context(patch.object(control, 'exchange', side_effect=lambda *a: self.child.copy()))
        self.stack.enter_context(patch.object(control, 'resolve_child_root', return_value=self.before.copy()))
        self.stack.enter_context(patch.object(control, 'discover', return_value={'instances': [self.before, self.child], 'unavailable': []}))
        self.stack.enter_context(patch.object(control, 'refresh', side_effect=lambda value: value.copy()))
        self.stack.enter_context(patch.object(control, 'mutate', side_effect=self.mutate))
        self.stack.enter_context(patch.object(control, 'start_child', side_effect=self.start_child))

    def owner(self, pid):
        outer = self
        source, session = (self.old, 2) if pid == 10 else (self.bootstrap, 3)
        class FakeOwner:
            def __init__(self):
                self.identity = dict(processId=pid, windowsSessionId=session, startedFileTime=pid * 10,
                                     executable=str(source / 'BetterGI.exe'))
                if pid == 50:
                    self.identity.update(windowsSessionId=3, executable=str(outer.root / 'GenshinImpact.exe'))
                self.closes = 0
            def require_alive(self):
                outer.events.append(('alive', pid))
            def wait_exit(self, seconds):
                outer.events.append(('exit', pid))
            def close(self):
                self.closes += 1
                if outer.fail_close:
                    raise OSError('synthetic close uncertainty')
        value = FakeOwner()
        self.owners.append(value)
        return value

    def verify(self, target, session, timeout, output):
        self.events.append('verify-task')
        self.assertEqual(session, 2)
        if self.fail_verify:
            raise ValueError('task missing')
        return dict(approvedTaskVerified=True, windowsSessionId=2)

    def mutate(self, command, status, **fields):
        self.events.append(command)
        self.assertEqual(command, 'retireRootForUpgrade')
        upgrade.validate_root_expectation(fields['rootUpgrade'])
        if self.fail_mutation:
            raise control.ControlError('synthetic lost retirement reply')
        return status

    def launch(self, target, game, timeout, output):
        self.events.append('launch-held')
        binding = json.loads((target / 'root-upgrade-startup.json').read_text())
        self.assertEqual(binding['gameStartedFileTime'], 500)
        self.assertEqual(binding['rootSessionId'], 2)
        self.assertLess((target / 'root-upgrade-startup.json').stat().st_size, 4096)
        if self.fail_launch:
            raise ValueError('synthetic cold launch failure')
        return self.after.copy()

    def start_child(self, root, timeout, preserve_window, **options):
        self.events.append('start-endpoint')
        self.assertEqual(options['startup_mode'], 'controlEndpoint')
        self.assertFalse(preserve_window)
        options['_before_dispatch'](root)
        options['_read_root'](root)
        discovery = {'instances': [self.after, self.final_child], 'unavailable': []}
        self.assertEqual(options['_candidate'](root, discovery), self.final_child)
        return dict(root=root, child=self.final_child)

    def run_upgrade(self):
        return upgrade.upgrade_root_child(control, self.args, process_factory=self.owner,
                                          verify_launcher=self.verify, launch=self.launch)

    def test_complete_handoff_preserves_defaults_and_root_store_but_never_resumes(self):
        result = self.run_upgrade()
        self.assertTrue(result['success'], result)
        self.assertTrue(result['schedulingHeld'])
        self.assertFalse(result['workResumed'])
        self.assertFalse(result['legacyStoreCoherenceVerified'])
        self.assertEqual(self.shipped.read_text(), 'shipped default')
        self.assertEqual((self.target / 'User/config.json').read_text(), 'root config')
        self.assertEqual((self.bootstrap / 'User/config.json').read_text(), 'child config')
        self.assertEqual((self.target / 'User/Pulonia/state.json').read_bytes(), (self.old / 'User/Pulonia/state.json').read_bytes())
        self.assertLess(self.events.index('verify-task'), self.events.index('retireRootForUpgrade'))
        self.assertLess(self.events.index(('exit', 20)), self.events.index('launch-held'))
        self.assertEqual([x.closes for x in self.owners], [1, 1, 1])

    def test_missing_approved_task_never_retires(self):
        self.fail_verify = True
        result = self.run_upgrade()
        self.assertFalse(result['success'])
        self.assertFalse(result['retirementAttempted'])
        self.assertNotIn('retireRootForUpgrade', self.events)

    def test_uncertain_retirement_preserves_failure_without_stage_launch_or_retry(self):
        self.fail_mutation = True
        result = self.run_upgrade()
        self.assertFalse(result['success'])
        self.assertTrue(result['retirementAttempted'])
        self.assertEqual(self.events.count('retireRootForUpgrade'), 1)
        self.assertNotIn('launch-held', self.events)
        self.assertFalse((self.target / 'User/config.json').exists())

    def test_failed_cold_launch_retains_staging_and_pending_binding(self):
        self.fail_launch = True
        result = self.run_upgrade()
        self.assertFalse(result['success'])
        self.assertTrue(result['rootRetired'] and result['childRetired'])
        self.assertTrue((self.target / 'root-upgrade-startup.json').exists())
        self.assertNotIn('start-endpoint', self.events)

    def test_close_failure_cannot_publish_success_or_repeat_close(self):
        self.fail_close = True
        result = self.run_upgrade()
        self.assertFalse(result['success'])
        self.assertEqual(len(result['cleanupErrors']), 3)
        self.assertEqual([x.closes for x in self.owners], [1, 1, 1])

    def test_foreign_native_game_stops_before_retirement(self):
        self.args.game_started_file_time = 501
        result = self.run_upgrade()
        self.assertFalse(result['retirementAttempted'])
        self.assertNotIn('retireRootForUpgrade', self.events)

    def test_conflicting_target_config_is_preserved_and_not_overwritten(self):
        (self.target / 'User/config.json').write_text('foreign config')
        result = self.run_upgrade()
        self.assertFalse(result['success'])
        self.assertFalse(result['retirementAttempted'])
        self.assertEqual((self.target / 'User/config.json').read_text(), 'foreign config')
        self.assertNotIn('launch-held', self.events)

    def test_explicit_resume_requires_nonce_and_never_runs_as_part_of_upgrade(self):
        with self.assertRaises(control.ControlError):
            upgrade.resume_root(control, self.after, 'foreign')
        self.assertNotIn('resumeRootAfterUpgrade', self.events)

    def test_existing_startup_history_refuses_before_retirement(self):
        path = self.target / 'root-upgrade-startup.consumed.json'
        path.write_text('retained previous attempt')
        result = self.run_upgrade()
        self.assertFalse(result['retirementAttempted'])
        self.assertEqual(path.read_text(), 'retained previous attempt')

    def test_conflicting_target_store_refuses_before_retirement(self):
        path = self.target / 'User/Pulonia/state.json'
        path.parent.mkdir()
        path.write_text('different retained history')
        result = self.run_upgrade()
        self.assertFalse(result['retirementAttempted'])
        self.assertEqual(path.read_text(), 'different retained history')
        self.assertNotIn('retireRootForUpgrade', self.events)

    def test_conflicting_target_opt_in_refuses_before_retirement(self):
        path = self.target / 'User/ExternalControl/enable-quest-control.json'
        path.parent.mkdir()
        path.write_text('{"version":1,"enabled":false}')
        result = self.run_upgrade()
        self.assertFalse(result['retirementAttempted'])
        self.assertEqual(path.read_text(), '{"version":1,"enabled":false}')
        self.assertNotIn('retireRootForUpgrade', self.events)

    def test_explicit_resume_uses_same_final_child_and_reports_server_release(self):
        with patch.object(control, 'discover', return_value={'instances': [self.after, self.final_child], 'unavailable': []}), \
                patch.object(control, 'mutate', return_value=dict(self.after, puloniaSchedulingHeld=False)) as mutate:
            result = upgrade.resume_root(control, self.after, 'new-root')
        self.assertTrue(result['explicitResume'])
        self.assertFalse(result['legacyStoreCoherenceVerified'])
        mutate.assert_called_once_with('resumeRootAfterUpgrade', self.after)

    def test_explicit_resume_refuses_foreign_child_package_before_mutation(self):
        foreign = dict(self.final_child, appDirectory=str(self.bootstrap))
        with patch.object(control, 'discover', return_value={'instances': [self.after, foreign], 'unavailable': []}), \
                patch.object(control, 'mutate', side_effect=AssertionError('must not release')):
            with self.assertRaises(control.ControlError):
                upgrade.resume_root(control, self.after, 'new-root')

    def test_explicit_resume_does_not_claim_success_when_server_still_held(self):
        with patch.object(control, 'discover', return_value={'instances': [self.after, self.final_child], 'unavailable': []}), \
                patch.object(control, 'mutate', return_value=self.after):
            with self.assertRaises(control.ControlError):
                upgrade.resume_root(control, self.after, 'new-root')


if __name__ == '__main__':
    unittest.main()
