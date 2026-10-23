using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using System;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Language-independent world HUD and modal-template checks with no OCR or extra capture.</summary>
public static class AgentWorldRecognizer
{
    /// <summary>Inspect a borrowed frame; reuse one grayscale conversion and the existing template ROIs.</summary>
    public static AgentWorldEvidence Recognize(Mat source) =>
        Recognize(source, static (task, name, region) => RecognitionAssets.Get(task, name, region));

    /// <summary>Allow offline tests to provide templates without bootstrapping the application's asset logger.</summary>
    internal static AgentWorldEvidence Recognize(Mat source, Func<string, string, ImageRegion, RecognitionObject> getTemplate)
    {
        try
        {
            if (source.Empty() || source.Channels() is not (3 or 4)) return AgentWorldEvidence.RecognitionFailed;
            // Existing asset templates use at most 1080p; retain the capture's aspect ratio.
            using var normalized = new Mat();
            var scale = Math.Min(1.0, Math.Min(1920.0 / source.Width, 1080.0 / source.Height));
            if (scale < 1)
                Cv2.Resize(source, normalized, new Size((int)(source.Width * scale), (int)(source.Height * scale)),
                    interpolation: InterpolationFlags.Area);
            var pixels = scale < 1 ? normalized : source;
            // ImageRegion owns only this shared header and its grayscale cache, not the caller's Mat.
            using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
            using var hud = region.Find(getTemplate(@"Common\Element", "PaimonMenu", region));
            if (!hud.IsExist()) return AgentWorldEvidence.HudMissing;
            using var modal = region.Find(getTemplate(@"Common\Element", "PromptDialogLeftBottomStar", region));
            if (modal.IsExist()) return AgentWorldEvidence.BlockingUi;
            using var confirm = region.Find(getTemplate("AutoFight", "Confirm", region));
            return confirm.IsExist() ? AgentWorldEvidence.BlockingUi : AgentWorldEvidence.WorldHud;
        }
        catch (Exception)
        {
            // A broken/missing asset blocks input while capture and diagnostics remain available.
            return AgentWorldEvidence.RecognitionFailed;
        }
    }
}
