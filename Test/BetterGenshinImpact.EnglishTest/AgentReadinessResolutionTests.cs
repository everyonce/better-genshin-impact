using System.Diagnostics;
using System.IO;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Offline resolution evidence and regression checks for the selected production cap.</summary>
public sealed class AgentReadinessResolutionTests(ITestOutputHelper output)
{
    /// <summary>Production exposes the bounded image to the cached asset loader without changing aspect ratio.</summary>
    [Theory]
    [InlineData(1920, 1080, 960, 540)]
    [InlineData(3840, 2160, 960, 540)]
    [InlineData(1920, 900, 960, 450)]
    [InlineData(1600, 1000, 864, 540)]
    [InlineData(640, 360, 640, 360)]
    [InlineData(720, 1280, 303, 540)]
    public void ProductionUsesBoundedViewportWithoutUpscaling(int width, int height, int expectedWidth, int expectedHeight)
    {
        using var pixels = new Mat(height, width, MatType.CV_8UC4, Scalar.Black);
        using var templates = new AgentWorldReadinessTests.TemplateFixture(expectedWidth, expectedHeight);
        var observed = new List<Size>();
        var evidence = AgentWorldRecognizer.Recognize(pixels, (task, name, region) =>
        {
            observed.Add(new Size(region.Width, region.Height));
            return templates.Get(task, name, region);
        });
        Assert.Equal(AgentWorldEvidence.HudMissing, evidence);
        Assert.Equal(new Size(expectedWidth, expectedHeight), Assert.Single(observed));
        Assert.False(pixels.IsDisposed);
    }

    /// <summary>Compare both smaller candidates with native recognition across HUD, blockers, channels and aspect ratios.</summary>
    [Fact]
    public void ReportReducedReadinessEquivalenceAndCpuCost()
    {
        var results = new List<object>();
        foreach (var (width, height) in new[] { (1920, 1080), (1920, 900), (1600, 1000) })
        foreach (var channels in new[] { 3, 4 })
        foreach (var lastCorner in new[] { false, true })
        foreach (var state in new[] { "world", "modal", "confirm", "blank" })
        {
            using var templates = new AgentWorldReadinessTests.TemplateFixture(width, height);
            using var pixels = new Mat(height, width, channels == 4 ? MatType.CV_8UC4 : MatType.CV_8UC3, Scalar.Black);
            if (state != "blank") Paste(pixels, templates.Hud, lastCorner);
            if (state == "modal") Paste(pixels, templates.Modal, lastCorner);
            if (state == "confirm") Paste(pixels, templates.Confirm, lastCorner);
            var expected = state == "world" ? AgentWorldEvidence.WorldHud
                : state == "blank" ? AgentWorldEvidence.HudMissing : AgentWorldEvidence.BlockingUi;
            var name = $"synthetic-{width}x{height}-{channels}ch-{(lastCorner ? "last" : "first")}-{state}";
            // Only the native-size first-corner cases need repeated timings; every case still checks both decisions.
            Evaluate(name, pixels, expected, width == 1920 && height == 1080 && channels == 3 && !lastCorner, results);
        }

        // Native captures are supplied by the parent; this experiment never captures a desktop or accesses a game.
        var recordings = Environment.GetEnvironmentVariable("BETTERGI_RESOLUTION_BENCHMARK_IMAGES");
        foreach (var path in (recordings ?? string.Empty).Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            using var pixels = Cv2.ImRead(path);
            Assert.False(pixels.Empty(), $"Could not decode offline capture: {path}");
            Assert.True(pixels.Width <= 1920 && pixels.Height <= 1080,
                "Supply a capture already inside the existing1080p bounds, so old/new compare identical source pixels.");
            Evaluate(path, pixels, AgentWorldEvidence.WorldHud, true, results);
            using var templates = new AgentWorldReadinessTests.TemplateFixture(pixels.Width, pixels.Height);
            foreach (var lastCorner in new[] { false, true })
            {
                using var modal = pixels.Clone();
                Paste(modal, templates.Modal, lastCorner);
                Evaluate($"{path}-modal-{(lastCorner ? "last" : "first")}", modal, AgentWorldEvidence.BlockingUi, true, results);
            }
            using var noHud = pixels.Clone();
            using (var roi = new Mat(noHud, templates.Hud.RegionOfInterest)) roi.SetTo(Scalar.Black);
            Evaluate($"{path}-hud-removed", noHud, AgentWorldEvidence.HudMissing, true, results);
        }

        // Separately reviewed blocked screenshots must not be mislabeled as world-positive inputs.
        var negatives = Environment.GetEnvironmentVariable("BETTERGI_RESOLUTION_NEGATIVE_IMAGES");
        foreach (var path in (negatives ?? string.Empty).Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            using var pixels = Cv2.ImRead(path);
            Assert.False(pixels.Empty(), $"Could not decode offline blocked capture: {path}");
            Assert.True(pixels.Width <= 1920 && pixels.Height <= 1080);
            using var templates = new AgentWorldReadinessTests.TemplateFixture(pixels.Width, pixels.Height);
            var expected = ExistingRecognize(pixels, templates.Get);
            Assert.True(expected is AgentWorldEvidence.HudMissing or AgentWorldEvidence.BlockingUi);
            Evaluate(path, pixels, expected, true, results);
        }

        var json = JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true });
        output.WriteLine(json);
        if (Environment.GetEnvironmentVariable("BETTERGI_RESOLUTION_BENCHMARK_OUTPUT") is { Length: > 0 } destination)
            File.WriteAllText(destination, json);
    }

    /// <summary>Require equivalence for the selected960 cap; retain rejected640 outcomes as experimental data.</summary>
    private static void Evaluate(string name, Mat source, AgentWorldEvidence expected, bool benchmark, List<object> results)
    {
        using var originalTemplates = new AgentWorldReadinessTests.TemplateFixture(source.Width, source.Height);
        AgentWorldEvidence Original() => ExistingRecognize(source, originalTemplates.Get);
        AgentWorldEvidence NativeFast() => NativeFastRecognize(source, originalTemplates.Get);
        Assert.Equal(expected, Original());
        Assert.Equal(expected, NativeFast());
        foreach (var (maxWidth, maxHeight) in new[] { (960, 540), (640, 360) })
        {
            var size = ReducedSize(source, maxWidth, maxHeight);
            using var templates = new AgentWorldReadinessTests.TemplateFixture(size.Width, size.Height);
            AgentWorldEvidence Candidate()
            {
                using var resized = new Mat();
                Cv2.Resize(source, resized, size, interpolation: InterpolationFlags.Area);
                return AgentWorldRecognizer.Recognize(resized, templates.Get);
            }
            var actual = Candidate();
            if (maxWidth == AgentWorldRecognizer.MaxWidth) Assert.Equal(expected, actual);
            var previousTimes = new List<double>();
            var nativeFastTimes = new List<double>();
            var reducedTimes = new List<double>();
            if (benchmark)
            {
                for (var i = 0; i < 3; i++) { Original(); NativeFast(); Candidate(); }
                for (var i = 0; i < 12; i++)
                {
                    // Include source downsampling, and alternate execution order under the user's current CPU load.
                    if (i % 2 == 0) { Measure(Original, previousTimes); Measure(NativeFast, nativeFastTimes); Measure(Candidate, reducedTimes); }
                    else { Measure(Candidate, reducedTimes); Measure(NativeFast, nativeFastTimes); Measure(Original, previousTimes); }
                }
            }
            results.Add(new
            {
                name, sourceWidth = source.Width, sourceHeight = source.Height, sourceChannels = source.Channels(),
                maxWidth, maxHeight, width = size.Width, height = size.Height,
                original = expected.ToString(), reduced = actual.ToString(), matches = actual == expected,
                samples = previousTimes.Count,
                previousMedianMs = Median(previousTimes), nativeFastMedianMs = Median(nativeFastTimes), reducedMedianMs = Median(reducedTimes),
                previousMaxMs = previousTimes.Count == 0 ? (double?)null : previousTimes.Max(),
                reducedMaxMs = reducedTimes.Count == 0 ? (double?)null : reducedTimes.Max()
            });
        }
    }

    /// <summary>Retain aspect ratio and avoid upscaling already-small images.</summary>
    private static Size ReducedSize(Mat source, int width, int height)
    {
        var scale = Math.Min(1.0, Math.Min((double)width / source.Width, (double)height / source.Height));
        var size = new Size((int)(source.Width * scale), (int)(source.Height * scale));
        Assert.InRange(size.Width, 1, width);
        Assert.InRange(size.Height, 1, height);
        // Integer truncation may remove less than one source-scaled pixel on each axis.
        Assert.InRange(Math.Abs(size.Width - source.Width * scale), 0, 1);
        Assert.InRange(Math.Abs(size.Height - source.Height * scale), 0, 1);
        return size;
    }

    /// <summary>Run the original full-frame grayscale path with the same shipped assets and thresholds.</summary>
    private static AgentWorldEvidence ExistingRecognize(Mat pixels, Func<string, string, ImageRegion, RecognitionObject> getTemplate)
    {
        using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
        using var hud = region.Find(getTemplate(@"Common\Element", "PaimonMenu", region));
        if (!hud.IsExist()) return AgentWorldEvidence.HudMissing;
        using var modal = region.Find(getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region));
        if (modal.IsExist()) return AgentWorldEvidence.BlockingUi;
        using var confirm = region.Find(getTemplate("AutoFight", "Confirm", region));
        return confirm.IsExist() ? AgentWorldEvidence.BlockingUi : AgentWorldEvidence.WorldHud;
    }

    /// <summary>Isolate the native-resolution ROI optimization from the subsequent source downsampling gain.</summary>
    private static AgentWorldEvidence NativeFastRecognize(Mat pixels, Func<string, string, ImageRegion, RecognitionObject> getTemplate)
    {
        using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
        if (!AgentWorldRecognizer.Matches(region, getTemplate(@"Common\Element", "PaimonMenu", region))) return AgentWorldEvidence.HudMissing;
        if (AgentWorldRecognizer.Matches(region, getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region))) return AgentWorldEvidence.BlockingUi;
        return AgentWorldRecognizer.Matches(region, getTemplate("AutoFight", "Confirm", region))
            ? AgentWorldEvidence.BlockingUi : AgentWorldEvidence.WorldHud;
    }

    /// <summary>Time recognition plus candidate resizing, excluding fixture loading.</summary>
    private static void Measure(Func<AgentWorldEvidence> recognize, List<double> samples)
    {
        var start = Stopwatch.GetTimestamp();
        recognize();
        samples.Add(Stopwatch.GetElapsedTime(start).TotalMilliseconds);
    }

    /// <summary>Return a central value only for repeatedly measured samples.</summary>
    private static double? Median(List<double> values)
    {
        if (values.Count == 0) return null;
        values.Sort();
        return (values[values.Count / 2 - 1] + values[values.Count / 2]) / 2;
    }

    /// <summary>Place each template at an exact configured search boundary, preserving alpha-channel semantics.</summary>
    private static void Paste(Mat pixels, RecognitionObject recognition, bool lastCorner)
    {
        var template = recognition.TemplateImageMat!;
        var roi = recognition.RegionOfInterest;
        var point = lastCorner ? new Point(roi.Right - template.Width, roi.Bottom - template.Height) : roi.TopLeft;
        using var target = new Mat(pixels, new Rect(point.X, point.Y, template.Width, template.Height));
        if (pixels.Channels() == template.Channels()) template.CopyTo(target);
        else Cv2.CvtColor(template, target, ColorConversionCodes.BGR2BGRA);
    }
}
