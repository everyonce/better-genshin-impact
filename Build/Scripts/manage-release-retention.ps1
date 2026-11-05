param(
    [ValidateSet('Plan', 'Apply', 'Register', 'Status', 'RecoverCapacity')][string]$Action = 'Plan',
    [string]$Repository = (Join-Path $PSScriptRoot '../..'),
    [string]$PolicyPath = (Join-Path $PSScriptRoot '../release-retention.json'),
    [string]$PublishDirectory,
    [string]$AuditPath
)
$ErrorActionPreference = 'Stop'
$taskRepository = [IO.Path]::GetFullPath($Repository).TrimEnd('\', '/')
$taskArtifacts = Join-Path $taskRepository 'artifacts'
$taskArchive = Join-Path $taskArtifacts 'release-evidence'
$taskPackageName = 'BetterGI-English-win-x64'
$taskManifestName = 'Portable-File-Manifest.json'
$taskUtf8 = [Text.UTF8Encoding]::new($false)
$taskPolicy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json
if ($taskPolicy.version -ne 1 -or $taskPolicy.keepRecentReleases -lt 0 -or
    $taskPolicy.minimumFreeBytes -lt 0 -or $taskPolicy.maximumProgramBytes -le 0) {
    throw 'Invalid release retention policy.'
}
$taskPins = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($taskPin in $taskPolicy.pinnedReleases) {
    if ($taskPin -notmatch '^release-r[1-9][0-9]*$' -or -not $taskPins.Add($taskPin)) {
        throw 'Pinned releases must be distinct numbered release directory names.'
    }
}

# User data and evidence are never traversed for pruning or content hashing.
function Test-PreservedPath([string]$RelativePath) {
    $taskParts = $RelativePath -split '[/\\]'
    foreach ($taskPart in $taskParts) {
        if ($taskPart -match '^(User|Cache|Logs?|observations|reports|receipts|recordings|captures|screenshots|TestResults|test-results|evidence|revisions|source-snapshots?)$') { return $true }
    }
    return $taskParts[-1] -match '^(Build-Source\.json|Build-SHA256\.json|Portable-File-Manifest\.json|configuration-staging\.json)$|\.(trx|log|etl|dmp|mp4|mkv|avi|webm|jsonl|csv|npz|npy)$'
}

# Every mutating path must remain within its explicit root, with no linked ancestors.
function Assert-ContainedPath([string]$Path, [string]$Root) {
    $taskFull = [IO.Path]::GetFullPath($Path)
    $taskBound = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    if ($taskFull -ne $taskBound -and -not $taskFull.StartsWith($taskBound + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes its retention root: $taskFull"
    }
    $taskWalk = $taskFull
    while ($taskWalk) {
        if ([IO.File]::Exists($taskWalk) -or [IO.Directory]::Exists($taskWalk)) {
            if (([IO.File]::GetAttributes($taskWalk) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked retention path rejected: $taskWalk" }
        }
        if ($taskWalk -eq $taskRepository -or $taskWalk -eq [IO.Path]::GetPathRoot($taskWalk)) { break }
        $taskWalk = [IO.Path]::GetDirectoryName($taskWalk)
    }
    return $taskFull
}

# Metadata-only walk. Unknown links and all evidence/data subtrees are preserved.
function Get-PackageFiles([string]$Package) {
    $taskStack = [Collections.Generic.Stack[IO.DirectoryInfo]]::new()
    $taskStack.Push([IO.DirectoryInfo]::new($Package))
    while ($taskStack.Count) {
        $taskDirectory = $taskStack.Pop()
        foreach ($taskItem in $taskDirectory.EnumerateFileSystemInfos()) {
            $taskRelative = [IO.Path]::GetRelativePath($Package, $taskItem.FullName)
            if (Test-PreservedPath $taskRelative) { continue }
            if (($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
            if ($taskItem -is [IO.DirectoryInfo]) { $taskStack.Push($taskItem) }
            else { $taskItem }
        }
    }
}

# Historical publishes lack a file manifest. Only recognized program containers and
# root binary/runtime files qualify; unknown files are retained in the evidence archive.
function Test-HistoricalProgramPath([string]$RelativePath) {
    if (Test-PreservedPath $RelativePath) { return $false }
    $taskParts = $RelativePath -split '[/\\]'
    if ($taskParts.Count -eq 1) {
        return $taskParts[0] -match '\.(dll|exe|pdb|pri)$|\.deps\.json$|\.runtimeconfig\.json$'
    }
    return $taskParts[0] -match '^(Assets|runtimes|amd64|dicts|GameTask|Licenses|English-Web-Source|[a-z]{2}(-[A-Za-z0-9]{2,8})?)$'
}

function Write-RetentionJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), $taskUtf8)
}

# Check free space even before the first artifacts directory has been created.
function Get-RetentionStatus([long]$ProgramBytes) {
    $taskFree = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskRepository))).AvailableFreeSpace
    return [pscustomobject]@{ utc = [DateTime]::UtcNow.ToString('o'); freeBytes = $taskFree;
        minimumFreeBytes = $taskPolicy.minimumFreeBytes; buildBytes = $ProgramBytes;
        maximumBuildBytes = $taskPolicy.maximumProgramBytes; pinnedReleases = @($taskPins);
        ready = ($taskFree -ge $taskPolicy.minimumFreeBytes -and $ProgramBytes -le $taskPolicy.maximumProgramBytes) }
}

# Register the clean publish before the application can add logs, caches or recordings.
if ($Action -eq 'Register') {
    if (-not $PublishDirectory) { throw 'Register requires PublishDirectory.' }
    $taskPublish = Assert-ContainedPath $PublishDirectory $taskArtifacts
    if (-not [IO.File]::Exists((Join-Path $taskPublish 'BetterGI.exe'))) { throw 'Cannot register a publish without BetterGI.exe.' }
    $taskPublishedFiles = @(Get-PackageFiles $taskPublish | ForEach-Object {
        [pscustomobject]@{ path = [IO.Path]::GetRelativePath($taskPublish, $_.FullName); bytes = $_.Length; lastWriteUtcTicks = $_.LastWriteTimeUtc.Ticks }
    })
    Write-RetentionJson (Join-Path $taskPublish $taskManifestName) ([pscustomobject]@{
        version = 1; createdAtUtc = [DateTime]::UtcNow.ToString('o'); files = $taskPublishedFiles
    })
    [pscustomobject]@{ action = 'Register'; directory = $taskPublish; files = $taskPublishedFiles.Count } | ConvertTo-Json
    return
}

if (-not [IO.Directory]::Exists($taskArtifacts)) {
    if ($Action -in @('Status','RecoverCapacity')) { Get-RetentionStatus 0 | ConvertTo-Json -Depth 4 }
    else { [pscustomobject]@{ action = $Action; releases = @(); deletedBytes = 0; ready = $true } | ConvertTo-Json }
    return
}
$null = Assert-ContainedPath $taskArtifacts $taskRepository
$taskReleases = @(Get-ChildItem -LiteralPath $taskArtifacts -Directory | Where-Object { $_.Name -match '^release-r[1-9][0-9]*$' })
$taskSuccessful = @($taskReleases | Where-Object {
    [IO.File]::Exists((Join-Path $_.FullName 'build-manifest.json')) -or
    [IO.File]::Exists((Join-Path $_.FullName "$taskPackageName/$taskManifestName"))
} | Sort-Object { [int]($_.Name -replace '^release-r', '') } -Descending)
$taskKeep = [Collections.Generic.HashSet[string]]::new($taskPins, [StringComparer]::OrdinalIgnoreCase)
$taskRecentReleases = @($taskSuccessful | Select-Object -First $taskPolicy.keepRecentReleases)
foreach ($taskRecent in $taskRecentReleases) { [void]$taskKeep.Add($taskRecent.Name) }
$taskPublishingRelease = $null
if ($PublishDirectory) {
    $taskPublish = [IO.Path]::GetFullPath($PublishDirectory)
    foreach ($taskRelease in $taskReleases) {
        if ($taskPublish.StartsWith($taskRelease.FullName + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            $taskPublishingRelease = $taskRelease.Name
            [void]$taskKeep.Add($taskRelease.Name)
        }
    }
}

function Get-ProgramCandidates([string]$Package, [switch]$RequireManifest) {
    $taskFileManifest = Join-Path $Package $taskManifestName
    if ([IO.File]::Exists($taskFileManifest)) {
        $null = Assert-ContainedPath $taskFileManifest $taskArtifacts
        $taskManifest = Get-Content -LiteralPath $taskFileManifest -Raw | ConvertFrom-Json
        if ($taskManifest.version -ne 1) { throw "Unsupported portable file manifest: $taskFileManifest" }
        $taskSeen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($taskEntry in $taskManifest.files) {
            if (-not $taskEntry.path -or $taskEntry.path -match ':' -or [IO.Path]::IsPathRooted($taskEntry.path) -or
                ($taskEntry.path -split '[/\\]') -contains '..' -or -not $taskSeen.Add($taskEntry.path)) { throw 'Invalid portable file manifest path.' }
            if (Test-PreservedPath $taskEntry.path) { continue }
            $taskPath = Assert-ContainedPath (Join-Path $Package $taskEntry.path) $Package
            if (-not [IO.File]::Exists($taskPath)) { continue }
            $taskFile = [IO.FileInfo]::new($taskPath)
            if ($taskFile.Length -ne [long]$taskEntry.bytes -or $taskFile.LastWriteTimeUtc.Ticks -ne [long]$taskEntry.lastWriteUtcTicks) { continue }
            [pscustomobject]@{ path = $taskEntry.path; bytes = $taskFile.Length; lastWriteUtcTicks = $taskFile.LastWriteTimeUtc.Ticks }
        }
        return
    }
    if ($RequireManifest) { return }
    foreach ($taskFile in Get-PackageFiles $Package) {
        $taskRelative = [IO.Path]::GetRelativePath($Package, $taskFile.FullName)
        $taskRootBinary = ($taskRelative -notmatch '[/\\]') -and (Test-HistoricalProgramPath $taskRelative)
        if ($taskRootBinary -or $taskKnownProgramPaths.Contains($taskRelative)) {
            [pscustomobject]@{ path = $taskRelative; bytes = $taskFile.Length; lastWriteUtcTicks = $taskFile.LastWriteTimeUtc.Ticks }
        }
    }
}

function Get-CurrentStorageStatus {
    $taskProgramBytes = 0L
    foreach ($taskRelease in $taskReleases) {
        $taskPackage = Join-Path $taskRelease.FullName $taskPackageName
        if (-not [IO.Directory]::Exists($taskPackage)) { continue }
        $null = Assert-ContainedPath $taskPackage $taskArtifacts
        foreach ($taskFile in Get-PackageFiles $taskPackage) { $taskProgramBytes += $taskFile.Length }
    }
    # Preserve the existing capacity accounting for non-numbered portable outputs.
    foreach ($taskOther in Get-ChildItem -LiteralPath $taskArtifacts -Directory) {
        if ($taskOther.Name -notmatch '^(release|BetterGI-English-win-x64|r[0-9]+-native-publish)$') { continue }
        $null = Assert-ContainedPath $taskOther.FullName $taskArtifacts
        foreach ($taskFile in Get-PackageFiles $taskOther.FullName) { $taskProgramBytes += $taskFile.Length }
    }
    Get-RetentionStatus $taskProgramBytes
}

# Only apply the rolling-release exception to packages with a verified published binary identity.
function Test-RegisteredPackageIdentity([IO.DirectoryInfo]$Release) {
    $package = Join-Path $Release.FullName $taskPackageName
    $manifestPath = Assert-ContainedPath (Join-Path $Release.FullName 'build-manifest.json') $taskArtifacts
    if (-not [IO.File]::Exists($manifestPath)) { return $false }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($manifest.version -ne 1 -or -not $manifest.targetDirectory -or
            [IO.Path]::GetFullPath($manifest.targetDirectory) -ne $package) { return $false }
        foreach ($file in @(@('BetterGI.exe', $manifest.exeSha256), @('BetterGI.dll', $manifest.dllSha256))) {
            $binary = Assert-ContainedPath (Join-Path $package $file[0]) $Release.FullName
            if ($file[1] -notmatch '^[0-9a-fA-F]{64}$' -or -not [IO.File]::Exists($binary) -or
                (Get-FileHash -LiteralPath $binary -Algorithm SHA256 -ErrorAction Stop).Hash -ne $file[1]) { return $false }
        }
        return $true
    } catch { return $false }
}

if ($Action -in @('Status','RecoverCapacity')) {
    $taskCapacity = Get-CurrentStorageStatus
    if ($Action -eq 'Status' -or $taskCapacity.ready) {
        $taskCapacity | ConvertTo-Json -Depth 4
        return
    }
    # Consider the ordinary rolling set only. Always keep its newest verified release, even if a
    # higher numbered incomplete publication or unreadable binary is present.
    $taskVerifiedRecent = @($taskRecentReleases | Where-Object { Test-RegisteredPackageIdentity $_ })
    $taskRollingCandidates = @($taskVerifiedRecent | Select-Object -Skip 1 | Where-Object {
        -not $taskPins.Contains($_.Name) -and $_.Name -ne $taskPublishingRelease -and
            [IO.File]::Exists((Join-Path $_.FullName "$taskPackageName/$taskManifestName"))
    })
}
else {
    # A current retained package supplies historical generated-path names, never byte hashes.
    $taskKnownProgramPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($taskRelease in $taskReleases) {
        if (-not $taskKeep.Contains($taskRelease.Name)) { continue }
        $taskPackage = Join-Path $taskRelease.FullName $taskPackageName
        if (-not [IO.Directory]::Exists($taskPackage)) { continue }
        $null = Assert-ContainedPath $taskPackage $taskArtifacts
        foreach ($taskFile in Get-PackageFiles $taskPackage) {
            $taskRelative = [IO.Path]::GetRelativePath($taskPackage, $taskFile.FullName)
            if (Test-HistoricalProgramPath $taskRelative) { [void]$taskKnownProgramPaths.Add($taskRelative) }
        }
    }
}

$taskResults = [Collections.Generic.List[object]]::new()
$taskDeletedBytes = 0L
$taskDeletedFiles = 0
$taskSelection = if ($Action -eq 'RecoverCapacity') { $taskRollingCandidates } else { $taskReleases }
foreach ($taskRelease in $taskSelection | Sort-Object { [int]($_.Name -replace '^release-r', '') }) {
    if ($Action -ne 'RecoverCapacity' -and $taskKeep.Contains($taskRelease.Name)) { continue }
    $taskSource = Assert-ContainedPath $taskRelease.FullName $taskArtifacts
    $taskPackage = Join-Path $taskSource $taskPackageName
    if (-not [IO.Directory]::Exists($taskPackage)) { continue }
    $null = Assert-ContainedPath $taskPackage $taskSource
    $taskTarget = Assert-ContainedPath (Join-Path $taskArchive $taskRelease.Name) $taskArchive
    if ([IO.Directory]::Exists($taskTarget) -or [IO.File]::Exists($taskTarget)) { throw "Archive already exists; nothing will be overwritten: $taskTarget" }
    if (-not [IO.File]::Exists((Join-Path $taskSource 'build-manifest.json')) -and
        -not [IO.File]::Exists((Join-Path $taskPackage $taskManifestName))) {
        $taskResults.Add([pscustomobject]@{ release = $taskRelease.Name; status = 'unregistered-preserved' })
        continue
    }
    $taskCandidates = @(Get-ProgramCandidates $taskPackage -RequireManifest:($Action -eq 'RecoverCapacity'))
    if ($Action -eq 'RecoverCapacity' -and ($taskCandidates.path -notcontains 'BetterGI.exe' -or
            $taskCandidates.path -notcontains 'BetterGI.dll')) {
        $taskResults.Add([pscustomobject]@{ release = $taskRelease.Name; status = 'changed-package-preserved' })
        continue
    }
    $taskBytes = 0L
    foreach ($taskCandidate in $taskCandidates) { $taskBytes += $taskCandidate.bytes }
    $taskResult = [ordered]@{ release = $taskRelease.Name; originalPath = $taskSource; archivePath = $taskTarget;
        status = 'planned'; candidateFiles = $taskCandidates.Count; candidateBytes = $taskBytes; deletedFiles = 0; deletedBytes = 0L }
    if ($Action -eq 'Plan') { $taskResults.Add([pscustomobject]$taskResult); continue }

    # Holding the executable without read/write sharing prevents a new launch while
    # retiring it. An in-use or inaccessible executable preserves the whole release.
    $taskGuard = $null
    $taskExecutable = Join-Path $taskPackage 'BetterGI.exe'
    if ([IO.File]::Exists($taskExecutable)) {
        try { $taskGuard = [IO.File]::Open($taskExecutable, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::Delete) }
        catch {
            $taskResult.status = 'in-use-or-inaccessible-preserved'
            $taskResult.reason = $_.Exception.Message
            $taskResults.Add([pscustomobject]$taskResult)
            continue
        }
    }
    $taskRemoved = [Collections.Generic.List[object]]::new()
    try {
        # Remove generated files while the executable is locked against new launches.
        # Windows cannot rename the containing directory until that handle is closed.
        $null = Assert-ContainedPath $taskSource $taskArtifacts
        $null = Assert-ContainedPath $taskTarget $taskArchive
        [IO.Directory]::CreateDirectory($taskArchive) | Out-Null
        foreach ($taskCandidate in $taskCandidates) {
            $taskPath = Assert-ContainedPath (Join-Path $taskPackage $taskCandidate.path) $taskSource
            $taskFile = [IO.FileInfo]::new($taskPath)
            if (-not $taskFile.Exists -or $taskFile.Length -ne $taskCandidate.bytes -or
                $taskFile.LastWriteTimeUtc.Ticks -ne $taskCandidate.lastWriteUtcTicks) { continue }
            [IO.File]::Delete($taskPath)
            $taskResult.deletedFiles++
            $taskResult.deletedBytes += $taskCandidate.bytes
            $taskRemoved.Add([pscustomobject]@{ path = $taskCandidate.path; bytes = $taskCandidate.bytes })
        }
        if ($taskGuard) { $taskGuard.Dispose(); $taskGuard = $null }
        # Same-volume directory rename preserves all remaining data and relative paths.
        [IO.Directory]::Move($taskSource, $taskTarget)
        $taskResult.status = 'retired'
    } catch {
        $taskResult.status = 'partial-preserved'
        $taskResult.reason = $_.Exception.Message
    } finally {
        if ($taskGuard) { $taskGuard.Dispose() }
        $taskDeletedFiles += $taskResult.deletedFiles
        $taskDeletedBytes += $taskResult.deletedBytes
        $taskResults.Add([pscustomobject]$taskResult)
        $taskAuditRoot = if ([IO.Directory]::Exists($taskTarget)) { $taskTarget } else { $taskSource }
        if ([IO.Directory]::Exists($taskAuditRoot)) {
            Write-RetentionJson (Join-Path $taskAuditRoot 'release-retirement.json') ([pscustomobject]@{
                version = 1; retiredAtUtc = [DateTime]::UtcNow.ToString('o'); result = $taskResult;
                preserved = 'All remaining files, including User, logs, recordings, test results, source snapshots and unknown files.';
                removedProgramFiles = @($taskRemoved)
            })
        }
    }
    if ($taskResult.status -eq 'partial-preserved') { break }
    if ($Action -eq 'RecoverCapacity' -and $taskResult.status -eq 'retired') {
        [void]$taskKeep.Remove($taskRelease.Name)
        $taskCapacity = Get-CurrentStorageStatus
        if ($taskCapacity.ready) { break }
    }
}
$taskSummary = [pscustomobject]@{
    version = 1; action = $Action; utc = [DateTime]::UtcNow.ToString('o');
    pinnedReleases = @($taskPins); keptReleases = @($taskKeep); keepRecentReleases = $taskPolicy.keepRecentReleases;
    deletedFiles = $taskDeletedFiles; deletedBytes = $taskDeletedBytes; releases = @($taskResults)
}
if ($AuditPath) {
    $taskAudit = Assert-ContainedPath $AuditPath $taskArtifacts
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($taskAudit)) | Out-Null
    Write-RetentionJson $taskAudit $taskSummary
}
if ($Action -in @('Apply','RecoverCapacity')) {
    [IO.Directory]::CreateDirectory($taskArchive) | Out-Null
    # Each archived release retains its own original-prefix mapping and deletion audit.
    Write-RetentionJson (Join-Path $taskArchive 'latest-retention-run.json') $taskSummary
}
if ($Action -eq 'RecoverCapacity') {
    $taskCapacity | Add-Member -NotePropertyName capacityRecovery -NotePropertyValue $taskSummary
    $taskCapacity | ConvertTo-Json -Depth 7
} else { $taskSummary | ConvertTo-Json -Depth 6 }
if (@($taskResults | Where-Object status -eq 'partial-preserved').Count) { throw 'Release retirement stopped after a partial operation; see the preserved audit.' }
