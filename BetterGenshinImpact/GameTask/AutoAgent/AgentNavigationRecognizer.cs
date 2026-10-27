using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using BetterGenshinImpact.GameTask.AutoTrackPath;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Common.Map.Maps;
using BetterGenshinImpact.GameTask.Common.Map.Maps.Base;
using BetterGenshinImpact.GameTask.Common.Map.MiniMap;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using OpenCvSharp;
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Opt-in, capture-thread-owned localization using BetterGI's existing fixed courtyard map and yaw recognizers.</summary>
internal sealed class AgentNavigationRecognizer : IDisposable
{
    /// <summary>Explicit capability name; callers cannot supply route coordinates or arbitrary assets.</summary>
    internal const string ProfileId = "mondstadt-courtyard-hybrid-v1";
    /// <summary>The shared map is accessed only while the agent owns the existing TaskRunner scope.</summary>
    private readonly SceneBaseMapByTemplateMatch _map;
    /// <summary>Owned yaw preprocessing state, never shared with another capture worker.</summary>
    private readonly MiniMapPreprocessor _yaw;
    /// <summary>Positive map-image anchor keeps matching local, without global fallback.</summary>
    private readonly Point2f _anchor;
    /// <summary>Fixed endpoints expressed in the map's native image coordinate plane.</summary>
    private readonly Waypoint _start, _end;
    /// <summary>Existing runtime camera scaling, used only for calculating a correction.</summary>
    private readonly double _dpi;

    /// <summary>Warm native assets before acquiring a frame; no input or model work occurs here.</summary>
    internal AgentNavigationRecognizer(double dpi)
    {
        _dpi = dpi;
        NativeNavigationBaselineOperations.ValidateRoute(File.ReadAllBytes(
            Global.Absolute(@"GameTask\Common\Element\Assets\Json\合成台_蒙德.json")), false);
        _map = MapManager.GetMap("Teyvat", "TemplateMatch") as SceneBaseMapByTemplateMatch
            ?? throw new InvalidOperationException("local_template_map_unavailable");
        _map.WarmUp();
        _anchor = _map.ConvertGenshinMapCoordinatesToImageCoordinates(
            new Point2f((float)NavigationBaselineTask.StartX, (float)NavigationBaselineTask.StartY));
        var endpoint = _map.ConvertGenshinMapCoordinatesToImageCoordinates(
            new Point2f((float)NavigationBaselineTask.EndX, (float)NavigationBaselineTask.EndY));
        _start = new Waypoint { X = _anchor.X, Y = _anchor.Y };
        _end = new Waypoint { X = endpoint.X, Y = endpoint.Y };
        _yaw = new MiniMapPreprocessor();
    }

    /// <summary>Declare the two reviewed points and matching constraints; the client still owns its explicit input lease.</summary>
    internal static object Capability => new
    {
        version = 1, profileId = ProfileId, sameFrame = true, readOnly = true,
        start = new { x = NavigationBaselineTask.StartX, y = NavigationBaselineTask.StartY },
        end = new { x = NavigationBaselineTask.EndX, y = NavigationBaselineTask.EndY },
        layerId = "City_102", minimumPositionConfidence = .99, minimumYawConfidence = .2,
        maxWidth = 1920, maxHeight = 1080, normalIsGroundedProof = false
    };

    /// <summary>Read only the supplied native image and publish no stale pose after any failed gate or match.</summary>
    internal AgentNavigationPose Recognize(Mat source, AgentObservation observation,
        AgentWorldReadiness readiness, AgentMotionEvidence motion)
    {
        var started = Stopwatch.GetTimestamp();
        AgentNavigationPose Missing(string reason) => AgentNavigationPose.Unavailable(observation.FrameId,
            reason, Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        if (!readiness.Ready) return Missing("world_not_ready");
        if (motion.Status != AgentMotionStatus.Normal || motion.SpaceKeyMatched != false)
            return Missing("non_normal_motion");
        if (source.Width > 1920 || source.Height > 1080 || source.Width < 640
            || Math.Abs((double)source.Width / source.Height - 16.0 / 9) > .02)
            return Missing("unsupported_geometry");
        try
        {
            // Borrow only the minimap ROI; conversion owns its output and never disposes or mutates capture pixels.
            using var minimap = new Mat(source, MapAssets.Get(source.Width, source.Height).MimiMapRect);
            using var bgr = new Mat();
            if (minimap.Channels() == 4) Cv2.CvtColor(minimap, bgr, ColorConversionCodes.BGRA2BGR);
            else if (minimap.Channels() == 3) minimap.CopyTo(bgr);
            else return Missing("unsupported_pixel_format");
            using var prepared = _yaw.TryPrepare(bgr, .2f);
            if (prepared is null) return Missing("yaw_unrecognized");
            var position = _map.GetPreparedLocalPosition(prepared, _anchor.X, _anchor.Y, 0);
            if (position == default) return Missing("local_position_unrecognized");
            var match = _map.PrevSuccessResult;
            var world = _map.ConvertImageCoordinatesToGenshinMapCoordinates(position);
            if (world is null || !AgentNavigationPose.IsQualified(world.Value.X, world.Value.Y,
                prepared.YawDegrees, match.Confidence, prepared.YawConfidence, match.Layer?.LayerId))
                return Missing("pose_not_qualified");
            var startHeading = Navigation.GetTargetOrientation(_start, position);
            var endHeading = Navigation.GetTargetOrientation(_end, position);
            var toStart = 0; var toEnd = 0;
            CameraRotateTask.ApplyMeasuredRotation(startHeading, prepared.YawDegrees, _dpi,
                CancellationToken.None, (dx, _) => toStart = dx);
            CameraRotateTask.ApplyMeasuredRotation(endHeading, prepared.YawDegrees, _dpi,
                CancellationToken.None, (dx, _) => toEnd = dx);
            return new("valid", null, observation.FrameId, world.Value.X, world.Value.Y, prepared.YawDegrees,
                match.Confidence, prepared.YawConfidence, match.Layer?.LayerId, startHeading, endHeading,
                toStart, toEnd, Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        }
        catch (Exception error) when (error is OpenCVException or InvalidOperationException or ArgumentException)
        {
            return Missing("recognition_failed:" + error.GetType().Name);
        }
    }

    /// <summary>Dispose only this stream's preprocessing resources; the map remains owned by MapManager.</summary>
    public void Dispose() => _yaw.Dispose();
}
