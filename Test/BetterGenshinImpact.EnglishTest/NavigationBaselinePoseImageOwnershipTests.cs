using System.Runtime.InteropServices;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Common.Map.MiniMap;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using OpenCvSharp;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU Mat ownership and same-pixel minimap checks; no capture, input, windows or timing claims.</summary>
public sealed class NavigationBaselinePoseImageOwnershipTests
{
    /// <summary>Use the actual CaptureContent constructor with an inert explicit-size desktop root.</summary>
    private static CaptureContent ActualContent(Mat image) =>
        new(image, 0, 0, new FakeSystemInfo(new RECT(0, 0, image.Width, image.Height), 1));

    /// <summary>Keep normalization outside allocation-selection fixtures so they inspect the exact transferred wrapper.</summary>
    private static CaptureContent HeaderContent(Mat image) => new(new ImageRegion(image, 0, 0));

    /// <summary>Construct deterministic native geometry with a textured minimap and no external assets.</summary>
    private static Mat Texture(int seed)
    {
        var frame = new Mat(1080, 1920, MatType.CV_8UC3, new Scalar(19, 37, 83));
        try
        {
            var bytes = new byte[212 * 212 * 3];
            new Random(seed).NextBytes(bytes);
            using var texture = new Mat(212, 212, MatType.CV_8UC3);
            Marshal.Copy(bytes, 0, texture.Data, bytes.Length);
            using var crop = new Mat(frame, MapAssets.Get(1920, 1080).MimiMapRect);
            texture.CopyTo(crop);
            return frame;
        }
        catch { frame.Dispose(); throw; }
    }

    /// <summary>Region disposal releases its own header while the caller's wrapper and pixels remain usable.</summary>
    [Fact]
    public void DesktopHeaderIsDistinctAndContentDisposalPreservesFrame()
    {
        using var frame = Texture(7);
        using var before = frame.Clone();
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, true, ActualContent);
        var owned = content.CaptureRectArea.SrcMat;
        Assert.NotSame(frame, owned);
        Assert.Equal(frame.Data, owned.Data);
        Assert.Equal(frame.Step(), owned.Step());
        Assert.Equal(0, Cv2.Norm(frame, owned, NormTypes.INF));
        content.Dispose();
        Assert.True(owned.IsDisposed);
        Assert.False(frame.IsDisposed);
        Assert.Equal(0, Cv2.Norm(before, frame, NormTypes.INF));
    }

    /// <summary>The distinct header owns a reference even if a caller retires its wrapper first.</summary>
    [Fact]
    public void HeaderRetainsAllocationAfterSourceWrapperRetires()
    {
        using var frame = Texture(42);
        using var expected = frame.Clone();
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, true, ActualContent);
        frame.Dispose();
        Assert.Equal(0, Cv2.Norm(expected, content.CaptureRectArea.SrcMat, NormTypes.INF));
    }

    /// <summary>A separate header preserves row stride and offset without converting a view into a raw unmanaged borrow.</summary>
    [Fact]
    public void HeaderPreservesSourceStrideAndOffset()
    {
        using var allocation = new Mat(1082, 1922, MatType.CV_8UC3, Scalar.All(23));
        using var frame = new Mat(allocation, new Rect(1, 1, 1920, 1080));
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, true, ActualContent);
        Assert.False(frame.IsContinuous());
        Assert.Equal(frame.Data, content.CaptureRectArea.SrcMat.Data);
        Assert.Equal(frame.Step(), content.CaptureRectArea.SrcMat.Step());
        Assert.Equal(0, Cv2.Norm(frame, content.CaptureRectArea.SrcMat, NormTypes.INF));
        content.Dispose();
        Assert.False(allocation.IsDisposed);
        Assert.False(frame.IsDisposed);
        Assert.Equal(23, frame.At<Vec3b>(0, 0).Item0);
    }

    /// <summary>Non-Desktop, changed dimensions and four-channel inputs keep an independent deep copy.</summary>
    [Theory]
    [InlineData(false, 1920, 1080, 3)]
    [InlineData(true, 1280, 720, 3)]
    [InlineData(true, 1919, 1080, 3)]
    [InlineData(true, 1920, 1079, 3)]
    [InlineData(true, 1920, 1080, 4)]
    public void OtherSelectionsKeepDeepCopy(bool desktopBgr, int width, int height, int channels)
    {
        using var frame = new Mat(height, width, channels == 3 ? MatType.CV_8UC3 : MatType.CV_8UC4, Scalar.All(31));
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, desktopBgr, HeaderContent);
        Assert.NotSame(frame, content.CaptureRectArea.SrcMat);
        Assert.NotEqual(frame.Data, content.CaptureRectArea.SrcMat.Data);
        Assert.Equal(frame.Type(), content.CaptureRectArea.SrcMat.Type());
        Assert.Equal(frame.Size(), content.CaptureRectArea.SrcMat.Size());
        Assert.Equal(0, Cv2.Norm(frame, content.CaptureRectArea.SrcMat, NormTypes.INF));
        frame.SetTo(Scalar.All(7));
        Assert.Equal(31, channels == 3 ? content.CaptureRectArea.SrcMat.At<Vec3b>(0, 0).Item0
            : content.CaptureRectArea.SrcMat.At<Vec4b>(0, 0).Item0);
    }

    /// <summary>Three channels alone do not select the byte-image optimization.</summary>
    [Fact]
    public void OtherPixelDepthKeepsDeepCopy()
    {
        using var frame = new Mat(1080, 1920, MatType.CV_32FC3, Scalar.All(0.25));
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, true, HeaderContent);
        Assert.NotEqual(frame.Data, content.CaptureRectArea.SrcMat.Data);
        Assert.Equal(frame.Type(), content.CaptureRectArea.SrcMat.Type());
        Assert.Equal(0, Cv2.Norm(frame, content.CaptureRectArea.SrcMat, NormTypes.INF));
    }

    /// <summary>A failure inside the actual region constructor retires the untransferred header or clone.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void ConstructorFailureDisposesPendingWrapperWithoutTouchingSource(bool desktopBgr)
    {
        using var frame = Texture(7);
        using var before = frame.Clone();
        Mat? pending = null;
        var calls = 0;
        Assert.Throws<NullReferenceException>(() =>
            NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, desktopBgr, image =>
            {
                pending = image;
                calls++;
                // Fail in the real constructor before DesktopRegion.Derive can receive the Mat.
                return new CaptureContent(image, 0, 0, null!);
            }));
        Assert.Equal(1, calls);
        Assert.NotNull(pending);
        Assert.NotSame(frame, pending);
        Assert.True(pending.IsDisposed);
        Assert.False(frame.IsDisposed);
        Assert.Equal(0, Cv2.Norm(before, frame, NormTypes.INF));
    }

    /// <summary>Retained evidence still uses independent pixels rather than the recognition header's shared allocation.</summary>
    [Fact]
    public void RetainedEvidenceCloneRemainsIndependent()
    {
        using var frame = Texture(2026);
        using var retained = frame.Clone();
        using var expected = retained.Clone();
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, true, ActualContent);
        Assert.NotEqual(retained.Data, content.CaptureRectArea.SrcMat.Data);
        // Deliberate fixture mutation proves evidence independence; production recognition must remain read-only.
        frame.SetTo(Scalar.All(0));
        content.Dispose();
        Assert.Equal(0, Cv2.Norm(expected, retained, NormTypes.INF));
    }

    /// <summary>The original content path and shared header produce exact crop, yaw, mask and prepared pixels.</summary>
    [Theory]
    [InlineData(7)]
    [InlineData(42)]
    [InlineData(2026)]
    public void MinimapPreparationIsEquivalentAndDoesNotMutateFrame(int seed)
    {
        using var frame = Texture(seed);
        using var before = frame.Clone();
        using var oldContent = ActualContent(frame.Clone());
        using var content = NativeNavigationBaselineOperations.CreatePoseCaptureContent(frame, true, ActualContent);
        using var oldCrop = new Mat(oldContent.CaptureRectArea.SrcMat, MapAssets.Get(oldContent.CaptureRectArea).MimiMapRect);
        using var crop = new Mat(content.CaptureRectArea.SrcMat, MapAssets.Get(content.CaptureRectArea).MimiMapRect);
        Assert.Equal(oldCrop.Size(), crop.Size());
        Assert.Equal(oldCrop.Type(), crop.Type());
        Assert.Equal(oldCrop.Step(), crop.Step());
        Assert.Equal(0, Cv2.Norm(oldCrop, crop, NormTypes.INF));
        using var oldProcessor = new MiniMapPreprocessor();
        using var processor = new MiniMapPreprocessor();
        using var expected = oldProcessor.TryPrepare(oldCrop, 0);
        using var actual = processor.TryPrepare(crop, 0);
        Assert.NotNull(expected);
        Assert.NotNull(actual);
        Assert.Equal(expected.YawDegrees, actual.YawDegrees);
        Assert.Equal(expected.YawConfidence, actual.YawConfidence);
        Assert.Equal(0, Cv2.Norm(expected.Pixels, actual.Pixels, NormTypes.INF));
        Assert.Equal(0, Cv2.Norm(expected.Mask, actual.Mask, NormTypes.INF));
        Assert.Equal(0, Cv2.Norm(before, frame, NormTypes.INF));
        // Prepared outputs own their storage after every borrowed input owner and scratch processor retires.
        oldCrop.Dispose(); crop.Dispose(); oldContent.Dispose(); content.Dispose(); frame.Dispose();
        oldProcessor.Dispose(); processor.Dispose();
        Assert.Equal(0, Cv2.Norm(expected.Pixels, actual.Pixels, NormTypes.INF));
        Assert.Equal(0, Cv2.Norm(expected.Mask, actual.Mask, NormTypes.INF));
    }
}
