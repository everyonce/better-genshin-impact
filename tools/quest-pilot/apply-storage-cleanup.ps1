param(
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ApprovedSha256,
    [Parameter(Mandatory)][string[]]$ProtectedRuntimeDirectories,
    [Parameter(Mandatory)][string]$AuditPath,
    [string]$CompleteRuntimeCheckpoint,
    [switch]$HistoricalWritersStopped
)
$ErrorActionPreference = 'Stop'
if (-not ('ApprovedFileCleanup' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'ApprovedFileCleanup.cs') }
$taskRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskArtifacts = (Join-Path $taskRepository 'artifacts').TrimEnd('\') + '\'
$taskManifestPath = (Resolve-Path -LiteralPath $Manifest).Path
if ((Get-FileHash -LiteralPath $taskManifestPath -Algorithm SHA256).Hash -ne $ApprovedSha256) { throw 'Manifest differs from the exact approved batch' }
$taskPlan = Get-Content -LiteralPath $taskManifestPath -Raw | ConvertFrom-Json
if ($taskPlan.version -ne 1 -or $taskPlan.files -ne @($taskPlan.candidates).Count) { throw 'Invalid cleanup manifest' }
$taskHistorical=$taskPlan.mode -eq 'historical-plan-only'
if ($taskHistorical) {
    if (-not $HistoricalWritersStopped) { throw 'Historical capture cleanup requires verified stopped writers' }
    $taskCaptureRoot=(Resolve-Path -LiteralPath $taskPlan.root).Path.TrimEnd('\')+'\'
    if (-not $taskCaptureRoot.StartsWith($taskArtifacts,[StringComparison]::OrdinalIgnoreCase) -or
        $taskCaptureRoot -notmatch '\\release-r[0-9]+\\BetterGI-English-win-x64\\User\\JsScript\\ActOnePilot\\$') { throw 'Historical cleanup must target one approved portable ActOnePilot tree' }
    $taskWitness=@($taskPlan.reports | Sort-Object bytes | Select-Object -First 1)
    if ($taskWitness.Count -ne 1) { throw 'Historical cleanup requires a preserved report witness' }
}
if (@($taskPlan.candidates | Where-Object kind -eq 'superseded-build').Count -gt 0 -and -not $CompleteRuntimeCheckpoint) { throw 'Build retirement requires its verified installed runtime checkpoint' }
$taskProtected = @($ProtectedRuntimeDirectories | ForEach-Object { (Resolve-Path -LiteralPath $_).Path.TrimEnd('\') + '\' })
if ($taskProtected.Count -lt 1) { throw 'Known active and rollback runtime directories are required' }
$taskCheckpointRecord = $null
if ($CompleteRuntimeCheckpoint) {
    $taskCheckpointPath=(Resolve-Path -LiteralPath $CompleteRuntimeCheckpoint).Path
    for ($taskWalkPath=$taskCheckpointPath; $taskWalkPath; $taskWalkPath=(Split-Path -Parent $taskWalkPath)) {
        if ((Get-Item -LiteralPath $taskWalkPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime checkpoint rejected' }
    }
    if (-not ($taskProtected | Where-Object { $taskCheckpointPath.StartsWith($_,[StringComparison]::OrdinalIgnoreCase) })) { throw 'Checkpoint must belong to a protected installed runtime' }
    $taskCheckpointRecord=Get-Content -LiteralPath $taskCheckpointPath -Raw | ConvertFrom-Json
    $taskExpectedCheckpoint=[IO.Path]::GetFullPath((Join-Path $taskCheckpointRecord.appDirectory 'User/ExternalControl/retention-checkpoint.json'))
    if ($taskExpectedCheckpoint -ne $taskCheckpointPath) { throw 'Checkpoint runtime directory mismatch' }
    if ($taskCheckpointRecord.state -ne 'cleanup-approval-required' -or $taskCheckpointRecord.cleanupManifestSha256 -ne $ApprovedSha256 -or
        (Get-FileHash -LiteralPath (Join-Path $taskCheckpointRecord.appDirectory 'BetterGI.dll')).Hash -ne $taskCheckpointRecord.dllSha256) { throw 'Installed verification checkpoint does not match this approved cleanup' }
}
$taskSeen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$taskTotal = 0L
function Assert-OrdinaryFile([string]$Path, [switch]$EvidenceReference) {
    $taskFull = [IO.Path]::GetFullPath($Path)
    $taskGenerated = $taskFull.StartsWith($taskRepository.TrimEnd('\')+'\', [StringComparison]::OrdinalIgnoreCase) -and
        [IO.Path]::GetRelativePath($taskRepository,$taskFull) -match '^(BetterGenshinImpact|Test\\BetterGenshinImpact\.[^\\]+)\\bin\\'
    $taskReference=$EvidenceReference -and $taskFull.StartsWith($taskRepository.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)
    if (-not $taskFull.StartsWith($taskArtifacts, [StringComparison]::OrdinalIgnoreCase) -and -not $taskGenerated -and -not $taskReference) { throw 'Cleanup paths must remain under artifacts or generated project bin directories' }
    $taskItem = Get-Item -LiteralPath $taskFull -Force
    if ($taskItem.PSIsContainer) { throw 'Manifest entries must be individual files' }
    for ($taskWalk = $taskItem; $null -ne $taskWalk; $taskWalk = $taskWalk.Parent) {
        if (($taskWalk.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point rejected: $taskFull" }
        if ($taskWalk -is [IO.FileInfo]) { $taskWalk = $taskWalk.Directory; if (($taskWalk.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse parent rejected' } }
    }
    return $taskFull
}
function Assert-Candidate($Entry) {
    $taskPath = Assert-OrdinaryFile $Entry.path
    if ($taskHistorical) {
        if (-not $taskPath.StartsWith($taskCaptureRoot+'observations\',[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($taskPath) -ne '.png') { throw 'Historical cleanup is restricted to approved observation PNGs' }
        if ((Get-Item -LiteralPath $taskPath).Length -ne [long]$Entry.bytes -or (Get-FileHash -LiteralPath $taskPath).Hash -ne $Entry.sha256) { throw "Changed historical capture: $taskPath" }
        $taskProbe=[IO.File]::Open($taskPath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $taskProbe.Dispose()
        return
    }
    $taskPreserved = Assert-OrdinaryFile $Entry.preserved
    if ($taskPath -eq $taskPreserved -or $taskPath -match '[/\\](User|Logs?|observations|reports|receipts)[/\\]') { throw 'User/evidence data is outside this duplicate-build cleanup policy' }
    foreach ($taskRuntime in $taskProtected) {
        if ($taskPath.StartsWith($taskRuntime, [StringComparison]::OrdinalIgnoreCase)) { throw 'Active/rollback runtime deletion rejected' }
    }
    if (-not ($taskProtected | Where-Object { $taskPreserved.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })) { throw 'Preserved copy must be inside a protected runtime' }
    if ((Get-Item -LiteralPath $taskPath).Length -ne [long]$Entry.bytes -or
        (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash -ne $Entry.sha256) { throw "Changed candidate: $taskPath" }
    $taskKeepBytes=if($Entry.kind -eq 'superseded-build'){[long]$Entry.preservedBytes}else{[long]$Entry.bytes}
    $taskKeepHash=if($Entry.kind -eq 'superseded-build'){$Entry.preservedSha256}else{$Entry.sha256}
    if ((Get-Item -LiteralPath $taskPreserved).Length -ne $taskKeepBytes -or
        (Get-FileHash -LiteralPath $taskPreserved -Algorithm SHA256).Hash -ne $taskKeepHash) { throw "Changed preserved copy or successor witness: $taskPreserved" }
    # Fail closed if a process has the candidate open. No process is terminated.
    $taskProbe = [IO.File]::Open($taskPath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $taskProbe.Dispose()
}
if ($taskHistorical) {
    $taskPreservedPaths=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($taskEvidence in @($taskPlan.retained)+@($taskPlan.reports)+@($taskPlan.references)) {
        $taskEvidencePath=Assert-OrdinaryFile $taskEvidence.path -EvidenceReference
        if ((Get-FileHash -LiteralPath $taskEvidencePath).Hash -ne $taskEvidence.sha256) { throw "Changed preserved evidence: $taskEvidencePath" }
        [void]$taskPreservedPaths.Add($taskEvidencePath)
    }
    foreach($taskEntry in $taskPlan.candidates) { if ($taskPreservedPaths.Contains([IO.Path]::GetFullPath($taskEntry.path))) { throw 'Capture appears in both deletion and preservation sets' } }
}
foreach ($taskEntry in $taskPlan.candidates) {
    if (-not $taskSeen.Add([IO.Path]::GetFullPath($taskEntry.path))) { throw 'Duplicate manifest path' }
    Assert-Candidate $taskEntry
    $taskTotal += [long]$taskEntry.bytes
}
if ($taskTotal -ne [long]$taskPlan.bytes) { throw 'Manifest byte total mismatch' }
$taskDrive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskRepository))
$taskBefore = $taskDrive.AvailableFreeSpace
$taskDeleted = 0
$taskDeletedBytes = 0L
$taskFailure = $null
try {
    foreach ($taskEntry in $taskPlan.candidates) {
        # Revalidate immediately before this individual deletion, including both hashes.
        Assert-Candidate $taskEntry
        if($taskHistorical) {
            [ApprovedFileCleanup]::DeleteWithWitness($taskEntry.path,$taskWitness[0].path,$taskEntry.sha256,[long]$taskEntry.bytes,$taskWitness[0].sha256,[long]$taskWitness[0].bytes)
        } elseif($taskEntry.kind -eq 'superseded-build') {
            [ApprovedFileCleanup]::DeleteWithWitness($taskEntry.path,$taskEntry.preserved,$taskEntry.sha256,[long]$taskEntry.bytes,$taskEntry.preservedSha256,[long]$taskEntry.preservedBytes)
        } else { [ApprovedFileCleanup]::DeleteVerified($taskEntry.path,$taskEntry.preserved,$taskEntry.sha256,[long]$taskEntry.bytes) }
        $taskDeleted++
        $taskDeletedBytes += [long]$taskEntry.bytes
    }
} catch { $taskFailure = $_.Exception.Message; throw }
finally {
    [pscustomobject]@{version=1;utc=(Get-Date).ToUniversalTime().ToString('o');manifest=$taskManifestPath;
        approvedSha256=$ApprovedSha256;protectedRuntimeDirectories=$taskProtected;
        deletedFiles=$taskDeleted;deletedLogicalBytes=$taskDeletedBytes;freeBefore=$taskBefore;
        freeAfter=$taskDrive.AvailableFreeSpace;failure=$taskFailure} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $AuditPath
}
Get-Content -LiteralPath $AuditPath
if ($taskCheckpointRecord) {
    if ($taskDeleted -ne $taskPlan.files) { throw 'Incomplete retirement cannot clear the runtime checkpoint' }
    $taskCheckpointRecord.state='completed'
    $taskCheckpointRecord | Add-Member -NotePropertyName cleanupAudit -NotePropertyValue ([IO.Path]::GetFullPath($AuditPath)) -Force
    $taskTemporaryCheckpoint=$taskCheckpointPath+'.completed.tmp'
    $taskCheckpointStream=[IO.File]::Open($taskTemporaryCheckpoint,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $taskCheckpointBytes=[Text.Encoding]::UTF8.GetBytes(($taskCheckpointRecord | ConvertTo-Json -Depth 8))
        $taskCheckpointStream.Write($taskCheckpointBytes)
    } finally { $taskCheckpointStream.Dispose() }
    Move-Item -LiteralPath $taskTemporaryCheckpoint -Destination $taskCheckpointPath -Force
}
