# Installed in Program Files with administrator ownership. The registered task accepts no arguments.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# Never auto-load a module from the caller's profile or workspace while elevated.
$env:PSModulePath = Join-Path $PSHOME 'Modules'
Import-Module (Join-Path $PSScriptRoot 'HostLauncher.psm1') -Force
$resultFile = Join-Path $PSScriptRoot 'last-host-result.json'
try {
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'approved-launcher.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if ($config.version -ne 1 -or $identity.User.Value -ne $config.userSid -or
        -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'This fixed launcher requires its registered interactive administrator account.'
    }
    Add-Type -AssemblyName System.Windows.Forms
    $session = [Diagnostics.Process]::GetCurrentProcess().SessionId
    if ($session -le 0 -or [Windows.Forms.SystemInformation]::TerminalServerSession) {
        throw 'The approved primary launcher can run only in the local interactive desktop session.'
    }
    $selection = Select-VerifiedHostPackage -ArtifactsDirectory $config.artifactsDirectory
    $package = $selection.package
    $existing = @(Get-Process -Name BetterGI -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session })
    if ($existing.Count -gt 0) {
        throw 'BetterGI already exists in this session. The ordinary launcher must verify/reuse it; this task never terminates it.'
    }
    # Only this fixed, verified application and its fixed arguments can run elevated.
    $package = Get-VerifiedHostPackage $package.targetDirectory
    $process = Start-Process -FilePath $package.executablePath -ArgumentList @('--automation', '--desktopClone') `
        -WorkingDirectory $package.targetDirectory -WindowStyle Hidden -PassThru
    $result = [ordered]@{ version = 1; dispatched = $true; processId = $process.Id; windowsSessionId = $session;
        targetDirectory = $package.targetDirectory; dllSha256 = $package.dllSha256; timeUtc = [DateTime]::UtcNow.ToString('o') }
}
catch {
    $result = [ordered]@{ version = 1; dispatched = $false; error = $_.Exception.Message; timeUtc = [DateTime]::UtcNow.ToString('o') }
}
# Registration precreates this file with administrator ownership; do not replace its ACL/owner.
[IO.File]::WriteAllText($resultFile, ($result | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
if (-not $result.dispatched) { exit 1 }
