<#
.SYNOPSIS
Prepare fixed launch shortcuts, or install their single approved task with -Install.
.DESCRIPTION
The default is a read-only registration plan. -PrepareShortcuts writes only workspace
shortcuts. -Install must be explicitly run from an elevated PowerShell after reviewing
the plan; it copies protected helpers and registers a current-user InteractiveToken task.
#>
[CmdletBinding()]
param([switch] $Install, [switch] $PrepareShortcuts)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))

function Get-RegistrationSha256 {
    param([string] $Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Write-RegistrationResult {
    param($Result)
    # Installation only: keep hidden UAC results inspectable without a second elevated wrapper.
    $directory = Join-Path $repository 'artifacts\rdp-automation'
    $path = [IO.Path]::GetFullPath((Join-Path $directory 'registration-result.json'))
    if (-not $path.StartsWith($repository.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Registration result escaped the workspace.' }
    $ancestor = $path
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            if (((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Registration results cannot use redirected paths.' }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
    $json = $Result | ConvertTo-Json -Depth 8
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    if ($bytes.Length -gt 65536) { throw 'Registration result exceeded the 64 KiB limit.' }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    # Unlink an old result, then create exclusively; never overwrite a hard-link target.
    if ([IO.File]::Exists($path)) { [IO.File]::Delete($path) }
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Set-ProtectedLauncherAcl {
    param([string] $Path, [bool] $Directory)
    # Administrators own every installed object; the filtered user token cannot rewrite its DACL.
    $acl = if ($Directory) { [Security.AccessControl.DirectorySecurity]::new() } else { [Security.AccessControl.FileSecurity]::new() }
    $acl.SetAccessRuleProtection($true, $false)
    $admins = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $user = [Security.Principal.SecurityIdentifier]::new($plan.userSid)
    $acl.SetOwner($admins)
    $inherit = if ($Directory) { [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit' } else { [Security.AccessControl.InheritanceFlags]::None }
    foreach ($account in @($admins, $system)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($account, 'FullControl', $inherit, 'None', 'Allow'))
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($user, 'ReadAndExecute', $inherit, 'None', 'Allow'))
    Set-Acl -LiteralPath $Path -AclObject $acl
}

try {
    Import-Module (Join-Path $PSScriptRoot 'ApprovedLauncher.psm1') -Force
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $plan = Get-ApprovedLauncherPlan -RepositoryRoot $repository -UserSid $identity.User.Value
    $helperHashes = @{}
    foreach ($name in $plan.installedFiles) { $helperHashes[$name] = Get-RegistrationSha256 (Join-Path $PSScriptRoot $name) }
    $plan | Add-Member -NotePropertyName helperSha256 -NotePropertyValue $helperHashes
    if ($PrepareShortcuts) {
        $directory = Join-Path $PSScriptRoot 'shortcuts'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $shell = New-Object -ComObject WScript.Shell
        foreach ($entry in @(@('Start BetterGI', 'Host'), @('Start Genshin in RDP', 'Game'))) {
            $shortcut = $shell.CreateShortcut((Join-Path $directory ($entry[0] + '.lnk')))
            $shortcut.TargetPath = $plan.executable
            $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot 'start-approved.ps1') + '" -Mode ' + $entry[1]
            $shortcut.WorkingDirectory = $repository
            $shortcut.WindowStyle = 7
            $shortcut.Description = 'Use the approved BetterGI host; game launch is restricted to its RDP child.'
            $shortcut.Save()
        }
    }
    if ($Install) {
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'Review the plan, then run this exact script with -Install from an elevated PowerShell. It will not request elevation itself.'
        }
        if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit Windows PowerShell for registration.' }
        # Reject redirects and foreign existing installations before changing protected files.
        $ancestor = $plan.installationDirectory
        while ($ancestor) {
            if (Test-Path -LiteralPath $ancestor) {
                $item = Get-Item -LiteralPath $ancestor -Force
                if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'The installation path contains a reparse point.' }
            }
            $ancestor = Split-Path -Parent $ancestor
            if (-not $ancestor) { break }
        }
        $configPath = Join-Path $plan.installationDirectory 'approved-launcher.json'
        if (Test-Path -LiteralPath $plan.installationDirectory) {
            if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'A foreign installation already occupies the protected directory.' }
            $old = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            if ($old.userSid -ne $plan.userSid -or $old.repositoryRoot -ine $plan.repositoryRoot) { throw 'The existing registration belongs to a different account or repository.' }
        }
        New-Item -ItemType Directory -Path $plan.installationDirectory -Force | Out-Null
        Set-ProtectedLauncherAcl $plan.installationDirectory $true
        foreach ($metadataName in @('approved-launcher.json', 'last-host-result.json')) {
            $metadataPath = Join-Path $plan.installationDirectory $metadataName
            if (Test-Path -LiteralPath $metadataPath) {
                if (((Get-Item -LiteralPath $metadataPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Installed metadata must not be redirected.' }
                Set-ProtectedLauncherAcl $metadataPath $false
            }
        }
        foreach ($name in $plan.installedFiles) {
            $destination = Join-Path $plan.installationDirectory $name
            if (Test-Path -LiteralPath $destination) {
                if (((Get-Item -LiteralPath $destination -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'An installed helper is a reparse point.' }
                Set-ProtectedLauncherAcl $destination $false
            }
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $destination -Force
            Set-ProtectedLauncherAcl $destination $false
            if ((Get-RegistrationSha256 $destination) -ne $helperHashes[$name]) { throw 'A protected helper changed while being copied; registration was stopped.' }
        }
        [IO.File]::WriteAllText($configPath, ($plan | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
        Set-ProtectedLauncherAcl $configPath $false
        $resultPath = Join-Path $plan.installationDirectory 'last-host-result.json'
        [IO.File]::WriteAllText($resultPath, '{"version":1,"dispatched":false,"state":"registered"}', [Text.UTF8Encoding]::new($false))
        Set-ProtectedLauncherAcl $resultPath $false
        $scheduler = New-Object -ComObject Schedule.Service
        $scheduler.Connect()
        try { $folder = $scheduler.GetFolder($plan.taskFolder) }
        catch { $folder = $scheduler.GetFolder('\').CreateFolder($plan.taskFolder, $plan.securityDescriptor) }
        $definition = $scheduler.NewTask(0)
        Set-ApprovedTaskDefinition $definition $plan
        $task = $folder.RegisterTaskDefinition($plan.taskName, $definition, 6, $plan.userSid, $null, 3, $plan.securityDescriptor)
        $task.SetSecurityDescriptor($plan.securityDescriptor, 0)
        if (-not (Test-ApprovedTaskDefinition $task.Definition $plan)) { throw 'Registered task verification failed.' }
    }
    $report = [pscustomobject]@{ version = 1; installed = [bool]$Install; shortcutsPrepared = [bool]$PrepareShortcuts; plan = $plan }
    if ($Install) { Write-RegistrationResult $report }
    $report | ConvertTo-Json -Depth 8
}
catch {
    $message = $_.Exception.Message
    if ($message.Length -gt 4096) { $message = $message.Substring(0, 4096) }
    $report = [ordered]@{ version = 1; installed = $false; error = $message }
    if ($Install) {
        try { Write-RegistrationResult $report }
        catch { $report.resultWriteError = $_.Exception.Message.Substring(0, [Math]::Min(1024, $_.Exception.Message.Length)) }
    }
    $report | ConvertTo-Json
    exit 1
}
