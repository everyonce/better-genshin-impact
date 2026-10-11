param([Parameter(Mandatory=$true)][string]$AppDirectory)
$ErrorActionPreference = 'Stop'
$sessionId = [Diagnostics.Process]::GetCurrentProcess().SessionId
if ($sessionId -ne 5) { throw 'Run this launcher inside the BetterGI RDP desktop (Windows session 5).' }
$existing = @(Get-Process BetterGI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $sessionId)
if ($existing.Count) { throw 'Exit only the BetterGI child from its tray menu first. Leave the outer Desktop Clone window open.' }
$root = (Resolve-Path -LiteralPath $AppDirectory).Path
$exe = Join-Path $root 'BetterGI.exe'
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'The staged BetterGI executable is missing.' }
$marker = Join-Path $root 'User/ExternalControl/enable-quest-control.json'
$optIn = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
if ($optIn.version -ne 1 -or $optIn.enabled -ne $true) { throw 'External quest control is not enabled for this build.' }
# This first launch is interactive. Later updates use the running child's fixed restartApp command.
Start-Process -FilePath $exe -ArgumentList '--instance','childsession' -WorkingDirectory $root -WindowStyle Hidden
