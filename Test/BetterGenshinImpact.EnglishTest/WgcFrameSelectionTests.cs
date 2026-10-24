using Fischless.GameCapture;
using Fischless.GameCapture.Graphics.Helpers;
using Windows.Graphics;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Runs the production two-pull selector with owned managed frames, without WinRT, GPU work or a game.</summary>
public sealed class WgcFrameSelectionTests
{
    /// <summary>The existing pool geometry used by these controlled acquisitions.</summary>
    private static readonly SizeInt32 CurrentSize = new() { Width = 1920, Height = 1080 };
    /// <summary>An accepted changed size must stop lookahead before the caller recreates its pool.</summary>
    private static readonly SizeInt32 ChangedSize = new() { Width = 1280, Height = 720 };

    /// <summary>One fake owned frame; property and disposal faults exercise the native ownership boundaries.</summary>
    private sealed class Frame(long timestamp, SizeInt32? size = null) : IDisposable
    {
        /// <summary>Immutable source timestamp exposed by the fake native frame.</summary>
        public long Timestamp { get; } = timestamp;
        /// <summary>Immutable content geometry exposed by the fake native frame.</summary>
        public SizeInt32 Size { get; } = size ?? CurrentSize;
        /// <summary>Optional controlled exception from reading SystemRelativeTime.</summary>
        public Exception? TimestampError { get; init; }
        /// <summary>Optional controlled exception from reading ContentSize.</summary>
        public Exception? SizeError { get; init; }
        /// <summary>Optional controlled exception after a disposal attempt.</summary>
        public Exception? DisposeError { get; init; }
        /// <summary>Number of ownership-release attempts; a failure must never cause a second attempt.</summary>
        public int DisposeCount { get; private set; }
        /// <summary>Number of times this frame reaches a simulated rendering consumer.</summary>
        public int RenderCount { get; private set; }
        /// <summary>Read a timestamp or inject its native-property error.</summary>
        public long ReadTimestamp() => TimestampError is { } error ? throw error : Timestamp;
        /// <summary>Read geometry or inject its native-property error.</summary>
        public SizeInt32 ReadSize() => SizeError is { } error ? throw error : Size;
        /// <summary>Only the selected, still-owned frame may reach the consumer.</summary>
        public void Render() { Assert.Equal(0, DisposeCount); RenderCount++; }
        /// <summary>Record every native-close attempt, even when that close fails.</summary>
        public void Dispose() { DisposeCount++; if (DisposeError is { } error) throw error; }
    }

    /// <summary>A deterministic pool/clock records ordering and leaves any third frame unconsumed.</summary>
    private sealed class Pool(params Frame?[] frames)
    {
        /// <summary>Finite native pull responses.</summary>
        private readonly Queue<Frame?> _frames = new(frames);
        /// <summary>Actual native pull attempts, including null and exceptions.</summary>
        public int Pulls { get; private set; }
        /// <summary>Number of immediate acquisition clock samples.</summary>
        public int ClockReads { get; private set; }
        /// <summary>Pull number on which a native call should throw.</summary>
        public int ThrowOnPull { get; init; }
        /// <summary>Native error preserved through ordinary selection cleanup.</summary>
        public Exception PullError { get; } = new InvalidOperationException("pool failure");
        /// <summary>Unconsumed responses prove selection does not drain until empty.</summary>
        public int Remaining => _frames.Count;
        /// <summary>Acquire one frame; no calls are hidden behind property access.</summary>
        private Frame? Take()
        {
            Pulls++;
            if (Pulls == ThrowOnPull) throw PullError;
            return _frames.Count > 0 ? _frames.Dequeue() : null;
        }
        /// <summary>Small deterministic clocks prove diagnostic mode does not restamp a source.</summary>
        private long Clock() => 100 + ++ClockReads;
        /// <summary>Exercise the production selector, asserting the clock precedes all frame properties.</summary>
        public Frame? Select(WgcCaptureGeneration generation, out GameCaptureSourceInfo? source,
            out SizeInt32 size, GameCaptureCallTiming? timing = null) =>
            WgcFrameSelection.TakeNewest(Take, frame =>
            {
                Assert.Equal(Pulls, ClockReads);
                return frame.ReadTimestamp();
            }, static frame => frame.ReadSize(), generation, CurrentSize, out source, out size, timing, Clock);
    }

    /// <summary>Ordinary and diagnostic selection perform the same two acquisitions and only render the newest.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void NewestOfTwoOwnsItsOriginalStampAndThirdFrameIsNotPulled(bool diagnostic)
    {
        var first = new Frame(1000);
        var second = new Frame(2000);
        var third = new Frame(3000);
        var pool = new Pool(first, second, third);
        var generation = new WgcCaptureGeneration();
        var timing = diagnostic ? new GameCaptureCallTiming() : null;
        using (var selected = pool.Select(generation, out var source, out var size, timing))
        {
            Assert.Same(second, selected);
            Assert.Equal(CurrentSize, size);
            Assert.Equal(new GameCaptureSourceInfo(generation.Epoch, 2000, 102), source);
            Assert.Equal(1, first.DisposeCount);
            selected!.Render();
            Assert.Equal(0, first.RenderCount);
            Assert.Equal(1, second.RenderCount);
            Assert.Null(generation.TryAcquire(1000, 9000));
            Assert.Null(generation.TryAcquire(2000, 9000));
            if (timing is not null)
            {
                Assert.Equal("acquired", timing.PoolResult);
                Assert.Same(source, timing.AcquiredSource);
                Assert.Equal(2, timing.PoolPullCount);
                Assert.Equal(2, timing.PoolFrameCount);
                Assert.Equal(1, timing.PoolDiscardedFrameCount);
                Assert.True(timing.PoolStartedAtTicks <= timing.PoolCompletedAtTicks);
                Assert.Null(timing.RenderStartedAtTicks); // Selection itself never renders/submits.
                Assert.Null(timing.SubmitStartedAtTicks);
            }
        }
        Assert.Equal(2, pool.Pulls);
        Assert.Equal(1, pool.Remaining);
        Assert.Equal(1, second.DisposeCount);
        Assert.Equal(0, third.DisposeCount);
    }

    /// <summary>A null pull ends the bounded inspection; a retained first frame remains caller-owned.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void NullStopsWithoutConsumingAnotherFrame(bool retainFirst)
    {
        var first = new Frame(1000);
        var untouched = new Frame(3000);
        var pool = retainFirst ? new Pool(first, null, untouched) : new Pool(null, untouched);
        var timing = new GameCaptureCallTiming();
        using var selected = pool.Select(new WgcCaptureGeneration(), out var source, out _, timing);
        Assert.Same(retainFirst ? first : null, selected);
        Assert.Equal(retainFirst ? 2 : 1, pool.Pulls);
        Assert.Equal(retainFirst ? 1 : 0, pool.ClockReads);
        Assert.Equal(1, pool.Remaining);
        Assert.Equal(retainFirst ? "acquired" : "empty", timing.PoolResult);
        Assert.Equal(retainFirst ? 1000L : (long?)null, source?.SourceTimestamp100ns);
        Assert.Equal(0, first.DisposeCount);
        Assert.Equal(0, untouched.DisposeCount);
    }

    /// <summary>A duplicate or regressing second source is discarded without renewing the selected first acquisition.</summary>
    [Theory]
    [InlineData(1000)]
    [InlineData(900)]
    [InlineData(0)]
    public void RejectedSecondSourceKeepsFirstStamp(long secondTimestamp)
    {
        var first = new Frame(1000);
        var rejected = new Frame(secondTimestamp) { SizeError = new InvalidOperationException("must not inspect geometry") };
        var pool = new Pool(first, rejected);
        var timing = new GameCaptureCallTiming();
        using var selected = pool.Select(new WgcCaptureGeneration(), out var source, out _, timing);
        Assert.Same(first, selected);
        Assert.Equal(101, source!.AcquiredAtStopwatchTicks);
        Assert.Same(source, timing.AcquiredSource);
        Assert.Equal("acquired", timing.PoolResult);
        Assert.Equal(1, rejected.DisposeCount);
        Assert.Equal(0, rejected.RenderCount);
    }

    /// <summary>Rejected frames still count toward the two-pull budget; only accepted geometry can stop selection.</summary>
    [Fact]
    public void RejectedFirstAllowsOneNewerFrameButTwoRejectedFramesReturnNothing()
    {
        var generation = new WgcCaptureGeneration();
        generation.TryAcquire(1000, 1);
        var rejected = new Frame(1000, ChangedSize);
        var fresh = new Frame(2000);
        var pool = new Pool(rejected, fresh);
        using (var selected = pool.Select(generation, out var source, out var size))
        {
            Assert.Same(fresh, selected);
            Assert.Equal(CurrentSize, size);
            Assert.Equal(102, source!.AcquiredAtStopwatchTicks);
        }
        var firstOld = new Frame(1000);
        var secondOld = new Frame(2000);
        var nextFresh = new Frame(3000);
        pool = new Pool(firstOld, secondOld, nextFresh);
        var timing = new GameCaptureCallTiming();
        Assert.Null(pool.Select(generation, out var none, out _, timing));
        Assert.Null(none);
        Assert.Equal("rejected_identity", timing.PoolResult);
        Assert.Null(timing.AcquiredSource);
        Assert.Equal(2, timing.PoolDiscardedFrameCount);
        Assert.Equal(1, firstOld.DisposeCount);
        Assert.Equal(1, secondOld.DisposeCount);
        Assert.Equal(1, pool.Remaining);
    }

    /// <summary>The first accepted resize stops lookahead, including a changed second frame.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void GeometryChangeStopsAtItsAcceptedCandidate(bool afterRetainedFrame)
    {
        var first = new Frame(1000);
        var resized = new Frame(2000, ChangedSize);
        var untouched = new Frame(3000);
        var pool = afterRetainedFrame ? new Pool(first, resized, untouched) : new Pool(resized, untouched);
        var generation = new WgcCaptureGeneration();
        using var selected = pool.Select(generation, out var source, out var size);
        Assert.Same(resized, selected);
        Assert.Equal(ChangedSize, size);
        Assert.Equal(afterRetainedFrame ? 2 : 1, pool.Pulls);
        Assert.Equal(afterRetainedFrame ? 1 : 0, first.DisposeCount);
        Assert.Null(generation.TryAcquire(source!.SourceTimestamp100ns, 9000));
        Assert.Equal(1, pool.Remaining);
        Assert.Equal(0, first.RenderCount);
        Assert.Equal(0, resized.RenderCount); // Caller must use its existing recreate-and-skip branch.
    }

    /// <summary>A native error on either pull prevents rendering and releases every earlier retained owner.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    public void PullFailureDisposesRetainedFrame(int failingPull)
    {
        var first = new Frame(1000);
        var pool = new Pool(first) { ThrowOnPull = failingPull };
        var generation = new WgcCaptureGeneration();
        var timing = new GameCaptureCallTiming();
        Assert.Same(pool.PullError, Assert.Throws<InvalidOperationException>(() => pool.Select(generation, out _, out _, timing)));
        Assert.Equal(failingPull, pool.Pulls);
        Assert.Equal(failingPull - 1, first.DisposeCount);
        Assert.Equal("threw", timing.PoolResult);
        Assert.Equal("pool", timing.FailureStage);
        Assert.NotNull(timing.PoolCompletedAtTicks);
        if (failingPull == 2) Assert.Null(generation.TryAcquire(1000, 9000));
    }

    /// <summary>Property faults dispose both owners; a size fault still consumes the already-read newer identity.</summary>
    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void PropertyFailureDisposesAllAcquisitions(bool second, bool sizeFailure)
    {
        var expected = new InvalidOperationException("property failure");
        var previous = new Frame(1000);
        var failed = new Frame(2000)
        {
            SizeError = sizeFailure ? expected : null,
            TimestampError = sizeFailure ? null : expected
        };
        var pool = second ? new Pool(previous, failed) : new Pool(failed);
        var generation = new WgcCaptureGeneration();
        var timing = new GameCaptureCallTiming();
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(() => pool.Select(generation, out _, out _, timing)));
        Assert.Equal(1, failed.DisposeCount);
        Assert.Equal(second ? 1 : 0, previous.DisposeCount);
        Assert.Equal("threw", timing.PoolResult);
        Assert.Equal(second ? 2 : 1, timing.PoolDiscardedFrameCount);
        if (sizeFailure) Assert.Null(generation.TryAcquire(2000, 9000));
        else if (second) Assert.Null(generation.TryAcquire(1000, 9000));
    }

    /// <summary>A superseded Close failure still releases the newest frame and retains known resize information for invalidation.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void SupersededDisposalFailureNeverLeaksNewFrame(bool bothThrow)
    {
        var first = new Frame(1000) { DisposeError = new InvalidOperationException("old close") };
        var newer = new Frame(2000, ChangedSize)
        { DisposeError = bothThrow ? new InvalidOperationException("new close") : null };
        var pool = new Pool(first, newer);
        var generation = new WgcCaptureGeneration();
        var timing = new GameCaptureCallTiming();
        GameCaptureSourceInfo? source = null;
        var size = CurrentSize;
        Assert.Throws<InvalidOperationException>(() => pool.Select(generation, out source, out size, timing));
        Assert.Equal(ChangedSize, size);
        Assert.Equal(2000, source!.SourceTimestamp100ns);
        Assert.Equal(102, source.AcquiredAtStopwatchTicks);
        Assert.Equal(1, first.DisposeCount);
        Assert.Equal(1, newer.DisposeCount);
        Assert.Equal(2, timing.PoolDiscardedFrameCount);
        Assert.Null(generation.TryAcquire(1000, 9000));
        Assert.Null(generation.TryAcquire(2000, 9000));
        Assert.Equal(0, newer.RenderCount);
    }

    /// <summary>A rejected second frame's Close failure also disposes the retained first candidate.</summary>
    [Fact]
    public void RejectedDisposalFailureReleasesRetainedFrame()
    {
        var first = new Frame(1000);
        var rejected = new Frame(1000) { DisposeError = new InvalidOperationException("rejected close") };
        var pool = new Pool(first, rejected);
        Assert.Throws<InvalidOperationException>(() => pool.Select(new WgcCaptureGeneration(), out _, out _));
        Assert.Equal(1, first.DisposeCount);
        Assert.Equal(1, rejected.DisposeCount);
        Assert.Equal(0, first.RenderCount);
    }

    /// <summary>A failed downstream render does not make either source eligible for a later acquisition.</summary>
    [Fact]
    public void FailedRenderDoesNotRenewSelectedOrDiscardedSources()
    {
        var first = new Frame(1000);
        var second = new Frame(2000);
        var generation = new WgcCaptureGeneration();
        Assert.Throws<InvalidOperationException>((Action)(() =>
        {
            using var selected = new Pool(first, second).Select(generation, out _, out _);
            selected!.Render();
            throw new InvalidOperationException("render failed");
        }));
        Assert.Equal(1, first.DisposeCount);
        Assert.Equal(1, second.DisposeCount);
        var timing = new GameCaptureCallTiming();
        Assert.Null(new Pool(new Frame(1000), new Frame(2000)).Select(generation, out _, out _, timing));
        Assert.Equal("rejected_identity", timing.PoolResult);
        Assert.Null(timing.AcquiredSource);
    }

    /// <summary>A retired generation rejects all candidates; a replacement gets its own epoch and first-acquisition clock.</summary>
    [Fact]
    public void RetiredGenerationCannotRenewSourcesInReplacement()
    {
        var old = new WgcCaptureGeneration();
        old.TryAcquire(1000, 1);
        old.Deactivate();
        var first = new Frame(1000);
        var second = new Frame(2000);
        Assert.Null(new Pool(first, second).Select(old, out _, out _));
        Assert.Equal(1, first.DisposeCount);
        Assert.Equal(1, second.DisposeCount);
        var replacement = new WgcCaptureGeneration();
        using var selected = new Pool(new Frame(1000)).Select(replacement, out var source, out _);
        Assert.Equal(replacement.Epoch, source!.CaptureEpoch);
        Assert.NotEqual(old.Epoch, source.CaptureEpoch);
        Assert.Equal(101, source.AcquiredAtStopwatchTicks);
    }
}
