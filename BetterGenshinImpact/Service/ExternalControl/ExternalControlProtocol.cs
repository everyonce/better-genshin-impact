using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace BetterGenshinImpact.Service.ExternalControl;

internal static class ExternalControlProtocol
{
    internal const int Version = 1;
    internal const int MaximumFrameBytes = 8 * 1024;
    internal static readonly TimeSpan MaximumRequestAge = TimeSpan.FromSeconds(30);

    internal static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 8
    };

    internal static bool TryDeserializeRequest(ReadOnlySpan<byte> payload, out ExternalControlRequest? request)
    {
        request = null;
        try
        {
            request = JsonSerializer.Deserialize<ExternalControlRequest>(payload, JsonOptions);
            return request is not null;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    internal static byte[] SerializeResponse(ExternalControlResponse response) =>
        JsonSerializer.SerializeToUtf8Bytes(response, JsonOptions);

    internal static string Fingerprint(ExternalControlRequest request)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(request, JsonOptions);
        return Convert.ToHexString(SHA256.HashData(bytes));
    }

    internal static DateTimeOffset GetReplayExpiry(long createdAtUnixMs) =>
        DateTimeOffset.FromUnixTimeMilliseconds(createdAtUnixMs)
        + MaximumRequestAge
        + TimeSpan.FromMilliseconds(1);

    internal static string? ValidateRequest(ExternalControlRequest request, DateTimeOffset now)
    {
        if (request.Version != Version)
        {
            return "unsupported_version";
        }
        if (request.RequestId == Guid.Empty)
        {
            return "invalid_request_id";
        }
        if (request.CreatedAtUnixMs <= 0)
        {
            return "invalid_timestamp";
        }

        DateTimeOffset createdAt;
        try
        {
            createdAt = DateTimeOffset.FromUnixTimeMilliseconds(request.CreatedAtUnixMs);
        }
        catch (ArgumentOutOfRangeException)
        {
            return "invalid_timestamp";
        }
        if (now - createdAt > MaximumRequestAge || createdAt - now > MaximumRequestAge)
        {
            return "stale_request";
        }

        var hasCommandParameters = request.ExecutablePath is not null || request.Arguments is not null
                                   || request.WorkingDirectory is not null || request.ChildSessionId is not null;
        if (request.Command != "launchChildCommand" && hasCommandParameters)
            return "unexpected_command_parameters";
        if (request.Command == "launchChildCommand"
            && (request.ChildSessionId is not > 0 || string.IsNullOrWhiteSpace(request.ExecutablePath)
                || !Path.IsPathFullyQualified(request.ExecutablePath) || request.ExecutablePath.StartsWith(@"\\")
                || request.ExecutablePath.Contains('\0')
                || string.IsNullOrWhiteSpace(request.WorkingDirectory) || !Path.IsPathFullyQualified(request.WorkingDirectory)
                || request.WorkingDirectory.StartsWith(@"\\") || request.WorkingDirectory.Contains('\0')
                || request.Arguments is null || request.Arguments.Length > 64
                || request.Arguments.Any(value => value is null || value.Length > 2048 || value.Contains('\0'))))
            return "invalid_command_parameters";

        if (request.Command is "status")
        {
            return request.TargetProcessId is null
                   && request.TargetWindowsSessionId is null
                   && request.TargetNonce is null
                ? null
                : "unexpected_target";
        }

        if (request.Command is not ("startPilot" or "stopPilot" or "restartApp" or "installRecoveryLauncher" or "restartHost" or "shutdownApp")
            && !IsAutomationCommand(request.Command))
        {
            return "unsupported_command";
        }
        if (request.TargetProcessId is not > 0
            || request.TargetWindowsSessionId is not >= 0
            || string.IsNullOrWhiteSpace(request.TargetNonce)
            || request.TargetNonce.Length > 128)
        {
            return "target_required";
        }
        return null;
    }

    /// <summary>Explicit lifecycle allowlist; arbitrary command parameters belong only to the standard-token launcher.</summary>
    internal static bool IsAutomationCommand(string? command) => command is "startChildSession"
        or "cancelChildStart" or "minimizeChildSession" or "showChildSession" or "launchChildCommand"
        or "startChildGame" or "stopAutomationTasks";

    internal static string CreatePipeName(int windowsSessionId, int processId, string userSid)
    {
        var sidHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(userSid)))[..16];
        return $"BetterGI.ExternalControl.{sidHash}.{windowsSessionId}.{processId}";
    }
}

internal sealed record ExternalControlRequest
{
    [JsonPropertyName("version")]
    public int Version { get; init; }

    [JsonPropertyName("requestId")]
    public Guid RequestId { get; init; }

    [JsonPropertyName("createdAtUnixMs")]
    public long CreatedAtUnixMs { get; init; }

    [JsonPropertyName("command")]
    public string? Command { get; init; }

    [JsonPropertyName("targetProcessId")]
    public int? TargetProcessId { get; init; }

    [JsonPropertyName("targetWindowsSessionId")]
    public int? TargetWindowsSessionId { get; init; }

    [JsonPropertyName("targetNonce")]
    public string? TargetNonce { get; init; }

    /// <summary>Local executable launched with the standard user token, never an elevated shell.</summary>
    [JsonPropertyName("executablePath")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ExecutablePath { get; init; }

    /// <summary>Separate argv items; the service never interprets shell syntax.</summary>
    [JsonPropertyName("arguments")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string[]? Arguments { get; init; }

    /// <summary>Existing local working directory for a standard-token command.</summary>
    [JsonPropertyName("workingDirectory")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? WorkingDirectory { get; init; }

    /// <summary>Exact connected child Windows session expected by the command caller.</summary>
    [JsonPropertyName("childSessionId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ChildSessionId { get; init; }
}

internal sealed record ExternalControlResponse
{
    [JsonPropertyName("version")]
    public int Version { get; init; } = ExternalControlProtocol.Version;

    [JsonPropertyName("requestId")]
    public Guid RequestId { get; init; }

    [JsonPropertyName("success")]
    public bool Success { get; init; }

    [JsonPropertyName("errorCode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ErrorCode { get; init; }

    [JsonPropertyName("message")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Message { get; init; }

    [JsonPropertyName("status")]
    public ExternalControlStatus? Status { get; init; }

    [JsonIgnore]
    internal bool ShutdownAfterWrite { get; init; }

    internal static ExternalControlResponse Failure(Guid requestId, string code, string message) => new()
    {
        RequestId = requestId,
        Success = false,
        ErrorCode = code,
        Message = message
    };
}

internal sealed record ExternalControlStatus
{
    /// <summary>Explicit machine-mode opt-in for this process.</summary>
    [JsonPropertyName("automationEnabled")]
    public bool AutomationEnabled { get; init; }
    /// <summary>Product version, for human diagnostics.</summary>
    [JsonPropertyName("appVersion")]
    public string AppVersion { get; init; } = string.Empty;
    /// <summary>Loaded assembly's on-disk SHA256, used to confirm a staged replacement.</summary>
    [JsonPropertyName("assemblySha256")]
    public string AssemblySha256 { get; init; } = string.Empty;
    /// <summary>Actual Windows child session owned by this host, if known.</summary>
    [JsonPropertyName("childSessionId")]
    public uint? ChildSessionId { get; init; }
    /// <summary>ActiveX state: 0 disconnected, 1 connected, 2 connecting.</summary>
    [JsonPropertyName("childConnectedState")]
    public int ChildConnectedState { get; init; }
    /// <summary>Whether the outer RDP host is minimized.</summary>
    [JsonPropertyName("childWindowMinimized")]
    public bool ChildWindowMinimized { get; init; }
    /// <summary>Current startup, game attachment, or stop workflow state.</summary>
    [JsonPropertyName("automationState")]
    public string AutomationState { get; init; } = "idle";
    /// <summary>Structured workflow error; no credential material is returned.</summary>
    [JsonPropertyName("automationError")]
    public string? AutomationError { get; init; }
    /// <summary>Any active task or lifecycle operation that prevents replacement.</summary>
    [JsonPropertyName("taskRunning")]
    public bool TaskRunning { get; init; }
    /// <summary>The child has successfully bound a game window and started capture.</summary>
    [JsonPropertyName("runtimeRunning")]
    public bool RuntimeRunning { get; init; }

    [JsonPropertyName("appDirectory")]
    public string AppDirectory { get; init; } = string.Empty;

    [JsonPropertyName("captureStorageVersion")]
    public int CaptureStorageVersion { get; init; }

    [JsonPropertyName("processId")]
    public int ProcessId { get; init; }

    [JsonPropertyName("windowsSessionId")]
    public int WindowsSessionId { get; init; }

    [JsonPropertyName("instanceType")]
    public string InstanceType { get; init; } = string.Empty;

    [JsonPropertyName("remoteDesktop")]
    public bool RemoteDesktop { get; init; }

    [JsonPropertyName("pipeName")]
    public string PipeName { get; init; } = string.Empty;

    [JsonPropertyName("instanceNonce")]
    public string InstanceNonce { get; init; } = string.Empty;

    [JsonPropertyName("pilotState")]
    public string PilotState { get; init; } = string.Empty;

    [JsonPropertyName("serviceOwnsPilot")]
    public bool ServiceOwnsPilot { get; init; }

    [JsonPropertyName("heartbeatFresh")]
    public bool HeartbeatFresh { get; init; }

    [JsonPropertyName("scriptSession")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ScriptSession { get; init; }

    [JsonPropertyName("heartbeatAtUnixMs")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? HeartbeatAtUnixMs { get; init; }

    [JsonPropertyName("frameId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? FrameId { get; init; }

    [JsonPropertyName("activeRequestId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ActiveRequestId { get; init; }

    [JsonPropertyName("scriptState")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ScriptState { get; init; }

    [JsonPropertyName("scriptError")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ScriptError { get; init; }

    [JsonPropertyName("rootProcessId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? RootProcessId { get; init; }

    [JsonPropertyName("recoveryLauncherInstalled")]
    public bool RecoveryLauncherInstalled { get; init; }

    [JsonPropertyName("hostRecoveryState")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? HostRecoveryState { get; init; }
}

internal sealed record PilotHeartbeat
{
    [JsonPropertyName("version")]
    public int Version { get; init; }

    [JsonPropertyName("processId")]
    public int ProcessId { get; init; }

    [JsonPropertyName("windowsSessionId")]
    public int WindowsSessionId { get; init; }

    [JsonPropertyName("session")]
    public string? Session { get; init; }

    [JsonPropertyName("state")]
    public string? State { get; init; }

    [JsonPropertyName("heartbeatAt")]
    public long HeartbeatAt { get; init; }

    [JsonPropertyName("frameId")]
    public long FrameId { get; init; }

    [JsonPropertyName("activeRequestId")]
    public string? ActiveRequestId { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
