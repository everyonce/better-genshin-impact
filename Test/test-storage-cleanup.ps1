$ErrorActionPreference='Stop'
$taskRepo=Split-Path -Parent $PSScriptRoot
$taskRoot=Join-Path $taskRepo ('artifacts/cleanup-routine-test-'+[guid]::NewGuid().ToString('N'))
$taskOld=Join-Path $taskRoot 'old'
$taskKeep=Join-Path $taskRoot 'keep'
$taskManifest=Join-Path $taskRoot 'manifest.json'
$taskAudit=Join-Path $taskRoot 'audit.json'
$taskApply=Join-Path $taskRepo 'tools/quest-pilot/apply-storage-cleanup.ps1'
New-Item -ItemType Directory -Path $taskOld,$taskKeep | Out-Null
try {
    $taskSource=Join-Path $taskOld 'test.dll'
    $taskCopy=Join-Path $taskKeep 'test.dll'
    [IO.File]::WriteAllText($taskSource,'duplicate')
    [IO.File]::WriteAllText($taskCopy,'duplicate')
    @{version=1;files=1;bytes=9;candidates=@(@{path=$taskSource;preserved=$taskCopy;bytes=9;sha256=(Get-FileHash $taskCopy).Hash})} |
        ConvertTo-Json -Depth 5 | Set-Content $taskManifest
    $taskHash=(Get-FileHash $taskManifest).Hash
    $taskRejected=0
    foreach($taskScenario in @('unapproved','changed-copy','protected','locked')) {
        $taskLock=$null
        try {
            if($taskScenario -eq 'changed-copy'){[IO.File]::WriteAllText($taskCopy,'different')}
            if($taskScenario -eq 'locked'){$taskLock=[IO.File]::Open($taskSource,'Open','ReadWrite','None')}
            $taskExpectedHash=if($taskScenario -eq 'unapproved'){'0'*64}else{$taskHash}
            $taskProtected=if($taskScenario -eq 'protected'){@($taskKeep,$taskOld)}else{@($taskKeep)}
            $taskDidReject=$false
            try { & $taskApply -Manifest $taskManifest -ApprovedSha256 $taskExpectedHash -ProtectedRuntimeDirectories $taskProtected -AuditPath $taskAudit | Out-Null }
            catch { $taskDidReject=$true }
            if(-not $taskDidReject -or -not (Test-Path $taskSource)){throw "Unsafe cleanup scenario: $taskScenario"}
            $taskRejected++
        } finally { if($taskLock){$taskLock.Dispose()}; [IO.File]::WriteAllText($taskCopy,'duplicate') }
    }
    $taskCheckpoint=Join-Path $taskKeep 'User/ExternalControl/retention-checkpoint.json'
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskCheckpoint) -Force | Out-Null
    $taskAssembly=Join-Path $taskKeep 'BetterGI.dll'
    [IO.File]::WriteAllText($taskAssembly,'installed build')
    @{version=1;appDirectory=$taskKeep;dllSha256=(Get-FileHash $taskAssembly).Hash;
      state='cleanup-approval-required';cleanupManifestSha256=('0'*64)} | ConvertTo-Json | Set-Content $taskCheckpoint
    $taskDidReject=$false
    try { & $taskApply -Manifest $taskManifest -ApprovedSha256 $taskHash -ProtectedRuntimeDirectories @($taskKeep) -AuditPath $taskAudit -CompleteRuntimeCheckpoint $taskCheckpoint | Out-Null }
    catch { $taskDidReject=$true }
    if(-not $taskDidReject -or -not(Test-Path $taskSource)){throw 'Mismatched checkpoint was not rejected'}
    $taskRecord=Get-Content $taskCheckpoint -Raw | ConvertFrom-Json
    $taskRecord.cleanupManifestSha256=$taskHash
    $taskRecord | ConvertTo-Json | Set-Content $taskCheckpoint
    & $taskApply -Manifest $taskManifest -ApprovedSha256 $taskHash -ProtectedRuntimeDirectories @($taskKeep) -AuditPath $taskAudit -CompleteRuntimeCheckpoint $taskCheckpoint | Out-Null
    $taskResult=Get-Content $taskAudit -Raw | ConvertFrom-Json
    if((Test-Path $taskSource) -or (Get-Content $taskCopy -Raw) -ne 'duplicate' -or $taskResult.deletedFiles -ne 1 -or $taskResult.deletedLogicalBytes -ne 9){throw 'Successful cleanup verification failed'}
    if((Get-Content $taskCheckpoint -Raw | ConvertFrom-Json).state -ne 'completed'){throw 'Successful retirement did not complete its checkpoint'}
    $taskGateRepo=Join-Path $taskRoot 'gate'
    $taskGateApp=Join-Path $taskGateRepo 'artifacts/release-r16/BetterGI-English-win-x64'
    $taskGateCheckpoint=Join-Path $taskGateApp 'User/ExternalControl/retention-checkpoint.json'
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskGateCheckpoint) -Force | Out-Null
    Copy-Item -LiteralPath $taskAssembly -Destination (Join-Path $taskGateApp 'BetterGI.dll')
    foreach($taskState in 'verification-required','completed') {
        @{state=$taskState;dllSha256=(Get-FileHash $taskAssembly).Hash} | ConvertTo-Json | Set-Content $taskGateCheckpoint
        $taskGateOutput=[Collections.Generic.List[string]]::new()
        try { & (Join-Path $taskRepo 'tools/quest-pilot/check-storage-headroom.ps1') -Repository $taskGateRepo | ForEach-Object {$taskGateOutput.Add([string]$_)} }
        catch { } # The real C: free-space floor may independently block this disposable fixture.
        $taskGateRecord=($taskGateOutput -join "`n") | ConvertFrom-Json
        $taskExpectedPending=if($taskState -eq 'completed'){0}else{1}
        if(@($taskGateRecord.pendingRetirementCheckpoints).Count -ne $taskExpectedPending){throw 'Publish gate ignored retirement checkpoint state'}
    }
    "Cleanup routine: $taskRejected unsafe scenarios and 1 mismatched checkpoint rejected; 1 approved deletion and checkpoint completion verified; preserved copy intact."
    'Publish gate: pending retirement blocks the next version; matching completed retirement clears that gate.'
    $taskHistoryRoot=Join-Path $taskRoot 'release-r99/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
    $taskFrames=Join-Path $taskHistoryRoot 'observations/session'
    $taskReports=Join-Path $taskHistoryRoot 'reports'
    New-Item -ItemType Directory -Path $taskFrames,$taskReports -Force | Out-Null
    $taskOldFrame=Join-Path $taskFrames 'frame-0001.png'
    $taskOldMetadata=Join-Path $taskFrames 'frame-0001.json'
    $taskKeepFrame=Join-Path $taskFrames 'frame-0002.png'
    $taskReport=Join-Path $taskReports 'session.json'
    [IO.File]::WriteAllText($taskOldFrame,'old')
    [IO.File]::WriteAllText($taskOldMetadata,'{}')
    [IO.File]::WriteAllText($taskKeepFrame,'keep')
    [IO.File]::WriteAllText($taskReport,'[]')
    $taskHistoryManifest=Join-Path $taskRoot 'historical.json'
    @{version=1;mode='historical-plan-only';root=$taskHistoryRoot;files=1;bytes=3;
      candidates=@(@{path=$taskOldFrame;bytes=3;sha256=(Get-FileHash $taskOldFrame).Hash});
      retained=@(@{path=$taskKeepFrame;bytes=4;sha256=(Get-FileHash $taskKeepFrame).Hash});
      reports=@(@{path=$taskReport;bytes=2;sha256=(Get-FileHash $taskReport).Hash});references=@()} |
      ConvertTo-Json -Depth 6 | Set-Content $taskHistoryManifest
    $taskHistoryHash=(Get-FileHash $taskHistoryManifest).Hash
    $taskDidReject=$false
    try { & $taskApply -Manifest $taskHistoryManifest -ApprovedSha256 $taskHistoryHash -ProtectedRuntimeDirectories @($taskKeep) -AuditPath $taskAudit | Out-Null }
    catch { $taskDidReject=$true }
    if(-not $taskDidReject -or -not(Test-Path $taskOldFrame)){throw 'Unverified historical writers were not rejected'}
    & $taskApply -Manifest $taskHistoryManifest -ApprovedSha256 $taskHistoryHash -ProtectedRuntimeDirectories @($taskKeep) -AuditPath $taskAudit -HistoricalWritersStopped | Out-Null
    if((Test-Path $taskOldFrame) -or -not(Test-Path $taskKeepFrame) -or -not(Test-Path $taskOldMetadata) -or -not(Test-Path $taskReport)){throw 'Historical cleanup failed preservation checks'}
    'Historical migration: same cleanup routine rejects unverified writers and preserves retained PNGs, observation JSON and reports.'
} finally {
    $taskResolved=[IO.Path]::GetFullPath($taskRoot)
    $taskPrefix=(Join-Path $taskRepo 'artifacts').TrimEnd('\')+'\'
    if(-not $taskResolved.StartsWith($taskPrefix,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path -Leaf $taskResolved) -notmatch '^cleanup-routine-test-[a-f0-9]{32}$'){throw 'Unsafe test cleanup target'}
    Remove-Item -LiteralPath $taskResolved -Recurse -Force
}
