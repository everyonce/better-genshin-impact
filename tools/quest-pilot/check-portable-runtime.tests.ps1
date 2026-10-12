$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'check-portable-runtime.ps1')

function Assert-Throws {
    param([scriptblock]$Body, [string]$ExpectedMessage)
    try { & $Body } catch {
        if ($_.Exception.Message -like "*$ExpectedMessage*") { return }
        throw "Expected error containing '$ExpectedMessage', got '$($_.Exception.Message)'"
    }
    throw "Expected an error containing '$ExpectedMessage'"
}

$fixture = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
try {
    $runtimeConfigPath = Join-Path $fixture 'BetterGI.runtimeconfig.json'
    $depsPath = Join-Path $fixture 'BetterGI.deps.json'
    foreach ($name in @(
        'BetterGI.exe', 'BetterGI.dll', 'coreclr.dll', 'hostfxr.dll', 'hostpolicy.dll',
        'System.Private.CoreLib.dll', 'PresentationFramework.dll', 'WindowsBase.dll'
    )) { Set-Content -LiteralPath (Join-Path $fixture $name) -Value 'fixture' }

    $runtimeConfig = [ordered]@{ runtimeOptions = [ordered]@{
        tfm = 'net8.0'
        includedFrameworks = @(
            [ordered]@{ name = 'Microsoft.NETCore.App'; version = '8.0.31' },
            [ordered]@{ name = 'Microsoft.WindowsDesktop.App'; version = '8.0.31' }
        )
    } }
    $deps = [ordered]@{
        runtimeTarget = [ordered]@{ name = '.NETCoreApp,Version=v8.0/win-x64'; signature = '' }
        targets = [ordered]@{
            '.NETCoreApp,Version=v8.0/win-x64' = [ordered]@{
                'runtimepack.Microsoft.NETCore.App.Runtime.win-x64/8.0.31' = [ordered]@{
                    runtime = [ordered]@{ 'lib/net8.0/System.Private.CoreLib.dll' = [ordered]@{ assemblyVersion = '8.0.0.0' } }
                    native = [ordered]@{ 'runtimes/win-x64/native/coreclr.dll' = [ordered]@{} }
                }
                'runtimepack.Microsoft.WindowsDesktop.App.Runtime.win-x64/8.0.31' = [ordered]@{
                    runtime = [ordered]@{ 'lib/net8.0/PresentationFramework.dll' = [ordered]@{ assemblyVersion = '8.0.0.0' } }
                }
            }
        }
    }

    $runtimeConfig | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $runtimeConfigPath
    $deps | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $depsPath
    $result = Assert-PortableRuntime -Directory $fixture
    if ($result -notlike 'Portable runtime preflight passed:*') { throw 'Valid portable fixture did not pass.' }

    $bad = $runtimeConfig | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $bad.runtimeOptions | Add-Member -NotePropertyName framework -NotePropertyValue ([pscustomobject]@{ name = 'Microsoft.NETCore.App'; version = '8.0.31' })
    $bad | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $runtimeConfigPath
    Assert-Throws { Assert-PortableRuntime -Directory $fixture } 'Framework-dependent runtimeconfig'

    $runtimeConfig | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $runtimeConfigPath
    Remove-Item -LiteralPath (Join-Path $fixture 'hostfxr.dll')
    Assert-Throws { Assert-PortableRuntime -Directory $fixture } 'hostfxr.dll'
    Set-Content -LiteralPath (Join-Path $fixture 'hostfxr.dll') -Value 'fixture'

    $badDeps = $deps | ConvertTo-Json -Depth 10 | ConvertFrom-Json
    $badDeps.targets.PSObject.Properties['.NETCoreApp,Version=v8.0/win-x64'].Value.PSObject.Properties.Remove('runtimepack.Microsoft.WindowsDesktop.App.Runtime.win-x64/8.0.31')
    $badDeps | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $depsPath
    Assert-Throws { Assert-PortableRuntime -Directory $fixture } 'both .NETCore.App and WindowsDesktop runtime packs'

    Write-Output 'Portable-runtime preflight tests passed (valid self-contained fixture and rejection of framework-dependent config, missing host, and incomplete runtime packs).'
}
finally {
    Remove-Item -LiteralPath $fixture -Recurse -Force
}
