param(
    [string]$AppDirectory
)

$ErrorActionPreference = 'Stop'

function Read-RuntimeJson {
    param([string]$Path, [int]$MaxBytes)

    $file = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($file.PSIsContainer -or $file.Length -le 0 -or $file.Length -gt $MaxBytes) {
        throw "Runtime preflight file is missing, empty, or too large: $(Split-Path -Leaf $Path)"
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
}

function Assert-PortableRuntime {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $appRoot = [IO.Path]::GetFullPath($Directory)
    if (-not (Test-Path -LiteralPath $appRoot -PathType Container)) {
        throw "Portable application directory does not exist: $appRoot"
    }

    $runtimeConfig = Read-RuntimeJson -Path (Join-Path $appRoot 'BetterGI.runtimeconfig.json') -MaxBytes 65536
    $runtimeOptions = $runtimeConfig.runtimeOptions
    if ($null -eq $runtimeOptions -or $runtimeOptions.tfm -notin @('net8.0', 'net10.0')) {
        throw 'Portable runtimeconfig must target a supported BetterGI runtime (net8.0 or net10.0).'
    }
    $frameworkVersion = $runtimeOptions.tfm.Substring(3)
    if ($runtimeOptions.PSObject.Properties.Name -contains 'framework' -or
        $runtimeOptions.PSObject.Properties.Name -contains 'frameworks') {
        throw 'Framework-dependent runtimeconfig is not safe for a portable restart.'
    }

    $included = @($runtimeOptions.includedFrameworks)
    $names = @($included | ForEach-Object { [string]$_.name } | Sort-Object -Unique)
    $knownNames = @('Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App', 'Microsoft.AspNetCore.App')
    if ($included.Count -ne $names.Count -or
        @($names | Where-Object { $knownNames -cnotcontains $_ }).Count -or
        $names -cnotcontains 'Microsoft.NETCore.App' -or $names -cnotcontains 'Microsoft.WindowsDesktop.App') {
        throw 'Portable runtimeconfig must include .NETCore.App and WindowsDesktop.App and only recognized frameworks.'
    }
    foreach ($framework in $included) {
        if ([string]$framework.version -notmatch ('^' + [regex]::Escape($frameworkVersion) + '\.[0-9]+$')) {
            throw "Portable runtimeconfig has an unexpected framework version: $($framework.name) $($framework.version)"
        }
    }

    $deps = Read-RuntimeJson -Path (Join-Path $appRoot 'BetterGI.deps.json') -MaxBytes 33554432
    $targetName = [string]$deps.runtimeTarget.name
    if ($targetName -cne ".NETCoreApp,Version=v$frameworkVersion/win-x64") {
        throw "Portable deps file has an unexpected runtime target: $targetName"
    }
    $target = $deps.targets.PSObject.Properties[$targetName].Value
    if ($null -eq $target) { throw 'Portable deps file is missing its win-x64 target.' }
    # Every declared runtime has one matching local pack. Ref packs are independent of framework versions.
    foreach ($frameworkName in $knownNames) {
        $packs = @($target.PSObject.Properties | Where-Object { $_.Name -like "runtimepack.$frameworkName.Runtime.win-x64/*" })
        if ($names -cnotcontains $frameworkName) {
            if ($packs.Count) { throw "Portable runtimeconfig omits the declared runtime pack: $frameworkName" }
            continue
        }
        if ($packs.Count -ne 1) {
            throw "Portable deps file must contain both .NETCore.App and WindowsDesktop runtime packs and every declared framework: $frameworkName"
        }
        $pack = $packs[0]
        if (@($pack.Value.runtime.PSObject.Properties).Count -eq 0) {
            throw "Portable deps runtime pack has no runtime assets: $($pack.Name)"
        }
        $packVersion = ($pack.Name -split '/')[-1]
        $configuredVersion = [string](@($included | Where-Object { $_.name -ceq $frameworkName })[0].version)
        if ($packVersion -cne $configuredVersion) {
            throw "Portable deps runtime pack version does not match runtimeconfig for $frameworkName."
        }
    }

    foreach ($name in @(
        'BetterGI.exe', 'BetterGI.dll', 'coreclr.dll', 'hostfxr.dll', 'hostpolicy.dll',
        'System.Private.CoreLib.dll', 'PresentationFramework.dll', 'WindowsBase.dll'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $appRoot $name) -PathType Leaf)) {
            throw "Portable runtime file is missing: $name"
        }
    }

    return "Portable runtime preflight passed: $appRoot"
}

if (-not [string]::IsNullOrWhiteSpace($AppDirectory)) {
    Assert-PortableRuntime -Directory $AppDirectory
}
elseif ($MyInvocation.InvocationName -ne '.') {
    throw 'Pass -AppDirectory with the staged BetterGI application directory.'
}
