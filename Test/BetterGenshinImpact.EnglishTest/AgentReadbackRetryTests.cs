using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise the real stream retry boundary with prescribed readbacks and virtual delays; no native capture or input.</summary>
public sealed class AgentReadbackRetryTests
{
    /// <summary>Prompt polls return the exact frame/source without publishing confirmations or consuming a ready refill.</summary>
    [Fact]
    public async Task PendingThenReadyTransfersExactFrameAndDoesNotPollRefill()
    {
        var fixture = new Fixture();
        var pending = GameCaptureReadbackConsumerTests.Pending();
        using var pixels = new Mat(3, 4, MatType.CV_8UC3, Scalar.All(7));
        using var ready = new GameCaptureFrame(pixels, null, pending.SourceInfo);
        fixture.Capture.Next = () => fixture.Capture.TypedCalls < 3
            ? new(GameCaptureAttemptOutcome.ReadbackPending, pending: pending)
            : new(GameCaptureAttemptOutcome.FrameReady, ready, pending with { SubmissionId = 2 });
        var before = fixture.Controller.GetWorldReadiness(fixture.Now);

        var result = await fixture.Run();

        Assert.Same(ready, result);
        Assert.Same(pending.SourceInfo, result!.SourceInfo);
        Assert.False(pixels.IsDisposed);
        Assert.Equal(3, fixture.Capture.TypedCalls);
        Assert.Equal(new[] { 2.0, 2.0 }, fixture.Delays);
        Assert.Equal(114, fixture.Now);
        Assert.Equal(before, fixture.Controller.GetWorldReadiness(fixture.Now));
        // Source time and the original published observation remain unchanged despite later poll completion.
        Assert.Equal(100, before.SourceCapturedAtMs);
    }

    /// <summary>Pending exhaustion is finite even if a faulty test clock/delay never advances time; it does not revoke readiness.</summary>
    [Fact]
    public async Task PendingCallCapDoesNotRenewOrInvalidateAuthority()
    {
        var fixture = new Fixture { AdvanceDelay = false };
        var before = fixture.Controller.GetWorldReadiness(fixture.Now);
        Assert.Null(await fixture.Run());
        Assert.Equal(9, fixture.Capture.TypedCalls);
        Assert.Equal(8, fixture.Delays.Count);
        Assert.All(fixture.Delays, delay => Assert.Equal(2, delay));
        Assert.Equal(before, fixture.Controller.GetWorldReadiness(fixture.Now));
        fixture.Now = 251;
        Assert.Equal("world_observation_stale", fixture.Controller.GetWorldReadiness(fixture.Now).Reason);
    }

    /// <summary>Both a slow capture and an overslept delay use the original turn deadline, never a renewed retry budget.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CadenceDeadlinePreventsAnotherCapture(bool oversleep)
    {
        var fixture = new Fixture();
        if (oversleep) fixture.AfterDelay = () => fixture.Now = 144;
        else fixture.Capture.Next = () => { fixture.Now = 142; return fixture.Pending; };
        Assert.Null(await fixture.Run());
        Assert.Equal(1, fixture.Capture.TypedCalls);
        Assert.Equal(oversleep ? 1 : 0, fixture.Delays.Count);
        Assert.True(fixture.Controller.GetWorldReadiness(fixture.Now).Ready);
    }

    /// <summary>Cancellation or retirement observed around the yield prevents any later readback invocation.</summary>
    [Theory]
    [InlineData("cancel_before")]
    [InlineData("cancel_after")]
    [InlineData("inactive_before")]
    [InlineData("inactive_after")]
    public async Task StopDuringPendingDoesNotRetry(string change)
    {
        var fixture = new Fixture();
        using var stop = new CancellationTokenSource();
        if (change == "cancel_before") stop.Cancel();
        if (change == "cancel_after") fixture.AfterDelay = stop.Cancel;
        if (change == "inactive_before") fixture.Active = false;
        if (change == "inactive_after") fixture.AfterDelay = () => fixture.Active = false;
        if (change.StartsWith("cancel", StringComparison.Ordinal))
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => fixture.Run(stop.Token));
        else Assert.Null(await fixture.Run(stop.Token));
        Assert.Equal(change.EndsWith("before", StringComparison.Ordinal) ? 0 : 1, fixture.Capture.TypedCalls);
    }

    /// <summary>Unavailable and empty pixels retain the existing immediate invalidation and owned-frame disposal.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RealFailureAfterPendingInvalidatesWithoutFurtherRetry(bool empty)
    {
        var fixture = new Fixture();
        using var pixels = new Mat();
        var frame = new GameCaptureFrame(pixels);
        fixture.Capture.Next = () => fixture.Capture.TypedCalls == 1 ? fixture.Pending
            : empty ? new(GameCaptureAttemptOutcome.FrameReady, frame) : default;
        Assert.Null(await fixture.Run());
        Assert.Equal(2, fixture.Capture.TypedCalls);
        Assert.Single(fixture.Delays);
        Assert.Equal("capture_unavailable", fixture.Controller.GetWorldReadiness(fixture.Now).Reason);
        Assert.Equal(empty, pixels.IsDisposed);
    }

    /// <summary>Backend exceptions and malformed pending metadata propagate, rather than becoming expected retry conditions.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FaultAndInvalidPendingNeverRetry(bool invalidMetadata)
    {
        var fixture = new Fixture();
        var failure = new InvalidOperationException("prescribed capture failure");
        fixture.Capture.Next = invalidMetadata
            ? () => new(GameCaptureAttemptOutcome.ReadbackPending,
                pending: GameCaptureReadbackConsumerTests.Pending() with { SubmissionId = 0 })
            : () => throw failure;
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Run());
        if (!invalidMetadata) Assert.Same(failure, actual);
        else Assert.Equal("invalid_pending_readback_metadata", actual.Message);
        Assert.Equal(1, fixture.Capture.TypedCalls);
        Assert.Empty(fixture.Delays);
    }

    /// <summary>Ordinary blocking mode still makes one legacy capture call and never reaches the polling method.</summary>
    [Fact]
    public async Task BlockingModeKeepsItsOriginalSingleCall()
    {
        var fixture = new Fixture();
        fixture.Capture.Mode = GameCaptureReadbackMode.Blocking;
        using var ready = new GameCaptureFrame(new Mat(3, 4, MatType.CV_8UC3, Scalar.All(8)));
        fixture.Capture.LegacyFrame = ready;
        Assert.Same(ready, await fixture.Run());
        Assert.Equal(1, fixture.Capture.LegacyCalls);
        Assert.Equal(0, fixture.Capture.TypedCalls);
        Assert.Empty(fixture.Delays);
        Assert.False(ready.Frame.IsDisposed);
    }

    /// <summary>Regressing/nonfinite elapsed clocks cannot prolong a pending turn or publish a new frame.</summary>
    [Theory]
    [InlineData(-1)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public async Task InvalidBudgetClockEndsPendingTurn(double now)
    {
        var fixture = new Fixture();
        fixture.AfterDelay = () => fixture.Now = now;
        Assert.Null(await fixture.Run());
        Assert.Equal(1, fixture.Capture.TypedCalls);
        Assert.Single(fixture.Delays);
    }

    /// <summary>The independent stale watchdog remains active during pending waits, with no timestamp renewal.</summary>
    [Fact]
    public async Task WatchdogCanExpireDuringPendingDelay()
    {
        var fixture = new Fixture { Now = 249 };
        fixture.AfterDelay = () =>
        {
            fixture.Controller.Tick(fixture.Now);
            Assert.Equal("world_observation_stale", fixture.Controller.GetWorldReadiness(fixture.Now).Reason);
        };
        Assert.Null(await fixture.Run());
        Assert.Equal(9, fixture.Capture.TypedCalls);
        Assert.Equal(2, fixture.Controller.GetWorldReadiness(fixture.Now).SourceFrameId);
        Assert.Equal(100, fixture.Controller.GetWorldReadiness(fixture.Now).SourceCapturedAtMs);
    }

    /// <summary>Virtual session time and prescribed readback outcomes use the actual stream helper/controller only.</summary>
    private sealed class Fixture
    {
        /// <summary>No runtime is needed by the injected capture boundary.</summary>
        internal readonly AgentStreamSession Stream = new(null!);
        /// <summary>Always available in-memory input; no operating-system input backend exists.</summary>
        internal readonly AgentActionController Controller = new(new Input(), false);
        /// <summary>Explicit readback implementation with per-method counts.</summary>
        internal readonly FakeCapture Capture = new();
        /// <summary>Each capture may return this immutable valid unpublished reservation.</summary>
        internal readonly GameCaptureAttempt Pending = new(GameCaptureAttemptOutcome.ReadbackPending,
            pending: GameCaptureReadbackConsumerTests.Pending());
        /// <summary>Current virtual session time; unrelated to immutable source metadata.</summary>
        internal double Now = 110;
        /// <summary>Models the existing runtime/window liveness boundary.</summary>
        internal bool Active = true;
        /// <summary>Test-only clock stall exercises the independent call cap.</summary>
        internal bool AdvanceDelay = true;
        /// <summary>Exact requested waits, without sleeping a thread.</summary>
        internal readonly List<double> Delays = [];
        /// <summary>Optional cancellation/retirement/oversleep injection at a completed wait.</summary>
        internal Action? AfterDelay;

        /// <summary>Start with two genuinely distinct positive observations.</summary>
        internal Fixture()
        {
            Capture.Next = () => Pending;
            Controller.RegisterFrame(new(1, 60, 4, 3, AgentWorldEvidence.WorldHud), 61);
            Controller.RegisterFrame(new(2, 100, 4, 3, AgentWorldEvidence.WorldHud), 101);
        }

        /// <summary>Keep the original turn timestamp fixed throughout every retry.</summary>
        internal Task<GameCaptureFrame?> Run(CancellationToken ct = default) =>
            Stream.CaptureWithPendingRetriesAsync(Capture, Controller, Now, () => Now, () => Active, ct, Delay);

        /// <summary>A deterministic asynchronous boundary without wall-clock sleeps.</summary>
        private Task Delay(TimeSpan time, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Delays.Add(time.TotalMilliseconds);
            if (AdvanceDelay) Now += time.TotalMilliseconds;
            AfterDelay?.Invoke();
            return Task.CompletedTask;
        }
    }

    /// <summary>Only prescribed in-memory results; diagnostics/native capture must never be invoked.</summary>
    private sealed class FakeCapture : IGameCapture, IGameCaptureReadback
    {
        /// <summary>Explicit mode selection used by the unchanged readback consumer.</summary>
        internal GameCaptureReadbackMode Mode = GameCaptureReadbackMode.PollSingleV1;
        /// <summary>Supplied result callback, sampled once per typed capture.</summary>
        internal Func<GameCaptureAttempt> Next = () => default;
        /// <summary>Legacy ready pixels for the unchanged blocking path.</summary>
        internal GameCaptureFrame? LegacyFrame;
        /// <summary>Count typed reads independently of ordinary captures.</summary>
        internal int TypedCalls;
        /// <summary>Count the original blocking API.</summary>
        internal int LegacyCalls;
        /// <inheritdoc />
        public bool IsCapturing => true;
        /// <inheritdoc />
        public GameCaptureReadbackMode ReadbackMode => Mode;
        /// <inheritdoc />
        public GameCaptureFrame? Capture() { LegacyCalls++; return LegacyFrame; }
        /// <inheritdoc />
        public GameCaptureAttempt CaptureAttempt() { TypedCalls++; return Next(); }
        /// <inheritdoc />
        public GameCaptureAttempt CaptureAttempt(out GameCaptureCallTiming timing) =>
            throw new InvalidOperationException("Unexpected diagnostic capture.");
        /// <inheritdoc />
        public void Start(nint window, Dictionary<string, object>? settings = null) =>
            throw new InvalidOperationException("No native start in inert fixture.");
        /// <inheritdoc />
        public void Stop() => throw new InvalidOperationException("No native stop in inert fixture.");
        /// <inheritdoc />
        public void Dispose() { }
    }

    /// <summary>No native input; controller watchdog and readiness remain real.</summary>
    private sealed class Input : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => throw new InvalidOperationException("No dispatch in this fixture.");
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => throw new InvalidOperationException("No dispatch in this fixture.");
        /// <inheritdoc />
        public void ReleaseAll() { }
    }
}
