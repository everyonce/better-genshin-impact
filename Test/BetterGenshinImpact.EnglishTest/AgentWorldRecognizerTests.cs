using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Compare the ROI boolean path with the existing matcher, using only offline CPU images.</summary>
public sealed class AgentWorldRecognizerTests(ITestOutputHelper output)
{
    /// <summary>Every configured ROI pixel remains searchable, including both corners; outside pixels remain excluded.</summary>
    [Theory]
    [InlineData(3, "first", true)]
    [InlineData(3, "last", true)]
    [InlineData(3, "outside", false)]
    [InlineData(4, "first", true)]
    [InlineData(4, "last", true)]
    [InlineData(4, "outside", false)]
    public void FullRoiAndChannelSemanticsMatchExistingSearch(int channels, string placement, bool expected)
    {
        using var pixels = Noise(128, 96, channels, 123);
        using var template = Noise(9, 7, 3, 456);
        var recognition = RecognitionObject.TemplateMatch(template);
        using var grayTemplate = recognition.TemplateImageGreyMat!;
        recognition.RegionOfInterest = new Rect(8, 9, 90, 65);
        var roi = recognition.RegionOfInterest;
        var location = placement switch
        {
            "first" => roi.TopLeft,
            "last" => new Point(roi.Right - template.Width, roi.Bottom - template.Height),
            _ => new Point(0, 0)
        };
        Paste(pixels, template, location);
        Assert.Equal(expected, ExistingMatch(pixels, recognition));
        Assert.Equal(expected, FastMatch(pixels, recognition));
    }

    /// <summary>Float response/scalar boundaries and the special one-element response preserve existing comparisons.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ScoreBoundariesMatchExistingSearch(bool singleResponse)
    {
        using var pixels = Noise(128, 96, 3, 123);
        using var template = Noise(9, 7, 3, 456);
        var recognition = RecognitionObject.TemplateMatch(template);
        using var grayTemplate = recognition.TemplateImageGreyMat!;
        recognition.RegionOfInterest = new Rect(8, 9, singleResponse ? template.Width : 90, singleResponse ? template.Height : 65);
        using (var target = new Mat(pixels, new Rect(8, 9, template.Width, template.Height)))
            Cv2.AddWeighted(template, 0.8, target, 0.2, 0, target);
        using var gray = new Mat();
        Cv2.CvtColor(pixels, gray, ColorConversionCodes.BGR2GRAY);
        using var search = new Mat(gray, recognition.RegionOfInterest);
        using var scores = new Mat();
        Cv2.MatchTemplate(search, grayTemplate, scores, TemplateMatchModes.CCoeffNormed);
        Cv2.MinMaxLoc(scores, out _, out double maximum);
        double[] thresholds = [0.8, maximum, Math.BitIncrement(maximum), Math.BitDecrement(maximum),
            MathF.BitIncrement((float)maximum), MathF.BitDecrement((float)maximum)];
        foreach (var threshold in thresholds)
        {
            recognition.Threshold = threshold;
            Assert.Equal(ExistingMatch(pixels, recognition), FastMatch(pixels, recognition));
        }
    }

    /// <summary>Configurations outside the simple grayscale mode retain the general matcher without reinterpretation.</summary>
    [Theory]
    [InlineData("mask")]
    [InlineData("color")]
    [InlineData("binary")]
    [InlineData("mode")]
    [InlineData("full")]
    public void OtherTemplateConfigurationsKeepExistingBehavior(string configuration)
    {
        using var pixels = Noise(128, 96, 3, 123);
        using var template = Noise(9, 7, 3, 456);
        using var mask = new Mat(template.Rows, template.Cols, MatType.CV_8UC1, Scalar.All(255));
        var recognition = RecognitionObject.TemplateMatch(template);
        using var grayTemplate = recognition.TemplateImageGreyMat!;
        recognition.RegionOfInterest = new Rect(8, 9, 90, 65);
        Paste(pixels, template, new Point(8, 9));
        switch (configuration)
        {
            case "mask": recognition.UseMask = true; recognition.MaskMat = mask; break;
            case "color": recognition.Use3Channels = true; break;
            case "binary": recognition.UseBinaryMatch = true; break;
            case "mode": recognition.TemplateMatchMode = TemplateMatchModes.SqDiffNormed; break;
            case "full": recognition.RegionOfInterest = default; break;
        }
        Assert.Equal(ExistingMatch(pixels, recognition), FastMatch(pixels, recognition));
    }

    /// <summary>Report warmed paired CPU timings and evidence equivalence; absolute timing is not a test assertion.</summary>
    [Fact]
    public void WarmedOfflineFramesMatchAndReportCpuCost()
    {
        var samples = new List<(string Name, Mat Pixels)>();
        try
        {
            using (var templates = new AgentWorldReadinessTests.TemplateFixture(1920, 1080))
            {
                var world = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
                Paste(world, templates.Hud.TemplateImageMat!, templates.Hud.RegionOfInterest.TopLeft + new Point(8, 8));
                samples.Add(("synthetic-world", world));
                var modal = world.Clone();
                Paste(modal, templates.Modal.TemplateImageMat!, templates.Modal.RegionOfInterest.TopLeft + new Point(8, 8));
                samples.Add(("synthetic-modal", modal));
                samples.Add(("synthetic-blank", new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black)));
            }
            // Optional local recordings are supplied by the coordinated benchmark invocation, never captured here.
            var recordings = Environment.GetEnvironmentVariable("BETTERGI_RECOGNITION_BENCHMARK_IMAGES");
            foreach (var path in (recordings ?? string.Empty).Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            {
                var pixels = Cv2.ImRead(path);
                Assert.False(pixels.Empty(), $"Could not load offline recording: {path}");
                samples.Add((path, pixels));
            }
            var results = new List<object>();
            foreach (var (name, pixels) in samples)
            {
                using var templates = new AgentWorldReadinessTests.TemplateFixture(pixels.Width, pixels.Height);
                AgentWorldEvidence Old() => ExistingRecognize(pixels, templates.Get);
                AgentWorldEvidence New() => AgentWorldRecognizer.Recognize(pixels, templates.Get);
                for (var i = 0; i < 3; i++) Assert.Equal(Old(), New());
                var previousTimes = new List<double>();
                var optimizedTimes = new List<double>();
                var expected = Old();
                for (var i = 0; i < 12; i++)
                {
                    // Alternate order so background load and warm caches do not consistently favor one path.
                    if (i % 2 == 0)
                    {
                        Assert.Equal(expected, Measure(Old, previousTimes));
                        Assert.Equal(expected, Measure(New, optimizedTimes));
                    }
                    else
                    {
                        Assert.Equal(expected, Measure(New, optimizedTimes));
                        Assert.Equal(expected, Measure(Old, previousTimes));
                    }
                }
                previousTimes.Sort();
                optimizedTimes.Sort();
                results.Add(new { name, width = pixels.Width, height = pixels.Height, evidence = expected.ToString(),
                    samples = previousTimes.Count, previousMedianMs = Median(previousTimes), optimizedMedianMs = Median(optimizedTimes),
                    previousMaxMs = previousTimes[^1], optimizedMaxMs = optimizedTimes[^1] });
            }
            var json = JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true });
            output.WriteLine(json);
            if (Environment.GetEnvironmentVariable("BETTERGI_RECOGNITION_BENCHMARK_OUTPUT") is { Length: > 0 } destination)
                File.WriteAllText(destination, json);
        }
        finally { foreach (var sample in samples) sample.Pixels.Dispose(); }
    }

    /// <summary>Preserve the previous full-frame grayscale/general-search path as the offline comparison.</summary>
    private static AgentWorldEvidence ExistingRecognize(Mat pixels,
        Func<string, string, ImageRegion, RecognitionObject> getTemplate)
    {
        using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
        using var hud = region.Find(getTemplate(@"Common\Element", "PaimonMenu", region));
        if (!hud.IsExist()) return AgentWorldEvidence.HudMissing;
        using var modal = region.Find(getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region));
        if (modal.IsExist()) return AgentWorldEvidence.BlockingUi;
        using var confirm = region.Find(getTemplate("AutoFight", "Confirm", region));
        return confirm.IsExist() ? AgentWorldEvidence.BlockingUi : AgentWorldEvidence.WorldHud;
    }

    /// <summary>Measure only CPU recognition, excluding fixture creation and image decoding.</summary>
    private static AgentWorldEvidence Measure(Func<AgentWorldEvidence> recognize, List<double> timings)
    {
        var started = Stopwatch.GetTimestamp();
        var evidence = recognize();
        timings.Add(Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        return evidence;
    }

    /// <summary>Interpolate the two central samples in the paired even-sized timing series.</summary>
    private static double Median(List<double> sorted) => (sorted[sorted.Count / 2 - 1] + sorted[sorted.Count / 2]) / 2;

    /// <summary>Invoke the new path with a borrowed Mat header.</summary>
    private static bool FastMatch(Mat pixels, RecognitionObject recognition)
    {
        using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
        return AgentWorldRecognizer.Matches(region, recognition);
    }

    /// <summary>Invoke the original public search path against exactly the same pixels and configuration.</summary>
    private static bool ExistingMatch(Mat pixels, RecognitionObject recognition)
    {
        using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
        using var match = region.Find(recognition);
        return match.IsExist();
    }

    /// <summary>Make deterministic bounded CPU fixtures without the global OpenCV random state.</summary>
    private static Mat Noise(int width, int height, int channels, int seed)
    {
        var result = new Mat(height, width, channels == 4 ? MatType.CV_8UC4 : MatType.CV_8UC3);
        var bytes = new byte[width * height * channels];
        new Random(seed).NextBytes(bytes);
        Marshal.Copy(bytes, 0, result.Data, bytes.Length);
        return result;
    }

    /// <summary>Place exact template pixels, adding only alpha when the source fixture uses four channels.</summary>
    private static void Paste(Mat pixels, Mat template, Point location)
    {
        using var target = new Mat(pixels, new Rect(location.X, location.Y, template.Width, template.Height));
        if (pixels.Channels() == template.Channels()) template.CopyTo(target);
        else Cv2.CvtColor(template, target, ColorConversionCodes.BGR2BGRA);
    }
}
