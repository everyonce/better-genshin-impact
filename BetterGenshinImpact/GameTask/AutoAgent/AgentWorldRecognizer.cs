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
            if (Matches(region, getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region))) return AgentWorldEvidence.BlockingUi;
            return Matches(region, getTemplate("AutoFight", "Confirm", region))
                ? AgentWorldEvidence.BlockingUi : AgentWorldEvidence.WorldHud;
        }
        catch (Exception)
        {
            // A broken/missing asset blocks input while capture and diagnostics remain available.
            return AgentWorldEvidence.RecognitionFailed;
        }
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
