using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.AutoTrackPath;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Common.Map.Maps;
using BetterGenshinImpact.GameTask.Common.Map.Maps.Base;
using BetterGenshinImpact.GameTask.Common.Map.MiniMap;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.Instance;
using Fischless.GameCapture;
using OpenCvSharp;
using Vanara.PInvoke;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Existing teleport, local template matching and camera rotation, pinned to one owned RDP runtime.</summary>
internal sealed class NativeNavigationResetOperations : INavigationResetOperations, IAsyncDisposable
{
    /// <summary>The exact runtime and input backend acquired by TaskRunner.</summary>
    private readonly GameRuntime _runtime;
    /// <summary>Existing teleport configuration; the destination itself is never configurable.</summary>
    private readonly AllConfig _config;
    /// <summary>An owned query/synchronize handle pins identity without requesting game modification rights.</summary>
    private readonly Kernel32.SafeHPROCESS _game;
    /// <summary>Original PID, checked against both the held handle and bound window throughout the reset.</summary>
    private readonly int _gameProcessId;
    /// <summary>Owned cancellation combines task stop, runtime detach and loss of the pinned input target.</summary>
    private readonly CancellationTokenSource _stop;
    /// <summary>Monitor runs throughout native teleport's internal waits and cleanup.</summary>
    private readonly Task _guard;
    /// <summary>Task-local camera recognizer preserves confidence instead of silently using fallback yaw.</summary>
    private readonly MiniMapPreprocessor _yaw;
    /// <summary>Existing template map; serial TaskRunner ownership prevents another navigation task mutating it.</summary>
    private SceneBaseMapByTemplateMatch? _map;
    /// <summary>Fixed spawn converted once into image coordinates for local-only matching.</summary>
    private Point2f _anchor;
    /// <summary>Capture identity remains constant during one reset.</summary>
    private Guid? _captureEpoch;
    /// <summary>Last consumed native source; repeated cached copies never count as new measurements.</summary>
    private long _lastTimestamp, _lastAcquisition;
    /// <summary>Inputs must settle before a subsequently acquired frame can verify their effect.</summary>
    private long _inputBarrier;
    /// <summary>Guard failure is published explicitly rather than reported as a user cancellation.</summary>
    internal string? GuardError { get; private set; }
    /// <summary>The token used by all native operations, including teleport retries.</summary>
    internal CancellationToken Token => _stop.Token;

    /// <summary>Reject wrong role/session/ownership before starting any native operation.</summary>
    internal NativeNavigationResetOperations(GameRuntime runtime, AllConfig config, CancellationToken ct)
    {
        if (!GameTaskSessionScope.IsActive || runtime.Kind != GameRuntimeKind.Win32Window
            || !System.Windows.Forms.SystemInformation.TerminalServerSession
            || InstanceBootstrap.Current?.Context.InstanceType != BetterGiInstanceType.ChildSession)
            throw new InvalidOperationException("rdp_task_runtime_required");
        _runtime = runtime;
        _config = config;
        try
        {
            _gameProcessId = runtime.Window.ProcessId;
            if (!Kernel32.ProcessIdToSessionId(Kernel32.GetCurrentProcessId(), out var sessionId))
                throw new InvalidOperationException("game_session_unavailable");
            _game = OpenPinnedProcess(_gameProcessId, sessionId);
            if (!IsAvailable())
                throw new InvalidOperationException("game_target_unavailable");
            _yaw = new MiniMapPreprocessor();
            _stop = CancellationTokenSource.CreateLinkedTokenSource(ct, runtime.Stopping);
            _guard = GuardAsync();
        }
        catch { _game?.Dispose(); _yaw?.Dispose(); throw; }
    }

    /// <summary>Reuse the same foreground/backend guard as agent input, plus the pinned process handle.</summary>
    private bool IsAvailable() => IsPinnedProcessAlive(_game, _gameProcessId) && _runtime.Window.ProcessId == _gameProcessId
        && !_runtime.IsStopping && _runtime.Window.IsAlive && !_runtime.Window.IsMinimized
        && (!_runtime.Window.RequiresForeground || _runtime.Window.IsForeground)
        && ReferenceEquals(InputHub.Backend, _runtime.Input);

    /// <summary>Open only the query-limited and synchronization rights used for identity/session validation and exit detection.</summary>
    internal static Kernel32.SafeHPROCESS OpenPinnedProcess(int processId, uint expectedSessionId)
    {
        if (processId <= 0) throw new InvalidOperationException("game_target_unavailable");
        var handle = Kernel32.OpenProcess(new ACCESS_MASK(Kernel32.ProcessAccess.PROCESS_QUERY_LIMITED_INFORMATION)
            | ACCESS_MASK.SYNCHRONIZE, false, checked((uint)processId));
        try
        {
            if (handle.IsInvalid || Kernel32.GetProcessId(handle) != (uint)processId
                || !Kernel32.ProcessIdToSessionId((uint)processId, out var sessionId) || sessionId != expectedSessionId
                || !IsPinnedProcessAlive(handle, processId))
                throw new InvalidOperationException("game_target_unavailable");
            return handle;
        }
        catch { handle.Dispose(); throw; }
    }

    /// <summary>Zero-time native wait detects exit on the original process object, including after its PID could be reused.</summary>
    internal static bool IsPinnedProcessAlive(Kernel32.SafeHPROCESS handle, int processId) =>
        !handle.IsInvalid && !handle.IsClosed && Kernel32.GetProcessId(handle) == (uint)processId
        && Kernel32.WaitForSingleObject(handle, 0) == Kernel32.WAIT_STATUS.WAIT_TIMEOUT;

    /// <summary>Cancel promptly on target loss; native helpers retain their existing cooperative checks.</summary>
    private async Task GuardAsync()
    {
        try
        {
            while (!_stop.IsCancellationRequested)
            {
                if (!IsAvailable()) { GuardError = "game_target_lost"; _stop.Cancel(); return; }
                await Task.Delay(25, _stop.Token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (_stop.IsCancellationRequested) { }
        catch (Exception) { GuardError = "game_target_check_failed"; _stop.Cancel(); }
    }

    /// <summary>Verify shipped waypoint coordinates and current world before teleporting; warmup is cooperative.</summary>
    public Task PrepareAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var target = MapLazyAssets.Get().ScenesDic["Teyvat"].Points.Single(point => point.Id == "10");
        if (target.Type != "TeleportWaypoint"
            || Math.Abs((double)target.X - NavigationResetTask.IconX) > 0.001
            || Math.Abs((double)target.Y - NavigationResetTask.IconY) > 0.001
            || Math.Abs((double)target.TranX - NavigationResetTask.SpawnX) > 0.001
            || Math.Abs((double)target.TranY - NavigationResetTask.SpawnY) > 0.001)
            throw new InvalidOperationException("waypoint_profile_changed");
        _map = MapManager.GetMap("Teyvat", "TemplateMatch") as SceneBaseMapByTemplateMatch
            ?? throw new InvalidOperationException("local_template_map_unavailable");
        _map.WarmUp();
        _anchor = _map.ConvertGenshinMapCoordinatesToImageCoordinates(
            new Point2f((float)NavigationResetTask.SpawnX, (float)NavigationResetTask.SpawnY));
        if (!float.IsFinite(_anchor.X) || !float.IsFinite(_anchor.Y) || _anchor.X <= 0 || _anchor.Y <= 0)
            throw new InvalidOperationException("invalid_local_anchor");
        ct.ThrowIfCancellationRequested();
        using var frame = CaptureWorld();
        ValidateSource(frame.SourceInfo, Stopwatch.GetTimestamp());
        return Task.CompletedTask;
    }

    /// <summary>Native teleport returns an icon coordinate; only later measured spawn samples establish arrival.</summary>
    public async Task TeleportAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        await new TpTask(_runtime, _config, ct).Tp(NavigationResetTask.IconX, NavigationResetTask.IconY);
        ct.ThrowIfCancellationRequested();
        _inputBarrier = Stopwatch.GetTimestamp();
    }

    /// <summary>Use CameraRotateTask on the same confidently recognized frame; never drive on its hidden fallback.</summary>
    public async Task<bool> RotateAsync(double yaw, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 50; attempt++)
        {
            // Only the first acquisition after Tp may wait for its HUD transition, before any camera input.
            var sample = await MeasureAsync(yaw, ct, allowPostTeleportHudSettling: attempt == 0);
            if (NavigationResetTask.IsYawOriented(sample.YawDegrees, yaw)) return true;
            await DelayAsync(120, ct);
        }
        return false;
    }

    /// <inheritdoc />
    public Task<NavigationResetSample> ReadPoseAsync(CancellationToken ct) => MeasureAsync(null, ct);
    /// <inheritdoc />
    public Task DelayAsync(int milliseconds, CancellationToken ct) => Task.Delay(milliseconds, ct);
    /// <inheritdoc />
    public void ReleaseInput() { if (ReferenceEquals(InputHub.Backend, _runtime.Input)) InputHub.ReleaseAll(); }

    /// <summary>Share one bounded HUD/minimap/yaw settle deadline; only the initial post-teleport read may wait for missing HUD.</summary>
    private Task<NavigationResetSample> MeasureAsync(double? rotateYaw, CancellationToken ct,
        bool allowPostTeleportHudSettling = false) => NavigationResetPoseAcquisition.ReadAsync(
            token => MeasureOnceAsync(rotateYaw, allowPostTeleportHudSettling, token), DelayAsync, ct);

    /// <summary>Use one new native source for every evidence check; transient misses return before any camera input.</summary>
    private Task<NavigationResetPoseProbe> MeasureOnceAsync(double? rotateYaw, bool allowPostTeleportHudSettling,
        CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        using var frame = CaptureFrame();
        var source = ValidateSource(frame.SourceInfo, Stopwatch.GetTimestamp());
        // No source can cross a post-input barrier by being copied from the backend cache again.
        if (source.SourceTimestamp100ns <= _lastTimestamp || source.AcquiredAtStopwatchTicks <= _lastAcquisition
            || !SourceIsAfterBarrier(source, _inputBarrier))
            return Task.FromResult(new NavigationResetPoseProbe(null,
                $"awaiting_new_source; source={source.SourceTimestamp100ns}"));
        _lastTimestamp = source.SourceTimestamp100ns;
        _lastAcquisition = source.AcquiredAtStopwatchTicks;
        // Teleport's main-UI check is not a settled native HUD guarantee. Retry only a newly sourced missing HUD;
        // blocked/error evidence stays terminal, and no pose matching or camera input runs on an unready frame.
        if (WorldRetryReason(AgentWorldRecognizer.Recognize(frame.Frame), allowPostTeleportHudSettling,
                source.SourceTimestamp100ns) is { } worldReason)
            return Task.FromResult(new NavigationResetPoseProbe(null, worldReason));
        // CaptureContent owns a clone; the original native frame keeps independent ownership and metadata.
        using var bgr = new Mat();
        if (frame.Frame.Channels() == 4) Cv2.CvtColor(frame.Frame, bgr, ColorConversionCodes.BGRA2BGR);
        using var content = new CaptureContent((frame.Frame.Channels() == 4 ? bgr : frame.Frame).Clone(), 0, 0, _runtime.SystemInfo);
        using var minimap = new Mat(content.CaptureRectArea.SrcMat, MapAssets.Get(content.CaptureRectArea).MimiMapRect);
        var (yaw, confidence) = _yaw.PredictRotationWithConfidence(minimap);
        if (!NavigationResetTask.IsReliableYaw(yaw, confidence))
            return Task.FromResult(new NavigationResetPoseProbe(null, FormattableString.Invariant(
                $"yaw_unrecognized; source={source.SourceTimestamp100ns}; yaw={yaw:F3}; yawConfidence={confidence:F4}")));
        // Rank0 is the existing strict 0.99 threshold. A failed match must not reuse PrevSuccessResult.
        var position = _map!.GetMiniMapPosition(minimap, _anchor.X, _anchor.Y, 0);
        if (position == default)
            return Task.FromResult(new NavigationResetPoseProbe(null, FormattableString.Invariant(
                $"local_position_unrecognized; source={source.SourceTimestamp100ns}; yaw={yaw:F3}; yawConfidence={confidence:F4}")));
        var match = _map.PrevSuccessResult;
        var world = _map.ConvertImageCoordinatesToGenshinMapCoordinates(position)
            ?? throw new InvalidOperationException("local_position_unrecognized");
        var sample = new NavigationResetSample(world.X, world.Y, yaw, DateTimeOffset.UtcNow, source.CaptureEpoch,
            source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, match.Confidence, confidence, match.Layer?.LayerId ?? "");
        if (!NavigationResetTask.IsValidPose(sample)) throw new InvalidOperationException(FormattableString.Invariant(
            $"pose_evidence_rejected; source={source.SourceTimestamp100ns}; x={world.X:F3}; y={world.Y:F3}; layer={sample.LayerId}; confidence={match.Confidence:F4}"));
        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
        ValidateSource(source, Stopwatch.GetTimestamp()); // Recognition/target checks cannot renew the source's age.
        ct.ThrowIfCancellationRequested();
        if (rotateYaw is { } target && !NavigationResetTask.IsYawOriented(yaw, target))
        {
            // This exact frame already supplied reliable yaw; do not invoke the separate recognizer's fallback.
            new CameraRotateTask(_runtime, ct).RotateToApproach((float)target, (float)yaw);
            _inputBarrier = Stopwatch.GetTimestamp();
        }
        return Task.FromResult(new NavigationResetPoseProbe(sample, null));
    }

    /// <summary>Acquire one owned native frame only while the original runtime/process/input target remains available.</summary>
    private GameCaptureFrame CaptureFrame()
    {
        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
        return _runtime.Capture.Capture() ?? throw new InvalidOperationException("capture_unavailable");
    }

    /// <summary>Preparation remains strict; no readiness allowance can authorize teleport from a non-world frame.</summary>
    private GameCaptureFrame CaptureWorld()
    {
        var frame = CaptureFrame();
        try
        {
            WorldRetryReason(AgentWorldRecognizer.Recognize(frame.Frame), false, frame.SourceInfo?.SourceTimestamp100ns ?? 0);
            return frame;
        }
        catch { frame.Dispose(); throw; }
    }

    /// <summary>Only missing HUD during the initial no-input post-teleport acquisition is a bounded transient miss.</summary>
    internal static string? WorldRetryReason(AgentWorldEvidence evidence, bool allowPostTeleportHudSettling, long sourceTimestamp)
    {
        if (evidence == AgentWorldEvidence.WorldHud) return null;
        var reason = $"world_not_ready; evidence={evidence}; source={sourceTimestamp}";
        if (allowPostTeleportHudSettling && evidence == AgentWorldEvidence.HudMissing) return reason;
        throw new InvalidOperationException(reason);
    }

    /// <summary>Use the same conservative min(reported, first-acquisition) anchor as streaming; unknown sources fail closed.</summary>
    private GameCaptureSourceInfo ValidateSource(GameCaptureSourceInfo? source, long now)
    {
        if (!SourceIsFresh(source, now) || _captureEpoch is { } epoch && source!.CaptureEpoch != epoch)
            throw new InvalidOperationException("native_source_unavailable_or_stale");
        _captureEpoch ??= source!.CaptureEpoch;
        return source!;
    }

    /// <summary>Pure native-clock check; this bounds capture acquisition age, not game simulation/render age.</summary>
    internal static bool SourceIsFresh(GameCaptureSourceInfo? source, long now)
    {
        if (!Stopwatch.IsHighResolution || source is null || source.CaptureEpoch == Guid.Empty
            || source.SourceTimestamp100ns <= 0 || source.AcquiredAtStopwatchTicks <= 0
            || source.AcquiredAtStopwatchTicks > now) return false;
        var reportedSeconds = source.SourceTimestamp100ns / 10_000_000.0;
        var acquiredSeconds = (double)source.AcquiredAtStopwatchTicks / Stopwatch.Frequency;
        var ageMs = ((double)now / Stopwatch.Frequency - Math.Min(reportedSeconds, acquiredSeconds)) * 1000;
        return double.IsFinite(ageMs) && ageMs is >= 0 and <= 500;
    }

    /// <summary>Both native timing signals must cross the settled-input cutoff, including delayed acquisition of old pixels.</summary>
    internal static bool SourceIsAfterBarrier(GameCaptureSourceInfo source, long barrier) =>
        Stopwatch.GetElapsedTime(barrier, source.AcquiredAtStopwatchTicks).TotalMilliseconds >= 80
        && (source.SourceTimestamp100ns / 10_000_000.0 - (double)barrier / Stopwatch.Frequency) * 1000 >= 80;

    /// <summary>Drain the identity watchdog and release task-local native recognizer resources.</summary>
    public async ValueTask DisposeAsync()
    {
        _stop.Cancel();
        try { await _guard.ConfigureAwait(false); }
        finally { _stop.Dispose(); _game.Dispose(); _yaw.Dispose(); }
    }
}
