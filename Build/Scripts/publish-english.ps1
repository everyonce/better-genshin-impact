param(
    [string]$DotNet = 'dotnet',
    [string]$OutputDirectory,
    [string]$WebAssetsRoot,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (!$OutputDirectory) { $OutputDirectory = Join-Path $repo 'artifacts\BetterGI-English-win-x64' }
if (!$WebAssetsRoot) { $WebAssetsRoot = Join-Path $repo 'Build\EnglishWeb\dist' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if ((Test-Path -LiteralPath $OutputDirectory) -and (Get-ChildItem -LiteralPath $OutputDirectory -Force | Select-Object -First 1)) {
    throw "Choose an empty output directory. Existing files will not be overwritten: $OutputDirectory"
}
foreach ($asset in @('Map\Editor\index.html', 'Web\ScriptRepo\index.html')) {
    if (!(Test-Path -LiteralPath (Join-Path $WebAssetsRoot $asset))) {
        throw "Missing English web asset: $asset. Run Build/EnglishWeb/build.ps1 first."
    }
}
# Retire superseded releases before allocating another portable runtime. The policy
# pins the user's retained builds and preserves evidence through same-volume moves.
$retentionScript = Join-Path $PSScriptRoot 'manage-release-retention.ps1'
& $retentionScript -Repository $repo -Action Apply -PublishDirectory $OutputDirectory
& (Join-Path $repo 'tools\quest-pilot\check-storage-headroom.ps1') -Repository $repo -PublishDirectory $OutputDirectory
# Honor the configured NuGet sources and existing package cache throughout publication.
& $DotNet run --project (Join-Path $repo 'Build\BetterGenshinImpact.I18nSync') -p:UseSharedCompilation=false -- --project (Join-Path $repo 'BetterGenshinImpact') --check-english
if ($LASTEXITCODE) { throw 'English coverage check failed.' }
if (!$SkipTests) {
    & $DotNet test (Join-Path $repo 'Test\BetterGenshinImpact.EnglishTest') -c Release -p:Platform=x64 -m:1 -nr:false -p:UseSharedCompilation=false
    if ($LASTEXITCODE) { throw 'English interface regression tests failed.' }
}
& $DotNet publish (Join-Path $repo 'BetterGenshinImpact\BetterGenshinImpact.csproj') -c Release -p:Platform=x64 -m:1 -nr:false -p:UseSharedCompilation=false -r win-x64 --self-contained true -o $OutputDirectory
if ($LASTEXITCODE) { throw 'English portable publish failed.' }
foreach ($assetDirectory in @('Map\Editor', 'Web\ScriptRepo')) {
    $destination = Join-Path $OutputDirectory "Assets\$assetDirectory"
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $WebAssetsRoot $assetDirectory) |
        Copy-Item -Destination $destination -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $repo 'LICENSE') -Destination $OutputDirectory
Copy-Item -LiteralPath (Join-Path $repo 'Docs\English-Build.txt') -Destination $OutputDirectory
Copy-Item -LiteralPath (Join-Path $repo 'Docs\Local-Setup.txt') -Destination $OutputDirectory
$webSource = Join-Path $OutputDirectory 'English-Web-Source'
New-Item -ItemType Directory -Path $webSource -Force | Out-Null
foreach ($sourceItem in @('README.md', 'source.json', 'build.ps1', 'floor-names.json', 'floor-name-notes.md', 'patches', 'licenses')) {
    Copy-Item -LiteralPath (Join-Path $repo "Build\EnglishWeb\$sourceItem") -Destination $webSource -Recurse -Force
}
# Clean portable defaults for this English-game build. Existing installations are untouched.
$config = @{ otherConfig = @{ uiCultureInfoName = 'en'; gameCultureInfoName = 'en' } }
New-Item -ItemType Directory -Path (Join-Path $OutputDirectory 'User') -Force | Out-Null
$config | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'User\config.json') -Encoding utf8
Get-FileHash -LiteralPath @((Join-Path $OutputDirectory 'BetterGI.exe'), (Join-Path $OutputDirectory 'BetterGI.dll')) -Algorithm SHA256 |
    Select-Object @{Name='File';Expression={Split-Path -Leaf $_.Path}},Algorithm,Hash |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'Build-SHA256.json') -Encoding utf8
$sourceCommit = & git -C $repo rev-parse HEAD
if ($LASTEXITCODE) { throw 'Could not record the source commit.' }
$sdk = (& $DotNet --version).Trim()
if ($LASTEXITCODE) { throw 'Could not record the SDK version.' }
$buildSource = @{ sourceCommit = $sourceCommit; sdk = $sdk; runtime = 'win-x64'; selfContained = $true }
$packagePath = [IO.DirectoryInfo]::new($OutputDirectory)
$numberedRelease = $packagePath.Name -ieq 'BetterGI-English-win-x64' -and $packagePath.Parent.Name -match '^release-r[0-9]+$'
if ($numberedRelease) {
    $status = @(& git -C $repo status --porcelain)
    if ($LASTEXITCODE) { throw 'Could not record source working tree status.' }
    $buildSource.workingTreeDirty = [bool]$status.Count
    if (!$SkipTests) {
        $buildSource.validationConfiguration = 'Release'
        $buildSource.validationKind = 'english-tests'
    }
}
$buildSource | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'Build-Source.json') -Encoding utf8
if ($numberedRelease) {
    & (Join-Path $repo 'tools/rdp-automation/register-build-identity.ps1') -TargetDirectory $OutputDirectory -PreserveWitness
}
# Record generated files while the publish is clean. Later user files and modified
# program files are excluded from automatic retirement by this manifest.
$artifactsRoot = (Join-Path $repo 'artifacts').TrimEnd('\') + '\'
if ($OutputDirectory.StartsWith($artifactsRoot, [StringComparison]::OrdinalIgnoreCase)) {
    & $retentionScript -Repository $repo -Action Register -PublishDirectory $OutputDirectory
}
& $retentionScript -Repository $repo -Action Apply -PublishDirectory $OutputDirectory
Write-Output "English portable build: $OutputDirectory"
