using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Recognition.OCR;
using BetterGenshinImpact.GameTask.AutoArtifactSalvage;
using BetterGenshinImpact.Helpers;
using Microsoft.Extensions.Localization;
using Microsoft.Extensions.Logging.Abstractions;
using OpenCvSharp;
using System.Globalization;

namespace BetterGenshinImpact.UnitTest.GameTaskTests.AutoArtifactSalvageTests;

/// <summary>Exercise localized artifact parsing with scripted OCR and synthetic pixels, without game access.</summary>
public sealed class AutoArtifactSalvageMarkerTests : IClassFixture<LocalizationFixture>
{
    /// <summary>Use the production satellite resources for each requested game language.</summary>
    private readonly IStringLocalizer<AutoArtifactSalvageTask> _localizer;

    /// <summary>Create only a resource localizer; no OCR model or application host is initialized.</summary>
    public AutoArtifactSalvageMarkerTests(LocalizationFixture localization)
    {
        _localizer = localization.CreateStringLocalizer<AutoArtifactSalvageTask>();
    }

    /// <summary>Explicit text must identify an inactive early substat without requiring three preceding stats.</summary>
    [Theory]
    [InlineData("en", "unactivated", true)]
    [InlineData("en", "Unactivated", true)]
    [InlineData("en", "UNACTIVATED", true)]
    [InlineData("en", "", false)]
    [InlineData("en", "activated", false)]
    [InlineData("fr", "À activer", true)]
    [InlineData("fr", "À ACTIVER", true)]
    [InlineData("zh-Hans", "待激活", true)]
    public void ExplicitMarkerParsesEarlySubstat(string cultureName, string marker, bool expected)
    {
        ArtifactStat result = Recognize(cultureName, marker);
        Assert.Equal(3, result.MinorAffixes.Length);
        Assert.Equal(ArtifactAffixType.ATK, result.MinorAffixes[0].Type);
        Assert.Equal(19f, result.MinorAffixes[0].Value);
        Assert.Equal(expected, result.MinorAffixes[0].IsUnactivated);
        Assert.All(result.MinorAffixes.Skip(1), affix => Assert.False(affix.IsUnactivated));
        Assert.Equal(0, result.Level);
    }

    /// <summary>Without an OCR marker, the fourth substat still uses the existing grayscale evidence.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void MissingMarkerRetainsFourthSubstatImageFallback(bool inactivePixels)
    {
        ArtifactStat result = Recognize("en", "", includeFourth: true, inactivePixels: inactivePixels);
        Assert.Equal(4, result.MinorAffixes.Length);
        Assert.Equal(ArtifactAffixType.CRITRate, result.MinorAffixes[3].Type);
        Assert.Equal(3.1f, result.MinorAffixes[3].Value);
        Assert.Equal(inactivePixels, result.MinorAffixes[3].IsUnactivated);
        Assert.All(result.MinorAffixes.Take(3), affix => Assert.False(affix.IsUnactivated));
    }

    /// <summary>Run the public recognition path against four scripted OCR regions and an in-memory card.</summary>
    private ArtifactStat Recognize(string cultureName, string marker, bool includeFourth = false, bool inactivePixels = false)
    {
        var culture = CultureInfo.GetCultureInfo(cultureName);
        // Resolve each stat label through the requested game-language resources.
        string Label(ArtifactAffixType type) => _localizer.WithCultureGet(culture, ArtifactAffix.DefaultStrDic[type]);
        string suffix = marker.Length == 0 ? "" : $" ({marker})";
        var lines = new List<string> { "+0", $"{Label(ArtifactAffixType.ATK)}+19{suffix}",
            $"{Label(ArtifactAffixType.DEF)}+16", $"{Label(ArtifactAffixType.ElementalMastery)}+23" };
        if (includeFourth)
            lines.Add($"{Label(ArtifactAffixType.CRITRate)}+{3.1f.ToString(culture)}%");
        OcrResult minorResult = Result(lines.ToArray());
        var ocr = new ScriptedOcr(Result("Saved OCR fixture"), Result("Fixture type"),
            Result(Label(ArtifactAffixType.ElementalMastery), "47"), minorResult);
        using var source = new Mat(600, 400, MatType.CV_8UC3, Scalar.All(255));

        // Reproduce the two grayscale peaks used by the existing fallback; all other pixels remain white.
        if (inactivePixels)
        {
            Rect line = minorResult.Regions[^1].Rect.BoundingRect();
            line.Y += (int)(source.Height * 0.52);
            using Mat background = source.SubMat(line);
            background.SetTo(Scalar.All(222));
            using Mat foreground = background.SubMat(new Rect(2, 2, 20, 4));
            foreground.SetTo(Scalar.All(152));
        }

        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new Vanara.PInvoke.RECT(0, 0, 1920, 1080), 1),
            new DisabledInputBackend());
        var task = new AutoArtifactSalvageTask(runtime, NullLogger<AutoArtifactSalvageTask>.Instance);
        var parameters = new AutoArtifactSalvageTaskParam(4, null, null, null, null, culture, _localizer);
        ArtifactStat parsed = task.GetArtifactStat(source, ocr, parameters, out _);
        Assert.Equal(0, ocr.Remaining);
        return parsed;
    }

    /// <summary>Keep OCR rectangles inside the artifact's left-aligned stat area and in reading order.</summary>
    private static OcrResult Result(params string[] lines) => new(lines.Select((text, index) =>
        new OcrResultRegion(new RotatedRect(new Point2f(51, 25 + index * 30), new Size2f(100, 10), 0), text, 1f)).ToArray());

    /// <summary>Return only saved test text and fail if recognition uses a different OCR entry point.</summary>
    private sealed class ScriptedOcr(params OcrResult[] results) : IOcrService
    {
        /// <summary>Expected ROI responses in production call order.</summary>
        private readonly Queue<OcrResult> _results = new(results);
        /// <summary>Remaining expected recognition calls.</summary>
        public int Remaining => _results.Count;
        /// <summary>Return the next scripted region set without examining an application or model.</summary>
        public OcrResult OcrResult(Mat mat) => _results.Dequeue();
        /// <summary>Reject unplanned recognition paths.</summary>
        public string Ocr(Mat mat) => throw new InvalidOperationException("Unexpected OCR entry point.");
        /// <summary>Reject unplanned recognition paths.</summary>
        public string OcrWithoutDetector(Mat mat) => throw new InvalidOperationException("Unexpected OCR entry point.");
    }

    /// <summary>Make keyboard and mouse access impossible throughout this parsing test.</summary>
    private sealed class DisabledInputBackend : IInputBackend
    {
        /// <summary>Retain the fake runtime's declared backend category without constructing Win32 channels.</summary>
        public InputBackendKind Kind => InputBackendKind.Win32;
        /// <summary>Fail before any foreground input could be emitted.</summary>
        public IInputChannel Foreground => throw new InvalidOperationException("Input is forbidden in recognition tests.");
        /// <summary>Fail before any background input could be emitted.</summary>
        public IInputChannel Background => throw new InvalidOperationException("Input is forbidden in recognition tests.");
        /// <summary>No keys are owned by this backend.</summary>
        public void ReleaseAll() { }
        /// <summary>No native resource was acquired.</summary>
        public void Dispose() { }
    }
}
