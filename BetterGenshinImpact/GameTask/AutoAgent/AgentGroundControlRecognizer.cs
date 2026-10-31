using System;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using BetterGenshinImpact.Core.Agent;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Bounded native keycap/glyph and existing swim-hint checks; no OCR, assets or extra capture.</summary>
public static class AgentGroundControlRecognizer
{
    /// <summary>Closed first-version capability, independent of motion and combat observation contracts.</summary>
    public static object Capability => new
    {
        version = 1, method = AgentGroundControlEvidence.MethodName, sameFrame = true, readOnly = true,
        requiresWgcSourceIdentity = true, sourceWidth = 1920, sourceHeight = 1080, cropFormat = "rgb24",
        eRegion = new { x = 1660, y = 1014, width = 75, height = 42 },
        qRegion = new { x = 1775, y = 1014, width = 80, height = 42 },
        swimRegion = new { x = 1819, y = 1028, width = 9, height = 7 },
        swimMinimumPixels = 4, maximumCropBytes = 19530, requiresBothKeycaps = true,
        authorizesInput = false, physicallyGrounded = false
    };

    // The masks retain the distinct E and Q glyphs and surrounding rectangular light keycaps.
    // '#' requires dark RGB, '.' requires neutral light RGB, '+' ignores antialias/corner pixels.
    // Reference: inspected dry frame24 SHA256 e2d586be955c79eafbf84fec522dac925e571122f93bc81ef21566952109efb8.
    internal static readonly string[] EPattern =
    [
        "+............................+", "+.............................", "..............................",
        "..............................", "..........+++++++++...........", "..........##########..........",
        "...........###+++++#..........", "...........###................", "...........###................",
        "...........###................", "...........########...........", "...........########...........",
        "...........###................", "...........###................", "...........###................",
        "...........###................", "...........#########..........", "..........+#########..........",
        "..............................", "..............................", "..............................",
        "..............................", "..............................", "+.............................", "++..........................++"
    ];
    /// <summary>Q requires its enclosed light centre and lower-right tail, rather than any white rectangle.</summary>
    internal static readonly string[] QPattern =
    [
        "+............................+", "+.............................", "..............................",
        "..............................", ".............++++.............", "...........+#######...........",
        "..........####..+###..........", ".........+###....+###.........", ".........###+.....###.........",
        ".........###......###+........", "........+###......####........", "........+###......####........",
        ".........###......####........", ".........###......###+........", ".........####.....###.........",
        "..........###+...###+.........", "..........+####+####..........", "............+#####+...........",
        "...............####...........", "................###+..........", ".................###+.........",
        "..............................", "..............................", "+............................+", "++..........................++"
    ];

    /// <summary>Inspect only these original native pixels; unsupported layouts remain unavailable.</summary>
    public static AgentGroundControlEvidence Recognize(Mat source, AgentObservation observation, AgentMotionEvidence motion)
    {
        var started = Stopwatch.GetTimestamp();
        AgentGroundControlEvidence Missing(string reason) => AgentGroundControlEvidence.Unavailable(observation,
            reason, Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        if (source.Empty() || source.Width != 1920 || source.Height != 1080 ||
            observation.SourceWidth != 1920 || observation.SourceHeight != 1080 ||
            source.Type() != MatType.CV_8UC3 && source.Type() != MatType.CV_8UC4)
            return Missing("unsupported_geometry");
        if (observation.SourceFrame is null) return Missing("source_identity_missing");
        if (observation.WorldEvidence != AgentWorldEvidence.WorldHud) return Missing("world_not_ready");
        try
        {
            var e = ReadCrop(source, new Rect(1660, 1014, 75, 42));
            var q = ReadCrop(source, new Rect(1775, 1014, 80, 42));
            var eMatch = Match(e.Bytes, e.Crop, EPattern, 1684, 1027);
            var qMatch = Match(q.Bytes, q.Crop, QPattern, 1804, 1027);
            var swim = 0;
            for (var y = 1028; y < 1035; y++)
                for (var x = 1819; x < 1828; x++)
                {
                    var i = ((y - q.Crop.Y) * q.Crop.Width + x - q.Crop.X) * 3;
                    if (q.Bytes[i] is >= 242 and <= 255 && q.Bytes[i + 1] is >= 223 and <= 233 &&
                        q.Bytes[i + 2] is >= 39 and <= 44) swim++;
                }
            var confirmed = eMatch.Matched && qMatch.Matched && swim < 4 &&
                motion.SpaceKeyMatched == false && motion.XKeyMatched == false;
            return new("valid", swim >= 4 ? "swim_control_hint" : confirmed ? "ground_control_layout" : "ground_controls_unconfirmed",
                observation.FrameId, observation.SourceFrame, 1920, 1080, confirmed, swim,
                motion.SpaceKeyMatched, motion.XKeyMatched, eMatch, qMatch, [e.Crop, q.Crop],
                Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        }
        catch (Exception) { return Missing("recognition_failed"); }
    }

    /// <summary>Copy only two tiny RGB regions and retain their exact inline bytes and hashes.</summary>
    private static (AgentControlCrop Crop, byte[] Bytes) ReadCrop(Mat source, Rect roi)
    {
        var channels = source.Channels();
        var row = new byte[roi.Width * channels];
        var bytes = new byte[roi.Width * roi.Height * 3];
        for (var y = 0; y < roi.Height; y++)
        {
            Marshal.Copy(source.Ptr(roi.Y + y) + roi.X * channels, row, 0, row.Length);
            for (var x = 0; x < roi.Width; x++)
            {
                var target = (y * roi.Width + x) * 3;
                bytes[target] = row[x * channels + 2];
                bytes[target + 1] = row[x * channels + 1];
                bytes[target + 2] = row[x * channels];
            }
        }
        return (new(roi.X, roi.Y, roi.Width, roi.Height, "rgb24", Convert.ToBase64String(bytes),
            Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()), bytes);
    }

    /// <summary>Search seven pixels per axis around the fixed keycap; preserve the best raw matching counts.</summary>
    private static AgentKeycapEvidence Match(byte[] bytes, AgentControlCrop crop, string[] pattern, int expectedX, int expectedY)
    {
        var darkExpected = pattern.Sum(row => row.Count(c => c == '#'));
        var lightExpected = pattern.Sum(row => row.Count(c => c == '.'));
        AgentKeycapEvidence? best = null;
        var bestScore = -1.0;
        for (var y = expectedY - 3; y <= expectedY + 3; y++)
            for (var x = expectedX - 3; x <= expectedX + 3; x++)
            {
                var dark = 0; var light = 0;
                for (var py = 0; py < 25; py++)
                    for (var px = 0; px < 30; px++)
                    {
                        var i = ((y + py - crop.Y) * crop.Width + x + px - crop.X) * 3;
                        var min = Math.Min(bytes[i], Math.Min(bytes[i + 1], bytes[i + 2]));
                        var max = Math.Max(bytes[i], Math.Max(bytes[i + 1], bytes[i + 2]));
                        if (pattern[py][px] == '#' && max < 150) dark++;
                        if (pattern[py][px] == '.' && min >= 205 && max - min <= 40) light++;
                    }
                var score = Math.Min((double)dark / darkExpected / .90, (double)light / lightExpected / .97);
                if (score > bestScore)
                {
                    bestScore = score;
                    best = new(dark * 100 >= 90 * darkExpected && light * 100 >= 97 * lightExpected,
                        x, y, 30, 25, dark, darkExpected, light, lightExpected);
                }
            }
        return best!;
    }
}
