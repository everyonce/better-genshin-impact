param([string]$DotNet = 'dotnet')
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
& $DotNet run --project (Join-Path $repo 'Build\BetterGenshinImpact.I18nSync') -p:RestoreSources=https://api.nuget.org/v3/index.json -- --project (Join-Path $repo 'BetterGenshinImpact') --check-english
exit $LASTEXITCODE
