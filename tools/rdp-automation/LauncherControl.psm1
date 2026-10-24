# Ordinary-token CLI transport. No shell is involved, and native stderr never
# becomes a terminating WinPS 5 NativeCommandError under ErrorActionPreference=Stop.
Set-StrictMode -Version Latest

function ConvertTo-LauncherArgument {
    param([AllowEmptyString()][string] $Value)
    if ($Value.Contains([char]0)) { throw 'A launcher argument cannot contain NUL.' }
    # Windows CRT parsing: double backslashes before a quote or the closing quote.
    $text = [Text.StringBuilder]::new('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') {
            [void]$text.Append(('\' * (2 * $slashes + 1))).Append('"')
        }
        else { [void]$text.Append(('\' * $slashes)).Append($character) }
        $slashes = 0
    }
    [void]$text.Append(('\' * (2 * $slashes))).Append('"')
    return $text.ToString()
}

function Invoke-LauncherProcess {
    param([Parameter(Mandatory)][string] $Executable, [string[]] $Arguments,
          [Parameter(Mandatory)][string] $Phase, [ValidateRange(1, 300)][int] $TimeoutSeconds = 150)
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.Arguments = (@($Arguments | ForEach-Object { ConvertTo-LauncherArgument $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
    $start.StandardErrorEncoding = [Text.UTF8Encoding]::new($false)
    $start.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $evidence = [ordered]@{phase=$Phase; exitCode=$null; timedOut=$false; outputComplete=$false;
        stdout=''; stderr=''; outputTruncated=$false; elapsedMs=0; processError=$null}
    try {
        if (-not $process.Start()) { throw 'The control process did not start.' }
        # Drain both streams concurrently so a full stderr pipe cannot block stdout.
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $evidence.timedOut = $true
            # Only this owned CLI process is stopped. Server-side outcomes remain
            # unknown and no control request is replayed.
            $process.Kill()
            $null = $process.WaitForExit(2000)
        }
        if ($process.HasExited) { $evidence.exitCode = $process.ExitCode }
        $complete = [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdout, $stderr), 2000)
        $evidence.outputComplete = $complete
        if ($stdout.Status -eq [Threading.Tasks.TaskStatus]::RanToCompletion) { $evidence.stdout = $stdout.Result }
        if ($stderr.Status -eq [Threading.Tasks.TaskStatus]::RanToCompletion) { $evidence.stderr = $stderr.Result }
        foreach ($stream in @('stdout', 'stderr')) {
            if ($evidence[$stream].Length -gt 262144) {
                $evidence[$stream] = $evidence[$stream].Substring(0, 262144)
                $evidence.outputTruncated = $true
            }
        }
    }
    catch { $evidence.processError = $_.Exception.GetBaseException().Message }
    finally { $evidence.elapsedMs = $clock.Elapsed.TotalMilliseconds; $process.Dispose() }
    return [pscustomobject]$evidence
}

function Invoke-LauncherJson {
    param([Parameter(Mandatory)][string] $Executable, [string[]] $Arguments,
          [Parameter(Mandatory)][string] $Phase, [ValidateRange(1, 300)][int] $TimeoutSeconds = 150)
    $evidence = Invoke-LauncherProcess -Executable $Executable -Arguments $Arguments -Phase $Phase -TimeoutSeconds $TimeoutSeconds
    $parsedError = $null
    try { if ($evidence.stderr.Trim()) { $parsedError = ConvertFrom-Json -InputObject $evidence.stderr -ErrorAction Stop } } catch { }
    $result = $null
    $jsonError = $null
    try { $result = ConvertFrom-Json -InputObject $evidence.stdout -ErrorAction Stop }
    catch { $jsonError = $_.Exception.Message }
    if ($evidence.exitCode -ne 0 -or $evidence.timedOut -or -not $evidence.outputComplete -or
        $evidence.outputTruncated -or $evidence.processError -or $jsonError -or $null -eq $result) {
        $detail = if ($null -ne $parsedError -and $parsedError.PSObject.Properties['error']) { [string]$parsedError.error }
                  elseif ($evidence.stderr.Trim()) { $evidence.stderr.Trim() }
                  elseif ($evidence.processError) { $evidence.processError }
                  elseif ($jsonError) { $jsonError } else { 'No complete JSON response was retained.' }
        if (-not $detail) { $detail = 'The control process failed without an error message.' }
        $failure = [ordered]@{phase=$Phase; process=$evidence; controlError=$parsedError}
        $exception = [InvalidOperationException]::new("Control phase '$Phase' failed (exit $($evidence.exitCode), timeout $($evidence.timedOut)): $detail No request was replayed.")
        $exception.Data['ControlFailure'] = $failure
        throw $exception
    }
    return [pscustomobject]@{value=$result; process=$evidence}
}

function Get-LauncherFailure {
    param([Parameter(Mandatory)] $ErrorRecord)
    $exception = $ErrorRecord.Exception
    while ($null -ne $exception) {
        if ($exception.Data.Contains('ControlFailure')) { return $exception.Data['ControlFailure'] }
        $exception = $exception.InnerException
    }
    return $null
}

Export-ModuleMember -Function ConvertTo-LauncherArgument, Invoke-LauncherProcess, Invoke-LauncherJson, Get-LauncherFailure
