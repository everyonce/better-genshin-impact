param(
    [string] $WorkRoot = (Join-Path $PSScriptRoot '.work')
)

$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'source.json') -Raw | ConvertFrom-Json

function Assert-Sha256([string] $Path, [string] $Expected) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) {
        throw "SHA-256 mismatch for $Path. Expected $Expected, found $actual."
    }
}

Assert-Sha256 (Join-Path $PSScriptRoot 'patches/map-editor-english.patch') $manifest.map.patchSha256
Assert-Sha256 (Join-Path $PSScriptRoot $manifest.map.displayLabels) $manifest.map.displayLabelsSha256
Assert-Sha256 (Join-Path $PSScriptRoot 'patches/script-web-english.patch') $manifest.scriptWeb.patchSha256

$sources = @(
    @{
        Name = 'map'
        Url = 'https://github.com/huiyadanli/bettergi-map.git'
        Commit = 'e08ea2a47bec72783a90f507d4fa3b931ad0ff0a'
        Patch = Join-Path $PSScriptRoot 'patches/map-editor-english.patch'
        BuildCommand = @('run', 'build:single')
        Artifact = 'dist/index.html'
        Destination = Join-Path $PSScriptRoot 'dist/Map/Editor/index.html'
    },
    @{
        Name = 'script-web'
        Url = 'https://github.com/zaodonganqi/bettergi-script-web.git'
        Commit = '48ddacfa693d2c0c88831f44c9b2a892c1446043'
        Patch = Join-Path $PSScriptRoot 'patches/script-web-english.patch'
        BuildCommand = @('run', 'build')
        Artifact = 'dist/index.html'
        Destination = Join-Path $PSScriptRoot 'dist/Web/ScriptRepo/index.html'
    }
)

function Invoke-Checked([string] $File, [string[]] $Arguments, [string] $WorkingDirectory) {
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

$resolvedWorkRoot = [System.IO.Path]::GetFullPath($WorkRoot)
New-Item -ItemType Directory -Path $resolvedWorkRoot -Force | Out-Null
$runRoot = Join-Path $resolvedWorkRoot ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

foreach ($source in $sources) {
    $checkout = Join-Path $runRoot $source.Name
    New-Item -ItemType Directory -Path $checkout -Force | Out-Null
    Invoke-Checked 'git' @('init', '--quiet') $checkout
    Invoke-Checked 'git' @('remote', 'add', 'origin', $source.Url) $checkout
    Invoke-Checked 'git' @('fetch', '--quiet', '--depth=1', 'origin', $source.Commit) $checkout
    Invoke-Checked 'git' @('checkout', '--quiet', '--detach', 'FETCH_HEAD') $checkout
    Invoke-Checked 'git' @('apply', '--check', $source.Patch) $checkout
    Invoke-Checked 'git' @('apply', $source.Patch) $checkout
    if ($source.Name -eq 'map') {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'floor-names.json') `
            -Destination (Join-Path $checkout 'src/config/teyvatFloorNameEn.json') -Force
    }
    Invoke-Checked 'npm' @('ci') $checkout
    Invoke-Checked 'npm' $source.BuildCommand $checkout

    $artifact = Join-Path $checkout $source.Artifact
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
        throw "Expected build artifact was not created: $artifact"
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $source.Destination) -Force | Out-Null
    Copy-Item -LiteralPath $artifact -Destination $source.Destination -Force
    Write-Host "Built $($source.Name): $($source.Destination)"
}
