param(
    [string]$DotNet,
    [string]$OutputDirectory,
    [switch]$RebuildWeb
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$toolchain = Join-Path $repo 'artifacts\toolchain'
if (!$DotNet) {
    $localDotNet = Join-Path $toolchain 'dotnet\dotnet.exe'
    $DotNet = if (Test-Path -LiteralPath $localDotNet) { $localDotNet } else { 'dotnet' }
}
$env:DOTNET_CLI_HOME = Join-Path $toolchain 'dotnet-home'
$env:NUGET_PACKAGES = Join-Path $repo 'packages'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $toolchain 'nuget-http'
$env:NUGET_SCRATCH = Join-Path $toolchain 'nuget-scratch'
$env:NUGET_PLUGINS_CACHE_PATH = Join-Path $toolchain 'nuget-plugins'
$env:DOTNET_CLI_USE_MSBUILD_SERVER = '0'
$taskTemp = Join-Path $repo 'artifacts\test-tmp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$localNode = Get-ChildItem -LiteralPath $toolchain -Directory -Filter 'node-*-win-x64' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($localNode) { $env:PATH = $localNode.FullName + [IO.Path]::PathSeparator + $env:PATH }
$env:npm_config_cache = Join-Path $toolchain 'npm-cache'
$sdkVersion = & $DotNet --version
if ($LASTEXITCODE -or [version]($sdkVersion -replace '-.*$', '') -lt [version]'10.0.100') {
    throw 'Install the .NET 10 SDK, or provide its dotnet.exe with -DotNet.'
}
if ($RebuildWeb -or !(Test-Path -LiteralPath (Join-Path $repo 'Build\EnglishWeb\dist\Map\Editor\index.html')) -or !(Test-Path -LiteralPath (Join-Path $repo 'Build\EnglishWeb\dist\Web\ScriptRepo\index.html'))) {
    & (Join-Path $repo 'Build\EnglishWeb\build.ps1')
}
$publishArguments = @{ DotNet = $DotNet }
if ($OutputDirectory) { $publishArguments.OutputDirectory = $OutputDirectory }
& (Join-Path $PSScriptRoot 'publish-english.ps1') @publishArguments
