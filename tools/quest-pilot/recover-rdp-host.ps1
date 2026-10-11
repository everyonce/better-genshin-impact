param()

$ErrorActionPreference = 'Stop'

function Assert-RecoveryCallerSession {
    param([int]$SessionId)
    if ($SessionId -ne 1) { throw 'Run this recovery helper from Windows session 1.' }
}

function Convert-AccountNameToSid {
    param([Parameter(Mandatory = $true)][string]$AccountName)

    try {
        $sid = New-Object -TypeName Security.Principal.SecurityIdentifier -ArgumentList $AccountName
        return $sid.Value
    }
    catch [ArgumentException] {
        try {
            $account = New-Object -TypeName Security.Principal.NTAccount -ArgumentList $AccountName
            return $account.Translate([Security.Principal.SecurityIdentifier]).Value
        }
        catch { throw 'Recovery task principal cannot be resolved to a Windows SID.' }
    }
}

function Get-ExpectedAppRoot {
    param([Parameter(Mandatory = $true)][string]$ExecutablePath)

    $appRoot = [IO.Path]::GetFullPath((Split-Path -Parent $ExecutablePath))
    $artifactsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../artifacts'))
    $releaseRoot = Split-Path -Parent $appRoot
    if ((Split-Path -Leaf $appRoot) -ne 'BetterGI-English-win-x64' -or
        (Split-Path -Leaf $releaseRoot) -notmatch '^release-r[0-9]+$' -or
        [IO.Path]::GetFullPath((Split-Path -Parent $releaseRoot)) -ne $artifactsRoot) {
        throw 'Recovery task points outside a staged release in this BetterGI workspace.'
    }

    $workspaceRoot = Split-Path -Parent $artifactsRoot
    $current = $appRoot
    while ($true) {
        if (-not (Test-Path -LiteralPath $current -PathType Container)) {
            throw 'Recovery task path contains a missing directory.'
        }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Recovery task path contains a linked directory.'
        }
        if ([string]::Equals([IO.Path]::GetFullPath($current), $workspaceRoot, [StringComparison]::OrdinalIgnoreCase)) { break }
        $parent = Split-Path -Parent $current
        if (-not $parent -or $parent -eq $current) { throw 'Recovery task path escapes the workspace.' }
        $current = $parent
    }
    return $appRoot
}

function Assert-RecoveryTaskContract {
    param(
        [Parameter(Mandatory = $true)]$Task,
        [Parameter(Mandatory = $true)][string]$CurrentUserSid
    )

    if (-not $Task.Enabled) { throw 'Recovery task is disabled.' }
    $definition = $Task.Definition
    $principal = $definition.Principal
    $taskSid = Convert-AccountNameToSid -AccountName ([string]$principal.UserId)
    if (-not [string]::Equals($taskSid, $CurrentUserSid, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Recovery task principal is not the current user.'
    }
    if ([int]$principal.LogonType -ne 3) { throw 'Recovery task must use an interactive token.' }
    if ([int]$principal.RunLevel -ne 1) { throw 'Recovery task must run at the highest available level.' }
    if ([string]$definition.Settings.ExecutionTimeLimit -ne 'PT0S') {
        throw 'Recovery task must have no execution time limit.'
    }
    if ([int]$definition.Settings.MultipleInstances -ne 0) {
        throw 'Recovery task must allow parallel activation while the desktop-clone host is running.'
    }
    if ([int]$definition.Triggers.Count -ne 0) { throw 'Recovery task must be on-demand with no triggers.' }
    if ([int]$definition.Actions.Count -ne 1) { throw 'Recovery task must contain exactly one action.' }

    $action = $definition.Actions.Item(1)
    if ([int]$action.Type -ne 0) { throw 'Recovery task action must be an executable action.' }
    $exe = [IO.Path]::GetFullPath([string]$action.Path)
    $appRoot = Get-ExpectedAppRoot -ExecutablePath $exe
    $expectedExe = [IO.Path]::GetFullPath((Join-Path $appRoot 'BetterGI.exe'))
    $workingDirectory = [IO.Path]::GetFullPath([string]$action.WorkingDirectory)
    if (-not [string]::Equals($exe, $expectedExe, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Recovery task executable is not BetterGI.exe in its staged release directory.'
    }
    if (-not [string]::Equals($workingDirectory, $appRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Recovery task working directory does not match its staged release directory.'
    }
    if ([string]$action.Arguments -cne '--desktopClone') {
        throw 'Recovery task arguments do not match the fixed --desktopClone action.'
    }

    return $appRoot
}

function Assert-StagedRecoveryBuild {
    param([Parameter(Mandatory = $true)][string]$AppRoot)

    function Read-BoundedJson {
        param([string]$Path, [int]$MaxBytes)
        Assert-NoLinkedPath -Root $AppRoot -Path $Path
        $file = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if ($file.PSIsContainer -or $file.Length -le 0 -or $file.Length -gt $MaxBytes) {
            throw "Recovery JSON file is missing, empty, or exceeds its size limit: $(Split-Path -Leaf $Path)"
        }
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
    }

    $manifestPath = Join-Path $AppRoot 'Host-Launcher.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Staged Host-Launcher.json is missing.' }
    $manifest = Read-BoundedJson -Path $manifestPath -MaxBytes 4096
    if ($manifest.version -ne 1 -or $manifest.desktopClone -ne $true) {
        throw 'Staged build does not declare support for direct desktop-clone startup.'
    }
    $manifestProperties = @($manifest.PSObject.Properties | ForEach-Object { $_.Name })
    if ($manifestProperties.Count -ne 3 -or
        -not ($manifestProperties -ccontains 'version') -or
        -not ($manifestProperties -ccontains 'desktopClone') -or
        -not ($manifestProperties -ccontains 'sha256')) {
        throw 'Host-Launcher.json must contain only version, desktopClone, and sha256.'
    }
    $hashProperties = @($manifest.sha256.PSObject.Properties | ForEach-Object { $_.Name })
    if ($hashProperties.Count -ne 2 -or
        -not ($hashProperties -ccontains 'BetterGI.exe') -or
        -not ($hashProperties -ccontains 'BetterGI.dll')) {
        throw 'Host-Launcher.json sha256 must contain exactly BetterGI.exe and BetterGI.dll.'
    }
    foreach ($name in @('BetterGI.exe', 'BetterGI.dll')) {
        $path = Join-Path $AppRoot $name
        Assert-NoLinkedPath -Root $AppRoot -Path $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Staged file is missing: $name" }
        if ([string]$manifest.sha256.$name -notmatch '^[A-Fa-f0-9]{64}$') {
            throw "Staged file hash is not a SHA256 value: $name"
        }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if (-not [string]::Equals($actual, [string]$manifest.sha256.$name, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Staged file hash mismatch: $name"
        }
    }

    $optInPath = Join-Path $AppRoot 'User/ExternalControl/enable-quest-control.json'
    if (-not (Test-Path -LiteralPath $optInPath -PathType Leaf)) { throw 'Staged external-control opt-in marker is missing.' }
    $optIn = Read-BoundedJson -Path $optInPath -MaxBytes 4096
    if ($optIn.version -ne 1 -or $optIn.enabled -ne $true -or $optIn.allowAppRestart -ne $true) {
        throw 'Staged external-control marker must enable quest control and app restart.'
    }

    $groupPath = Join-Path $AppRoot 'User/ScriptGroup/ActOneRun.json'
    if (-not (Test-Path -LiteralPath $groupPath -PathType Leaf)) { throw 'Staged ActOneRun group is missing.' }
    $group = Read-BoundedJson -Path $groupPath -MaxBytes 65536
    $enabledProjects = @($group.projects | Where-Object { $_.status -eq 'Enabled' })
    if ($group.name -ne 'ActOneRun' -or $enabledProjects.Count -ne 1 -or
        $enabledProjects[0].type -ne 'Javascript' -or $enabledProjects[0].folderName -ne 'ActOnePilot') {
        throw 'Staged ActOneRun group must contain only the enabled ActOnePilot JavaScript project.'
    }
    foreach ($name in @('main.js', 'bgi.js', 'engine.js')) {
        $scriptPath = Join-Path $AppRoot "User/JsScript/ActOnePilot/$name"
        Assert-NoLinkedPath -Root $AppRoot -Path $scriptPath
        if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
            throw "Staged ActOnePilot package is incomplete: $name"
        }
    }
}

function Assert-NoLinkedPath {
    param([string]$Root, [string]$Path)
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $current = [IO.Path]::GetFullPath($Path)
    if (-not $current.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Recovery file path escapes its staged application directory.'
    }
    while ($current.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Recovery configuration contains a linked file or directory.'
            }
        }
        $parent = Split-Path -Parent $current
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
}

function Invoke-RdpHostRecovery {
    Assert-RecoveryCallerSession -SessionId ([Diagnostics.Process]::GetCurrentProcess().SessionId)
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $service = $null
    $folder = $null
    $task = $null
    $runningTask = $null
    try {
        $service = New-Object -ComObject 'Schedule.Service'
        $service.Connect()
        $folder = $service.GetFolder('\')
        try { $task = $folder.GetTask('BetterGI-Quest-RDP-Host') }
        catch { throw 'Recovery task BetterGI-Quest-RDP-Host is not registered.' }

        $appRoot = Assert-RecoveryTaskContract -Task $task -CurrentUserSid $sid
        Assert-StagedRecoveryBuild -AppRoot $appRoot

        $sessionOneInstances = @(Get-Process -Name BetterGI -ErrorAction SilentlyContinue |
            Where-Object { $_.SessionId -eq 1 })

        # TASK_RUN_USE_SESSION_ID (4) targets session 1; null user selects its logged-on user.
        $runningTask = $task.RunEx($null, 4, 1, $null)
        if ($sessionOneInstances.Count -gt 0) {
            Write-Output "Activation dispatched through the validated recovery task; this does not confirm RDP connection or child readiness."
        }
        else {
            Write-Output "Launch dispatched through the validated recovery task for $appRoot; this does not confirm RDP connection or child readiness."
        }
    }
    finally {
        if ($runningTask -and [Runtime.InteropServices.Marshal]::IsComObject($runningTask)) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($runningTask)
        }
        if ($task -and [Runtime.InteropServices.Marshal]::IsComObject($task)) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($task)
        }
        if ($folder -and [Runtime.InteropServices.Marshal]::IsComObject($folder)) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($folder)
        }
        if ($service -and [Runtime.InteropServices.Marshal]::IsComObject($service)) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($service)
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-RdpHostRecovery }
