using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Pipes;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.Instance;
using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;
using OpenCvSharp;
using System;
using System.Buffers;
using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>
/// An explicitly launched RDP-only agent session inside the caller's existing TaskRunner scope.
/// Capture publishes one latest RGB frame; a slow policy never creates a screenshot queue.
/// </summary>
public sealed class AgentStreamSession
{
    /// <summary>Bound game lifetime; this session never acquires or activates a different window.</summary>
    private readonly GameRuntime _runtime;
    /// <summary>JSON uses the same camel-case schema in both directions.</summary>
    private readonly JsonSerializerSettings _json = new()
    {
        ContractResolver = new CamelCasePropertyNamesContractResolver(),
        MaxDepth = 16,
        TypeNameHandling = TypeNameHandling.None
    };
    /// <summary>Fresh identities prevent stale clients from continuing after a restart.</summary>
    private readonly string _sessionId = Guid.NewGuid().ToString("N");
    /// <summary>Separate input lease identity for protocol validation.</summary>
    private readonly string _ownerEpoch = Guid.NewGuid().ToString("N");
    /// <summary>One monotonic clock shared by frames, proposals and receipts.</summary>
    private readonly long _clockOrigin = Stopwatch.GetTimestamp();
    /// <summary>All host and mapped source times share this explicit QPC origin.</summary>
    private double NowMs => Stopwatch.GetElapsedTime(_clockOrigin).TotalMilliseconds;
    /// <summary>Latest-only publication; byte arrays are immutable after publication.</summary>
    private CapturedFrame? _latest;
    /// <summary>Protects publication leases so a buffer cannot be recycled while transport reads it.</summary>
    private readonly object _frameGate = new();
    /// <summary>Monotonic observation sequence.</summary>
    private long _frameId;
    /// <summary>Aggregate pending polls are diagnostic only; they never become frame IDs or readiness confirmations.</summary>
    private long _readbackPendingCount;
    /// <summary>Last typed capture outcome; bounded scalar telemetry contains no image or renewable source clock.</summary>
    private string? _lastCaptureOutcome;
    /// <summary>One publication cadence also bounds initiation of expected-pending readback retries.</summary>
    internal const double CaptureCadenceMs = 1000.0 / 30;
    /// <summary>Yield between nonblocking polls; never spin or retry a genuine unavailable result.</summary>
    internal const int PendingReadbackRetryDelayMs = 2;
    /// <summary>A separate call cap remains finite even with a stalled clock or immediately completing test delay.</summary>
    internal const int MaximumPendingReadbackRetries = 8;
    /// <summary>Optional native transition evidence, bounded independently of the stream and input controller.</summary>
    private readonly AgentReadinessSnapshots _snapshots;
    /// <summary>Fixed image contract for this stream lifetime; never switched under an active client.</summary>
    private readonly string _observationProfile;
    /// <summary>Capture-loop-owned immutable plan; replaced only when native dimensions change.</summary>
    private AgentHamming192Plan? _nativeResizePlan;
    /// <summary>Used only to add explicitly negotiated detached application data; no transport callback holds its lock.</summary>
    private AgentActionController? _applicationController;

    /// <summary>Only the explicit start option may expose queued v2 on this session.</summary>
    private readonly bool _experimentalQueuedStepApplications;
    /// <summary>Server-read staged assembly fingerprint, never supplied by an agent client.</summary>
    private readonly string? _producerBuildSha256;
    /// <summary>Transport-thread-owned one-shot latch; failed or lost confirmation cannot renew the channel.</summary>
    private bool _queuedEnableAttempted;
    /// <summary>Explicit same-owner opt-in to read-only native pose metadata; ordinary streams keep their existing capture cost.</summary>
    private bool _navigationGuidanceEnabled;
    /// <summary>Optional same-image HUD analysis; ordinary streams do not pay its native pixel-processing cost.</summary>
    private bool _combatObservationEnabled;
    /// <summary>Published before the enable flag and immutable once the capture thread may construct its recognizer.</summary>
    private string _navigationProfileId = AgentNavigationProfile.Courtyard;
    /// <summary>Explicit one-shot UI authority; ordinary actions always use the original world guard.</summary>
    private AgentMapInspection? _mapInspection;

    /// <summary>Authenticated opt-in configuration uses the existing exact session QPC origin, never paired approximate samples.</summary>
    internal JObject StepApplicationConfiguration(RuntimeAgentInput input, string producerBuildSha256, int version = 1)
    {
        AgentStepApplicationWire.Require(Stopwatch.IsHighResolution, "application_qpc_unavailable");
        var config = new JObject { ["version"] = version, ["mode"] = version == 2 ? AgentStepApplicationWire.QueuedMode : AgentStepApplicationWire.Mode,
            ["sessionId"] = _sessionId, ["ownerEpoch"] = _ownerEpoch, ["channelId"] = Guid.NewGuid().ToString("N"),
            ["backendId"] = "win32-sendinput", ["backendEpoch"] = version == 2 ? input.OriginalApplicationBackendEpoch : input.ApplicationBackendEpoch,
            ["buildSha256"] = producerBuildSha256, ["clockKind"] = "windows_qpc", ["sessionOriginTicks"] = _clockOrigin,
            ["clockFrequency"] = Stopwatch.Frequency,
            ["allowedKeys"] = new JArray(AgentActionController.AllowedKeys.Where(k => !AgentStepApplicationWire.Aliases.Contains(k)).OrderBy(k => k, StringComparer.Ordinal)) };
        AgentStepApplicationWire.Configuration(config); return config;
    }

    /// <summary>Create a stream bound to the current task's runtime.</summary>
    public AgentStreamSession(GameRuntime runtime, string observationProfile = AgentObservationProfile.Legacy,
        bool experimentalQueuedStepApplications = false, string? producerBuildSha256 = null)
    {
        _runtime = runtime;
        _experimentalQueuedStepApplications = experimentalQueuedStepApplications;
        if (experimentalQueuedStepApplications) AgentStepApplicationWire.Digest(producerBuildSha256);
        _producerBuildSha256 = producerBuildSha256;
        _observationProfile = AgentObservationProfile.Normalize(observationProfile);
        _snapshots = new AgentReadinessSnapshots(Global.Absolute(Path.Combine("User", "AgentDiagnostics", _sessionId)));
    }

    /// <summary>Run until cancellation or controller disconnect. Input is explicitly opt-in.</summary>
    public async Task RunAsync(string pipeName, bool enableInput, CancellationToken cancellationToken,
        Action? onListening = null)
    {
        AgentStepApplicationWire.Require(!_experimentalQueuedStepApplications || enableInput, "queued_input_opt_in_required");
        ValidateInputPolicy(enableInput);
        if (!GameTaskSessionScope.IsActive)
            throw new InvalidOperationException("Agent streaming must run inside the current TaskRunner session.");
        // A console session can have any numeric ID: only the OS remote-session flag establishes RDP.
        if (!System.Windows.Forms.SystemInformation.TerminalServerSession ||
            InstanceBootstrap.Current?.Context.InstanceType != BetterGiInstanceType.ChildSession)
            throw new InvalidOperationException("Agent streaming is restricted to a separate RDP child session.");
        if (_runtime.Kind != GameRuntimeKind.Win32Window)
            throw new InvalidOperationException("The initial agent bridge supports the local Win32 game runtime only.");
        if (string.IsNullOrEmpty(pipeName) || !Regex.IsMatch(pipeName, @"\ABetterGI\.Agent\.[A-Za-z0-9_.-]{1,100}\z"))
            throw new ArgumentException("Use a pipe name beginning BetterGI.Agent. followed by a short local identifier.", nameof(pipeName));

        using var stop = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _runtime.Stopping);
        using var identity = WindowsIdentity.GetCurrent();
        await using var pipe = LocalUserPipe.Create(pipeName, identity.User
            ?? throw new InvalidOperationException("The agent pipe requires a Windows user identity."));
        var input = new RuntimeAgentInput(_runtime);
        var controller = new AgentActionController(input, enableInput, () => NowMs, _runtime.DesktopDcSourcePolicy, input.ReadTrackedState);
        _mapInspection = new AgentMapInspection(_sessionId, _ownerEpoch, _clockOrigin, controller, input);
        // Install the nonthrowing observer before any owned loop can dispatch input.
        input.Telemetry.Sink = controller.RecordInputCall;
        if (AgentStepApplicationWire.Available) _applicationController = controller;
        var captureTask = Task.Run(() => CaptureLoopAsync(controller, stop.Token), stop.Token);
        var inputTask = Task.Run(() => InputLoopAsync(controller, stop.Token), stop.Token);
        var transportTask = ServeAsync(pipe, controller, input, enableInput, stop.Token);
        try
        {
            // Signal readiness after acquiring the pipe and starting all owned loops.
            onListening?.Invoke();
            var finished = await Task.WhenAny(captureTask, inputTask, transportTask);
            await finished;
        }
        finally
        {
            // Input release precedes waiting for any native capture or pipe operation to unwind.
            stop.Cancel();
            _mapInspection.Cancel();
            controller.Stop(NowMs, "session_ended");
            await pipe.DisposeAsync();
            try { await Task.WhenAll(captureTask, inputTask, transportTask); }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
            finally
            {
                lock (_frameGate) { _latest?.Release(); _latest = null; }
                await _snapshots.CompleteAsync(TimeSpan.FromSeconds(3));
            }
        }
    }

    /// <summary>Capture and downsample independently of disk, OCR, inference and transport writes.</summary>
    private async Task CaptureLoopAsync(AgentActionController controller, CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(CaptureCadenceMs));
        AgentNavigationRecognizer? navigation = null;
        AgentSourceFrame? previousSource = null;
        try
        {
        while (await timer.WaitForNextTickAsync(ct))
        {
            if (!_runtime.Window.IsAlive || _runtime.IsStopping) return;
            // Warm the opt-in local map before capturing, so warmup cannot renew an old image's timestamp.
            if (Volatile.Read(ref _navigationGuidanceEnabled) && navigation is null)
                navigation = new AgentNavigationRecognizer(_runtime.SystemInfo.DpiScale, Volatile.Read(ref _navigationProfileId));
            var capturedAt = NowMs;
            // Expected GPU readback may finish before the next cadence. Real failures still skip/invalidate immediately.
            // Preserve this original request time across polls; neither retry nor delay renews source authority.
            using var captured = await CaptureWithPendingRetriesAsync(_runtime.Capture, controller, capturedAt,
                () => NowMs, () => _runtime.Window.IsAlive && !_runtime.IsStopping, ct);
            if (captured is null) continue;
            var source = captured!.Frame;
            // Desktop evidence is required even for passive publication; absence never uses the old receipt-time fallback.
            var hostSnapshot = MapHostEvidence(captured, _runtime.IsDesktopCapture, _runtime.DesktopDcSourcePolicy,
                _clockOrigin, Stopwatch.Frequency, NowMs);
            // Snapshot diagnostics now: another capture may replace the provider's latest record before transport reads this frame.
            var captureTiming = captured.HostSnapshotInfo is { } exactHost &&
                _runtime.Capture is IDesktopDcCaptureDiagnostics diagnostics ? diagnostics.GetTiming(exactHost) : null;
            // Known WGC sources retain their original identity and time when the backend returns cached pixels.
            if (captured!.SourceInfo is not null && !Stopwatch.IsHighResolution)
            {
                controller.InvalidateWorld(NowMs, "source_clock_unavailable");
                continue;
            }
            var sourceFrame = captured.SourceInfo is { } timing
                ? MapSourceFrame(timing, _clockOrigin, Stopwatch.Frequency) : null;
            if (sourceFrame is not null && previousSource is not null &&
                sourceFrame.CaptureEpoch == previousSource.CaptureEpoch && sourceFrame.Timestamp100ns == previousSource.Timestamp100ns)
                continue; // Keep the last published frame; the independent input watchdog still expires its source age.
            previousSource = sourceFrame;
            var frameId = Interlocked.Increment(ref _frameId);
            var recognitionStarted = Stopwatch.GetTimestamp();
            var evidence = navigation is null ? AgentWorldRecognizer.Recognize(source)
                : NavigationBaselineCapturePolicy.RecognizeWorld(source,
                    NavigationBaselineCapturePolicy.TaskOwnedTimer, _ => { });
            var recognitionMs = Stopwatch.GetElapsedTime(recognitionStarted).TotalMilliseconds;
            var observation = new AgentObservation(frameId, capturedAt, source.Width, source.Height, evidence, recognitionMs, sourceFrame)
            { HostSnapshot = hostSnapshot };
            // A negative frame releases input before RGB conversion or transport can delay it.
            var readiness = controller.RegisterFrame(observation, NowMs);
            // Inspect these same native pixels after the safety gate; never take another capture for motion hints.
            var motion = AgentMotionRecognizer.Recognize(source, readiness.Ready);
            var navigationPose = navigation?.Recognize(source, observation, readiness, motion);
            var combatEvidence = Volatile.Read(ref _combatObservationEnabled)
                ? AgentCombatRecognizer.Recognize(source, observation, readiness.Ready) : null;
            if (_mapInspection?.Pending == true)
                _mapInspection.Observe(source, observation, readiness, motion, navigationPose, ct);
            _snapshots.Observe(source, observation, readiness);
            var resizeStarted = Stopwatch.GetTimestamp();
            var bytes = EncodeObservation(source, out var width, out var height, out var payloadBytes);
            CapturedFrame next;
            try
            {
                next = new CapturedFrame(observation, width, height, bytes, payloadBytes,
                    NowMs - capturedAt, readiness, motion)
                { ObservationResizeMs = Stopwatch.GetElapsedTime(resizeStarted).TotalMilliseconds,
                    DesktopDcTiming = captureTiming, NavigationPose = navigationPose, CombatEvidence = combatEvidence };
            }
            catch { ArrayPool<byte>.Shared.Return(bytes); throw; }
            lock (_frameGate)
            {
                var previous = _latest;
                _latest = next;
                previous?.Release();
            }
        }
        }
        finally { navigation?.Dispose(); }
    }

    /// <summary>Transfer one ready frame, retrying only validated expected-pending outcomes inside a finite capture turn.</summary>
    /// <remarks>The deadline bounds retry initiation, not an already executing synchronous capture. Recognition, source/session
    /// validation and the independent input watchdog remain outside this helper. Injected clocks/delays support inert tests.</remarks>
    internal async Task<GameCaptureFrame?> CaptureWithPendingRetriesAsync(IGameCapture capture,
        AgentActionController controller, double capturedAt, Func<double> clock, Func<bool> isActive,
        CancellationToken ct, Func<TimeSpan, CancellationToken, Task>? delay = null)
    {
        delay ??= Task.Delay;
        for (var retries = 0; ; retries++)
        {
            ct.ThrowIfCancellationRequested();
            if (!isActive()) return null;
            // An overslept delay must not start another capture, even if the nominal requested delay fit.
            if (retries > 0)
            {
                var elapsed = clock() - capturedAt;
                if (!double.IsFinite(elapsed) || elapsed < 0 || elapsed >= CaptureCadenceMs) return null;
            }
            var attempt = GameCaptureReadbackConsumer.Capture(capture, false, out _);
            var frame = attempt.Frame;
            try
            {
                if (!SkipUnpublishedCapture(attempt, controller, clock()))
                {
                    var ready = frame;
                    frame = null; // Caller now owns the exact returned pixels and immutable source metadata.
                    return ready;
                }
            }
            finally { frame?.Dispose(); }

            if (attempt.Outcome != GameCaptureAttemptOutcome.ReadbackPending ||
                retries >= MaximumPendingReadbackRetries) return null;
            var spent = clock() - capturedAt;
            if (!double.IsFinite(spent) || spent < 0 ||
                spent + PendingReadbackRetryDelayMs >= CaptureCadenceMs) return null;
            await delay(TimeSpan.FromMilliseconds(PendingReadbackRetryDelayMs), ct).ConfigureAwait(false);
        }
    }

    /// <summary>Only returned pixels can enter recognition; expected polling never renews or artificially invalidates authority.</summary>
    internal bool SkipUnpublishedCapture(GameCaptureAttempt attempt, AgentActionController controller, double now)
    {
        Volatile.Write(ref _lastCaptureOutcome, attempt.Outcome.ToString());
        if (attempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending)
        {
            Interlocked.Increment(ref _readbackPendingCount);
            return true;
        }
        if (attempt.Frame is null || attempt.Frame.Frame.Empty())
        {
            controller.InvalidateWorld(now, "capture_unavailable");
            return true;
        }
        return false;
    }

    /// <summary>Rent one immutable publication payload; the caller takes ownership only on success.</summary>
    /// <remarks>Native memory is borrowed synchronously while the captured Mat remains owned by the loop.
    /// Conversion failures return the lease. Only the exact payload prefix is transmitted/released later.</remarks>
    internal unsafe byte[] EncodeObservation(Mat source, out int width, out int height, out int payloadBytes,
        ArrayPool<byte>? pool = null)
    {
        pool ??= ArrayPool<byte>.Shared;
        if (source.Empty() || (source.Type() != MatType.CV_8UC3 && source.Type() != MatType.CV_8UC4))
            throw new ArgumentException("Agent observations require a nonempty native BGR/BGRA byte image.", nameof(source));
        if (_observationProfile == AgentObservationProfile.P2PNativeHamming192)
        {
            if (_nativeResizePlan is null || _nativeResizePlan.Width != source.Width || _nativeResizePlan.Height != source.Height)
                _nativeResizePlan = new AgentHamming192Plan(source.Width, source.Height);
            int channels = source.Channels();
            int stride = checked((int)source.Step());
            int visibleBytes = checked((int)((long)(source.Height - 1) * stride + (long)source.Width * channels));
            var input = new ReadOnlySpan<byte>((void*)source.Data, visibleBytes);
            width = height = AgentHamming192Plan.OutputSize;
            payloadBytes = AgentHamming192Plan.OutputBytes;
            var output = pool.Rent(payloadBytes);
            try
            {
                _nativeResizePlan.ResizeInto(input, stride, channels, true, output.AsSpan(0, payloadBytes));
                return output;
            }
            catch { pool.Return(output); throw; }
        }

        // Preserve the existing default operation order, aspect ratio, cap and interpolation exactly.
        var scale = Math.Min(1.0, Math.Min(640.0 / source.Width, 360.0 / source.Height));
        using var small = new Mat();
        Cv2.Resize(source, small, new Size(Math.Max(1, (int)(source.Width * scale)),
            Math.Max(1, (int)(source.Height * scale))), interpolation: InterpolationFlags.Area);
        using var rgb = new Mat();
        Cv2.CvtColor(small, rgb, small.Channels() == 4 ? ColorConversionCodes.BGRA2RGB : ColorConversionCodes.BGR2RGB);
        width = rgb.Width;
        height = rgb.Height;
        payloadBytes = checked(width * height * 3);
        var bytes = pool.Rent(payloadBytes);
        try { Marshal.Copy(rgb.Data, bytes, 0, payloadBytes); return bytes; }
        catch { pool.Return(bytes); throw; }
    }

    /// <summary>Observe focus/deadline changes even when the model or socket stops responding.</summary>
    private async Task InputLoopAsync(AgentActionController controller, CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(10));
        while (await timer.WaitForNextTickAsync(ct))
        {
            controller.Tick(NowMs);
            _mapInspection?.Watch();
        }
    }

    /// <summary>Serve one same-user controller; disconnect ends this task rather than transferring the lease.</summary>
    private async Task ServeAsync(NamedPipeServerStream pipe, AgentActionController controller,
        RuntimeAgentInput input, bool enableInput, CancellationToken ct)
    {
        await pipe.WaitForConnectionAsync(ct);
        await WriteAsync(pipe, CreateHello(enableInput), null, ct);
        while (!ct.IsCancellationRequested)
        {
            var request = await ReadAsync(pipe, ct);
            if (request is null) return;
            if (request.Version != 1 || request.SessionId != _sessionId || request.OwnerEpoch != _ownerEpoch || request.GoalVersion != 1)
            {
                await WriteAsync(pipe, new { type = "rejected", reason = "session_identity_mismatch" }, null, ct);
                continue;
            }
            if (request.HasStepApplicationsAck && !(_experimentalQueuedStepApplications && request.Command == "enableStepApplications"))
            {
                try
                {
                    AgentStepApplicationWire.Require(request.StepApplicationsAck is not null, "null_application_ack");
                    controller.AcknowledgeStepApplications(request.StepApplicationsAck!);
                }
                catch (Exception) { await WriteAsync(pipe, new { type = "rejected", reason = "invalid_step_application_ack" }, null, ct); continue; }
            }
            switch (request.Command)
            {
                case "inspectJunctionMap":
                case "recoverJunctionMap":
                case "mapInspectionStatus":
                case "mapInspectionImage":
                    object mapReply;
                    byte[]? mapPng = null;
                    try
                    {
                        if (request.Command is "inspectJunctionMap" or "recoverJunctionMap")
                        {
                            _mapInspection!.Start(request.RequestId, enableInput && !_experimentalQueuedStepApplications &&
                                Volatile.Read(ref _navigationGuidanceEnabled) && Stopwatch.IsHighResolution,
                                request.Command == "recoverJunctionMap", request.PriorEvidenceSha256);
                            mapReply = new { type = "mapInspectionStarted", request.RequestId };
                        }
                        else if (request.Command == "mapInspectionStatus")
                            mapReply = new { type = "mapInspection", inspection = _mapInspection!.Status(request.RequestId) };
                        else
                        {
                            mapPng = _mapInspection!.Image(request.RequestId, request.FrameId);
                            mapReply = new { type = "mapInspectionImage", request.RequestId, request.FrameId,
                                payloadBytes = mapPng.Length, sha256 = Convert.ToHexString(
                                    System.Security.Cryptography.SHA256.HashData(mapPng)).ToLowerInvariant() };
                        }
                    }
                    catch (InvalidOperationException error)
                    {
                        mapReply = new { type = "rejected", reason = error.Message };
                    }
                    await WriteAsync(pipe, mapReply, mapPng is null ? (ReadOnlyMemory<byte>?)null : mapPng, ct);
                    break;
                case "enableNavigationGuidance":
                    // This command only enables evidence. Input still requires both original explicit opt-ins.
                    var navigationProfile = request.NavigationProfile ?? AgentNavigationProfile.Courtyard;
                    if (!AgentNavigationProfile.IsSupported(navigationProfile)
                        || Volatile.Read(ref _navigationGuidanceEnabled) && navigationProfile != Volatile.Read(ref _navigationProfileId))
                    {
                        await WriteAsync(pipe, new { type = "rejected", reason = "unsupported_or_locked_navigation_profile" }, null, ct);
                        break;
                    }
                    Volatile.Write(ref _navigationProfileId, navigationProfile);
                    Volatile.Write(ref _navigationGuidanceEnabled, true);
                    await WriteAsync(pipe, new { type = "navigationGuidance", enabled = true,
                        capability = AgentNavigationRecognizer.GetCapability(navigationProfile) }, null, ct);
                    break;
                case "enableCombatObservation":
                    // Evidence-only negotiation does not change either native or client input authorization.
                    Volatile.Write(ref _combatObservationEnabled, true);
                    await WriteAsync(pipe, new { type = "combatObservation", enabled = true,
                        capability = AgentCombatRecognizer.Capability }, null, ct);
                    break;
                case "enableStepApplications":
                    JObject confirmation;
                    try
                    {
                        ClaimQueuedEnable(request, enableInput);
                        var configuration = StepApplicationConfiguration(input, _producerBuildSha256!, version: 2);
                        confirmation = controller.ConfigureQueuedStepApplications(configuration, input);
                        _applicationController = controller;
                    }
                    catch (InvalidOperationException error)
                    {
                        await WriteAsync(pipe, new { type = "rejected", reason = error.Message }, null, ct);
                        break;
                    }
                    // Write failures remain transport uncertainty. Never turn them into a second confirmation or input retry.
                    await WriteAsync(pipe, QueuedEnableReply(confirmation, NowMs), null, ct);
                    break;
                case "frame":
                    CapturedFrame? frame;
                    lock (_frameGate) { frame = _latest; frame?.Retain(); }
                    try
                    {
                        var currentReadiness = controller.GetWorldReadinessAndExecutionSnapshot(out var frameNow, out var executionContext);
                        if (frame is null)
                            await WriteAsync(pipe, WithDesktopEvidence(new { type = "waiting", payloadBytes = 0, observationProfile = _observationProfile,
                                readback = ReadbackSnapshot(),
                                inputAvailable = input.IsAvailable && currentReadiness.Ready,
                                worldReadiness = currentReadiness, serverNowMs = frameNow, executionContext,
                                motionEvidence = AgentMotionEvidence.Unavailable("capture_unavailable") }), null, ct);
                        else
                            await WriteAsync(pipe, WithDesktopEvidence(new { type = "frame", frame.Observation.FrameId, frame.Observation.CapturedAtMs,
                                frame.Width, frame.Height, frame.Observation.SourceWidth, frame.Observation.SourceHeight,
                                pixelFormat = "rgb24", frame.PayloadBytes, frame.CaptureMs,
                                observationProfile = _observationProfile, frame.ObservationResizeMs,
                                readback = ReadbackSnapshot(),
                                inputAvailable = input.IsAvailable && currentReadiness.Ready && frame.Readiness.Ready &&
                                    frame.Readiness.Epoch == currentReadiness.Epoch,
                                worldReadiness = currentReadiness, frameWorldReadiness = frame.Readiness,
                                motionEvidence = MotionForReadiness(frame.MotionEvidence, frame.Readiness, currentReadiness),
                                navigationPose = frame.NavigationPose,
                                combatEvidence = frame.CombatEvidence,
                                frame.Observation.SourceFrame,
                                sourceTimestampKind = frame.Observation.SourceFrame is null ? "unknown" : "wgc_reported_compositor_qpc",
                                sourceFrameAgeMs = frame.Observation.SourceFrame is { } sourceTiming
                                    ? (double?)(frameNow - sourceTiming.FreshnessAtMs) : null,
                                reportedSourceFrameAgeMs = frame.Observation.SourceFrame is { } reportedTiming
                                    ? (double?)(frameNow - reportedTiming.CapturedAtMs) : null,
                                serverNowMs = frameNow, executionContext,
                                receipts = controller.DrainReceipts(), droppedReceipts = controller.DroppedReceipts },
                                frame.Observation.HostSnapshot, frameNow, frame.DesktopDcTiming),
                                frame.Bytes.AsMemory(0, frame.PayloadBytes), ct);
                    }
                    finally { frame?.Release(); }
                    break;
                case "action":
                    if (_mapInspection?.RejectWalkingProposal() == true)
                    {
                        await WriteAsync(pipe, new { type = "rejected", request.RequestId, reason = "map_inspection_fenced" }, null, ct);
                        break;
                    }
                    if (_experimentalQueuedStepApplications && _applicationController is null)
                    {
                        await WriteAsync(pipe, new { type = "rejected", reason = "step_applications_not_enabled" }, null, ct);
                        break;
                    }
                    var now = NowMs;
                    var reason = controller.Submit(request, now, out var acceptedAtMs);
                    // Standard actions need not spend their first-input deadline waiting for the periodic tick.
                    // Acceptance remains admission only; the controller rechecks freshness/readiness before input.
                    if (reason is null) controller.TickFirstStandardStep(request.RequestId, NowMs);
                    var reply = new { type = reason is null ? "accepted" : "rejected", request.RequestId,
                        reason, receivedAtMs = now, acceptedAtMs = reason is null ? acceptedAtMs : (double?)null };
                    var admission = reason is null ? controller.QueuedAdmission(request.RequestId) : null;
                    if (admission is null) await WriteAsync(pipe, reply, null, ct);
                    else
                    {
                        var queuedReply = JObject.FromObject(reply, JsonSerializer.Create(_json));
                        queuedReply["stepApplicationAdmission"] = admission;
                        await WriteAsync(pipe, queuedReply, null, ct);
                    }
                    break;
                case "status":
                    var statusReadiness = controller.GetWorldReadinessAndExecutionSnapshot(out var statusNow, out var statusExecutionContext);
                    await WriteAsync(pipe, WithDesktopEvidence(new { type = "status", inputAvailable = input.IsAvailable && statusReadiness.Ready,
                        worldReadiness = statusReadiness,
                        readback = ReadbackSnapshot(),
                        diagnostics = _snapshots.Snapshot(),
                        serverNowMs = statusNow, executionContext = statusExecutionContext, receipts = controller.DrainReceipts(),
                        droppedReceipts = controller.DroppedReceipts }), null, ct);
                    break;
                case "configureDiagnostics":
                    if (request.RecordReadinessTransitions is not { } recordTransitions)
                    {
                        await WriteAsync(pipe, new { type = "rejected", reason = "missing_diagnostics_option" }, null, ct);
                        break;
                    }
                    _snapshots.Configure(recordTransitions);
                    await WriteAsync(pipe, new { type = "diagnostics", serverNowMs = NowMs,
                        diagnostics = _snapshots.Snapshot() }, null, ct);
                    break;
                case "release":
                    _mapInspection?.Cancel();
                    // The acknowledgement is also the client's fresh-source barrier, so sample it after release finishes.
                    var releasedReadiness = controller.ReleaseAndGetSnapshot(NowMs, out var releaseAcknowledgedAt, out var releaseExecutionContext);
                    await WriteAsync(pipe, new { type = "released", serverNowMs = releaseAcknowledgedAt,
                        worldReadiness = releasedReadiness, executionContext = releaseExecutionContext,
                        receipts = controller.DrainReceipts(), droppedReceipts = controller.DroppedReceipts }, null, ct);
                    break;
                case "stop":
                    _mapInspection?.Cancel();
                    controller.Stop(NowMs, "client_stop");
                    await WriteAsync(pipe, new { type = "stopped", executionContext = controller.GetExecutionContextSnapshot(),
                        receipts = controller.DrainReceipts() }, null, ct);
                    return;
                default:
                    await WriteAsync(pipe, new { type = "rejected", reason = "unknown_command" }, null, ct);
                    break;
            }
        }
    }

    /// <summary>A release, stale observation or recovery epoch must not revive cached motion evidence.</summary>
    internal static AgentMotionEvidence MotionForReadiness(AgentMotionEvidence evidence,
        AgentWorldReadiness frameReadiness, AgentWorldReadiness currentReadiness) =>
        currentReadiness.Ready && frameReadiness.Ready && currentReadiness.Epoch == frameReadiness.Epoch
            ? evidence : AgentMotionEvidence.Unavailable("world_not_ready");

    /// <summary>Bounded poll telemetry is separate from the retained frame's immutable source and capture clocks.</summary>
    private object ReadbackSnapshot() => new { mode = GameCaptureSettings.GetReadbackModeName(_runtime?.Capture),
        pendingCount = Interlocked.Read(ref _readbackPendingCount), lastOutcome = Volatile.Read(ref _lastCaptureOutcome) };

    /// <summary>Declare the visual input gate and resumable release capability before accepting requests.</summary>
    private object CreateHello(bool enableInput) => WithQueuedCapability(WithDesktopEvidence(new
    {
        type = "hello", version = 1, sessionId = _sessionId, ownerEpoch = _ownerEpoch,
        goalVersion = 1, inputEnabled = enableInput, supportsRelease = true,
        mapInspection = new { version = 1, recoveryVersion = 1, station = "sidewalk-junction", wgcOnly = true, maximumSourceAgeMs = 150,
            gameProcessId = _runtime?.Window.ProcessId ?? 0, gameWindowHandle = _runtime?.Window.Handle.ToInt64() ?? 0,
            deadlineMs = 12000, minimumResponseMs = 80, maxImages = 3, inputChannel = "original-game-hwnd" },
        readbackMode = GameCaptureSettings.GetReadbackModeName(_runtime?.Capture), readbackVersion = 1,
        supportsStartBeforeMs = true, maxActionStartAgeMs = AgentActionController.MaxActionStartAgeMs,
        clockFrequency = 1000, allowedKeys = AgentActionController.AllowedKeys,
        inputTelemetry = new { version = 1, eventCapacity = AgentActionController.InputEventCapacity,
            clock = "monotonic milliseconds since session start", sessionOriginAtStopwatchTicks = _clockOrigin,
            stopwatchFrequency = Stopwatch.Frequency, snapshotBasis = "controller_lock_publication_time",
            retainedEvents = true, observesBlockedCallConcurrently = false, physicalExecutionProven = false },
        clock = "monotonic milliseconds since session start", captureTimestampKind = "host_capture_request",
        observationProfile = _observationProfile, observationPreprocessing = AgentObservationProfile.Describe(_observationProfile),
        widthLimit = _observationProfile == AgentObservationProfile.P2PNativeHamming192 ? 192 : 640,
        heightLimit = _observationProfile == AgentObservationProfile.P2PNativeHamming192 ? 192 : 360,
        motionEvidence = new { version = 1, method = AgentMotionEvidence.MethodName,
            statuses = new[] { "unknown", "normal", "climb", "fly" }, normalIsGroundedProof = false, sameFrame = true,
            maxRecognitionWidth = AgentMotionRecognizer.MaxWidth, maxRecognitionHeight = AgentMotionRecognizer.MaxHeight },
        sourceFrameTiming = new { version = 2, maxAgeMs = AgentWorldReadinessGate.MaxAgeMs,
            distinctFramesForConfirmation = AgentWorldReadinessGate.ConfirmationFrames,
            knownTimestampKind = "wgc_reported_compositor_qpc", unknownFallback = "host_capture_request",
            freshnessAnchor = "min(reported_compositor_qpc, immutable_first_acquisition_qpc)",
            freshnessClockKinds = new[] { "reported_compositor_qpc", "first_acquisition_qpc" }, measuresGameRenderAge = false },
        supportsReadinessSnapshots = true, diagnostics = _snapshots.Snapshot(),
        navigationGuidance = AgentNavigationRecognizer.Capability,
        combatObservation = AgentCombatRecognizer.Capability,
        navigationProfiles = new[] { AgentNavigationProfile.Courtyard, AgentNavigationProfile.MondstadtSurface,
            AgentNavigationProfile.MondstadtCombatScout, AgentNavigationProfile.MondstadtNorthCombatScout },
        worldReadiness = new
        {
            version = 1, requiredForInput = true, method = "paimon_hud_and_modal_templates",
            confirmationFrames = AgentWorldReadinessGate.ConfirmationFrames, maxAgeMs = AgentWorldReadinessGate.MaxAgeMs,
            sourceTimestampKind = "host_capture_request",
            maxRecognitionWidth = AgentWorldRecognizer.MaxWidth, maxRecognitionHeight = AgentWorldRecognizer.MaxHeight,
            preserveAspectRatio = true, downsampling = "area", modalStarConfirmation = "native_template",
            nativeModalMaxWidth = AgentWorldRecognizer.NativeModalMaxWidth,
            nativeModalMaxHeight = AgentWorldRecognizer.NativeModalMaxHeight
        }
    }), enableInput);

    /// <summary>Default sessions retain the original header object and byte path; opt-in adds only the fixed v2 capability.</summary>
    internal object WithQueuedCapability(object header, bool enableInput)
    {
        if (!_experimentalQueuedStepApplications) return header;
        AgentStepApplicationWire.Require(enableInput, "queued_input_opt_in_required");
        var value = JObject.FromObject(header, JsonSerializer.Create(_json));
        value.Add("stepApplicationsAvailable", new JObject { ["version"] = 2, ["mode"] = AgentStepApplicationWire.QueuedMode });
        return value;
    }

    /// <summary>Consume a single authenticated, closed-shape enable request before any configuration can be installed.</summary>
    internal void ClaimQueuedEnable(AgentRequest request, bool enableInput)
    {
        AgentStepApplicationWire.Require(_experimentalQueuedStepApplications && enableInput, "step_applications_unavailable");
        var raw = request.RawApplicationRequest ?? throw new InvalidOperationException("enable_request_required");
        AgentStepApplicationWire.Fields(raw, "version", "command", "sessionId", "ownerEpoch", "goalVersion");
        AgentStepApplicationWire.Require(AgentStepApplicationWire.Integer(raw["version"]) == 1
            && AgentStepApplicationWire.Text(raw["command"]) == "enableStepApplications"
            && AgentStepApplicationWire.Text(raw["sessionId"]) == _sessionId
            && AgentStepApplicationWire.Text(raw["ownerEpoch"]) == _ownerEpoch
            && AgentStepApplicationWire.Integer(raw["goalVersion"]) == 1, "session_identity_mismatch");
        AgentStepApplicationWire.Require(!_queuedEnableAttempted, "step_applications_already_attempted");
        _queuedEnableAttempted = true;
    }

    /// <summary>The confirmation has its own field; ordinary retransmission extensions retain their existing names.</summary>
    internal static JObject QueuedEnableReply(JObject confirmation, double now) => new()
    {
        ["type"] = "stepApplicationsEnabled", ["stepApplicationConfirmation"] = confirmation.DeepClone(), ["serverNowMs"] = now
    };

    /// <summary>Reject desktop input opt-in before allocating the pipe, capture loop or input owner.</summary>
    internal void ValidateInputPolicy(bool enableInput)
    {
        if (enableInput && _runtime.IsDesktopCapture) _runtime.ThrowIfDesktopControllerUnavailable();
    }

    /// <summary>Add host-only wire fields without changing existing backend header objects or null-field behavior.</summary>
    internal object WithDesktopEvidence(object header, AgentHostSnapshot? snapshot = null, double? now = null,
        DesktopDcCaptureTiming? timing = null)
    {
        if (!_runtime.IsDesktopCapture) return header;
        var value = JObject.FromObject(header, JsonSerializer.Create(_json));
        value["hostSnapshotVersion"] = 1;
        value["sourceKind"] = DesktopCapturePolicy.HostAcquisitionV1;
        value["desktopDcSourcePolicy"] = _runtime.DesktopDcSourcePolicy;
        if (value["type"]?.Value<string>() == "frame")
        {
            if (snapshot is null || now is null || !snapshot.IsValidAt(now.Value) ||
                snapshot.DesktopDcSourcePolicy != _runtime.DesktopDcSourcePolicy)
                throw new InvalidOperationException("invalid_host_snapshot_publication");
            value["hostSnapshot"] = JObject.FromObject(snapshot, JsonSerializer.Create(_json));
            value["hostAcquisitionAgeMs"] = now.Value - snapshot.StartedAtMs;
            value["hostAcquisitionIntervalMs"] = snapshot.CompletedAtMs - snapshot.StartedAtMs;
            // Timings are optional diagnostics. A missing/foreign record cannot change this frame's authority or clocks.
            if (timing is not null && timing.CaptureEpoch == snapshot.CaptureEpoch &&
                timing.SnapshotId == snapshot.SnapshotId)
                value["desktopDcCaptureTiming"] = JObject.FromObject(timing, JsonSerializer.Create(_json));
        }
        if (value["type"]?.Value<string>() == "hello")
        {
            value["sourceFrameTiming"] = JObject.FromObject(new
            {
                version = 3, maxAgeMs = AgentWorldReadinessGate.MaxAgeMs,
                distinctSnapshotsForConfirmation = AgentWorldReadinessGate.ConfirmationFrames,
                knownTimestampKind = "unknown", sourceKind = DesktopCapturePolicy.HostAcquisitionV1, unknownFallback = "rejected",
                freshnessAnchor = "host_snapshot_started_qpc", measuresGameRenderAge = false
            });
            value["worldReadiness"]!["sourceTimestampKind"] = "unknown";
            value["worldReadiness"]!["sourceKind"] = DesktopCapturePolicy.HostAcquisitionV1;
            value["worldReadiness"]!["freshnessAnchor"] = "host_snapshot_started_qpc";
        }
        return value;
    }

    /// <summary>Bind the exact raw host interval to this stream; malformed/mixed/foreign evidence is terminal.</summary>
    internal static AgentHostSnapshot? MapHostEvidence(GameCaptureFrame frame, bool desktop, string? policy,
        long origin, long frequency, double checkedAtMs)
    {
        if (!desktop)
        {
            if (frame.HostSnapshotInfo is not null) throw new InvalidOperationException("unexpected_host_snapshot");
            return null;
        }
        if (!Stopwatch.IsHighResolution || frame.SourceInfo is not null || frame.HostSnapshotInfo is not { } host ||
            frequency != Stopwatch.Frequency || host.ClockFrequency != frequency)
            throw new InvalidOperationException("invalid_host_snapshot");
        var mapped = new AgentHostSnapshot(host.CaptureEpoch.ToString("N"), host.SnapshotId,
            host.StartedAtStopwatchTicks, host.CompletedAtStopwatchTicks, host.ClockFrequency, origin,
            DesktopCapturePolicy.Validate(policy));
        if (!mapped.IsValidAt(checkedAtMs)) throw new InvalidOperationException("invalid_host_snapshot");
        return mapped;
    }

    /// <summary>Convert source TimeSpan ticks and local QPC ticks without assuming equal tick frequencies.</summary>
    internal static AgentSourceFrame MapSourceFrame(GameCaptureSourceInfo source, long sessionOrigin, long frequency)
    {
        if (frequency <= 0) throw new ArgumentOutOfRangeException(nameof(frequency));
        // Microsoft defines WGC SystemRelativeTime as compositor QPC time expressed in 100ns TimeSpan units.
        // Real WGC timestamps can lead acquisition; preserve them and bound freshness by immutable first acquisition.
        // Stopwatch.GetTimestamp uses the same Windows QPC clock, but raw ticks must use Stopwatch.Frequency.
        // https://learn.microsoft.com/uwp/api/windows.graphics.capture.direct3d11captureframe.systemrelativetime
        // https://learn.microsoft.com/windows/win32/sysinfo/acquiring-high-resolution-time-stamps
        // Int128 arithmetic avoids intermediate overflow and subtraction of large rounded floating-point values.
        var sourceDelta = (Int128)source.SourceTimestamp100ns * frequency - (Int128)sessionOrigin * TimeSpan.TicksPerSecond;
        return new AgentSourceFrame(source.CaptureEpoch.ToString("N"), source.SourceTimestamp100ns,
            (double)sourceDelta / frequency / TimeSpan.TicksPerMillisecond,
            (double)((Int128)source.AcquiredAtStopwatchTicks - sessionOrigin) * 1000 / frequency);
    }

    /// <summary>Read a bounded JSON header. Incoming requests never contain image payloads.</summary>
    private async Task<AgentRequest?> ReadAsync(Stream stream, CancellationToken ct)
    {
        var prefix = new byte[4];
        var count = await stream.ReadAsync(prefix.AsMemory(0, 1), ct);
        if (count == 0) return null;
        await stream.ReadExactlyAsync(prefix.AsMemory(1), ct);
        var length = BinaryPrimitives.ReadInt32LittleEndian(prefix);
        if (length is < 2 or > 65536) throw new InvalidDataException("Agent request exceeds the protocol size limit.");
        var bytes = new byte[length];
        await stream.ReadExactlyAsync(bytes, ct);
        var text = Encoding.UTF8.GetString(bytes);
        var request = JsonConvert.DeserializeObject<AgentRequest>(text, _json)
            ?? throw new InvalidDataException("Missing agent request.");
        // The legacy parser is unchanged. New authority-bearing envelopes additionally reject duplicate fields.
        if (request.HasStepApplicationEnvelope || request.HasStepApplicationsAck || request.HasQueueAfter || request.Command == "enableStepApplications")
        {
            text = new UTF8Encoding(false, true).GetString(bytes);
            request = request with { RawApplicationRequest = AgentStepApplicationWire.Parse(text, 65536) };
        }
        return request;
    }

    /// <summary>Write JSON followed by optional raw pixels; never base64-encode or persist control frames.</summary>
    private async Task WriteAsync(Stream stream, object header, ReadOnlyMemory<byte>? pixels, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        byte[] bytes;
        var extensions = _applicationController?.StepApplicationExtensions();
        if (extensions is null) bytes = Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(header, _json));
        else
        {
            var combined = JObject.FromObject(header, JsonSerializer.Create(_json));
            foreach (var property in extensions.Properties())
            {
                AgentStepApplicationWire.Require(!combined.ContainsKey(property.Name), "application_extension_collision");
                combined.Add(property.Name, property.Value.DeepClone());
            }
            bytes = Encoding.ASCII.GetBytes(AgentStepApplicationWire.Freeze(combined, AgentStepApplicationWire.HeaderBytes));
        }
        var prefix = new byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(prefix, bytes.Length);
        await stream.WriteAsync(prefix, timeout.Token);
        await stream.WriteAsync(bytes, timeout.Token);
        if (pixels is not null) await stream.WriteAsync(pixels.Value, timeout.Token);
        await stream.FlushAsync(timeout.Token);
    }

    /// <summary>Owned, immutable RGB image and capture metadata; older instances are reclaimed after readers finish.</summary>
    private sealed class CapturedFrame(AgentObservation observation, int width, int height, byte[] bytes, int payloadBytes,
        double captureMs, AgentWorldReadiness readiness, AgentMotionEvidence motionEvidence)
    {
        /// <summary>Initial reference belongs to the publication slot.</summary>
        private int _references = 1;
        /// <summary>Clock and source viewport metadata.</summary>
        public AgentObservation Observation { get; } = observation;
        /// <summary>Transmitted image width.</summary>
        public int Width { get; } = width;
        /// <summary>Transmitted image height.</summary>
        public int Height { get; } = height;
        /// <summary>Leased buffer, possibly larger than the payload.</summary>
        public byte[] Bytes { get; } = bytes;
        /// <summary>Exact RGB payload length; pool capacity is never transmitted.</summary>
        public int PayloadBytes { get; } = payloadBytes;
        /// <summary>Capture plus conversion duration.</summary>
        public double CaptureMs { get; } = captureMs;
        /// <summary>Profile conversion plus any plan creation, excluding native world/motion recognition.</summary>
        public double ObservationResizeMs { get; init; }
        /// <summary>Immutable diagnostics selected for this acquisition; never fetched again from mutable backend state.</summary>
        public DesktopDcCaptureTiming? DesktopDcTiming { get; init; }
        /// <summary>Readiness derived from precisely this image, distinct from the current input gate.</summary>
        public AgentWorldReadiness Readiness { get; } = readiness;
        /// <summary>Keyboard-hint evidence derived from this publication's native source before downsampling.</summary>
        public AgentMotionEvidence MotionEvidence { get; } = motionEvidence;
        /// <summary>Optional localization from these same native pixels, with no carried-over pose on skipped recognition.</summary>
        public AgentNavigationPose? NavigationPose { get; init; }
        /// <summary>Optional, immutable HUD evidence from this source image, never refreshed independently.</summary>
        public AgentCombatEvidence? CombatEvidence { get; init; }
        /// <summary>Acquire under the publication lock before reading the buffer.</summary>
        public void Retain() => Interlocked.Increment(ref _references);
        /// <summary>Recycle only after the publication slot and transport have both finished.</summary>
        public void Release()
        {
            if (Interlocked.Decrement(ref _references) == 0) ArrayPool<byte>.Shared.Return(Bytes);
        }
    }
}
