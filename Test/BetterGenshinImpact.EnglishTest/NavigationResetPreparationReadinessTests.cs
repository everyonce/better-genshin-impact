using System.Diagnostics;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationReset;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Preparation-only age waiting, owner sequencing and clocks; no application, capture provider or input is started.</summary>
public sealed class NavigationResetPreparationReadinessTests
{
    /// <summary>A fixed positive QPC origin keeps synthetic source metadata in the supported native domain.</summary>
    private static readonly long Origin = Stopwatch.Frequency * 10;
    /// <summary>Represent an immutable capture/acquisition pair with the ordinary conservative age anchor.</summary>
    private static GameCaptureSourceInfo Source(Guid epoch, int ageMs) => new(epoch,
        (long)((10 - ageMs / 1000.0) * 10_000_000), Origin - Stopwatch.Frequency * ageMs / 1000);

    /// <summary>The r26-02 age can wait, but only a later fresh source allows the real workflow to call teleport.</summary>
    [Fact]
    public async Task StaleCachedFramesThenFreshWorldPermitOneTeleport()
    {
        var epoch = Guid.NewGuid();
        var stale = Source(epoch, 1043);
        var sources = new Queue<GameCaptureSourceInfo>([stale, stale, Source(epoch, 30)]);
        Guid? pinned = null;
        GameCaptureSourceInfo? previous = null;
        var events = new List<string>();
        var operations = new PreparationOperations((attempt, _) =>
        {
            var source = sources.Dequeue();
            var reason = NativeNavigationResetOperations.PreparationSourceRejectionReason(source, Origin, pinned, previous);
            Assert.True(reason is null or "source_age_exceeds_500ms");
            pinned ??= source.CaptureEpoch;
            previous = source;
            NativeNavigationResetOperations.WorldRetryReason(AgentWorldEvidence.WorldHud, false, source.SourceTimestamp100ns);
            events.Add($"world:{attempt}");
            return reason is null ? NavigationResetPreparationState.Ready : NavigationResetPreparationState.SourceAge;
        }, events);
        var result = await new NavigationResetTask(operations).RunAsync(0, _ => { }, CancellationToken.None);
        Assert.Equal(3, result.Length);
        Assert.Equal(1, operations.Teleports);
        Assert.Equal(new[] { "world:1", "delay:120", "world:2", "delay:120", "world:3", "teleport" }, events.Take(6));
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>Persistent old pixels consume exactly the finite work allowance and never start teleport.</summary>
    [Fact]
    public async Task PersistentAgeStopsAtTwentyFiveWithoutInput()
    {
        var attempts = 0;
        var operations = new PreparationOperations((attempt, _) =>
        {
            Assert.Equal(++attempts, attempt);
            return NavigationResetPreparationState.SourceAge;
        });
        var error = await Assert.ThrowsAsync<NavigationResetPreparationTimeoutException>(() =>
            new NavigationResetTask(operations).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Contains("attempts=25", error.Message);
        Assert.Contains("source_age_exceeds_500ms", error.Message);
        Assert.Equal(24, operations.Delays);
        Assert.Equal(0, operations.Teleports);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>Hard errors do not become retries even when they have misleading age-looking exception text.</summary>
    [Theory]
    [InlineData("game_target_lost")]
    [InlineData("preparation_frame_geometry_changed")]
    [InlineData("chat_not_closed: Open")]
    [InlineData("source_age_exceeds_500ms")]
    public async Task HardProbeExceptionsPropagateWithoutReplay(string message)
    {
        var original = new InvalidOperationException(message);
        var operations = new PreparationOperations((_, _) => throw original);
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            new NavigationResetTask(operations).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Same(original, error);
        Assert.Equal(0, operations.Delays);
        Assert.Equal(0, operations.Teleports);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>A world failure remains terminal despite concurrent stale metadata; preparation has no HUD-settling permission.</summary>
    [Theory]
    [InlineData(AgentWorldEvidence.HudMissing)]
    [InlineData(AgentWorldEvidence.BlockingUi)]
    [InlineData(AgentWorldEvidence.RecognitionFailed)]
    public async Task HardWorldOutcomesCannotBeTurnedIntoAgeRetry(AgentWorldEvidence evidence)
    {
        var stale = Source(Guid.NewGuid(), 1043);
        var calls = 0;
        await Assert.ThrowsAsync<InvalidOperationException>(() => NavigationResetPreparationReadiness.WaitAsync((_, _) =>
        {
            calls++;
            Assert.Equal("source_age_exceeds_500ms", NativeNavigationResetOperations.PreparationSourceRejectionReason(stale, Origin, null, null));
            NativeNavigationResetOperations.WorldRetryReason(evidence, false, stale.SourceTimestamp100ns);
            return NavigationResetPreparationState.SourceAge;
        }, (_, _) => throw new Exception("must not delay"), CancellationToken.None, () => Origin));
        Assert.Equal(1, calls);
    }

    /// <summary>A linked owner cancellation wins even when the synchronous probe returns an apparently ready result.</summary>
    [Fact]
    public async Task OwnerCancellationRejectsSynchronousReadyResult()
    {
        using var owner = new CancellationTokenSource();
        var operations = new PreparationOperations((_, _) =>
        {
            owner.Cancel();
            return NavigationResetPreparationState.Ready;
        });
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new NavigationResetTask(operations).RunAsync(0, _ => { }, owner.Token));
        Assert.Equal(0, operations.Teleports);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>A cancelled owner cannot enter capture, and cancellation while waiting cannot enter another probe.</summary>
    [Fact]
    public async Task CancellationBeforeOrBetweenProbesHasNoOrphanWork()
    {
        using var before = new CancellationTokenSource();
        before.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => NavigationResetPreparationReadiness.WaitAsync(
            (_, _) => throw new Exception("must not capture"), (_, _) => Task.CompletedTask, before.Token));
        using var during = new CancellationTokenSource();
        var calls = 0;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => NavigationResetPreparationReadiness.WaitAsync((_, _) =>
        {
            calls++;
            return NavigationResetPreparationState.SourceAge;
        }, (_, token) => { during.Cancel(); token.ThrowIfCancellationRequested(); return Task.CompletedTask; }, during.Token));
        Assert.Equal(1, calls);
    }

    /// <summary>Coincident native cancellation is not relabeled merely because this window's deadline has also fired.</summary>
    [Fact]
    public void OnlyExactWindowCancellationIsTranslatedAndOwnerStillWins()
    {
        using var window = new CancellationTokenSource();
        using var owner = new CancellationTokenSource();
        using var foreign = new CancellationTokenSource();
        window.Cancel(); foreign.Cancel();
        var owned = new OperationCanceledException(window.Token);
        Assert.True(NavigationResetPreparationReadiness.IsOwnDeadlineCancellation(owned, owner.Token, window.Token));
        Assert.False(NavigationResetPreparationReadiness.IsOwnDeadlineCancellation(new OperationCanceledException(foreign.Token), owner.Token, window.Token));
        Assert.False(NavigationResetPreparationReadiness.IsOwnDeadlineCancellation(new OperationCanceledException(), owner.Token, window.Token));
        owner.Cancel();
        Assert.False(NavigationResetPreparationReadiness.IsOwnDeadlineCancellation(owned, owner.Token, window.Token));
    }

    /// <summary>A native cancellation keeps its original instance/token through the real workflow, even after a long synchronous probe.</summary>
    [Fact]
    public async Task UnrelatedNativeCancellationPropagatesWithoutTeleport()
    {
        using var native = new CancellationTokenSource();
        native.Cancel();
        var original = new OperationCanceledException(native.Token);
        var now = Origin;
        var operations = new PreparationOperations((_, _) => { now += Stopwatch.Frequency * 4; throw original; }) { Clock = () => now };
        var error = await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            new NavigationResetTask(operations).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Same(original, error);
        Assert.Equal(native.Token, error.CancellationToken);
        Assert.Equal(0, operations.Teleports);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>Clock budget is checked after synchronous capture even when the real timer has not fired.</summary>
    [Theory]
    [InlineData(3000)]
    [InlineData(6000)]
    public async Task SlowSynchronousReadyProbeCannotAuthorizeTeleport(int elapsedMs)
    {
        var now = Origin;
        var operations = new PreparationOperations((_, _) =>
        {
            now += Stopwatch.Frequency * elapsedMs / 1000;
            return NavigationResetPreparationState.Ready;
        }) { Clock = () => now };
        var error = await Assert.ThrowsAsync<NavigationResetPreparationTimeoutException>(() =>
            new NavigationResetTask(operations).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Contains("attempts=1", error.Message);
        Assert.Equal(0, operations.Teleports);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>A prior stale frame cannot be reported as the last outcome when a subsequent fresh probe completed too late.</summary>
    [Fact]
    public async Task StaleThenLateReadyReportsActualLastOutcomeWithoutTeleport()
    {
        var now = Origin;
        var operations = new PreparationOperations((attempt, _) =>
        {
            if (attempt == 1) return NavigationResetPreparationState.SourceAge;
            now += Stopwatch.Frequency * 3;
            return NavigationResetPreparationState.Ready;
        }) { Clock = () => now };
        var error = await Assert.ThrowsAsync<NavigationResetPreparationTimeoutException>(() =>
            new NavigationResetTask(operations).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Contains("attempts=2", error.Message);
        Assert.Contains("last=ready_but_expired", error.Message);
        Assert.DoesNotContain("last=source_age_exceeds_500ms", error.Message);
        Assert.Equal(0, operations.Teleports);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>The monotonic budget is rechecked before a second capture and the clock cannot move backward.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DelayedSpacingOrRegressedClockCannotEnterNextProbe(bool regress)
    {
        var now = Origin;
        var calls = 0;
        var task = NavigationResetPreparationReadiness.WaitAsync((_, _) =>
        {
            calls++;
            return NavigationResetPreparationState.SourceAge;
        }, (_, _) => { now += regress ? -1 : Stopwatch.Frequency * 3; return Task.CompletedTask; }, CancellationToken.None, () => now);
        if (regress)
            Assert.Equal("preparation_clock_regressed", (await Assert.ThrowsAsync<InvalidOperationException>(() => task)).Message);
        else
            await Assert.ThrowsAsync<NavigationResetPreparationTimeoutException>(() => task);
        Assert.Equal(1, calls);
    }

    /// <summary>Missing/invalid clocks, changed generation and genuine regressions take priority over stale age.</summary>
    [Fact]
    public void HardSourceFailuresCannotMasqueradeAsAge()
    {
        var epoch = Guid.NewGuid();
        var stale = Source(epoch, 1043);
        var classify = (GameCaptureSourceInfo? source, GameCaptureSourceInfo? previous) =>
            NativeNavigationResetOperations.PreparationSourceRejectionReason(source, Origin, epoch, previous);
        Assert.Equal("source_missing", classify(null, null));
        Assert.Equal("source_epoch_empty", classify(stale with { CaptureEpoch = Guid.Empty }, null));
        Assert.Equal("source_timestamp_invalid", classify(stale with { SourceTimestamp100ns = 0 }, null));
        Assert.Equal("acquisition_timestamp_invalid", classify(stale with { AcquiredAtStopwatchTicks = 0 }, null));
        Assert.Equal("acquisition_in_future", classify(stale with { AcquiredAtStopwatchTicks = Origin + 1 }, null));
        Assert.Equal("source_epoch_changed", classify(stale with { CaptureEpoch = Guid.NewGuid() }, stale));
        Assert.Equal("source_clock_regressed", classify(stale with { SourceTimestamp100ns = stale.SourceTimestamp100ns - 1 }, stale));
        Assert.Equal("source_clock_regressed", classify(stale with { AcquiredAtStopwatchTicks = stale.AcquiredAtStopwatchTicks - 1 }, stale));
        Assert.Equal("source_identity_changed", classify(stale with { AcquiredAtStopwatchTicks = stale.AcquiredAtStopwatchTicks + 1 }, stale));
        Assert.Equal("source_age_exceeds_500ms", classify(stale, stale));
        Assert.Null(classify(Source(epoch, 499), stale));
        // Reported future QPC retains the unchanged conservative first-acquisition fallback.
        Assert.Null(classify(Source(epoch, 30) with { SourceTimestamp100ns = long.MaxValue }, stale));
    }

    /// <summary>Each captured geometry component remains pinned across age retries, including pixel format.</summary>
    [Theory]
    [InlineData(1919, 1080, false)]
    [InlineData(1920, 1079, false)]
    [InlineData(1920, 1080, true)]
    public void GeometryChangeBeatsSimultaneousSourceAge(int width, int height, bool bgra)
    {
        var source = Source(Guid.NewGuid(), 1043);
        var expected = (1920, 1080, MatType.CV_8UC3);
        var observed = (width, height, bgra ? MatType.CV_8UC4 : MatType.CV_8UC3);
        Assert.Equal("preparation_frame_geometry_changed", NativeNavigationResetOperations.PreparationFrameRejectionReason(
            source, Origin, source.CaptureEpoch, source, observed, expected));
        Assert.Equal("source_age_exceeds_500ms", NativeNavigationResetOperations.PreparationFrameRejectionReason(
            source, Origin, source.CaptureEpoch, source, expected, expected));
    }

    /// <summary>A native timeout is not this readiness timeout and cannot be swallowed or replayed.</summary>
    [Fact]
    public async Task NativeTimeoutAndUnknownProbeOutcomeRemainHard()
    {
        var native = new TimeoutException("capture timeout");
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPreparationReadiness.WaitAsync(
            (_, _) => throw native, (_, _) => throw new Exception("must not delay"), CancellationToken.None));
        Assert.Same(native, error);
        Assert.Equal("invalid_preparation_probe_state", (await Assert.ThrowsAsync<InvalidOperationException>(() =>
            NavigationResetPreparationReadiness.WaitAsync((_, _) => (NavigationResetPreparationState)999,
                (_, _) => throw new Exception("must not delay"), CancellationToken.None))).Message);
    }

    /// <summary>Exercise the real reset workflow around the preparation helper; all other operations are deterministic no-input fakes.</summary>
    private sealed class PreparationOperations(Func<int, CancellationToken, NavigationResetPreparationState> probe,
        List<string>? events = null) : INavigationResetOperations
    {
        /// <summary>Keep timers deterministic without sleeping or replacing the owner's cancellation.</summary>
        public Func<long> Clock { get; init; } = () => Origin;
        /// <summary>Count ordinary input-start admission, not cleanup releases.</summary>
        public int Teleports, Releases, Delays;
        /// <summary>Distinct final evidence lets the workflow finish normally after a successful preparation.</summary>
        private int _reads;
        /// <summary>Retain one final verification generation.</summary>
        private readonly Guid _epoch = Guid.NewGuid();
        /// <summary>Route the workflow through the exact production readiness loop.</summary>
        public Task PrepareAsync(CancellationToken ct) => NavigationResetPreparationReadiness.WaitAsync(probe, DelayAsync, ct, Clock);
        /// <summary>Record the sole first input phase without sending any input.</summary>
        public Task TeleportAsync(CancellationToken ct) { Teleports++; events?.Add("teleport"); return Task.CompletedTask; }
        /// <summary>Fake already aligned yaw.</summary>
        public Task<bool> RotateAsync(double yaw, CancellationToken ct) => Task.FromResult(true);
        /// <summary>Provide distinct valid fixed-profile poses for the unchanged final acceptance gate.</summary>
        public Task<NavigationResetSample> ReadPoseAsync(CancellationToken ct)
        {
            var seconds = 20 + ++_reads * .12;
            return Task.FromResult(new NavigationResetSample(NavigationResetTask.SpawnX, NavigationResetTask.SpawnY, 0,
                DateTimeOffset.UnixEpoch, _epoch, (long)(seconds * 10_000_000), (long)(seconds * Stopwatch.Frequency), 1, 1, "City_102"));
        }
        /// <summary>Record spacing without creating timing-dependent tests.</summary>
        public Task DelayAsync(int milliseconds, CancellationToken ct) { Delays++; events?.Add($"delay:{milliseconds}"); return Task.CompletedTask; }
        /// <summary>Observe the workflow's mandatory cleanup tail separately from positive input admission.</summary>
        public void ReleaseInput() => Releases++;
    }
}
