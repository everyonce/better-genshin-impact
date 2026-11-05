<# Register an existing numbered portable build without invoking the SDK or changing its package. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$TargetDirectory,
    [string]$SourceRevision,
    [string]$SdkVersion,
    [ValidateSet('Debug','Release')][string]$PublishConfiguration = 'Release',
    [ValidateSet('Debug','Release')][string]$ValidationConfiguration,
    [ValidateSet('solution-build','english-tests')][string]$ValidationKind,
    [Nullable[bool]]$WorkingTreeDirty,
    [switch]$PreserveWitness
)
$ErrorActionPreference = 'Stop'

# Hash the published bytes without depending on PowerShell module auto-loading.
# Nested cleanup also disposes the algorithm when opening the file fails.
function Get-BuildFileSha256 {
    param([Parameter(Mandatory)][string] $Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try {
            return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
        }
        finally { $stream.Dispose() }
    }
    finally { $algorithm.Dispose() }
}

# A receipt can authorize later executable replacement. Keep its source, parent and destination off links.
function Assert-PhysicalPath([string]$Path) {
    $item = [IO.Path]::GetFullPath($Path)
    while ($item) {
        try {
            if ([IO.File]::GetAttributes($item) -band [IO.FileAttributes]::ReparsePoint) {
                throw "Package identity paths must be physical: $item"
            }
        }
        catch [IO.FileNotFoundException] {}
        catch [IO.DirectoryNotFoundException] {}
        $parent = [IO.Directory]::GetParent($item)
        $item = if ($parent) { $parent.FullName } else { $null }
    }
}

$target = [IO.Path]::GetFullPath($TargetDirectory).TrimEnd('\','/')
$releaseRoot = [IO.Directory]::GetParent($target)
if ([IO.Path]::GetFileName($target) -ine 'BetterGI-English-win-x64' -or $releaseRoot.Name -notmatch '^release-r[0-9]+$') {
    throw 'Package identity requires a numbered release-rN/BetterGI-English-win-x64 output.'
}
$manifestPath = Join-Path $releaseRoot.FullName 'build-manifest.json'
Assert-PhysicalPath $manifestPath
$hashes = @{}
$builtAt = [DateTime]::MinValue
foreach ($name in 'BetterGI.exe','BetterGI.dll') {
    $file = Join-Path $target $name
    Assert-PhysicalPath $file
    $binary = Get-Item -LiteralPath $file
    if ($binary.Length -le 0) { throw "Missing or empty package binary: $name" }
    if ($binary.LastWriteTimeUtc -gt $builtAt) { $builtAt = $binary.LastWriteTimeUtc }
    $hashes[$name] = Get-BuildFileSha256 -Path $file
}

# English packages contain source and binary receipts. Support later registration without guessing
# whether Debug was built or what the working tree looked like at the time of publication.
$buildSource = Join-Path $target 'Build-Source.json'
if ([IO.File]::Exists($buildSource)) {
    Assert-PhysicalPath $buildSource
    $receipt = [IO.File]::ReadAllText($buildSource) | ConvertFrom-Json
    if ($receipt.runtime -ne 'win-x64' -or $receipt.selfContained -isnot [bool] -or !$receipt.selfContained -or
        ($SourceRevision -and $SourceRevision -ne $receipt.sourceCommit) -or ($SdkVersion -and $SdkVersion -ne $receipt.sdk)) {
        throw 'English publisher source receipt does not match the requested package identity.'
    }
    $SourceRevision = $receipt.sourceCommit
    $SdkVersion = $receipt.sdk
    $builtAt = (Get-Item -LiteralPath $buildSource).LastWriteTimeUtc
    if (!$PSBoundParameters.ContainsKey('WorkingTreeDirty') -and $receipt.workingTreeDirty -is [bool]) {
        $WorkingTreeDirty = $receipt.workingTreeDirty
    }
    if (!$ValidationConfiguration -and !$ValidationKind -and $receipt.validationConfiguration -and $receipt.validationKind) {
        $ValidationConfiguration = $receipt.validationConfiguration
        $ValidationKind = $receipt.validationKind
    }
    $buildHashes = Join-Path $target 'Build-SHA256.json'
    Assert-PhysicalPath $buildHashes
    $rows = @([IO.File]::ReadAllText($buildHashes) | ConvertFrom-Json)
    # Windows PowerShell and pwsh both expose the JSON array through the pipeline.
    $rows = @($rows | ForEach-Object { $_ })
    foreach ($name in $hashes.Keys) {
        $match = @($rows | Where-Object { $_.File -eq $name })
        if ($rows.Count -ne 2 -or $match.Count -ne 1 -or $match[0].Algorithm -ne 'SHA256' -or $match[0].Hash -ne $hashes[$name]) {
            throw "English publisher hash receipt differs for $name."
        }
    }
}
if ($SourceRevision -notmatch '^[0-9a-f]{40}$' -or $SdkVersion -notmatch '^\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]+)?$') {
    throw 'The package source commit and SDK version are required.'
}
if ([bool]$ValidationConfiguration -ne [bool]$ValidationKind) { throw 'Supply both the verified configuration and validation kind.' }
$manifest = [ordered]@{
    version = 1; targetDirectory = $target; builtAtUtc = $builtAt.ToString('o')
    sourceRevision = $SourceRevision; workingTreeDirty = $WorkingTreeDirty; sdkVersion = $SdkVersion
    validationConfiguration = $(if ($ValidationConfiguration) { $ValidationConfiguration } else { $null })
    validationKind = $(if ($ValidationKind) { $ValidationKind } else { $null })
    publishConfiguration = $PublishConfiguration; runtimeIdentifier = 'win-x64'; selfContained = $true
    exeSha256 = $hashes['BetterGI.exe']; dllSha256 = $hashes['BetterGI.dll']
}
$witnessParent = Join-Path $releaseRoot.Parent.FullName 'release-retention\package-witnesses'
$witness = Join-Path $witnessParent $releaseRoot.Name
$witnessManifest = Join-Path $witness 'build-manifest.json'
$existing = @($manifestPath)
if ($PreserveWitness) {
    Assert-PhysicalPath $witnessManifest
    if ([IO.Directory]::Exists($witness)) {
        if (![IO.File]::Exists($witnessManifest)) { throw "Incomplete package witness: $witness" }
        $existing += $witnessManifest
    }
}

# A retry reuses the original receipt, including its timestamp and any additional verification.
$canonical = $null
foreach ($file in $existing) {
    if (![IO.File]::Exists($file)) { continue }
    if ((Get-Item -LiteralPath $file).Length -gt 65536) { throw "Oversize existing build manifest: $file" }
    $bytes = [IO.File]::ReadAllBytes($file)
    $saved = [Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff) | ConvertFrom-Json
    foreach ($key in $manifest.Keys) {
        if ($key -eq 'builtAtUtc' -or ($null -eq $manifest[$key] -and $key -in @('workingTreeDirty','validationConfiguration','validationKind'))) { continue }
        $actual = ConvertTo-Json -Compress -InputObject $saved.$key
        $expected = ConvertTo-Json -Compress -InputObject $manifest[$key]
        if ($actual -ne $expected) { throw "Existing package identity differs at $key in $file." }
    }
    if ($null -ne $canonical -and [Convert]::ToBase64String($canonical) -ne [Convert]::ToBase64String($bytes)) {
        throw 'Existing package manifests have different bytes.'
    }
    $canonical = $bytes
}
if ($null -eq $canonical) {
    $canonical = [Text.UTF8Encoding]::new($false).GetBytes(($manifest | ConvertTo-Json -Depth 4))
}

if ($PreserveWitness) {
    # Publish the whole witness directory at once. Failure never exposes a partial archive as a valid release.
    $pending = $null
    $witnessSource = $witness
    if (![IO.Directory]::Exists($witness)) {
        [IO.Directory]::CreateDirectory($witnessParent) | Out-Null
        $pending = Join-Path $witnessParent ('.pending-' + [guid]::NewGuid().ToString('N'))
        $witnessSource = $pending
    }
    $binaries = Join-Path $witnessSource 'BetterGI-English-win-x64'
    try {
        if ($pending) {
            [IO.Directory]::CreateDirectory($binaries) | Out-Null
            [IO.File]::WriteAllBytes((Join-Path $pending 'build-manifest.json'), $canonical)
        }
        foreach ($name in $hashes.Keys) {
            $copy = Join-Path $binaries $name
            Assert-PhysicalPath $copy
            if ($pending) { [IO.File]::Copy((Join-Path $target $name), $copy) }
            if ((Get-BuildFileSha256 -Path $copy) -ne $hashes[$name]) { throw "Package witness differs for $name." }
        }
        if ($pending) { [IO.Directory]::Move($pending, $witness) }
    }
    finally {
        if ($pending -and [IO.Directory]::Exists($pending)) {
            foreach ($name in 'BetterGI.exe','BetterGI.dll') { [IO.File]::Delete((Join-Path $binaries $name)) }
            [IO.File]::Delete((Join-Path $pending 'build-manifest.json'))
            if ([IO.Directory]::Exists($binaries)) { [IO.Directory]::Delete($binaries) }
            [IO.Directory]::Delete($pending)
        }
    }
}
if (![IO.File]::Exists($manifestPath)) {
    $temporary = Join-Path $releaseRoot.FullName ('.build-manifest-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllBytes($temporary,$canonical)
        [IO.File]::Move($temporary,$manifestPath)
    } finally { [IO.File]::Delete($temporary) }
}
