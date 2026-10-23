using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using System;
using System.Diagnostics;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Reuse Bv.GetMotionStatus's keyboard-hint rule on the already captured native image.</summary>
public static class AgentMotionRecognizer
{
    /// <summary>Preserve native key-tip detail up to the shipped asset reference width.</summary>
    public const int MaxWidth = 1920;
    /// <summary>Normalize larger captures consistently with other native template checks.</summary>
    public const int MaxHeight = 1080;

    /// <summary>Inspect borrowed pixels only after this frame has passed world readiness.</summary>
    public static AgentMotionEvidence Recognize(Mat source, bool worldReady) =>
        Recognize(source, worldReady, static (name, region) => ElementRecognition.Get(name, region));

    /// <summary>Allow CPU fixtures to supply the existing assets without starting the application logger.</summary>
    internal static AgentMotionEvidence Recognize(Mat source, bool worldReady,
        Func<string, ImageRegion, RecognitionObject> getTemplate)
    {
        if (!worldReady) return AgentMotionEvidence.Unavailable("world_not_ready");
        var started = Stopwatch.GetTimestamp();
        try
        {
            if (source.Empty() || source.Type() != MatType.CV_8UC3 && source.Type() != MatType.CV_8UC4)
                return AgentMotionEvidence.Unavailable("invalid_capture", Stopwatch.GetElapsedTime(started).TotalMilliseconds);
            using var normalized = new Mat();
            var scale = Math.Min(1.0, Math.Min((double)MaxWidth / source.Width, (double)MaxHeight / source.Height));
            if (scale < 1)
                Cv2.Resize(source, normalized, new Size((int)(source.Width * scale), (int)(source.Height * scale)),
                    interpolation: InterpolationFlags.Area);
            var pixels = scale < 1 ? normalized : source;
            // Own only a shared Mat header; disposing recognition must not dispose the capture's pixels.
            using var region = new ImageRegion(new Mat(pixels, new Rect(0, 0, pixels.Width, pixels.Height)), 0, 0);
            // The existing boolean matcher crops before grayscale conversion and preserves the asset threshold/ROI.
            var space = AgentWorldRecognizer.Matches(region, getTemplate("SpaceKey", region));
            var x = AgentWorldRecognizer.Matches(region, getTemplate("XKey", region));
            // Exactly the existing Bv.GetMotionStatus rule. No Space match is not evidence of safe ground.
            var status = space ? x ? AgentMotionStatus.Climb : AgentMotionStatus.Fly : AgentMotionStatus.Normal;
            return new AgentMotionEvidence(status, space ? "key_tips_matched" : "space_key_not_found",
                AgentMotionEvidence.MethodName, Stopwatch.GetElapsedTime(started).TotalMilliseconds, space, x);
        }
        catch (Exception)
        {
            // Missing/broken assets are explicit unknown evidence; the separate world input gate remains authoritative.
            return AgentMotionEvidence.Unavailable("recognition_failed", Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        }
    }
}
