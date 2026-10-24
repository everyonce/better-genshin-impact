"""Real WinPS 5 subprocess framing with headless fixtures only; no app/control calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_start_host import DIRECTORY, POWERSHELL


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Requires Windows PowerShell.')
class LauncherControlTests(unittest.TestCase):
    def run_fixture(self, body, arguments=(), timeout=10):
        """Exercise the exported production helper under Stop, including native stderr."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            fixture = folder / 'literal child.py'
            fixture.write_text(body, encoding='utf-8')
            payload = folder / 'arguments.json'
            payload.write_text(json.dumps(list(arguments)), encoding='utf-8')
            script = folder / 'check.ps1'
            script.write_text('''param($Module, $Python, $Fixture, $Payload, [int]$Seconds)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Import-Module $Module -Force
$literalArguments = Get-Content -LiteralPath $Payload -Raw -Encoding UTF8 | ConvertFrom-Json
$arguments = @($Fixture) + $literalArguments
try {
    $reply = Invoke-LauncherJson -Executable $Python -Arguments $arguments -Phase 'ensure-child' -TimeoutSeconds $Seconds
    @{ok=$true;reply=$reply;powerShellMajor=$PSVersionTable.PSVersion.Major} | ConvertTo-Json -Depth 20
} catch {
    @{ok=$false;message=$_.Exception.Message;failure=(Get-LauncherFailure $_);
      powerShellMajor=$PSVersionTable.PSVersion.Major} | ConvertTo-Json -Depth 20
}
''', encoding='utf-8')
            result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(script), str(DIRECTORY / 'LauncherControl.psm1'),
                                     sys.executable, str(fixture), str(payload), str(timeout)],
                                    capture_output=True, text=True, encoding='utf-8', timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            value = json.loads(result.stdout)
            self.assertEqual(value['powerShellMajor'], 5)
            return value

    def test_failure_retains_separate_streams_exit_and_parsed_phase_evidence(self):
        value = self.run_fixture('''import json,sys
print('stdout retained')
print(json.dumps({'success':False,'error':'fixture failed',
  'replacementEvidence':{'phase':'replacement_readiness','restartAcknowledged':True}}),file=sys.stderr)
sys.exit(17)
''')
        self.assertFalse(value['ok'])
        failure = value['failure']
        self.assertEqual(failure['phase'], 'ensure-child')
        self.assertEqual(failure['process']['exitCode'], 17)
        self.assertEqual(failure['process']['stdout'], 'stdout retained\r\n')
        self.assertIn('fixture failed', failure['process']['stderr'])
        self.assertTrue(failure['controlError']['replacementEvidence']['restartAcknowledged'])
        self.assertIn('fixture failed', value['message'])

    def test_success_stderr_is_not_a_winps_native_command_error(self):
        value = self.run_fixture("import json,sys\nprint(json.dumps({'ready':True}))\nprint('warning',file=sys.stderr)\n")
        self.assertTrue(value['ok'])
        self.assertTrue(value['reply']['value']['ready'])
        self.assertEqual(value['reply']['process']['stderr'].strip(), 'warning')

    def test_literal_argv_roundtrip_preserves_empty_quotes_slashes_unicode_and_metacharacters(self):
        arguments = ['', 'two words', 'quote"here', 'ends\\', 'two\\\\', '\\"',
                     'a\\\\"b', '$(Write-Error nope); & | < > `', '日本語']
        value = self.run_fixture('import json,sys\nprint(json.dumps({"args":sys.argv[1:]}))\n', arguments)
        self.assertTrue(value['ok'])
        self.assertEqual(value['reply']['value']['args'], arguments)

    def test_invalid_success_json_preserves_stdout_and_produces_nonempty_error(self):
        value = self.run_fixture("print('not JSON')\n")
        self.assertFalse(value['ok'])
        self.assertEqual(value['failure']['process']['exitCode'], 0)
        self.assertIn('not JSON', value['failure']['process']['stdout'])
        self.assertTrue(value['message'])

    def test_empty_stderr_error_field_does_not_make_empty_failure(self):
        value = self.run_fixture('import sys\nprint(\'{"error":""}\',file=sys.stderr)\nsys.exit(1)\n')
        self.assertFalse(value['ok'])
        self.assertIn('failed without an error message', value['message'])

    def test_timeout_stops_only_owned_fixture_and_reports_unknown_outcome_without_retry(self):
        value = self.run_fixture('import time\ntime.sleep(8)\n', timeout=1)
        self.assertFalse(value['ok'])
        self.assertTrue(value['failure']['process']['timedOut'])
        self.assertLess(value['failure']['process']['elapsedMs'], 6000)
        self.assertIn('No request was replayed', value['message'])


if __name__ == '__main__':
    unittest.main()
