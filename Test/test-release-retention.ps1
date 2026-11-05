param([string]$Repository = (Join-Path $PSScriptRoot '..'))
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath($Repository)
$taskScript = Join-Path $taskRoot 'Build/Scripts/manage-release-retention.ps1'
$taskTestRoot = Join-Path $taskRoot ('artifacts/tests/release-retention-' + [Guid]::NewGuid().ToString('N'))
$taskPassed = [Collections.Generic.List[string]]::new()
$taskSkipped = [Collections.Generic.List[string]]::new()

# Fixtures contain tiny files only and remain available for inspecting failed cases.
function Assert-TaskTest([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Write-TaskFile([string]$Path, [string]$Content) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
}
function New-TaskFixture([string]$Name, [string[]]$Pins = @('release-r1', 'release-r55', 'release-r56'), [int]$Recent = 2) {
    $taskFixture = Join-Path $taskTestRoot $Name
    [IO.Directory]::CreateDirectory((Join-Path $taskFixture 'artifacts')) | Out-Null
    Write-TaskFile (Join-Path $taskFixture 'policy.json') (@{
        version = 1; pinnedReleases = $Pins; keepRecentReleases = $Recent;
        minimumFreeBytes = 0; maximumProgramBytes = 1073741824
    } | ConvertTo-Json)
    return $taskFixture
}
function New-TaskRelease([string]$Fixture, [int]$Number, [switch]$Unregistered) {
    $taskRelease = Join-Path $Fixture "artifacts/release-r$Number"
    $taskPackage = Join-Path $taskRelease 'BetterGI-English-win-x64'
    Write-TaskFile (Join-Path $taskPackage 'BetterGI.exe') 'executable'
    Write-TaskFile (Join-Path $taskPackage 'BetterGI.dll') 'assembly'
    Write-TaskFile (Join-Path $taskPackage 'Assets/model.bin') 'packaged-model'
    if (-not $Unregistered) { Write-TaskFile (Join-Path $taskRelease 'build-manifest.json') '{"version":1}' }
    return $taskPackage
}
function Invoke-TaskRetention([string]$Fixture, [string]$Mode = 'Apply', [string]$Publish) {
    $taskArguments = @{ Repository = $Fixture; PolicyPath = (Join-Path $Fixture 'policy.json'); Action = $Mode }
    if ($Publish) { $taskArguments.PublishDirectory = $Publish }
    return (& $taskScript @taskArguments | ConvertFrom-Json)
}

$taskFixture = New-TaskFixture 'preservation'
foreach ($taskNumber in @(1, 55, 56)) { $null = New-TaskRelease $taskFixture $taskNumber }
$taskPackage = New-TaskRelease $taskFixture 2
$taskEvidence = @('User/recordings/frame.png', 'log/session.log', 'Cache/frame.png',
    'TestResults/results.trx', 'Assets/TestResults/nested.trx', 'Assets/unique-old-model.bin',
    'diagnostic.json', 'Build-Source.json')
foreach ($taskRelative in $taskEvidence) { Write-TaskFile (Join-Path $taskPackage $taskRelative) "preserved:$taskRelative" }
Write-TaskFile (Join-Path $taskFixture 'artifacts/release-r2/source-snapshot/source.cs') 'source evidence'
$taskPlan = Invoke-TaskRetention $taskFixture 'Plan'
Assert-TaskTest ($taskPlan.releases.Count -eq 1 -and $taskPlan.releases[0].candidateFiles -eq 3) 'Plan must include only recognized generated files.'
Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskPackage 'BetterGI.exe')) 'Plan must not delete or move files.'
$taskResult = Invoke-TaskRetention $taskFixture
Assert-TaskTest ($taskResult.deletedFiles -eq 3 -and $taskResult.releases[0].status -eq 'retired') 'Expected three generated files to retire.'
$taskArchivedPackage = Join-Path $taskFixture 'artifacts/release-evidence/release-r2/BetterGI-English-win-x64'
foreach ($taskRelative in $taskEvidence) {
    Assert-TaskTest ((Get-Content -LiteralPath (Join-Path $taskArchivedPackage $taskRelative) -Raw) -eq "preserved:$taskRelative") "Evidence changed: $taskRelative"
}
Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskFixture 'artifacts/release-evidence/release-r2/source-snapshot/source.cs')) 'Source snapshots must survive.'
foreach ($taskNumber in @(1, 55, 56)) {
    Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskFixture "artifacts/release-r$taskNumber/BetterGI-English-win-x64/BetterGI.exe")) 'A pinned executable was removed.'
}
$taskPassed.Add('plan, pins, data and source preservation')

$taskFixture = New-TaskFixture 'recent'
foreach ($taskNumber in @(1, 55, 56, 57, 58)) { $null = New-TaskRelease $taskFixture $taskNumber }
$null = New-TaskRelease $taskFixture 99 -Unregistered
$taskResult = Invoke-TaskRetention $taskFixture
Assert-TaskTest ($taskResult.keptReleases -contains 'release-r57' -and $taskResult.keptReleases -contains 'release-r58') 'Keep the newest two successful builds.'
Assert-TaskTest ($taskResult.releases[0].status -eq 'unregistered-preserved') 'An incomplete newer build must not displace successful builds or be deleted.'
$null = New-TaskRelease $taskFixture 59
$taskResult = Invoke-TaskRetention $taskFixture
Assert-TaskTest ($taskResult.keptReleases -contains 'release-r58' -and $taskResult.keptReleases -contains 'release-r59') 'Retention must advance when another successful build arrives.'
Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskFixture 'artifacts/release-evidence/release-r57/release-retirement.json')) 'The superseded rolling build must retire automatically.'
$taskResult = Invoke-TaskRetention $taskFixture
Assert-TaskTest ($taskResult.deletedFiles -eq 0) 'Repeating cleanup must not remove additional retained files.'
$taskPassed.Add('newest successful builds and incomplete publish preservation')

$taskFixture = New-TaskFixture 'in-use' @('release-r1') 0
$null = New-TaskRelease $taskFixture 1
$taskPackage = New-TaskRelease $taskFixture 2
$taskHandle = [IO.File]::Open((Join-Path $taskPackage 'BetterGI.exe'), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    $taskResult = Invoke-TaskRetention $taskFixture
    Assert-TaskTest ($taskResult.releases[0].status -eq 'in-use-or-inaccessible-preserved') 'An in-use executable must prevent retirement.'
    Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskPackage 'BetterGI.dll')) 'An in-use release must remain intact.'
} finally { $taskHandle.Dispose() }
$taskPassed.Add('in-use executable protection')

$taskFixture = New-TaskFixture 'registered' @('release-r1') 0
$null = New-TaskRelease $taskFixture 1
$taskPackage = New-TaskRelease $taskFixture 2
$null = Invoke-TaskRetention $taskFixture 'Register' $taskPackage
Write-TaskFile (Join-Path $taskPackage 'Assets/model.bin') 'modified model data'
[IO.File]::SetLastWriteTimeUtc((Join-Path $taskPackage 'Assets/model.bin'), [DateTime]::UtcNow.AddSeconds(2))
Write-TaskFile (Join-Path $taskPackage 'new-recording.mp4') 'new recording'
$taskResult = Invoke-TaskRetention $taskFixture
$taskArchivedPackage = Join-Path $taskFixture 'artifacts/release-evidence/release-r2/BetterGI-English-win-x64'
Assert-TaskTest ($taskResult.deletedFiles -eq 2) 'Only unchanged registered program files may be removed.'
Assert-TaskTest ((Get-Content -LiteralPath (Join-Path $taskArchivedPackage 'Assets/model.bin') -Raw) -eq 'modified model data') 'Modified registered files must survive.'
Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskArchivedPackage 'new-recording.mp4')) 'Unregistered recordings must survive.'
$taskPassed.Add('registered metadata, changed files and later recordings')

$taskFixture = New-TaskFixture 'unsafe-path' @('release-r1') 0
$null = New-TaskRelease $taskFixture 1
$taskPackage = New-TaskRelease $taskFixture 2
Write-TaskFile (Join-Path $taskPackage 'Portable-File-Manifest.json') '{"version":1,"files":[{"path":"../../sentinel.txt","bytes":1,"lastWriteUtcTicks":0}]}'
$taskRejected = $false
try { $null = Invoke-TaskRetention $taskFixture } catch { $taskRejected = $_.Exception.Message -match 'Invalid portable file manifest path' }
Assert-TaskTest $taskRejected 'Unsafe manifest paths must be rejected.'
Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskPackage 'BetterGI.exe')) 'Unsafe manifests must fail before moving their release.'
$taskPassed.Add('manifest traversal rejection')

$taskFixture = New-TaskFixture 'archive-collision' @('release-r1') 0
$null = New-TaskRelease $taskFixture 1
$taskPackage = New-TaskRelease $taskFixture 2
Write-TaskFile (Join-Path $taskFixture 'artifacts/release-evidence/release-r2/sentinel.txt') 'existing archive'
$taskRejected = $false
try { $null = Invoke-TaskRetention $taskFixture } catch { $taskRejected = $_.Exception.Message -match 'Archive already exists' }
Assert-TaskTest $taskRejected 'Existing archives must never be overwritten.'
Assert-TaskTest (Test-Path -LiteralPath (Join-Path $taskPackage 'BetterGI.exe')) 'Archive collisions must preserve the original release.'
$taskPassed.Add('archive collision protection')

$taskFixture = New-TaskFixture 'junction' @('release-r1') 0
$null = New-TaskRelease $taskFixture 1
$taskPackage = New-TaskRelease $taskFixture 2
$taskOutside = Join-Path $taskFixture 'outside-package'
Write-TaskFile (Join-Path $taskOutside 'important.dll') 'outside data'
$taskLinkCreated = $false
try {
    New-Item -ItemType Junction -Path (Join-Path $taskPackage 'Assets/linked') -Target $taskOutside | Out-Null
    $taskLinkCreated = $true
} catch {
    $taskSkipped.Add('junction fixture creation unavailable: ' + $_.Exception.Message)
}
if ($taskLinkCreated) {
    $null = Invoke-TaskRetention $taskFixture
    Assert-TaskTest ((Get-Content -LiteralPath (Join-Path $taskOutside 'important.dll') -Raw) -eq 'outside data') 'A linked directory target must never be traversed or deleted.'
    $taskPassed.Add('junction target preservation')
}

$taskFixture = New-TaskFixture 'publish-protection' @('release-r1') 0
$null = New-TaskRelease $taskFixture 1
$taskPackage = New-TaskRelease $taskFixture 2
$taskResult = Invoke-TaskRetention $taskFixture 'Apply' $taskPackage
Assert-TaskTest ($taskResult.deletedFiles -eq 0 -and (Test-Path -LiteralPath $taskPackage)) 'The explicitly publishing directory must remain protected.'
$taskStatus = Invoke-TaskRetention $taskFixture 'Status'
Assert-TaskTest ($taskStatus.ready -and $taskStatus.buildBytes -eq 64) 'Headroom must count program bytes without gameplay checkpoint prerequisites.'
$taskPolicy = Get-Content -LiteralPath (Join-Path $taskFixture 'policy.json') -Raw | ConvertFrom-Json
$taskPolicy.maximumProgramBytes = 1
Write-TaskFile (Join-Path $taskFixture 'policy.json') ($taskPolicy | ConvertTo-Json)
$taskStatus = Invoke-TaskRetention $taskFixture 'Status'
Assert-TaskTest (-not $taskStatus.ready) 'Storage admission must fail when preserved builds exceed the configured capacity.'
$taskPassed.Add('publish directory protection and storage-only admission')

# Reproduce the ordinary publish preflight with small registered test binaries and actual archive guards.
function New-VerifiedRelease([string]$Fixture, [int]$Number) {
    $package = New-TaskRelease $Fixture $Number
    $identity = @{
        version=1; targetDirectory=$package; exeSha256=(Get-FileHash -LiteralPath (Join-Path $package 'BetterGI.exe')).Hash
        dllSha256=(Get-FileHash -LiteralPath (Join-Path $package 'BetterGI.dll')).Hash
    }
    Write-TaskFile (Join-Path ([IO.Path]::GetDirectoryName($package)) 'build-manifest.json') ($identity | ConvertTo-Json)
    $null = Invoke-TaskRetention $Fixture 'Register' $package
    return $package
}
$taskFixture = New-TaskFixture 'pressured-publish' @('release-r1','release-r55','release-r56') 2
foreach ($n in @(1,55,56,75,76,77)) { $null = New-VerifiedRelease $taskFixture $n }
$taskSource = Join-Path $taskFixture 'artifacts/release-r76/BetterGI-English-win-x64'
Write-TaskFile (Join-Path $taskSource 'User/recordings/scene.png') 'exact recording'
Write-TaskFile (Join-Path $taskSource 'TestResults/native.trx') 'exact results'
$taskPublish = Join-Path $taskFixture 'artifacts/release-r78/BetterGI-English-win-x64'
# Use the public publisher check and its relative manager/policy paths inside this fixture only.
$taskAdmission = Join-Path $taskFixture 'tools/quest-pilot/check-storage-headroom.ps1'
$taskManager = Join-Path $taskFixture 'Build/Scripts/manage-release-retention.ps1'
foreach ($f in ($taskAdmission,$taskManager)) { [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($f)) }
[IO.File]::Copy((Join-Path $taskRoot 'tools/quest-pilot/check-storage-headroom.ps1'),$taskAdmission)
[IO.File]::Copy($taskScript,$taskManager)
$taskFixturePolicy = Join-Path $taskFixture 'Build/release-retention.json'
$taskPolicy = Get-Content -LiteralPath (Join-Path $taskFixture 'policy.json') -Raw | ConvertFrom-Json
Write-TaskFile $taskFixturePolicy ($taskPolicy | ConvertTo-Json)
$taskGuard = [IO.File]::Open((Join-Path $taskFixture 'artifacts/release-r75/BetterGI-English-win-x64/BetterGI.exe'),'Open','Read','Read')
try {
    $normal = Invoke-TaskRetention $taskFixture 'Apply' $taskPublish
    Assert-TaskTest ($normal.releases.status -contains 'in-use-or-inaccessible-preserved') 'Running older host must survive normal cleanup.'
    $ample = & $taskAdmission -Repository $taskFixture -PublishDirectory $taskPublish | ConvertFrom-Json
    Assert-TaskTest ($ample.ready -and (Test-Path -LiteralPath $taskSource)) 'A rolling release must survive when capacity is sufficient.'
    $taskPolicy.maximumProgramBytes = $ample.buildBytes - 32
    Write-TaskFile $taskFixturePolicy ($taskPolicy | ConvertTo-Json)
    # A read-only check cannot retire anything, even when the configured budget is exceeded.
    $rejected = $false
    try { $null = & $taskAdmission -Repository $taskFixture } catch { $rejected = $_.Exception.Message -match 'Storage preflight failed' }
    Assert-TaskTest ($rejected -and (Test-Path $taskSource)) 'Read-only admission may not retire a package.'
    $blocked = $false
    try { $null = & $taskAdmission -Repository $taskFixture -PublishDirectory $taskSource } catch { $blocked = $_.Exception.Message -match 'no eligible previous release' }
    Assert-TaskTest ($blocked -and (Test-Path $taskSource)) 'Even under pressure the explicit publish target must stay intact.'
    $recovered = & $taskAdmission -Repository $taskFixture -PublishDirectory $taskPublish | ConvertFrom-Json
    Assert-TaskTest ($recovered.ready -and $recovered.buildBytes -eq $taskPolicy.maximumProgramBytes -and
        $recovered.capacityRecovery.releases.Count -eq 1 -and $recovered.capacityRecovery.releases[0].release -eq 'release-r76') 'Only the inactive previous release should retire.'
    foreach ($n in @(1,55,56,75,77)) {
        Assert-TaskTest (Test-Path (Join-Path $taskFixture "artifacts/release-r$n/BetterGI-English-win-x64/BetterGI.exe")) 'A protected executable disappeared.'
    }
    $evidence = Join-Path $taskFixture 'artifacts/release-evidence/release-r76/BetterGI-English-win-x64'
    Assert-TaskTest ((Get-Content (Join-Path $evidence 'User/recordings/scene.png') -Raw) -eq 'exact recording') 'Recording bytes changed.'
    Assert-TaskTest ((Get-Content (Join-Path $evidence 'TestResults/native.trx') -Raw) -eq 'exact results') 'Test results changed.'
} finally { $taskGuard.Dispose() }
$taskPassed.Add('publish capacity recovery preserves pins, active host, newest build and evidence')

$taskFixture = New-TaskFixture 'ineligible-rollback' @() 4
$old = New-VerifiedRelease $taskFixture 70
$active = New-VerifiedRelease $taskFixture 71
$newest = New-VerifiedRelease $taskFixture 72
# A higher unverified manifest cannot be used as proof that the last verified version has a successor.
$null = New-TaskRelease $taskFixture 73
Write-TaskFile (Join-Path $old 'BetterGI.dll') 'different executable bytes'
$taskPolicy = Get-Content -LiteralPath (Join-Path $taskFixture 'policy.json') -Raw | ConvertFrom-Json
$taskPolicy.maximumProgramBytes = 1
Write-TaskFile (Join-Path $taskFixture 'policy.json') ($taskPolicy | ConvertTo-Json)
$handle = [IO.File]::Open((Join-Path $active 'BetterGI.exe'),'Open','Read','Read')
try {
    $recovery = Invoke-TaskRetention $taskFixture 'RecoverCapacity'
    Assert-TaskTest (-not $recovery.ready -and $recovery.capacityRecovery.deletedFiles -eq 0) 'Protected or unverified releases cannot satisfy the configured budget.'
    foreach ($package in ($old,$active,$newest)) { Assert-TaskTest (Test-Path (Join-Path $package 'BetterGI.exe')) 'An ineligible package disappeared.' }
} finally { $handle.Dispose() }
$taskPassed.Add('capacity recovery rejects mismatched binaries, an in-use recent executable and an unverified successor')

$taskFixture = New-TaskFixture 'minimal-recovery' @() 3
foreach ($n in @(10,11,12)) { $null = New-VerifiedRelease $taskFixture $n }
$taskPolicy = Get-Content -LiteralPath (Join-Path $taskFixture 'policy.json') -Raw | ConvertFrom-Json
$taskPolicy.maximumProgramBytes = 64
Write-TaskFile (Join-Path $taskFixture 'policy.json') ($taskPolicy | ConvertTo-Json)
$recovery = Invoke-TaskRetention $taskFixture 'RecoverCapacity'
Assert-TaskTest ($recovery.ready -and $recovery.buildBytes -eq 64 -and $recovery.capacityRecovery.releases.Count -eq 1 -and
    $recovery.capacityRecovery.releases[0].release -eq 'release-r10') 'Stop as soon as enough bytes have been recovered.'
$taskPassed.Add('only the oldest necessary verified rollback retires')

$taskFixture = New-TaskFixture 'first-publish'
# This is the known empty fixture directory, not a recursive removal.
[IO.Directory]::Delete((Join-Path $taskFixture 'artifacts'))
$taskStatus = Invoke-TaskRetention $taskFixture 'Status'
Assert-TaskTest ($taskStatus.ready -and $taskStatus.buildBytes -eq 0 -and $taskStatus.freeBytes -gt 0) 'First publish must still inspect free disk space.'
$taskPolicy = Get-Content -LiteralPath (Join-Path $taskFixture 'policy.json') -Raw | ConvertFrom-Json
$taskPolicy.minimumFreeBytes = [long]::MaxValue
Write-TaskFile (Join-Path $taskFixture 'policy.json') ($taskPolicy | ConvertTo-Json)
$taskStatus = Invoke-TaskRetention $taskFixture 'Status'
Assert-TaskTest (-not $taskStatus.ready) 'First publish must reject insufficient free space.'
$taskPassed.Add('free-space admission before the first publish')

[pscustomobject]@{ passed = $taskPassed.Count; cases = $taskPassed.ToArray(); skipped = $taskSkipped.ToArray(); fixtures = $taskTestRoot } | ConvertTo-Json -Depth 4
