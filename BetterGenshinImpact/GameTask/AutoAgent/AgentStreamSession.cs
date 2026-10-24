using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Pipes;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.Instance;
using Fischless.GameCapture;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using OpenCvSharp;
using System;
using System.Buffers;
using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
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
    /// <summary>Optional native transition evidence, bounded independently of the stream and input controller.</summary>
    private readonly AgentReadinessSnapshots _snapshots;
    /// <summary>Fixed image contract for this stream lifetime; never switched under an active client.</summary>
    private readonly string _observationProfile;
    /// <summary>Capture-loop-owned immutable plan; replaced only when native dimensions change.</summary>
    private AgentHamming192Plan? _nativeResizePlan;

    /// <summary>Create a stream bound to the current task's runtime.</summary>
    public AgentStreamSession(GameRuntime runtime, string observationProfile = AgentObservationProfile.Legacy)
    {
        _runtime = runtime;
        _observationProfile = AgentObservationProfile.Normalize(observationProfile);
        _snapshots = new AgentReadinessSnapshots(Global.Absolute(Path.Combine("User", "AgentDiagnostics", _sessionId)));
    }

    /// <summary>Run until cancellation or controller disconnect. Input is explicitly opt-in.</summary>
    public async Task RunAsync(string pipeName, bool enableInput, CancellationToken cancellationToken,
        Action? onListening = null)
    {
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
        var controller = new AgentActionController(input, enableInput, () => NowMs);
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
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(1000.0 / 30));
        AgentSourceFrame? previousSource = null;
        while (await timer.WaitForNextTickAsync(ct))
        {
            if (!_runtime.Window.IsAlive || _runtime.IsStopping) return;
            var capturedAt = NowMs;
            // A missing frame skips this publication tick; retry sleeps would add latency to later frames.
            using var captured = _runtime.Capture.Capture();
            var source = captured?.Frame;
            if (source is null || source.Empty())
            {
                controller.InvalidateWorld(NowMs, "capture_unavailable");
                continue;
            }
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
            var evidence = AgentWorldRecognizer.Recognize(source);
            var recognitionMs = Stopwatch.GetElapsedTime(recognitionStarted).TotalMilliseconds;
            var observation = new AgentObservation(frameId, capturedAt, source.Width, source.Height, evidence, recognitionMs, sourceFrame);
            // A negative frame releases input before RGB conversion or transport can delay it.
            var readiness = controller.RegisterFrame(observation, NowMs);
            // Inspect these same native pixels after the safety gate; never take another capture for motion hints.
            var motion = AgentMotionRecognizer.Recognize(source, readiness.Ready);
            _snapshots.Observe(source, observation, readiness);
            var resizeStarted = Stopwatch.GetTimestamp();
            var bytes = EncodeObservation(source, out var width, out var height, out var payloadBytes);
            CapturedFrame next;
            try
            {
                next = new CapturedFrame(observation, width, height, bytes, payloadBytes,
                    NowMs - capturedAt, readiness, motion)
                { ObservationResizeMs = Stopwatch.GetElapsedTime(resizeStarted).TotalMilliseconds };
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
        while (await timer.WaitForNextTickAsync(ct)) controller.Tick(NowMs);
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
            switch (request.Command)
            {
                case "frame":
                    CapturedFrame? frame;
                    lock (_frameGate) { frame = _latest; frame?.Retain(); }
                    try
                    {
                        var currentReadiness = controller.GetWorldReadinessSnapshot(out var frameNow);
                        if (frame is null)
                            await WriteAsync(pipe, new { type = "waiting", payloadBytes = 0, observationProfile = _observationProfile,
                                inputAvailable = input.IsAvailable && currentReadiness.Ready,
                                worldReadiness = currentReadiness, serverNowMs = frameNow,
                                motionEvidence = AgentMotionEvidence.Unavailable("capture_unavailable") }, null, ct);
                        else
                            await WriteAsync(pipe, new { type = "frame", frame.Observation.FrameId, frame.Observation.CapturedAtMs,
                                frame.Width, frame.Height, frame.Observation.SourceWidth, frame.Observation.SourceHeight,
                                pixelFormat = "rgb24", frame.PayloadBytes, frame.CaptureMs,
                                observationProfile = _observationProfile, frame.ObservationResizeMs,
                                inputAvailable = input.IsAvailable && currentReadiness.Ready && frame.Readiness.Ready &&
                                    frame.Readiness.Epoch == currentReadiness.Epoch,
                                worldReadiness = currentReadiness, frameWorldReadiness = frame.Readiness,
                                motionEvidence = MotionForReadiness(frame.MotionEvidence, frame.Readiness, currentReadiness),
                                frame.Observation.SourceFrame,
                                sourceTimestampKind = frame.Observation.SourceFrame is null ? "unknown" : "wgc_reported_compositor_qpc",
                                sourceFrameAgeMs = frame.Observation.SourceFrame is { } sourceTiming
                                    ? (double?)(frameNow - sourceTiming.FreshnessAtMs) : null,
                                reportedSourceFrameAgeMs = frame.Observation.SourceFrame is { } reportedTiming
                                    ? (double?)(frameNow - reportedTiming.CapturedAtMs) : null,
                                serverNowMs = frameNow,
                                receipts = controller.DrainReceipts(), droppedReceipts = controller.DroppedReceipts },
                                frame.Bytes.AsMemory(0, frame.PayloadBytes), ct);
                    }
                    finally { frame?.Release(); }
                    break;
                case "action":
                    var now = NowMs;
                    var reason = controller.Submit(request, now, out var acceptedAtMs);
                    await WriteAsync(pipe, new { type = reason is null ? "accepted" : "rejected", request.RequestId,
                        reason, receivedAtMs = now, acceptedAtMs = reason is null ? acceptedAtMs : (double?)null }, null, ct);
                    break;
                case "status":
                    var statusReadiness = controller.GetWorldReadinessSnapshot(out var statusNow);
                    await WriteAsync(pipe, new { type = "status", inputAvailable = input.IsAvailable && statusReadiness.Ready,
                        worldReadiness = statusReadiness,
                        diagnostics = _snapshots.Snapshot(),
                        serverNowMs = statusNow, receipts = controller.DrainReceipts(),
                        droppedReceipts = controller.DroppedReceipts }, null, ct);
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
                    var releasedAt = NowMs;
                    controller.Release(releasedAt);
                    // The acknowledgement is also the client's fresh-source barrier, so sample it after release finishes.
                    var releasedReadiness = controller.GetWorldReadinessSnapshot(out var releaseAcknowledgedAt);
                    await WriteAsync(pipe, new { type = "released", serverNowMs = releaseAcknowledgedAt,
                        worldReadiness = releasedReadiness,
                        receipts = controller.DrainReceipts(), droppedReceipts = controller.DroppedReceipts }, null, ct);
                    break;
                case "stop":
                    controller.Stop(NowMs, "client_stop");
                    await WriteAsync(pipe, new { type = "stopped", receipts = controller.DrainReceipts() }, null, ct);
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

    /// <summary>Declare the visual input gate and resumable release capability before accepting requests.</summary>
    private object CreateHello(bool enableInput) => new
    {
        type = "hello", version = 1, sessionId = _sessionId, ownerEpoch = _ownerEpoch,
        goalVersion = 1, inputEnabled = enableInput, supportsRelease = true,
        supportsStartBeforeMs = true, maxActionStartAgeMs = AgentActionController.MaxActionStartAgeMs,
        clockFrequency = 1000, allowedKeys = AgentActionController.AllowedKeys,
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
    };

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
        return JsonConvert.DeserializeObject<AgentRequest>(Encoding.UTF8.GetString(bytes), _json)
            ?? throw new InvalidDataException("Missing agent request.");
    }

    /// <summary>Write JSON followed by optional raw pixels; never base64-encode or persist control frames.</summary>
    private async Task WriteAsync(Stream stream, object header, ReadOnlyMemory<byte>? pixels, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        var bytes = Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(header, _json));
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
        /// <summary>Readiness derived from precisely this image, distinct from the current input gate.</summary>
        public AgentWorldReadiness Readiness { get; } = readiness;
        /// <summary>Keyboard-hint evidence derived from this publication's native source before downsampling.</summary>
        public AgentMotionEvidence MotionEvidence { get; } = motionEvidence;
        /// <summary>Acquire under the publication lock before reading the buffer.</summary>
        public void Retain() => Interlocked.Increment(ref _references);
        /// <summary>Recycle only after the publication slot and transport have both finished.</summary>
        public void Release()
        {
            if (Interlocked.Decrement(ref _references) == 0) ArrayPool<byte>.Shared.Return(Bytes);
        }
    }
}
