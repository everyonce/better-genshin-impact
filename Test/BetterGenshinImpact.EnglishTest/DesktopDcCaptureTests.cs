using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using OpenCvSharp;
using Vanara.PInvoke;
using Xunit;
using FakeGdi = BetterGenshinImpact.EnglishTest.DesktopDcGdiOwnershipTests.FakeGdi;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercises the actual capture transaction with fake GDI/targets and small CPU Mats; no window/capture native APIs run.</summary>
public sealed class DesktopDcCaptureTests
{
    /// <summary>Create a controlled transaction while retaining real Mat ownership and public frame publication.</summary>
    private static DesktopDcCapture Create(FakeGdi native, Func<nint, DesktopDcTargetSnapshot>? reader = null,
        Func<DesktopDcGdiOwner, Mat>? clone = null, Func<long>? clock = null)
    {
        long ticks = 100;
        return new DesktopDcCapture(reader ?? (_ => DesktopDcTargetTests.Valid()), native,
            clone ?? (_ => new Mat(2, 2, MatType.CV_8UC3, Scalar.All(7))),
            clock ?? (() => Interlocked.Increment(ref ticks)), 1000,
            () => new DesktopDcThreadDpiScopeTests.CallbackScope(() => { }));
    }

    /// <summary>Frame evidence starts before guards and ends after actual cleanup, with no WGC source information.</summary>
    [Fact]
    public void HostIntervalAndIdentityArePublishedOnlyAfterCleanup()
    {
        var native = new FakeGdi();
        var events = new List<string>();
        long ticks = 100;
        using var capture = Create(native, _ => { events.Add("guard"); return DesktopDcTargetTests.Valid(); },
            owner => { events.Add("clone"); Assert.Equal((nint)40, owner.Bits); return new Mat(2, 2, MatType.CV_8UC3); },
            () =>
            {
                events.Add("clock");
                if (events.Contains("clone")) Assert.Equal("release_screen", native.Calls.Last());
                return ++ticks;
            });
        capture.Start(100, new Dictionary<string, object> { ["autoFixWin11BitBlt"] = true, ["UseCpuConvert"] = true });
        Assert.Empty(native.Calls);
        events.Clear();
        using var first = capture.Capture();
        Assert.NotNull(first);
        Assert.Equal(new[] { "clock", "guard", "guard", "clone", "clock" }, events);
        Assert.Null(first.SourceInfo);
        Assert.NotNull(first.HostSnapshotInfo);
        Assert.Equal(new RECT(320, 180, 2240, 1260), first.CaptureRect!.Value);
        Assert.NotEqual(Guid.Empty, first.HostSnapshotInfo.CaptureEpoch);
        Assert.Equal(1, first.HostSnapshotInfo.SnapshotId);
        Assert.Equal(101, first.HostSnapshotInfo.StartedAtStopwatchTicks);
        Assert.Equal(102, first.HostSnapshotInfo.CompletedAtStopwatchTicks);
        Assert.Equal(1000, first.HostSnapshotInfo.ClockFrequency);
        events.Clear();
        using var second = capture.Capture();
        Assert.Equal(first.HostSnapshotInfo.CaptureEpoch, second!.HostSnapshotInfo!.CaptureEpoch);
        Assert.Equal(2, second.HostSnapshotInfo.SnapshotId);
        Assert.NotSame(first.Frame, second.Frame);
        Assert.False(first.Frame.IsDisposed);
        Assert.Equal(2, native.Calls.Count(item => item == "screen"));
        Assert.Equal(2, native.Calls.Count(item => item == "release_screen"));
        capture.Stop();
        Assert.Null(capture.Capture());
        capture.Start(100);
        using var third = capture.Capture();
        Assert.NotEqual(first.HostSnapshotInfo.CaptureEpoch, third!.HostSnapshotInfo!.CaptureEpoch);
        Assert.Equal(1, third.HostSnapshotInfo.SnapshotId);
    }

    /// <summary>Post-copy target drift fails before a clone and does not move the pinned crop or silently retry.</summary>
    [Fact]
    public void PostCopyTargetChangeDiscardsTheCapture()
    {
        var native = new FakeGdi();
        var reads = 0;
        var clones = 0;
        using var capture = Create(native, _ => ++reads == 3
                ? DesktopDcTargetTests.Valid() with { ScreenRect = new RECT(321, 180, 2241, 1260) }
                : DesktopDcTargetTests.Valid(),
            _ => { clones++; return new Mat(); });
        capture.Start(100);
        Assert.Throws<InvalidOperationException>(() => capture.Capture());
        Assert.Equal(0, clones);
        Assert.Equal(1, native.Calls.Count(item => item == "copy"));
        Assert.Equal("release_screen", native.Calls.Last());
    }

    /// <summary>Pre-copy identity/geometry drift reaches no GDI acquisition at all.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void PinnedIdentityChangesFailBeforeGdi(int kind)
    {
        var native = new FakeGdi();
        var reads = 0;
        var original = DesktopDcTargetTests.Valid();
        var changed = kind switch
        {
            0 => original with { ProcessId = 201 },
            1 => original with { ProcessCreationFileTime = original.ProcessCreationFileTime + 1 },
            _ => original with { Dpi = 120 }
        };
        using var capture = Create(native, _ => ++reads == 1 ? original : changed);
        capture.Start(100);
        Assert.Throws<InvalidOperationException>(() => capture.Capture());
        Assert.Empty(native.Calls);
    }

    /// <summary>A clone failure still cleans every acquired GDI resource and retains the primary exception.</summary>
    [Fact]
    public void CloneFailureDoesNotEscapeBorrowedResources()
    {
        var native = new FakeGdi();
        var primary = new InvalidOperationException("clone failed");
        using var capture = Create(native, clone: _ => throw primary);
        capture.Start(100);
        Assert.Same(primary, Assert.Throws<InvalidOperationException>(() => capture.Capture()));
        Assert.Equal("release_screen", native.Calls.Last());
        Assert.Equal(1, native.Calls.Count(item => item == "copy"));
    }

    /// <summary>Even an independent completed clone is disposed when cleanup cannot establish safe completion.</summary>
    [Theory]
    [InlineData("restore")]
    [InlineData("delete_bitmap")]
    [InlineData("delete_dc")]
    [InlineData("release_screen")]
    public void CleanupUncertaintyDisposesCloneAndQuarantinesPermanently(string operation)
    {
        var native = new FakeGdi();
        Mat? image = null;
        using var capture = Create(native, clone: _ => image = new Mat(2, 2, MatType.CV_8UC3));
        capture.Start(100);
        native.Failures.Add(operation);
        Assert.Throws<DesktopDcCleanupException>(() => capture.Capture());
        Assert.NotNull(image);
        Assert.True(image.IsDisposed);
        Assert.False(capture.IsCapturing);
        var count = native.Calls.Count;
        capture.Stop();
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
        Assert.Throws<DesktopDcCleanupException>(() => capture.Capture());
        capture.Dispose();
        Assert.Equal(count, native.Calls.Count);
    }

    /// <summary>Copy failure and cleanup failure survive together, with no frame or clean retry.</summary>
    [Fact]
    public void PrimaryAndCleanupFailuresAreBothRetained()
    {
        var native = new FakeGdi();
        using var capture = Create(native);
        capture.Start(100);
        native.Failures.UnionWith(new[] { "copy", "release_screen" });
        var failure = Assert.Throws<AggregateException>(() => capture.Capture());
        Assert.Contains("SRCCOPY", failure.InnerExceptions[0].Message);
        Assert.True(DesktopDcCleanupException.IsPresent(failure));
        Assert.False(capture.IsCapturing);
    }

    /// <summary>A query-handle cleanup error before acquisition also prevents later Start/Capture reuse.</summary>
    [Fact]
    public void StartQueryCleanupFailureQuarantinesWithoutGdi()
    {
        var native = new FakeGdi();
        using var capture = Create(native, _ => throw new DesktopDcCleanupException("query close failed"));
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
        capture.Stop();
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
        Assert.Empty(native.Calls);
    }

    /// <summary>Start, Capture and Stop can run on different threads because only Capture owns GDI handles.</summary>
    [Fact]
    public void LifecycleThreadsDoNotTransferGdiOwnership()
    {
        var native = new FakeGdi();
        using var capture = Create(native);
        Exception? failure = null;
        var startThread = new Thread(() => { try { capture.Start(100); } catch (Exception error) { failure = error; } });
        startThread.Start();
        Assert.True(startThread.Join(TimeSpan.FromSeconds(5)));
        Assert.Null(failure);
        var captureThread = new Thread(() => { try { using var image = capture.Capture(); } catch (Exception error) { failure = error; } });
        captureThread.Start();
        Assert.True(captureThread.Join(TimeSpan.FromSeconds(5)));
        Assert.Null(failure);
        capture.Stop();
        Assert.All(native.Threads, thread => Assert.Equal(captureThread.ManagedThreadId, thread));
        Assert.False(capture.IsCapturing);
    }

    /// <summary>A concurrent Stop waits for the call-owned cleanup; it cannot delete a live borrowed DIB.</summary>
    [Fact]
    public async Task ConcurrentStopWaitsForCaptureCleanup()
    {
        var native = new FakeGdi();
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        using var stopStarted = new ManualResetEventSlim();
        native.OnCopy = () => { entered.Set(); if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException(); };
        using var capture = Create(native);
        capture.Start(100);
        var pendingCapture = Task.Run(() => capture.Capture());
        Task? pendingStop = null;
        try
        {
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            pendingStop = Task.Run(() => { stopStarted.Set(); capture.Stop(); });
            Assert.True(stopStarted.Wait(TimeSpan.FromSeconds(5)));
            Assert.False(pendingStop.Wait(TimeSpan.FromMilliseconds(30)));
            Assert.DoesNotContain("release_screen", native.Calls);
        }
        finally { release.Set(); }
        using var frame = await pendingCapture.WaitAsync(TimeSpan.FromSeconds(5));
        if (pendingStop is not null) await pendingStop.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.NotNull(frame);
        Assert.Equal("release_screen", native.Calls.Last());
        Assert.False(capture.IsCapturing);
    }

    /// <summary>A reentrant Stop retires admission, but cannot make an old in-flight frame usable.</summary>
    [Fact]
    public void ReentrantStopRejectsTheInFlightSnapshot()
    {
        var native = new FakeGdi();
        using var capture = Create(native);
        capture.Start(100);
        native.OnCopy = capture.Stop;
        Assert.Throws<InvalidOperationException>(() => capture.Capture());
        Assert.Equal("release_screen", native.Calls.Last());
        Assert.False(capture.IsCapturing);
    }

    /// <summary>A returned clone is also discarded if a reentrant stop occurs during its creation.</summary>
    [Fact]
    public void StopDuringCloneCannotPublishAcrossGenerations()
    {
        var native = new FakeGdi();
        DesktopDcCapture? capture = null;
        Mat? image = null;
        capture = Create(native, clone: _ =>
        {
            capture!.Stop();
            Assert.Throws<InvalidOperationException>(() => capture.Start(100));
            return image = new Mat(2, 2, MatType.CV_8UC3);
        });
        using (capture)
        {
            capture.Start(100);
            Assert.Throws<InvalidOperationException>(() => capture.Capture());
            Assert.True(image!.IsDisposed);
        }
    }

    /// <summary>A backwards completion clock rejects and disposes pixels even when all native cleanup succeeded.</summary>
    [Fact]
    public void RegressingCompletionCannotPublishPixels()
    {
        var native = new FakeGdi();
        Mat? image = null;
        var times = new Queue<long>(new long[] { 100, 99 });
        using var capture = Create(native, clone: _ => image = new Mat(2, 2, MatType.CV_8UC3), clock: () => times.Dequeue());
        capture.Start(100);
        Assert.Throws<InvalidOperationException>(() => capture.Capture());
        Assert.True(image!.IsDisposed);
        Assert.Equal("release_screen", native.Calls.Last());
    }
}
