<# Stable standard-token shortcut target. Genshin is requested only through an actual RDP child. #>
[CmdletBinding()]
param([ValidateSet('Host', 'Game')][string] $Mode = 'Host', [string] $PythonExe = '',
      [switch] $PreserveWindow,
      [ValidateRange(10, 180)][int] $TimeoutSeconds = 120)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

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
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$resultDirectory = Join-Path $repository 'artifacts\rdp-automation'
Import-Module (Join-Path $PSScriptRoot 'LauncherControl.psm1') -Force
$controlEvidence = [Collections.Generic.List[object]]::new()
$phase = 'initialization'

function Invoke-ApprovedControl {
    param([string[]] $Arguments)
    $reply = Invoke-LauncherJson -Executable $PythonExe -Arguments (@((Join-Path $PSScriptRoot 'rdp_control.py')) + $Arguments) `
        -Phase $Arguments[0] -TimeoutSeconds ($TimeoutSeconds + 30)
    $controlEvidence.Add($reply.process)
    return $reply.value
}

try {
    if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
    # Reuse a currently running verified numbered host, even after a newer child release was built.
    Import-Module (Join-Path $PSScriptRoot 'HostLauncher.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot 'ApprovedLauncher.psm1') -Force
    $phase = 'select_package'
    $childSelection = Select-VerifiedHostPackage -ArtifactsDirectory (Join-Path $repository 'artifacts')
    $session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    $phase = 'discover'
    $discovery = Invoke-ApprovedControl -Arguments @('discover')
    $target = ''
    $currentPackage = Select-ApprovedWarmHost -Instances @($discovery.instances) -WindowsSessionId $session -ArtifactsDirectory (Join-Path $repository 'artifacts')
    if ($null -ne $currentPackage) { $target = $currentPackage.targetDirectory }
    $phase = 'host'
    $hostOutput = & (Join-Path $PSScriptRoot 'start-host.ps1') -TargetDirectory $target -PythonExe $PythonExe `
        -UseApprovedTask -PreserveWindow:$PreserveWindow -TimeoutSeconds $TimeoutSeconds
    $hostExitCode = $LASTEXITCODE
    $hostResult = ($hostOutput -join [Environment]::NewLine) | ConvertFrom-Json
    if ($hostExitCode -ne 0) {
        $exception = [InvalidOperationException]::new("Host startup failed: $($hostResult.error)")
        $exception.Data['ControlFailure'] = [ordered]@{phase='host'; exitCode=$hostExitCode;
            stdout=($hostOutput -join [Environment]::NewLine); result=$hostResult}
        throw $exception
    }
    # Both approved links ensure a usable selected child. The lower-level
    # start-host command remains primary-only; no protected task changes are needed.
    $childArguments = @(Get-ApprovedChildArguments -Root $hostResult.root -Package $childSelection.package `
        -Mode $Mode -PreserveWindow:$PreserveWindow)
    $phase = 'ensure-child'
    $childResult = Invoke-ApprovedControl -Arguments ($childArguments + @('--timeout', [string]$TimeoutSeconds))
    $result = [ordered]@{ version = 1; success = $true; mode = $Mode; host = $hostResult;
        readinessScope = $childResult.readinessScope; selectedChild = $childResult;
        skippedPackages = $childSelection.skippedPackages; controlEvidence=@($controlEvidence.ToArray()) }
    if ($Mode -eq 'Game') { $result.game = $childResult.child }
}
catch { $result = [ordered]@{ version = 1; success = $false; mode = $Mode; phase=$phase;
    error = $_.Exception.Message; controlFailure=(Get-LauncherFailure $_); controlEvidence=@($controlEvidence.ToArray()) } }
New-Item -ItemType Directory -Path $resultDirectory -Force | Out-Null
$json = $result | ConvertTo-Json -Depth 20
[IO.File]::WriteAllText((Join-Path $resultDirectory 'last-shortcut-result.json'), $json, [Text.UTF8Encoding]::new($false))
Write-Output $json
if (-not $result.success) { exit 1 }
