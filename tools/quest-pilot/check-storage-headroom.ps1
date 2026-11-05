param([string]$Repository = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)), [string]$PublishDirectory)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath $Repository).Path
# Storage admission depends on retained program bytes and free space. Historical
# gameplay validation checkpoints remain evidence, not prerequisites for retirement.
$taskAdmission = @{ Repository = $taskRoot; Action = 'Status' }
if ($PublishDirectory) {
    $taskAdmission.Action = 'RecoverCapacity'
    $taskAdmission.PublishDirectory = $PublishDirectory
}
$taskStatusJson = & (Join-Path $PSScriptRoot '../../Build/Scripts/manage-release-retention.ps1') @taskAdmission
$taskStatus = $taskStatusJson | ConvertFrom-Json
$taskStatusJson
if (-not $taskStatus.ready) {
    if ($PublishDirectory) {
        throw "Storage preflight failed after release retention: $($taskStatus.buildBytes) program bytes and $($taskStatus.freeBytes) free bytes; no eligible previous release restored the configured limits."
    }
    throw 'Storage preflight failed: run Build/Scripts/manage-release-retention.ps1 -Action Apply and inspect its preserved-release report. Retained builds or free space exceed Build/release-retention.json limits.'
}
