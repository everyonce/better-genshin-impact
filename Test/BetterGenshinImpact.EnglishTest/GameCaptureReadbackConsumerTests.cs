using System.Diagnostics;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Typed consumer selection/ownership without a native capture session or GPU work.</summary>
public sealed class GameCaptureReadbackConsumerTests
{
    /// <summary>Only explicit polling selects the new API; diagnostic selection does not change outcomes or retry.</summary>
    [Theory]
    [InlineData(false, false)] [InlineData(false, true)]
    [InlineData(true, false)] [InlineData(true, true)]
    public void ExactModeAndDiagnosticRouting(bool polling, bool diagnostic)
    {
        var capture = new FakeCapture(polling ? GameCaptureReadbackMode.PollSingleV1 : GameCaptureReadbackMode.Blocking);
        var result = GameCaptureReadbackConsumer.Capture(capture, diagnostic, out var timing);
        Assert.Equal(polling ? GameCaptureAttemptOutcome.ReadbackPending : GameCaptureAttemptOutcome.Unavailable, result.Outcome);
        Assert.Equal(polling ? 1 : 0, capture.TypedCalls); Assert.Equal(polling ? 0 : 1, capture.LegacyCalls);
        Assert.Equal(diagnostic ? 1 : 0, capture.DiagnosticCalls); Assert.Equal(diagnostic, timing is not null);
        Assert.Null(result.Frame);
    }

    /// <summary>A ready frame with its next refill remains ready; the consumer, not metadata, owns its disposal.</summary>
    [Fact]
    public void ReadyWithRefillPreservesPixelIdentityAndOwnership()
    {
        using var frame = new GameCaptureFrame(new Mat(3, 4, MatType.CV_8UC3, Scalar.All(7)));
        var pending = Pending();
        var capture = new FakeCapture(GameCaptureReadbackMode.PollSingleV1)
            { Attempt = new(GameCaptureAttemptOutcome.FrameReady, frame, pending) };
        var result = GameCaptureReadbackConsumer.Capture(capture, false, out _);
        Assert.Same(frame, result.Frame); Assert.Same(pending, result.Pending);
        Assert.Equal(GameCaptureAttemptOutcome.FrameReady, result.Outcome); Assert.False(frame.Frame.IsDisposed);
        result.Frame!.Dispose(); Assert.True(frame.Frame.IsDisposed);
    }

    /// <summary>Do not learn an offset or reject the already-observed raw-QPC lead; pending has no age authority.</summary>
    [Fact]
    public void PendingValidationAllowsRawFutureAndOldSourcesWithoutChangingThem()
    {
        var pending = Pending();
        var now = Stopwatch.GetTimestamp();
        var future = pending with { SourceInfo = pending.SourceInfo with { SourceTimestamp100ns = long.MaxValue / 2 } };
        GameCaptureReadbackConsumer.ValidatePending(future, now);
        GameCaptureReadbackConsumer.ValidatePending(pending, now + Stopwatch.Frequency * 10);
        Assert.Equal(long.MaxValue / 2, future.SourceInfo.SourceTimestamp100ns);
    }

    /// <summary>Hard unpublished-header faults never become expected Pending, even when the underlying source is old.</summary>
    [Theory]
    [InlineData("submission")] [InlineData("future_acquisition")] [InlineData("future_submit")]
    [InlineData("epoch")] [InlineData("regression")] [InlineData("identity")]
    [InlineData("geometry")] [InlineData("zero")]
    public void HardPendingMetadataRejects(string change)
    {
        var pending = Pending(); var now = Stopwatch.GetTimestamp(); var previous = pending.SourceInfo;
        pending = change switch
        {
            "submission" => pending with { SubmissionId = 0 },
            "future_acquisition" => pending with { SourceInfo = previous with { AcquiredAtStopwatchTicks = now + 1 } },
            "future_submit" => pending with { SubmittedAtStopwatchTicks = now + 1 },
            "epoch" => pending with { SourceInfo = previous with { CaptureEpoch = Guid.NewGuid() } },
            "regression" => pending with { SourceInfo = previous with { SourceTimestamp100ns = previous.SourceTimestamp100ns - 1 } },
            "identity" => pending with { SourceInfo = previous with { AcquiredAtStopwatchTicks = previous.AcquiredAtStopwatchTicks - 1 } },
            "geometry" => pending with { Width = 8 },
            _ => pending with { Height = 0 }
        };
        Assert.Throws<InvalidOperationException>(() => GameCaptureReadbackConsumer.ValidatePending(pending, now,
            previous, previous.CaptureEpoch, 4, 3));
    }

    /// <summary>Shared immutable fixture; no pointer, image, game or operating-system capture is owned.</summary>
    internal static GameCapturePendingReadback Pending()
    {
        var ticks = Stopwatch.GetTimestamp() - Stopwatch.Frequency;
        var source = new GameCaptureSourceInfo(Guid.Parse("713e569b-05ac-4a78-aadf-8a29455fcd92"),
            (long)((Int128)ticks * 10_000_000 / Stopwatch.Frequency), ticks);
        return new(1, source, ticks + 1, 4, 3, null);
    }

    /// <summary>Explicit fake APIs expose routing and contain no platform calls.</summary>
    internal sealed class FakeCapture(GameCaptureReadbackMode mode) : IGameCapture, IGameCaptureReadback, IGameCaptureDiagnostics
    {
        /// <summary>Exact requested mode.</summary>
        public GameCaptureReadbackMode ReadbackMode => Mode;
        /// <summary>Test-only backend selection changes exercise the legacy routing branch without a restart.</summary>
        internal GameCaptureReadbackMode Mode = mode;
        /// <summary>Synthetic capture remains active.</summary>
        public bool IsCapturing => true;
        /// <summary>Count ordinary native-boundary calls.</summary>
        internal int LegacyCalls;
        /// <summary>Count typed calls; no retry is hidden inside the adapter.</summary>
        internal int TypedCalls;
        /// <summary>Count diagnostic overloads separately.</summary>
        internal int DiagnosticCalls;
        /// <summary>One prescribed immutable outcome.</summary>
        internal GameCaptureAttempt Attempt = new(GameCaptureAttemptOutcome.ReadbackPending, pending: Pending());
        /// <inheritdoc />
        public GameCaptureFrame? Capture() { LegacyCalls++; return null; }
        /// <inheritdoc />
        public GameCaptureFrame? Capture(out GameCaptureCallTiming timing) { DiagnosticCalls++; timing = new(); return Capture(); }
        /// <inheritdoc />
        public GameCaptureAttempt CaptureAttempt() { TypedCalls++; return Attempt; }
        /// <inheritdoc />
        public GameCaptureAttempt CaptureAttempt(out GameCaptureCallTiming timing) { DiagnosticCalls++; timing = new(); return CaptureAttempt(); }
        /// <inheritdoc />
        public void Start(nint window, Dictionary<string, object>? settings = null) { }
        /// <inheritdoc />
        public void Stop() { }
        /// <inheritdoc />
        public void Dispose() { }
    }
}
