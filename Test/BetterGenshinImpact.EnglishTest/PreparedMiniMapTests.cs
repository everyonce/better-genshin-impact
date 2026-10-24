using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Core.Recognition.OpenCv.TemplateMatch;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Common.Map.Maps;
using BetterGenshinImpact.GameTask.Common.Map.Maps.Base;
using BetterGenshinImpact.GameTask.Common.Map.MiniMap;
using OpenCvSharp;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU-only equivalence and owned-output checks; optional saved captures never launch or capture the game.</summary>
public sealed class PreparedMiniMapTests(ITestOutputHelper output)
{
    /// <summary>Deterministic color texture exercises masking and rotation without external image assets.</summary>
    private static Mat Texture(int seed)
    {
        var bytes = new byte[212 * 212 * 3];
        new Random(seed).NextBytes(bytes);
        var image = new Mat(212, 212, MatType.CV_8UC3);
        Marshal.Copy(bytes, 0, image.Data, bytes.Length);
        return image;
    }

    /// <summary>The independent old calls and the new shared pass produce bit-identical pixels, masks and raw yaw/confidence.</summary>
    [Theory]
    [InlineData(7)]
    [InlineData(42)]
    [InlineData(2026)]
    public void SyntheticPixelsAndYawAreUnchanged(int seed)
    {
        using var image = Texture(seed);
        using var before = image.Clone();
        using var oldYaw = new MiniMapPreprocessor();
        using var oldMap = new MiniMapPreprocessor();
        using var shared = new MiniMapPreprocessor();
        var (yaw, confidence) = oldYaw.PredictRotationWithConfidence(image);
        var (pixels, mask) = oldMap.GetMiniMapAndMask(image);
        using (pixels)
        using (mask)
        using (var prepared = shared.TryPrepare(image, 0))
        {
            Assert.NotNull(prepared);
            Assert.Equal(yaw, prepared.YawDegrees); Assert.Equal(confidence, prepared.YawConfidence);
            Assert.Equal(0, Cv2.Norm(pixels, prepared.Pixels, NormTypes.INF));
            Assert.Equal(0, Cv2.Norm(mask, prepared.Mask, NormTypes.INF));
            Assert.Equal(0, Cv2.Norm(before, image, NormTypes.INF));
        }
    }

    /// <summary>Prepared outputs do not borrow mutable scratch or source pixels, and disposed outputs cannot be matched.</summary>
    [Fact]
    public void ResultOutlivesSourceAndPreprocessorWithoutMutation()
    {
        var preprocessor = new MiniMapPreprocessor();
        var source = Texture(7);
        using var prepared = preprocessor.TryPrepare(source, 0);
        Assert.NotNull(prepared);
        using var pixelsBefore = prepared.Pixels.Clone();
        using var maskBefore = prepared.Mask.Clone();
        source.SetTo(Scalar.All(0)); source.Dispose();
        using (var next = Texture(42))
        using (preprocessor.TryPrepare(next, 0)) { }
        preprocessor.Dispose();
        Assert.Equal(0, Cv2.Norm(pixelsBefore, prepared.Pixels, NormTypes.INF));
        Assert.Equal(0, Cv2.Norm(maskBefore, prepared.Mask, NormTypes.INF));
        var ownedPixels = prepared.Pixels;
        var ownedMask = prepared.Mask;
        prepared.Dispose(); prepared.Dispose();
        Assert.True(ownedPixels.IsDisposed); Assert.True(ownedMask.IsDisposed);
        Assert.Throws<ObjectDisposedException>(() => prepared.Pixels);
        Assert.Throws<ObjectDisposedException>(() => prepared.Mask);
    }

    /// <summary>A low-confidence image returns no prepared outputs and cannot contaminate the next valid preparation.</summary>
    [Fact]
    public void RejectYawBeforeMaskPreparationAndRecoverNextImage()
    {
        using var preprocessor = new MiniMapPreprocessor();
        using var black = new Mat(212, 212, MatType.CV_8UC3, Scalar.All(0));
        var (_, confidence) = preprocessor.PredictRotationWithConfidence(black);
        Assert.True(confidence < 0.2f);
        Assert.Null(preprocessor.TryPrepare(black, 0.2f));
        using var image = Texture(42);
        using var fresh = new MiniMapPreprocessor();
        using var expected = fresh.TryPrepare(image, 0);
        using var actual = preprocessor.TryPrepare(image, 0);
        Assert.NotNull(expected); Assert.NotNull(actual);
        Assert.Equal(expected.YawDegrees, actual.YawDegrees);
        Assert.Equal(expected.YawConfidence, actual.YawConfidence);
        Assert.Equal(0, Cv2.Norm(expected.Pixels, actual.Pixels, NormTypes.INF));
        Assert.Equal(0, Cv2.Norm(expected.Mask, actual.Mask, NormTypes.INF));
    }

    /// <summary>Malformed policy thresholds fail before processing or allocating a prepared image.</summary>
    [Theory]
    [InlineData(float.NaN)]
    [InlineData(float.PositiveInfinity)]
    [InlineData(-0.1f)]
    [InlineData(1.01f)]
    public void RejectMalformedConfidenceThreshold(float threshold)
    {
        using var preprocessor = new MiniMapPreprocessor();
        using var source = Texture(7);
        Assert.Throws<ArgumentOutOfRangeException>(() => preprocessor.TryPrepare(source, threshold));
    }

    /// <summary>Prepared local matching cannot invoke global lookup on the old non-positive-anchor fallback path.</summary>
    [Theory]
    [InlineData(0, 1)]
    [InlineData(1, -1)]
    [InlineData(float.NaN, 1)]
    [InlineData(1, float.PositiveInfinity)]
    public void LocalPreparedEntryRejectsInvalidAnchor(float x, float y)
    {
        using var processor = new MiniMapPreprocessor();
        using var image = Texture(7);
        using var prepared = processor.TryPrepare(image, 0);
        var map = new TeyvatMapTest();
        try
        {
            Assert.NotNull(prepared);
            Assert.Throws<ArgumentOutOfRangeException>(() => map.GetPreparedLocalPosition(prepared, x, y, 0));
            Assert.Equal(default, map.PrevSuccessResult.MapPos);
            Assert.Null(map.PrevSuccessResult.Layer);
        }
        finally { DisposeTestMapScratch(map); }
    }

    /// <summary>Dispose test-owned map scratch only; production map instances intentionally live in the global map cache.</summary>
    private static void DisposeTestMapScratch(SceneBaseMapByTemplateMatch map) =>
        ((MiniMapPreprocessor)typeof(SceneBaseMapByTemplateMatch).GetField("_miniMapPreprocessor", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(map)!).Dispose();

    /// <summary>Own the decoder stream explicitly, including image-decoding failures.</summary>
    private static Mat ReadImage(string path, ImreadModes mode = ImreadModes.Color)
    {
        using var stream = File.OpenRead(path);
        return Mat.FromStream(stream, mode);
    }

    /// <summary>Replay explicit local images with the shipped Mondstadt layer, and report paired CPU phases without timing assertions.</summary>
    [Fact]
    public void ReplaySavedNativeImagesAndMeasureCpuPhases()
    {
        var paths = (Environment.GetEnvironmentVariable("BETTERGI_MINIMAP_NATIVE_IMAGES") ?? "")
            .Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries);
        if (paths.Length == 0) { output.WriteLine("Optional saved-native replay was not requested."); return; }
        var assetRoot = Environment.GetEnvironmentVariable("BETTERGI_MINIMAP_ASSET_ROOT");
        Assert.False(string.IsNullOrEmpty(assetRoot));
        var layerDirectory = Path.Combine(assetRoot!, "Assets", "Map", "Teyvat");
        using var metadata = JsonDocument.Parse(File.ReadAllText(Path.Combine(layerDirectory, "city_info.json")));
        var description = metadata.RootElement.EnumerateArray().Single(item => item.GetProperty("LayerId").GetString() == "City_102");
        using var coarse = ReadImage(Path.Combine(layerDirectory, "City_102_color.webp"));
        using var fine = ReadImage(Path.Combine(layerDirectory, "City_102_gray.webp"), ImreadModes.Grayscale);
        using var matcher = new FastSqDiffMatcher(coarse, new Size(52, 52));
        var layer = new BaseMapLayerByTemplateMatch
        {
            LayerId = "City_102", Floor = description.GetProperty("Floor").GetInt32(),
            Scale = description.GetProperty("Scale").GetSingle(), Left = description.GetProperty("Left").GetSingle(),
            Top = description.GetProperty("Top").GetSingle(), CoarseColorMatcher = matcher
        };
        layer.FineGrayMap.Dispose(); layer.FineGrayMap = fine;
        var oldMap = new TeyvatMapTest { Layers = [layer] };
        var sharedMap = new TeyvatMapTest { Layers = [layer] };
        var reports = new List<object>();
        try
        {
            using var oldYaw = new MiniMapPreprocessor();
            using var shared = new MiniMapPreprocessor();
            var anchor = oldMap.ConvertGenshinMapCoordinatesToImageCoordinates(new Point2f(-867.7041015625f, 2281.378173828125f));
            foreach (var path in paths)
            {
                var sourceHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));
                using var pixels = Cv2.ImRead(path);
                Assert.False(pixels.Empty());
                using var minimap = new Mat(pixels, MapAssets.Get(pixels.Width, pixels.Height).MimiMapRect);
                using var unchanged = minimap.Clone();
                var timings = new List<object>();
                for (var i = 0; i < 24; i++)
                {
                    // Alternate arm order after warm-up so clock/cache drift does not always favor one implementation.
                    float yaw = 0, confidence = 0, sharedYaw = 0, sharedConfidence = 0;
                    Point2f oldPosition = default, sharedPosition = default;
                    double oldYawMs = 0, oldMapMs = 0, sharedPrepareMs = 0, sharedMapMs = 0;
                    void Original()
                    {
                        var clock = Stopwatch.StartNew();
                        (yaw, confidence) = oldYaw.PredictRotationWithConfidence(minimap);
                        oldYawMs = clock.Elapsed.TotalMilliseconds;
                        clock.Restart(); oldPosition = oldMap.GetMiniMapPosition(minimap, anchor.X, anchor.Y, 0);
                        oldMapMs = clock.Elapsed.TotalMilliseconds;
                    }
                    void Prepared()
                    {
                        var clock = Stopwatch.StartNew();
                        using var prepared = shared.TryPrepare(minimap, 0.2f);
                        sharedPrepareMs = clock.Elapsed.TotalMilliseconds;
                        Assert.NotNull(prepared);
                        sharedYaw = prepared.YawDegrees; sharedConfidence = prepared.YawConfidence;
                        clock.Restart(); sharedPosition = sharedMap.GetPreparedLocalPosition(prepared, anchor.X, anchor.Y, 0);
                        sharedMapMs = clock.Elapsed.TotalMilliseconds;
                    }
                    if ((i & 1) == 0) { Original(); Prepared(); } else { Prepared(); Original(); }
                    // Parity work follows BOTH arms, so it cannot warm only the second arm of a timing pair.
                    using (var prepared = shared.TryPrepare(minimap, 0.2f))
                    {
                        Assert.NotNull(prepared);
                        using var reference = new MiniMapPreprocessor();
                        var (oldPixels, oldMask) = reference.GetMiniMapAndMask(minimap);
                        using (oldPixels)
                        using (oldMask)
                        {
                            Assert.Equal(0, Cv2.Norm(oldPixels, prepared.Pixels, NormTypes.INF));
                            Assert.Equal(0, Cv2.Norm(oldMask, prepared.Mask, NormTypes.INF));
                        }
                    }
                    Assert.Equal(yaw, sharedYaw); Assert.Equal(confidence, sharedConfidence);
                    Assert.NotEqual(default, oldPosition); Assert.Equal(oldPosition, sharedPosition);
                    Assert.Equal(oldMap.PrevSuccessResult.MapPos, sharedMap.PrevSuccessResult.MapPos);
                    Assert.Equal(oldMap.PrevSuccessResult.Confidence, sharedMap.PrevSuccessResult.Confidence);
                    Assert.Same(layer, oldMap.PrevSuccessResult.Layer); Assert.Same(layer, sharedMap.PrevSuccessResult.Layer);
                    Assert.InRange(oldMap.PrevSuccessResult.Confidence, 0.99, 1);
                    if (i >= 4) timings.Add(new { originalFirst = (i & 1) == 0, oldYawMs, oldMapMs,
                        originalTotalMs = oldYawMs + oldMapMs, sharedPrepareMs, sharedMapMs,
                        preparedTotalMs = sharedPrepareMs + sharedMapMs });
                }
                Assert.Equal(0, Cv2.Norm(unchanged, minimap, NormTypes.INF));
                Assert.Equal(sourceHash, Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))));
                // An explicit positive but out-of-layer local anchor must fail, retaining each arm's last successful cache.
                var oldSuccess = oldMap.PrevSuccessResult;
                var sharedSuccess = sharedMap.PrevSuccessResult;
                using (var prepared = shared.TryPrepare(minimap, 0.2f))
                {
                    Assert.NotNull(prepared);
                    Assert.Equal(default, oldMap.GetMiniMapPosition(minimap, 1, 1, 0));
                    Assert.Equal(default, sharedMap.GetPreparedLocalPosition(prepared, 1, 1, 0));
                    Assert.Equal(oldSuccess.MapPos, oldMap.PrevSuccessResult.MapPos);
                    Assert.Equal(oldSuccess.Confidence, oldMap.PrevSuccessResult.Confidence);
                    Assert.Same(oldSuccess.Layer, oldMap.PrevSuccessResult.Layer);
                    Assert.Equal(sharedSuccess.MapPos, sharedMap.PrevSuccessResult.MapPos);
                    Assert.Equal(sharedSuccess.Confidence, sharedMap.PrevSuccessResult.Confidence);
                    Assert.Same(sharedSuccess.Layer, sharedMap.PrevSuccessResult.Layer);
                }
                reports.Add(new { path, sha256 = sourceHash, imageWidth = pixels.Width, imageHeight = pixels.Height,
                    roi = MapAssets.Get(pixels.Width, pixels.Height).MimiMapRect.ToString(),
                    position = new { x = oldMap.PrevSuccessResult.MapPos.X, y = oldMap.PrevSuccessResult.MapPos.Y },
                    confidence = oldMap.PrevSuccessResult.Confidence, layer = "City_102", timings });
            }
        }
        finally { DisposeTestMapScratch(oldMap); DisposeTestMapScratch(sharedMap); }
        var report = JsonSerializer.Serialize(new { evidenceKind = "saved-native-cpu-equivalence", gameInput = false,
            gpuInference = false, layerScope = "City_102 only; both arms share the same shipped matcher and rank-0 algorithm",
            assets = new[] { "city_info.json", "City_102_color.webp", "City_102_gray.webp" }
                .Select(name => new { name, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(layerDirectory, name)))) }).ToArray(),
            exactPixelsMasksYawConfidencePosition = true, failedLocalMatchPreservesCache = true,
            measuredLiveLeaseBenefit = false, reports }, new JsonSerializerOptions { WriteIndented = true });
        output.WriteLine(report);
        if (Environment.GetEnvironmentVariable("BETTERGI_MINIMAP_REPORT") is { Length: > 0 } destination)
            File.WriteAllText(destination, report);
    }
}
