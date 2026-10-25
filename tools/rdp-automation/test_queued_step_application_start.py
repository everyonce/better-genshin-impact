"""Prepared fake-only tests of exact selected CLI bodies; never import the live CLI."""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
FUNCTIONS = ('_observation_profile', 'exchange', 'require_role', 'mutate', 'refresh',
             'wait_status', '_game_runtime_ready', 'start_agent', '_desktop_dc_capability',
             '_controller_source_policy', '_controller_source_unchanged', '_parse_navigation_yaw', 'main')
CONSTANTS = ('COMMAND_FIELDS', 'MAX_MESSAGE', 'MAX_NAVIGATION_DIAGNOSTICS_RESPONSE', 'CAPTURE_MODES',
             'READBACK_MODES', 'SOURCE_RETENTIONS', 'CONVERSION_MODES', 'DESKTOP_DC_SOURCE_POLICIES',
             'SHADOW_CAPTURE_MODE', 'LEGACY_OBSERVATION_PROFILE', 'OBSERVATION_PROFILES')
ERRORS = ('NavigationResetError', 'NavigationBaselineError', 'ReplacementError')


def forbidden(*args, **kwargs):
    """Fail any unprovided operational seam rather than falling back to a real API."""
    raise AssertionError('unprovided operational seam')


def load_selected(folder):
    """Compile only declared AST definitions/constants, never module imports or loader code."""
    path = {'files': HERE / 'rdp_control.py',
            'preimages': HERE / 'fixtures/queued_start/legacy/rdp_control.py'}[folder]
    tree = ast.parse(path.read_bytes(), filename=str(path))
    namespace = dict(argparse=argparse, hashlib=hashlib, io=io, json=json, Path=Path, re=re,
                     struct=struct, sys=sys, __file__=str(path), ControlError=type('ControlError', (RuntimeError,), {}),
                     time=SimpleNamespace(time=lambda: 1700000000.0, monotonic=lambda: 1.0, sleep=forbidden),
                     uuid=SimpleNamespace(uuid4=lambda: 'fixture-request'), discover=forbidden)
    selected = [node for node in tree.body if
                isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS or
                isinstance(node, ast.ClassDef) and node.name in ERRORS or
                isinstance(node, ast.Assign) and len(node.targets) == 1 and
                isinstance(node.targets[0], ast.Name) and node.targets[0].id in CONSTANTS]
    names = {node.name for node in selected if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert names == set(FUNCTIONS + ERRORS)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    transport_path = HERE.parent / 'quest-pilot/controller-control.py'
    transport_tree = ast.parse(transport_path.read_bytes())
    read = next(node for node in transport_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'read_exact')
    exec(compile(ast.Module(body=[read], type_ignores=[]), str(transport_path), 'exec'), namespace)
    namespace['transport'] = SimpleNamespace(WinPipeApi=forbidden, read_exact=namespace['read_exact'])
    fake_path = HERE / 'test_rdp_control.py'
    fake = next(node for node in ast.parse(fake_path.read_bytes()).body if isinstance(node, ast.ClassDef) and node.name == 'FakePipe')
    exec(compile(ast.Module(body=[fake], type_ignores=[]), str(fake_path), 'exec'), namespace)
    return namespace


@contextmanager
def replace(namespace, **values):
    """Temporarily replace selected globals with explicit local fakes."""
    before = {key: namespace[key] for key in values}
    namespace.update(values)
    try:
        yield
    finally:
        namespace.update(before)


class QueuedStartCases(unittest.TestCase):
    """Exercise the actual validation/serialization/control flow with in-memory peers."""
    def setUp(self):
        self.c = load_selected('files')
        self.child = dict(processId=123, windowsSessionId=3, instanceNonce='child-epoch',
                          instanceType='ChildSession', remoteDesktop=True, automationEnabled=True,
                          runtimeRunning=True, automationState='game_ready', agentStreamState='idle',
                          agentStreamRunning=False, agentInputEnabled=False)

    def pipe(self, control=None, status=None):
        """Create the unchanged existing FakePipe with the selected child session."""
        api = (control or self.c)['FakePipe'](status or self.child)
        api.session = 3
        return api

    def start(self, control=None, child=None, enable=False, profile=None, **options):
        """Use actual mutate/refresh/framing and supply exactly two in-memory peers."""
        c = control or self.c
        child = child or self.child
        profile = profile or c['LEGACY_OBSERVATION_PROFILE']
        ready = dict(child, agentStreamState='listening', agentStreamRunning=True,
                     agentInputEnabled=enable, agentObservationProfile=profile)
        peers = [self.pipe(c, ready), self.pipe(c, ready)]
        pending = list(peers)
        c['transport'].WinPipeApi = lambda: pending.pop(0)
        result = c['start_agent'](child, 1, enable, profile, **options)
        return result, peers, pending

    def cli(self, argv):
        """Run the actual parser/dispatch body with bounded stdout and fake discovery/start."""
        calls, discoveries = [], []
        def discovery():
            discoveries.append(True)
            return {'instances': [self.child]}
        def start(*args, **kwargs):
            calls.append((args, kwargs))
            return self.child
        before = sys.argv, sys.stdout, sys.stderr
        sys.argv, sys.stdout, sys.stderr = ['rdp_control.py', *argv], io.StringIO(), io.StringIO()
        try:
            with replace(self.c, discover=discovery, start_agent=start, exchange=forbidden):
                try:
                    code = self.c['main']()
                except SystemExit as error:
                    code = error.code
            return code, calls, discoveries, sys.stdout.getvalue(), sys.stderr.getvalue()
        finally:
            sys.argv, sys.stdout, sys.stderr = before

    def test_opted_start_dispatches_once_with_each_profile(self):
        for profile in self.c['OBSERVATION_PROFILES']:
            with self.subTest(profile=profile):
                result, peers, pending = self.start(enable=True, profile=profile,
                    experimental_queued_step_applications=True)
                self.assertFalse(pending)
                self.assertEqual(result['agentStreamState'], 'listening')
                self.assertEqual(peers[0].request['command'], 'startAgentStream')
                self.assertIs(peers[0].request['enableInput'], True)
                self.assertIs(peers[0].request['experimentalQueuedStepApplications'], True)
                self.assertEqual(peers[1].request['command'], 'status')
                self.assertTrue(all(peer.closed and len(peer.written) == 1 for peer in peers))

    def test_omitted_and_false_preserve_original_framed_bytes(self):
        old = load_selected('preimages')
        for enable in (False, True):
            for profile in self.c['OBSERVATION_PROFILES']:
                _, expected, _ = self.start(old, enable=enable, profile=profile)
                for options in ({}, {'experimental_queued_step_applications': False}):
                    with self.subTest(enable=enable, profile=profile, options=options):
                        _, actual, _ = self.start(enable=enable, profile=profile, **options)
                        self.assertEqual([p.written for p in actual], [p.written for p in expected])
                        self.assertNotIn('experimentalQueuedStepApplications', actual[0].request)

    def test_wire_accepts_exact_true_and_false(self):
        for experimental, enable in ((False, False), (False, True), (True, True)):
            for profile in (None, *self.c['OBSERVATION_PROFILES']):
                fields = dict(enableInput=enable, experimentalQueuedStepApplications=experimental)
                if profile is not None:
                    fields['observationProfile'] = profile
                api = self.pipe()
                self.c['exchange']('startAgentStream', 123, 3, nonce='child-epoch', fields=fields, api=api)
                self.assertIs(api.request['experimentalQueuedStepApplications'], experimental)

    def test_wire_rejects_wrong_types_before_connection(self):
        for value in (None, 0, 1, '', 'false', [], {}):
            api = self.pipe()
            with self.subTest(value=value), self.assertRaises(self.c['ControlError']):
                self.c['exchange']('startAgentStream', 123, 3, nonce='child-epoch',
                    fields=dict(enableInput=True, experimentalQueuedStepApplications=value), api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))

    def test_helper_rejects_wrong_types_before_mutation(self):
        for value in (None, 0, 1, '', 'false', [], {}):
            with self.subTest(value=value), self.assertRaises(self.c['ControlError']):
                self.c['start_agent'](self.child, 1, True, experimental_queued_step_applications=value)

    def test_input_required_without_boolean_coercion(self):
        for enable in (False, None, 0, 1, 'true'):
            api = self.pipe()
            with self.subTest(enable=enable), self.assertRaises(self.c['ControlError']):
                self.c['exchange']('startAgentStream', 123, 3, nonce='child-epoch',
                    fields=dict(enableInput=enable, experimentalQueuedStepApplications=True), api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))
            with self.assertRaises(self.c['ControlError']):
                self.c['start_agent'](self.child, 1, enable, experimental_queued_step_applications=True)

    def test_missing_input_and_unknown_fields_reject_before_connection(self):
        for fields in ({}, {'experimentalQueuedStepApplications': True},
                       {'observationProfile': None, 'experimentalQueuedStepApplications': False},
                       {'enableInput': True, 'experimentalQueuedStepApplications': True, 'extra': 1}):
            api = self.pipe()
            with self.subTest(fields=fields), self.assertRaises(self.c['ControlError']):
                self.c['exchange']('startAgentStream', 123, 3, nonce='child-epoch', fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))

    def test_cross_command_field_rejects_even_false(self):
        for command, fields in self.c['COMMAND_FIELDS'].items():
            if command == 'startAgentStream':
                continue
            for value in (False, True):
                api = self.pipe()
                supplied = dict.fromkeys(fields)
                supplied['experimentalQueuedStepApplications'] = value
                with self.subTest(command=command, value=value), self.assertRaises(self.c['ControlError']):
                    self.c['exchange'](command, 123, 3, nonce='child-epoch', fields=supplied, api=api)
                self.assertFalse(hasattr(api, 'pipe_name'))

    def test_no_new_commands_and_only_one_allowed_field(self):
        old = load_selected('preimages')['COMMAND_FIELDS']
        self.assertEqual(set(self.c['COMMAND_FIELDS']), set(old))
        for command in old:
            expected = old[command] | {'experimentalQueuedStepApplications'} if command == 'startAgentStream' else old[command]
            self.assertEqual(self.c['COMMAND_FIELDS'][command], expected)

    def test_opted_start_refuses_unverified_running_permission(self):
        running = dict(self.child, agentStreamRunning=True, agentInputEnabled=True, agentStreamState='listening')
        with self.assertRaisesRegex(self.c['ControlError'], 'Stop the current agent'):
            self.c['start_agent'](running, 1, True, experimental_queued_step_applications=True)

    def test_ordinary_running_join_remains_unmodified(self):
        running = dict(self.child, agentStreamRunning=True, agentInputEnabled=True, agentStreamState='listening')
        api = self.pipe(status=running)
        self.c['transport'].WinPipeApi = lambda: api
        result = self.c['start_agent'](running, 1, True, experimental_queued_step_applications=False)
        self.assertEqual(result, running)
        self.assertEqual(api.request['command'], 'status')
        self.assertEqual(len(api.written), 1)

    def test_existing_role_runtime_and_source_gates_remain(self):
        for updates in ({'remoteDesktop': False}, {'instanceType': 'Primary'}, {'automationEnabled': False},
                        {'runtimeRunning': False}, {'captureMode': 'DesktopDc'}):
            with self.subTest(updates=updates), self.assertRaises(self.c['ControlError']):
                self.c['start_agent'](dict(self.child, **updates), 1, True, experimental_queued_step_applications=True)

    def test_authentication_still_precedes_write(self):
        for field, value in (('pid', 999), ('session', 5)):
            api = self.pipe()
            setattr(api, field, value)
            with self.subTest(field=field), self.assertRaises(self.c['ControlError']):
                self.c['exchange']('startAgentStream', 123, 3, nonce='child-epoch',
                    fields=dict(enableInput=True, experimentalQueuedStepApplications=True), api=api)
            self.assertEqual(api.written, [])
            self.assertTrue(api.closed)

    def test_nonce_change_is_not_replayed(self):
        api = self.pipe(status=dict(self.child, instanceNonce='different'))
        with self.assertRaisesRegex(self.c['ControlError'], 'instance changed'):
            self.c['exchange']('startAgentStream', 123, 3, nonce='child-epoch',
                fields=dict(enableInput=True, experimentalQueuedStepApplications=True), api=api)
        self.assertEqual(len(api.written), 1)
        self.assertTrue(api.closed)

    def test_failed_listening_does_not_repeat_start(self):
        peers = [self.pipe(), self.pipe(status=dict(self.child, agentStreamState='rejected'))]
        pending = list(peers)
        self.c['transport'].WinPipeApi = lambda: pending.pop(0)
        with self.assertRaisesRegex(self.c['ControlError'], 'ended before readiness'):
            self.c['start_agent'](self.child, 1, True, experimental_queued_step_applications=True)
        self.assertFalse(pending)
        self.assertEqual([p.request['command'] for p in peers], ['startAgentStream', 'status'])

    def test_cli_only_explicit_opt_in_adds_keyword(self):
        for profile in self.c['OBSERVATION_PROFILES']:
            code, calls, discoveries, _, _ = self.cli(['start-agent', '--enable-input',
                '--experimental-queued-step-applications', '--observation-profile', profile])
            self.assertEqual(code, 0)
            self.assertEqual(len(discoveries), 1)
            self.assertEqual(calls, [((self.child, 120, True, profile), {'experimental_queued_step_applications': True})])

    def test_cli_ordinary_call_shape_is_exact(self):
        for args, enable in (([], False), (['--enable-input'], True)):
            code, calls, _, _, _ = self.cli(['start-agent', *args])
            self.assertEqual(code, 0)
            self.assertEqual(calls, [((self.child, 120, enable, self.c['LEGACY_OBSERVATION_PROFILE']), {})])

    def test_cli_missing_input_rejects_before_discovery_or_status(self):
        for target in ([], ['--process-id', '123', '--windows-session-id', '3']):
            code, calls, discoveries, _, error = self.cli(['start-agent', '--experimental-queued-step-applications', *target])
            self.assertEqual(code, 1)
            self.assertIn('requires --enable-input', error)
            self.assertEqual(calls, [])
            self.assertEqual(discoveries, [])

    def test_cli_cross_command_and_value_arguments_are_rejected(self):
        for args in (['stop-agent', '--experimental-queued-step-applications'],
                     ['status', '--experimental-queued-step-applications'],
                     ['start-agent', '--experimental-queued-step-applications=false'],
                     ['start-agent', '--experimental-queued-step-applications', 'false']):
            code, calls, discoveries, _, _ = self.cli(args)
            self.assertEqual(code, 2)
            self.assertEqual(calls, [])
            self.assertEqual(discoveries, [])


if __name__ == '__main__':
    unittest.main()
