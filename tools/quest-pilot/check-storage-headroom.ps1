param([string]$Repository = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath $Repository).Path
$taskArtifacts = Join-Path $taskRoot 'artifacts'
$taskFree = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskRoot))).AvailableFreeSpace
$taskBuildBytes = 0L
$taskPending = @()
if (Test-Path -LiteralPath $taskArtifacts) {
    foreach ($taskBuild in Get-ChildItem -LiteralPath $taskArtifacts -Directory) {
        if ($taskBuild.Name -notmatch '^(release(-r[0-9]+)?|BetterGI-English-win-x64|r[0-9]+-native-publish)$') { continue }
        $taskApp=Join-Path $taskBuild.FullName 'BetterGI-English-win-x64'
        $taskCheckpoint=Join-Path $taskApp 'User/ExternalControl/retention-checkpoint.json'
        if ((Test-Path -LiteralPath (Join-Path $taskApp 'BetterGI.dll')) -and (Test-Path -LiteralPath $taskCheckpoint)) {
            $taskRecord=Get-Content -LiteralPath $taskCheckpoint -Raw | ConvertFrom-Json
            if ($taskRecord.state -ne 'completed' -or (Get-FileHash -LiteralPath (Join-Path $taskApp 'BetterGI.dll')).Hash -ne $taskRecord.dllSha256) {
                $taskPending += $taskCheckpoint
            }
        }
        foreach ($taskFile in Get-ChildItem -LiteralPath $taskBuild.FullName -Recurse -File) {
            $taskRelative = [IO.Path]::GetRelativePath($taskBuild.FullName, $taskFile.FullName)
            if ($taskRelative -match '(^|[\\/])(User|Logs?|observations|reports|receipts)([\\/]|$)') { continue }
            $taskBuildBytes += $taskFile.Length
        }
    }
}
[pscustomobject]@{utc=(Get-Date).ToUniversalTime().ToString('o');freeBytes=$taskFree;
    minimumFreeBytes=4GB;buildBytes=$taskBuildBytes;maximumBuildBytes=4GB;
    pendingRetirementCheckpoints=$taskPending;
    ready=($taskFree -ge 4GB -and $taskBuildBytes -le 4GB -and $taskPending.Count -eq 0)} | ConvertTo-Json
if ($taskFree -lt 4GB -or $taskBuildBytes -gt 4GB -or $taskPending.Count -gt 0) {
    throw 'Storage preflight failed: retain active/rollback runtimes and unique evidence; obtain exact cleanup approval before building, staging, pushing or merging.'
}
