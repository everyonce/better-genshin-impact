# Pure package and process-identity checks shared by the launcher and its tests.
Set-StrictMode -Version Latest

function Get-LocalHostPath {
    param([Parameter(Mandatory)][string] $Path)
    if ($Path -notmatch '^[A-Za-z]:[\\/]' -or $Path.StartsWith('\\') -or $Path.Contains([char]0)) {
        throw 'A local absolute path is required.'
    }
    return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Assert-NoHostLinks {
    param([Parameter(Mandatory)][string] $Path)
    # Reject redirected files and ancestors before accepting any executable bytes.
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse points are not supported in a release path: $($item.FullName)"
        }
        $item = if ($item -is [IO.DirectoryInfo]) { $item.Parent } else { $item.Directory }
    }
}

function Get-HostSha256 {
    param([Parameter(Mandatory)][string] $Path)
    # Framework hashing also works when a restricted shell cannot auto-load Get-FileHash.
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}

function Get-VerifiedHostPackage {
    param([Parameter(Mandatory)][string] $TargetDirectory)
    $target = Get-LocalHostPath $TargetDirectory
    $releaseRoot = Split-Path -Parent $target
    if ((Split-Path -Leaf $target) -ine 'BetterGI-English-win-x64' -or
        (Split-Path -Leaf $releaseRoot) -notmatch '^release-r([0-9]+)$') {
        throw 'Choose a numbered release-rN/BetterGI-English-win-x64 portable package.'
    }
    $releaseNumber = [long]$Matches[1]
    Assert-NoHostLinks $target
    $manifestPath = Join-Path $releaseRoot 'build-manifest.json'
    Assert-NoHostLinks $manifestPath
    if ((Get-Item -LiteralPath $manifestPath).Length -gt 65536) { throw 'The build manifest is too large.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.version -ne 1 -or (Get-LocalHostPath $manifest.targetDirectory) -ine $target) {
        throw 'The build manifest version or target directory does not match this package.'
    }
    foreach ($binary in @(@('BetterGI.exe', 'exeSha256'), @('BetterGI.dll', 'dllSha256'))) {
        $path = Join-Path $target $binary[0]
        Assert-NoHostLinks $path
        $expected = [string]$manifest.($binary[1])
        if ($expected -notmatch '^[a-fA-F0-9]{64}$' -or
            (Get-Item -LiteralPath $path).Length -eq 0 -or
            (Get-HostSha256 $path) -ine $expected) {
            throw "Build manifest hash mismatch: $($binary[0])"
        }
    }
    # A valid app hash alone does not establish that its portable runtime was published.
    foreach ($file in @('hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll', 'System.Private.CoreLib.dll', 'PresentationFramework.dll',
                        'BetterGI.runtimeconfig.json', 'BetterGI.deps.json')) {
        $path = Join-Path $target $file
        Assert-NoHostLinks $path
        if ((Get-Item -LiteralPath $path).Length -eq 0) { throw "The portable package is missing $file." }
    }
    $runtime = (Get-Content -LiteralPath (Join-Path $target 'BetterGI.runtimeconfig.json') -Raw -Encoding UTF8 | ConvertFrom-Json).runtimeOptions
    $names = @($runtime.includedFrameworks | ForEach-Object { $_.name } | Sort-Object)
    $expectedNames = @('Microsoft.AspNetCore.App', 'Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App')
    if ($runtime.tfm -ne 'net10.0' -or $runtime.PSObject.Properties['framework'] -or $runtime.PSObject.Properties['frameworks'] -or
        $names.Count -ne 3 -or ($names -join ',') -ne ($expectedNames -join ',') -or
        @($runtime.includedFrameworks | Where-Object { $_.version -notmatch '^10\.0\.\d+$' }).Count -ne 0) {
        throw 'The package must contain the self-contained .NET10 desktop runtime.'
    }
    $deps = Get-Content -LiteralPath (Join-Path $target 'BetterGI.deps.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($deps.runtimeTarget.name -ne '.NETCoreApp,Version=v10.0/win-x64') { throw 'The package must target win-x64.' }
    return [pscustomobject]@{
        release = $releaseNumber; targetDirectory = $target; manifestPath = $manifestPath
        executablePath = Join-Path $target 'BetterGI.exe'
        exeSha256 = ([string]$manifest.exeSha256).ToLowerInvariant()
        dllSha256 = ([string]$manifest.dllSha256).ToLowerInvariant()
    }
}

function Select-VerifiedHostPackage {
    param([Parameter(Mandatory)][string] $ArtifactsDirectory, [string] $TargetDirectory = '')
    if ($TargetDirectory) {
        return [pscustomobject]@{ package = Get-VerifiedHostPackage $TargetDirectory; skippedPackages = @() }
    }
    $artifacts = Get-LocalHostPath $ArtifactsDirectory
    $skipped = [Collections.Generic.List[object]]::new()
    $releases = @(Get-ChildItem -LiteralPath $artifacts -Directory | Where-Object { $_.Name -match '^release-r[0-9]+$' } |
        Sort-Object { [long]($_.Name.Substring(9)) } -Descending)
    foreach ($release in $releases) {
        try {
            $package = Get-VerifiedHostPackage (Join-Path $release.FullName 'BetterGI-English-win-x64')
            return [pscustomobject]@{ package = $package; skippedPackages = @($skipped.ToArray()) }
        }
        catch { $skipped.Add([pscustomobject]@{ directory = $release.FullName; reason = $_.Exception.Message }) }
    }
    throw "No verified numbered portable release was found in $artifacts. Rejected packages: $($skipped | ConvertTo-Json -Compress)"
}

function Test-HostIdentity {
    param([Parameter(Mandatory)] $Status, [Parameter(Mandatory)] $Package,
          [Parameter(Mandatory)][int] $WindowsSessionId, [int] $ExpectedProcessId = 0)
    # Malformed or incomplete status is never sufficient evidence to reuse a process.
    try {
        return ($Status.instanceType -eq 'Primary' -and $Status.automationEnabled -is [bool] -and $Status.automationEnabled -eq $true -and
            $Status.remoteDesktop -is [bool] -and $Status.remoteDesktop -eq $false -and $Status.windowsSessionId -eq $WindowsSessionId -and
            $Status.processId -gt 0 -and ($ExpectedProcessId -eq 0 -or $Status.processId -eq $ExpectedProcessId) -and
            $Status.instanceNonce -is [string] -and $Status.instanceNonce.Length -gt 0 -and
            (Get-LocalHostPath $Status.appDirectory) -ieq $Package.targetDirectory -and
            $Status.assemblySha256 -ieq $Package.dllSha256)
    }
    catch { return $false }
}

function Select-StartedHost {
    param([object[]] $Instances = @(), [Parameter(Mandatory)] $Package,
          [Parameter(Mandatory)][int] $WindowsSessionId, [int[]] $BeforeProcessIds = @())
    # The unelevated loader may exit after App.UseElevated starts a different PID.
    # Trust the verified endpoint identity, never the lifetime of that initial loader.
    $roots = @($Instances | Where-Object { $_.instanceType -eq 'Primary' -and $_.windowsSessionId -eq $WindowsSessionId })
    if ($roots.Count -gt 1) { throw 'Multiple primary hosts appeared during startup; select and inspect their identities manually.' }
    if ($roots.Count -eq 0) { return $null }
    $candidate = $roots[0]
    if ($BeforeProcessIds -contains $candidate.processId -or -not (Test-HostIdentity $candidate $Package $WindowsSessionId)) {
        throw 'An incompatible primary appeared during startup; its role, package, hash, session, or automation identity does not match.'
    }
    return $candidate
}

Export-ModuleMember -Function Select-VerifiedHostPackage, Get-VerifiedHostPackage, Test-HostIdentity, Select-StartedHost
