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
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;
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
    /// <summary>At most one terminal source/capture diagnostic is logged for this reset; never shared with another capture caller.</summary>
    private bool _sourceDiagnosticLogged;
    /// <summary>The first discarded stale pose source is retained independently of any later terminal diagnostic.</summary>
    private bool _transientSourceDiagnosticLogged;
    /// <summary>Run-local pose probe ordinal distinguishes later orientation/verification from initial HUD settling.</summary>
    private int _poseAcquisitionOrdinal;
    /// <summary>Immutable requested policy; actual suppression is activated only after awaited teleport.</summary>
    private readonly string _capturePolicy;
    /// <summary>Effective immutable mode at native ownership admission; never inferred from configuration.</summary>
    private readonly string? _readbackMode;
    /// <summary>Bounded aggregate and last metadata-only pending call; neither grants source or pose authority.</summary>
    private int _readbackPendingCount;
    /// <summary>Last invocation's pending descriptor only, cleared before every subsequent capture.</summary>
    private GameCapturePendingReadback? _lastReadbackPending;
    /// <summary>Only successful TaskRunner activation permits replacing timer chat checks with owned-frame checks.</summary>
    private bool _timerCaptureIsolated;
    /// <summary>Guard failure is published explicitly rather than reported as a user cancellation.</summary>
    internal string? GuardError { get; private set; }
    /// <summary>The token used by all native operations, including teleport retries.</summary>
    internal CancellationToken Token => _stop.Token;

    /// <summary>Reject wrong role/session/ownership before starting any native operation.</summary>
    internal NativeNavigationResetOperations(GameRuntime runtime, AllConfig config, CancellationToken ct,
        string capturePolicy = NavigationResetCapturePolicy.Shared)
    {
        if (!NavigationResetCapturePolicy.IsSupported(capturePolicy)) throw new ArgumentException("unsupported_capture_policy", nameof(capturePolicy));
        _capturePolicy = capturePolicy;
        if (!GameTaskSessionScope.IsActive || runtime.Kind != GameRuntimeKind.Win32Window
            || !System.Windows.Forms.SystemInformation.TerminalServerSession
            || InstanceBootstrap.Current?.Context.InstanceType != BetterGiInstanceType.ChildSession)
            throw new InvalidOperationException("rdp_task_runtime_required");
        _runtime = runtime;
        _readbackMode = GameCaptureSettings.GetReadbackModeName(runtime.Capture);
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
    public async Task PrepareAsync(CancellationToken ct)
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
        // Warmup runs once under the owner deadline. The following bounded readiness window may retry age or close one positively recognized map.
        Guid? provisionalEpoch = _captureEpoch;
        GameCaptureSourceInfo? previousSource = null;
        GameCaptureSourceInfo? readySource = null;
        GameCaptureCallTiming? lastTiming = null;
        GameCaptureSourceInfo? lastSource = null;
        (int Width, int Height, MatType Type)? geometry = null;
        int? lastAttempt = null;
        var lastStage = "prepare_after_capture";
        var mapRecovery = new NavigationResetMapRecovery();
        // This admission clock starts no later than the existing readiness clock; recovery cannot extend its3s budget.
        var preparationStarted = Stopwatch.GetTimestamp();
        var preparationCompleted = false;
        try
        {
            await NavigationResetPreparationReadiness.WaitAsync((attempt, token) =>
            {
                lastAttempt = attempt;
                lastStage = "prepare_after_capture";
                using var frame = CaptureFrame(out lastTiming, out var pending, preparationAcquisitionOrdinal: attempt);
                lastSource = frame?.SourceInfo;
                token.ThrowIfCancellationRequested();
                if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
                var now = Stopwatch.GetTimestamp();
                if (pending is not null)
                {
                    GameCaptureReadbackConsumer.ValidatePending(pending, now, previousSource, provisionalEpoch,
                        geometry?.Width, geometry?.Height);
                    LogSourceDiagnostic("readback_pending", "prepare_readback_pending", null, now, lastTiming,
                        "readback_pending", transient: true, preparationAcquisitionOrdinal: attempt, expectedEpoch: provisionalEpoch);
                    return NavigationResetPreparationState.ReadbackPending;
                }
                if (frame is null) throw new InvalidOperationException("capture_unavailable");
                var observedGeometry = (frame.Frame.Width, frame.Frame.Height, frame.Frame.Type());
                var reason = PreparationFrameRejectionReason(lastSource, now, provisionalEpoch, previousSource,
                    observedGeometry, geometry);
                if (reason is not null and not "source_age_exceeds_500ms")
                {
                    LogSourceDiagnostic(reason, lastStage, lastSource, now, lastTiming,
                        preparationAcquisitionOrdinal: attempt, expectedEpoch: provisionalEpoch);
                    throw new InvalidOperationException(reason == "preparation_frame_geometry_changed"
                        ? reason : "native_source_unavailable_or_stale");
                }
                // Valid headers pin this window even when the first pixels are old. Identical cached tuples may wait.
                provisionalEpoch ??= lastSource!.CaptureEpoch;
                geometry ??= observedGeometry;
                previousSource = lastSource;

                // Ordinary world preparation keeps its original recognizer. Only a positively known map may send Escape.
                var world = mapRecovery.Attempted
                    ? NavigationResetCapturePolicy.RecognizeWorld(frame.Frame, true)
                    : AgentWorldRecognizer.Recognize(frame.Frame);
                if (mapRecovery.Attempted) NavigationResetMapRecovery.ValidateSettlingWorld(frame.Frame, world);
                var knownMap = !mapRecovery.Attempted && world == AgentWorldEvidence.HudMissing
                    && NavigationResetMapRecovery.RecognizeKnownMap(frame.Frame);
                if (!knownMap)
                    WorldRetryReason(world, mapRecovery.Attempted, lastSource!.SourceTimestamp100ns);
                token.ThrowIfCancellationRequested();
                if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
                now = Stopwatch.GetTimestamp();
                lastStage = "prepare_after_world";
                reason = PreparationSourceRejectionReason(lastSource, now, provisionalEpoch, previousSource);
                if (reason == "source_age_exceeds_500ms")
                {
                    LogSourceDiagnostic(reason, lastStage, lastSource, now, lastTiming, "preparation_source_pending",
                        transient: true, preparationAcquisitionOrdinal: attempt, expectedEpoch: provisionalEpoch);
                    return NavigationResetPreparationState.SourceAge;
                }
                if (reason is not null)
                {
                    LogSourceDiagnostic(reason, lastStage, lastSource, now, lastTiming,
                        preparationAcquisitionOrdinal: attempt, expectedEpoch: provisionalEpoch);
                    throw new InvalidOperationException("native_source_unavailable_or_stale");
                }
                if (knownMap)
                {
                    // The exact same pixels passed positive map/chat/modal checks and the post-recognition age gate.
                    // Latch before dispatch; a partial press/release error never permits another Escape.
                    mapRecovery.CloseOnce(lastSource!, preparationStarted, () =>
                    {
                        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
                        if (GameCaptureSettings.GetReadbackModeName(_runtime.Capture) != _readbackMode)
                            throw new InvalidOperationException("readback_mode_changed");
                    }, () => _runtime.Input.Foreground.Keyboard.KeyPress(User32.VK.VK_ESCAPE),
                       () => _runtime.Input.Foreground.Keyboard.KeyUp(User32.VK.VK_ESCAPE), token);
                    return NavigationResetPreparationState.MapClosing;
                }
                if (mapRecovery.Attempted && (world != AgentWorldEvidence.WorldHud || !mapRecovery.SourcePassedRelease(lastSource!)))
                    return NavigationResetPreparationState.MapClosing;
                readySource = lastSource;
                return NavigationResetPreparationState.Ready;
            }, DelayAsync, ct);
            preparationCompleted = true;
        }
        catch (NavigationResetPreparationTimeoutException)
        {
            LogSourceDiagnostic("preparation_readiness_timeout", lastStage, lastSource, Stopwatch.GetTimestamp(), lastTiming,
                "preparation_readiness_timeout", preparationAcquisitionOrdinal: lastAttempt, expectedEpoch: provisionalEpoch);
            throw;
        }
        finally
        {
            if (mapRecovery.Attempted)
            {
                // One compact log retains ambiguous press/release failures; logging itself never changes cleanup or cancellation.
                try
                {
                    App.GetLogger<NativeNavigationResetOperations>().LogInformation("Navigation reset known-map close: {Diagnostic}",
                        JsonConvert.SerializeObject(new { Version = 1, mapRecovery.TriggerSource, mapRecovery.RequestedAtTicks,
                            mapRecovery.ReleasedAtTicks, mapRecovery.Error, mapRecovery.ReleaseError,
                            ClockFrequency = Stopwatch.Frequency, ReadySource = readySource,
                            WorldVerified = preparationCompleted, InputAcknowledgment = false }));
                }
                catch { /* Bounded evidence must not replace the original native failure. */ }
            }
        }
        // Commit only after the helper has rejected cancellation and a late synchronous success; pose high-water stays untouched.
        _captureEpoch = readySource!.CaptureEpoch;
    }

    /// <summary>Native teleport returns an icon coordinate; only later measured spawn samples establish arrival.</summary>
    public async Task TeleportAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        // Only reset teleport opts in, and only if its already-selected runtime is polling. Other backends remain legacy.
        var waitForPendingCapture = _runtime.Capture is IGameCaptureReadback
            { ReadbackMode: GameCaptureReadbackMode.PollSingleV1 };
        await new TpTask(_runtime, _config, ct, waitForPendingCapture).Tp(NavigationResetTask.IconX, NavigationResetTask.IconY);
        ct.ThrowIfCancellationRequested();
        _inputBarrier = Stopwatch.GetTimestamp();
    }

    /// <summary>Activate the TaskRunner-owned lease after teleport; never return a disposable lease to native code.</summary>
    internal async Task IsolateCaptureAsync(Func<CancellationToken, Task> activate, CancellationToken ct)
    {
        if (_capturePolicy != NavigationResetCapturePolicy.TaskOwnedTimer || _timerCaptureIsolated)
            throw new InvalidOperationException("invalid_reset_capture_activation");
        ct.ThrowIfCancellationRequested();
        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
        await activate(ct);
        ct.ThrowIfCancellationRequested();
        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
        _timerCaptureIsolated = true;
    }

    /// <summary>Use CameraRotateTask on the same confidently recognized frame; never drive on its hidden fallback.</summary>
    public async Task<bool> RotateAsync(double yaw, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 50; attempt++)
        {
            // Only the first acquisition after Tp may wait for a missing HUD. Every pose read may discard stale
            // sources within its existing bounded wait; no camera command runs until independently fresh recognition.
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

    /// <summary>Every pose read shares one bounded source/minimap/yaw settle deadline; initial HUD settling stays separate.</summary>
    private async Task<NavigationResetSample> MeasureAsync(double? rotateYaw, CancellationToken ct,
        bool allowPostTeleportHudSettling = false)
    {
        // Local metadata cannot be consumed by the earlier one-per-run transient log or leak across windows.
        var evidence = new NavigationResetPoseTimeoutEvidence(Stopwatch.GetTimestamp());
        try
        {
            return await NavigationResetPoseAcquisition.ReadAsync(async token =>
            {
                var result = await MeasureOnceAsync(rotateYaw, allowPostTeleportHudSettling, token, evidence);
                evidence.Complete(result, Stopwatch.GetTimestamp());
                return result;
            }, DelayAsync, ct);
        }
        catch (TimeoutException)
        {
            // Preserve the original exception and terminal budget even if diagnostic construction/logging fails.
            try
            {
                var detail = evidence.Snapshot(Stopwatch.GetTimestamp());
                var probe = detail.CurrentProbe;
                LogSourceDiagnostic(probe?.PendingReadback is null ? "pose_acquisition_timeout" : "readback_pending_timeout",
                    probe?.Stage ?? "capture", probe?.Source, detail.TimedOutAtTicks, probe?.Capture,
                    "pose_acquisition_timeout", phase: rotateYaw.HasValue ? "orienting" : "verifying",
                    poseAcquisitionOrdinal: probe?.PoseAcquisitionOrdinal, initialHudSettling: allowPostTeleportHudSettling,
                    poseAcquisitionTimeout: detail);
            }
            catch { /* Timeout evidence must never replace cancellation/cleanup behavior or the original failure. */ }
            throw;
        }
    }

    /// <summary>Use one new native source for every evidence check; transient misses return before any camera input.</summary>
    private Task<NavigationResetPoseProbe> MeasureOnceAsync(double? rotateYaw, bool allowPostTeleportHudSettling,
        CancellationToken ct, NavigationResetPoseTimeoutEvidence evidence)
    {
        ct.ThrowIfCancellationRequested();
        var ordinal = ++_poseAcquisitionOrdinal;
        var phase = rotateYaw.HasValue ? "orienting" : "verifying";
        var diagnostic = evidence.Begin(ordinal, Stopwatch.GetTimestamp());
        GameCaptureCallTiming? timing = null;
        GameCapturePendingReadback? pending = null;
        GameCaptureFrame? capturedFrame;
        try { capturedFrame = CaptureFrame(out timing, out pending, phase, ordinal, allowPostTeleportHudSettling); }
        finally
        {
            // The invocation-local out trace survives capture throws and never borrows another caller's timing.
            diagnostic.Capture = timing;
            diagnostic.PendingReadback = pending;
            diagnostic.CaptureFinishedAtTicks = Stopwatch.GetTimestamp();
        }
        using var frame = capturedFrame;
        diagnostic.Source = frame?.SourceInfo;
        try
        {
            ct.ThrowIfCancellationRequested();
            if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
            var capturedAt = Stopwatch.GetTimestamp();
            if (pending is not null)
            {
                var consumed = _captureEpoch is { } epoch && _lastTimestamp > 0 && _lastAcquisition > 0
                    ? new GameCaptureSourceInfo(epoch, _lastTimestamp, _lastAcquisition) : null;
                GameCaptureReadbackConsumer.ValidatePending(pending, capturedAt, consumed, _captureEpoch);
                LogSourceDiagnostic("readback_pending", "capture", null, capturedAt, timing, "readback_pending",
                    transient: true, phase, ordinal, allowPostTeleportHudSettling);
                return Task.FromResult(new NavigationResetPoseProbe(null, "readback_pending"));
            }
            if (frame is null) throw new InvalidOperationException("capture_unavailable");
            diagnostic.Stage = diagnostic.SourceCheckStage = "after_capture";
            diagnostic.SourceCheckedAtTicks = capturedAt;
            if (PoseSourceRetryReason(frame.SourceInfo, capturedAt, _captureEpoch, "after_capture") is { } pendingSource)
            {
                // Discard without recognition or changing epoch, consumed clocks, or the input barrier.
                // ReadAsync retains its original 3-second/25-attempt/120ms limits; no stale frame authorizes input.
                LogSourceDiagnostic("source_age_exceeds_500ms", "after_capture", frame.SourceInfo,
                    capturedAt, timing, "pose_source_pending", transient: true, phase, ordinal, allowPostTeleportHudSettling);
                return Task.FromResult(new NavigationResetPoseProbe(null, pendingSource));
            }
            var source = ValidateSource(frame.SourceInfo, capturedAt, "after_capture", timing, phase, ordinal, allowPostTeleportHudSettling);
            // No source can cross a post-input barrier by being copied from the backend cache again.
            if (source.SourceTimestamp100ns <= _lastTimestamp || source.AcquiredAtStopwatchTicks <= _lastAcquisition
                || !SourceIsAfterBarrier(source, _inputBarrier))
                return Task.FromResult(new NavigationResetPoseProbe(null,
                    $"awaiting_new_source; source={source.SourceTimestamp100ns}"));
            _lastTimestamp = source.SourceTimestamp100ns;
            _lastAcquisition = source.AcquiredAtStopwatchTicks;
            // Teleport's main-UI check is not a settled native HUD guarantee. Retry only a newly sourced missing HUD;
            // blocked/error evidence stays terminal, and no pose matching or camera input runs on an unready frame.
            diagnostic.Stage = "world_recognition";
            diagnostic.RecognitionStartedAtTicks = Stopwatch.GetTimestamp();
            if (WorldRetryReason(NavigationResetCapturePolicy.RecognizeWorld(frame.Frame, _timerCaptureIsolated), allowPostTeleportHudSettling,
                    source.SourceTimestamp100ns) is { } worldReason)
                return Task.FromResult(new NavigationResetPoseProbe(null, worldReason));
            // CaptureContent owns a clone; the original native frame keeps independent ownership and metadata.
            using var bgr = new Mat();
            if (frame.Frame.Channels() == 4) Cv2.CvtColor(frame.Frame, bgr, ColorConversionCodes.BGRA2BGR);
            using var content = new CaptureContent((frame.Frame.Channels() == 4 ? bgr : frame.Frame).Clone(), 0, 0, _runtime.SystemInfo);
            using var minimap = new Mat(content.CaptureRectArea.SrcMat, MapAssets.Get(content.CaptureRectArea).MimiMapRect);
            diagnostic.Stage = "yaw_recognition";
            var (yaw, confidence) = _yaw.PredictRotationWithConfidence(minimap);
            if (!NavigationResetTask.IsReliableYaw(yaw, confidence))
                return Task.FromResult(new NavigationResetPoseProbe(null, FormattableString.Invariant(
                    $"yaw_unrecognized; source={source.SourceTimestamp100ns}; yaw={yaw:F3}; yawConfidence={confidence:F4}")));
            // Rank0 is the existing strict 0.99 threshold. A failed match must not reuse PrevSuccessResult.
            diagnostic.Stage = "position_recognition";
            var position = _map!.GetMiniMapPosition(minimap, _anchor.X, _anchor.Y, 0);
            if (position == default)
                return Task.FromResult(new NavigationResetPoseProbe(null, FormattableString.Invariant(
                    $"local_position_unrecognized; source={source.SourceTimestamp100ns}; yaw={yaw:F3}; yawConfidence={confidence:F4}")));
            var match = _map.PrevSuccessResult;
            var world = _map.ConvertImageCoordinatesToGenshinMapCoordinates(position)
                ?? throw new InvalidOperationException("local_position_unrecognized");
            var sample = new NavigationResetSample(world.X, world.Y, yaw, DateTimeOffset.UtcNow, source.CaptureEpoch,
                source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, match.Confidence, confidence, match.Layer?.LayerId ?? "");
            diagnostic.RecognitionFinishedAtTicks = Stopwatch.GetTimestamp();
            diagnostic.Stage = "pose_validation";
            if (!NavigationResetTask.IsValidPose(sample)) throw new InvalidOperationException(FormattableString.Invariant(
                $"pose_evidence_rejected; source={source.SourceTimestamp100ns}; x={world.X:F3}; y={world.Y:F3}; layer={sample.LayerId}; confidence={match.Confidence:F4}"));
            if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
            ct.ThrowIfCancellationRequested();
            var recognizedAt = Stopwatch.GetTimestamp();
            diagnostic.Stage = diagnostic.SourceCheckStage = "after_recognition";
            diagnostic.SourceCheckedAtTicks = recognizedAt;
            if (PoseSourceRetryReason(source, recognizedAt, _captureEpoch, "after_recognition") is { } recognitionPendingSource)
            {
                // Recognition cannot renew source age. Keep the consumed-clock high-water marks so this image cannot
                // be reused, but discard the pose before camera input or success. The original input barrier is unchanged.
                LogSourceDiagnostic("source_age_exceeds_500ms", "after_recognition", source, recognizedAt, timing,
                    "pose_source_pending", transient: true, phase, ordinal, allowPostTeleportHudSettling);
                return Task.FromResult(new NavigationResetPoseProbe(null, recognitionPendingSource));
            }
            ValidateSource(source, recognizedAt, "after_recognition", timing, phase, ordinal, allowPostTeleportHudSettling);
            ct.ThrowIfCancellationRequested();
            if (rotateYaw is { } target && !NavigationResetTask.IsYawOriented(yaw, target))
            {
                // This exact frame already supplied reliable yaw; do not invoke the separate recognizer's fallback.
                new CameraRotateTask(_runtime, ct).RotateToApproach((float)target, (float)yaw);
                _inputBarrier = Stopwatch.GetTimestamp();
            }
            return Task.FromResult(new NavigationResetPoseProbe(sample, null));
        }
        finally
        {
            // Include early recognition misses/cancellation without pretending that the probe returned a result.
            if (diagnostic.RecognitionStartedAtTicks is not null && diagnostic.RecognitionFinishedAtTicks is null)
                diagnostic.RecognitionFinishedAtTicks = Stopwatch.GetTimestamp();
        }
    }

    /// <summary>Acquire one owned native frame only while the original runtime/process/input target remains available.</summary>
    private GameCaptureFrame? CaptureFrame(out GameCaptureCallTiming? timing, out GameCapturePendingReadback? pending,
        string phase = "preparing",
        int? poseAcquisitionOrdinal = null, bool? initialHudSettling = null, int? preparationAcquisitionOrdinal = null)
    {
        timing = null;
        pending = null; _lastReadbackPending = null;
        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
        GameCaptureFrame? frame;
        try
        {
            var attempt = GameCaptureReadbackConsumer.Capture(_runtime.Capture, true, out timing);
            frame = attempt.Frame;
            if (attempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending)
            {
                pending = _lastReadbackPending = attempt.Pending;
                _readbackPendingCount++;
                return null;
            }
        }
        catch
        {
            LogSourceDiagnostic("capture_threw", "capture", null, Stopwatch.GetTimestamp(), timing, "capture_threw",
                phase: phase, poseAcquisitionOrdinal: poseAcquisitionOrdinal, initialHudSettling: initialHudSettling,
                preparationAcquisitionOrdinal: preparationAcquisitionOrdinal);
            throw;
        }
        if (frame is not null) return frame;
        LogSourceDiagnostic("capture_null", "capture", null, Stopwatch.GetTimestamp(), timing, "capture_unavailable",
            phase: phase, poseAcquisitionOrdinal: poseAcquisitionOrdinal, initialHudSettling: initialHudSettling,
            preparationAcquisitionOrdinal: preparationAcquisitionOrdinal);
        throw new InvalidOperationException("capture_unavailable");
    }

    /// <summary>Preparation retries age only; malformed, changing or regressing source identity stays terminal.</summary>
    internal static string? PreparationSourceRejectionReason(GameCaptureSourceInfo? source, long now,
        Guid? expectedEpoch, GameCaptureSourceInfo? previous)
    {
        var reason = SourceRejectionReason(source, now, expectedEpoch);
        if (reason is not null and not "source_age_exceeds_500ms") return reason;
        if (previous is not null && source is not null)
        {
            if (source.SourceTimestamp100ns < previous.SourceTimestamp100ns
                || source.AcquiredAtStopwatchTicks < previous.AcquiredAtStopwatchTicks) return "source_clock_regressed";
            if (source.SourceTimestamp100ns == previous.SourceTimestamp100ns
                && source.AcquiredAtStopwatchTicks != previous.AcquiredAtStopwatchTicks) return "source_identity_changed";
        }
        return reason;
    }

    /// <summary>Geometry changes remain hard even when the otherwise valid frame also exceeds the age threshold.</summary>
    internal static string? PreparationFrameRejectionReason(GameCaptureSourceInfo? source, long now,
        Guid? expectedEpoch, GameCaptureSourceInfo? previous, (int Width, int Height, MatType Type) geometry,
        (int Width, int Height, MatType Type)? expectedGeometry)
    {
        var reason = PreparationSourceRejectionReason(source, now, expectedEpoch, previous);
        if (reason is not null and not "source_age_exceeds_500ms") return reason;
        return expectedGeometry is { } pinned && geometry != pinned ? "preparation_frame_geometry_changed" : reason;
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
    private GameCaptureSourceInfo ValidateSource(GameCaptureSourceInfo? source, long now, string stage,
        GameCaptureCallTiming? timing, string phase = "preparing", int? poseAcquisitionOrdinal = null,
        bool? initialHudSettling = null)
    {
        if (SourceRejectionReason(source, now, _captureEpoch) is { } reason)
        {
            LogSourceDiagnostic(reason, stage, source, now, timing,
                phase: phase, poseAcquisitionOrdinal: poseAcquisitionOrdinal, initialHudSettling: initialHudSettling);
            throw new InvalidOperationException("native_source_unavailable_or_stale");
        }
        _captureEpoch ??= source!.CaptureEpoch;
        return source!;
    }

    /// <summary>Explain the existing predicates without relaxing the 500ms threshold or epoch admission.</summary>
    internal static string? SourceRejectionReason(GameCaptureSourceInfo? source, long now, Guid? expectedEpoch)
    {
        // A changed generation is terminal even if its pixels are also old; age cannot hide identity loss.
        if (source is { CaptureEpoch: var observed } && observed != Guid.Empty
            && expectedEpoch is { } expected && observed != expected) return "source_epoch_changed";
        if (!SourceIsFresh(source, now))
        {
            if (!Stopwatch.IsHighResolution) return "high_resolution_clock_unavailable";
            if (source is null) return "source_missing";
            if (source.CaptureEpoch == Guid.Empty) return "source_epoch_empty";
            if (source.SourceTimestamp100ns <= 0) return "source_timestamp_invalid";
            if (source.AcquiredAtStopwatchTicks <= 0) return "acquisition_timestamp_invalid";
            if (source.AcquiredAtStopwatchTicks > now) return "acquisition_in_future";
            return "source_age_exceeds_500ms";
        }
        return expectedEpoch is { } epoch && source!.CaptureEpoch != epoch ? "source_epoch_changed" : null;
    }

    /// <summary>Pose acquisitions may retry age alone before input; preparation uses its separate bounded window.</summary>
    internal static string? PoseSourceRetryReason(GameCaptureSourceInfo? source, long now, Guid? expectedEpoch, string stage) =>
        stage is "after_capture" or "after_recognition" && expectedEpoch is { } epoch && epoch != Guid.Empty
        && source?.CaptureEpoch == epoch && SourceRejectionReason(source, now, expectedEpoch) == "source_age_exceeds_500ms"
            ? $"pose_source_stale; stage={stage}; source={source.SourceTimestamp100ns}" : null;

    /// <summary>Log each category once after capture locks; a transient record cannot consume the terminal diagnostic slot.</summary>
    private void LogSourceDiagnostic(string reason, string stage, GameCaptureSourceInfo? source, long now,
        GameCaptureCallTiming? timing, string errorCode = "native_source_unavailable_or_stale", bool transient = false,
        string phase = "preparing", int? poseAcquisitionOrdinal = null, bool? initialHudSettling = null,
        int? preparationAcquisitionOrdinal = null, Guid? expectedEpoch = null,
        NavigationResetPoseTimeoutDiagnostic? poseAcquisitionTimeout = null)
    {
        ref var logged = ref (transient ? ref _transientSourceDiagnosticLogged : ref _sourceDiagnosticLogged);
        if (logged) return;
        logged = true;
        try
        {
            var record = new NavigationResetSourceDiagnostic { ErrorCode = errorCode, Reason = reason, Stage = stage,
                Phase = phase, PoseAcquisitionOrdinal = poseAcquisitionOrdinal, InitialHudSettling = initialHudSettling,
                PreparationAcquisitionOrdinal = preparationAcquisitionOrdinal,
                ReadbackMode = _readbackMode, ReadbackPendingCount = _readbackPendingCount,
                PendingReadback = poseAcquisitionTimeout is null ? _lastReadbackPending : poseAcquisitionTimeout.CurrentProbe?.PendingReadback,
                PoseAcquisitionTimeout = poseAcquisitionTimeout,
                NowTicks = now, ExpectedEpoch = expectedEpoch ?? _captureEpoch, ObservedSource = source, Capture = timing };
            App.GetLogger<NativeNavigationResetOperations>().LogWarning(transient
                    ? "Navigation reset transient source diagnostic: {Diagnostic}"
                    : "Navigation reset source diagnostic: {Diagnostic}",
                JsonConvert.SerializeObject(record));
        }
        catch { /* Diagnostics must not change reset cancellation, input cleanup, or its stable error. */ }
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
