param([int]$SessionId=5, [string]$Group='ActOneRun', [int]$RestartPid=0)
$ErrorActionPreference='Stop'
$root=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../artifacts/release-r8/BetterGI-English-win-x64'))
$exe=Join-Path $root 'BetterGI.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Pilot executable missing' }
if ($Group -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid group' }
$game=@(Get-Process GenshinImpact -ErrorAction Stop)
if ($game.Count -ne 1 -or $game[0].SessionId -ne $SessionId -or $SessionId -eq [System.Diagnostics.Process]::GetCurrentProcess().SessionId) { throw 'Game is not exclusively in the requested remote session' }
$existing=@(Get-Process BetterGI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $SessionId)
if ($RestartPid -gt 0) {
    if ($existing.Count -ne 1 -or $existing[0].Id -ne $RestartPid -or $existing[0].Path -ne $exe) {throw 'Refusing to restart an unexpected process'}
    Stop-Process -InputObject $existing[0]
    $existing[0].WaitForExit(5000) | Out-Null
    $existing=@(Get-Process BetterGI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $SessionId)
}
if ($existing.Count) { throw 'Close the child BetterGI instance before launching the pilot' }
$scheduler=New-Object -ComObject Schedule.Service
$scheduler.Connect()
$folder=$scheduler.GetFolder('\')
$task=$scheduler.NewTask(0)
$account=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$task.Principal.UserId=$account
$task.Principal.LogonType=3
$task.Principal.RunLevel=1
$task.Settings.Hidden=$true
$task.Settings.ExecutionTimeLimit='PT0S'
$task.Settings.DisallowStartIfOnBatteries=$false
$task.Settings.StopIfGoingOnBatteries=$false
$action=$task.Actions.Create(0)
$action.Path=$exe
$action.Arguments="--instance childsession --startGroups $Group"
$action.WorkingDirectory=$root
$name='BetterGI-QuestPilot-'+[Guid]::NewGuid().ToString('N')
$registered=$null
try {
    $registered=$folder.RegisterTaskDefinition($name,$task,2,$account,$null,3,$null)
    $running=$registered.RunEx($null,4,$SessionId,$null)
    if ($null -eq $running) { throw 'No running task returned' }
    Write-Output "Launched $Group in session $SessionId"
} finally {
    if($null -ne $registered) { $folder.DeleteTask($name,0) }
}

