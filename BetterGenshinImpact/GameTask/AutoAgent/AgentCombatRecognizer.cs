using BetterGenshinImpact.Core.Agent;
using OpenCvSharp;
using System;
using System.Collections.Generic;
using System.Diagnostics;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Bounded color analysis on borrowed native pixels, without captures, OCR, waits, or input.</summary>
public static class AgentCombatRecognizer
{
    /// <summary>Limit clutter processing and avoid treating a red scene as many targets.</summary>
    private const int MaximumRedPixels = 16384;
    /// <summary>Reject an ambiguous component set before walking its statistics.</summary>
    private const int MaximumComponents = 256;
    /// <summary>Bound the number of published candidates in each frame.</summary>
    private const int MaximumCandidates = 16;

    /// <summary>Explicit, opt-in contract; neither the colors nor the candidates grant control authority.</summary>
    public static object Capability => new
    {
        version = 1, method = AgentCombatEvidence.MethodName, sameFrame = true, readOnly = true,
        requiresWgcSourceIdentity = true, minWidth = 1280, maxWidth = 1920, maxHeight = 1080,
        aspectRatio = "16:9", referenceWidth = 1920, referenceHeight = 1080,
        healthRow = new { x = 808, y = 1010, width = 304 },
        enemyRegion = new { x = 200, y = 100, width = 1400, height = 800 },
        maximumCandidates = MaximumCandidates, healthFractionIsEstimate = true,
        authorizesInput = false, enemyIdentityVerified = false, killVerified = false
    };

    /// <summary>Analyze only a ready, source-bound image; every failure clears all current candidates.</summary>
    public static AgentCombatEvidence Recognize(Mat source, AgentObservation observation, bool worldReady)
    {
        if (!worldReady) return AgentCombatEvidence.Unavailable(observation, "world_not_ready");
        if (observation.FrameId <= 0 || observation.SourceFrame is null)
            return AgentCombatEvidence.Unavailable(observation, "source_identity_unavailable");
        var started = Stopwatch.GetTimestamp();
        AgentCombatEvidence Missing(string reason) => AgentCombatEvidence.Unavailable(observation, reason,
            Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        try
        {
            if (source.Empty() || source.Type() != MatType.CV_8UC3 && source.Type() != MatType.CV_8UC4)
                return Missing("invalid_capture");
            if (source.Width != observation.SourceWidth || source.Height != observation.SourceHeight)
                return Missing("source_geometry_mismatch");
            if (source.Width < 1280 || source.Width > 1920 || source.Height > 1080
                || Math.Abs((double)source.Width / source.Height - 16.0 / 9) > .002)
                return Missing("unsupported_geometry");
            var scale = source.Width / 1920.0;
            var health = ReadHealth(source, scale);
            // Match BetterGI's native red health-bar color without using its global tracker or a second capture.
            var region = new Rect((int)Math.Round(200 * scale), (int)Math.Round(100 * scale),
                (int)Math.Round(1400 * scale), (int)Math.Round(800 * scale));
            using var crop = new Mat(source, region);
            using var mask = new Mat();
            Cv2.InRange(crop, new Scalar(82, 82, 247, 0), new Scalar(98, 98, 255, 255), mask);
            var candidates = new List<AgentEnemyBarCandidate>();
            var redPixels = Cv2.CountNonZero(mask);
            var overloaded = redPixels > MaximumRedPixels;
            if (!overloaded && redPixels > 0)
            {
                // Restrict component labeling to actual red pixels; one small bar need not label a full native ROI.
                var activeArea = Cv2.BoundingRect(mask);
                using var activeMask = new Mat(mask, activeArea);
                using var labels = new Mat();
                using var stats = new Mat();
                using var centroids = new Mat();
                var count = Cv2.ConnectedComponentsWithStats(activeMask, labels, stats, centroids, PixelConnectivity.Connectivity4);
                overloaded = count - 1 > MaximumComponents;
                // A broad component budget bounds work even on a cluttered frame.
                for (var index = 1; !overloaded && index < count; index++)
                {
                    var width = stats.At<int>(index, (int)ConnectedComponentsTypes.Width);
                    var height = stats.At<int>(index, (int)ConnectedComponentsTypes.Height);
                    var pixels = stats.At<int>(index, (int)ConnectedComponentsTypes.Area);
                    if (width < 24 * scale || width > 320 * scale || height < Math.Max(1, 2 * scale)
                        || height > 14 * scale || width < height * 5 || pixels < width * height * .7) continue;
                    candidates.Add(new AgentEnemyBarCandidate(
                        region.X + activeArea.X + stats.At<int>(index, (int)ConnectedComponentsTypes.Left),
                        region.Y + activeArea.Y + stats.At<int>(index, (int)ConnectedComponentsTypes.Top), width, height, pixels));
                    overloaded = candidates.Count > MaximumCandidates;
                }
            }
            // Ambiguous red evidence may retain health information, but never a partial target set.
            if (overloaded) candidates.Clear();
            return new AgentCombatEvidence("valid", overloaded ? "red_mask_overloaded" : "native_colors_analyzed",
                observation.FrameId, observation.SourceFrame, source.Width, source.Height, health.Color,
                health.Fraction, health.Pixels, candidates.AsReadOnly(), overloaded,
                Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        }
        catch (Exception error) when (error is OpenCVException or ArgumentException or InvalidOperationException)
        {
            return Missing("recognition_failed");
        }
    }

    /// <summary>Estimate fill from the known native HUD row, tolerating text holes but requiring its left prefix.</summary>
    private static (string Color, double? Fraction, int Pixels) ReadHealth(Mat source, double scale)
    {
        var left = (int)Math.Round(808 * scale);
        var right = (int)Math.Round(1112 * scale);
        var row = (int)Math.Round(1010 * scale);
        var first = ReadBgr(source, row, left);
        var color = Matches(first, 34, 215, 150) ? "green" : Matches(first, 90, 90, 255) ? "red" : "unknown";
        if (color == "unknown") return (color, null, 0);
        var run = 0;
        var pixels = 0;
        var last = -1;
        var prefix = 0;
        for (var x = left; x < right; x++)
        {
            var pixel = ReadBgr(source, row, x);
            var matched = color == "green" ? Matches(pixel, 34, 215, 150) : Matches(pixel, 90, 90, 255);
            run = matched ? run + 1 : 0;
            if (matched) pixels++;
            if (x == left + prefix && matched) prefix++;
            // Ignore isolated pixels after a text gap or beyond the bar's real edge.
            if (run >= 3) last = x;
        }
        return prefix >= 3 && last >= left ? (color, (last - left + 1.0) / (right - left), pixels)
            : ("unknown", null, pixels);
    }

    /// <summary>Read three color channels without converting or modifying the borrowed Mat.</summary>
    private static Vec3b ReadBgr(Mat source, int row, int column)
    {
        if (source.Channels() == 3) return source.At<Vec3b>(row, column);
        var pixel = source.At<Vec4b>(row, column);
        return new Vec3b(pixel.Item0, pixel.Item1, pixel.Item2);
    }

    /// <summary>Small color tolerance preserves the native HUD rule across capture formats.</summary>
    private static bool Matches(Vec3b pixel, int blue, int green, int red) =>
        Math.Abs(pixel.Item0 - blue) <= 4 && Math.Abs(pixel.Item1 - green) <= 4 && Math.Abs(pixel.Item2 - red) <= 4;
}
