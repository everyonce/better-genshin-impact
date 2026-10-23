using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.Core.Recognition.OpenCv;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Model.Area;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;
using OpenCvSharp;
using System.IO;
using System.Security.Cryptography;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU-only checks of shipped key-tip templates, negative evidence, ownership and native-image replay.</summary>
public sealed class AgentMotionRecognizerTests(ITestOutputHelper output)
{
    /// <summary>Exercise every existing Space/X rule on two capture sizes and channel layouts.</summary>
    public static IEnumerable<object[]> HintCases()
    {
        foreach (var width in new[] { 1280, 1920 })
        foreach (var channels in new[] { 3, 4 })
        foreach (var space in new[] { false, true })
        foreach (var x in new[] { false, true })
            yield return [width, channels, space, x];
    }

    /// <summary>Use the actual shipped assets and preserve the existing recognizer's X-only negative fallback.</summary>
    [Theory]
    [MemberData(nameof(HintCases))]
    public void ShippedHintsMatchExistingRuleWithoutChangingBorrowedPixels(int width, int channels, bool space, bool x)
    {
        var height = width * 9 / 16;
        using var fixture = new HintFixture(width, height);
        using var pixels = new Mat(height, width, channels == 4 ? MatType.CV_8UC4 : MatType.CV_8UC3, Scalar.Black);
        if (space) Paste(pixels, fixture.Space, false);
        if (x) Paste(pixels, fixture.X, true);
        using var before = pixels.Clone();
        var evidence = AgentMotionRecognizer.Recognize(pixels, true, fixture.Get);
        Assert.Equal(space ? x ? AgentMotionStatus.Climb : AgentMotionStatus.Fly : AgentMotionStatus.Normal, evidence.Status);
        Assert.Equal(space, evidence.SpaceKeyMatched);
        Assert.Equal(x, evidence.XKeyMatched);
        Assert.Equal(AgentMotionEvidence.MethodName, evidence.Method);
        Assert.True(double.IsFinite(evidence.RecognitionMs) && evidence.RecognitionMs >= 0);
        Assert.Equal(0, Cv2.Norm(before, pixels));
        using var region = Borrow(pixels);
        using var existingSpace = region.Find(fixture.Space);
        using var existingX = region.Find(fixture.X);
        Assert.Equal(existingSpace.IsExist(), evidence.SpaceKeyMatched);
        Assert.Equal(existingX.IsExist(), evidence.XKeyMatched);
    }

    /// <summary>The canonical 1080p scale is retained for larger captures instead of losing small key tips.</summary>
    [Fact]
    public void LargerCaptureNormalizesBeforeUsingExistingHints()
    {
        using var fixture = new HintFixture(1920, 1080);
        using var canonical = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
        Paste(canonical, fixture.Space, false);
        Paste(canonical, fixture.X, true);
        using var large = new Mat();
        Cv2.Resize(canonical, large, new Size(3840, 2160), interpolation: InterpolationFlags.Nearest);
        Assert.Equal(AgentMotionStatus.Climb, AgentMotionRecognizer.Recognize(large, true, fixture.Get).Status);
    }

    /// <summary>Identical shapes outside the existing key-tip ROI cannot manufacture climb evidence.</summary>
    [Fact]
    public void OutsideRoiHintsRemainNegativeEvidence()
    {
        using var fixture = new HintFixture(1920, 1080);
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
        using (var space = new Mat(pixels, new Rect(40, 40, fixture.Space.TemplateImageMat!.Width, fixture.Space.TemplateImageMat.Height)))
            fixture.Space.TemplateImageMat.CopyTo(space);
        using (var x = new Mat(pixels, new Rect(140, 40, fixture.X.TemplateImageMat!.Width, fixture.X.TemplateImageMat.Height)))
            fixture.X.TemplateImageMat.CopyTo(x);
        var evidence = AgentMotionRecognizer.Recognize(pixels, true, fixture.Get);
        Assert.Equal(AgentMotionStatus.Normal, evidence.Status);
        Assert.False(evidence.SpaceKeyMatched);
        Assert.False(evidence.XKeyMatched);
        Assert.Equal("space_key_not_found", evidence.Reason);
    }

    /// <summary>Blocked UI must not perform recognition or reuse the previous successful motion state.</summary>
    [Fact]
    public void BlockedWorldDoesNoTemplateWork()
    {
        using var pixels = new Mat();
        var calls = 0;
        var evidence = AgentMotionRecognizer.Recognize(pixels, false, (_, _) => { calls++; throw new InvalidOperationException(); });
        AssertUnavailable(evidence, "world_not_ready");
        Assert.Equal(0, calls);
        Assert.Equal(0, evidence.RecognitionMs);
    }

    /// <summary>Asset failures and unsupported pixel layouts are unknown, not an apparent grounded/normal state.</summary>
    [Fact]
    public void RecognitionErrorsAndInvalidPixelsFailUnknown()
    {
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
        AssertUnavailable(AgentMotionRecognizer.Recognize(pixels, true, (_, _) => throw new IOException("fixture missing")), "recognition_failed");
        using var gray = new Mat(1080, 1920, MatType.CV_8UC1, Scalar.Black);
        AssertUnavailable(AgentMotionRecognizer.Recognize(gray, true, (_, _) => throw new InvalidOperationException()), "invalid_capture");
    }

    /// <summary>Even after recovery, a cached publication from a previous interruption cannot revive old motion hints.</summary>
    [Theory]
    [InlineData(true, true, 3, 3, true)]
    [InlineData(false, true, 3, 3, false)]
    [InlineData(true, false, 3, 3, false)]
    [InlineData(true, true, 3, 4, false)]
    public void PublicationRequiresBothReadyAndSameEpoch(bool frameReady, bool currentReady, long frameEpoch, long currentEpoch, bool visible)
    {
        var evidence = new AgentMotionEvidence(AgentMotionStatus.Fly, "key_tips_matched", AgentMotionEvidence.MethodName, 0.25, true, false);
        var frame = new AgentWorldReadiness(frameReady, "fixture", 9, 10, 11, 0.1, frameEpoch);
        var current = frame with { Ready = currentReady, Epoch = currentEpoch };
        var published = AgentStreamSession.MotionForReadiness(evidence, frame, current);
        if (visible) Assert.Same(evidence, published);
        else AssertUnavailable(published, "world_not_ready");
        var json = JObject.Parse(JsonConvert.SerializeObject(published, new JsonSerializerSettings
        { ContractResolver = new CamelCasePropertyNamesContractResolver() }));
        Assert.Equal(visible ? "fly" : "unknown", json["status"]!.Value<string>());
        Assert.Equal(visible ? 0.25 : 0, json["recognitionMs"]!.Value<double>());
    }

    /// <summary>Optional reviewed native images provide real normal, blocked and hash-pinned climbing evidence.</summary>
    [Fact]
    public void ReplayReviewedNativeWorldAndBlockedCaptures()
    {
        var reports = new List<object>();
        // These two unmodified r10 captures were visually reviewed for a wall-climbing pose and visible Space+X hints.
        // The native images remain local; hashes prevent a different screenshot silently inheriting the positive label.
        var reviewedClimbHashes = new[]
        {
            "b0b5253212c63b58ff1c20203d13c09d3ef6bee469d1e95ba17ecf75f691695b",
            "22c5209116bd4cc9fa7ac6607940d4a55617028efef19585e7c0645ee7e31b2f"
        };
        foreach (var (variable, expectedStatus) in new[]
        {
            ("BETTERGI_MOTION_WORLD_IMAGES", AgentMotionStatus.Normal),
            ("BETTERGI_MOTION_BLOCKED_IMAGES", AgentMotionStatus.Unknown),
            ("BETTERGI_MOTION_CLIMB_IMAGES", AgentMotionStatus.Climb)
        })
        foreach (var path in (Environment.GetEnvironmentVariable(variable) ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            var sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
            if (expectedStatus == AgentMotionStatus.Climb) Assert.Contains(sha256, reviewedClimbHashes);
            var blocked = expectedStatus == AgentMotionStatus.Unknown;
            using var pixels = Cv2.ImRead(path);
            Assert.False(pixels.Empty(), path);
            using var before = pixels.Clone();
            using var world = new AgentWorldReadinessTests.TemplateFixture(pixels.Width, pixels.Height);
            var worldEvidence = AgentWorldRecognizer.Recognize(pixels, world.Get);
            Assert.Equal(!blocked, worldEvidence == AgentWorldEvidence.WorldHud);
            using var hints = new HintFixture(pixels.Width, pixels.Height);
            var evidence = AgentMotionRecognizer.Recognize(pixels, !blocked, hints.Get);
            Assert.Equal(expectedStatus, evidence.Status);
            Assert.Equal(AgentMotionEvidence.MethodName, evidence.Method);
            if (expectedStatus == AgentMotionStatus.Climb)
            {
                Assert.True(evidence.SpaceKeyMatched);
                Assert.True(evidence.XKeyMatched);
                Assert.Equal("key_tips_matched", evidence.Reason);
            }
            Assert.Equal(0, Cv2.Norm(before, pixels));
            var caseKind = expectedStatus switch
            {
                AgentMotionStatus.Climb => "captured-world-climb",
                AgentMotionStatus.Unknown => "captured-blocked",
                _ => "captured-world-negative"
            };
            reports.Add(new { path, sha256, caseKind, expectedStatus = expectedStatus.ToString(),
                worldEvidence = worldEvidence.ToString(), evidence });
        }
        var json = JsonConvert.SerializeObject(reports, Formatting.Indented);
        output.WriteLine(json);
        if (Environment.GetEnvironmentVariable("BETTERGI_MOTION_REPORT") is { Length: > 0 } destination)
            File.WriteAllText(destination, json);
    }

    /// <summary>Unavailable results retain no misleading positive or negative match booleans.</summary>
    private static void AssertUnavailable(AgentMotionEvidence evidence, string reason)
    {
        Assert.Equal(AgentMotionStatus.Unknown, evidence.Status);
        Assert.Equal(reason, evidence.Reason);
        Assert.Null(evidence.SpaceKeyMatched);
        Assert.Null(evidence.XKeyMatched);
        Assert.True(double.IsFinite(evidence.RecognitionMs) && evidence.RecognitionMs >= 0);
    }

    /// <summary>Borrow the native pixels through a disposable header only.</summary>
    private static ImageRegion Borrow(Mat pixels) => new(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);

    /// <summary>Place non-overlapping shipped hints at opposite ends of their configured ROI.</summary>
    private static void Paste(Mat pixels, RecognitionObject recognition, bool right)
    {
        var template = recognition.TemplateImageMat!;
        var roi = recognition.RegionOfInterest;
        using var target = new Mat(pixels, new Rect(right ? roi.Right - template.Width : roi.X, roi.Y, template.Width, template.Height));
        if (pixels.Channels() == 4) Cv2.CvtColor(template, target, ColorConversionCodes.BGR2BGRA);
        else template.CopyTo(target);
    }

    /// <summary>Load only the shipped key-tip assets with their exact default threshold, scale and existing ROI.</summary>
    private sealed class HintFixture : IDisposable
    {
        /// <summary>Existing Space hint template.</summary>
        public RecognitionObject Space { get; }
        /// <summary>Existing X hint template.</summary>
        public RecognitionObject X { get; }

        /// <summary>Mirror Recognition.json's keyTip rectangle and RecognitionAssets' reference scaling.</summary>
        public HintFixture(int width, int height)
        {
            var scale = width / 1920.0;
            var roi = new Rect((int)(width - 350 * scale), (int)(height - 70 * scale), (int)(200 * scale), (int)(70 * scale));
            Space = Load("key_space.png", roi, scale);
            X = Load("key_x.png", roi, scale);
        }

        /// <summary>Return the same object for grayscale fast-path and existing ImageRegion.Find parity checks.</summary>
        public RecognitionObject Get(string name, ImageRegion region)
        {
            Assert.InRange(region.Width, 1, AgentMotionRecognizer.MaxWidth);
            Assert.InRange(region.Height, 1, AgentMotionRecognizer.MaxHeight);
            return name == "SpaceKey" ? Space : name == "XKey" ? X : throw new ArgumentException(name);
        }

        /// <summary>Read and scale an existing asset without constructing app services.</summary>
        private static RecognitionObject Load(string file, Rect roi, double scale)
        {
            using var original = Cv2.ImRead(Path.Combine(AppContext.BaseDirectory, "GameTask", "Common", "Element", "Assets", "1920x1080", file));
            Assert.False(original.Empty());
            var resized = ResizeHelper.Resize(original, scale);
            return new RecognitionObject { RecognitionType = RecognitionTypes.TemplateMatch,
                TemplateImageMat = ReferenceEquals(original, resized) ? original.Clone() : resized,
                RegionOfInterest = roi, DrawOnWindow = false }.InitTemplate();
        }

        /// <summary>Release both template representations after the offline test.</summary>
        public void Dispose()
        {
            foreach (var template in new[] { Space, X })
            {
                template.TemplateImageGreyMat?.Dispose();
                template.TemplateImageMat?.Dispose();
            }
        }
    }
}
