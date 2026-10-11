import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / 'tools/quest-pilot/act-one-command.py'


class CompactCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'User/JsScript/ActOnePilot'
        self.root.mkdir(parents=True)
        self.env = dict(os.environ, BETTERGI_PILOT_APP_DIR=self.temp.name)
        self.observation = {
            'session': 'session-a', 'frameId': 9, 'screenshotPath': 'observations/session-a/frame-0009.png',
            'hud': {'world': True, 'health': {'current': 100, 'max': 100}},
            'ocr': [
                {'text': 'Go to the gate', 'x': 30, 'y': 100, 'width': 150, 'height': 20},
                {'text': 'UID:', 'x': 1688, 'y': 1054, 'width': 41, 'height': 17},
                {'text': '123456789', 'x': 1726, 'y': 1052, 'width': 135, 'height': 23},
                {'text': 'UD:234567890', 'x': 1680, 'y': 1052, 'width': 120, 'height': 20},
                {'text': ':345678901', 'x': 1680, 'y': 1052, 'width': 110, 'height': 20},
                {'text': '456789012', 'x': 1730, 'y': 1052, 'width': 120, 'height': 20},
                {'text': '123456', 'x': 30, 'y': 200, 'width': 60, 'height': 20},
            ],
        }
        (self.root / 'observation.json').write_text(json.dumps(self.observation), encoding='utf-8')

    def test_compact_terminal_keeps_result_and_fresh_frame_without_event_or_uid_dump(self):
        process = subprocess.Popen(
            [sys.executable, str(CLI), 'observe', '--session', 'session-a', '--frame', '9',
             '--compact', '--wait-seconds', '2'], env=self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        request_path = self.root / 'request.json'
        deadline = time.monotonic() + 1
        while not request_path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(request_path.exists(), 'CLI should submit its single request')
        request = json.loads(request_path.read_text(encoding='utf-8'))
        receipt = {
            'id': request['id'], 'session': 'session-a', 'mission': 'observe', 'status': 'completed',
            'frameId': 9, 'details': {'elapsedMs': 321, 'result': {'status': 'observed'},
                                     'inputEvents': [{'type': 'rotate', 'dx': -750}]},
        }
        (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
        stdout, stderr = process.communicate(timeout=3)
        self.assertEqual(process.returncode, 0, stderr)
        lines = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual(len(lines), 2)
        compact = lines[-1]
        self.assertEqual(compact['submittedId'], request['id'])
        self.assertEqual(compact['terminalId'], request['id'])
        self.assertEqual(compact['status'], 'completed')
        self.assertEqual(compact['result'], {'status': 'observed'})
        self.assertEqual(compact['elapsedMs'], 321)
        self.assertEqual(compact['session'], 'session-a')
        self.assertEqual(compact['frameId'], 9)
        self.assertTrue(compact['screenshot'].endswith('frame-0009.png'))
        self.assertEqual(compact['hud'], self.observation['hud'])
        self.assertEqual(compact['ocr'], [self.observation['ocr'][0], self.observation['ocr'][-1]])
        self.assertNotIn('inputEvents', compact)
        self.assertNotIn('observation', compact)

    def test_compact_pending_output_does_not_replay_or_change_request(self):
        result = subprocess.run(
            [sys.executable, str(CLI), 'observe', '--session', 'session-a', '--frame', '9',
             '--compact', '--wait-seconds', '0'], env=self.env, text=True,
            capture_output=True, check=True)
        lines = [json.loads(line) for line in result.stdout.splitlines()]
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        self.assertEqual(lines[0]['submitted'], request['id'])
        self.assertEqual(lines[1]['pending'], request['id'])
        self.assertIn('Do not replay', lines[1]['instruction'])
        self.assertEqual(request['expectedFrameId'], 9)


if __name__ == '__main__':
    unittest.main()
