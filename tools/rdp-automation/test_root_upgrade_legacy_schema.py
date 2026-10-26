"""Portable scalar admission regressions; no real package, User data or endpoint access."""
import contextlib
import copy
import ctypes
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

with patch.object(ctypes, 'WinDLL', create=True, side_effect=AssertionError('No native API in fixtures')):
    import rdp_control as control
    import root_upgrade as upgrade
    import child_reconciliation as reconcile


class RootUpgradeLegacySchemaTests(unittest.TestCase):
    """Run real admission/helper bodies while replacing only the package-I/O boundary."""

    def setUp(self):
        """Use an unopened repository-relative synthetic path and trap all operational entry points."""
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(__file__).resolve().parent / 'synthetic-no-io' / 'release-r1' / 'BetterGI-English-win-x64'
        self.root = dict(processId=10, windowsSessionId=2, instanceNonce='synthetic-root',
                         instanceType='Primary', remoteDesktop=False, automationEnabled=True,
                         appDirectory=str(self.directory), assemblySha256=reconcile.LEGACY_R1_SHA256,
                         taskRunning=False, runtimeRunning=False, pilotState='idle', automationState='idle')
        self.package_hash = reconcile.LEGACY_R1_SHA256
        self.package_error = None
        self.package_calls = []
        self.stack.enter_context(patch.object(reconcile, 'verified_package', side_effect=self.package))
        for owner, name in ((ctypes, 'WinDLL'), (subprocess, 'Popen'), (socket, 'socket'),
                            (upgrade, 'OwnedProcess'), (upgrade, '_launcher'),
                            (control.transport, 'WinPipeApi'), (control, 'exchange'),
                            (control, 'discover'), (control, 'refresh'), (control, 'mutate'),
                            (control, 'start_child')):
            self.stack.enter_context(patch.object(owner, name, create=True,
                                                 side_effect=AssertionError('No operational call: ' + name)))

    def package(self, actual_control, directory, releases):
        """Record the real verifier's arguments and model its success/failure without opening paths."""
        self.package_calls.append((actual_control, Path(directory), Path(releases)))
        if self.package_error is not None:
            raise self.package_error
        return dict(targetDirectory=str(directory), dllSha256=self.package_hash)

    def child(self):
        """A scalar child is explicitly idle and endpoint-ready until a test removes evidence."""
        return dict(self.root, instanceType='ChildSession', remoteDesktop=True, uiStatus='current',
                    instanceNonce='synthetic-child', windowsSessionId=3, agentStreamRunning=False)

    def test_exact_verified_legacy_primary_accepts_omission_without_mutating_status(self):
        """The known hash and release name alone are insufficient until the package join succeeds."""
        self.assertEqual(reconcile.LEGACY_R1_SHA256,
                         '7f611984b27be839d1f3d9ee17c8b75383f6708367ff1533420c7d7bc4920a0d')
        before = copy.deepcopy(self.root)
        self.assertIs(upgrade._idle(control, self.root, child=False), self.root)
        self.assertEqual(self.root, before)
        self.assertNotIn('agentStreamRunning', self.root)
        self.assertEqual(self.package_calls, [(control, self.directory, self.directory.parent.parent)])

    def test_legacy_with_explicit_current_ui_and_terminal_pilot_still_requires_verification(self):
        """All existing accepted terminal pilot states use the same exact package boundary."""
        for pilot in ('idle', 'completed', 'failed', 'cancelled'):
            with self.subTest(pilot=pilot):
                status = dict(self.root, uiStatus='current', pilotState=pilot)
                self.assertIs(upgrade._idle(control, status, child=False), status)
        self.assertEqual(len(self.package_calls), 4)

    def test_package_verification_failure_propagates_without_accepting_legacy_hash(self):
        """An on-disk verification failure cannot be converted into a schema exception."""
        self.package_error = control.ControlError('synthetic manifest verification failure')
        with self.assertRaises(control.ControlError) as caught:
            upgrade._idle(control, self.root, child=False)
        self.assertIs(caught.exception, self.package_error)
        self.assertEqual(len(self.package_calls), 1)

    def test_package_hash_must_equal_reported_loaded_assembly(self):
        """The real _verified_status rejects a different verified on-disk binary."""
        self.package_hash = 'a' * 64
        with self.assertRaisesRegex(control.ControlError, 'process assembly'):
            upgrade._idle(control, self.root, child=False)
        self.assertEqual(len(self.package_calls), 1)

    def test_repeat_idle_admission_revalidates_package_instead_of_caching_success(self):
        """A changed disk result on the next boundary is rejected with the original status retained."""
        upgrade._idle(control, self.root, child=False)
        self.package_hash = 'b' * 64
        with self.assertRaises(control.ControlError):
            upgrade._idle(control, self.root, child=False)
        self.assertEqual(len(self.package_calls), 2)
        self.assertNotIn('agentStreamRunning', self.root)

    def test_current_or_unknown_verified_primary_cannot_omit_stream_evidence(self):
        """A matching verified package is not permission to generalize the R1 schema exception."""
        for digest in ('a' * 64, '0' * 64):
            with self.subTest(digest=digest):
                self.package_hash = digest
                status = dict(self.root, uiStatus='current', assemblySha256=digest)
                with self.assertRaises(control.ControlError):
                    upgrade._idle(control, status, child=False)
        self.assertEqual(len(self.package_calls), 2)

    def test_legacy_hash_at_another_release_name_is_not_legacy(self):
        """Keep the real _legacy path/hash conjunction rather than a hash-only exemption."""
        status = dict(self.root, uiStatus='current', appDirectory=str(
            self.directory.parent.parent / 'release-r2' / self.directory.name))
        with self.assertRaises(control.ControlError):
            upgrade._idle(control, status, child=False)
        self.assertEqual(len(self.package_calls), 1)

    def test_child_omission_is_rejected_for_legacy_and_current_hashes(self):
        """Every child retains explicit stream-idle evidence regardless of its reported build."""
        for digest in (reconcile.LEGACY_R1_SHA256, 'a' * 64):
            status = dict(self.child(), assemblySha256=digest)
            del status['agentStreamRunning']
            with self.subTest(digest=digest), self.assertRaises(control.ControlError):
                upgrade._idle(control, status, child=True)
        self.assertEqual(self.package_calls, [])

    def test_explicit_nonfalse_stream_evidence_never_uses_omission_compatibility(self):
        """Null, true and coerced false values remain unsafe rather than being treated as absence."""
        for value in (None, True, 0, 1, 'false', [], {}):
            with self.subTest(value=value), self.assertRaises(control.ControlError):
                upgrade._idle(control, dict(self.root, agentStreamRunning=value), child=False)
        self.assertEqual(self.package_calls, [])

    def test_missing_or_nonfalse_task_and_runtime_evidence_is_rejected(self):
        """The legacy stream omission does not weaken independent activity predicates."""
        for field in ('taskRunning', 'runtimeRunning'):
            for missing, value in [(True, None), *[(False, x) for x in (None, True, 0, 'false')]]:
                status = dict(self.root)
                if missing:
                    status.pop(field)
                else:
                    status[field] = value
                with self.subTest(field=field, missing=missing, value=value), self.assertRaises(control.ControlError):
                    upgrade._idle(control, status, child=False)

    def test_missing_or_unknown_pilot_state_remains_rejected(self):
        """No missing or active pilot ownership may be interpreted as detached idle."""
        for missing, value in [(True, None), (False, None), (False, 'running'), (False, 'unknown'), (False, 0)]:
            status = dict(self.root)
            if missing:
                status.pop('pilotState')
            else:
                status['pilotState'] = value
            with self.subTest(missing=missing, value=value), self.assertRaises(control.ControlError):
                upgrade._idle(control, status, child=False)

    def test_missing_or_nonfalse_remote_desktop_cannot_claim_legacy_primary(self):
        """The compatibility branch requires an explicit non-RDP primary."""
        for missing, value in [(True, None), *[(False, x) for x in (None, True, 0, 'false')]]:
            status = dict(self.root)
            if missing:
                status.pop('remoteDesktop')
            else:
                status['remoteDesktop'] = value
            with self.subTest(missing=missing, value=value), self.assertRaises(control.ControlError):
                upgrade._idle(control, status, child=False)
        self.assertEqual(self.package_calls, [])

    def test_explicit_degraded_ui_is_not_overridden_by_known_legacy_bytes(self):
        """The unchanged current-UI predicate wins before package compatibility is considered."""
        for value in (None, 'stale', 'unresponsive', False):
            with self.subTest(value=value), self.assertRaises(control.ControlError):
                upgrade._idle(control, dict(self.root, uiStatus=value), child=False)
        self.assertEqual(self.package_calls, [])

    def test_role_automation_and_nonce_requirements_precede_package_verification(self):
        """Authenticated role prerequisites retain their exact types and nonempty nonce."""
        for field, value in (('instanceType', 'ChildSession'), ('instanceType', None),
                             ('automationEnabled', False), ('automationEnabled', 1),
                             ('instanceNonce', ''), ('instanceNonce', None)):
            with self.subTest(field=field, value=value), self.assertRaises(control.ControlError):
                upgrade._idle(control, dict(self.root, **{field: value}), child=False)
        self.assertEqual(self.package_calls, [])

    def test_current_primary_explicit_false_path_does_not_read_a_package(self):
        """Ordinary modern idle status retains its original byte/dictionary path."""
        status = dict(self.root, uiStatus='current', assemblySha256='c' * 64, agentStreamRunning=False)
        before = copy.deepcopy(status)
        self.assertIs(upgrade._idle(control, status, child=False), status)
        self.assertEqual(status, before)
        self.assertEqual(self.package_calls, [])

    def test_current_child_explicit_false_still_requires_idle_endpoint(self):
        """Accept unchanged child evidence, reject a startup-in-progress endpoint without I/O."""
        status = self.child()
        self.assertIs(upgrade._idle(control, status, child=True), status)
        with self.assertRaises(control.ControlError):
            upgrade._idle(control, dict(status, automationState='starting_game'), child=True)
        self.assertEqual(self.package_calls, [])

    def test_missing_reported_assembly_is_rejected_even_with_fake_package_success(self):
        """An absent assembly cannot borrow the verified R1 package identity."""
        status = dict(self.root, uiStatus='current')
        status.pop('assemblySha256')
        with self.assertRaisesRegex(control.ControlError, 'process assembly'):
            upgrade._idle(control, status, child=False)
        self.assertEqual(len(self.package_calls), 1)


if __name__ == '__main__':
    unittest.main()
