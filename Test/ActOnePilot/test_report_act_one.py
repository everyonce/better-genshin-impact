import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'quest-pilot' / 'report-act-one.py'
spec = importlib.util.spec_from_file_location('report_act_one', SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportActOneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_observation(self, session):
        directory = self.root / 'observations' / session
        directory.mkdir(parents=True)
        frame = {'session': session, 'frameId': 1, 'timestamp': 1000,
                 'timings': {}, 'hud': {'objectives': ['Current objective']}, 'map': None}
        (directory / 'frame-0001.json').write_text(json.dumps(frame), encoding='utf-8')

    def test_jsonl_is_preferred_over_legacy_json_and_keeps_latest_terminal_record(self):
        reports = self.root / 'reports'
        reports.mkdir()
        session = 's-jsonl'
        self.write_observation(session)
        legacy = [{'session': session, 'id': 'mission', 'mission': 'observe', 'status': 'completed',
                   'details': {'inputEvents': [{'type': 'legacy'}]}}]
        (reports / f'{session}.json').write_text(json.dumps(legacy), encoding='utf-8')
        records = [
            {'session': session, 'id': 'mission', 'mission': 'observe', 'status': 'started', 'details': None},
            {'session': session, 'id': 'mission', 'mission': 'observe', 'status': 'completed',
             'details': {'inputEvents': [{'type': 'key', 'key': 'VK_J', 'durationMs': 10,
                                          'startedAt': 100, 'finishedAt': 111}]}},
        ]
        (reports / f'{session}.jsonl').write_text('\n'.join(json.dumps(item) for item in records) + '\n{partial', encoding='utf-8')
        result = report.build_report(self.root)['sessions'][0]
        self.assertEqual(result['mission_outcomes']['completed'], 1)
        self.assertEqual(result['controller_emitted_input']['event_counts_by_mission'], {'observe': {'key': 1}})
        self.assertEqual(result['controller_emitted_input']['key_counts_by_mission'], {'observe': {'VK_J': 1}})
        self.assertEqual(result['key_duration_ms_by_mission_and_requested_duration']['observe']['10']['actual_ms_min'], 11)

    def test_legacy_json_array_remains_supported_without_jsonl(self):
        reports = self.root / 'reports'
        reports.mkdir()
        session = 's-legacy'
        self.write_observation(session)
        data = [{'session': session, 'id': 'mission', 'mission': 'navigation', 'status': 'failed',
                 'details': {'reason': 'bounded stop', 'result': {'turns': 2},
                             'inputEvents': [{'type': 'forward'}]}}]
        (reports / f'{session}.json').write_text(json.dumps(data), encoding='utf-8')
        result = report.build_report(self.root)['sessions'][0]
        self.assertEqual(result['mission_outcomes']['failed'], 1)
        self.assertEqual(result['mission_reasons']['failed'], {'bounded stop': 1})
        self.assertEqual(result['controller_emitted_input']['turns_by_mission'], {'navigation': 2})
        self.assertEqual(result['controller_emitted_input']['event_counts_by_mission'], {'navigation': {'forward': 1}})

    def test_interior_or_complete_malformed_jsonl_record_fails_with_location(self):
        reports = self.root / 'reports'
        reports.mkdir()
        session = 's-corrupt'
        valid = json.dumps({'id': 'm1', 'mission': 'observe', 'status': 'started'})
        (reports / f'{session}.jsonl').write_text(valid + '\n{broken}\n' + valid + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, rf'{session}\.jsonl:2'):
            report.build_report(self.root)


if __name__ == '__main__':
    unittest.main()
