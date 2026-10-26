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
& (Join-Path $repo 'tools\quest-pilot\check-storage-headroom.ps1') -Repository $repo
& $DotNet run --project (Join-Path $repo 'Build\BetterGenshinImpact.I18nSync') -p:UseSharedCompilation=false -p:RestoreSources=https://api.nuget.org/v3/index.json -- --project (Join-Path $repo 'BetterGenshinImpact') --check-english
if ($LASTEXITCODE) { throw 'English coverage check failed.' }
if (!$SkipTests) {
    & $DotNet test (Join-Path $repo 'Test\BetterGenshinImpact.EnglishTest') -c Release -p:Platform=x64 -m:1 -nr:false -p:UseSharedCompilation=false -p:RestoreSources=https://api.nuget.org/v3/index.json
    if ($LASTEXITCODE) { throw 'English interface regression tests failed.' }
}
& $DotNet publish (Join-Path $repo 'BetterGenshinImpact\BetterGenshinImpact.csproj') -c Release -p:Platform=x64 -m:1 -nr:false -p:UseSharedCompilation=false -r win-x64 --self-contained true -p:RestoreSources=https://api.nuget.org/v3/index.json -o $OutputDirectory
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
@{ sourceCommit = $sourceCommit; sdk = (& $DotNet --version); runtime = 'win-x64'; selfContained = $true } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'Build-Source.json') -Encoding utf8
# Record generated files while the publish is clean. Later user files and modified
# program files are excluded from automatic retirement by this manifest.
$artifactsRoot = (Join-Path $repo 'artifacts').TrimEnd('\') + '\'
if ($OutputDirectory.StartsWith($artifactsRoot, [StringComparison]::OrdinalIgnoreCase)) {
    & $retentionScript -Repository $repo -Action Register -PublishDirectory $OutputDirectory
}
& $retentionScript -Repository $repo -Action Apply -PublishDirectory $OutputDirectory
Write-Output "English portable build: $OutputDirectory"
