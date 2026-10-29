using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationReset;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>One bounded, same-stream inspection at the surveyed junction. The normal action controller never grants map input.</summary>
internal sealed class AgentMapInspection(string sessionId, string ownerEpoch, long originTicks,
    AgentActionController controller, IMapInspectionInput input, Func<Mat, bool>? recognizeMap = null)
{
    /// <summary>Owned by this stream only; capture, reads and terminal cancellation share the same state.</summary>
    private readonly object _gate = new();
    /// <summary>Interrupt a key hold before the cancellation caller waits for the capture lock.</summary>
    private readonly CancellationTokenSource _interrupt = new();
    /// <summary>Strictly bounded lists retain three junction, two map and three return sources.</summary>
    private readonly List<MapSource> _before = [], _map = [], _returned = [];
    /// <summary>At most two input attempts and three full-resolution PNGs belong to this operation.</summary>
    private readonly List<MapPulse> _inputs = [];
    private readonly Dictionary<long, byte[]> _images = [];
    /// <summary>Three bounded native pixel copies at most. PNG compression occurs only after terminal release.</summary>
    private readonly List<(List<MapSource> Rows, long Frame, MatType Type, byte[] Bytes)> _originals = [];
    /// <summary>Never clear a used request or regrant movement on failure.</summary>
    private string? _requestId, _reason, _epoch, _priorEvidenceSha256;
    private string _phase = "idle";
    private long _startedTicks, _deadlineTicks, _lastStamp, _lastFrame, _barrier;
    private double _lastAcquisition = -1;
    private int _width, _height;
    /// <summary>Count every ordinary action rejected by the native map fence, independently of dispatched input.</summary>
    private int _ordinaryRequestsWhileFenced;
    /// <summary>Expired captures reset only their uncommitted observation streak. None can authorize dispatch.</summary>
    private int _staleCandidates;
    private long _lastStaleFrame;
    private double _maxDiscardedAgeMs;
    /// <summary>Actual native input telemetry at admission and final release.</summary>
    private AgentExecutionContext? _initial, _final;
    private AgentWorldReadiness? _finalReadiness;
    private double _finalReleaseAtMs;

    /// <summary>Read on the capture and input loops without allocating per observation.</summary>
    internal bool Pending => Volatile.Read(ref _phase) is "awaitJunction" or "awaitMap" or "awaitRecoveryMap" or "awaitWorld";
    /// <summary>Failure keeps all ordinary actions fenced for this lease.</summary>
    internal bool BlocksMovement => Volatile.Read(ref _phase) is not ("idle" or "completed");
    /// <summary>Serialize an ordinary proposal's admission decision with the final world release.</summary>
    internal bool RejectWalkingProposal()
    {
        if (!BlocksMovement) return false;
        lock (_gate)
        {
            if (!BlocksMovement) return false;
            _ordinaryRequestsWhileFenced++;
            return true;
        }
    }
    /// <summary>Pin one live, idle stream before accumulating its post-request sources.</summary>
    internal void Start(string id, bool permitted, bool recovery = false, string? priorEvidenceSha256 = null)
    {
        lock (_gate)
        {
            if (_requestId is not null || !permitted || !Guid.TryParseExact(id, "N", out var parsed) || parsed.ToString("N") != id)
                throw new InvalidOperationException("map_inspection_unavailable");
            if (recovery ? priorEvidenceSha256 is not { Length: 64 } || !priorEvidenceSha256.All(char.IsAsciiHexDigitLower)
                         : priorEvidenceSha256 is not null)
                throw new InvalidOperationException("map_recovery_proof_identity");
            controller.WithIdleMapInput(() =>
            {
                if (!input.MapTargetReady) throw new InvalidOperationException("map_input_target_unavailable");
                _initial = controller.GetExecutionContextSnapshot();
                if (!SoftwareReleased(_initial))
                    throw new InvalidOperationException("map_prior_release_required");
                _requestId = id;
                _priorEvidenceSha256 = priorEvidenceSha256;
                _barrier = _startedTicks = Stopwatch.GetTimestamp();
                _deadlineTicks = checked(_startedTicks + 12 * Stopwatch.Frequency);
                Volatile.Write(ref _phase, recovery ? "awaitRecoveryMap" : "awaitJunction");
            });
        }
    }

    /// <summary>Fail even if no further capture arrives. No input is attempted by the watchdog.</summary>
    internal void Watch()
    {
        if (!Pending) return;
        lock (_gate)
            if (Pending && (Stopwatch.GetTimestamp() >= _deadlineTicks || !input.MapTargetReady))
                End("failed", "map_deadline_or_target_lost");
    }

    /// <summary>A stop, release or disconnect immediately revokes any pending map input.</summary>
    internal void Cancel()
    {
        if (!Pending) return;
        _interrupt.Cancel();
        lock (_gate) { if (Pending) End("cancelled", "map_interrupted"); }
    }

    /// <summary>Only original WGC pixels from this capture turn may authorize a fixed UI key.</summary>
    internal void Observe(Mat pixels, AgentObservation observation, AgentWorldReadiness readiness,
        AgentMotionEvidence motion, AgentNavigationPose? pose, CancellationToken ct)
    {
        lock (_gate)
        {
            if (!Pending) return;
            try
            {
                Check(ct);
                var src = observation.SourceFrame ?? throw new InvalidOperationException("map_wgc_source_required");
                if (_epoch is null && src.FreshnessAtMs < Milliseconds(_startedTicks)) return; // A capture in flight before admission.
                if (_epoch is null) { _epoch = src.CaptureEpoch; _width = pixels.Width; _height = pixels.Height; }
                if (_epoch != src.CaptureEpoch || _width != pixels.Width || _height != pixels.Height ||
                    _width is < 1 or > 1920 || _height is < 1 or > 1080 || observation.FrameId <= _lastFrame ||
                    src.Timestamp100ns <= _lastStamp || src.AcquiredAtMs <= _lastAcquisition)
                    throw new InvalidOperationException("map_source_discontinuity");
                _lastFrame = observation.FrameId; _lastStamp = src.Timestamp100ns; _lastAcquisition = src.AcquiredAtMs;
                bool mapPhase = _phase is "awaitMap" or "awaitRecoveryMap";
                var rows = mapPhase ? _map : _phase == "awaitWorld" ? _returned : _before;
                if (DiscardExpired(rows, src, Stopwatch.GetTimestamp())) return;
                if (src.FreshnessAtMs < Milliseconds(_barrier) + (_inputs.Count == 0 && _priorEvidenceSha256 is null ? 0 : 80)) return;
                if (observation.WorldEvidence is AgentWorldEvidence.BlockingUi or AgentWorldEvidence.RecognitionFailed)
                    throw new InvalidOperationException("map_blocking_or_unrecognized_ui");
                var knownMap = mapPhase && observation.WorldEvidence == AgentWorldEvidence.HudMissing && !readiness.Ready &&
                    (recognizeMap ?? NavigationResetMapRecovery.RecognizeKnownMap)(pixels);
                Check(ct);
                if (DiscardExpired(rows, src, Stopwatch.GetTimestamp())) return;
                var row = new MapSource(observation.FrameId, pixels.Width, pixels.Height, src.CaptureEpoch, src.Timestamp100ns,
                    src.AcquiredAtMs, readiness, pose, motion, knownMap, null);
                if (mapPhase ? !knownMap : !Junction(row) || rows.Any(v => !Near(v, row)) ||
                    _phase == "awaitWorld" && (_before.Count > 0 && !Near(_before[^1], row) ||
                        readiness.Epoch < _map[^1].WorldReadiness.Epoch ||
                        _before.Count > 0 && readiness.Epoch == _before[^1].WorldReadiness.Epoch))
                { rows.Clear(); return; }
                int spacing = mapPhase ? 30 : 80;
                if (rows.Count != 0 && (row.Timestamp100ns - rows[^1].Timestamp100ns < spacing * 10_000 ||
                    row.AcquiredAtMs - rows[^1].AcquiredAtMs < spacing)) return;
                rows.Add(row);
                if (rows.Count != (mapPhase ? 2 : 3)) return;

                // The source Mat remains owned until Observe returns. Keep its exact pixels even on a partial input failure.
                var attempts = _inputs.Count;
                try { if (_phase != "awaitWorld" && !TryPulse(_phase == "awaitJunction", row, rows, src, ct)) return; }
                finally
                {
                    if (_phase == "awaitWorld" || attempts < _inputs.Count) RetainOriginal(pixels, rows, row.FrameId);
                }
                Check(ct);
                if (_phase == "awaitWorld") End("completed", null);
                else Volatile.Write(ref _phase, mapPhase ? "awaitWorld" : "awaitMap");
            }
            catch (Exception e) { End(ct.IsCancellationRequested || _interrupt.IsCancellationRequested ? "cancelled" : "failed", e.Message); }
        }
    }

    /// <summary>Same-clock source freshness is bounded by both first acquisition and compositor time.</summary>
    private double Milliseconds(long ticks) => (ticks - originTicks) * 1000.0 / Stopwatch.Frequency;
    /// <summary>Discard late observation-only candidates, including those whose recognition used up the original budget.</summary>
    private bool DiscardExpired(List<MapSource> rows, AgentSourceFrame src, long now)
    {
        double age = Milliseconds(now) - src.FreshnessAtMs;
        if (!double.IsFinite(age) || age < 0) throw new InvalidOperationException("map_invalid_source_clock");
        if (age <= 150) return false;
        rows.Clear();
        _staleCandidates++;
        _lastStaleFrame = _lastFrame;
        _maxDiscardedAgeMs = Math.Max(_maxDiscardedAgeMs, age);
        return true;
    }
    /// <summary>Bound absolute position, confidence and same-frame evidence before dispatch or resumption.</summary>
    internal static bool Junction(MapSource r) => r.WorldReadiness.Ready && r.WorldReadiness.SourceFrameId == r.FrameId &&
        r.MotionEvidence.Status == AgentMotionStatus.Normal && r.MotionEvidence.SpaceKeyMatched == false &&
        r.NavigationPose is { State: "valid", LayerId: "City_102", X: double x, Y: double y, YawDegrees: >= 0 and < 360,
            PositionConfidence: >= .99 and <= 1, YawConfidence: >= .2 and <= 1 } p && p.FrameId == r.FrameId &&
        Math.Pow(x + 846.30078125, 2) + Math.Pow(y - 2261.13671875, 2) <= 4;
    /// <summary>Three independent poses must agree in position and circular camera heading.</summary>
    internal static bool Near(MapSource a, MapSource b)
    {
        var p = a.NavigationPose!; var q = b.NavigationPose!;
        return Math.Pow(p.X!.Value - q.X!.Value, 2) + Math.Pow(p.Y!.Value - q.Y!.Value, 2) <= 2.25 &&
            Math.Abs((p.YawDegrees!.Value - q.YawDegrees!.Value + 540) % 360 - 180) <= 3;
    }
    /// <summary>Check cancellation, original HWND/backend and the whole-operation deadline.</summary>
    private void Check(CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        _interrupt.Token.ThrowIfCancellationRequested();
        if (!input.MapTargetReady || Stopwatch.GetTimestamp() >= _deadlineTicks)
            throw new InvalidOperationException("map_deadline_or_target_lost");
    }
    /// <summary>Consume each authority once; even partial failures retain a row and attempt a targeted key-up.</summary>
    private bool TryPulse(bool open, MapSource frame, List<MapSource> rows, AgentSourceFrame src, CancellationToken ct)
    {
        var row = new MapPulse(open ? "openMap" : "closeMap", open ? "M" : "ESCAPE", frame.FrameId);
        controller.WithIdleMapInput(() =>
        {
            var current = controller.GetWorldReadinessSnapshot(out _);
            Check(ct);
            var now = Stopwatch.GetTimestamp();
            if (now >= _deadlineTicks) throw new InvalidOperationException("map_deadline_or_target_lost");
            if (DiscardExpired(rows, src, now)) return;
            if (current.Ready != open || current.Epoch != frame.WorldReadiness.Epoch || current.SourceFrameId != frame.FrameId)
                throw new InvalidOperationException("map_dispatch_authority_expired");
            _inputs.Add(row); // An attempt is consumed only after the final original-clock and target checks succeed.
            row.RequestedTicks = now;
            bool pressed = false;
            try
            {
                input.MapKey(open, true);
                pressed = true;
                using var hold = CancellationTokenSource.CreateLinkedTokenSource(ct, _interrupt.Token);
                hold.Token.WaitHandle.WaitOne(50);
            }
            finally
            {
                input.MapKey(open, false);
                _barrier = row.ReleasedTicks = Stopwatch.GetTimestamp();
                row.Outcome = pressed ? "released" : "down_failed_up_returned";
            }
        });
        return row.RequestedTicks != 0;
    }

    /// <summary>Copy the borrowed, potentially strided, full-resolution source. Capture never waits for PNG compression.</summary>
    private void RetainOriginal(Mat pixels, List<MapSource> rows, long frame)
    {
        var type = pixels.Type();
        if (type != MatType.CV_8UC3 && type != MatType.CV_8UC4 || _originals.Count >= 3)
            throw new InvalidOperationException("map_original_pixel_type");
        var stride = checked(pixels.Width * pixels.Channels());
        var bytes = new byte[checked(stride * pixels.Height)];
        if (pixels.IsContinuous()) Marshal.Copy(pixels.Data, bytes, 0, bytes.Length);
        else for (int y = 0; y < pixels.Height; y++) Marshal.Copy(pixels.Ptr(y), bytes, y * stride, stride);
        _originals.Add((rows, frame, type, bytes));
    }

    /// <summary>Compress retained bytes on the transport reader after final release, outside the game-input authority window.</summary>
    private void SealImages()
    {
        if (Pending || _originals.Count == 0) return;
        foreach (var original in _originals)
        {
            using var mat = Mat.FromPixelData(_height, _width, original.Type, original.Bytes);
            var png = mat.ImEncode(".png", [new ImageEncodingParam(ImwriteFlags.PngCompression, 1)]);
            if (png.Length is < 1 or > 32 * 1024 * 1024) throw new InvalidOperationException("map_image_size");
            _images[original.Frame] = png;
            original.Rows[^1] = original.Rows[^1] with { Sha256 = Convert.ToHexString(SHA256.HashData(png)).ToLowerInvariant() };
        }
        _originals.Clear();
    }
    /// <summary>Completion also requires an independent explicit software release from the original controller.</summary>
    private void End(string phase, string? reason)
    {
        try
        {
            _finalReadiness = controller.ReleaseAndGetSnapshot(Milliseconds(Stopwatch.GetTimestamp()), out _finalReleaseAtMs, out _final);
            if (!SoftwareReleased(_final))
                throw new InvalidOperationException("map_terminal_release_uncertain");
            if (phase == "completed" && _ordinaryRequestsWhileFenced != 0)
                throw new InvalidOperationException("map_unexpected_ordinary_proposal");
        }
        catch (Exception e) { phase = "failed"; reason = e.Message; }
        _reason = reason is { Length: > 200 } ? reason[..200] : reason;
        Volatile.Write(ref _phase, phase);
    }
    /// <summary>Aggregate key release is deliberately software-only and latches physical uncertainty in native telemetry.</summary>
    private static bool SoftwareReleased(AgentExecutionContext state) => state.TelemetryComplete && state.Active is null &&
        state.TrackedState.HeldKeys.Length == 0 && state.TrackedState.ReleaseOutcome == "returned_unverified" &&
        state.LastInputEvent?.Call is { Operation: "releaseAll", Stage: "returned_unverified", Error: null };
    /// <summary>Snapshot the immutable proof prefix independently of subsequent transport writes.</summary>
    internal object Status(string id)
    {
        lock (_gate)
        {
            RequireId(id);
            SealImages();
            return new { version = 1, requestId = id, sessionId, ownerEpoch, phase = _phase, reason = _reason,
                mode = _priorEvidenceSha256 is null ? "inspection" : "recovery", priorEvidenceSha256 = _priorEvidenceSha256,
                gameProcessId = input.GameProcessId, gameWindowHandle = input.GameWindowHandle,
                staleCandidates = _staleCandidates, lastStaleFrame = _lastStaleFrame, maxDiscardedAgeMs = _maxDiscardedAgeMs,
                originTicks, frequency = Stopwatch.Frequency, startedTicks = _startedTicks, deadlineTicks = _deadlineTicks,
                before = _before.ToArray(), map = _map.ToArray(), returned = _returned.ToArray(), inputs = _inputs.ToArray(),
                initialExecutionContext = _initial, finalExecutionContext = _final, finalReadiness = _finalReadiness,
                finalReleaseAtMs = _finalReleaseAtMs, ordinaryRequestsWhileFenced = _ordinaryRequestsWhileFenced,
                pendingActions = _phase == "completed" ? 0 : (int?)null };
        }
    }
    /// <summary>Only the three retained original PNGs from this request can be fetched.</summary>
    internal byte[] Image(string id, long frame)
    {
        lock (_gate)
        {
            RequireId(id);
            SealImages();
            return _images.TryGetValue(frame, out var bytes) ? bytes : throw new InvalidOperationException("map_image_unavailable");
        }
    }
    /// <summary>Require the original operation identity, including on reads after failure.</summary>
    private void RequireId(string id)
    {
        if (_requestId is null || _requestId != id) throw new InvalidOperationException("map_request_mismatch");
    }
    /// <summary>Metadata from the exact original image used by the native recognition stage.</summary>
    internal sealed record MapSource(long FrameId, int Width, int Height, string CaptureEpoch, long Timestamp100ns,
        double AcquiredAtMs, AgentWorldReadiness WorldReadiness, AgentNavigationPose? NavigationPose,
        AgentMotionEvidence MotionEvidence, bool KnownMap, string? Sha256);
    /// <summary>Before/after clocks bracket the actual fixed HWND input calls; failures never earn successful inspection.</summary>
    private sealed class MapPulse(string action, string key, long frameId)
    {
        public string Action { get; } = action;
        public string Key { get; } = key;
        public long FrameId { get; } = frameId;
        public long RequestedTicks { get; set; }
        public long ReleasedTicks { get; set; }
        public string Outcome { get; set; } = "attempted";
    }
}

/// <summary>Only the fixed map and Escape transitions are expressible by the original native target.</summary>
internal interface IMapInspectionInput
{
    /// <summary>Already-bound game process and handle from the owning runtime; neither is supplied by the client.</summary>
    int GameProcessId { get; }
    long GameWindowHandle { get; }
    /// <summary>Current HWND, capture, foreground and configured binding all match this lease.</summary>
    bool MapTargetReady { get; }
    /// <summary>Dispatch one targeted key transition, independently checking the HWND owner before the call.</summary>
    void MapKey(bool open, bool down);
}
