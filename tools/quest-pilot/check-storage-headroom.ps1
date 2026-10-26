param([string]$Repository = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath $Repository).Path
# Storage admission depends on retained program bytes and free space. Historical
# gameplay validation checkpoints remain evidence, not prerequisites for retirement.
$taskStatusJson = & (Join-Path $PSScriptRoot '../../Build/Scripts/manage-release-retention.ps1') -Repository $taskRoot -Action Status
$taskStatus = $taskStatusJson | ConvertFrom-Json
$taskStatusJson
if (-not $taskStatus.ready) {
    throw 'Storage preflight failed: run Build/Scripts/manage-release-retention.ps1 -Action Apply and inspect its preserved-release report. Retained builds or free space exceed Build/release-retention.json limits.'
}
