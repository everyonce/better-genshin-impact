using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using System;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Language-independent world HUD and modal-template checks with no OCR or extra capture.</summary>
public static class AgentWorldRecognizer
{
    /// <summary>Validated recognition bound; all existing search ROIs and thresholds remain unchanged.</summary>
    public const int MaxWidth = 960;
    /// <summary>Retain aspect ratio inside this height without upscaling smaller captures.</summary>
    public const int MaxHeight = 540;
    /// <summary>Retain canonical native detail when confirming the small modal-star marker.</summary>
    public const int NativeModalMaxWidth = 1920;
    /// <summary>Existing assets use at most this native confirmation height.</summary>
    public const int NativeModalMaxHeight = 1080;
    /// <summary>Allow modest capture/color variation while rejecting shape-only scenery matches.</summary>
    internal const double MaxModalColorRms = 32;
    /// <summary>Unusually dense candidate fields fail closed instead of delaying the capture loop.</summary>
    private const int MaxModalCandidates = 512;

    /// <summary>Inspect borrowed pixels with cached templates and the complete existing search ROIs.</summary>
    public static AgentWorldEvidence Recognize(Mat source) =>
        Recognize(source, static (task, name, region) => RecognitionAssets.Get(task, name, region));

    /// <summary>Allow offline tests to provide templates without bootstrapping the application's asset logger.</summary>
    internal static AgentWorldEvidence Recognize(Mat source, Func<string, string, ImageRegion, RecognitionObject> getTemplate)
    {
        try
        {
            if (source.Empty() || source.Channels() is not (3 or 4)) return AgentWorldEvidence.RecognitionFailed;
            // The offline matrix preserved all 56 outcomes at 960x540; 640x360 lost HUD detection in 12 cases.
            // Scale the complete image and existing cached templates together, retaining the capture's aspect ratio.
            using var normalized = new Mat();
            var scale = Math.Min(1.0, Math.Min((double)MaxWidth / source.Width, (double)MaxHeight / source.Height));
            if (scale < 1)
                Cv2.Resize(source, normalized, new Size((int)(source.Width * scale), (int)(source.Height * scale)),
                    interpolation: InterpolationFlags.Area);
            var pixels = scale < 1 ? normalized : source;
            // ImageRegion owns only this shared header and any fallback grayscale cache, not the caller's Mat.
            using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
            if (!Matches(region, getTemplate(@"Common\Element", "PaimonMenu", region))) return AgentWorldEvidence.HudMissing;
            if (Matches(region, getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region)) &&
                ConfirmNativeModal(source, getTemplate)) return AgentWorldEvidence.BlockingUi;
            return Matches(region, getTemplate("AutoFight", "Confirm", region))
                ? AgentWorldEvidence.BlockingUi : AgentWorldEvidence.WorldHud;
        }
        catch (Exception)
        {
            // A broken/missing asset blocks input while capture and diagnostics remain available.
            return AgentWorldEvidence.RecognitionFailed;
        }
    }

    /// <summary>Confirm a coarse star match against its entire native ROI, never only the coarse maximum position.</summary>
    private static bool ConfirmNativeModal(Mat source, Func<string, string, ImageRegion, RecognitionObject> getTemplate)
    {
        // A 22px marker becomes 11px at the fast scale and can alias ordinary scenery into a false popup.
        // Preserve the existing threshold and full search region at native detail before blocking gameplay.
        using var normalized = new Mat();
        var scale = Math.Min(1.0, Math.Min((double)NativeModalMaxWidth / source.Width, (double)NativeModalMaxHeight / source.Height));
        if (scale < 1)
            Cv2.Resize(source, normalized, new Size((int)(source.Width * scale), (int)(source.Height * scale)),
                interpolation: InterpolationFlags.Area);
        var pixels = scale < 1 ? normalized : source;
        using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
        return MatchesModalAppearance(region, getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region));
    }

    /// <summary>Require co-located shape and color evidence at every native modal-star candidate.</summary>
    internal static bool MatchesModalAppearance(ImageRegion region, RecognitionObject recognition)
    {
        var bounds = recognition.RegionOfInterest;
        // This confirmation is specific to the shipped unmasked star. Changed/broken assets fail closed.
        if (recognition.RecognitionType != RecognitionTypes.TemplateMatch || recognition.Use3Channels ||
            recognition.UseBinaryMatch || recognition.UseMask || recognition.MaskMat is not null ||
            recognition.TemplateMatchMode != TemplateMatchModes.CCoeffNormed ||
            recognition.TemplateImageMat is not { } color || color.Empty() || color.Type() != MatType.CV_8UC3 ||
            recognition.TemplateImageGreyMat is not { } template || template.Empty() || template.Type() != MatType.CV_8UC1 ||
            color.Size() != template.Size() ||
            region.SrcMat.Type() != MatType.CV_8UC3 && region.SrcMat.Type() != MatType.CV_8UC4 ||
            !double.IsFinite(recognition.Threshold) || recognition.Threshold is < 0 or > 1 ||
            bounds.X < 0 || bounds.Y < 0 || bounds.Width <= 0 || bounds.Height <= 0 ||
            bounds.Right > region.SrcMat.Width || bounds.Bottom > region.SrcMat.Height)
            throw new InvalidOperationException("Unsupported modal-star appearance template.");
        if (bounds.Width < template.Width || bounds.Height < template.Height) return false;

        using var pixels = new Mat(region.SrcMat, bounds);
        using var gray = new Mat();
        Cv2.CvtColor(pixels, gray, ColorConversionCodes.BGR2GRAY);
        using var scores = new Mat();
        Cv2.MatchTemplate(gray, template, scores, recognition.TemplateMatchMode);
        // Retain the general matcher's direct-double comparison for a one-element response.
        if (scores.Total() == 1 && !(scores.At<float>(0, 0) >= recognition.Threshold)) return false;
        using var mask = new Mat();
        Cv2.Compare(scores, new Scalar(recognition.Threshold), mask, CmpType.GE);
        var count = Cv2.CountNonZero(mask);
        if (count == 0) return false;
        if (count > MaxModalCandidates) throw new InvalidOperationException("Modal-star candidate limit exceeded.");
        using var candidates = new Mat();
        Cv2.FindNonZero(mask, candidates);
        using var bgr = new Mat();
        if (pixels.Channels() == 4) Cv2.CvtColor(pixels, bgr, ColorConversionCodes.BGRA2BGR);
        var source = pixels.Channels() == 4 ? bgr : pixels;
        var maximumSquaredError = MaxModalColorRms * MaxModalColorRms * color.Total() * color.Channels();
        for (var i = 0; i < count; i++)
        {
            // Grayscale NCC removes color, mean and contrast: stone/foliage can resemble this 22px star.
            // The native r8 false candidates have RGB RMS errors >=42.95; <=32 also accepts tested +/-24 shifts.
            // Check all candidates, so a stronger scenery peak cannot hide a genuine marker elsewhere in the ROI.
            var point = candidates.At<Point>(i, 0);
            using var candidate = new Mat(source, new Rect(point.X, point.Y, color.Width, color.Height));
            if (Cv2.Norm(candidate, color, NormTypes.L2SQR) <= maximumSquaredError) return true;
        }
        return false;
    }

    /// <summary>Only the simple fixed-ROI grayscale configuration uses the boolean-only fast path.</summary>
    internal static bool Matches(ImageRegion region, RecognitionObject recognition)
    {
        var bounds = recognition.RegionOfInterest;
        if (recognition.RecognitionType != RecognitionTypes.TemplateMatch || recognition.Use3Channels
            || recognition.UseBinaryMatch || recognition.UseMask || recognition.MaskMat is not null
            || recognition.DrawOnWindow || recognition.TemplateMatchMode != TemplateMatchModes.CCoeffNormed
            || bounds == default || recognition.TemplateImageGreyMat is not { } template
            || template.Empty() || template.Type() != MatType.CV_8UC1
            || region.SrcMat.Type() != MatType.CV_8UC3 && region.SrcMat.Type() != MatType.CV_8UC4
            || !double.IsFinite(recognition.Threshold) || recognition.Threshold is < 0 or > 1
            || bounds.X < 0 || bounds.Y < 0 || bounds.Width <= 0 || bounds.Height <= 0
            || bounds.Right > region.SrcMat.Width || bounds.Bottom > region.SrcMat.Height)
        {
            // Preserve the existing behavior for masks, color/binary matching, reference search and other modes.
            using var match = region.Find(recognition);
            return match.IsExist();
        }
        if (bounds.Width < template.Width || bounds.Height < template.Height) return false;

        // Crop before conversion: no pixels outside this template's configured search region are processed.
        using var pixels = new Mat(region.SrcMat, bounds);
        using var gray = new Mat();
        Cv2.CvtColor(pixels, gray, ColorConversionCodes.BGR2GRAY);
        using var scores = new Mat();
        Cv2.MatchTemplate(gray, template, scores, recognition.TemplateMatchMode);
        // The general matcher intentionally compares its one-element response directly as a double threshold.
        if (scores.Width == 1 && scores.Height == 1) return scores.At<float>(0, 0) >= recognition.Threshold;
        Cv2.MinMaxLoc(scores, out _, out double maximum);
        // OpenCV compares its float response matrix against a scalar converted to the same float depth.
        // No candidate mask, position extraction or NMS is needed to answer whether any match exists.
        return maximum >= (float)recognition.Threshold;
    }
}
