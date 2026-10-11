$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'recover-rdp-host.ps1')

function New-TestCollection {
    param([object[]]$Items)
    $collection = [pscustomobject]@{ Count = $Items.Count; Values = $Items }
    $collection | Add-Member -MemberType ScriptMethod -Name Item -Value { param($Index) return $this.Values[$Index - 1] }
    return $collection
}

function New-TestTask {
    $appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../artifacts/release-r11/BetterGI-English-win-x64'))
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $action = [pscustomobject]@{
        Type = 0
        Path = Join-Path $appRoot 'BetterGI.exe'
        Arguments = '--desktopClone'
        WorkingDirectory = $appRoot
    }
    $definition = [pscustomobject]@{
        Principal = [pscustomobject]@{ UserId = $currentSid; LogonType = 3; RunLevel = 1 }
        Settings = [pscustomobject]@{ ExecutionTimeLimit = 'PT0S'; MultipleInstances = 0 }
        Triggers = New-TestCollection @()
        Actions = New-TestCollection @($action)
    }
    return [pscustomobject]@{ Enabled = $true; Definition = $definition }
}

function Assert-Throws {
    param([scriptblock]$Body, [string]$ExpectedMessage)
    try { & $Body } catch {
        if ($_.Exception.Message -like "*$ExpectedMessage*") { return }
        throw "Expected error containing '$ExpectedMessage', got '$($_.Exception.Message)'"
    }
    throw "Expected an error containing '$ExpectedMessage'"
}

$task = New-TestTask
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$appRoot = Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid
if ((Split-Path -Leaf $appRoot) -ne 'BetterGI-English-win-x64') { throw 'Valid task returned the wrong application directory.' }
if ((Convert-AccountNameToSid -AccountName ([Security.Principal.WindowsIdentity]::GetCurrent().Name)) -ne $currentSid) {
    throw 'Account-name principal did not resolve to the current user SID.'
}
Assert-Throws { Assert-RecoveryCallerSession -SessionId 2 } 'Windows session 1'
Assert-RecoveryCallerSession -SessionId 1

$task = New-TestTask
$task.Definition.Actions.Item(1).Arguments = '--desktopClone --arbitrary'
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'fixed --desktopClone'

$task = New-TestTask
$task.Definition.Principal.UserId = 'S-1-5-21-111-222-333'
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'current user'

$task = New-TestTask
$task.Definition.Principal.LogonType = 2
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'interactive token'

$task = New-TestTask
$task.Definition.Principal.RunLevel = 0
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'highest available level'

$task = New-TestTask
$task.Definition.Settings.ExecutionTimeLimit = 'PT1H'
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'no execution time limit'

$task = New-TestTask
$task.Definition.Settings.MultipleInstances = 2
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'allow parallel activation'

$task = New-TestTask
$task.Definition.Triggers = New-TestCollection @([pscustomobject]@{})
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'no triggers'

$task = New-TestTask
$task.Definition.Actions.Item(1).WorkingDirectory = $env:TEMP
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'working directory'

$task = New-TestTask
$task.Definition.Actions.Item(1).Path = Join-Path $env:TEMP 'untrusted.exe'
Assert-Throws { Assert-RecoveryTaskContract -Task $task -CurrentUserSid $currentSid } 'outside a staged release'

Write-Output 'Recovery-task contract tests passed (SID/name identity, caller session, task contract, and rejection of altered action or paths).'
