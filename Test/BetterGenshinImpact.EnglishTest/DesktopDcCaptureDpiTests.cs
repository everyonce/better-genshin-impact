using Fischless.GameCapture.DesktopDc;
using OpenCvSharp;
using Xunit;
using FakeGdi = BetterGenshinImpact.EnglishTest.DesktopDcGdiOwnershipTests.FakeGdi;
using Scope = BetterGenshinImpact.EnglishTest.DesktopDcThreadDpiScopeTests.CallbackScope;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise actual capture publication and failure ordering around fake caller-local DPI scopes.</summary>
public sealed class DesktopDcCaptureDpiTests
{
    /// <summary>Start cannot expose an admitted generation until restoration has completed.</summary>
    [Fact]
    public void StartPublishesAfterRestoration()
    {
        DesktopDcCapture? capture = null;
        var events = new List<string>();
        capture = new DesktopDcCapture(_ => { events.Add("guard"); return DesktopDcTargetTests.Valid(); },
            new FakeGdi(), _ => new Mat(), () => 100, 1000,
            () => { events.Add("enter"); return new Scope(() => { Assert.False(capture!.IsCapturing); events.Add("restore"); }); });
        using (capture)
        {
            capture.Start(100);
            Assert.True(capture.IsCapturing);
            Assert.Equal(new[] { "enter", "guard", "restore" }, events);
        }
    }

    /// <summary>Host start includes DPI admission; completion follows GDI release and DPI restoration.</summary>
    [Fact]
    public void CaptureHostIntervalIncludesTheCompleteDpiScope()
    {
        var native = new FakeGdi();
        var events = new List<string>();
        var capturing = false;
        long clock = 100;
        using var capture = new DesktopDcCapture(_ => { events.Add("guard"); return DesktopDcTargetTests.Valid(); },
            native, _ => { events.Add("clone"); return new Mat(); },
            () => { events.Add("clock"); return ++clock; }, 1000,
            () => { events.Add("enter"); return new Scope(() =>
            { if (capturing) Assert.Equal("release_screen", native.Calls.Last()); events.Add("restore"); }); });
        capture.Start(100);
        events.Clear();
        capturing = true;
        using var frame = capture.Capture();
        Assert.NotNull(frame);
        Assert.Equal(new[] { "clock", "enter", "guard", "guard", "clone", "restore", "clock" }, events);
        Assert.Equal(101, frame.HostSnapshotInfo!.StartedAtStopwatchTicks);
        Assert.Equal(102, frame.HostSnapshotInfo.CompletedAtStopwatchTicks);
    }

    /// <summary>A Start restoration failure prevents publication and all later reuse.</summary>
    [Fact]
    public void StartRestorationFailureQuarantines()
    {
        var native = new FakeGdi();
        using var capture = new DesktopDcCapture(_ => DesktopDcTargetTests.Valid(), native, _ => new Mat(), () => 100, 1000,
            () => new Scope(() => throw new InvalidOperationException("restore")));
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
        Assert.False(capture.IsCapturing);
        capture.Stop();
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
        Assert.Throws<DesktopDcCleanupException>(() => capture.Capture());
        Assert.Empty(native.Calls);
    }

    /// <summary>A failed validation retains its original error even when DPI restoration also fails.</summary>
    [Fact]
    public void StartPreservesGuardAndRestorationErrors()
    {
        var primary = new InvalidOperationException("guard");
        using var capture = new DesktopDcCapture(_ => throw primary, new FakeGdi(), _ => new Mat(), () => 100, 1000,
            () => new Scope(() => throw new InvalidOperationException("restore")));
        var error = Assert.Throws<AggregateException>(() => capture.Start(100));
        Assert.Same(primary, error.InnerExceptions[0]);
        Assert.True(DesktopDcCleanupException.IsPresent(error));
        Assert.False(capture.IsCapturing);
    }

    /// <summary>No clone survives restoration failure and no completion clock or frame is published.</summary>
    [Fact]
    public void CaptureRestorationFailureDisposesPixelsBeforeQuarantine()
    {
        var native = new FakeGdi();
        var captures = false;
        var clocks = 0;
        Mat? image = null;
        using var capture = new DesktopDcCapture(_ => DesktopDcTargetTests.Valid(), native,
            _ => image = new Mat(), () => { clocks++; return 100; }, 1000,
            () => new Scope(() => { if (captures) throw new InvalidOperationException("restore"); }));
        capture.Start(100);
        captures = true;
        Assert.Throws<DesktopDcCleanupException>(() => capture.Capture());
        Assert.True(image!.IsDisposed);
        Assert.Equal("release_screen", native.Calls.Last());
        Assert.Equal(1, clocks);
        Assert.False(capture.IsCapturing);
        capture.Stop();
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
    }

    /// <summary>Copy and restoration errors remain distinct and GDI teardown precedes DPI restoration.</summary>
    [Fact]
    public void CapturePreservesPrimaryAndDpiCleanupFailures()
    {
        var native = new FakeGdi();
        var captures = false;
        using var capture = new DesktopDcCapture(_ => DesktopDcTargetTests.Valid(), native, _ => new Mat(), () => 100, 1000,
            () => new Scope(() =>
            {
                if (!captures) return;
                Assert.Equal("release_screen", native.Calls.Last());
                throw new InvalidOperationException("restore");
            }));
        capture.Start(100);
        captures = true;
        native.Failures.Add("copy");
        var error = Assert.Throws<AggregateException>(() => capture.Capture());
        Assert.Contains("SRCCOPY", error.InnerExceptions[0].Message);
        Assert.True(DesktopDcCleanupException.IsPresent(error));
        Assert.False(capture.IsCapturing);
    }

    /// <summary>Failed entry prevents guards/GDI and a known restored failure does not invent cleanup uncertainty.</summary>
    [Fact]
    public void CaptureEntryFailureDoesNotAcquireGdi()
    {
        var native = new FakeGdi();
        var captures = false;
        var reads = 0;
        var primary = new InvalidOperationException("entry verification failed after known restoration");
        using var capture = new DesktopDcCapture(_ => { reads++; return DesktopDcTargetTests.Valid(); }, native,
            _ => new Mat(), () => 100, 1000,
            () => captures ? throw primary : new Scope(() => { }));
        capture.Start(100);
        captures = true;
        Assert.Same(primary, Assert.Throws<InvalidOperationException>(() => capture.Capture()));
        Assert.Equal(1, reads);
        Assert.Empty(native.Calls);
        Assert.True(capture.IsCapturing);
    }
}
