using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Pipes;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.Instance;
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
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    /// <summary>Latest-only publication; byte arrays are immutable after publication.</summary>
    private CapturedFrame? _latest;
    /// <summary>Protects publication leases so a buffer cannot be recycled while transport reads it.</summary>
    private readonly object _frameGate = new();
    /// <summary>Monotonic observation sequence.</summary>
    private long _frameId;

    /// <summary>Create a stream bound to the current task's runtime.</summary>
    public AgentStreamSession(GameRuntime runtime) => _runtime = runtime;

    /// <summary>Run until cancellation or controller disconnect. Input is explicitly opt-in.</summary>
    public async Task RunAsync(string pipeName, bool enableInput, CancellationToken cancellationToken)
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
        var controller = new AgentActionController(input, enableInput);
        var captureTask = Task.Run(() => CaptureLoopAsync(controller, stop.Token), stop.Token);
        var inputTask = Task.Run(() => InputLoopAsync(controller, stop.Token), stop.Token);
        var transportTask = ServeAsync(pipe, controller, input, enableInput, stop.Token);
        try
        {
            var finished = await Task.WhenAny(captureTask, inputTask, transportTask);
            await finished;
        }
        finally
        {
            // Input release precedes waiting for any native capture or pipe operation to unwind.
            stop.Cancel();
            controller.Stop(_clock.Elapsed.TotalMilliseconds, "session_ended");
            await pipe.DisposeAsync();
            try { await Task.WhenAll(captureTask, inputTask, transportTask); }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
            finally
            {
                lock (_frameGate) { _latest?.Release(); _latest = null; }
            }
        }
    }

    /// <summary>Capture and downsample independently of disk, OCR, inference and transport writes.</summary>
    private async Task CaptureLoopAsync(AgentActionController controller, CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(1000.0 / 30));
        while (await timer.WaitForNextTickAsync(ct))
        {
            if (!_runtime.Window.IsAlive || _runtime.IsStopping) return;
            if (_runtime.Window.IsMinimized || !_runtime.Window.IsForeground) continue;
            var capturedAt = _clock.Elapsed.TotalMilliseconds;
            // A missing frame skips this publication tick; retry sleeps would add latency to later frames.
            using var captured = _runtime.Capture.Capture();
            var source = captured?.Frame;
            if (source is null || source.Empty()) continue;
            var scale = Math.Min(1.0, Math.Min(640.0 / source.Width, 360.0 / source.Height));
            using var small = new Mat();
            Cv2.Resize(source, small, new Size(Math.Max(1, (int)(source.Width * scale)),
                Math.Max(1, (int)(source.Height * scale))), interpolation: InterpolationFlags.Area);
            using var rgb = new Mat();
            Cv2.CvtColor(small, rgb, small.Channels() == 4 ? ColorConversionCodes.BGRA2RGB : ColorConversionCodes.BGR2RGB);
            var payloadBytes = checked(rgb.Width * rgb.Height * 3);
            var bytes = ArrayPool<byte>.Shared.Rent(payloadBytes);
            Marshal.Copy(rgb.Data, bytes, 0, payloadBytes);
            var observation = new AgentObservation(Interlocked.Increment(ref _frameId), capturedAt, source.Width, source.Height);
            controller.RegisterFrame(observation);
            lock (_frameGate)
            {
                var previous = _latest;
                _latest = new CapturedFrame(observation, rgb.Width, rgb.Height, bytes, payloadBytes,
                    _clock.Elapsed.TotalMilliseconds - capturedAt);
                previous?.Release();
            }
        }
    }

    /// <summary>Observe focus/deadline changes even when the model or socket stops responding.</summary>
    private async Task InputLoopAsync(AgentActionController controller, CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(10));
        while (await timer.WaitForNextTickAsync(ct)) controller.Tick(_clock.Elapsed.TotalMilliseconds);
    }

    /// <summary>Serve one same-user controller; disconnect ends this task rather than transferring the lease.</summary>
    private async Task ServeAsync(NamedPipeServerStream pipe, AgentActionController controller,
        RuntimeAgentInput input, bool enableInput, CancellationToken ct)
    {
        await pipe.WaitForConnectionAsync(ct);
        await WriteAsync(pipe, new { type = "hello", version = 1, sessionId = _sessionId, ownerEpoch = _ownerEpoch,
            goalVersion = 1, inputEnabled = enableInput, clockFrequency = 1000, allowedKeys = AgentActionController.AllowedKeys,
            clock = "monotonic milliseconds since session start", captureTimestampKind = "host_capture_request",
            widthLimit = 640, heightLimit = 360 }, null, ct);
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
                        if (frame is null)
                            await WriteAsync(pipe, new { type = "waiting", payloadBytes = 0, inputAvailable = input.IsAvailable }, null, ct);
                        else
                            await WriteAsync(pipe, new { type = "frame", frame.Observation.FrameId, frame.Observation.CapturedAtMs,
                                frame.Width, frame.Height, frame.Observation.SourceWidth, frame.Observation.SourceHeight,
                                pixelFormat = "rgb24", frame.PayloadBytes, frame.CaptureMs,
                                inputAvailable = input.IsAvailable, serverNowMs = _clock.Elapsed.TotalMilliseconds,
                                receipts = controller.DrainReceipts(), droppedReceipts = controller.DroppedReceipts },
                                frame.Bytes.AsMemory(0, frame.PayloadBytes), ct);
                    }
                    finally { frame?.Release(); }
                    break;
                case "action":
                    var now = _clock.Elapsed.TotalMilliseconds;
                    var reason = controller.Submit(request, now);
                    await WriteAsync(pipe, new { type = reason is null ? "accepted" : "rejected", request.RequestId,
                        reason, receivedAtMs = now }, null, ct);
                    break;
                case "status":
                    await WriteAsync(pipe, new { type = "status", inputAvailable = input.IsAvailable,
                        serverNowMs = _clock.Elapsed.TotalMilliseconds, receipts = controller.DrainReceipts(),
                        droppedReceipts = controller.DroppedReceipts }, null, ct);
                    break;
                case "stop":
                    controller.Stop(_clock.Elapsed.TotalMilliseconds, "client_stop");
                    await WriteAsync(pipe, new { type = "stopped", receipts = controller.DrainReceipts() }, null, ct);
                    return;
                default:
                    await WriteAsync(pipe, new { type = "rejected", reason = "unknown_command" }, null, ct);
                    break;
            }
        }
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
    private sealed class CapturedFrame(AgentObservation observation, int width, int height, byte[] bytes, int payloadBytes, double captureMs)
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
        /// <summary>Acquire under the publication lock before reading the buffer.</summary>
        public void Retain() => Interlocked.Increment(ref _references);
        /// <summary>Recycle only after the publication slot and transport have both finished.</summary>
        public void Release()
        {
            if (Interlocked.Decrement(ref _references) == 0) ArrayPool<byte>.Shared.Return(Bytes);
        }
    }
}
