"""Exercise the real PowerShell package checks without launching BetterGI or inspecting sessions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


DIRECTORY = Path(__file__).resolve().parent
POWERSHELL = shutil.which('powershell.exe') or shutil.which('pwsh.exe')


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Requires Windows PowerShell.')
class HostLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def package(self, number):
        target = self.root / f'release-r{number}' / 'BetterGI-English-win-x64'
        target.mkdir(parents=True)
        for name in ('BetterGI.exe', 'BetterGI.dll', 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll',
                     'System.Private.CoreLib.dll', 'PresentationFramework.dll'):
            (target / name).write_bytes(b'synthetic fixture; not executable')
        (target / 'BetterGI.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {
            'tfm': 'net10.0', 'includedFrameworks': [{'name': name, 'version': '10.0.4'} for name in
                ('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App', 'Microsoft.AspNetCore.App')]}}))
        (target / 'BetterGI.deps.json').write_text(json.dumps({
            'runtimeTarget': {'name': '.NETCoreApp,Version=v10.0/win-x64'}}))
        manifest = {'version': 1, 'targetDirectory': str(target),
                    'exeSha256': hashlib.sha256((target / 'BetterGI.exe').read_bytes()).hexdigest(),
                    'dllSha256': hashlib.sha256((target / 'BetterGI.dll').read_bytes()).hexdigest()}
        (target.parent / 'build-manifest.json').write_text(json.dumps(manifest))
        return target, manifest

    def validate(self, *extra):
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(DIRECTORY / 'start-host.ps1'), '-ValidateOnly',
                                 '-ArtifactsDirectory', str(self.root), *map(str, extra)],
                                capture_output=True, text=True, timeout=30)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_selects_numeric_newest_verified_release_and_reports_incomplete_newer_one(self):
        self.package(2)
        newest, _ = self.package(10)
        incomplete = self.root / 'release-r11' / 'BetterGI-English-win-x64'
        incomplete.mkdir(parents=True)
        code, result = self.validate()
        self.assertEqual(code, 0, result)
        self.assertEqual(Path(result['package']['targetDirectory']), newest)
        self.assertEqual(result['package']['release'], 10)
        self.assertEqual(len(result['skippedPackages']), 1)
        self.assertIn('release-r11', result['skippedPackages'][0]['directory'])

    def test_explicit_target_hash_mismatch_fails_without_falling_back(self):
        self.package(1)
        target, _ = self.package(2)
        (target / 'BetterGI.dll').write_bytes(b'changed after build')
        code, result = self.validate('-TargetDirectory', target)
        self.assertEqual(code, 1)
        self.assertFalse(result['rootReady'])
        self.assertIn('hash mismatch', result['error'])

    def test_manifest_cannot_redirect_to_another_directory(self):
        target, manifest = self.package(1)
        manifest['targetDirectory'] = str(target.parent)
        (target.parent / 'build-manifest.json').write_text(json.dumps(manifest))
        code, result = self.validate('-TargetDirectory', target)
        self.assertEqual(code, 1)
        self.assertIn('target directory', result['error'])

    def test_missing_runtime_file_fails_before_any_process_work(self):
        target, _ = self.package(1)
        (target / 'coreclr.dll').unlink()
        code, result = self.validate('-TargetDirectory', target)
        self.assertEqual(code, 1)
        self.assertIn('coreclr.dll', result['error'])

    def test_identity_requires_matching_role_session_pid_hash_nonce_and_automation(self):
        target, manifest = self.package(1)
        status = {'instanceType': 'Primary', 'automationEnabled': True, 'remoteDesktop': False,
                  'windowsSessionId': 2, 'processId': 1234, 'instanceNonce': 'fresh-nonce',
                  'appDirectory': str(target), 'assemblySha256': manifest['dllSha256']}
        cases = [status]
        for key, value in [('instanceType', 'ChildSession'), ('automationEnabled', False),
                           ('automationEnabled', 'true'), ('remoteDesktop', True), ('windowsSessionId', 3),
                           ('processId', 4321), ('instanceNonce', ''), ('assemblySha256', '0' * 64),
                           ('appDirectory', str(target.parent))]:
            cases.append({**status, key: value})
        cases.append({})
        fixture = self.root / 'identities.json'
        fixture.write_text(json.dumps(cases))
        script = self.root / 'identity-check.ps1'
        script.write_text('''param($Module, $Target, $Fixture)
$ErrorActionPreference = 'Stop'
Import-Module $Module -Force
$package = Get-VerifiedHostPackage $Target
$cases = Get-Content -LiteralPath $Fixture -Raw | ConvertFrom-Json
$results = @($cases | ForEach-Object { Test-HostIdentity -Status $_ -Package $package -WindowsSessionId 2 -ExpectedProcessId 1234 })
ConvertTo-Json -InputObject $results
''')
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), str(DIRECTORY / 'HostLauncher.psm1'), str(target), str(fixture)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [True] + [False] * (len(cases) - 1))

    def test_exited_loader_can_be_replaced_by_one_verified_elevated_host(self):
        target, manifest = self.package(1)
        status = {'instanceType': 'Primary', 'automationEnabled': True, 'remoteDesktop': False,
                  'windowsSessionId': 2, 'processId': 4321, 'instanceNonce': 'elevated-nonce',
                  'appDirectory': str(target), 'assemblySha256': manifest['dllSha256']}
        fixture = self.root / 'startup.json'
        fixture.write_text(json.dumps({'loaderProcessId': 1234, 'loaderExited': True, 'root': status}))
        script = self.root / 'startup-check.ps1'
        script.write_text('''param($Module, $Target, $Fixture)
$ErrorActionPreference = 'Stop'
Import-Module $Module -Force
$package = Get-VerifiedHostPackage $Target
$fixture = Get-Content -LiteralPath $Fixture -Raw | ConvertFrom-Json
$pending = Select-StartedHost -Package $package -WindowsSessionId 2
$root = Select-StartedHost -Instances @($fixture.root) -Package $package -WindowsSessionId 2
$ambiguousRejected = $false
try { Select-StartedHost -Instances @($fixture.root, $fixture.root) -Package $package -WindowsSessionId 2 | Out-Null }
catch { $ambiguousRejected = $true }
$oldProcessRejected = $false
try { Select-StartedHost -Instances @($fixture.root) -Package $package -WindowsSessionId 2 -BeforeProcessIds @(4321) | Out-Null }
catch { $oldProcessRejected = $true }
@{ pending = ($null -eq $pending); rootProcessId = $root.processId;
   loaderExited = $fixture.loaderExited; loaderProcessId = $fixture.loaderProcessId;
   ambiguousRejected = $ambiguousRejected; oldProcessRejected = $oldProcessRejected } | ConvertTo-Json
''')
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), str(DIRECTORY / 'HostLauncher.psm1'), str(target), str(fixture)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['loaderExited'])
        self.assertEqual(report['rootProcessId'], 4321)
        self.assertNotEqual(report['rootProcessId'], report['loaderProcessId'])
        self.assertTrue(report['pending'])
        self.assertTrue(report['ambiguousRejected'])
        self.assertTrue(report['oldProcessRejected'])


if __name__ == '__main__':
    unittest.main()
