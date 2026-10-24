using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Deterministic initial-source admission; no native capture, timer, game, input or model execution.</summary>
public sealed class NavigationBaselineInitialReadinessTests
{
    /// <summary>One synthetic immutable capture lifetime.</summary>
    private static readonly Guid Epoch = Guid.Parse("713e569b-05ac-4a78-aadf-8a29455fcd92");
    /// <summary>Independent raw and acquisition clocks on the production QPC origin.</summary>
    private static GameCaptureSourceInfo Source(double raw, double? acquisition = null) =>
        new(Epoch, (long)(raw * 10000), (long)((acquisition ?? raw) * Stopwatch.Frequency / 1000));
    /// <summary>A valid same-frame initial pose, independent of a later movement command.</summary>
    private static NavigationBaselineSample Sample(GameCaptureSourceInfo source, double now) =>
        new(NavigationBaselineTask.StartX, NavigationBaselineTask.StartY, 47, DateTimeOffset.UnixEpoch,
            source.CaptureEpoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, .999, .8,
            "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 1),
            NavigationBaselineTask.SourceAge(source, now), 47, NavigationBaselineTask.Length, 0, 0,
            new(now, now, now, now));
    /// <summary>Match the real header/age order; only code after this method represents recognition.</summary>
    private static NavigationBaselineSample Capture(NavigationBaselineInitialReadiness window, GameCaptureSourceInfo source,
        double now, CancellationToken ct, int width = 1920)
    {
        using var reservation = window.BeginCapture(ct);
        reservation.CompleteCapture();
        window.ValidateHeader(source, width, 1080, 3, ct);
        window.ValidateSource(source, "after_capture", window.Record.ObservationStart + window.Record.ReadCount - 1,
            window.Record.PollStart + window.Record.PollCount - 1, ct);
        return Sample(source, now);
    }
    /// <summary>Use the same Pending validator as the native integration, before refunding exactly one reservation.</summary>
    private static void Pending(NavigationBaselineInitialReadiness window, GameCapturePendingReadback pending, double now)
    {
        using var reservation = window.BeginCapture(default);
        window.ValidatePending(pending, (long)(now * Stopwatch.Frequency / 1000));
        reservation.CompletePending();
    }

    /// <summary>The old staged image is discarded before recognition; its fresh successor alone supplies the first pose.</summary>
    [Fact]
    public async Task StalePendingThenFreshRefillRecognizesOnlyFreshPixels()
    {
        double now = 1800; var old = Source(1100, 1140);
        var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var pending = new GameCapturePendingReadback(293, old, (long)(1141 * Stopwatch.Frequency / 1000), 1920, 1080, null);
        var reads = 0; var recognized = new List<GameCaptureSourceInfo>(); GameCaptureSourceInfo? consumed = null;
        var result = await window.ReadAsync(token =>
        {
            reads++;
            if (reads == 1)
            {
                for (var i = 0; i < 6; i++) { Pending(window, pending, now); now += 5; }
                Assert.Null(window.SeenSource); Assert.Null(consumed);
            }
            var source = reads == 1 ? old : Source(now - 2);
            var sample = Capture(window, source, now, token);
            consumed = source; recognized.Add(source);
            return Task.FromResult(sample);
        }, (deadline, _) => { now = deadline; return Task.CompletedTask; }, default);
        Assert.Equal(2, reads); Assert.Single(recognized); Assert.Equal(result.Source, consumed);
        Assert.NotEqual(old, result.Source); Assert.Equal(1, window.Record.SourceAgeDiscards);
        Assert.Equal(8, window.Record.PollCount); Assert.Equal(6, window.Record.PendingPollCount);
        Assert.Equal(2, window.Record.CaptureCount); Assert.Equal(1, window.Record.AdmittedReadIndex);
        Assert.Equal("source_age_discard", window.Record.SourceChecks[0].Disposition);
        Assert.Equal("completed", window.Record.Outcome); Assert.Null(window.Record.Error);
    }

    /// <summary>Exactly150ms is allowed; either older conservative clock triggers the same strict rejection.</summary>
    [Theory]
    [InlineData(1000, 1000, 1150, false)]
    [InlineData(1000, 1000, 1150.01, true)]
    [InlineData(1001, 1000, 1150.01, true)]
    [InlineData(1000, 1001, 1150.01, true)]
    public void ExactFreshnessBoundary(double raw, double acquired, double now, bool stale)
    {
        var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var source = Source(raw, acquired); window.ValidateHeader(source, 1920, 1080, 3, default);
        if (stale) Assert.Throws<NavigationBaselineInitialReadiness.SourceAgeException>(() =>
            window.ValidateSource(source, "after_capture", 0, 0, default));
        else Assert.Same(source, window.ValidateSource(source, "after_capture", 0, 0, default));
    }

    /// <summary>Pinning a stale header never excuses changed identity/geometry or missing/malformed/future clocks.</summary>
    [Theory]
    [InlineData("epoch", "source_epoch_changed")]
    [InlineData("regression", "native_source_regressed")]
    [InlineData("restamp", "native_source_regressed")]
    [InlineData("geometry", "native_frame_geometry_changed")]
    [InlineData("missing", "invalid_native_source")]
    [InlineData("invalid", "invalid_native_source")]
    [InlineData("future", "acquisition_in_future")]
    [InlineData("channels", "unsupported_native_frame")]
    public void HardHeaderFailureWinsOverOldAge(string change, string expected)
    {
        var window = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, "task_owned_timer");
        var first = Source(1000); window.ValidateHeader(first, 1920, 1080, 3, default);
        GameCaptureSourceInfo? source = change switch
        {
            "epoch" => first with { CaptureEpoch = Guid.NewGuid() }, "regression" => Source(999),
            "restamp" => first with { AcquiredAtStopwatchTicks = first.AcquiredAtStopwatchTicks + 1 },
            "missing" => null, "invalid" => first with { SourceTimestamp100ns = 0 },
            "future" => Source(1000, 2001), _ => first
        };
        Assert.Equal(expected, Assert.Throws<InvalidOperationException>(() =>
            window.ValidateHeader(source, change == "geometry" ? 1919 : 1920, 1080,
                change == "channels" ? 1 : 3, default)).Message);
        Assert.Same(first, window.SeenSource); Assert.Empty(window.Record.SourceChecks);
    }

    /// <summary>The owned policy's existing chat geometry limit is hard even before stale pixels are recognized.</summary>
    [Fact]
    public void OversizedOwnedChatGeometryCannotHideBehindAge()
    {
        var window = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, "task_owned_timer");
        Assert.StartsWith("unsupported_chat_frame_geometry", Assert.Throws<InvalidOperationException>(() =>
            window.ValidateHeader(Source(1000), 1921, 1080, 3, default)).Message);
        Assert.Null(window.SeenSource);
    }

    /// <summary>Even the first Pending cannot refund known unsupported geometry; it still cannot pin an epoch/source.</summary>
    [Theory]
    [InlineData("task_owned_timer", 1921, "unsupported_chat_frame_geometry")]
    [InlineData("shared", 3841, "unsupported_native_frame")]
    public void UnsupportedFirstPendingRetainsCharge(string policy, int width, string error)
    {
        var window = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, policy);
        var pending = new GameCapturePendingReadback(1, Source(1000), (long)(1001 * Stopwatch.Frequency / 1000), width, 1080, null);
        Assert.StartsWith(error, Assert.Throws<InvalidOperationException>(() => Pending(window, pending, 2000)).Message);
        Assert.Equal(1, window.Record.CaptureCount); Assert.Equal(0, window.Record.PendingPollCount); Assert.Null(window.SeenSource);
    }

    /// <summary>A different collector's typed signal cannot authorize an initial retry.</summary>
    [Fact]
    public async Task ForeignAgeSignalIsTerminal()
    {
        var window = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, "task_owned_timer");
        var other = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, "task_owned_timer");
        var original = new NavigationBaselineInitialReadiness.SourceAgeException(other);
        var failure = await Assert.ThrowsAsync<NavigationBaselineInitialReadiness.SourceAgeException>(() => window.ReadAsync(
            _ => throw original, (_, _) => throw new Exception("must not wait"), default));
        Assert.Same(original, failure); Assert.Equal(1, window.Record.ReadCount); Assert.Equal(0, window.Record.SourceAgeDiscards);
    }

    /// <summary>Unavailable/native failures keep the pre-call charge and never turn into Pending or another read.</summary>
    [Theory]
    [InlineData("capture_unavailable")][InlineData("native_capture_failed")]
    public async Task NullAndThrowKeepTheirReservation(string error)
    {
        var window = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, "task_owned_timer");
        var failure = await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(token =>
        { using var reservation = window.BeginCapture(token); throw new InvalidOperationException(error); },
            (_, _) => throw new Exception("must not wait"), default));
        Assert.Equal(error, failure.Message); Assert.Equal(1, window.Record.CaptureCount);
        Assert.Equal(0, window.Record.PendingPollCount); Assert.Equal(1, window.Record.ReadCount); Assert.Null(window.SeenSource);
    }

    /// <summary>Known vision/pose/native failures are terminal after a fresh capture; they never produce another read.</summary>
    [Theory]
    [InlineData("chat_not_closed")][InlineData("world_not_ready")][InlineData("non_normal_motion")]
    [InlineData("yaw_unrecognized")][InlineData("wrong_layer")][InlineData("game_target_lost")]
    [InlineData("capture_unavailable")][InlineData("native_capture_failed")]
    public async Task HardFailureNeverRetries(string reason)
    {
        double now = 1100; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var reads = 0;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(token =>
        { reads++; Capture(window, Source(1090), now, token); throw new InvalidOperationException(reason); },
            (_, _) => throw new InvalidOperationException("Unexpected retry."), default));
        Assert.Equal(reason, error.Message); Assert.Equal(1, reads); Assert.Equal(0, window.Record.SourceAgeDiscards);
        Assert.Null(window.Record.AdmittedReadIndex); Assert.Equal("failed", window.Record.Outcome);
    }

    /// <summary>Age that expires after recognition or cleanup is terminal and leaves the consumed/seen source intact.</summary>
    [Theory]
    [InlineData("after_recognition")][InlineData("validating_source")][InlineData("returning_initial_pose")]
    public async Task PostCaptureAgeNeverRetries(string stage)
    {
        double now = 1100; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var source = Source(1090); var reads = 0;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(token =>
        {
            reads++; var sample = Capture(window, source, now, token); now = 1241;
            if (stage != "returning_initial_pose") window.ValidateSource(source, stage, 0, 0, token);
            return Task.FromResult(sample);
        }, (_, _) => throw new InvalidOperationException("Unexpected retry."), default));
        Assert.Equal("native_source_unavailable_or_stale", error.Message); Assert.Equal(1, reads);
        Assert.Same(source, window.SeenSource); Assert.Equal(0, window.Record.SourceAgeDiscards);
    }

    /// <summary>Cooperative native overrun cannot cause recognition or acceptance after the clipped deadline.</summary>
    [Fact]
    public async Task NativeOverrunStopsBeforeRecognition()
    {
        double now = 1000; var window = new NavigationBaselineInitialReadiness(() => now, 1050, 0, 0, "task_owned_timer");
        var recognized = false;
        await Assert.ThrowsAsync<NavigationBaselineInitialReadiness.DeadlineException>(() => window.ReadAsync(token =>
        {
            using var reservation = window.BeginCapture(token); now = 1050; reservation.CompleteCapture();
            var source = Source(1049); window.ValidateHeader(source, 1920, 1080, 3, token);
            window.ValidateSource(source, "after_capture", 0, 0, token); recognized = true;
            return Task.FromResult(Sample(source, now));
        }, (_, _) => Task.CompletedTask, default));
        Assert.False(recognized); Assert.Equal(1050, window.Record.DeadlineAtMs); Assert.Null(window.Record.AdmittedReadIndex);
    }

    /// <summary>Repeated stale cache tuples do not reset clocks or escape the32 completed-capture/read bounds.</summary>
    [Fact]
    public async Task RepeatedStaleSourceExhaustsFixedReadBudget()
    {
        double now = 2000; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var source = Source(1000);
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(token =>
            Task.FromResult(Capture(window, source, now, token)), (at, _) => { now = at; return Task.CompletedTask; }, default));
        Assert.Equal("initial_readiness_read_limit_exceeded", error.Message); Assert.Equal(32, window.Record.ReadCount);
        Assert.Equal(32, window.Record.CaptureCount); Assert.Equal(32, window.Record.SourceAgeDiscards);
        Assert.Equal(4000, window.Record.DeadlineAtMs); Assert.Same(source, window.SeenSource);
    }

    /// <summary>Cancellation and unowned cancellation exceptions retain their actual token/origin without retry.</summary>
    [Theory]
    [InlineData(true)][InlineData(false)]
    public async Task CancellationIsNotAgeOrAnInventedWindowTimeout(bool cancelOwner)
    {
        using var owner = new CancellationTokenSource(); using var foreign = new CancellationTokenSource();
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        var original = new OperationCanceledException(foreign.Token);
        var error = await Assert.ThrowsAnyAsync<OperationCanceledException>(() => window.ReadAsync(_ =>
        { if (cancelOwner) owner.Cancel(); throw cancelOwner ? new OperationCanceledException(owner.Token) : original; },
            (_, _) => throw new InvalidOperationException("Unexpected retry."), owner.Token));
        if (cancelOwner) Assert.Equal(owner.Token, error.CancellationToken); else Assert.Same(original, error);
        Assert.Null(window.Record.AdmittedReadIndex); Assert.Equal(0, window.Record.SourceAgeDiscards);
    }

    /// <summary>One collector cannot be reopened, and closed windows refuse later capture work.</summary>
    [Fact]
    public async Task CompletedWindowCannotBeReused()
    {
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        await window.ReadAsync(token => Task.FromResult(Capture(window, Source(1090), 1100, token)),
            (_, _) => Task.CompletedTask, default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(_ => throw new Exception("must not run"),
            (_, _) => Task.CompletedTask, default));
        Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default));
    }

    /// <summary>Already-cancelled ownership cannot start a read or reserve a capture.</summary>
    [Fact]
    public async Task PreCancelledOwnerDoesNotStartWork()
    {
        using var stop = new CancellationTokenSource(); stop.Cancel();
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => window.ReadAsync(_ => throw new Exception("must not read"),
            (_, _) => throw new Exception("must not wait"), stop.Token));
        Assert.Equal(0, window.Record.ReadCount); Assert.Equal(0, window.Record.PollCount);
    }

    /// <summary>A nonfinite/regressing clock is a hard failure rather than another source-age opportunity.</summary>
    [Theory]
    [InlineData(1099)][InlineData(double.NaN)][InlineData(double.PositiveInfinity)]
    public void InvalidOrRegressingWindowClockIsTerminal(double next)
    {
        double now = 1100; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        now = next;
        Assert.Equal("invalid_initial_readiness_clock", Assert.Throws<InvalidOperationException>(() => window.Check(default)).Message);
        Assert.Equal(0, window.Record.PollCount);
    }

    /// <summary>Ready/error calls stop at32 independently of valid Pending refunds.</summary>
    [Fact]
    public void ChargedCaptureBudgetIsIndependentOfPendingRefunds()
    {
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        for (var i = 0; i < 32; i++) { using var reservation = window.BeginCapture(default); }
        Assert.Equal("initial_readiness_capture_limit_exceeded", Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default)).Message);
        Assert.Equal(32, window.Record.PollCount); Assert.Equal(0, window.Record.PendingPollCount);
    }

    /// <summary>A classified Pending retains its refund when a later wait reaches cancellation or the fixed deadline.</summary>
    [Theory]
    [InlineData(false)][InlineData(true)]
    public async Task PendingWaitCannotEscapeWindow(bool cancel)
    {
        double now = 1100; using var stop = new CancellationTokenSource();
        var window = new NavigationBaselineInitialReadiness(() => now, 1150, 0, 0, "task_owned_timer");
        Pending(window, new(1, Source(1000), (long)(1001 * Stopwatch.Frequency / 1000), 1920, 1080, null), now);
        Task Wait() => NativeNavigationBaselineOperations.WaitForReadbackAsync(new(0, now), () => window.Check(stop.Token), () => now,
            (_, _) => { if (cancel) stop.Cancel(); else now = 1150; return Task.CompletedTask; }, false, stop.Token);
        if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(Wait);
        else await Assert.ThrowsAsync<NavigationBaselineInitialReadiness.DeadlineException>(Wait);
        Assert.Equal(1, window.Record.PollCount); Assert.Equal(1, window.Record.PendingPollCount); Assert.Equal(0, window.Record.CaptureCount);
    }

    /// <summary>Pending never pins a source, repeated settlement cannot steal a later charge, and malformed metadata stays charged.</summary>
    [Fact]
    public void ConservativeReservationAndPendingOwnership()
    {
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        var pending = new GameCapturePendingReadback(1, Source(1000), (long)(1001 * Stopwatch.Frequency / 1000), 1920, 1080, null);
        Pending(window, pending, 1100); Assert.Null(window.SeenSource); Assert.Null(window.Width);
        var completed = window.BeginCapture(default); completed.CompleteCapture(); completed.Dispose();
        using (var next = window.BeginCapture(default))
        {
            Assert.Throws<InvalidOperationException>(completed.CompletePending);
            Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default));
        }
        Assert.Throws<InvalidOperationException>(() => Pending(window, pending with { SubmissionId = 0 }, 1100));
        Assert.Equal(4, window.Record.PollCount); Assert.Equal(3, window.Record.CaptureCount);
        Assert.Equal(1, window.Record.PendingPollCount); Assert.Null(window.SeenSource);
    }

    /// <summary>Four hundred settled Pending polls stop before another native call even if the test clock does not advance.</summary>
    [Fact]
    public void PendingBudgetIsFiniteAndCannotRefundGlobalPolls()
    {
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        var pending = new GameCapturePendingReadback(1, Source(1000), (long)(1001 * Stopwatch.Frequency / 1000), 1920, 1080, null);
        for (var i = 0; i < 400; i++) Pending(window, pending, 1100);
        Assert.Equal("initial_readiness_pending_poll_limit_exceeded", Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default)).Message);
        Assert.Equal(400, window.Record.PollCount); Assert.Equal(0, window.Record.CaptureCount);
    }

    /// <summary>The stale pixel header constrains subsequent unpublished metadata without making Pending a new consumed source.</summary>
    [Theory]
    [InlineData("epoch")][InlineData("geometry")][InlineData("regression")]
    public void StaleHeaderConstrainsLaterPending(string change)
    {
        var window = new NavigationBaselineInitialReadiness(() => 2000, 31000, 0, 0, "task_owned_timer");
        var source = Source(1000); window.ValidateHeader(source, 1920, 1080, 3, default);
        var pending = new GameCapturePendingReadback(1, source, (long)(1001 * Stopwatch.Frequency / 1000), 1920, 1080, null);
        pending = change switch { "epoch" => pending with { SourceInfo = source with { CaptureEpoch = Guid.NewGuid() } },
            "geometry" => pending with { Width = 1919 }, _ => pending with { SourceInfo = Source(999) } };
        Assert.Throws<InvalidOperationException>(() => Pending(window, pending, 2000));
        Assert.Same(source, window.SeenSource); Assert.Equal(1, window.Record.CaptureCount); Assert.Equal(0, window.Record.PendingPollCount);
    }

    /// <summary>Exercise actual native admission guards before any runtime access, using a no-worker/no-op input lease.</summary>
    [Theory]
    [InlineData("closed")][InlineData("recovery")][InlineData("recovering")][InlineData("started")]
    [InlineData("prior_read")][InlineData("prior_source")][InlineData("prior_input")]
    public async Task NativeEntryRejectsPriorWorkWithoutCapture(string condition)
    {
        await using var lease = new NavigationBaselineInputLease(() => 1100, () => true, () => { }, () => { }, _ => { },
            default, startWatchdog: false, timingContract: "v4");
        var native = (NativeNavigationBaselineOperations)RuntimeHelpers.GetUninitializedObject(typeof(NativeNavigationBaselineOperations));
        Set(native, "_lease", lease); Set(native, "_supportsRecovery", true);
        Set(native, "_observationAttempts", new List<NavigationBaselineObservationAttempt>());
        Set(native, "_capturePolls", new List<NavigationBaselineCapturePoll>());
        switch (condition)
        {
            case "closed": Set(native, "_inputClosed", true); break;
            case "recovery": Set(native, "_recoveryEnabled", true); break;
            case "recovering": Set(native, "_recovering", true); break;
            case "started": Set(native, "_initialReadinessStarted", true); break;
            case "prior_read": Set(native, "_observationAttempts", new List<NavigationBaselineObservationAttempt> { new(1000) }); break;
            case "prior_source": Set(native, "_lastSource", Source(1090)); break;
            case "prior_input": lease.Rotate(Source(1090), 1, default); break;
        }
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => native.ReadInitialPoseAsync(31000, default));
        Assert.StartsWith("initial_readiness_requires_", error.Message);
    }

    /// <summary>The native movement/recovery entrypoints cannot grant authority during initial admission.</summary>
    [Fact]
    public void NativeInputAndRecoveryCannotRunInsideInitialWindow()
    {
        var native = (NativeNavigationBaselineOperations)RuntimeHelpers.GetUninitializedObject(typeof(NativeNavigationBaselineOperations));
        Set(native, "_activeInitialReadiness", new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer"));
        var sample = Sample(Source(1090), 1100);
        Assert.Equal("initial_readiness_input_blocked", Assert.Throws<InvalidOperationException>(() => native.Forward(sample, default)).Message);
        Assert.Equal("initial_readiness_input_blocked", Assert.Throws<InvalidOperationException>(() => native.Rotate(sample, default)).Message);
        Assert.Equal("initial_readiness_input_blocked", Assert.Throws<InvalidOperationException>(() => native.ReleaseForward()).Message);
        Assert.Equal("initial_readiness_input_blocked", Assert.Throws<InvalidOperationException>(native.EnableRecovery).Message);
    }

    /// <summary>Only fixture-private object fields are populated; invalid entry must fail before any real runtime/native dependency.</summary>
    private static void Set(object target, string field, object value) => target.GetType()
        .GetField(field, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(target, value);

    /// <summary>File-only diagnostics preserve exact counts/source joins without enlarging the compact workflow result.</summary>
    [Fact]
    public void InitialEvidenceIsOptionalAndSeparateFromFinalReadiness()
    {
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        var journal = new NavigationBaselineJournal { RunId = new string('a', 32), GameProcessId = 10, WindowsSessionId = 3,
            WorkflowResult = new() { TimingContract = "v4" }, Observations = [], InputTransitions = [], ScheduleWaits = [],
            ObservationAttempts = [], CapturePolls = [new(0, 1100) { InitialReadinessCaptureCharged = false }],
            InitialReadinessWindow = window.Record };
        using var doc = JsonDocument.Parse(journal.Serialize());
        Assert.Equal(1, doc.RootElement.GetProperty("initialReadinessWindow").GetProperty("version").GetInt32());
        Assert.False(doc.RootElement.GetProperty("trainingEligible").GetBoolean());
        Assert.False(doc.RootElement.GetProperty("capturePolls")[0].GetProperty("initialReadinessCaptureCharged").GetBoolean());
        Assert.False(doc.RootElement.GetProperty("capturePolls")[0].TryGetProperty("finalVerificationCaptureCharged", out _));
        Assert.DoesNotContain("initialReadiness", JsonSerializer.Serialize(journal.WorkflowResult));
    }
}
