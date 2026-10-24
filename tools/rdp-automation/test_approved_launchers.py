"""Pure registration and target checks. These tests never register tasks or launch applications."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_start_host import DIRECTORY, POWERSHELL


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Requires Windows PowerShell.')
class ApprovedLauncherTests(unittest.TestCase):
    def run_script(self, source):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'check.ps1'
            script.write_text("param($Module)\n$ErrorActionPreference='Stop'\nImport-Module $Module -Force\n" + source)
            result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(script), str(DIRECTORY / 'ApprovedLauncher.psm1')],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_plan_has_one_protected_fixed_action_and_interactive_user(self):
        result = self.run_script('''
$sid = 'S-1-5-21-1-2-3-1001'
$plan = Get-ApprovedLauncherPlan -RepositoryRoot 'D:\work\genshin-auto' -UserSid $sid -ProgramFilesDirectory 'C:\Program Files' -WindowsDirectory 'C:\Windows'
$uncRejected = $false
try { Get-ApprovedLauncherPlan -RepositoryRoot '\\server\share' -UserSid $sid | Out-Null } catch { $uncRejected = $true }
@{ plan=$plan; uncRejected=$uncRejected } | ConvertTo-Json -Depth 8
''')
        plan = result['plan']
        self.assertEqual(plan['logonType'], 3)
        self.assertEqual(plan['runLevel'], 1)
        self.assertEqual(plan['taskPath'], '\\BetterGI Automation\\StartHost')
        self.assertEqual(plan['workingDirectory'], 'C:\\Program Files\\BetterGI Automation')
        self.assertIn('C:\\Program Files\\BetterGI Automation\\Invoke-ApprovedHost.ps1', plan['arguments'])
        self.assertNotIn('D:\\work', plan['arguments'])
        self.assertNotIn('$(', plan['arguments'])
        self.assertNotIn('-Command', plan['arguments'])
        self.assertTrue(plan['securityDescriptor'].startswith('O:BAG:SYD:P'))
        self.assertIn('(A;;GRGX;;;S-1-5-21-1-2-3-1001)', plan['securityDescriptor'])
        self.assertTrue(result['uncRejected'])

    def test_task_definition_rejects_argument_account_logon_and_action_changes(self):
        result = self.run_script('''
$plan = Get-ApprovedLauncherPlan -RepositoryRoot 'D:\work\genshin-auto' -UserSid 'S-1-5-21-1-2-3-1001'
$actions = [pscustomobject]@{ Count=0; Entries=[Collections.Generic.List[object]]::new() }
$actions | Add-Member ScriptMethod Create { param($kind)
    $item=[pscustomobject]@{ Type=$kind; Path=''; Arguments=''; WorkingDirectory='' }
    $this.Entries.Add($item); $this.Count++; return $item
}
$actions | Add-Member ScriptMethod Item { param($index) return $this.Entries[$index-1] }
$definition = [pscustomobject]@{
    RegistrationInfo=[pscustomobject]@{Description=''}
    Principal=[pscustomobject]@{UserId='';LogonType=0;RunLevel=0}
    Settings=[pscustomobject]@{Enabled=$false;Hidden=$false;AllowDemandStart=$false;DisallowStartIfOnBatteries=$true;
        StopIfGoingOnBatteries=$true;MultipleInstances=0;ExecutionTimeLimit=''}
    Actions=$actions;Triggers=[pscustomobject]@{Count=0}
}
Set-ApprovedTaskDefinition $definition $plan
$checks=[Collections.Generic.List[bool]]::new()
$checks.Add((Test-ApprovedTaskDefinition $definition $plan))
$definition.Actions.Item(1).Arguments += ' -Command whoami'
$checks.Add((Test-ApprovedTaskDefinition $definition $plan)); $definition.Actions.Item(1).Arguments=$plan.arguments
$definition.Principal.LogonType=1
$checks.Add((Test-ApprovedTaskDefinition $definition $plan)); $definition.Principal.LogonType=3
$definition.Principal.UserId='S-1-5-21-1-2-3-1002'
$checks.Add((Test-ApprovedTaskDefinition $definition $plan)); $definition.Principal.UserId=$plan.userSid
$definition.Triggers.Count=1
$checks.Add((Test-ApprovedTaskDefinition $definition $plan)); $definition.Triggers.Count=0
$definition.Actions.Count=2
$checks.Add((Test-ApprovedTaskDefinition $definition $plan))
@{ checks=@($checks.ToArray()); timeLimit=$definition.Settings.ExecutionTimeLimit;
   multipleInstances=$definition.Settings.MultipleInstances } | ConvertTo-Json
''')
        self.assertEqual(result['checks'], [True, False, False, False, False, False])
        self.assertEqual(result['timeLimit'], 'PT0S')
        self.assertEqual(result['multipleInstances'], 2)

    def test_game_arguments_require_the_exact_distinct_connected_rdp_child(self):
        result = self.run_script('''
$root=[pscustomobject]@{instanceType='Primary';automationEnabled=$true;processId=123;windowsSessionId=2;childSessionId=3;childConnectedState=1}
$child=[pscustomobject]@{instanceType='ChildSession';automationEnabled=$true;processId=456;rootProcessId=123;windowsSessionId=3;remoteDesktop=$true}
$arguments=@(Get-ApprovedGameArguments $root $child)
$rejected=[Collections.Generic.List[bool]]::new()
foreach ($change in @(@('remoteDesktop',$false), @('remoteDesktop','true'), @('instanceType','Primary'),
                      @('windowsSessionId',2), @('windowsSessionId',4), @('rootProcessId',999), @('automationEnabled',$false))) {
    $copy=$child.PSObject.Copy(); $copy.($change[0])=$change[1]
    try { Get-ApprovedGameArguments $root $copy | Out-Null; $rejected.Add($false) } catch { $rejected.Add($true) }
}
$root.childConnectedState=0
try { Get-ApprovedGameArguments $root $child | Out-Null; $rejected.Add($false) } catch { $rejected.Add($true) }
@{ arguments=$arguments; rejected=@($rejected.ToArray()) } | ConvertTo-Json
''')
        self.assertEqual(result['arguments'], ['start-game', '--process-id', '456', '--windows-session-id', '3'])
        self.assertEqual(result['rejected'], [True] * 8)

    def test_task_principal_resolves_account_names_to_exact_approved_sid(self):
        result = self.run_script('''
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$plan=Get-ApprovedLauncherPlan -RepositoryRoot 'D:\\work\\genshin-auto' -UserSid $identity.User.Value
$actions=[pscustomobject]@{Count=1;Action=[pscustomobject]@{
    Type=0;Path=$plan.executable;Arguments=$plan.arguments;WorkingDirectory=$plan.workingDirectory}}
$actions | Add-Member ScriptMethod Item { param($index) return $this.Action }
$definition=[pscustomobject]@{
    Actions=$actions;Triggers=[pscustomobject]@{Count=0}
    Principal=[pscustomobject]@{UserId=$identity.Name;LogonType=3;RunLevel=1}}
$qualifiedAccepted=Test-ApprovedTaskDefinition $definition $plan
$definition.Principal.UserId=$identity.Name.Split('\\')[-1]
$shortAccepted=Test-ApprovedTaskDefinition $definition $plan
$definition.Principal.UserId='NT AUTHORITY\\SYSTEM'
$wrongAccepted=Test-ApprovedTaskDefinition $definition $plan
$definition.Principal.UserId='BetterGI-No-Such-Account-'+[guid]::NewGuid().ToString('N')
$unknownAccepted=Test-ApprovedTaskDefinition $definition $plan
@{qualifiedAccepted=$qualifiedAccepted;shortAccepted=$shortAccepted;
  wrongAccepted=$wrongAccepted;unknownAccepted=$unknownAccepted} | ConvertTo-Json
''')
        self.assertEqual(result, {'qualifiedAccepted': True, 'shortAccepted': True,
                                  'wrongAccepted': False, 'unknownAccepted': False})

    def test_all_launcher_scripts_parse_without_execution(self):
        result = self.run_script('''
$directory=Split-Path -Parent $Module
$failures=@(Get-ChildItem -LiteralPath $directory -File | Where-Object { $_.Extension -in '.ps1','.psm1' } | ForEach-Object {
    $tokens=$null; $errors=$null
    $null=[System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors)
    if ($errors) { $_.Name }
})
ConvertTo-Json -InputObject @{failures=$failures}
''')
        self.assertEqual(result['failures'], [])

    def test_warm_window_plan_minimizes_only_existing_window_unless_preserved(self):
        result = self.run_script('''
$root=[pscustomobject]@{processId=123;windowsSessionId=2;childConnectedState=1;childWindowMinimized=$false;uiStatus='current'}
$shown=@(Get-WarmHostWindowArguments -Status $root)
$preserved=@(Get-WarmHostWindowArguments -Status $root -PreserveWindow)
$root.childWindowMinimized=$true
$alreadyMinimized=@(Get-WarmHostWindowArguments -Status $root)
$root.childWindowMinimized=$false; $root.childConnectedState=0
$disconnected=@(Get-WarmHostWindowArguments -Status $root)
$root.childConnectedState=1; $root.uiStatus='timeout'
$degradedRejected=$false
try { Get-WarmHostWindowArguments -Status $root | Out-Null } catch { $degradedRejected=$true }
@{shown=$shown;preserved=$preserved;alreadyMinimized=$alreadyMinimized;disconnected=$disconnected;degradedRejected=$degradedRejected} | ConvertTo-Json
''')
        self.assertEqual(result['shown'], ['minimize', '--process-id', '123', '--windows-session-id', '2'])
        for key in ('preserved', 'alreadyMinimized', 'disconnected'):
            self.assertEqual(result[key], [])
        self.assertTrue(result['degradedRejected'])

    def test_task_dispatch_binds_console_session_without_action_parameters(self):
        result = self.run_script('''
$task=[pscustomobject]@{Calls=[Collections.Generic.List[object]]::new()}
$task | Add-Member ScriptMethod RunEx { param($taskParameters,$flags,$sessionId,$runUser)
    $this.Calls.Add(@{parametersAreNull=($null -eq $taskParameters);flags=$flags;sessionId=$sessionId;userIsNull=($null -eq $runUser)})
}
Invoke-ApprovedHostTask -Task $task -WindowsSessionId 2
$zeroRejected=$false
try { Invoke-ApprovedHostTask -Task $task -WindowsSessionId 0 } catch { $zeroRejected=$true }
@{calls=@($task.Calls.ToArray());zeroRejected=$zeroRejected} | ConvertTo-Json -Depth 5
''')
        self.assertEqual(result['calls'], [{'parametersAreNull': True, 'flags': 4, 'sessionId': 2, 'userIsNull': True}])
        self.assertTrue(result['zeroRejected'])

    def test_both_shortcut_modes_pin_selected_child_separately_from_existing_root(self):
        result = self.run_script('''
$root=[pscustomobject]@{instanceType='Primary';automationEnabled=$true;remoteDesktop=$false;
    processId=123;windowsSessionId=2;instanceNonce='root-epoch';appDirectory='D:\\old-root'}
$package=[pscustomobject]@{targetDirectory='D:\\selected-child';exeSha256=('a'*64);dllSha256=('b'*64)}
$hostArgs=@(Get-ApprovedChildArguments -Root $root -Package $package -Mode Host)
$gameArgs=@(Get-ApprovedChildArguments -Root $root -Package $package -Mode Game -PreserveWindow)
$invalidNonceRejected=$false
$root.instanceNonce=''
try { Get-ApprovedChildArguments -Root $root -Package $package -Mode Host | Out-Null } catch { $invalidNonceRejected=$true }
@{hostArgs=$hostArgs;gameArgs=$gameArgs;invalidNonceRejected=$invalidNonceRejected} | ConvertTo-Json
''')
        common = ['ensure-child', '--process-id', '123', '--windows-session-id', '2',
                  '--instance-nonce', 'root-epoch', '--target-directory', 'D:\\selected-child',
                  '--exe-sha256', 'a' * 64, '--dll-sha256', 'b' * 64]
        self.assertEqual(result['hostArgs'], common)
        self.assertEqual(result['gameArgs'], common + ['--preserve-window', '--start-game'])
        self.assertTrue(result['invalidNonceRejected'])

    def test_install_result_is_bounded_and_does_not_overwrite_hard_link_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'artifacts' / 'rdp-automation' / 'registration-result.json'
            output.parent.mkdir(parents=True)
            sentinel = root / 'sentinel.json'
            sentinel.write_text('unchanged')
            os.link(sentinel, output)
            root_literal = str(root).replace("'", "''")
            result = self.run_script("$repository='" + root_literal + "'\n" + '''
# Load only the diagnostic function, never the installer's top-level executable statements.
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path (Split-Path -Parent $Module) 'register-approved-launchers.ps1'), [ref]$tokens, [ref]$errors)
$definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Write-RegistrationResult'}, $true)
. ([scriptblock]::Create($definition.Extent.Text))
Write-RegistrationResult @{version=1;installed=$false;error='example failure'}
$largeRejected=$false
try { Write-RegistrationResult @{error=('x'*70000)} } catch { $largeRejected=$true }
@{largeRejected=$largeRejected;stored=(Get-Content -LiteralPath (Join-Path $repository 'artifacts/rdp-automation/registration-result.json') -Raw | ConvertFrom-Json)} | ConvertTo-Json -Depth 5
''')
            self.assertTrue(result['largeRejected'])
            self.assertEqual(result['stored']['error'], 'example failure')
            self.assertFalse(result['stored']['installed'])
            self.assertEqual(sentinel.read_text(), 'unchanged')
            self.assertFalse(output.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_warm_start_reuses_verified_r1_even_when_r3_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in (1, 3):
                target = root / f'release-r{number}' / 'BetterGI-English-win-x64'
                target.mkdir(parents=True)
                for name in ('BetterGI.exe', 'BetterGI.dll', 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll',
                             'System.Private.CoreLib.dll', 'PresentationFramework.dll'):
                    (target / name).write_bytes(b'synthetic')
                (target / 'BetterGI.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {
                    'tfm': 'net10.0', 'includedFrameworks': [{'name': name, 'version': '10.0.4'} for name in
                        ('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App', 'Microsoft.AspNetCore.App')]}}))
                (target / 'BetterGI.deps.json').write_text(json.dumps({'runtimeTarget': {'name': '.NETCoreApp,Version=v10.0/win-x64'}}))
                digest = hashlib.sha256(b'synthetic').hexdigest()
                (target.parent / 'build-manifest.json').write_text(json.dumps({
                    'version': 1, 'targetDirectory': str(target), 'exeSha256': digest, 'dllSha256': digest}))
            fixture = root / 'warm.json'
            fixture.write_text(json.dumps({'artifacts': str(root), 'status': {
                'instanceType': 'Primary', 'automationEnabled': True, 'remoteDesktop': False,
                'windowsSessionId': 2, 'processId': 123, 'instanceNonce': 'root-r1',
                'appDirectory': str(root / 'release-r1' / 'BetterGI-English-win-x64'), 'assemblySha256': digest}}))
            fixture_literal = str(fixture).replace("'", "''")
            result = self.run_script("$fixture = Get-Content -LiteralPath '" + fixture_literal + "' -Raw | ConvertFrom-Json\n" + '''
Import-Module (Join-Path (Split-Path -Parent $Module) 'HostLauncher.psm1') -Force
$cold=Select-VerifiedHostPackage -ArtifactsDirectory $fixture.artifacts
$warm=Select-ApprovedWarmHost -Instances @($fixture.status) -WindowsSessionId 2 -ArtifactsDirectory $fixture.artifacts
$fixture.status.assemblySha256='0'*64
$mismatchRejected=$false
try { Select-ApprovedWarmHost -Instances @($fixture.status) -WindowsSessionId 2 -ArtifactsDirectory $fixture.artifacts | Out-Null }
catch { $mismatchRejected=$true }
@{coldRelease=$cold.package.release;warmRelease=$warm.release;mismatchRejected=$mismatchRejected} | ConvertTo-Json
''')
            self.assertEqual(result, {'coldRelease': 3, 'warmRelease': 1, 'mismatchRejected': True})


if __name__ == '__main__':
    unittest.main()
