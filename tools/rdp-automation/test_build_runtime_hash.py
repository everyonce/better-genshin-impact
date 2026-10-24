"""Test the build manifest's actual hash helper without invoking build or publish."""
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
class BuildRuntimeHashTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def invoke(self, path, mode='hash'):
        # Parse the real build script and execute only the named function definition.
        # Never dot-source its top-level SDK, release-selection or publishing statements.
        script = self.root / 'hash-check.ps1'
        script.write_text(r'''param($BuildScript, $Target, $Mode)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($BuildScript, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Build script has parser errors.' }
$definitions = @($ast.FindAll({param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-BuildFileSha256'
}, $true))
if ($definitions.Count -ne 1) { throw 'Expected exactly one build hash helper.' }
. ([scriptblock]::Create($definitions[0].Extent.Text))
$manifestCalls = @($ast.FindAll({param($node)
    $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'Get-BuildFileSha256'
}, $true))
if ($manifestCalls.Count -ne 2) { throw 'Both published binaries must use the tested helper.' }

# Reproduce the packaging failure: the utility module cannot auto-load, so the
# original Get-FileHash command is unavailable in this fresh child shell.
$PSModuleAutoLoadingPreference = 'None'
Microsoft.PowerShell.Core\Remove-Module Microsoft.PowerShell.Utility -ErrorAction SilentlyContinue
$hashUnavailable = $false
try { $null = Get-FileHash -LiteralPath $Target -Algorithm SHA256 }
catch [Management.Automation.CommandNotFoundException] { $hashUnavailable = $true }
if (-not $hashUnavailable) { throw 'Get-FileHash must be unavailable in this fixture.' }

$result = @{ hashUnavailable = $hashUnavailable; engine = $PSVersionTable.PSVersion.ToString() }
if ($Mode -eq 'hash') {
    $result.hash = Get-BuildFileSha256 -Path $Target
    # Exclusive reopen proves the successful helper released its file handle.
    $exclusive = [IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { $result.exclusiveReopen = $true } finally { $exclusive.Dispose() }
}
elseif ($Mode -eq 'missing') {
    $result.failed = $false
    try { $result.hash = Get-BuildFileSha256 -Path $Target }
    catch { $result.failed = $true; $result.errorType = $_.Exception.GetBaseException().GetType().FullName }
}
elseif ($Mode -eq 'locked') {
    $lock = [IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $result.failed = $false
        try { $result.hash = Get-BuildFileSha256 -Path $Target }
        catch { $result.failed = $true; $result.errorType = $_.Exception.GetBaseException().GetType().FullName }
    }
    finally { $lock.Dispose() }
    $result.recoveredHash = Get-BuildFileSha256 -Path $Target
}
else { throw 'Unknown fixture mode.' }

# JSON serialization is test output only, after the hash checks have finished.
Microsoft.PowerShell.Core\Import-Module Microsoft.PowerShell.Utility
$result | ConvertTo-Json -Compress
''', encoding='utf-8')
        result = subprocess.run(
            [POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(script), str(DIRECTORY / 'build-runtime.ps1'), str(path), mode],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome['hashUnavailable'])
        return outcome

    def assert_hash(self, path, data):
        path.write_bytes(data)
        result = self.invoke(path)
        self.assertEqual(result['hash'], hashlib.sha256(data).hexdigest())
        self.assertRegex(result['hash'], r'^[0-9a-f]{64}$')
        self.assertTrue(result['exclusiveReopen'])

    def test_empty_file(self):
        self.assert_hash(self.root / 'empty.dll', b'')

    def test_binary_bytes_are_not_decoded_as_text(self):
        self.assert_hash(self.root / 'binary.exe', bytes(range(256)) + b'\x00\xff\r\n')

    def test_large_file(self):
        self.assert_hash(self.root / 'large.dll', bytes(range(256)) * 32769)

    def test_literal_unicode_and_wildcard_characters_in_path(self):
        self.assert_hash(self.root / 'published [1] \u6e38\u620f.dll', b'published bytes')

    def test_missing_file_fails_without_returning_a_digest(self):
        result = self.invoke(self.root / 'missing.exe', 'missing')
        self.assertTrue(result['failed'])
        self.assertEqual(result['errorType'], 'System.IO.FileNotFoundException')
        self.assertNotIn('hash', result)

    def test_locked_file_fails_then_recovers_after_external_lock_release(self):
        path = self.root / 'locked.dll'
        data = b'bytes protected by another reader'
        path.write_bytes(data)
        result = self.invoke(path, 'locked')
        self.assertTrue(result['failed'])
        self.assertEqual(result['errorType'], 'System.IO.IOException')
        self.assertNotIn('hash', result)
        self.assertEqual(result['recoveredHash'], hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    unittest.main()
