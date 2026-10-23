<#
.SYNOPSIS
Verify a numbered portable release and start or reuse its primary automation host.
.DESCRIPTION
Launches no game directly. BetterGI connects its minimized RDP window and launches
the game only in that child. Existing incompatible hosts require user-managed closure.
ValidateOnly reads package files without inspecting processes or launching applications.
#>
[CmdletBinding()]
param(
    [string] $TargetDirectory = '',
    [string] $ArtifactsDirectory = '',
    [string] $PythonExe = '',
    [ValidateRange(5, 180)][int] $TimeoutSeconds = 45,
    [switch] $UseApprovedTask,
    [switch] $ValidateOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ValidateOnly) {

# Refuse an administrator/high-integrity shell before importing workspace helpers.
if (-not ('BetterGIOrdinaryLauncherToken' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class BetterGIOrdinaryLauncherToken {
    [DllImport("advapi32.dll", EntryPoint="GetTokenInformation", SetLastError=true)]
    static extern bool ReadInt(IntPtr token, int kind, out int value, int size, out int needed);
    [DllImport("advapi32.dll", EntryPoint="GetTokenInformation", SetLastError=true)]
    static extern bool ReadBuffer(IntPtr token, int kind, IntPtr value, int size, out int needed);
    public static bool IsElevated(IntPtr token) {
        int elevated, needed;
        if (!ReadInt(token, 20, out elevated, 4, out needed)) throw new Win32Exception();
        if (elevated != 0) return true;
        ReadBuffer(token, 25, IntPtr.Zero, 0, out needed);
        if (needed <= 0) throw new Win32Exception();
        IntPtr buffer = Marshal.AllocHGlobal(needed);
        try {
            if (!ReadBuffer(token, 25, buffer, needed, out needed)) throw new Win32Exception();
            IntPtr sid = Marshal.ReadIntPtr(buffer);
            int count = Marshal.ReadByte(sid, 1);
            if (count < 1) throw new InvalidOperationException("Missing token integrity label.");
            return Marshal.ReadInt32(sid, 8 + 4 * (count - 1)) >= 0x3000;
        } finally { Marshal.FreeHGlobal(buffer); }
    }
}
'@
}
if ([BetterGIOrdinaryLauncherToken]::IsElevated([Security.Principal.WindowsIdentity]::GetCurrent().Token)) {
    throw 'Run this ordinary launcher from a non-elevated PowerShell or the normal desktop shortcut, not the registration administrator shell.'
}
}
Import-Module (Join-Path $PSScriptRoot 'HostLauncher.psm1') -Force
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $ArtifactsDirectory) { $ArtifactsDirectory = Join-Path $repoRoot 'artifacts' }

function Invoke-HostControl {
    param([string[]] $ControlArguments)
    $output = & $PythonExe (Join-Path $PSScriptRoot 'rdp_control.py') @ControlArguments
    if ($LASTEXITCODE -ne 0) { throw "Control CLI failed: $($output -join [Environment]::NewLine)" }
    return ($output -join [Environment]::NewLine) | ConvertFrom-Json
}

try {
    $selection = Select-VerifiedHostPackage -ArtifactsDirectory $ArtifactsDirectory -TargetDirectory $TargetDirectory
    $package = $selection.package
    if ($ValidateOnly) {
        [pscustomobject]@{ version = 1; validated = $true; package = $package; skippedPackages = $selection.skippedPackages } |
            ConvertTo-Json -Depth 8
        exit 0
    }
    if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Select an installed Python executable with -PythonExe.' }
    Add-Type -AssemblyName System.Windows.Forms
    if ([Windows.Forms.SystemInformation]::TerminalServerSession) { throw 'Run the primary-host launcher from the local desktop session.' }
    $session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    $discovery = Invoke-HostControl -ControlArguments @('discover')
    $primaries = @($discovery.instances | Where-Object { $_.instanceType -eq 'Primary' })
    $compatible = @($primaries | Where-Object { Test-HostIdentity $_ $package $session })
    $sameSessionProcesses = @(Get-Process -Name BetterGI -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })
    $launchProcessId = $null
    if ($compatible.Count -eq 1 -and $primaries.Count -eq 1 -and
        @($sameSessionProcesses | Where-Object { $_.Id -ne $compatible[0].processId }).Count -eq 0) {
        $status = $compatible[0]
        $action = 'reused'
    }
    else {
        if ($primaries.Count -gt 0 -or $sameSessionProcesses.Count -gt 0 -or @($discovery.unavailable).Count -gt 0) {
            $identities = @($sameSessionProcesses | ForEach-Object { "PID $($_.Id), session $($_.SessionId)" }) -join '; '
            throw "An incompatible, legacy, or unavailable BetterGI host already exists ($identities). Inspect discover/status and close that host normally before retrying. This launcher does not kill processes or bypass elevation."
        }
        # Recheck immediately before launch. No shell command string, installer, or credentials are involved.
        $package = Get-VerifiedHostPackage $package.targetDirectory
        if ($UseApprovedTask) {
            # This ordinary-token caller only triggers the administrator-approved fixed action.
            Import-Module (Join-Path $PSScriptRoot 'ApprovedLauncher.psm1') -Force
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $plan = Get-ApprovedLauncherPlan -RepositoryRoot $repoRoot -UserSid $sid
            if ($package.targetDirectory -ine (Select-VerifiedHostPackage -ArtifactsDirectory $plan.artifactsDirectory).package.targetDirectory) {
                throw 'The fixed approved task launches the newest verified release in its registered workspace.'
            }
            $installed = Get-Content -LiteralPath (Join-Path $plan.installationDirectory 'approved-launcher.json') -Raw | ConvertFrom-Json
            if ($installed.userSid -ne $plan.userSid -or $installed.repositoryRoot -ine $plan.repositoryRoot) { throw 'The approved installation identifies a different account or workspace.' }
            $scheduler = New-Object -ComObject Schedule.Service
            $scheduler.Connect()
            $task = $scheduler.GetFolder($plan.taskFolder).GetTask($plan.taskName)
            if (-not $task.Enabled -or -not (Test-ApprovedTaskDefinition $task.Definition $plan)) {
                throw 'The approved task is disabled or no longer has its fixed registered action. Review registration again.'
            }
            Invoke-ApprovedHostTask -Task $task -WindowsSessionId $session
        }
        else {
            $launched = Start-Process -FilePath $package.executablePath -ArgumentList @('--automation', '--desktopClone') `
                -WorkingDirectory $package.targetDirectory -WindowStyle Hidden -PassThru
            $launchProcessId = $launched.Id
        }
        $action = 'launched'
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        $status = $null
        $lastFailure = 'The control endpoint has not appeared.'
        while ([DateTime]::UtcNow -lt $deadline) {
            $currentDiscovery = $null
            try {
                $currentDiscovery = Invoke-HostControl -ControlArguments @('discover')
            }
            catch { $lastFailure = $_.Exception.Message }
            if ($null -ne $currentDiscovery) {
                $status = Select-StartedHost -Instances @($currentDiscovery.instances) -Package $package `
                    -WindowsSessionId $session -BeforeProcessIds @($sameSessionProcesses | ForEach-Object { $_.Id })
                if ($null -ne $status) { break }
            }
            Start-Sleep -Milliseconds 500
        }
        if ($null -eq $status) { throw "Host readiness timed out: $lastFailure Query discover/status before retrying; no process was terminated." }
    }
    [pscustomobject]@{
        version = 1; rootReady = $true; action = $action; launchProcessId = $launchProcessId; package = $package
        root = $status; skippedPackages = $selection.skippedPackages
    } | ConvertTo-Json -Depth 10
}
catch {
    [pscustomobject]@{ version = 1; rootReady = $false; error = $_.Exception.Message } | ConvertTo-Json -Depth 5
    exit 1
}
