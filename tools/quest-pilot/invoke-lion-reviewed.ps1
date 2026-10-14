param(
    [Parameter(Mandatory)][string]$Session,
    [Parameter(Mandatory)][int]$Frame,
    [Parameter(Mandatory)][int]$Witness,
    [ValidateSet('walk','carefulWalk','jumpForward','boardPlatform','disembarkPlatform','carefulBoard','carefulDisembark','carefulDisembarkActive','carefulWind','carefulGlide','probe','windLaunch','glideForward','openDoor','openChest','activateMechanism','electroAttack','electroTrial','normalBurst','selectKaeya','selectTraveler','selectLisa','selectAmber','kaeyaCombat','lisaCombat','travelerCombat','amberCombat','lisaRescueBurst','nativeCombat','collectLoot')][string]$Action='walk',
    [ValidateRange(-750,750)][int]$Turn=0,
    [ValidateRange(0,8)][int]$Holds=0,
    [ValidateSet(200,400,800)][int]$MoveMs=800,
    [ValidateSet('VK_W','VK_A','VK_S','VK_D')][string]$MoveKey='VK_W',
    [int]$WindTutorialFrame=0,
    [switch]$CombatReviewed,
    [Parameter(Mandatory)][string]$AppDir,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][int]$WindowsSessionId
)
$ErrorActionPreference='Stop'
# Convenience wrapper only: one explicitly reviewed request, never a replay.
# The existing client and in-game adapter retain all ownership/freshness guards.
if($Session -notmatch '^[a-z0-9-]+$' -or $Frame -le $Witness -or $Witness -lt 0){throw 'Pinned session and earlier witness required'}
$taskApp=(Resolve-Path -LiteralPath $AppDir).Path
$taskRuntime=Join-Path $taskApp 'User/JsScript/ActOnePilot'
$taskPermit=@{session=$Session;frameId=$Frame;witnessFrameId=$Witness;reviewed=$true;
    action=$Action;relativeDx=$Turn;holds=$Holds;moveKey=$MoveKey;moveMs=$MoveMs;combatReviewed=[bool]$CombatReviewed;
    windTutorialFrameId=$WindTutorialFrame;createdAt=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()}
$taskPermit|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $taskRuntime 'lion-visual-move.json')
$env:BETTERGI_PILOT_APP_DIR=$taskApp
$taskLines=@(& $Python (Join-Path $PSScriptRoot 'act-one-command.py') questStep --step lionVisualMove --session $Session --frame $Frame --expected-windows-session-id $WindowsSessionId --compact --wait-seconds 25)
if($LASTEXITCODE -ne 0){$taskLines|Write-Output;throw 'Controller client failed; inspect exact receipt, do not replay'}
$taskTerminal=$null
foreach($taskLine in $taskLines){
    try{$taskRecord=$taskLine|ConvertFrom-Json}catch{$taskLine|Write-Output;continue}
    if($taskRecord.result){$taskTerminal=$taskRecord}else{$taskLine|Write-Output}
}
if(!$taskTerminal){return} # Pending is left pending; never submit another request.
$taskTerminal|Select-Object submittedId,status,result,elapsedMs,frameId,latestFrameId,controllerQuiescent|ConvertTo-Json -Depth 8
if(!$taskTerminal.controllerQuiescent){return}
$taskField=$taskTerminal.result.fieldFrameId
if($null -ne $taskField){
    $taskCapture=Join-Path $taskRuntime ('observations/{0}/frame-{1:0000}.png' -f $Session,[int]$taskField)
    if(Test-Path -LiteralPath $taskCapture){& (Join-Path $PSScriptRoot 'preview-capture.ps1') -Path $taskCapture}
}
