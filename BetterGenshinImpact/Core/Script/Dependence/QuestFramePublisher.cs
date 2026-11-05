using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;
using OpenCvSharp;

namespace BetterGenshinImpact.Core.Script.Dependence;

/// <summary>One demand-driven, source-timestamped RGB192 publisher sharing the script's existing capture backend.</summary>
internal sealed class QuestFramePublisher(GameRuntime runtime, string session, int windowsSessionId, int gameProcessId)
{
    /// <summary>One RGB buffer is reused after the previous reply has finished writing.</summary>
    private readonly byte[] _rgb = new byte[AgentHamming192Plan.OutputBytes];
    /// <summary>Resize plan for the latest native source dimensions.</summary>
    private AgentHamming192Plan? _plan;
    /// <summary>Highest published identity and timestamp of a WGC source or desktop acquisition.</summary>
    private (Guid Epoch, long Id)? _lastSource;
    /// <summary>Lifetime epoch for capture providers without their own source generation.</summary>
    private readonly string _publisherEpoch = Guid.NewGuid().ToString("N");
    /// <summary>Monotonically increasing successful frame number, including across client reconnects.</summary>
    private long _frameId;
    /// <summary>Capture request timing limits even a client which repeatedly reconnects.</summary>
    private long _lastPull;

    /// <summary>Wait for the 30 Hz ceiling, then acquire exactly one native frame. No queue, recording or input is involved.</summary>
    internal async Task<(object Header, ReadOnlyMemory<byte> Pixels)> NextAsync(CancellationToken token)
    {
        if (_lastPull != 0)
        {
            var remaining = TimeSpan.FromMilliseconds(1000d / 30) - Stopwatch.GetElapsedTime(_lastPull);
            if (remaining > TimeSpan.Zero) await Task.Delay(remaining, token).ConfigureAwait(false);
        }
        token.ThrowIfCancellationRequested();
        _lastPull = Stopwatch.GetTimestamp();
        if (runtime.IsStopping || !runtime.Window.IsAlive || runtime.Window.ProcessId != gameProcessId ||
            !runtime.Capture.IsCapturing || runtime.Window.IsMinimized || runtime.IsDesktopCapture && !runtime.Window.IsForeground)
            return Unavailable("game_unavailable");

        // Use this task's provider without starting or stopping another capture session.
        using var captured = runtime.Capture.Capture();
        if (captured is null || captured.Frame.Empty()) return Unavailable("frame_unavailable");
        token.ThrowIfCancellationRequested();
        var now = Stopwatch.GetTimestamp();
        var timing = SourceTiming(captured.SourceInfo, captured.HostSnapshotInfo, runtime.IsDesktopCapture, _lastPull, now);
        if (timing is null) return Unavailable("invalid_source_time");
        var (kind, ageMs, source) = timing.Value;
        if (source is { } current && _lastSource is { } previous && current.Epoch == previous.Epoch && current.Id <= previous.Id)
            return Unavailable("source_not_advanced");
        if (ageMs > 500) return Unavailable("source_expired");
        long capturedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - (long)Math.Ceiling(ageMs);
        var mat = captured.Frame;
        if (mat.Type() != MatType.CV_8UC3 && mat.Type() != MatType.CV_8UC4 ||
            mat.Width > AgentHamming192Plan.MaximumSourceDimension || mat.Height > AgentHamming192Plan.MaximumSourceDimension)
            return Unavailable("unsupported_source_image");
        Resize(mat);
        token.ThrowIfCancellationRequested();
        _lastSource = source;
        object header = new { type = "frame", protocolVersion = 1, session, processId = Environment.ProcessId,
            windowsSessionId, gameProcessId, frameId = ++_frameId, capturedAtUnixMs, sourceKind = kind,
            sourceEpoch = source?.Epoch.ToString("N") ?? _publisherEpoch, captureBackend = runtime.Capture.GetType().Name,
            sourceWidth = mat.Width, sourceHeight = mat.Height, width = 192, height = 192, pixelFormat = "rgb24",
            observationProfile = AgentObservationProfile.P2PNativeHamming192, payloadBytes = _rgb.Length };
        return (header, _rgb);
    }

    /// <summary>Map immutable WGC or DesktopDC evidence to source age. Other captures use their own request start.</summary>
    internal static (string Kind, double AgeMs, (Guid Epoch, long Id)? Source)? SourceTiming(
        GameCaptureSourceInfo? wgc, GameCaptureHostSnapshotInfo? host, bool desktop, long requested, long now)
    {
        if (requested <= 0 || now < requested) return null;
        if (desktop)
        {
            if (host is null || wgc is not null || host.CaptureEpoch == Guid.Empty || host.SnapshotId <= 0 ||
                host.ClockFrequency != Stopwatch.Frequency || host.StartedAtStopwatchTicks <= 0 ||
                host.CompletedAtStopwatchTicks < host.StartedAtStopwatchTicks || host.CompletedAtStopwatchTicks > now) return null;
            return ("desktopdc-host", Stopwatch.GetElapsedTime(host.StartedAtStopwatchTicks, now).TotalMilliseconds,
                (host.CaptureEpoch, host.SnapshotId));
        }
        if (host is not null) return null;
        if (wgc is null) return ("capture-request", Stopwatch.GetElapsedTime(requested, now).TotalMilliseconds, null);
        if (!Stopwatch.IsHighResolution || wgc.CaptureEpoch == Guid.Empty || wgc.SourceTimestamp100ns <= 0 ||
            wgc.AcquiredAtStopwatchTicks <= 0 || wgc.AcquiredAtStopwatchTicks > now) return null;
        // The compositor and Stopwatch use the same QPC epoch; retain the older of render time and first acquisition.
        var renderAge = (double)((Int128)now * TimeSpan.TicksPerSecond - (Int128)wgc.SourceTimestamp100ns * Stopwatch.Frequency)
            / Stopwatch.Frequency / TimeSpan.TicksPerMillisecond;
        return ("wgc-source", Math.Max(renderAge, Stopwatch.GetElapsedTime(wgc.AcquiredAtStopwatchTicks, now).TotalMilliseconds),
            (wgc.CaptureEpoch, wgc.SourceTimestamp100ns));
    }

    /// <summary>Apply the same native Hamming resampler and RGB24 layout used by the Open P2P stream.</summary>
    private unsafe void Resize(Mat mat)
    {
        if (_plan is null || _plan.Width != mat.Width || _plan.Height != mat.Height)
            _plan = new AgentHamming192Plan(mat.Width, mat.Height);
        int channels = mat.Channels(), stride = checked((int)mat.Step());
        int count = checked((mat.Height - 1) * stride + mat.Width * channels);
        _plan.ResizeInto(new ReadOnlySpan<byte>((void*)mat.Data, count), stride, channels, true, _rgb);
    }

    /// <summary>Missing or stale captures produce zero payload bytes and no new frame number.</summary>
    private (object, ReadOnlyMemory<byte>) Unavailable(string reason) =>
        (new { type = "unavailable", protocolVersion = 1, session, processId = Environment.ProcessId,
            windowsSessionId, gameProcessId, reason, payloadBytes = 0 }, ReadOnlyMemory<byte>.Empty);
}
