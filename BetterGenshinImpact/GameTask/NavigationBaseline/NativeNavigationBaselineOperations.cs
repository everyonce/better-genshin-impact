using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
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

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Strict native pose/camera boundary for one fixed leg, with no OCR, global matching or recovery macros.</summary>
internal sealed class NativeNavigationBaselineOperations : INavigationBaselineOperations, INavigationBaselineRecoveryOperations, INavigationBaselineFinalVerificationOperations, IAsyncDisposable
{
    /// <summary>Bound retained images, their encoded files and the separate post-release journal; pipe limits stay unchanged.</summary>
    internal const int MaximumWidth = 3840, MaximumHeight = 2160, MaximumPngBytes = 40 * 1024 * 1024,
        MaximumJournalBytes = 6 * 1024 * 1024;
    /// <summary>Flat source-poll evidence covers the 30-second workflow without an unbounded nested capture list.</summary>
    internal const int MaximumCapturePolls = 4096;
    /// <summary>The exact TaskRunner runtime and process identity.</summary>
    private readonly GameRuntime _runtime;
    /// <summary>Unique owner-issued run identifier, never a caller-supplied path.</summary>
    private readonly string _runId;
    /// <summary>Owned timer-pause selection; shared preserves the original recognition path.</summary>
    private readonly string _capturePolicy;
    /// <summary>Immutable effective backend mode at ownership admission; configuration alone is not evidence.</summary>
    private readonly string? _readbackMode;
    /// <summary>Only v4 changes interruption handling; shared capture/default contracts remain unchanged.</summary>
    private readonly bool _supportsRecovery;
    /// <summary>Enable after the verified anchor; permanent closure disables it before final reads.</summary>
    private bool _recoveryEnabled, _recovering;
    /// <summary>Fixed active recovery deadline and first poll offset; neither advances on retries.</summary>
    private double _recoveryDeadline;
    /// <summary>Global poll index at this bounded window's entry.</summary>
    private int _recoveryPollStart;
    /// <summary>At most two file-only attempts, joined to the original observation/poll evidence.</summary>
    private readonly List<NavigationBaselineRecoveryAttempt> _recoveryAttempts = [];
    /// <summary>Active v4 terminal-read window; it never enables the movement recovery path.</summary>
    private NavigationBaselineFinalVerification? _activeFinalVerification;
    /// <summary>One retained file-only final window, including failure before its first capture.</summary>
    private NavigationBaselineFinalVerificationWindow? _finalVerificationWindow;
    /// <summary>Query-limited/synchronize handle prevents PID reuse without requesting game modification access.</summary>
    private readonly Kernel32.SafeHPROCESS _game;
    /// <summary>Pinned game and Windows session identifiers.</summary>
    private readonly int _gameProcessId;
    /// <summary>Actual RDP session shared by this child and its game.</summary>
    private readonly uint _sessionId;
    /// <summary>Task stop and runtime detach feed the independent input watchdog.</summary>
    private readonly CancellationTokenSource _lifetime;
    /// <summary>Task-local confidence-bearing yaw recognizer.</summary>
    private readonly MiniMapPreprocessor _yaw;
    /// <summary>One-purpose input/watchdog owner; no image work occurs under its lock.</summary>
    private readonly NavigationBaselineInputLease _lease;
    /// <summary>Explicit local template map, accessed only inside exclusive TaskRunner ownership.</summary>
    private SceneBaseMapByTemplateMatch? _map;
    /// <summary>Positive image-space local anchor and fixed endpoint, derived with the same map conversion.</summary>
    private Point2f _anchor;
    /// <summary>Pure heading helper input, never passed to PathExecutor.</summary>
    private Waypoint? _endpoint;
    /// <summary>Native source high-water, pinned for this entire run.</summary>
    private GameCaptureSourceInfo? _lastSource;
    /// <summary>A resize cannot silently change recognition/camera geometry during this measured leg.</summary>
    private int _captureWidth, _captureHeight;
    /// <summary>Latest actual input completion/cutoff and required response delay.</summary>
    private double _inputBarrier, _responseMs;
    /// <summary>Normal closure records its barrier exactly once, even during repeated finally cleanup.</summary>
    private bool _inputClosed;
    /// <summary>At most two owned copies; final verification replaces and disposes its previous image.</summary>
    private Mat? _initialImage, _finalImage;
    /// <summary>Exact source associations for the retained native pixels.</summary>
    private GameCaptureSourceInfo? _initialImageSource, _finalImageSource;
    /// <summary>One bounded diagnostic per native read, including a failed final in-flight read.</summary>
    private readonly List<NavigationBaselineObservationAttempt> _observationAttempts = [];
    /// <summary>Run-level source/wait rows, admitted before each capture and published only after input closes.</summary>
    private readonly List<NavigationBaselineCapturePoll> _capturePolls = [];
    /// <summary>Selected per-call backend detail is bounded separately, with one terminal slot reserved.</summary>
    private int _retainedCaptureTimings;
    /// <summary>Only the last invocation stays pending for promotion if the later control gate fails after a successful read.</summary>
    private (NavigationBaselineCapturePoll Poll, GameCaptureCallTiming Timing)? _lastCaptureTiming;

    /// <summary>Require real RDP child ownership before opening handles, starting the watchdog or reading game pixels.</summary>
    internal NativeNavigationBaselineOperations(GameRuntime runtime, string runId, CancellationToken ct,
        string timingContract = NavigationBaselineTiming.V1, string capturePolicy = NavigationBaselineCapturePolicy.Shared)
    {
        if (!NavigationBaselineTiming.IsSupported(timingContract)) throw new ArgumentException("unsupported_timing_contract", nameof(timingContract));
        if (!NavigationBaselineCapturePolicy.IsSupported(capturePolicy)) throw new ArgumentException("unsupported_capture_policy", nameof(capturePolicy));
        if (!GameTaskSessionScope.IsActive || runtime.Kind != GameRuntimeKind.Win32Window
            || !System.Windows.Forms.SystemInformation.TerminalServerSession
            || InstanceBootstrap.Current?.Context.InstanceType != BetterGiInstanceType.ChildSession)
            throw new InvalidOperationException("rdp_task_runtime_required");
        if (!Guid.TryParseExact(runId, "N", out var id) || id == Guid.Empty) throw new ArgumentException("invalid_baseline_run_id", nameof(runId));
        _runtime = runtime; _runId = runId; _capturePolicy = capturePolicy;
        _readbackMode = GameCaptureSettings.GetReadbackModeName(runtime.Capture);
        _supportsRecovery = timingContract == NavigationBaselineTiming.V4;
        try
        {
            _gameProcessId = runtime.Window.ProcessId;
            if (_gameProcessId <= 0 || !Kernel32.ProcessIdToSessionId(Kernel32.GetCurrentProcessId(), out _sessionId))
                throw new InvalidOperationException("game_session_unavailable");
            _game = Kernel32.OpenProcess(new ACCESS_MASK(Kernel32.ProcessAccess.PROCESS_QUERY_LIMITED_INFORMATION)
                | ACCESS_MASK.SYNCHRONIZE, false, checked((uint)_gameProcessId));
            if (!Kernel32.ProcessIdToSessionId((uint)_gameProcessId, out var gameSession) || gameSession != _sessionId || !IsAvailable())
                throw new InvalidOperationException("game_target_unavailable");
            _yaw = new MiniMapPreprocessor();
            _lifetime = CancellationTokenSource.CreateLinkedTokenSource(ct, runtime.Stopping);
            var channel = runtime.Input.Foreground;
            _lease = new(() => NowMs, IsAvailable,
                () => channel.Keyboard.KeyDown(User32.VK.VK_W), () => channel.Keyboard.KeyUp(User32.VK.VK_W),
                dx => channel.Mouse.MoveMouseBy(dx, 0), _lifetime.Token, timingContract: timingContract);
        }
        catch { _game?.Dispose(); _yaw?.Dispose(); _lifetime?.Dispose(); throw; }
    }

    /// <summary>Absolute QPC milliseconds, sharing the native acquisition time origin.</summary>
    public double NowMs => Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency;
    /// <summary>Explicit may-hold state survives ambiguous native input failure.</summary>
    public bool ForwardHeld => _lease.ForwardHeld;
    /// <summary>Latched watchdog reason for diagnostics instead of generic cancellation.</summary>
    public string? Fault => _lease.Fault;
    /// <summary>Explicit failed W release, even if later best-effort cleanup succeeds.</summary>
    public string? ReleaseError => _lease.ReleaseError;
    /// <summary>Use this combined token for all observations and waits.</summary>
    internal CancellationToken Token => _lease.Token;

    /// <summary>Keep the original process object, window, foreground and input backend pinned throughout native work.</summary>
    private bool IsAvailable() => !_game.IsInvalid && !_game.IsClosed
        && Kernel32.GetProcessId(_game) == (uint)_gameProcessId
        && Kernel32.WaitForSingleObject(_game, 0) == Kernel32.WAIT_STATUS.WAIT_TIMEOUT
        && _runtime.Window.ProcessId == _gameProcessId && !_runtime.IsStopping
        && _runtime.Window.IsAlive && !_runtime.Window.IsMinimized
        && (!_runtime.Window.RequiresForeground || _runtime.Window.IsForeground)
        && ReferenceEquals(InputHub.Backend, _runtime.Input);

    /// <summary>Fail before any native work if cancellation, target identity or the lease has ended abnormally.</summary>
    private void CheckAvailable(CancellationToken ct)
    {
        if (Fault is { } fault) throw new InvalidOperationException(fault);
        ct.ThrowIfCancellationRequested(); Token.ThrowIfCancellationRequested();
        if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
        if (_activeFinalVerification is { } final)
        {
            if (!_inputClosed || _recoveryEnabled || _recovering || ForwardHeld || ReleaseError is not null)
                throw new InvalidOperationException("final_verification_requires_input_closed");
            final.Check(ct);
        }
        if (_recovering) NavigationBaselineRecovery.EnsureWindow(NowMs, _recoveryDeadline, _capturePolls.Count - _recoveryPollStart);
        if (!_recovering && _recoveryEnabled && _lease.PendingRecovery is { } pause)
            throw new NavigationBaselineRecoveryRequired(pause.Cause, "between_observations", pause: pause);
    }

    /// <summary>Validate the fixed shipped route without ever executing any of its actions.</summary>
    internal static void ValidateRoute(ReadOnlySpan<byte> bytes)
    {
        if (Convert.ToHexString(SHA256.HashData(bytes)) != NavigationBaselineTask.RouteSha256)
            throw new InvalidOperationException("route_profile_changed");
        using var document = JsonDocument.Parse(bytes.ToArray());
        var points = document.RootElement.GetProperty("positions");
        if (points.GetArrayLength() < 2) throw new InvalidOperationException("route_profile_changed");
        for (var i = 0; i < 2; i++)
        {
            var point = points[i];
            if (point.GetProperty("x").GetDouble() != (i == 0 ? NavigationBaselineTask.StartX : NavigationBaselineTask.EndX)
                || point.GetProperty("y").GetDouble() != (i == 0 ? NavigationBaselineTask.StartY : NavigationBaselineTask.EndY)
                || point.GetProperty("type").GetString() != (i == 0 ? "teleport" : "path")
                || point.GetProperty("move_mode").GetString() != "walk" || point.GetProperty("action").GetString() != "")
                throw new InvalidOperationException("route_profile_changed");
        }
    }

    /// <summary>Warm only the explicit local matching map; synchronous warmup remains cooperatively bounded.</summary>
    public Task PrepareAsync(CancellationToken ct)
    {
        CheckAvailable(ct);
        ValidateRoute(File.ReadAllBytes(Global.Absolute(@"GameTask\Common\Element\Assets\Json\合成台_蒙德.json")));
        _map = MapManager.GetMap("Teyvat", "TemplateMatch") as SceneBaseMapByTemplateMatch
            ?? throw new InvalidOperationException("local_template_map_unavailable");
        _map.WarmUp();
        _anchor = _map.ConvertGenshinMapCoordinatesToImageCoordinates(new Point2f((float)NavigationBaselineTask.StartX, (float)NavigationBaselineTask.StartY));
        var endpoint = _map.ConvertGenshinMapCoordinatesToImageCoordinates(new Point2f((float)NavigationBaselineTask.EndX, (float)NavigationBaselineTask.EndY));
        if (!float.IsFinite(_anchor.X) || !float.IsFinite(_anchor.Y) || _anchor.X <= 0 || _anchor.Y <= 0
            || !float.IsFinite(endpoint.X) || !float.IsFinite(endpoint.Y) || endpoint.X <= 0 || endpoint.Y <= 0)
            throw new InvalidOperationException("invalid_local_anchor");
        _endpoint = new Waypoint { X = endpoint.X, Y = endpoint.Y };
        CheckAvailable(ct);
        return Task.CompletedTask;
    }

    /// <summary>Reject invalid/native-old pixels before any recognition; only duplicates/barrier waiting may be polled again.</summary>
    private GameCaptureSourceInfo ValidateSource(GameCaptureSourceInfo? source, string stage = "validating_source",
        NavigationBaselineObservationAttempt? finalAttempt = null, CancellationToken ct = default)
    {
        if (_activeFinalVerification is { } final)
            return final.ValidateSource(source, stage, finalAttempt
                ?? throw new InvalidOperationException("final_verification_read_context_missing"), ct);
        var now = NowMs;
        if (_supportsRecovery && NavigationBaselineRecovery.HardSourceRejection(source, now, _lastSource) is { } hard)
            throw new InvalidOperationException(hard);
        var age = NavigationBaselineTask.SourceAge(source, now);
        if (_recoveryEnabled && double.IsFinite(age) && age > NavigationBaselineTask.MaximumSourceAgeMs)
            throw new NavigationBaselineRecoveryRequired(NavigationBaselineRecoveryCause.SourceAge, stage, source);
        if (!double.IsFinite(age) || age is < 0 or > NavigationBaselineTask.MaximumSourceAgeMs)
            throw new InvalidOperationException("native_source_unavailable_or_stale");
        if (_lastSource is { } previous && source!.CaptureEpoch != previous.CaptureEpoch)
            throw new InvalidOperationException("source_epoch_changed");
        return source!;
    }

    /// <summary>One generation and non-regressing clocks are mandatory; equal cached clocks only permit waiting.</summary>
    internal static string? SourceIdentityRejection(GameCaptureSourceInfo source, GameCaptureSourceInfo? previous) =>
        previous is null ? null : source.CaptureEpoch != previous.CaptureEpoch ? "source_epoch_changed"
        : source.SourceTimestamp100ns < previous.SourceTimestamp100ns || source.AcquiredAtStopwatchTicks < previous.AcquiredAtStopwatchTicks
            ? "native_source_regressed" : null;

    /// <summary>Use one native frame for world, key-tip motion, yaw and strict local position; there is no cached-pose fallback.</summary>
    public Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct) =>
        ReadPoseCoreAsync(retainImage, ct);

    /// <summary>Final admission uses this same source/recognition path with an explicit fixed transaction callback.</summary>
    private Task<NavigationBaselineSample> ReadPoseCoreAsync(string? retainImage, CancellationToken ct,
        Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission>? stageFinalRows = null) =>
        RecordObservationAsync(_observationAttempts, () => NowMs, () => Fault, async attempt =>
    {
        var observationStarted = attempt.StartedAtMs;
        while (true)
        {
            attempt.Stage = "checking_target";
            CheckAvailable(ct);
            if (_recovering) NavigationBaselineRecovery.EnsureWindow(NowMs, _recoveryDeadline,
                _capturePolls.Count - _recoveryPollStart, admitCapture: true);
            var requested = NowMs;
            // Reserve both global evidence and final-window limits before the actual native call.
            if (_capturePolls.Count >= MaximumCapturePolls) throw new InvalidOperationException("capture_diagnostics_capacity_exceeded");
            _activeFinalVerification?.BeginCapture(ct);
            var poll = BeginCapturePoll(_capturePolls, _observationAttempts.Count - 1, requested);
            attempt.Stage = "capturing"; attempt.CaptureStartedAtMs = requested; attempt.CaptureReturnedAtMs = null;
            attempt.CaptureCount++;
            GameCaptureCallTiming? captureTiming = null;
            var diagnosticCapture = _runtime.Capture as IGameCaptureDiagnostics;
            poll.CaptureTimingSupported = diagnosticCapture is not null;
            try
            {
                var captureAttempt = GameCaptureReadbackConsumer.Capture(_runtime.Capture, true, out captureTiming);
                using var frame = captureAttempt.Frame;
                poll.RecordReadback(captureAttempt);
                if (captureAttempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending)
                {
                    var pendingReturned = NowMs;
                    poll.CaptureReturnedAtMs = pendingReturned; attempt.CaptureReturnedAtMs = pendingReturned;
                    attempt.LastReturnedSource = null;
                    // Metadata sanity precedes an already-expired lease: a changed epoch/geometry remains a hard failure.
                    GameCaptureReadbackConsumer.ValidatePending(captureAttempt.Pending!, Stopwatch.GetTimestamp(), _activeFinalVerification?.SeenSource ?? _lastSource,
                        width: _captureWidth == 0 ? null : _captureWidth, height: _captureHeight == 0 ? null : _captureHeight);
                    attempt.Stage = "waiting_readback";
                    await WaitForReadbackAsync(poll, () => CheckAvailable(ct), () => NowMs,
                        WaitUntilAsync, _recovering, ct).ConfigureAwait(false);
                    continue;
                }
                if (frame is null) throw new InvalidOperationException("capture_unavailable");
                var returned = NowMs;
                poll.CaptureReturnedAtMs = returned; poll.Source = frame.SourceInfo;
                attempt.CaptureReturnedAtMs = returned; attempt.LastReturnedSource = frame.SourceInfo; attempt.Stage = "validating_capture";
                // V4 validates every hard header/geometry predicate before considering age or a watchdog pause.
                if (_supportsRecovery)
                {
                    if (NavigationBaselineRecovery.HardSourceRejection(frame.SourceInfo, NowMs, _lastSource) is { } hard)
                        throw new InvalidOperationException(hard);
                    if (frame.Frame.Empty() || frame.Frame.Width > MaximumWidth || frame.Frame.Height > MaximumHeight
                        || frame.Frame.Channels() is not (3 or 4)) throw new InvalidOperationException("unsupported_native_frame");
                    if (_captureWidth != 0 && (_captureWidth != frame.Frame.Width || _captureHeight != frame.Frame.Height))
                        throw new InvalidOperationException("native_frame_geometry_changed");
                    ct.ThrowIfCancellationRequested();
                    if (!IsAvailable()) throw new InvalidOperationException("game_target_lost");
                }
                var source = ValidateSource(frame.SourceInfo, "after_capture", attempt, ct);
                if (frame.Frame.Empty() || frame.Frame.Width > MaximumWidth || frame.Frame.Height > MaximumHeight
                    || frame.Frame.Channels() is not (3 or 4)) throw new InvalidOperationException("unsupported_native_frame");
                if (_captureWidth != 0 && (_captureWidth != frame.Frame.Width || _captureHeight != frame.Frame.Height))
                    throw new InvalidOperationException("native_frame_geometry_changed");
                _captureWidth = frame.Frame.Width; _captureHeight = frame.Frame.Height;
                if (SourceIdentityRejection(source, _lastSource) is { } sourceError) throw new InvalidOperationException(sourceError);
                poll.Classify(source, _capturePolls.Count > 1 ? _capturePolls[^2].Source : null,
                    _lastSource, _inputBarrier, _responseMs, NowMs);
                var duplicate = poll.DuplicateOfAccepted == true;
                var beforeBarrier = _responseMs > 0 && !NavigationBaselineTask.AfterBarrier(source, _inputBarrier, _responseMs);
                if (duplicate || beforeBarrier)
                {
                    if (duplicate) attempt.DuplicateCount++;
                    if (beforeBarrier) attempt.BarrierCount++;
                    attempt.Stage = "waiting_source";
                    // No recognition or input authority is renewed while awaiting distinct response pixels.
                    poll.WaitStartedAtMs = NowMs;
                    poll.WaitRequestedDeadlineMs = poll.WaitStartedAtMs + (_recovering ? NavigationBaselineRecovery.RetryDelayMs : 5);
                    try { await WaitUntilAsync(poll.WaitRequestedDeadlineMs.Value, ct).ConfigureAwait(false); }
                    finally { poll.WaitExitedAtMs = NowMs; }
                    continue;
                }
                _lastSource = source;
                // Capture admission ends before recognition; a later recognizer error is not labelled as a capture failure.
                poll.EndedAtMs = NowMs;
                attempt.RecognitionStartedAtMs = NowMs;
                // Recovery always requires same-frame closed-chat evidence, including a shared-capture run.
                var checkChat = _recovering || _capturePolicy == NavigationBaselineCapturePolicy.TaskOwnedTimer;
                attempt.Stage = checkChat ? "recognizing_chat" : "recognizing_world";
                var worldEvidence = !checkChat
                    ? AgentWorldRecognizer.Recognize(frame.Frame)
                    : NavigationBaselineCapturePolicy.RecognizeWorld(frame.Frame, NavigationBaselineCapturePolicy.TaskOwnedTimer, chat =>
                {
                    attempt.ChatCompletedAtMs = NowMs; attempt.ChatState = chat.State.ToString();
                    if (chat.State == Common.BgiVision.ChatUiState.Closed) attempt.Stage = "recognizing_world";
                });
                attempt.WorldCompletedAtMs = NowMs;
                if (worldEvidence != AgentWorldEvidence.WorldHud) throw new InvalidOperationException($"world_not_ready: {worldEvidence}");
                attempt.Stage = "recognizing_motion";
                var motion = AgentMotionRecognizer.Recognize(frame.Frame, true);
                attempt.MotionCompletedAtMs = NowMs;
                if (motion.Status != AgentMotionStatus.Normal || motion.Method != AgentMotionEvidence.MethodName
                    || motion.SpaceKeyMatched != false || motion.XKeyMatched is null)
                    throw new InvalidOperationException($"non_normal_motion: {motion.Status}/{motion.Reason}");
                attempt.Stage = "preparing_crop";
                using var bgr = new Mat();
                if (frame.Frame.Channels() == 4) Cv2.CvtColor(frame.Frame, bgr, ColorConversionCodes.BGRA2BGR);
                using var content = new CaptureContent((frame.Frame.Channels() == 4 ? bgr : frame.Frame).Clone(), 0, 0, _runtime.SystemInfo);
                using var minimap = new Mat(content.CaptureRectArea.SrcMat, MapAssets.Get(content.CaptureRectArea).MimiMapRect);
                attempt.CropCompletedAtMs = NowMs;
                attempt.Stage = "preparing_minimap";
                using var prepared = _yaw.TryPrepare(minimap, 0.2f);
                attempt.PreprocessingCompletedAtMs = NowMs;
                if (prepared is null) throw new InvalidOperationException("yaw_unrecognized");
                var yaw = prepared.YawDegrees;
                var yawConfidence = prepared.YawConfidence;
                attempt.Stage = "recognizing_position";
                var position = _map!.GetPreparedLocalPosition(prepared, _anchor.X, _anchor.Y, 0);
                if (position == default) throw new InvalidOperationException("local_position_unrecognized");
                var match = _map.PrevSuccessResult; // Only this successful current call may supply confidence/layer.
                var world = _map.ConvertImageCoordinatesToGenshinMapCoordinates(position)
                    ?? throw new InvalidOperationException("local_position_unrecognized");
                var geometry = NavigationBaselineTask.Geometry(world.X, world.Y);
                var sample = new NavigationBaselineSample(world.X, world.Y, yaw, DateTimeOffset.UtcNow, source.CaptureEpoch,
                    source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, match.Confidence, yawConfidence, match.Layer?.LayerId ?? "",
                    new("normal", motion.Method, false, motion.XKeyMatched.Value, motion.RecognitionMs),
                    NavigationBaselineTask.SourceAge(source, NowMs), Navigation.GetTargetOrientation(_endpoint!, position),
                    geometry.Distance, geometry.Projection, geometry.CrossTrack, new(observationStarted, requested, returned, NowMs));
                attempt.RecognitionCompletedAtMs = sample.Timing.RecognitionCompletedAtMs; attempt.Stage = "validating_pose";
                if (_supportsRecovery && NavigationBaselineRecovery.HardPoseRejection(sample) is { } hardPose)
                    throw new InvalidOperationException(hardPose);
                _activeFinalVerification?.ValidatePose(sample);
                if (_supportsRecovery) ValidateSource(source, "after_recognition", attempt, ct);
                if (NavigationBaselineTask.PoseRejection(sample) is { } rejection) throw new InvalidOperationException(rejection);
                CheckAvailable(ct); ValidateSource(source, "validating_source", attempt, ct);
                if (_activeFinalVerification is { } final)
                {
                    if (retainImage != "final" || stageFinalRows is null)
                        throw new InvalidOperationException("final_verification_read_context_missing");
                    attempt.Stage = "retaining_image";
                    Mat? candidate = frame.Frame.Clone();
                    Mat? previous = null;
                    try
                    {
                        attempt.Stage = "rechecking_target_source";
                        final.Admit(sample, _observationAttempts.Count - 1, attempt, stageFinalRows,
                            () =>
                            {
                                // No allocations, disposal or callbacks after the final freshness/row checks.
                                previous = _finalImage; _finalImage = candidate;
                                _finalImageSource = source; candidate = null;
                            }, () => CheckAvailable(ct), ct);
                        attempt.Stage = "completed";
                    }
                    finally { candidate?.Dispose(); previous?.Dispose(); }
                    return sample;
                }
                attempt.Stage = "retaining_image";
                if (retainImage == "initial") { _initialImage?.Dispose(); _initialImage = frame.Frame.Clone(); _initialImageSource = source; }
                else if (retainImage == "final") { _finalImage?.Dispose(); _finalImage = frame.Frame.Clone(); _finalImageSource = source; }
                attempt.Stage = "rechecking_target_source";
                CheckAvailable(ct); ValidateSource(source, "validating_source", attempt, ct);
                attempt.Stage = "completed";
                return sample;
            }
            catch (Exception exception)
            {
                if (poll.EndedAtMs is null) poll.Error = NavigationBaselineObservationAttempt.DescribeError(exception);
                throw;
            }
            finally
            {
                poll.EndedAtMs ??= NowMs;
                // The out value is assigned even on backend throw; do not lose the failed invocation's stages.
                poll.RetainTiming(captureTiming, poll.Error is not null, ref _retainedCaptureTimings,
                    readbackPending: poll.Result == "readback_pending");
                _lastCaptureTiming = captureTiming is null ? null : (poll, captureTiming);
            }
        }
    });

    /// <summary>Expected Pending uses only the existing source-wait cadence/guards; it cannot renew a lease or reset a window.</summary>
    internal static async Task WaitForReadbackAsync(NavigationBaselineCapturePoll poll, Action checkAvailable,
        Func<double> clock, Func<double, CancellationToken, Task> waitUntil, bool recovering, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        checkAvailable();
        poll.WaitStartedAtMs = clock();
        poll.WaitRequestedDeadlineMs = poll.WaitStartedAtMs + (recovering ? NavigationBaselineRecovery.RetryDelayMs : 5);
        try { await waitUntil(poll.WaitRequestedDeadlineMs.Value, ct).ConfigureAwait(false); }
        finally { poll.WaitExitedAtMs = clock(); }
        ct.ThrowIfCancellationRequested();
        checkAvailable();
    }

    /// <summary>Admit a flat row before capture; capacity loss stops the run rather than silently dropping evidence.</summary>
    internal static NavigationBaselineCapturePoll BeginCapturePoll(List<NavigationBaselineCapturePoll> polls, int observationIndex, double startedAtMs)
    {
        if (polls.Count >= MaximumCapturePolls) throw new InvalidOperationException("capture_diagnostics_capacity_exceeded");
        var poll = new NavigationBaselineCapturePoll(observationIndex, startedAtMs);
        polls.Add(poll);
        return poll;
    }

    /// <summary>Retain a failed read in finally without native input or IO; capacity failure is explicit and never truncates.</summary>
    internal static async Task<NavigationBaselineSample> RecordObservationAsync(List<NavigationBaselineObservationAttempt> attempts,
        Func<double> clock, Func<string?> leaseFault, Func<NavigationBaselineObservationAttempt, Task<NavigationBaselineSample>> read)
    {
        if (attempts.Count >= NavigationBaselineTask.MaximumObservations)
            throw new InvalidOperationException("observation_diagnostics_capacity_exceeded");
        var attempt = new NavigationBaselineObservationAttempt(clock());
        attempts.Add(attempt);
        try { return await read(attempt).ConfigureAwait(false); }
        catch (Exception exception) { attempt.Error = NavigationBaselineObservationAttempt.DescribeError(exception); throw; }
        finally { attempt.EndedAtMs = clock(); attempt.LeaseFault = leaseFault(); }
    }

    /// <summary>Check the actual measured pose again before entering the input owner's final source/target gate.</summary>
    private void ValidateDispatch(NavigationBaselineSample sample, CancellationToken ct)
    {
        if (_supportsRecovery)
        {
            if (NavigationBaselineRecovery.HardPoseRejection(sample) is { } hardPose) throw new InvalidOperationException(hardPose);
            if (NavigationBaselineRecovery.HardSourceRejection(sample.Source, NowMs, _lastSource) is { } hardSource)
                throw new InvalidOperationException(hardSource);
            if (_lastSource != sample.Source) throw new InvalidOperationException("dispatch_source_mismatch");
            ValidateSource(sample.Source, "before_dispatch");
        }
        CheckAvailable(ct);
        if (NavigationBaselineTask.PoseRejection(sample) is { } rejection) throw new InvalidOperationException(rejection);
        ValidateSource(sample.Source);
        if (_lastSource != sample.Source) throw new InvalidOperationException("dispatch_source_mismatch");
        ct.ThrowIfCancellationRequested();
    }

    /// <summary>Reuse the existing measured-yaw gains with the pinned horizontal mouse sink, never a second recognizer.</summary>
    public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct)
    {
        ValidateDispatch(sample, ct);
        NavigationBaselineInputEvent? intent = null;
        CameraRotateTask.ApplyMeasuredRotation((float)sample.TargetHeadingDegrees, (float)sample.YawDegrees,
            _runtime.SystemInfo.DpiScale, ct, (dx, dy) => intent = _lease.Rotate(sample.Source, dx, ct));
        if (intent is null) throw new InvalidOperationException("camera_correction_not_dispatched");
        if (intent.Kind == "camera") { _inputBarrier = intent.CompletedAtMs; _responseMs = 80; }
        return intent;
    }

    /// <summary>Only real W-down moves the response barrier; renewal performs no repeated native keydown.</summary>
    public NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
    {
        ValidateDispatch(sample, ct);
        var intent = _lease.Forward(sample.Source, ct);
        if (intent.Kind == "w_down") { _inputBarrier = intent.CompletedAtMs; _responseMs = 60; }
        return intent;
    }

    /// <summary>Fresh response evidence follows a real W release before later camera alignment.</summary>
    public NavigationBaselineInputEvent ReleaseForward()
    {
        var intent = _lease.ReleaseForward();
        if (intent.Kind == "w_up") { _inputBarrier = intent.CompletedAtMs; _responseMs = 80; }
        return intent;
    }

    /// <summary>Pin the completed release cutoff once; final verification cannot revive controller input.</summary>
    public void CloseInput()
    {
        _recoveryEnabled = false;
        var completed = _lease.Close();
        if (!_inputClosed) { _inputClosed = true; _inputBarrier = completed; _responseMs = 80; }
    }

    /// <summary>One fixed no-input final window; partial admitted samples stay in task evidence on failure.</summary>
    public async Task ReadFinalSamplesAsync(double ownerDeadlineMs,
        Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission> stageRows, CancellationToken ct)
    {
        if (!_supportsRecovery || !_inputClosed || ForwardHeld || Fault is not null || ReleaseError is not null
            || _recovering || _recoveryEnabled || _activeFinalVerification is not null || _finalVerificationWindow is not null)
            throw new InvalidOperationException("final_verification_requires_input_closed");
        CheckAvailable(ct);
        var final = new NavigationBaselineFinalVerification(() => NowMs, _inputBarrier, ownerDeadlineMs,
            _lastSource ?? throw new InvalidOperationException("native_source_unavailable"),
            _observationAttempts.Count, _capturePolls.Count);
        _finalVerificationWindow = final.Record; _activeFinalVerification = final;
        try
        {
            await final.CollectAsync(token => ReadPoseCoreAsync("final", token, stageRows), WaitUntilAsync, ct)
                .ConfigureAwait(false);
        }
        finally
        {
            final.Record.ObservationEnd = _observationAttempts.Count;
            final.Record.PollEnd = _capturePolls.Count;
            _activeFinalVerification = null;
        }
    }

    /// <summary>Recovery is explicit and cannot precede the first independently verified anchor.</summary>
    public void EnableRecovery()
    {
        if (!_supportsRecovery || _inputClosed || _recoveryEnabled) throw new InvalidOperationException("recovery_not_available");
        _lease.EnableRecovery(); _recoveryEnabled = true;
    }

    /// <summary>Release first, wait with no input, then rearm from fresh same-frame evidence; no controller step is replayed.</summary>
    public async Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired interruption,
        double ownerDeadlineMs, CancellationToken ct)
    {
        if (!_recoveryEnabled || _recovering || _inputClosed || !double.IsFinite(ownerDeadlineMs))
            throw new InvalidOperationException("recovery_not_available");
        ct.ThrowIfCancellationRequested();
        var pause = _lease.PauseForRecovery(interruption, ct);
        if (_recoveryAttempts.Count >= NavigationBaselineRecovery.MaximumRecoveries)
            throw new InvalidOperationException("recovery_limit_exceeded");
        _recoveryDeadline = Math.Min(ownerDeadlineMs, pause.StartedAtMs + NavigationBaselineRecovery.MaximumWaitMs);
        _recoveryPollStart = _capturePolls.Count;
        var attempt = new NavigationBaselineRecoveryAttempt { Pause = pause, TriggerCause = interruption.Cause, TriggerStage = interruption.Stage,
            TriggerSource = interruption.ObservedSource, DeadlineAtMs = _recoveryDeadline,
            ObservationStart = _observationAttempts.Count, PollStart = _capturePolls.Count };
        _recoveryAttempts.Add(attempt);
        _recovering = true;
        _inputBarrier = pause.ReleasedAtMs; _responseMs = 80;
        using var window = CancellationTokenSource.CreateLinkedTokenSource(ct);
        try
        {
            if (_recoveryDeadline <= NowMs) throw new InvalidOperationException("recovery_deadline_exceeded");
            window.CancelAfter(TimeSpan.FromMilliseconds(Math.Max(0, _recoveryDeadline - NowMs)));
            while (true)
            {
                CheckAvailable(window.Token);
                try
                {
                    var sample = await ReadPoseAsync(null, window.Token).ConfigureAwait(false);
                    // Native recognition/route checks and the final gate use this exact newly admitted source.
                    ValidateDispatch(sample, window.Token);
                    _lease.ResumeRecovery(pause, sample.Source, window.Token);
                    attempt.Outcome = "resumed"; attempt.ResumedSample = sample;
                    return sample;
                }
                catch (NavigationBaselineRecoveryRequired retry) when (retry.Cause == NavigationBaselineRecoveryCause.SourceAge
                    && (retry.Pause is null || ReferenceEquals(retry.Pause, pause)))
                {
                    // Every failed native read already owns a bounded observation/poll row. Do not reset the window.
                    await WaitUntilAsync(Math.Min(NowMs + NavigationBaselineRecovery.RetryDelayMs, _recoveryDeadline), window.Token)
                        .ConfigureAwait(false);
                }
            }
        }
        catch (Exception exception)
        {
            attempt.Outcome = "failed";
            attempt.Error = exception is OperationCanceledException && !ct.IsCancellationRequested
                ? "recovery_deadline_exceeded" : NavigationBaselineObservationAttempt.DescribeError(exception);
            if (exception is OperationCanceledException && !ct.IsCancellationRequested)
                throw new NavigationBaselineRecoveryTimeoutException(exception);
            throw;
        }
        finally
        {
            attempt.ObservationEnd = _observationAttempts.Count; attempt.PollEnd = _capturePolls.Count;
            attempt.EndedAtMs = NowMs; _recovering = false;
        }
    }

    /// <summary>Short waits allow the independent lease to release during source barriers or delayed recognition.</summary>
    public async Task WaitUntilAsync(double deadlineMs, CancellationToken ct)
    {
        while (NowMs < deadlineMs)
        {
            CheckAvailable(ct);
            await Task.Delay(TimeSpan.FromMilliseconds(Math.Min(5, Math.Max(1, deadlineMs - NowMs))), Token).ConfigureAwait(false);
        }
        CheckAvailable(ct);
    }

    /// <summary>Write one new bounded file atomically; never overwrite prior run evidence.</summary>
    private static string WriteEvidenceFile(string directory, string name, byte[] bytes, int maximum)
    {
        if (bytes.Length > maximum) throw new InvalidOperationException("evidence_file_capacity_exceeded");
        var destination = Path.Combine(directory, name);
        var pending = destination + ".pending";
        using (var stream = new FileStream(pending, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        { stream.Write(bytes); stream.Flush(true); }
        File.Move(pending, destination, false);
        return Convert.ToHexString(SHA256.HashData(bytes));
    }

    /// <summary>A bound that stopped retention must remain explicitly incomplete even if its partial journal writes successfully.</summary>
    internal static bool EvidenceIsComplete(NavigationBaselineRunResult result) =>
        result.Error?.Contains("capacity", StringComparison.Ordinal) != true;

    /// <summary>All encoding/disk writes occur after permanent input closure; artifacts remain system-generated intent/pose evidence.</summary>
    public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result, NavigationBaselineDecision[] decisions,
        NavigationBaselineScheduleWait[] scheduleWaits)
    {
        if (!_inputClosed && Fault is null) throw new InvalidOperationException("evidence_requires_input_closed");
        if (ForwardHeld) throw new InvalidOperationException("evidence_requires_forward_released");
        if (decisions.Length > NavigationBaselineTask.MaximumObservations) throw new InvalidOperationException("observation_capacity_exceeded");
        if (scheduleWaits.Length > NavigationBaselineTask.MaximumObservations || _observationAttempts.Count > NavigationBaselineTask.MaximumObservations)
            throw new InvalidOperationException("observation_diagnostics_capacity_exceeded");
        if (_capturePolls.Count > MaximumCapturePolls) throw new InvalidOperationException("capture_diagnostics_capacity_exceeded");
        // This final invocation can be fast and successful even when its following input gate expired. No capture is repeated.
        if (_lastCaptureTiming is { } last) last.Poll.RetainTiming(last.Timing, true, ref _retainedCaptureTimings);
        _lastCaptureTiming = null;
        var directory = Global.Absolute(Path.Combine("User", "NavigationBaselines", _runId));
        if (Directory.Exists(directory)) throw new InvalidOperationException("evidence_run_directory_exists");
        Directory.CreateDirectory(directory);
        string? initialPath = null, initialHash = null, finalPath = null, finalHash = null;
        if (_initialImage is not null)
        {
            if (!Cv2.ImEncode(".png", _initialImage, out var bytes) || bytes.Length == 0)
                throw new InvalidOperationException("initial_image_encoding_failed");
            initialHash = WriteEvidenceFile(directory, "initial.png", bytes, MaximumPngBytes);
            initialPath = Path.Combine(directory, "initial.png");
        }
        if (_finalImage is not null)
        {
            if (!Cv2.ImEncode(".png", _finalImage, out var bytes) || bytes.Length == 0)
                throw new InvalidOperationException("final_image_encoding_failed");
            finalHash = WriteEvidenceFile(directory, "final.png", bytes, MaximumPngBytes);
            finalPath = Path.Combine(directory, "final.png");
        }
        if (result.Verified && (initialPath is null || finalPath is null)) throw new InvalidOperationException("successful_evidence_images_missing");
        var complete = EvidenceIsComplete(result);
        var report = new NavigationBaselineJournal { RunId = _runId,
            ReadbackMode = _readbackMode,
            GameProcessId = _gameProcessId, WindowsSessionId = _sessionId, WorkflowResult = result,
            Observations = decisions, InputTransitions = _lease.Events, ScheduleWaits = scheduleWaits,
            ObservationAttempts = _observationAttempts, CapturePolls = _capturePolls,
            RecoveryPauses = _lease.RecoveryPauses, RecoveryAttempts = _recoveryAttempts,
            FinalVerificationWindow = _finalVerificationWindow,
            InitialImage = new(initialPath, initialHash, _initialImageSource),
            FinalImage = new(finalPath, finalHash, _finalImageSource) };
        var json = report.Serialize();
        var journalHash = WriteEvidenceFile(directory, "controller-intent-and-pose.json", json, MaximumJournalBytes);
        return Task.FromResult(new NavigationBaselineEvidence(complete, Path.Combine(directory, "controller-intent-and-pose.json"),
            journalHash, initialPath, initialHash, finalPath, finalHash) { ReadbackMode = _readbackMode });
    }

    /// <summary>Drain the lease before disposing its pinned native resources; retain ordinary TaskRunner release cleanup.</summary>
    public async ValueTask DisposeAsync()
    {
        try { await _lease.DisposeAsync().ConfigureAwait(false); }
        finally
        {
            try { if (ReferenceEquals(InputHub.Backend, _runtime.Input)) InputHub.ReleaseAll(); }
            finally
            {
                _lifetime.Dispose(); _game.Dispose(); _yaw.Dispose();
                _initialImage?.Dispose(); _finalImage?.Dispose();
            }
        }
    }
}
