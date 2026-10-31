using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json.Linq;
using OpenCvSharp;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU-only native HUD checks, borrowed-pixel ownership, negative evidence, and optional retained-image replay.</summary>
public sealed class AgentCombatRecognizerTests(ITestOutputHelper output)
{
    /// <summary>Both supported capture layouts retain small bars and never mutate the original image.</summary>
    [Theory]
    [InlineData(1280, 3)]
    [InlineData(1280, 4)]
    [InlineData(1920, 3)]
    [InlineData(1920, 4)]
    public void NativeColorEvidenceRemainsBoundToBorrowedSource(int width, int channels)
    {
        using var pixels = Canvas(width, channels);
        var scale = width / 1920.0;
        Fill(pixels, scale, 808, 1008, 275, 5, new Scalar(34, 215, 150, 255));
        Fill(pixels, scale, 940, 1008, 75, 5, Scalar.White);
        Fill(pixels, scale, 800, 400, 120, 6, new Scalar(90, 90, 255, 255));
        using var before = pixels.Clone();
        var observation = Observation(width);
        var evidence = AgentCombatRecognizer.Recognize(pixels, observation, true);
        Assert.Equal("valid", evidence.State);
        Assert.Equal("green", evidence.PlayerHealthColor);
        Assert.InRange(evidence.PlayerHealthFractionEstimate!.Value, .89, .92);
        var bar = Assert.Single(evidence.EnemyBarCandidates);
        Assert.Equal((int)Math.Round(800 * scale), bar.X);
        Assert.Equal((int)Math.Round(400 * scale), bar.Y);
        Assert.Same(observation.SourceFrame, evidence.SourceFrame);
        Assert.Equal(observation.FrameId, evidence.FrameId);
        Assert.False(evidence.AuthorizesInput);
        Assert.False(evidence.EnemyIdentityVerified);
        Assert.False(evidence.KillVerified);
        Assert.Equal(0, Cv2.Norm(before, pixels));
    }

    /// <summary>Low health remains measurable through a text gap; stray end pixels cannot inflate fill.</summary>
    [Fact]
    public void RedHealthUsesConnectedRightEdgeAndRequiresLeftPrefix()
    {
        using var pixels = Canvas();
        Fill(pixels, 1, 808, 1008, 60, 5, new Scalar(90, 90, 255));
        Fill(pixels, 1, 826, 1008, 8, 5, Scalar.White);
        pixels.Set(1010, 1100, new Vec3b(90, 90, 255));
        var evidence = AgentCombatRecognizer.Recognize(pixels, Observation(), true);
        Assert.Equal("red", evidence.PlayerHealthColor);
        Assert.Equal(60.0 / 304, evidence.PlayerHealthFractionEstimate);
        pixels.Set(1010, 808, new Vec3b(0, 0, 0));
        evidence = AgentCombatRecognizer.Recognize(pixels, Observation() with { FrameId = 43 }, true);
        Assert.Equal("unknown", evidence.PlayerHealthColor);
        Assert.Null(evidence.PlayerHealthFractionEstimate);
    }

    /// <summary>World or source failures return no prior health or target values, even after a valid frame.</summary>
    [Fact]
    public void UnavailableFramesCannotReusePositiveEvidence()
    {
        using var pixels = Canvas();
        Fill(pixels, 1, 808, 1008, 275, 5, new Scalar(34, 215, 150));
        Fill(pixels, 1, 800, 400, 120, 6, new Scalar(90, 90, 255));
        Assert.Single(AgentCombatRecognizer.Recognize(pixels, Observation(), true).EnemyBarCandidates);
        foreach (var evidence in new[]
        {
            AgentCombatRecognizer.Recognize(pixels, Observation() with { FrameId = 43 }, false),
            AgentCombatRecognizer.Recognize(pixels, Observation() with { SourceFrame = null }, true),
            AgentCombatRecognizer.Recognize(pixels, Observation(1280), true)
        })
        {
            Assert.Equal("unavailable", evidence.State);
            Assert.Equal("unknown", evidence.PlayerHealthColor);
            Assert.Null(evidence.PlayerHealthFractionEstimate);
            Assert.Empty(evidence.EnemyBarCandidates);
        }
    }

    /// <summary>Red shapes outside the native target region, or with non-bar geometry, remain non-targets.</summary>
    [Fact]
    public void UnrelatedRedPixelsAndUnsupportedGeometryRemainUnknown()
    {
        using var pixels = Canvas();
        Fill(pixels, 1, 800, 30, 120, 6, new Scalar(90, 90, 255));
        Fill(pixels, 1, 700, 400, 20, 20, new Scalar(90, 90, 255));
        var evidence = AgentCombatRecognizer.Recognize(pixels, Observation(), true);
        Assert.Empty(evidence.EnemyBarCandidates);
        Assert.Equal("unknown", evidence.PlayerHealthColor);
        using var small = Canvas(960);
        Assert.Equal("unsupported_geometry", AgentCombatRecognizer.Recognize(small, Observation(960), true).Reason);
        using var invalid = new Mat(1080, 1920, MatType.CV_8UC1, Scalar.Black);
        Assert.Equal("invalid_capture", AgentCombatRecognizer.Recognize(invalid, Observation(), true).Reason);
    }

    /// <summary>A red scene or excessive plausible bars produces explicit ambiguity, never a truncated target list.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void RedOverloadClearsCandidates(bool dense)
    {
        using var pixels = Canvas();
        if (dense) Fill(pixels, 1, 400, 200, 200, 100, new Scalar(90, 90, 255));
        else for (var index = 0; index < 17; index++)
            Fill(pixels, 1, 400, 200 + index * 20, 40, 4, new Scalar(90, 90, 255));
        var evidence = AgentCombatRecognizer.Recognize(pixels, Observation(), true);
        Assert.True(evidence.RedMaskOverloaded);
        Assert.Empty(evidence.EnemyBarCandidates);
        Assert.Equal("red_mask_overloaded", evidence.Reason);
    }

    /// <summary>Capabilities advertise the limited estimator and cannot be mistaken for hostile or kill proof.</summary>
    [Fact]
    public void CapabilityMakesReadOnlyScopeExplicit()
    {
        var capability = JObject.FromObject(AgentCombatRecognizer.Capability);
        Assert.True(capability["readOnly"]!.Value<bool>());
        Assert.True(capability["sameFrame"]!.Value<bool>());
        Assert.False(capability["authorizesInput"]!.Value<bool>());
        Assert.Equal(808, capability["healthRow"]!["x"]!.Value<int>());
        Assert.Equal(304, capability["healthRow"]!["width"]!.Value<int>());
    }

    /// <summary>When explicitly supplied, replay preserved local PNGs and report measured CPU cost without launching BetterGI.</summary>
    [Fact]
    public void ExplicitRetainedImageReplay()
    {
        var paths = Environment.GetEnvironmentVariable("BETTERGI_COMBAT_REPLAY_IMAGES");
        if (string.IsNullOrEmpty(paths)) { output.WriteLine("No retained-image replay requested."); return; }
        var timings = new List<double>();
        foreach (var path in paths.Split(';', StringSplitOptions.RemoveEmptyEntries))
        {
            using var pixels = Cv2.ImRead(path);
            Assert.False(pixels.Empty());
            for (var index = 0; index < 22; index++)
            {
                var evidence = AgentCombatRecognizer.Recognize(pixels, Observation(pixels.Width), true);
                Assert.Equal("valid", evidence.State);
                Assert.Equal("green", evidence.PlayerHealthColor);
                Assert.InRange(evidence.PlayerHealthFractionEstimate!.Value, .88, .93);
                Assert.Empty(evidence.EnemyBarCandidates);
                if (index >= 2) timings.Add(evidence.RecognitionMs);
            }
            output.WriteLine($"Replayed native HUD: {path}");
        }
        timings.Sort();
        Assert.NotEmpty(timings);
        output.WriteLine($"Native HUD samples={timings.Count}; medianMs={timings[timings.Count / 2]:F4}; " +
            $"p95Ms={timings[(int)Math.Ceiling(timings.Count * .95) - 1]:F4}; maxMs={timings[^1]:F4}");
        // Measure positive component work separately; retained outdoor negatives cannot establish encounter cost.
        foreach (var barCount in new[] { 1, 8, 16 })
        {
            using var synthetic = Canvas();
            for (var index = 0; index < barCount; index++)
                Fill(synthetic, 1, 300 + index % 4 * 350, 200 + index / 4 * 100, 120, 6, new Scalar(90, 90, 255));
            timings.Clear();
            for (var index = 0; index < 22; index++)
            {
                var evidence = AgentCombatRecognizer.Recognize(synthetic, Observation(), true);
                Assert.Equal(barCount, evidence.EnemyBarCandidates.Count);
                if (index >= 2) timings.Add(evidence.RecognitionMs);
            }
            timings.Sort();
            output.WriteLine($"Synthetic native bars={barCount}; samples={timings.Count}; " +
                $"medianMs={timings[timings.Count / 2]:F4}; p95Ms={timings[18]:F4}; maxMs={timings[^1]:F4}");
        }
    }

    /// <summary>Create a native capture buffer owned by the fixture.</summary>
    private static Mat Canvas(int width = 1920, int channels = 3) =>
        new(width * 9 / 16, width, channels == 4 ? MatType.CV_8UC4 : MatType.CV_8UC3, Scalar.Black);

    /// <summary>Construct one immutable fixture source identity in the same observation clock.</summary>
    private static AgentObservation Observation(int width = 1920) =>
        new(42, 100, width, width * 9 / 16, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame("fixture", 1000000, 100, 101));

    /// <summary>Draw a scaled native rectangle without resizing away its small HUD details.</summary>
    private static void Fill(Mat pixels, double scale, int x, int y, int width, int height, Scalar color) =>
        Cv2.Rectangle(pixels, new Rect((int)Math.Round(x * scale), (int)Math.Round(y * scale),
            (int)Math.Round(width * scale), (int)Math.Round(height * scale)), color, -1);
}
