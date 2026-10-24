using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.AutoTrackPath;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Common.Job;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture;
using OpenCvSharp;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Offline typed-readback, cancellation, ownership and actual UI-helper exception boundaries; no game or input backend is used.</summary>
public sealed class TeleportCaptureReadbackTests
{
    /// <summary>Pending is pixel-free work, and Ready plus another reservation transfers only the returned frame.</summary>
    [Fact]
    public void PendingThenReadyWithRefillTransfersExactlyOneFrame()
    {
        var h = new Harness(); using var frame = Frame();
        var next = GameCaptureReadbackConsumerTests.Pending();
        h.Enqueue(Pending(), new(GameCaptureAttemptOutcome.FrameReady, frame, next));
        var actual = h.Read();
        Assert.Same(frame, actual); Assert.False(frame.Frame.IsDisposed);
        Assert.Equal(new[] { 10 }, h.Delays); Assert.Equal(2, h.Backend.Calls);
        Assert.Equal(0, h.Warnings); Assert.Equal(0, h.Backend.LegacyCalls);
        actual.Dispose(); Assert.True(frame.Frame.IsDisposed);
    }

    /// <summary>Pending neither uses nor resets the genuine Unavailable budget.</summary>
    [Fact]
    public void MixedPendingAndUnavailableRetainsTheOriginalUnavailablePattern()
    {
        var h = new Harness(); using var frame = Frame();
        h.Enqueue(default, Pending(), default, Pending(), new(GameCaptureAttemptOutcome.FrameReady, frame));
        Assert.Same(frame, h.Read());
        Assert.Equal(new[] { 10, 30, 10 }, h.Delays);
        Assert.Equal(5, h.Backend.Calls); Assert.Equal(1, h.Warnings);
    }

    /// <summary>Four genuine unavailable outcomes still fail after exactly the original three 30ms waits.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void UnavailableDoesNotBecomeAnUnboundedPendingRetry(bool interleave)
    {
        var h = new Harness();
        for (var i = 0; i < 4; i++)
        {
            h.Enqueue(default(GameCaptureAttempt));
            if (interleave && i < 3) h.Enqueue(Pending());
        }
        var error = Assert.Throws<Exception>(() => h.Read());
        Assert.Equal("Screenshot failed after multiple attempts!", error.Message);
        Assert.Equal(interleave ? 7 : 4, h.Backend.Calls);
        Assert.Equal(3, h.Delays.Count(delay => delay == 30));
        Assert.Equal(interleave ? 3 : 0, h.Delays.Count(delay => delay == 10));
        Assert.Equal(1, h.Warnings); Assert.False(TpTask.IsTaskStopException(error));
    }

    /// <summary>The final allowed call may return Ready, but call201 can never execute even with a stalled test clock.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void ExactNativeCallCap(bool finalReady)
    {
        var h = new Harness { AdvanceDuringDelay = false }; using var frame = Frame();
        for (var i = 0; i < 199; i++) h.Enqueue(Pending());
        h.Enqueue(finalReady ? new(GameCaptureAttemptOutcome.FrameReady, frame) : Pending());
        if (finalReady) Assert.Same(frame, h.Read());
        else Assert.Equal(TeleportCaptureAbortReason.CallLimit, Assert.Throws<TeleportCaptureAbortedException>(() => h.Read()).Reason);
        Assert.Equal(200, h.Backend.Calls); Assert.Equal(199, h.Delays.Count);
    }

    /// <summary>Exactly2s is expired, including a Ready result returned by a synchronous call begun on time.</summary>
    [Theory]
    [InlineData(1999, true)] [InlineData(2000, false)] [InlineData(2500, false)]
    public void DeadlineRecheckedAfterSynchronousReturn(double elapsed, bool accepted)
    {
        var h = new Harness(); using var frame = Frame();
        h.Steps.Enqueue(() => { h.Now += elapsed; return new(GameCaptureAttemptOutcome.FrameReady, frame); });
        if (accepted) Assert.Same(frame, h.Read());
        else
        {
            Assert.Equal(TeleportCaptureAbortReason.Deadline, Assert.Throws<TeleportCaptureAbortedException>(() => h.Read()).Reason);
            Assert.True(frame.Frame.IsDisposed);
        }
        Assert.Equal(1, h.Backend.Calls); Assert.Empty(h.Delays);
    }

    /// <summary>Cancellation from a slow native return wins over admitting its pixels or another screenshot.</summary>
    [Fact]
    public void CancellationAfterSlowReadyDisposesWithoutAction()
    {
        using var stop = new CancellationTokenSource(); var h = new Harness(); using var frame = Frame();
        var actions = 0;
        h.Steps.Enqueue(() => { h.Now += 2500; stop.Cancel(); return new(GameCaptureAttemptOutcome.FrameReady, frame); });
        var error = Assert.Throws<OperationCanceledException>(() => { h.Read(stop.Token); actions++; });
        Assert.Equal(stop.Token, error.CancellationToken); Assert.True(frame.Frame.IsDisposed);
        Assert.Equal(0, actions); Assert.Equal(1, h.Backend.Calls);
    }

    /// <summary>Already-cancelled requests and cancellation during Pending spacing cannot poll again.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void CancellationBeforeOrDuringWait(bool alreadyCancelled)
    {
        using var stop = new CancellationTokenSource(); var h = new Harness();
        if (alreadyCancelled) stop.Cancel();
        h.AfterDelay = () => stop.Cancel();
        Assert.Throws<OperationCanceledException>(() => h.Read(stop.Token));
        Assert.Equal(alreadyCancelled ? 0 : 1, h.Backend.Calls);
    }

    /// <summary>Target loss/mode change/capture stop are checked after native completion, with rejected pixels disposed.</summary>
    [Theory]
    [InlineData("target", "TargetUnavailable")]
    [InlineData("mode", "ModeChanged")]
    [InlineData("stopped", "CaptureStopped")]
    public void ContextLossAfterReadyIsTerminal(string change, string reason)
    {
        var h = new Harness(); using var frame = Frame();
        h.Steps.Enqueue(() =>
        {
            if (change == "target") h.TargetAlive = false;
            if (change == "mode") h.Backend.Mode = GameCaptureReadbackMode.Blocking;
            if (change == "stopped") h.Backend.Capturing = false;
            return new(GameCaptureAttemptOutcome.FrameReady, frame);
        });
        var error = Assert.Throws<TeleportCaptureAbortedException>(() => h.Read());
        Assert.Equal(Enum.Parse<TeleportCaptureAbortReason>(reason), error.Reason); Assert.True(frame.Frame.IsDisposed);
        Assert.True(TpTask.IsTaskStopException(error)); Assert.Equal(1, h.Backend.Calls);
    }

    /// <summary>Hard context changes accompanying a thrown native call cannot become a generic teleport retry.</summary>
    [Fact]
    public void ModeLossDuringNativeErrorRetainsTerminalPriority()
    {
        var h = new Harness();
        h.Steps.Enqueue(() => { h.Backend.Mode = GameCaptureReadbackMode.Blocking; throw new InvalidOperationException("native failure"); });
        Assert.Equal(TeleportCaptureAbortReason.ModeChanged, Assert.Throws<TeleportCaptureAbortedException>(() => h.Read()).Reason);
        Assert.Equal(1, h.Backend.Calls); Assert.Empty(h.Delays);
    }

    /// <summary>An explicit reader never silently invokes blocking capture when its pinned mode is absent.</summary>
    [Fact]
    public void ExplicitReaderRefusesBlockingBeforeCapture()
    {
        var h = new Harness(); h.Backend.Mode = GameCaptureReadbackMode.Blocking;
        Assert.Equal(TeleportCaptureAbortReason.ModeChanged, Assert.Throws<TeleportCaptureAbortedException>(() => h.Read()).Reason);
        Assert.Equal(0, h.Backend.Calls); Assert.Equal(0, h.Backend.LegacyCalls);
    }

    /// <summary>Clock corruption is terminal even when the native call returns pixels.</summary>
    [Fact]
    public void NonfiniteClockAfterReadyDisposesFrame()
    {
        var h = new Harness(); using var frame = Frame();
        h.Steps.Enqueue(() => { h.Now = double.NaN; return new(GameCaptureAttemptOutcome.FrameReady, frame); });
        Assert.Equal(TeleportCaptureAbortReason.InvalidClock, Assert.Throws<TeleportCaptureAbortedException>(() => h.Read()).Reason);
        Assert.True(frame.Frame.IsDisposed);
    }

    /// <summary>Native and structural errors are never converted to Pending or matched using their message text.</summary>
    [Fact]
    public void NativeAndMalformedMetadataErrorsPropagateWithoutWaiting()
    {
        var original = new InvalidOperationException("readback_pending"); var h = new Harness();
        h.Steps.Enqueue(() => throw original);
        Assert.Same(original, Assert.Throws<InvalidOperationException>(() => h.Read()));
        Assert.Empty(h.Delays); Assert.Equal(1, h.Backend.Calls);
        var malformed = new Harness();
        malformed.Enqueue(new GameCaptureAttempt(GameCaptureAttemptOutcome.ReadbackPending,
            pending: GameCaptureReadbackConsumerTests.Pending() with { Width = 0 }));
        var invalid = Assert.Throws<TeleportCaptureAbortedException>(() => malformed.Read());
        Assert.Equal(TeleportCaptureAbortReason.InvalidPendingMetadata, invalid.Reason);
        Assert.IsType<InvalidOperationException>(invalid.InnerException);
        Assert.Empty(malformed.Delays); Assert.Equal(1, malformed.Backend.Calls);
    }

    /// <summary>A late target check and a regressing clock cannot admit even an otherwise valid Ready frame.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void SlowContextOrClockRegressionRejectsReady(bool regress)
    {
        var h = new Harness(); using var frame = Frame();
        h.Enqueue(new GameCaptureAttempt(GameCaptureAttemptOutcome.FrameReady, frame));
        h.AfterTargetCheck = () => { if (h.Backend.Calls == 1) h.Now = regress ? 0 : 3000; };
        var error = Assert.Throws<TeleportCaptureAbortedException>(() => h.Read());
        Assert.Equal(regress ? TeleportCaptureAbortReason.InvalidClock : TeleportCaptureAbortReason.Deadline, error.Reason);
        Assert.True(frame.Frame.IsDisposed);
    }

    /// <summary>The real ReturnMainUi and Welkin error boundaries cannot turn exact terminal failures into a later action.</summary>
    [Theory]
    [InlineData("deadline")] [InlineData("calls")] [InlineData("target")] [InlineData("mode")]
    [InlineData("cancel")] [InlineData("runtime")] [InlineData("metadata")]
    public async Task NestedUiHelpersDoNotSwallowCaptureStops(string kind)
    {
        Exception expected = kind switch
        {
            "deadline" => new TeleportCaptureAbortedException(TeleportCaptureAbortReason.Deadline),
            "calls" => new TeleportCaptureAbortedException(TeleportCaptureAbortReason.CallLimit),
            "target" => new TeleportCaptureAbortedException(TeleportCaptureAbortReason.TargetUnavailable),
            "mode" => new TeleportCaptureAbortedException(TeleportCaptureAbortReason.ModeChanged),
            "metadata" => new TeleportCaptureAbortedException(TeleportCaptureAbortReason.InvalidPendingMetadata,
                new InvalidOperationException("invalid_pending_readback_metadata")),
            "cancel" => new OperationCanceledException(),
            _ => new NormalEndException("runtime stopped")
        };
        var captures = 0; var logged = 0; var laterActions = 0;
        async Task Run()
        {
            await BlessingOfTheWelkinMoonTask.RunCheckAsync(
                () => new ReturnMainUiTask(null!).Start(CancellationToken.None, () => { captures++; throw expected; }),
                _ => logged++, true);
            laterActions++;
        }
        Assert.Same(expected, await Record.ExceptionAsync(Run));
        Assert.True(TpTask.IsTaskStopException(expected));
        Assert.Equal(1, captures); Assert.Equal(0, logged); Assert.Equal(0, laterActions);
    }

    /// <summary>Standalone Welkin keeps its old best-effort catch, and opt-in does not reinterpret ordinary vision errors.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task ExistingBestEffortErrorHandlingIsPreserved(bool optedIn)
    {
        Exception expected = optedIn ? new InvalidOperationException("vision failed") : new OperationCanceledException();
        Exception? logged = null;
        await BlessingOfTheWelkinMoonTask.RunCheckAsync(() => Task.FromException(expected), e => logged = e, optedIn);
        Assert.Same(expected, logged);
    }

    /// <summary>The runtime adapter transfers normal and resized images without leaving the original pixel allocation owned twice.</summary>
    [Theory]
    [InlineData(1920, 1080)] [InlineData(2560, 1440)]
    public void RegionTransferOwnsNormalAndLargePixels(int width, int height)
    {
        var info = new FakeSystemInfo(new RECT(0, 0, width, height), 1)
            { CaptureAreaRect = new RECT(0, 0, width, height) };
        using var environment = TestGameRuntime.Create(info);
        using var frame = Frame(width, height); var h = new Harness();
        h.Enqueue(new GameCaptureAttempt(GameCaptureAttemptOutcome.FrameReady, frame));
        using var runtime = new GameRuntime(environment.Kind, environment.Window, h.Backend, environment.Input,
            info, environment.MaskWindowDrawingBoard, environment.MaskWindowMapState);
        var region = runtime.CaptureToRectAreaForTeleport(CancellationToken.None);
        Assert.Equal(1920, region.Width); Assert.Equal(1080, region.Height);
        Assert.Equal(width > 1920, frame.Frame.IsDisposed);
        Assert.False(region.SrcMat.IsDisposed);
        region.Dispose(); Assert.True(frame.Frame.IsDisposed); Assert.True(region.SrcMat.IsDisposed);
    }

    /// <summary>Failure before CaptureContent takes ownership must still release the actual returned pixels.</summary>
    [Fact]
    public void RegionConstructionFailureDisposesFrame()
    {
        var info = new FakeSystemInfo(new RECT(0, 0, 4, 3), 1) { DesktopRectArea = null! };
        using var environment = TestGameRuntime.Create(info); using var frame = Frame(); var h = new Harness();
        h.Enqueue(new GameCaptureAttempt(GameCaptureAttemptOutcome.FrameReady, frame));
        using var runtime = new GameRuntime(environment.Kind, environment.Window, h.Backend, environment.Input,
            info, environment.MaskWindowDrawingBoard, environment.MaskWindowMapState);
        Assert.Throws<NullReferenceException>(() => runtime.CaptureToRectAreaForTeleport(CancellationToken.None));
        Assert.True(frame.Frame.IsDisposed);
    }

    /// <summary>CPU-owned pixels only; the fake backend never creates GPU resources.</summary>
    private static GameCaptureFrame Frame(int width = 4, int height = 3) => new(new Mat(height, width, MatType.CV_8UC3, Scalar.All(7)));
    /// <summary>A structurally valid immutable Pending descriptor without pixel authority.</summary>
    private static GameCaptureAttempt Pending() => new(GameCaptureAttemptOutcome.ReadbackPending,
        pending: GameCaptureReadbackConsumerTests.Pending());

    /// <summary>Deterministic acquisition/target/clock/wait seams; all native-boundary calls are counted.</summary>
    private sealed class Harness
    {
        /// <summary>Queued native outcomes or injected native failures.</summary>
        internal readonly Queue<Func<GameCaptureAttempt>> Steps = new();
        /// <summary>Observed spacing without sleeping.</summary>
        internal readonly List<int> Delays = [];
        /// <summary>The exact fake backend retained throughout one request.</summary>
        internal readonly Backend Backend;
        /// <summary>Deterministic nonnegative monotonic milliseconds.</summary>
        internal double Now = 1000;
        /// <summary>Whether the injected wait advances time.</summary>
        internal bool AdvanceDuringDelay = true;
        /// <summary>Current target-availability evidence.</summary>
        internal bool TargetAlive = true;
        /// <summary>Count legacy unavailable warnings.</summary>
        internal int Warnings;
        /// <summary>Optional deterministic cancellation/mode race at a wait boundary.</summary>
        internal Action? AfterDelay;
        /// <summary>Optional deterministic slow/reentrant target check.</summary>
        internal Action? AfterTargetCheck;
        /// <summary>Bind one fake capture to this scripted request.</summary>
        internal Harness() => Backend = new Backend(() => Steps.Count == 0 ? Pending() : Steps.Dequeue()());
        /// <summary>Enqueue immutable outcomes without executing them.</summary>
        internal void Enqueue(params GameCaptureAttempt[] attempts)
        {
            foreach (var attempt in attempts) Steps.Enqueue(() => attempt);
        }
        /// <summary>Exercise the production state machine with clock/wait substitutes only.</summary>
        internal GameCaptureFrame Read(CancellationToken ct = default) => TeleportCaptureReadback.Capture(Backend, ct,
            () =>
            {
                AfterTargetCheck?.Invoke();
                if (!TargetAlive) throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.TargetUnavailable);
            }, () => Warnings++, () => Now,
            (milliseconds, token) =>
            {
                Delays.Add(milliseconds);
                if (AdvanceDuringDelay) Now += milliseconds;
                AfterDelay?.Invoke(); token.ThrowIfCancellationRequested();
            });
    }

    /// <summary>Typed fake backend that exposes accidental legacy calls or stop/mode changes.</summary>
    private sealed class Backend(Func<GameCaptureAttempt> read) : IGameCapture, IGameCaptureReadback
    {
        /// <summary>Current mode is explicit and may be changed only by a test race.</summary>
        internal GameCaptureReadbackMode Mode = GameCaptureReadbackMode.PollSingleV1;
        /// <summary>Current capture lifetime is controlled by tests.</summary>
        internal bool Capturing = true;
        /// <summary>Actual typed native-boundary call count.</summary>
        internal int Calls;
        /// <summary>Accidental legacy calls are separately visible.</summary>
        internal int LegacyCalls;
        /// <inheritdoc />
        public GameCaptureReadbackMode ReadbackMode => Mode;
        /// <inheritdoc />
        public bool IsCapturing => Capturing;
        /// <inheritdoc />
        public GameCaptureAttempt CaptureAttempt() { Calls++; return read(); }
        /// <inheritdoc />
        public GameCaptureAttempt CaptureAttempt(out GameCaptureCallTiming timing) { timing = new(); return CaptureAttempt(); }
        /// <inheritdoc />
        public GameCaptureFrame? Capture() { LegacyCalls++; throw new InvalidOperationException("Unexpected legacy capture"); }
        /// <inheritdoc />
        public void Start(nint handle, Dictionary<string, object>? settings = null) => throw new NotSupportedException();
        /// <inheritdoc />
        public void Stop() => throw new NotSupportedException();
        /// <inheritdoc />
        public void Dispose() { }
    }
}
