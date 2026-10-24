using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using BetterGenshinImpact.Core.Agent;
using Fischless.GameCapture;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.ChildSession;

namespace BetterGenshinImpact.Service.ExternalControl;

internal static class ExternalControlProtocol
{
    internal const int Version = 1;
    internal const int MaximumFrameBytes = 8 * 1024;
    /// <summary>Only the explicit read-only evidence reply may exceed the legacy frame limit; requests remain 8 KiB.</summary>
    internal const int MaximumDiagnosticsResponseBytes = 32 * 1024;
    internal static readonly TimeSpan MaximumRequestAge = TimeSpan.FromSeconds(30);

    internal static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 8,
        Converters = { new CaptureModeJsonConverter() }
    };

    /// <summary>Bounded waypoint evidence adds two response containers; request parsing and fingerprints keep depth eight.</summary>
    private static readonly JsonSerializerOptions _responseJsonOptions = new(JsonOptions) { MaxDepth = 10 };

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
        JsonSerializer.SerializeToUtf8Bytes(response, _responseJsonOptions);

    /// <summary>Preserve ordinary status compatibility with older hosts while returning all bounded reset observations.</summary>
    internal static int MaximumResponseBytes(string? command) => command is "navigationResetDiagnostics" or "navigationBaselineResult"
        ? MaximumDiagnosticsResponseBytes : MaximumFrameBytes;

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
        if (request.Command != "startChildSession" && request.HasChildStartupMode)
            return "unexpected_command_parameters";
        if (request.HasChildStartupMode && !ChildSessionStartupOperation.IsSupported(request.ChildStartupMode))
            return "invalid_command_parameters";
        if (request.Command != "restartApp" && request.HasIdleRestart)
            return "unexpected_command_parameters";
        if (request.HasIdleRestart && (request.IdleRestart is null || !ExternalControlRestart.IsValidExpectation(request.IdleRestart)))
            return "invalid_command_parameters";
        if (request.HasShadowCapture && (request.Command != "startNavigationBaseline" || request.ShadowCapture != NavigationBaselineShadowMode.Rgb192))
            return "invalid_shadow_capture";
        if (request.HasShadowCapture && (request.TimingContract != NavigationBaselineTiming.V4
                || request.CapturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer))
            return "shadow_capture_requires_v4_task_owned_timer";
        if (request.HasRouteProfile && (request.Command != "startNavigationBaseline"
                || !NavigationBaselineRouteProfile.IsSupported(request.RouteProfile)))
            return "invalid_route_profile";
        if (request.RouteProfile is NavigationBaselineRouteProfile.TwoLegId or NavigationBaselineRouteProfile.ReverseId
            && (request.TimingContract != NavigationBaselineTiming.V4 || request.CapturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer))
            return "two_leg_requires_v4_task_owned_timer";
        if (request.HasContinuationFromRunId && (request.Command != "startNavigationBaseline"
                || request.RouteProfile != NavigationBaselineRouteProfile.ReverseId)) return "unexpected_command_parameters";
        if (request.RouteProfile == NavigationBaselineRouteProfile.ReverseId
            && (!Guid.TryParseExact(request.ContinuationFromRunId, "N", out var predecessor) || predecessor == Guid.Empty))
            return "invalid_continuation_predecessor";
        if (request.Command != "startNavigationBaseline" && request.HasTimingContract)
            return "unexpected_command_parameters";
        if (request.HasTimingContract && !NavigationBaselineTiming.IsSupported(request.TimingContract))
            return "invalid_command_parameters";
        if (request.Command is not ("startNavigationBaseline" or "startNavigationReset") && request.HasCapturePolicy)
            return "unexpected_command_parameters";
        if (request.HasCapturePolicy && !(request.Command == "startNavigationReset"
                ? NavigationResetCapturePolicy.IsSupported(request.CapturePolicy)
                : NavigationBaselineCapturePolicy.IsSupported(request.CapturePolicy)))
            return "invalid_command_parameters";
        if (request.Command != "navigationBaselineResult" && request.NavigationBaselineRunId is not null)
            return "unexpected_command_parameters";
        if (request.Command == "navigationBaselineResult"
            && (!Guid.TryParseExact(request.NavigationBaselineRunId, "N", out var baselineRunId) || baselineRunId == Guid.Empty))
            return "invalid_command_parameters";
        if (request.Command != "navigationResetDiagnostics" && request.NavigationResetRunId is not null)
            return "unexpected_command_parameters";
        if (request.Command == "navigationResetDiagnostics"
            && (!Guid.TryParseExact(request.NavigationResetRunId, "N", out var resetRunId) || resetRunId == Guid.Empty))
            return "invalid_command_parameters";
        if (request.Command != "startAgentStream" && request.EnableInput is not null)
            return "unexpected_command_parameters";
        if (request.Command != "startAgentStream" && request.HasObservationProfile)
            return "unexpected_command_parameters";
        if (request.Command == "startAgentStream" && !AgentObservationProfile.IsSupported(request.ObservationProfile))
            return "invalid_command_parameters";
        if (request.Command != "startNavigationReset" && request.TargetYawDegrees is not null)
            return "unexpected_command_parameters";
        if (request.Command == "startNavigationReset" && !NavigationResetTask.IsValidYaw(request.TargetYawDegrees ?? 0))
            return "invalid_command_parameters";
        if (request.Command != "setCaptureMode" && request.CaptureMode is not null)
            return "unexpected_command_parameters";
        if (request.Command == "setCaptureMode"
            && (request.CaptureMode is null || !Enum.IsDefined(request.CaptureMode.Value)))
            return "invalid_command_parameters";
        if (request.Command != "setCaptureMode" && request.HasReadbackMode)
            return "unexpected_command_parameters";
        if (request.Command == "setCaptureMode" && request.HasReadbackMode
            && (request.ReadbackMode is not ("blocking" or "poll_single_v1")
                || request.CaptureMode != CaptureModes.WindowsGraphicsCaptureV2))
            return "invalid_command_parameters";
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

        if (request.Command is not ("startPilot" or "stopPilot" or "restartApp" or "installRecoveryLauncher" or "restartHost" or "shutdownApp" or "navigationResetDiagnostics" or "navigationBaselineResult")
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
        or "startChildGame" or "stopAutomationTasks" or "startAgentStream" or "stopAgentStream" or "setCaptureMode"
        or "startNavigationReset" or "startNavigationBaseline";

    internal static string CreatePipeName(int windowsSessionId, int processId, string userSid)
    {
        var sidHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(userSid)))[..16];
        return $"BetterGI.ExternalControl.{sidHash}.{windowsSessionId}.{processId}";
    }
}

internal sealed record ExternalControlRequest
{
    /// <summary>Track explicit null so only omission retains the legacy child startup contract.</summary>
    private string? _childStartupMode;
    /// <summary>Optional strict intent for primary child startup; never changes an existing operation's intent.</summary>
    [JsonPropertyName("childStartupMode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChildStartupMode
    {
        get => _childStartupMode;
        init { _childStartupMode = value; HasChildStartupMode = true; }
    }
    /// <summary>Reject explicit null and parameters on unrelated commands before dispatch.</summary>
    [JsonIgnore]
    internal bool HasChildStartupMode { get; private set; }
    /// <summary>Backing value preserves explicit null versus omitted legacy route selection.</summary>
    /// <summary>Explicit optional archive selector, fingerprinted with the complete request.</summary>
    private string? _shadowCapture;
    [JsonPropertyName("shadowCapture")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ShadowCapture { get => _shadowCapture; init { _shadowCapture = value; HasShadowCapture = true; } }
    /// <summary>Distinguish legacy omission from invalid explicit null.</summary>
    [JsonIgnore] internal bool HasShadowCapture { get; private set; }

    private string? _routeProfile;
    /// <summary>Exact built-in route selector, valid only for starting this baseline.</summary>
    [JsonPropertyName("routeProfile")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RouteProfile { get => _routeProfile; init { _routeProfile = value; HasRouteProfile = true; } }
    /// <summary>Explicit null must not silently become the legacy profile.</summary>
    [JsonIgnore] internal bool HasRouteProfile { get; private set; }
    /// <summary>Exact local retained baseline identifier only; JSON cannot supply predecessor result or coordinates.</summary>
    private string? _continuationFromRunId;
    /// <summary>Bound by the existing request fingerprint and replay cache.</summary>
    [JsonPropertyName("continuationFromRunId"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ContinuationFromRunId { get => _continuationFromRunId; init { _continuationFromRunId = value; HasContinuationFromRunId = true; } }
    /// <summary>Explicit null is rejected instead of falling back to an unlinked run.</summary>
    [JsonIgnore] internal bool HasContinuationFromRunId { get; private set; }
    /// <summary>Track presence so an explicit null cannot silently select the legacy timing contract.</summary>
    private string? _timingContract;
    /// <summary>Optional fixed navigation-baseline timing selector; omission preserves v1.</summary>
    [JsonPropertyName("timingContract")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TimingContract
    {
        get => _timingContract;
        init { _timingContract = value; HasTimingContract = true; }
    }
    /// <summary>Reject this parameter on every other command, including explicit null values.</summary>
    [JsonIgnore]
    internal bool HasTimingContract { get; private set; }

    /// <summary>Fixed navigation timer-sharing selector; explicit null is invalid for either operation.</summary>
    private string? _capturePolicy;
    /// <summary>Omitted requests retain shared timer/task capture.</summary>
    [JsonPropertyName("capturePolicy")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? CapturePolicy
    {
        get => _capturePolicy;
        init { _capturePolicy = value; HasCapturePolicy = true; }
    }
    /// <summary>Distinguish absent legacy fields from explicit null.</summary>
    [JsonIgnore]
    internal bool HasCapturePolicy { get; private set; }
    /// <summary>Track explicit null so the restart-only option cannot appear on another command.</summary>
    private ExternalControlIdleRestart? _idleRestart;

    /// <summary>Optional atomic idle-only restart with exact target pins; omission preserves direct legacy behavior.</summary>
    [JsonPropertyName("idleRestart")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ExternalControlIdleRestart? IdleRestart
    {
        get => _idleRestart;
        init { _idleRestart = value; HasIdleRestart = true; }
    }

    /// <summary>Distinguish omitted legacy restart from an explicitly malformed null option.</summary>
    [JsonIgnore]
    internal bool HasIdleRestart { get; private set; }
    /// <summary>Exact terminal fixed-leg run for a read-only result query; no supplied route or input is accepted.</summary>
    [JsonPropertyName("navigationBaselineRunId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? NavigationBaselineRunId { get; init; }
    /// <summary>Exact accepted reset run for the read-only diagnostics command; never selects or starts work.</summary>
    [JsonPropertyName("navigationResetRunId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? NavigationResetRunId { get; init; }
    /// <summary>Optional bounded yaw for the fixed navigation-reset profile; no coordinates or script are accepted.</summary>
    [JsonPropertyName("targetYawDegrees")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? TargetYawDegrees { get; init; }
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

    /// <summary>Explicit agent input opt-in; absence is observation-only. Valid only for startAgentStream.</summary>
    [JsonPropertyName("enableInput")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? EnableInput { get; init; }

    /// <summary>Preserve explicit null presence so other commands cannot carry this start-only option.</summary>
    private string? _observationProfile;

    /// <summary>Fixed agent preprocessing profile; omitted/null retains the legacy stream format.</summary>
    [JsonPropertyName("observationProfile")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ObservationProfile
    {
        get => _observationProfile;
        init { _observationProfile = value; HasObservationProfile = true; }
    }

    /// <summary>Track option presence separately from its null-as-legacy value during validation.</summary>
    [JsonIgnore]
    internal bool HasObservationProfile { get; private set; }

    /// <summary>One existing capture backend; valid only for the scoped setCaptureMode command.</summary>
    [JsonPropertyName("captureMode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public CaptureModes? CaptureMode { get; init; }

    /// <summary>Backing value keeps an explicit null distinct from an omitted mode.</summary>
    private string? _readbackMode;

    /// <summary>Optional exact WGC V2 readback mode; omission selects blocking when reattaching.</summary>
    [JsonPropertyName("readbackMode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ReadbackMode
    {
        get => _readbackMode;
        init { _readbackMode = value; HasReadbackMode = true; }
    }

    /// <summary>Reject explicit null and use on unrelated commands before any mutation.</summary>
    [JsonIgnore]
    internal bool HasReadbackMode { get; private set; }
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
    /// <summary>Primary-only support for immutable endpoint/game intent across connection and callback launch paths.</summary>
    [JsonPropertyName("childStartupIntentVersion")]
    public int ChildStartupIntentVersion { get; init; }
    /// <summary>Current/last explicit primary startup intent; absent UI data never authorizes joining endpoint-only startup.</summary>
    [JsonPropertyName("childStartupMode")]
    public string? ChildStartupMode { get; init; }
    /// <summary>Highest supported idle-restart contract: version one reserves admission/pins; version two adds explicit startup intent.</summary>
    [JsonPropertyName("idleRestartVersion")]
    public int IdleRestartVersion { get; init; }
    /// <summary>Compact fixed-leg owner state; complete evidence is available only through its pinned result query.</summary>
    [JsonPropertyName("navigationBaseline")]
    public NavigationBaselineStatus NavigationBaseline { get; init; } = new();
    /// <summary>Current/last fixed reset and its verified 2D pose samples, independent of runtime attachment status.</summary>
    [JsonPropertyName("navigationReset")]
    public NavigationResetStatus NavigationReset { get; init; } = new();
    /// <summary>Only current confirms fresh UI-owned readiness; timeout/cancelled/unavailable/failed are conservative.</summary>
    [JsonPropertyName("uiStatus")]
    public string UiStatus { get; init; } = "unavailable";

    /// <summary>Agent task state; listening is published only after pipe creation succeeds.</summary>
    [JsonPropertyName("agentStreamState")]
    public string AgentStreamState { get; init; } = "idle";
    /// <summary>Most recent agent task rejection/failure, independent of game startup.</summary>
    [JsonPropertyName("agentStreamError")]
    public string? AgentStreamError { get; init; }
    /// <summary>True until the service-owned agent task and its cleanup have finished.</summary>
    [JsonPropertyName("agentStreamRunning")]
    public bool AgentStreamRunning { get; init; }
    /// <summary>Server-side input opt-in for the active agent lease.</summary>
    [JsonPropertyName("agentInputEnabled")]
    public bool AgentInputEnabled { get; init; }
    /// <summary>Immutable preprocessing profile of the active or most recently finished agent task.</summary>
    [JsonPropertyName("agentObservationProfile")]
    public string AgentObservationProfile { get; init; } = global::BetterGenshinImpact.Core.Agent.AgentObservationProfile.Legacy;
    /// <summary>Fixed agent transport endpoint; callers cannot choose arbitrary pipe names.</summary>
    [JsonPropertyName("agentPipeName")]
    public string AgentPipeName { get; init; } = string.Empty;
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

    /// <summary>Selected capture backend; successful reattachment additionally requires game_ready and runtimeRunning.</summary>
    [JsonPropertyName("captureMode")]
    public string CaptureMode { get; init; } = string.Empty;

    /// <summary>Version of the WGC V2 readback selection/status contract, independent of capture health.</summary>
    [JsonPropertyName("readbackVersion")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ReadbackVersion { get; init; }

    /// <summary>Exact readback choices supported for WindowsGraphicsCaptureV2 only.</summary>
    [JsonPropertyName("readbackModes")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string[]? ReadbackModes { get; init; }

    /// <summary>Saved WGC V2 setting; this does not describe a running capture.</summary>
    [JsonPropertyName("configuredReadbackMode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ConfiguredReadbackMode { get; init; }

    /// <summary>Actual attached capture mode, absent when capture is stopped or lacks this capability.</summary>
    [JsonPropertyName("effectiveReadbackMode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EffectiveReadbackMode { get; init; }

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
