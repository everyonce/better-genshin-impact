import contextlib
import importlib.util
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / 'tools/quest-pilot/act-one-command.py'
spec = importlib.util.spec_from_file_location('act_one_command_quest_step_test', CLI)
command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command)


class QuestStepCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'User/JsScript/ActOnePilot'
        self.root.mkdir(parents=True)
        self.old_root = command.ROOT
        command.ROOT = self.root
        self.addCleanup(setattr, command, 'ROOT', self.old_root)
        (self.root / 'observation.json').write_text(
            json.dumps({'session': 'session-a', 'frameId': 7}), encoding='utf-8')
        (self.root / 'controller-status.json').write_text(json.dumps({
            'version': 1, 'processId': 4321, 'windowsSessionId': 6, 'remoteDesktop': True,
            'session': 'session-a', 'state': 'idle',
            'heartbeatAt': int(time.time() * 1000), 'frameId': 7,
        }), encoding='utf-8')
        self.process_verifier = mock.Mock()
        original_check = command.require_live_controller

        def check_with_mocked_process(root, session, frame, expected_session, **kwargs):
            return original_check(root, session, frame, expected_session,
                                 process_verifier=self.process_verifier, **kwargs)

        self.live_check_patch = mock.patch.object(command, 'require_live_controller', check_with_mocked_process)
        self.live_check_patch.start()
        self.addCleanup(self.live_check_patch.stop)

    def run_cli(self, argv):
        output = io.StringIO()
        with mock.patch('sys.argv', ['act-one-command.py', *argv]), contextlib.redirect_stdout(output):
            command.main()
        return output.getvalue()

    def test_step_is_serialized_as_data_with_frame_and_session(self):
        self.run_cli(['questStep', '--session', 'session-a', '--expected-windows-session-id', '6', '--frame', '7',
                      '--step', 'glideOpen', '--wait-seconds', '0'])
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        self.assertEqual(request['mission'], 'questStep')
        self.assertEqual(request['step'], 'glideOpen')
        self.assertEqual(request['session'], 'session-a')
        self.assertEqual(request['expectedFrameId'], 7)
        self.assertNotIn('key', request)
        self.process_verifier.assert_called_once_with(4321, 6)

    def test_invalid_step_is_rejected_before_writing_a_request(self):
        with self.assertRaisesRegex(SystemExit, '--step must start lowercase'):
            self.run_cli(['questStep', '--session', 'session-a', '--expected-windows-session-id', '6', '--frame', '7',
                          '--step', 'VK_F;anything', '--wait-seconds', '0'])
        self.assertFalse((self.root / 'request.json').exists())


if __name__ == '__main__':
    unittest.main()
