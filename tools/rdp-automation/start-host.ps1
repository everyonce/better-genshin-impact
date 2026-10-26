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
    [switch] $PreserveWindow,
    [switch] $ValidateOnly,
    [switch] $ValidateApprovedTask,
    # Opt-in existing-session lifetime binding; no installed task arguments are changed.
    [ValidateRange(0, 2147483647)][int] $UpgradeSessionId = 0,
    [ValidateRange(0, 2147483647)][int] $UpgradeGameProcessId = 0,
    [ValidateRange(0, 9223372036854775807)][long] $UpgradeGameStartedFileTime = 0
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$upgrade = $UpgradeSessionId -ne 0 -or $UpgradeGameProcessId -ne 0 -or $UpgradeGameStartedFileTime -ne 0
if ($upgrade -and ($UpgradeSessionId -le 0 -or $UpgradeGameProcessId -le 0 -or $UpgradeGameStartedFileTime -le 0 -or -not $UseApprovedTask -or $PreserveWindow)) {
    throw 'Upgrade startup requires all existing lifetime fields, the approved fixed task and a minimized root.'
}
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
Import-Module (Join-Path $PSScriptRoot 'LauncherControl.psm1') -Force
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $ArtifactsDirectory) { $ArtifactsDirectory = Join-Path $repoRoot 'artifacts' }

function Invoke-HostControl {
    param([string[]] $ControlArguments)
    $reply = Invoke-LauncherJson -Executable $PythonExe -Arguments (@((Join-Path $PSScriptRoot 'rdp_control.py')) + $ControlArguments) `
        -Phase ('host/' + $ControlArguments[0]) -TimeoutSeconds ($TimeoutSeconds + 30)
    return $reply.value
}

# Validate the exact existing installation without installing/reconfiguring or launching anything.
function Get-VerifiedApprovedTask {
    param($Package)
    # Use this PowerShell installation's hash commands, not an inherited Core/Windows module mix.
    # This process-local import does not change the protected task or installed helpers.
    Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -Force -ErrorAction Stop
    Import-Module (Join-Path $PSScriptRoot 'ApprovedLauncher.psm1') -Force
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $plan = Get-ApprovedLauncherPlan -RepositoryRoot $repoRoot -UserSid $sid
    if ($package.targetDirectory -ine (Select-VerifiedHostPackage -ArtifactsDirectory $plan.artifactsDirectory).package.targetDirectory) {
        throw 'The fixed approved task launches the newest verified release in its registered workspace.'
    }
    $configPath = Join-Path $plan.installationDirectory 'approved-launcher.json'
    if ((Get-Item -LiteralPath $configPath).Length -gt 65536) { throw 'Approved launcher configuration exceeds 64 KiB.' }
    $installed = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($installed.version -ne 1 -or $installed.artifactsDirectory -ine $plan.artifactsDirectory) { throw 'Approved launcher configuration differs from the fixed workspace.' }
    foreach ($name in $plan.installedFiles) {
        $installedPath = Join-Path $plan.installationDirectory $name
        if ((Get-Item -LiteralPath $installedPath).Length -gt 1048576 -or
            (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash) {
            throw 'The installed approved helper differs from the reviewed fixed helper. No automatic installation or repair.'
        }
    }
    if ($installed.userSid -ne $plan.userSid -or $installed.repositoryRoot -ine $plan.repositoryRoot) { throw 'The approved installation identifies a different account or workspace.' }
    $scheduler = New-Object -ComObject Schedule.Service
    $scheduler.Connect()
    $task = $scheduler.GetFolder($plan.taskFolder).GetTask($plan.taskName)
    if (-not $task.Enabled -or -not (Test-ApprovedTaskDefinition $task.Definition $plan)) {
        throw 'The approved task is disabled or no longer has its fixed registered action. Review registration again.'
    }
    return $task
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
    if ($ValidateApprovedTask) {
        $null = Get-VerifiedApprovedTask -Package $package
        [pscustomobject]@{ version = 1; approvedTaskVerified = $true; windowsSessionId = $session; package = $package } | ConvertTo-Json -Depth 8
        exit 0
    }
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
            $task = Get-VerifiedApprovedTask -Package $package
            Import-Module (Join-Path $PSScriptRoot 'ApprovedLauncher.psm1') -Force
            Invoke-ApprovedHostTask -Task $task -WindowsSessionId $session
        }
        else {
            $startupArguments = @('--automation', '--desktopClone')
            $launched = Start-Process -FilePath $package.executablePath -ArgumentList $startupArguments `
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
    if ($upgrade -and ($action -ne 'launched' -or $status.puloniaSchedulingHeld -ne $true -or
            $status.upgradeSessionId -ne $UpgradeSessionId -or $status.upgradeGameProcessId -ne $UpgradeGameProcessId -or
            $status.upgradeGameStartedFileTime -ne $UpgradeGameStartedFileTime)) {
        throw 'The new root did not retain the exact scheduling hold and existing game/session binding.'
    }
    if ($action -eq 'reused') {
        Import-Module (Join-Path $PSScriptRoot 'ApprovedLauncher.psm1') -Force
        $windowArguments = @(Get-WarmHostWindowArguments -Status $status -PreserveWindow:$PreserveWindow)
        if ($windowArguments.Count -gt 0) {
            $updated = Invoke-HostControl -ControlArguments ($windowArguments + @('--timeout', [string]$TimeoutSeconds))
            if (-not (Test-HostIdentity $updated $package $session $status.processId) -or
                $updated.instanceNonce -cne $status.instanceNonce -or $updated.childWindowMinimized -ne $true) {
                throw 'The primary identity or minimized window state changed during warm startup.'
            }
            $status = $updated
        }
    }
    [pscustomobject]@{
        version = 1; rootReady = $true; action = $action; launchProcessId = $launchProcessId; package = $package
        readinessScope = 'primary_control_endpoint'; rdpConnected = ($status.childConnectedState -eq 1)
        root = $status; skippedPackages = $selection.skippedPackages
    } | ConvertTo-Json -Depth 10
}
catch {
    [pscustomobject]@{ version = 1; rootReady = $false; error = $_.Exception.Message;
        controlFailure=(Get-LauncherFailure $_) } | ConvertTo-Json -Depth 20
    exit 1
}
exit 0
