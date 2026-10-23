using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU-only star appearance regressions and optional replay of reviewed private native captures.</summary>
public sealed class AgentModalAppearanceTests(ITestOutputHelper output)
{
    /// <summary>Cover native/small captures, both channel layouts, ROI corners and modest photometric changes.</summary>
    public static IEnumerable<object[]> MarkerCases()
    {
        foreach (var width in new[] { 1920, 960 })
        foreach (var channels in new[] { 3, 4 })
        foreach (var last in new[] { false, true })
        foreach (var variation in new[] { "exact", "darker", "brighter", "contrast", "color" })
            yield return [width, channels, last, variation];
    }

    /// <summary>Shipped markers remain blocking despite modest tested brightness, contrast or channel variation.</summary>
    [Theory]
    [MemberData(nameof(MarkerCases))]
    public void ModestMarkerVariationsRemainBlocking(int width, int channels, bool last, string variation)
    {
        var height = width * 9 / 16;
        using var templates = new AgentWorldReadinessTests.TemplateFixture(width, height);
        using var pixels = new Mat(height, width, channels == 4 ? MatType.CV_8UC4 : MatType.CV_8UC3, Scalar.Black);
        Paste(pixels, templates.Hud, templates.Hud.TemplateImageMat!, false);
        using var marker = Vary(templates.Modal.TemplateImageMat!, variation);
        Paste(pixels, templates.Modal, marker, last);
        Assert.Equal(AgentWorldEvidence.BlockingUi, AgentWorldRecognizer.Recognize(pixels, templates.Get));
        Assert.False(pixels.IsDisposed);
    }

    /// <summary>A shape match without the marker's contrast must not stop ordinary gameplay.</summary>
    [Theory]
    [InlineData(3)]
    [InlineData(4)]
    public void ShapeOnlyLookalikeIsRejected(int channels)
    {
        using var templates = new AgentWorldReadinessTests.TemplateFixture(1920, 1080);
        using var pixels = new Mat(1080, 1920, channels == 4 ? MatType.CV_8UC4 : MatType.CV_8UC3, Scalar.Black);
        Paste(pixels, templates.Hud, templates.Hud.TemplateImageMat!, false);
        using var lookalike = Vary(templates.Modal.TemplateImageMat!, "low-contrast");
        Paste(pixels, templates.Modal, lookalike, false);
        using var region = Borrow(pixels);
        Assert.True(AgentWorldRecognizer.Matches(region, templates.Modal));
        Assert.False(AgentWorldRecognizer.MatchesModalAppearance(region, templates.Modal));
        Assert.Equal(AgentWorldEvidence.WorldHud, AgentWorldRecognizer.Recognize(pixels, templates.Get));
    }

    /// <summary>A stronger false shape cannot mask a genuine, slightly noisy marker elsewhere in the full ROI.</summary>
    [Fact]
    public void StrongerFalseCandidateDoesNotHideRealMarker()
    {
        using var templates = new AgentWorldReadinessTests.TemplateFixture(1920, 1080);
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
        Paste(pixels, templates.Hud, templates.Hud.TemplateImageMat!, false);
        using var lookalike = Vary(templates.Modal.TemplateImageMat!, "low-contrast");
        using var marker = Vary(templates.Modal.TemplateImageMat!, "noise");
        Assert.True(ShapeScore(lookalike, templates.Modal) > ShapeScore(marker, templates.Modal));
        Assert.True(ShapeScore(marker, templates.Modal) >= templates.Modal.Threshold);
        Paste(pixels, templates.Modal, lookalike, false);
        Paste(pixels, templates.Modal, marker, true);
        using var region = Borrow(pixels);
        Assert.True(AgentWorldRecognizer.MatchesModalAppearance(region, templates.Modal));
        Assert.Equal(AgentWorldEvidence.BlockingUi, AgentWorldRecognizer.Recognize(pixels, templates.Get));
    }

    /// <summary>An implausibly dense template field remains blocked and has bounded candidate processing.</summary>
    [Fact]
    public void ExcessCandidatesFailClosed()
    {
        using var templates = new AgentWorldReadinessTests.TemplateFixture(1920, 1080);
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
        Paste(pixels, templates.Hud, templates.Hud.TemplateImageMat!, false);
        var marker = templates.Modal.TemplateImageMat!;
        var bounds = templates.Modal.RegionOfInterest;
        for (var y = bounds.Y; y <= bounds.Bottom - marker.Height; y += marker.Height)
        for (var x = bounds.X; x <= bounds.Right - marker.Width; x += marker.Width)
        {
            using var destination = new Mat(pixels, new Rect(x, y, marker.Width, marker.Height));
            marker.CopyTo(destination);
        }
        Assert.Equal(AgentWorldEvidence.RecognitionFailed, AgentWorldRecognizer.Recognize(pixels, templates.Get));
    }

    /// <summary>Optional real world/journal replays stay distinct from synthetic translated or overlaid test cases.</summary>
    [Fact]
    public void ReplayReviewedNativeCapturesAndRecordEvidence()
    {
        var results = new List<object>();
        foreach (var path in Paths("BETTERGI_MODAL_WORLD_IMAGES"))
        {
            using var captured = Cv2.ImRead(path);
            Assert.False(captured.Empty(), path);
            using var templates = new AgentWorldReadinessTests.TemplateFixture(captured.Width, captured.Height);
            var digest = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
            foreach (var phase in new[] { new Point(0, 0), new Point(1, 0), new Point(0, 1), new Point(1, 1) })
            {
                using var pixels = new Mat(captured.Rows, captured.Cols, captured.Type(), Scalar.Black);
                using (var from = new Mat(captured, new Rect(0, 0, captured.Width - phase.X, captured.Height - phase.Y)))
                using (var to = new Mat(pixels, new Rect(phase.X, phase.Y, from.Width, from.Height))) from.CopyTo(to);
                var actual = AgentWorldRecognizer.Recognize(pixels, templates.Get);
                Assert.True(actual == AgentWorldEvidence.WorldHud, $"{path} phase {phase}: {actual}");
                var times = new List<double>();
                if (phase == default)
                {
                    // Warm caches before timing; these are offline CPU measurements, never a live result.
                    for (var i = 0; i < 2; i++) AgentWorldRecognizer.Recognize(pixels, templates.Get);
                    for (var i = 0; i < 7; i++)
                    {
                        var started = Stopwatch.GetTimestamp();
                        Assert.Equal(AgentWorldEvidence.WorldHud, AgentWorldRecognizer.Recognize(pixels, templates.Get));
                        times.Add(Stopwatch.GetElapsedTime(started).TotalMilliseconds);
                    }
                    times.Sort();
                }
                results.Add(new { path, sha256 = digest, caseKind = phase == default ? "captured-world" : "synthetic-translation",
                    phaseX = phase.X, phaseY = phase.Y, evidence = actual.ToString(), timingSamples = times.Count,
                    offlineMedianMs = times.Count == 0 ? (double?)null : times[times.Count / 2] });
            }
            foreach (var last in new[] { false, true })
            foreach (var variation in new[] { "exact", "darker", "brighter", "color" })
            {
                using var pixels = captured.Clone();
                using var marker = Vary(templates.Modal.TemplateImageMat!, variation);
                Paste(pixels, templates.Modal, marker, last);
                Assert.Equal(AgentWorldEvidence.BlockingUi, AgentWorldRecognizer.Recognize(pixels, templates.Get));
                results.Add(new { path, sha256 = digest, caseKind = "synthetic-modal-overlay", last, variation,
                    evidence = AgentWorldEvidence.BlockingUi.ToString() });
            }
            // The independent confirm-button and absent-HUD guards are intentionally unchanged.
            using var confirm = captured.Clone();
            Paste(confirm, templates.Confirm, templates.Confirm.TemplateImageMat!, true);
            Assert.Equal(AgentWorldEvidence.BlockingUi, AgentWorldRecognizer.Recognize(confirm, templates.Get));
            using var missingHud = captured.Clone();
            using (var hud = new Mat(missingHud, templates.Hud.RegionOfInterest)) hud.SetTo(Scalar.Black);
            Assert.Equal(AgentWorldEvidence.HudMissing, AgentWorldRecognizer.Recognize(missingHud, templates.Get));
        }
        foreach (var path in Paths("BETTERGI_MODAL_BLOCKED_IMAGES"))
        {
            using var pixels = Cv2.ImRead(path);
            Assert.False(pixels.Empty(), path);
            using var templates = new AgentWorldReadinessTests.TemplateFixture(pixels.Width, pixels.Height);
            var actual = AgentWorldRecognizer.Recognize(pixels, templates.Get);
            Assert.True(actual is AgentWorldEvidence.HudMissing or AgentWorldEvidence.BlockingUi, $"{path}: {actual}");
            results.Add(new { path, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant(),
                caseKind = "captured-blocked", evidence = actual.ToString() });
        }
        var json = JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true });
        output.WriteLine(json);
        if (Environment.GetEnvironmentVariable("BETTERGI_MODAL_REPORT") is { Length: > 0 } destination)
            File.WriteAllText(destination, json);
    }

    /// <summary>Read only explicitly supplied private image paths; no captures or images are generated here.</summary>
    private static IEnumerable<string> Paths(string variable) =>
        (Environment.GetEnvironmentVariable(variable) ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries);

    /// <summary>Borrow the source header without disposing the caller's pixels.</summary>
    private static ImageRegion Borrow(Mat pixels) => new(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);

    /// <summary>Measure the existing grayscale criterion on one candidate independently of its color error.</summary>
    private static double ShapeScore(Mat pixels, RecognitionObject recognition)
    {
        using var gray = new Mat();
        Cv2.CvtColor(pixels, gray, ColorConversionCodes.BGR2GRAY);
        using var response = new Mat();
        Cv2.MatchTemplate(gray, recognition.TemplateImageGreyMat!, response, TemplateMatchModes.CCoeffNormed);
        return response.At<float>(0, 0);
    }

    /// <summary>Explicit synthetic perturbations test bounded appearance tolerance, not unobserved live modal behavior.</summary>
    private static Mat Vary(Mat template, string variation)
    {
        var marker = template.Clone();
        switch (variation)
        {
            case "darker": template.ConvertTo(marker, template.Type(), 1, -24); break;
            case "brighter": template.ConvertTo(marker, template.Type(), 1, 24); break;
            case "contrast": template.ConvertTo(marker, template.Type(), 0.85, 12); break;
            case "low-contrast": template.ConvertTo(marker, template.Type(), 0.25, 112); break;
            case "color": Cv2.Add(marker, new Scalar(12, -10, 8), marker); break;
            case "noise":
                var random = new Random(42);
                for (var y = 0; y < marker.Rows; y++)
                for (var x = 0; x < marker.Cols; x++)
                {
                    var pixel = marker.At<Vec3b>(y, x);
                    for (var c = 0; c < 3; c++) pixel[c] = (byte)Math.Clamp(pixel[c] + random.Next(-18, 19), 0, 255);
                    marker.Set(y, x, pixel);
                }
                break;
        }
        return marker;
    }

    /// <summary>Place the same RGB content at either exact ROI corner; alpha is irrelevant to recognition.</summary>
    private static void Paste(Mat pixels, RecognitionObject recognition, Mat marker, bool last)
    {
        var roi = recognition.RegionOfInterest;
        var point = last ? new Point(roi.Right - marker.Width, roi.Bottom - marker.Height) : roi.TopLeft;
        using var destination = new Mat(pixels, new Rect(point.X, point.Y, marker.Width, marker.Height));
        if (pixels.Channels() == marker.Channels()) marker.CopyTo(destination);
        else Cv2.CvtColor(marker, destination, ColorConversionCodes.BGR2BGRA);
    }
}
