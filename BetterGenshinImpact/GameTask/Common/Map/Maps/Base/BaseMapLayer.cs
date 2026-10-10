using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Recognition.OpenCv.FeatureMatch;
using BetterGenshinImpact.Core.Recognition.OpenCv.Model;
using BetterGenshinImpact.Helpers;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.Common.Map.Maps.Base;

/// <summary>
/// 每层的特征
/// </summary>
public class BaseMapLayer(SceneBaseMap baseMap)
{
    // public string Name { get; set; } = string.Empty;
    //
    // public string LayerId { get; set; } = string.Empty;
    //
    // public string LayerGroupId { get; set; } = string.Empty;

    /// <summary>
    /// 层级
    /// </summary>
    public int Floor { get; set; } = 0;

    /// <summary>
    /// 当前层的所有特征
    /// </summary>
    public Mat TrainDescriptors { get; set; } = new();

    public KeyPoint[] TrainKeyPoints { get; set; } = [];

    /// <summary>
    /// 切割后的特征块
    /// </summary>
    public KeyPointFeatureBlock[][] SplitBlocks { get; set; } = [];

    /// <summary>
    /// 最近一次合并的特征块
    /// </summary>
    private KeyPointFeatureBlock? _lastMergedBlock = null;

    /// <summary>
    /// 从本地文件加载分层地图信息
    /// 路径 Assets\Map
    /// - Teyvat
    ///     - Teyvat_0_2048_SIFT.kp.bin
    ///     - Teyvat_0_2048_SIFT.mat.png
    ///     - Teyvat_-1_2048_SIFT.kp.bin
    ///     - Teyvat_-1_2048_SIFT.mat.png
    /// </summary>
    /// <param name="baseMap"></param>
    /// <returns></returns>
    public static List<BaseMapLayer> LoadLayers(SceneBaseMap baseMap)
    {
        var layers = new List<BaseMapLayer>();
        var layerDir = Path.Combine(Global.Absolute(@"Assets\Map\"), baseMap.Type.ToString());
        if (!Directory.Exists(layerDir))
        {
            return layers;
        }

        var files = Directory.GetFiles(layerDir);
        var validFiles = files.Where(f => (f.EndsWith(".kp.bin") || f.EndsWith(".mat.png"))
                                          && !f.EndsWith("Teyvat_0_256_SIFT.kp.bin")
                                          && !f.EndsWith("Teyvat_0_256_SIFT.mat.png"));
        // 解析后按 floor 分组，然后按 floor 创建BaseMapLayer
        var groupedFiles = validFiles.GroupBy(file =>
        {
            var fileName = Path.GetFileNameWithoutExtension(file);
            var parts = fileName.Split('_');
            if (parts.Length < 3)
            {
                throw new Exception($"Unrecognized file name in the layered map data folder: {fileName}");
            }

            return int.TryParse(parts[1], out var floor) ? floor : throw new Exception($"Unrecognized file name in the layered map data folder: {fileName}");
        });

        foreach (var group in groupedFiles)
        {
            var floor = group.Key;
            var layer = new BaseMapLayer(baseMap) { Floor = floor };

            // 查找特征文件路径
            var kpFilePath = group.First(f => f.EndsWith(".kp.bin"));
            var matFilePath = group.First(f => f.EndsWith(".mat.png"));

            SpeedTimer speedTimer = new($"Loading map features for {Path.GetFileNameWithoutExtension(kpFilePath)}");
            // 加载特征数据
            layer.TrainKeyPoints = FeatureStorageHelper.LoadKeyPointArray(kpFilePath) ?? throw new Exception($"Failed to load map data. File: {kpFilePath}");
            speedTimer.Record("Keypoints");
            layer.TrainDescriptors = FeatureStorageHelper.LoadDescriptorMat(matFilePath) ?? throw new Exception($"Failed to load map data. File: {matFilePath}");
            speedTimer.Record("Descriptors");

            // 切割特征数据
            if (baseMap.SplitRow > 0 || baseMap.SplitCol > 0)
            {
                layer.SplitBlocks = KeyPointFeatureBlockHelper.SplitFeatures(baseMap.MapSize, baseMap.SplitRow, baseMap.SplitCol, layer.TrainKeyPoints, layer.TrainDescriptors);
                speedTimer.Record("Split keypoints");
            }

            speedTimer.DebugPrint();

            layers.Add(layer);
        }

        // 从 0, -1, -2 这样的顺序对这个list排序
        layers.Sort((a, b) =>
        {
            if (a.Floor == b.Floor)
            {
                return 0;
            }

            return a.Floor < b.Floor ? 1 : -1;
        });
        return layers;
    }
    
    public static BaseMapLayer LoadLayer(SceneBaseMap baseMap, string kpFilePath, string matFilePath)
    {
        var layer = new BaseMapLayer(baseMap)
        {
            Floor = 0,
            TrainKeyPoints = FeatureStorageHelper.LoadKeyPointArray(kpFilePath) ?? throw new Exception($"Failed to load map data. File: {kpFilePath}"),
            TrainDescriptors = FeatureStorageHelper.LoadDescriptorMat(matFilePath) ?? throw new Exception($"Failed to load map data. File: {matFilePath}")
        };
        return layer;
    }

    /// <summary>
    /// 选择切分后的特征块合并
    /// </summary>
    /// <param name="prevX"></param>
    /// <param name="prevY"></param>
    /// <returns></returns>
    public (KeyPoint[], Mat) ChooseBlocks(float prevX, float prevY)
    {
        if (baseMap.SplitRow <= 0 || baseMap.SplitCol <= 0 || SplitBlocks.Length == 0)
        {
            return (TrainKeyPoints, TrainDescriptors);
        }

        var (cellRow, cellCol) = KeyPointFeatureBlockHelper.GetCellIndex(baseMap.MapSize, baseMap.SplitRow, baseMap.SplitCol, prevX, prevY);
        Debug.WriteLine($"Current coordinates ({prevX},{prevY}) are in feature block ({cellRow},{cellCol})");
        if (_lastMergedBlock == null || _lastMergedBlock.MergedCenterCellRow != cellRow || _lastMergedBlock.MergedCenterCellCol != cellCol)
        {
            Debug.WriteLine($"---------Switched to a new feature block ({cellRow},{cellCol}); merging keypoints--------");
            _lastMergedBlock = KeyPointFeatureBlockHelper.MergeNeighboringFeatures(SplitBlocks, TrainDescriptors, cellRow, cellCol);
        }

        return (_lastMergedBlock.KeyPointArray, _lastMergedBlock.Descriptor!);
    }
}
