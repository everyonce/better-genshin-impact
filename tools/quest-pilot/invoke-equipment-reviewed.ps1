param(
    [Parameter(Mandatory)][string]$Session,
    [Parameter(Mandatory)][int]$Frame,
    [ValidateSet('inspect','equip','back','addOre','enhanceWeapon')][string]$Action='inspect',
    [Parameter(Mandatory)][int]$X,
    [Parameter(Mandatory)][int]$Y,
    [Parameter(Mandatory)][string[]]$Evidence,
    [Parameter(Mandatory)][string]$AppDir,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][int]$WindowsSessionId
)
$ErrorActionPreference='Stop'
$taskApp=(Resolve-Path -LiteralPath $AppDir).Path
$taskRuntime=Join-Path $taskApp 'User/JsScript/ActOnePilot'
$taskObservation=Get-Content -LiteralPath (Join-Path $taskRuntime 'observation.json') -Raw|ConvertFrom-Json
if($taskObservation.session -ne $Session -or $taskObservation.frameId -ne $Frame){throw 'Pinned observation changed'}
$taskEvidence=@(foreach($taskLabel in $Evidence){
    $taskRows=@($taskObservation.ocr|Where-Object {$_.text.Trim() -ceq $taskLabel})
    if($taskRows.Count -ne 1){throw "Unique reviewed label missing: $taskLabel"}
    @{text=$taskLabel;x=[int]$taskRows[0].x;y=[int]$taskRows[0].y}
})
@{session=$Session;frameId=$Frame;reviewed=$true;createdAt=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();
    action=$Action;x=$X;y=$Y;evidence=$taskEvidence}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $taskRuntime 'lion-menu-review.json')
$env:BETTERGI_PILOT_APP_DIR=$taskApp
$taskLines=@(& $Python (Join-Path $PSScriptRoot 'act-one-command.py') questStep --step lisaTeamReview --session $Session --frame $Frame --expected-windows-session-id $WindowsSessionId --compact --wait-seconds 25)
$taskLines|Write-Output
if($LASTEXITCODE -ne 0){throw 'Controller client failed; inspect exact receipt, never replay'}
foreach($taskLine in $taskLines){
    try{$taskRecord=$taskLine|ConvertFrom-Json}catch{continue}
    if($taskRecord.controllerQuiescent -and $taskRecord.screenshot -and (Test-Path -LiteralPath $taskRecord.screenshot)){
        & (Join-Path $PSScriptRoot 'preview-capture.ps1') -Path $taskRecord.screenshot
    }
}
