<#
.SYNOPSIS
Runs selected agent tests with repository-local temporary storage.
.DESCRIPTION
Windows sandbox temporary directories can refuse atomic file replacement.
Keep these inert tests in the writable workspace without changing production
control checks, requesting elevation, or starting BetterGI or a model.
#>
param(
    [string]$Python = 'C:\Programs\Python\Python311\python.exe',
    [string[]]$Modules = @(
        'test_combat_trial',
        'test_combat_paused_review',
        'test_combat_paused_file_admission',
        'test_audit_combat_paused_review'
    )
)

$ErrorActionPreference = 'Stop'
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$temporaryDirectory = Join-Path $repository 'artifacts\test-tmp'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "The installed Python interpreter is missing: $Python"
}
if (-not $Modules.Count -or @($Modules | Where-Object { $_ -notmatch '^test_[a-z0-9_]+(?:\.[A-Za-z0-9_]+)*$' }).Count) {
    throw 'Provide one or more local unittest module, class, or method names.'
}

# Restore the caller's environment; individual fixtures own their unique folders.
$previousTemp = [Environment]::GetEnvironmentVariable('TEMP', 'Process')
$previousTmp = [Environment]::GetEnvironmentVariable('TMP', 'Process')
New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
Push-Location (Join-Path $repository 'tools\bettergi-agent')
try {
    $env:TEMP = $temporaryDirectory
    $env:TMP = $temporaryDirectory
    & $Python -E -B -X utf8 -m unittest -v @Modules
    if ($LASTEXITCODE -ne 0) {
        throw "Agent tests failed (exit $LASTEXITCODE)."
    }
}
finally {
    [Environment]::SetEnvironmentVariable('TEMP', $previousTemp, 'Process')
    [Environment]::SetEnvironmentVariable('TMP', $previousTmp, 'Process')
    Pop-Location
}
