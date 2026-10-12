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
    if ($null -eq $runtimeOptions -or $runtimeOptions.tfm -ne 'net8.0') {
        throw 'Portable runtimeconfig must target net8.0.'
    }
    if ($runtimeOptions.PSObject.Properties.Name -contains 'framework' -or
        $runtimeOptions.PSObject.Properties.Name -contains 'frameworks') {
        throw 'Framework-dependent runtimeconfig is not safe for a portable restart.'
    }

    $included = @($runtimeOptions.includedFrameworks)
    $names = @($included | ForEach-Object { [string]$_.name } | Sort-Object -Unique)
    if ($included.Count -ne 2 -or $names.Count -ne 2 -or
        -not ($names -ccontains 'Microsoft.NETCore.App') -or
        -not ($names -ccontains 'Microsoft.WindowsDesktop.App')) {
        throw 'Portable runtimeconfig must include exactly Microsoft.NETCore.App and Microsoft.WindowsDesktop.App.'
    }
    foreach ($framework in $included) {
        if ([string]$framework.version -notmatch '^8\.0\.[0-9]+$') {
            throw "Portable runtimeconfig has an unexpected framework version: $($framework.name) $($framework.version)"
        }
    }

    $deps = Read-RuntimeJson -Path (Join-Path $appRoot 'BetterGI.deps.json') -MaxBytes 33554432
    $targetName = [string]$deps.runtimeTarget.name
    if ($targetName -notmatch '^\.NETCoreApp,Version=v8\.0/win-x64$') {
        throw "Portable deps file has an unexpected runtime target: $targetName"
    }
    $target = $deps.targets.PSObject.Properties[$targetName].Value
    if ($null -eq $target) { throw 'Portable deps file is missing its win-x64 target.' }
    $runtimePacks = @($target.PSObject.Properties | Where-Object {
        $_.Name -like 'runtimepack.Microsoft.NETCore.App.Runtime.win-x64/*' -or
        $_.Name -like 'runtimepack.Microsoft.WindowsDesktop.App.Runtime.win-x64/*'
    })
    if ($runtimePacks.Count -ne 2 -or
        -not ($runtimePacks.Name | Where-Object { $_ -like 'runtimepack.Microsoft.NETCore.App.Runtime.win-x64/*' }) -or
        -not ($runtimePacks.Name | Where-Object { $_ -like 'runtimepack.Microsoft.WindowsDesktop.App.Runtime.win-x64/*' })) {
        throw 'Portable deps file must contain both .NETCore.App and WindowsDesktop runtime packs.'
    }
    foreach ($pack in $runtimePacks) {
        if (@($pack.Value.runtime.PSObject.Properties).Count -eq 0) {
            throw "Portable deps runtime pack has no runtime assets: $($pack.Name)"
        }
        $frameworkName = if ($pack.Name -like 'runtimepack.Microsoft.NETCore.App.Runtime.win-x64/*') {
            'Microsoft.NETCore.App'
        }
        else { 'Microsoft.WindowsDesktop.App' }
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
