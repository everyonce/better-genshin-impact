# Registration plans are data only. Importing this module never creates tasks or launches programs.
Set-StrictMode -Version Latest

function Get-ApprovedLauncherPlan {
    param([Parameter(Mandatory)][string] $RepositoryRoot, [Parameter(Mandatory)][string] $UserSid,
          [string] $ProgramFilesDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles),
          [string] $WindowsDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Windows))
    if ($RepositoryRoot -notmatch '^[A-Za-z]:[\\/]' -or $RepositoryRoot.StartsWith('\\')) { throw 'A local absolute repository path is required.' }
    $sid = [Security.Principal.SecurityIdentifier]::new($UserSid)
    if ($sid.IsWellKnown([Security.Principal.WellKnownSidType]::LocalSystemSid)) { throw 'An interactive user account is required.' }
    $repository = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\', '/')
    $installation = Join-Path $ProgramFilesDirectory 'BetterGI Automation'
    $scriptPath = Join-Path $installation 'Invoke-ApprovedHost.ps1'
    return [pscustomobject]@{
        version = 1; repositoryRoot = $repository; artifactsDirectory = Join-Path $repository 'artifacts'
        userSid = $UserSid; installationDirectory = $installation
        taskFolder = '\BetterGI Automation'; taskName = 'StartHost'; taskPath = '\BetterGI Automation\StartHost'
        executable = Join-Path $WindowsDirectory 'System32\WindowsPowerShell\v1.0\powershell.exe'
        arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $scriptPath + '"'
        workingDirectory = $installation; logonType = 3; runLevel = 1
        securityDescriptor = "O:BAG:SYD:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGX;;;$UserSid)"
        installedFiles = @('HostLauncher.psm1', 'Invoke-ApprovedHost.ps1')
    }
}

function Test-ApprovedTaskDefinition {
    param([Parameter(Mandatory)] $Definition, [Parameter(Mandatory)] $Plan)
    # Task.Run receives no parameters; there are no substitutable action arguments.
    try {
        # Task Scheduler may return a local account name after registration with a SID.
        # Resolve that display form back to the exact approved identity; unknown accounts fail closed.
        $principal = [string]$Definition.Principal.UserId
        $principalSid = if ($principal -match '^S-\d-') {
            [Security.Principal.SecurityIdentifier]::new($principal)
        }
        else {
            [Security.Principal.NTAccount]::new($principal).Translate([Security.Principal.SecurityIdentifier])
        }
        $expectedSid = [Security.Principal.SecurityIdentifier]::new([string]$Plan.userSid)
        return ($Definition.Actions.Count -eq 1 -and $Definition.Actions.Item(1).Type -eq 0 -and
            $Definition.Actions.Item(1).Path -ieq $Plan.executable -and
            $Definition.Actions.Item(1).Arguments -ceq $Plan.arguments -and
            $Definition.Actions.Item(1).WorkingDirectory -ieq $Plan.workingDirectory -and
            $principalSid.Equals($expectedSid) -and
            $Definition.Principal.LogonType -eq 3 -and $Definition.Principal.RunLevel -eq 1 -and
            $Definition.Triggers.Count -eq 0)
    }
    catch { return $false }
}

function Set-ApprovedTaskDefinition {
    param([Parameter(Mandatory)] $Definition, [Parameter(Mandatory)] $Plan)
    # One fixed action and one account. No password, argument forwarding, trigger or shell payload.
    $Definition.RegistrationInfo.Description = 'Start a verified local BetterGI build; RDP game startup remains guarded by BetterGI.'
    $Definition.Principal.UserId = $Plan.userSid
    $Definition.Principal.LogonType = 3
    $Definition.Principal.RunLevel = 1
    $Definition.Settings.Enabled = $true
    $Definition.Settings.Hidden = $true
    $Definition.Settings.AllowDemandStart = $true
    $Definition.Settings.DisallowStartIfOnBatteries = $false
    $Definition.Settings.StopIfGoingOnBatteries = $false
    $Definition.Settings.MultipleInstances = 2
    # Do not kill the long-lived BetterGI descendant after a task time limit.
    $Definition.Settings.ExecutionTimeLimit = 'PT0S'
    $action = $Definition.Actions.Create(0)
    $action.Path = $Plan.executable
    $action.Arguments = $Plan.arguments
    $action.WorkingDirectory = $Plan.workingDirectory
}

function Get-ApprovedGameArguments {
    param([Parameter(Mandatory)] $Root, [Parameter(Mandatory)] $Child)
    # A shortcut can select only the registered primary's actual, distinct RDP child.
    if ($Root.instanceType -ne 'Primary' -or $Root.automationEnabled -ne $true -or
        $Child.instanceType -ne 'ChildSession' -or $Child.automationEnabled -ne $true -or
        $Child.remoteDesktop -isnot [bool] -or $Child.remoteDesktop -ne $true -or
        $Child.rootProcessId -ne $Root.processId -or $Child.processId -le 0 -or
        $Child.windowsSessionId -le 0 -or $Child.windowsSessionId -eq $Root.windowsSessionId -or
        $Child.windowsSessionId -ne $Root.childSessionId -or $Root.childConnectedState -ne 1) {
        throw 'Game launch requires a connected, actual RDP child belonging to the verified primary.'
    }
    return @('start-game', '--process-id', [string]$Child.processId, '--windows-session-id', [string]$Child.windowsSessionId)
}

function Invoke-ApprovedHostTask {
    param([Parameter(Mandatory)] $Task, [Parameter(Mandatory)][int] $WindowsSessionId)
    if ($WindowsSessionId -le 0) { throw 'An exact interactive console session is required.' }
    # TASK_RUN_USE_SESSION_ID is essential when this account also owns an RDP logon.
    $null = $Task.RunEx($null, 4, $WindowsSessionId, $null)
}

function Select-ApprovedWarmHost {
    param([object[]] $Instances = @(), [Parameter(Mandatory)][int] $WindowsSessionId,
          [Parameter(Mandatory)][string] $ArtifactsDirectory)
    $roots = @($Instances | Where-Object { $_.instanceType -eq 'Primary' })
    if ($roots.Count -eq 0) { return $null }
    if ($roots.Count -ne 1) { throw 'Multiple primary hosts require explicit identity selection.' }
    $package = Get-VerifiedHostPackage $roots[0].appDirectory
    $actualArtifacts = [IO.Path]::GetFullPath((Split-Path -Parent (Split-Path -Parent $package.targetDirectory))).TrimEnd('\', '/')
    $expectedArtifacts = [IO.Path]::GetFullPath($ArtifactsDirectory).TrimEnd('\', '/')
    if ($actualArtifacts -ine $expectedArtifacts -or -not (Test-HostIdentity $roots[0] $package $WindowsSessionId)) {
        throw 'The existing primary is not a verified automated host in this workspace and console session.'
    }
    return $package
}

function Get-WarmHostWindowArguments {
    param([Parameter(Mandatory)] $Status, [switch] $PreserveWindow)
    # Only an existing connected/connecting window needs an extra warm minimize.
    # A new connection retains BetterGI's existing minimized startup behavior.
    if ($PreserveWindow -or $Status.childWindowMinimized -eq $true -or $Status.childConnectedState -notin @(1, 2)) { return }
    if ($Status.PSObject.Properties['uiStatus'] -and $Status.uiStatus -ne 'current') {
        throw 'Current root UI status is unavailable; its window state cannot be verified.'
    }
    return @('minimize', '--process-id', [string]$Status.processId, '--windows-session-id', [string]$Status.windowsSessionId)
}

function Get-ApprovedChildArguments {
    param([Parameter(Mandatory)] $Root, [Parameter(Mandatory)] $Package,
          [ValidateSet('Host', 'Game')][string] $Mode, [switch] $PreserveWindow)
    # Pin the latest child separately from the older host we deliberately retain.
    if ($Root.instanceType -ne 'Primary' -or $Root.automationEnabled -isnot [bool] -or
        $Root.automationEnabled -ne $true -or $Root.remoteDesktop -isnot [bool] -or $Root.remoteDesktop -ne $false -or
        $Root.processId -le 0 -or $Root.windowsSessionId -le 0 -or
        $Root.instanceNonce -isnot [string] -or -not $Root.instanceNonce -or
        $Package.exeSha256 -notmatch '^[a-fA-F0-9]{64}$' -or $Package.dllSha256 -notmatch '^[a-fA-F0-9]{64}$') {
        throw 'Selected-child startup requires the verified primary epoch and both selected binary hashes.'
    }
    $arguments = @('ensure-child', '--process-id', [string]$Root.processId,
        '--windows-session-id', [string]$Root.windowsSessionId, '--instance-nonce', $Root.instanceNonce,
        '--target-directory', $Package.targetDirectory, '--exe-sha256', $Package.exeSha256,
        '--dll-sha256', $Package.dllSha256)
    if ($PreserveWindow) { $arguments += '--preserve-window' }
    if ($Mode -eq 'Game') { $arguments += '--start-game' }
    return $arguments
}

Export-ModuleMember -Function Get-ApprovedLauncherPlan, Test-ApprovedTaskDefinition, Set-ApprovedTaskDefinition, Get-ApprovedGameArguments, Invoke-ApprovedHostTask, Select-ApprovedWarmHost, Get-WarmHostWindowArguments, Get-ApprovedChildArguments
