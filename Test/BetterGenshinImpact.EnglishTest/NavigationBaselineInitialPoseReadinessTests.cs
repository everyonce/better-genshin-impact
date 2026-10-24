using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Initial-only stage retries use a fake clock/read boundary; no capture, native input, timer or model is started.</summary>
public sealed class NavigationBaselineInitialPoseReadinessTests
{
    /// <summary>One immutable synthetic capture lifetime shared by each independent fixture.</summary>
    private static readonly Guid Epoch = Guid.Parse("73563c26-0958-48da-a4bd-11bbf2b83b47");
    /// <summary>The only later source stages the native initial path may use.</summary>
    private static readonly string[] LaterStages = ["after_recognition", "before_initial_retention", "after_initial_retention"];
    /// <summary>Build both native clocks from the same explicit monotonic millisecond value.</summary>
    private static GameCaptureSourceInfo Source(double time) =>
        new(Epoch, (long)(time * 10000), (long)(time * Stopwatch.Frequency / 1000));
    /// <summary>One valid same-frame anchor; the initial collector grants no movement from this object itself.</summary>
    private static NavigationBaselineSample Sample(GameCaptureSourceInfo source, double now) =>
        new(NavigationBaselineTask.StartX, NavigationBaselineTask.StartY, 47, DateTimeOffset.UnixEpoch,
            source.CaptureEpoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, .999, .8,
            "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 1),
            NavigationBaselineTask.SourceAge(source, now), 47, NavigationBaselineTask.Length, 0, 0, new(now, now, now, now));
    /// <summary>Mirror reservation/header/check ownership before any fixture recognition callback.</summary>
    private static NavigationBaselineSample Capture(NavigationBaselineInitialReadiness window, GameCaptureSourceInfo source,
        double now, CancellationToken token)
    {
        using var reservation = window.BeginCapture(token); reservation.CompleteCapture();
        window.ValidateHeader(source, 1920, 1080, 3, token);
        Check(window, source, "after_capture", token);
        return Sample(source, now);
    }
    /// <summary>Every recorded stage references the current read and its actual last charged capture.</summary>
    private static void Check(NavigationBaselineInitialReadiness window, GameCaptureSourceInfo source, string stage,
        CancellationToken token) => window.ValidateSource(source, stage,
        window.Record.ObservationStart + window.Record.ReadCount - 1, window.Record.PollStart + window.Record.PollCount - 1, token);

    /// <summary>Every supported stage preserves the exact150ms boundary and emits a typed signal only above it.</summary>
    [Theory]
    [InlineData("after_capture", 150, false)][InlineData("after_capture", 150.01, true)]
    [InlineData("after_recognition", 150, false)][InlineData("after_recognition", 150.01, true)]
    [InlineData("before_initial_retention", 150, false)][InlineData("before_initial_retention", 150.01, true)]
    [InlineData("after_initial_retention", 150, false)][InlineData("after_initial_retention", 150.01, true)]
    [InlineData("returning_initial_pose", 150, false)][InlineData("returning_initial_pose", 150.01, true)]
    public void ExactStageFreshnessBoundary(string stage, double age, bool rejected)
    {
        var source = Source(1000); var window = new NavigationBaselineInitialReadiness(() => 1000 + age, 31000, 0, 0, "task_owned_timer");
        window.ValidateHeader(source, 1920, 1080, 3, default);
        if (rejected)
        {
            var error = Assert.Throws<NavigationBaselineInitialReadiness.SourceAgeException>(() => window.ValidateSource(source, stage, 0, 0, default));
            Assert.Same(window, error.Owner); Assert.Same(window.Record.SourceChecks[0], error.Check);
        }
        else Assert.Same(source, window.ValidateSource(source, stage, 0, 0, default));
        Assert.Equal(stage, Assert.Single(window.Record.SourceChecks).Stage);
        Assert.Equal(rejected ? "source_age_discard" : stage == "after_capture" ? "fresh_capture" : "fresh_source",
            window.Record.SourceChecks[0].Disposition);
    }

    /// <summary>Only the fresh successor survives; discarded retained images are cleared before waiting and consumed identity is not rolled back.</summary>
    [Theory]
    [InlineData("after_capture")][InlineData("after_recognition")][InlineData("before_initial_retention")]
    [InlineData("after_initial_retention")][InlineData("returning_initial_pose")]
    public async Task StageAgeDiscardThenFreshRead(string rejectedStage)
    {
        double now = rejectedStage == "after_capture" ? 1200 : 1100;
        var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var first = Source(1000); GameCaptureSourceInfo? consumed = null, retained = null;
        var reads = 0; var discarded = 0; var waits = 0;
        var sample = await window.ReadAsync(token =>
        {
            reads++;
            if (reads == 2) { Assert.Null(retained); Assert.Equal(rejectedStage == "after_capture" ? null : first, consumed); }
            var source = reads == 1 ? first : Source(now - 1);
            var result = Capture(window, source, now, token); consumed = source;
            foreach (var stage in LaterStages)
            {
                if (stage == "after_initial_retention") retained = source;
                if (reads == 1 && stage == rejectedStage) now = 1151;
                Check(window, source, stage, token);
            }
            if (reads == 1 && rejectedStage == "returning_initial_pose") now = 1151;
            return Task.FromResult(result);
        }, (at, _) => { waits++; Assert.Null(retained); now = at; return Task.CompletedTask; }, default,
            () => { discarded++; retained = null; });
        Assert.Equal(2, reads); Assert.Equal(1, discarded); Assert.Equal(1, waits);
        Assert.Equal(sample.Source, consumed); Assert.Equal(sample.Source, retained);
        Assert.Equal(2, window.Record.CaptureCount); Assert.Equal(2, window.Record.PollCount);
        Assert.Equal(1, window.Record.SourceAgeDiscards); Assert.Equal(1, window.Record.AdmittedReadIndex);
        var discard = Assert.Single(window.Record.SourceChecks.Where(check => check.Disposition == "source_age_discard"));
        Assert.Equal(rejectedStage, discard.Stage); Assert.Equal(0, discard.ObservationIndex);
        Assert.Equal("returning_initial_pose", window.Record.SourceChecks[^1].Stage);
        Assert.Equal("fresh_source", window.Record.SourceChecks[^1].Disposition);
    }

    /// <summary>A completely returned read can still be rejected by the outer initial gate; its read row remains truthful.</summary>
    [Fact]
    public async Task ReturnedReadDiscardHasSeparateStageEvidence()
    {
        double now = 1100; var attempts = new List<NavigationBaselineObservationAttempt>();
        var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var calls = 0;
        await window.ReadAsync(token => NativeNavigationBaselineOperations.RecordObservationAsync(attempts, () => now, () => null, attempt =>
        {
            calls++; var source = calls == 1 ? Source(1000) : Source(now - 1);
            var sample = Capture(window, source, now, token);
            attempt.LastReturnedSource = source; attempt.Stage = "completed";
            if (calls == 1) now = 1151;
            return Task.FromResult(sample);
        }), (at, _) => { now = at; return Task.CompletedTask; }, default);
        Assert.Equal(2, attempts.Count); Assert.Equal("completed", attempts[0].Stage); Assert.Null(attempts[0].Error);
        var rejected = Assert.Single(window.Record.SourceChecks.Where(check => check.Disposition == "source_age_discard"));
        Assert.Equal("returning_initial_pose", rejected.Stage); Assert.Equal(0, rejected.ObservationIndex);
        Assert.True(rejected.CheckedAtMs >= attempts[0].EndedAtMs); Assert.Equal(1, window.Record.AdmittedReadIndex);
    }

    /// <summary>Disposal errors stop before waiting or another capture; matching age text cannot hide the cleanup failure.</summary>
    [Theory]
    [InlineData("after_capture")][InlineData("after_initial_retention")][InlineData("returning_initial_pose")]
    public async Task DiscardCleanupFailureIsTerminal(string stage)
    {
        double now = stage == "after_capture" ? 1200 : 1100;
        var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var original = new IOException("retained_image_disposal_failed"); var reads = 0;
        var error = await Assert.ThrowsAsync<IOException>(() => window.ReadAsync(token =>
        {
            reads++; var source = Source(1000); var sample = Capture(window, source, now, token); now = 1151;
            if (stage != "returning_initial_pose") Check(window, source, stage, token);
            return Task.FromResult(sample);
        }, (_, _) => throw new Exception("must not wait"), default, () => throw original));
        Assert.Same(original, error); Assert.Equal(1, reads); Assert.Equal(1, window.Record.SourceAgeDiscards);
        Assert.Null(window.Record.AdmittedReadIndex); Assert.Contains(original.Message, window.Record.Error);
    }

    /// <summary>Owner cancellation or the clipped deadline after disposal prevents a further wait/read without resetting budgets.</summary>
    [Theory]
    [InlineData(false)][InlineData(true)]
    public async Task CancelOrDeadlineDuringDiscardStopsBeforeRetry(bool cancel)
    {
        double now = 1100; using var owner = new CancellationTokenSource();
        var window = new NavigationBaselineInitialReadiness(() => now, 1200, 0, 0, "task_owned_timer");
        Task Run() => window.ReadAsync(token =>
        {
            var sample = Capture(window, Source(1000), now, token); now = 1151;
            Check(window, sample.Source, "after_recognition", token); return Task.FromResult(sample);
        }, (_, _) => throw new Exception("must not wait"), owner.Token,
            () => { if (cancel) owner.Cancel(); else now = 1200; });
        if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(Run);
        else await Assert.ThrowsAsync<NavigationBaselineInitialReadiness.DeadlineException>(Run);
        Assert.Equal(1, window.Record.ReadCount); Assert.Equal(1200, window.Record.DeadlineAtMs);
        Assert.Equal(1, window.Record.SourceAgeDiscards); Assert.Null(window.Record.AdmittedReadIndex);
    }

    /// <summary>Hard source identity/clock faults and generic messages never authorize an age retry.</summary>
    [Theory]
    [InlineData("epoch")][InlineData("regression")][InlineData("missing")][InlineData("future")]
    [InlineData("generic_age_text")][InlineData("unrecorded_typed")][InlineData("fresh_typed")]
    public async Task PostCaptureHardOrInventedFailureDoesNotRetry(string failure)
    {
        double now = 1100; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var reads = 0;
        await Assert.ThrowsAnyAsync<InvalidOperationException>(() => window.ReadAsync(token =>
        {
            reads++; var source = Source(1000); Capture(window, source, now, token); now = 1151;
            if (failure == "generic_age_text") throw new InvalidOperationException("initial_readiness_source_age: after_recognition");
            if (failure == "unrecorded_typed") throw new NavigationBaselineInitialReadiness.SourceAgeException(window);
            if (failure == "fresh_typed") throw new NavigationBaselineInitialReadiness.SourceAgeException(window, window.Record.SourceChecks[^1]);
            GameCaptureSourceInfo? invalid = failure switch
            {
                "epoch" => source with { CaptureEpoch = Guid.NewGuid() }, "regression" => Source(999),
                "future" => source with { AcquiredAtStopwatchTicks = (long)(1152 * Stopwatch.Frequency / 1000) }, _ => null
            };
            window.ValidateSource(invalid, "after_recognition", 0, 0, token);
            return Task.FromResult(Sample(source, now));
        }, (_, _) => throw new Exception("must not wait"), default));
        Assert.Equal(1, reads); Assert.Equal(0, window.Record.SourceAgeDiscards); Assert.Null(window.Record.AdmittedReadIndex);
    }

    /// <summary>The existing hard-pose classifier wins over simultaneous positive age expiry before the retryable check.</summary>
    [Theory]
    [InlineData("wrong_layer")][InlineData("invalid_yaw_confidence")][InlineData("non_normal_motion")]
    public async Task HardPoseWinsOverAge(string failure)
    {
        double now = 1100; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(token =>
        {
            var sample = Capture(window, Source(1000), now, token); now = 1151;
            sample = failure switch
            {
                "wrong_layer" => sample with { LayerId = "other", SourceAgeMs = 151 },
                "invalid_yaw_confidence" => sample with { YawConfidence = 0, SourceAgeMs = 151 },
                _ => sample with { Motion = sample.Motion with { Status = "flying" }, SourceAgeMs = 151 }
            };
            if (NavigationBaselineRecovery.HardPoseRejection(sample) is { } hard) throw new InvalidOperationException(hard);
            Check(window, sample.Source, "after_recognition", token); return Task.FromResult(sample);
        }, (_, _) => throw new Exception("must not wait"), default));
        Assert.Equal(failure, error.Message); Assert.Equal(0, window.Record.SourceAgeDiscards);
    }

    /// <summary>Repeated short recognition overruns exhaust the original32-read bound well before any expanded wall budget.</summary>
    [Fact]
    public async Task LaterStageRetriesCannotExceedReadBudget()
    {
        double now = 2000; var window = new NavigationBaselineInitialReadiness(() => now, 31000, 0, 0, "task_owned_timer");
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.ReadAsync(token =>
        {
            var sample = Capture(window, Source(now - 149), now, token); now += 2;
            Check(window, sample.Source, "after_recognition", token); return Task.FromResult(sample);
        }, (at, _) => { now = at; return Task.CompletedTask; }, default));
        Assert.Equal("initial_readiness_read_limit_exceeded", error.Message);
        Assert.Equal(32, window.Record.ReadCount); Assert.Equal(32, window.Record.CaptureCount);
        Assert.Equal(32, window.Record.SourceAgeDiscards); Assert.Equal(4000, window.Record.DeadlineAtMs);
    }

    /// <summary>Even an internal caller repeating checks cannot grow stage evidence beyond the fixed160 rows.</summary>
    [Fact]
    public void SourceCheckCapacityIsBounded()
    {
        var window = new NavigationBaselineInitialReadiness(() => 1100, 31000, 0, 0, "task_owned_timer");
        var source = Source(1000); window.ValidateHeader(source, 1920, 1080, 3, default);
        for (var i = 0; i < 160; i++) window.ValidateSource(source, "after_recognition", 0, 0, default);
        Assert.Equal("initial_readiness_check_capacity_exceeded", Assert.Throws<InvalidOperationException>(() =>
            window.ValidateSource(source, "after_recognition", 0, 0, default)).Message);
        Assert.Equal(160, window.Record.SourceChecks.Count);
    }

    /// <summary>The actual native image cleanup disposes only owned pixels, clears identity and retains consumed source/barriers.</summary>
    [Fact]
    public void NativeDiscardDetachesPixelsWithoutRollingBackSource()
    {
        var native = (NativeNavigationBaselineOperations)RuntimeHelpers.GetUninitializedObject(typeof(NativeNavigationBaselineOperations));
        using var image = new Mat(2, 2, MatType.CV_8UC3, Scalar.All(7)); var source = Source(1000);
        Set(native, "_initialImage", image); Set(native, "_initialImageSource", source); Set(native, "_lastSource", source);
        Set(native, "_inputBarrier", 123.0); Set(native, "_responseMs", 80.0);
        native.DiscardInitialImage(); native.DiscardInitialImage();
        Assert.True(image.IsDisposed); Assert.Null(Get(native, "_initialImage")); Assert.Null(Get(native, "_initialImageSource"));
        Assert.Same(source, Get(native, "_lastSource")); Assert.Equal(123.0, Get(native, "_inputBarrier")); Assert.Equal(80.0, Get(native, "_responseMs"));
    }

    /// <summary>Access fixture-only fields without constructing any game/runtime/input dependency.</summary>
    private static object? Get(object target, string name) => target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(target);
    /// <summary>Install only already-owned test pixels and immutable values into the uninitialized native object.</summary>
    private static void Set(object target, string name, object value) => target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(target, value);
}
