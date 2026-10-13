param(
    [Parameter(Mandatory)][string]$SourceRuntime,
    [Parameter(Mandatory)][string]$TestedOutput,
    [Parameter(Mandatory)][string]$Destination
)
$ErrorActionPreference='Stop'
$taskRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
& (Join-Path $PSScriptRoot 'check-storage-headroom.ps1') -Repository $taskRepo
$taskSource=(Resolve-Path -LiteralPath $SourceRuntime).Path
$taskTested=(Resolve-Path -LiteralPath $TestedOutput).Path
$taskDestination=[IO.Path]::GetFullPath($Destination)
$taskRelative=[IO.Path]::GetRelativePath($taskRepo,$taskDestination)
if($taskRelative -notmatch '^artifacts\\release-r[0-9]+\\BetterGI-English-win-x64$' -or (Test-Path -LiteralPath $taskDestination)) { throw 'Choose one new managed portable runtime directory' }
& (Join-Path $PSScriptRoot 'check-portable-runtime.ps1') -AppDirectory $taskSource
$taskNewDeps=Get-Content -LiteralPath (Join-Path $taskTested 'BetterGI.deps.json') -Raw | ConvertFrom-Json
$taskOldDeps=Get-Content -LiteralPath (Join-Path $taskSource 'BetterGI.deps.json') -Raw | ConvertFrom-Json
$taskPackages=@($taskOldDeps.libraries.PSObject.Properties | Where-Object {$_.Value.type -eq 'package'} | Select-Object -ExpandProperty Name)
foreach($taskPackage in $taskNewDeps.libraries.PSObject.Properties | Where-Object {$_.Value.type -eq 'package'}) {
    if($taskPackage.Name -notin $taskPackages){throw "Portable dependency differs from tested package graph: $($taskPackage.Name)"}
}
function Copy-OrdinaryFile([string]$Source,[string]$Target) {
    $taskItem=Get-Item -LiteralPath $Source -Force
    if($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked source file rejected'}
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Target))
    [IO.File]::Copy($Source,$Target,$true)
}
foreach($taskFile in Get-ChildItem -LiteralPath $taskSource -Recurse -File) {
    $taskChild=[IO.Path]::GetRelativePath($taskSource,$taskFile.FullName)
    if($taskChild -match '^(User|Logs?)(\\|$)'){continue}
    Copy-OrdinaryFile $taskFile.FullName (Join-Path $taskDestination $taskChild)
}
# Retain compatible self-contained runtime/deps files, but install the exact tested
# project assemblies. No package version or native dependency changes are allowed.
foreach($taskProject in $taskNewDeps.libraries.PSObject.Properties | Where-Object {$_.Value.type -eq 'project'}) {
    $taskName=($taskProject.Name -split '/')[0]
    foreach($taskExtension in '.dll','.pdb') {
        $taskAssembly=Join-Path $taskTested ($taskName+$taskExtension)
        if(Test-Path -LiteralPath $taskAssembly){Copy-OrdinaryFile $taskAssembly (Join-Path $taskDestination ($taskName+$taskExtension))}
    }
}
foreach($taskFile in Get-ChildItem -LiteralPath (Join-Path $taskSource 'User') -Recurse -File) {
    $taskChild=[IO.Path]::GetRelativePath($taskSource,$taskFile.FullName)
    if($taskChild -match '^User\\JsScript\\ActOnePilot\\' -or $taskChild -match '\\(observations|reports|receipts|revisions|Logs?)\\' -or $taskChild -match '\\retention-checkpoint\.json$'){continue}
    Copy-OrdinaryFile $taskFile.FullName (Join-Path $taskDestination $taskChild)
}
foreach($taskTracked in git -C $taskRepo ls-files 'BetterGenshinImpact/User/JsScript/ActOnePilot/*') {
    $taskChild=$taskTracked.Substring('BetterGenshinImpact/'.Length)
    Copy-OrdinaryFile (Join-Path $taskRepo $taskTracked) (Join-Path $taskDestination $taskChild)
}
$taskGroup=Join-Path $taskDestination 'User/ScriptGroup/ActOneRun.json'
$taskConfiguration=Get-Content -LiteralPath $taskGroup -Raw | ConvertFrom-Json
foreach($taskProject in $taskConfiguration.projects){$taskProject.jsScriptSettingsObject.enableInput=$false}
$taskConfiguration | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $taskGroup -Encoding utf8
& (Join-Path $PSScriptRoot 'check-portable-runtime.ps1') -AppDirectory $taskDestination
$taskExpected=(Get-FileHash -LiteralPath (Join-Path $taskTested 'BetterGI.dll')).Hash
if((Get-FileHash -LiteralPath (Join-Path $taskDestination 'BetterGI.dll')).Hash -ne $taskExpected){throw 'Staged DLL differs from tested assembly'}
[pscustomobject]@{utc=(Get-Date).ToUniversalTime().ToString('o');sourceRuntime=$taskSource;testedOutput=$taskTested;
    destination=$taskDestination;dllSha256=$taskExpected;exeSha256=(Get-FileHash -LiteralPath (Join-Path $taskDestination 'BetterGI.exe')).Hash;
    supervisedInputEnabled=$false;historicalCapturesCopied=$false} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $taskRepo 'artifacts/retention-r16-staging.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskRepo 'artifacts/retention-r16-staging.json')
