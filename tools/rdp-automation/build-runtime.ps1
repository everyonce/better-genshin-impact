<# Build a new portable release without modifying an installation that may be running. #>
[CmdletBinding()]
param(
    [ValidateRange(0, 1000000)] [int] $Release = 0,
    # Keep Debug publishing compatible with earlier calls; choose Release explicitly for latency trials.
    [ValidateSet('Debug', 'Release')] [string] $PublishConfiguration = 'Debug',
    # Optional shared directory containing the installed toolchain and versioned release outputs.
    [string] $ArtifactsDirectory,
    # Optional shared NuGet package cache when building a separate checkout.
    [string] $PackageCacheDirectory
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

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
# Resolve caller-selected locations explicitly; drive-relative paths depend on hidden shell state.
foreach ($requestedPath in @($ArtifactsDirectory, $PackageCacheDirectory)) {
    if (-not [string]::IsNullOrWhiteSpace($requestedPath) -and
        $requestedPath -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)') {
        throw 'Shared artifact and package directories must be absolute Windows paths.'
    }
}
$artifactRoot = if ([string]::IsNullOrWhiteSpace($ArtifactsDirectory)) {
    Join-Path $repoRoot 'artifacts'
} else { [IO.Path]::GetFullPath($ArtifactsDirectory) }
$packageCache = if ([string]::IsNullOrWhiteSpace($PackageCacheDirectory)) {
    Join-Path $repoRoot 'packages'
} else { [IO.Path]::GetFullPath($PackageCacheDirectory) }
$sdkRoot = Join-Path $artifactRoot 'toolchain\dotnet'
$dotnetExe = Join-Path $sdkRoot 'dotnet.exe'
if (-not (Test-Path -LiteralPath $dotnetExe -PathType Leaf)) {
    throw "The installed .NET SDK is missing at $dotnetExe. This script does not install dependencies."
}

# Select a fresh version directory. Existing releases, including failed builds, are retained.
if ($Release -eq 0) {
    $numbers = @(Get-ChildItem -LiteralPath $artifactRoot -Directory | ForEach-Object {
        if ($_.Name -match '^release-r([0-9]+)$') { [int]$Matches[1] }
    })
    $Release = if ($numbers.Count) { ($numbers | Measure-Object -Maximum).Maximum + 1 } else { 1 }
}
$releaseRoot = Join-Path $artifactRoot "release-r$Release"
$target = Join-Path $releaseRoot 'BetterGI-English-win-x64'
if (Test-Path -LiteralPath $releaseRoot) {
    throw "Release directory already exists: $releaseRoot. Choose an unused release number."
}

# Keep the SDK and package cache local; restore the caller's process environment afterward.
$names = @('DOTNET_ROOT', 'DOTNET_CLI_HOME', 'NUGET_PACKAGES', 'MSBUILDDISABLENODEREUSE')
$previousEnvironment = @{}
foreach ($name in $names) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
Push-Location $repoRoot
try {
    $env:DOTNET_ROOT = $sdkRoot
    $env:DOTNET_CLI_HOME = Join-Path $artifactRoot 'toolchain\dotnet-home'
    $env:NUGET_PACKAGES = $packageCache
    $env:MSBUILDDISABLENODEREUSE = '1'
    $sdkVersion = (& $dotnetExe --version).Trim()
    if ($LASTEXITCODE -ne 0 -or ([version]($sdkVersion -split '-')[0]).Major -lt 10) {
        throw 'Building this repository requires .NET SDK 10 or later.'
    }
    New-Item -ItemType Directory -Path $target | Out-Null

    # NuGet sources follow the existing machine/repository configuration and installed package cache.
    # The required solution build runs before publishing the same source into an isolated release.
    & $dotnetExe msbuild BetterGenshinImpact.sln -restore -p:Configuration=Debug -p:UseSharedCompilation=false -m:1 -nr:false -nologo -tl:off -clp:ErrorsOnly
    if ($LASTEXITCODE -ne 0) { throw "Solution build failed (exit $LASTEXITCODE). Partial release retained at $releaseRoot." }
    & $dotnetExe publish BetterGenshinImpact/BetterGenshinImpact.csproj -c $PublishConfiguration -r win-x64 --self-contained true -p:Platform=x64 -p:UseSharedCompilation=false -o $target -m:1 -nr:false -nologo -tl:off -clp:ErrorsOnly
    if ($LASTEXITCODE -ne 0) { throw "Publish failed (exit $LASTEXITCODE). Partial release retained at $releaseRoot." }

    # Record identity for later readiness and hot-replacement verification.
    $revision = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not identify the repository revision.' }
    $manifest = [ordered]@{
        version = 1
        targetDirectory = $target
        builtAtUtc = [DateTime]::UtcNow.ToString('o')
        sourceRevision = $revision
        workingTreeDirty = [bool](& git status --porcelain)
        sdkVersion = $sdkVersion
        validationConfiguration = 'Debug'
        publishConfiguration = $PublishConfiguration
        runtimeIdentifier = 'win-x64'
        selfContained = $true
        exeSha256 = Get-BuildFileSha256 -Path (Join-Path $target 'BetterGI.exe')
        dllSha256 = Get-BuildFileSha256 -Path (Join-Path $target 'BetterGI.dll')
    }
    $json = $manifest | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $releaseRoot 'build-manifest.json'), $json, [Text.UTF8Encoding]::new($false))
    Write-Output $json
}
finally {
    Pop-Location
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
}
