using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using BetterGenshinImpact.Core.Recognition.OpenCv.TemplateMatch;
using OpenCvSharp;
using BetterGenshinImpact.GameTask.Common.Map.MiniMap;
using BetterGenshinImpact.Helpers;
using Microsoft.Extensions.Logging;

namespace BetterGenshinImpact.GameTask.Common.Map.Maps.Base;

using static MiniMapMatchConfig;

public abstract class SceneBaseMapByTemplateMatch : SceneBaseMap
{
    private readonly MiniMapPreprocessor _miniMapPreprocessor = new();
    
    private List<BaseMapLayerByTemplateMatch> _layers = [];
    private readonly object _layersLock = new();
    public new List<BaseMapLayerByTemplateMatch> Layers
    {
        get
        {
            if (_layers.Count == 0)
            {
                lock (_layersLock)
                {
                    if (_layers.Count == 0)
                    {
                        TaskControl.Logger.LogInformation("[TemplateMatch] Loading Teyvat map templates; this may take a while. Please wait...");
                        Layers = BaseMapLayerByTemplateMatch.LoadLayers(this);
                        TaskControl.Logger.LogInformation("Map feature points loaded!");
                    }
                }
            }
            return _layers;
        }
        set => _layers = value ?? [];
    }
    
    public MatchResult PrevSuccessResult;
    
    public struct MatchResult
    {
        public BaseMapLayerByTemplateMatch? Layer = null; // 地图信息
        public Point2f MapPos = new Point2f(0, 0);        // 匹配位置
        public double Confidence = 0;

        public readonly bool IsSuccess(int rank)
        {
            var index = Math.Clamp(rank, 0, ConfidenceThresholds.Length - 1);
            return Confidence <= 1 && Confidence >= ConfidenceThresholds[index];
        }
        public MatchResult() {}
    }
    
    protected SceneBaseMapByTemplateMatch(
        MapTypes type, 
        Size mapSize, 
        Point2f mapOriginInImageCoordinate, 
        int mapImageBlockWidth, 
        int splitRow, 
        int splitCol)
        : base(type, mapSize, mapOriginInImageCoordinate, mapImageBlockWidth, splitRow, splitCol)
    {
    }
    
    public override void WarmUp()
    {
        Console.WriteLine("Preloaded map layers: " + Layers.Count);
    }
    
    public override Point2f GetMiniMapPosition(Mat colorMiniMapMat)
    {
        var result= new MatchResult();
        var (miniMap, mask) = _miniMapPreprocessor.GetMiniMapAndMask(colorMiniMapMat);
        using (miniMap)
        using (mask)
        {
            GlobalMatch(miniMap, mask, ref result);
            return UpdateResult(result, 2);
        }
    }

    /// <summary>
    /// 小地图局部匹配，失败不进行全局匹配，若需要全局请用全局匹配
    /// </summary>
    /// <param name="colorMiniMapMat"></param>
    /// <param name="prevX"></param>
    /// <param name="prevY"></param>
    /// <returns></returns>
    public override Point2f GetMiniMapPosition(Mat colorMiniMapMat, float prevX, float prevY)
    {
        return GetMiniMapPosition(colorMiniMapMat, prevX, prevY, 2);
    }

    public Point2f GetMiniMapPosition(Mat colorMiniMapMat, float prevX, float prevY, int rank)
    {
        if (prevX <= 0 || prevY <= 0)
        {
            return GetMiniMapPosition(colorMiniMapMat);
        }
        var curResult = new MatchResult();
        var (miniMap, mask) = _miniMapPreprocessor.GetMiniMapAndMask(colorMiniMapMat);
        using (miniMap)
        using (mask)
        {
            LocalMatch(miniMap, mask, ConvertImageCoordinatesToGenshinMapCoordinates(new Point2f(prevX, prevY))!.Value, ref curResult);
            return UpdateResult(curResult, rank);
        }
    }

    /// <summary>
    /// Bounded local match for a fogged minimap. The caller must supply a recently verified
    /// position; this deliberately has no global fallback or navigation-cache side effects.
    /// </summary>
    public Point2f GetFogAwareLocalPosition(Mat colorMiniMapMat, Point2f expectedImagePosition, string layerId)
    {
        if (string.IsNullOrWhiteSpace(layerId)
            || !float.IsFinite(expectedImagePosition.X) || !float.IsFinite(expectedImagePosition.Y))
            return default;

        var expected = ConvertImageCoordinatesToGenshinMapCoordinates(expectedImagePosition);
        if (expected is null) return default;

        using var preprocessor = new MiniMapPreprocessor();
        var (_, rotationConfidence) = preprocessor.PredictRotationWithConfidence(colorMiniMapMat);
        if (rotationConfidence < 0.82f) return default;

        var (miniMap, mask) = preprocessor.GetMiniMapAndMask(colorMiniMapMat);
        using (miniMap)
        using (mask)
        using (var gray = new Mat())
        using (var bright = new Mat())
        {
            var originalPixels = Cv2.CountNonZero(mask);
            if (originalPixels < 5000) return default;
            Cv2.CvtColor(miniMap, gray, ColorConversionCodes.BGR2GRAY);
            Cv2.Threshold(gray, bright, 100, 255, ThresholdTypes.Binary);
            Cv2.BitwiseAnd(mask, bright, mask);
            var visiblePixels = Cv2.CountNonZero(mask);
            // Only use this mode when fog really covers a substantial part of the minimap.
            if (visiblePixels < 3000 || visiblePixels > originalPixels * 0.6) return default;

            using var context = new MatchContext(miniMap, mask);
            var result = new MatchResult();
            // Fog masks remove most terrain information. A nearby underground/city
            // layer can win the score while returning a plausible but wrong point.
            foreach (var layer in Layers.Where(layer => layer.LayerId == layerId))
            {
                var (candidate, value) = layer.RoughMatch(
                    context.MaskedMiniMapRoughs, context.MaskRoughF, expected.Value, 3);
                if (candidate == default || !context.NormalizerRough.Update(value + context.TplSumSq))
                    continue;
                result.Layer = layer;
                result.MapPos = candidate;
                result.Confidence = context.NormalizerRough.Confidence();
            }

            if (!result.IsSuccess(2)) return default;
            ExactMatch(context, ref result);
            if (result.Confidence < 0.955 || result.Confidence > 1
                || Distance(result.MapPos, expected.Value) > 15)
                return default;
            return ConvertGenshinMapCoordinatesToImageCoordinates(result.MapPos);
        }
    }

    private static double Distance(Point2f a, Point2f b) =>
        Math.Sqrt(Math.Pow(a.X - b.X, 2) + Math.Pow(a.Y - b.Y, 2));
    
    private Point2f UpdateResult(in MatchResult result, int rank)
    {
        if (!result.IsSuccess(rank)) return default;
        PrevSuccessResult = result;
        return ConvertGenshinMapCoordinatesToImageCoordinates(PrevSuccessResult.MapPos);
    }
    
    [Conditional("DEBUG")]
    private static void LogMatchResult(string stage, in MatchResult result)
    {
        Debug.WriteLine($"{stage}: coordinates ({result.MapPos.X:F4}, {result.MapPos.Y:F4}), confidence {result.Confidence:F4}");
    }

    #region 模板匹配
    
    public void GlobalMatch(Mat miniMap, Mat mask, ref MatchResult result)
    {
        SpeedTimer speedTimer = new SpeedTimer("Global match");
        using var context = new MatchContext(miniMap, mask);
        RoughMatchGlobal(context, ref result);
        speedTimer.Record("Global coarse match");
        ExactMatch(context, ref result);
        speedTimer.Record("Exact match");
        speedTimer.DebugPrint();
    }

    // 局部匹配：在上一次匹配位置附近进行搜索
    public void LocalMatch(Mat miniMap, Mat mask, Point2f pos, ref MatchResult result)
    {
        SpeedTimer speedTimer = new SpeedTimer("Local match");
        using var context = new MatchContext(miniMap, mask);
        RoughMatchLocal(context, pos, ref result);
        speedTimer.Record("Local coarse match");
        ExactMatch(context, ref result);
        speedTimer.Record("Exact match");
        speedTimer.DebugPrint();
    }
    
    public void RoughMatchGlobal(MatchContext context, ref MatchResult result)
    {
        foreach (var layer in Layers)
        {
            var (tempPos, tempVal) = layer.RoughMatch(context.MaskedMiniMapRoughs, context.MaskRoughF);
            if (!context.NormalizerRough.Update(tempVal + context.TplSumSq)) continue;
            result.Layer = layer;
            result.MapPos = tempPos;
        }
        result.Confidence = context.NormalizerRough.Confidence();
        LogMatchResult("Global coarse match", result);
    }
    
    public void RoughMatchLocal(MatchContext context, Point2f pos, ref MatchResult result)
    {
        result.MapPos = pos;
        if (PrevSuccessResult.MapPos.Equals(pos))
        {
            result.Layer = PrevSuccessResult.Layer;
        }
        if (result.Layer != null)
        {
            var (tempPos, tempVal) = result.Layer.RoughMatch(context.MaskedMiniMapRoughs, context.MaskRoughF, pos);
            if (tempPos != default && context.NormalizerRough.Update(tempVal + context.TplSumSq))
            {
                result.MapPos = tempPos;
                result.Confidence = context.NormalizerRough.Confidence();
            }
        }

        if (result.IsSuccess(0))
        {
            LogMatchResult("Local coarse match", result);
            return;
        }
        
        var flag = false;
        foreach (var layer in (result.Layer == null)? Layers : Layers.Where(layer => layer != PrevSuccessResult.Layer))
        {
            var (tempPos, tempVal) = layer.RoughMatch(context.MaskedMiniMapRoughs, context.MaskRoughF, pos);
            if (tempPos == default || !context.NormalizerRough.Update(tempVal + context.TplSumSq)) continue;
            result.Layer = layer;
            result.MapPos = tempPos;
            flag = true;
        }
        if (flag) result.Confidence = context.NormalizerRough.Confidence();
        LogMatchResult("Local coarse match", result);
        //if (CurResult.IsSuccess) return;
        //RoughMatchLocalChan(context, pos);
        //if (CurResult.IsSuccess) return;
        //RoughMatchGlobal(context);
    }

    /// <summary>
    /// 指定通道匹配，用于边缘位置匹配，暂时不用，等后续优化
    /// </summary>
    /// <param name="context"></param>
    /// <param name="pos"></param>
    /// <param name="result"></param>
    public void RoughMatchLocalChan(MatchContext context, Point2f pos, ref MatchResult result)
    {
        result = default;
        var flag = false;
        foreach (var layer in Layers)
        {
            var (tempPos, tempVal) = layer.RoughMatch(context.MaskedMiniMapRoughs, context.MaskRoughF, pos, context.Channels);
            if (!context.NormalizerRoughChan.Update(tempVal + context.TplSumSqChan)) continue;
            result.Layer = layer;
            result.MapPos = tempPos;
            flag = true;
        }
        if (flag) result.Confidence = context.NormalizerRough.Confidence();
    }
    
    public void ExactMatch(MatchContext context, ref MatchResult result)
    {
        if (result.Layer == null || !result.IsSuccess(2)) return;
        var (tempPos, tempVal) = result.Layer.ExactMatch(context.MiniMapExact, context.MaskExact, result.MapPos);
        if (tempPos != default && context.NormalizerExact.Update(tempVal))
        {
            result.MapPos = tempPos;
            result.Confidence = context.NormalizerExact.Confidence();
        }
        else
        {
            result.Confidence = 0;
        }
        LogMatchResult("Exact match", result);
    }
    #endregion
    
}
