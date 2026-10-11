param([Parameter(Mandatory=$true)][string]$AppDirectory)
$ErrorActionPreference = 'Stop'
$artifactsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../artifacts'))
$appRoot = (Resolve-Path -LiteralPath $AppDirectory).Path
$releaseRoot = Split-Path -Parent $appRoot
if ((Split-Path -Leaf $appRoot) -ne 'BetterGI-English-win-x64' -or
    (Split-Path -Leaf $releaseRoot) -notmatch '^release-r[0-9]+$' -or
    (Split-Path -Parent $releaseRoot) -ne $artifactsRoot) {
    throw 'Use a staged release inside this BetterGI workspace.'
}
$manifest = Get-Content -LiteralPath (Join-Path $appRoot 'Host-Launcher.json') -Raw | ConvertFrom-Json
if ($manifest.version -ne 1 -or $manifest.desktopClone -ne $true) {
    throw 'This build does not declare support for direct desktop-clone startup.'
}
foreach ($name in @('BetterGI.exe','BetterGI.dll')) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $appRoot $name) -Algorithm SHA256).Hash
    if ($actual -ne $manifest.sha256.$name) { throw "Staged file hash mismatch: $name" }
}
$sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
if ($sessionId -ne 1) { throw 'Run this host launcher on the main desktop, Windows session 1.' }
$existing = @(Get-Process BetterGI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $sessionId)
if ($existing.Count) { throw 'A main-desktop BetterGI is already running. Exit it from its tray menu first.' }
# Start the exact workspace executable. App-name launchers can select the installed copy.
# Windows may require the user to accept elevation; no credentials or game input are sent here.
$process = Start-Process -FilePath (Join-Path $appRoot 'BetterGI.exe') -ArgumentList '--desktopClone' -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru
Write-Output "Desktop-clone host launch dispatched: PID $($process.Id), build $appRoot"
