import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / 'tools/quest-pilot/act-one-command.py'


class QuestStepCliTests(unittest.TestCase):
    def test_step_is_serialized_as_data_with_frame_and_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'User/JsScript/ActOnePilot'
            root.mkdir(parents=True)
            (root / 'observation.json').write_text(json.dumps({'session': 'session-a', 'frameId': 7}), encoding='utf-8')
            env = dict(os.environ, BETTERGI_PILOT_APP_DIR=temp)
            result = subprocess.run([sys.executable, str(CLI), 'questStep', '--session', 'session-a', '--frame', '7',
                                     '--step', 'glideOpen', '--wait-seconds', '0'], env=env,
                                    text=True, capture_output=True, check=True)
            request = json.loads((root / 'request.json').read_text(encoding='utf-8'))
            self.assertEqual(request['mission'], 'questStep')
            self.assertEqual(request['step'], 'glideOpen')
            self.assertEqual(request['session'], 'session-a')
            self.assertEqual(request['expectedFrameId'], 7)
            self.assertNotIn('key', request)

    def test_invalid_step_is_rejected_before_writing_a_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'User/JsScript/ActOnePilot'
            root.mkdir(parents=True)
            (root / 'observation.json').write_text(json.dumps({'session': 'session-a', 'frameId': 7}), encoding='utf-8')
            env = dict(os.environ, BETTERGI_PILOT_APP_DIR=temp)
            result = subprocess.run([sys.executable, str(CLI), 'questStep', '--session', 'session-a', '--frame', '7',
                                     '--step', 'VK_F;anything', '--wait-seconds', '0'], env=env,
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'request.json').exists())


if __name__ == '__main__':
    unittest.main()
