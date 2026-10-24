using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using OpenCvSharp;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Compatibility of existing frame construction and the explicit new host-evidence variant.</summary>
public sealed class GameCaptureHostSnapshotTests
{
    /// <summary>Existing signatures retain null host metadata and exact source identity.</summary>
    [Fact]
    public void ExistingConstructorsRetainTheirOriginalEvidence()
    {
        using var first = new GameCaptureFrame(new Mat());
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 100, 200);
        using var second = new GameCaptureFrame(new Mat(), new RECT(1, 2, 3, 4), source);
        Assert.Null(first.SourceInfo);
        Assert.Null(first.HostSnapshotInfo);
        Assert.Same(source, second.SourceInfo);
        Assert.Null(second.HostSnapshotInfo);
    }

    /// <summary>Host snapshots retain their original identity/interval and do not synthesize source evidence.</summary>
    [Fact]
    public void HostConstructorPreservesTheExactRecordAndOwnsPixels()
    {
        var host = new GameCaptureHostSnapshotInfo(Guid.NewGuid(), 1, 100, 120, 1000);
        var pixels = new Mat();
        var frame = new GameCaptureFrame(pixels, new RECT(0, 0, 1920, 1080), null, host);
        Assert.Same(host, frame.HostSnapshotInfo);
        Assert.Null(frame.SourceInfo);
        frame.Dispose();
        Assert.True(pixels.IsDisposed);
    }

    /// <summary>Mixed evidence is rejected without taking ownership of the caller's Mat.</summary>
    [Fact]
    public void MixedKindsRejectBeforeOwnershipTransfer()
    {
        using var pixels = new Mat();
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 100, 200);
        var host = new GameCaptureHostSnapshotInfo(Guid.NewGuid(), 1, 100, 120, 1000);
        Assert.Throws<ArgumentException>(() => new GameCaptureFrame(pixels, null, source, host));
        Assert.False(pixels.IsDisposed);
    }

    /// <summary>The enum is additive and factory construction opens no native capture resource.</summary>
    [Fact]
    public void AdditiveFactoryDoesNotReplaceOldModesOrInventPolling()
    {
        Assert.Equal(0, (int)CaptureModes.BitBlt);
        Assert.Equal(1, (int)CaptureModes.WindowsGraphicsCapture);
        Assert.Equal(2, (int)CaptureModes.DwmGetDxSharedSurface);
        Assert.Equal(3, (int)CaptureModes.WindowsGraphicsCaptureHdr);
        Assert.Equal(5, (int)CaptureModes.WindowsGraphicsCaptureV2);
        Assert.Equal(6, (int)CaptureModes.DesktopDc);
        using var capture = GameCaptureFactory.Create(CaptureModes.DesktopDc);
        Assert.IsType<DesktopDcCapture>(capture);
        Assert.False(capture.IsCapturing);
        Assert.False(capture is IGameCaptureReadback);
        Assert.Null(capture.Capture());
    }
}
