using BetterGenshinImpact.Core.Recognition;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using OpenCvSharp;
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;

namespace BetterGenshinImpact.Service;

public sealed record RecognitionTemplateDraft
{
    public const double DefaultThreshold = 0.8;
    public const TemplateMatchModes DefaultTemplateMatchMode = TemplateMatchModes.CCoeffNormed;
    public const string DefaultMaskColor = "#00FF00";
    public const int DefaultBinaryThreshold = 128;
    public const int DefaultMaxMatchCount = -1;
    public const SearchAnchorMode DefaultSearchAnchorMode = SearchAnchorMode.Auto;
    public const int DefaultSearchExpand = 10;

    public required string JsonPath { get; init; }

    public required string AssetsRootPath { get; init; }

    public required string ObjectName { get; init; }

    public required string TemplateFileName { get; init; }

    public required Rect Selection { get; init; }

    public required int ReferenceWidth { get; init; }

    public required int ReferenceHeight { get; init; }

    public double Threshold { get; init; } = DefaultThreshold;

    public TemplateMatchModes TemplateMatchMode { get; init; } = DefaultTemplateMatchMode;

    public bool Use3Channels { get; init; }

    public bool UseMask { get; init; }

    public string MaskColor { get; init; } = DefaultMaskColor;

    public bool UseBinaryMatch { get; init; }

    public int BinaryThreshold { get; init; } = DefaultBinaryThreshold;

    public int MaxMatchCount { get; init; } = DefaultMaxMatchCount;

    public bool DrawOnWindow { get; init; }

    public SearchAnchorMode SearchAnchorMode { get; init; } = DefaultSearchAnchorMode;

    /// <summary>
    /// 参考画布坐标系中的独立搜索框；为空时使用模板选区作为基础搜索框。
    /// </summary>
    public Rect? ReferenceSearchBox { get; init; }

    public int SearchExpandWidth { get; init; } = DefaultSearchExpand;

    public int SearchExpandHeight { get; init; } = DefaultSearchExpand;

    /// <summary>
    /// 按当前截图宽高计算的四边扩展比例，0.05 表示 5%；有值时优先于像素扩展。
    /// </summary>
    public SearchExpandRatio? SearchExpandPercent { get; init; }
}

public sealed record RecognitionTemplateSavePlan(
    string JsonPath,
    string ImagePath,
    string JsonContent,
    Rect Selection,
    int ReferenceWidth,
    int ReferenceHeight,
    IReadOnlyList<string> Conflicts);

/// <summary>
/// 负责校验并一致性写入 Recognition 模板图片与 JSON 配置。
/// </summary>
public sealed class RecognitionTemplateAssetService
{
    private static readonly UTF8Encoding Utf8WithoutBom = new(false);
    private const string FallbackResolutionFolder = "1920x1080";

    public RecognitionTemplateSavePlan Prepare(RecognitionTemplateDraft draft)
    {
        ArgumentNullException.ThrowIfNull(draft);

        var jsonPath = NormalizeJsonPath(draft.JsonPath);
        var assetsRootPath = NormalizeDirectoryPath(draft.AssetsRootPath, "Assets root directory");
        var objectName = draft.ObjectName.Trim();
        var templateFileName = draft.TemplateFileName.Trim();

        ValidateObjectName(objectName);
        ValidateTemplateFileName(templateFileName);
        ValidateRecognitionParameters(draft);

        var resolutionDirectory = Path.GetFullPath(Path.Combine(assetsRootPath, FallbackResolutionFolder));
        var imagePath = Path.GetFullPath(Path.Combine(resolutionDirectory, templateFileName));
        EnsureChildPath(resolutionDirectory, imagePath);

        var root = LoadOrCreateRoot(jsonPath);
        var objects = GetOrCreateObjects(root);
        var conflicts = FindConflicts(objects, objectName, templateFileName, imagePath);

        objects[objectName] = BuildObjectConfig(draft, templateFileName);
        var jsonContent = root.ToString(Formatting.Indented) + Environment.NewLine;

        // 用现有类型反序列化一次，提前发现生成结构与当前 Recognition.json 模型不兼容的问题。
        _ = JsonConvert.DeserializeObject<RecognitionObjectJsonFile>(jsonContent)
            ?? throw new InvalidOperationException("The generated Recognition.json configuration could not be parsed.");

        return new RecognitionTemplateSavePlan(
            jsonPath,
            imagePath,
            jsonContent,
            draft.Selection,
            draft.ReferenceWidth,
            draft.ReferenceHeight,
            conflicts);
    }

    public void Commit(RecognitionTemplateSavePlan plan, Mat screenshot)
    {
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(screenshot);

        if (screenshot.Width != plan.ReferenceWidth || screenshot.Height != plan.ReferenceHeight)
        {
            throw new InvalidOperationException("The screenshot dimensions have changed. Reopen the template editor.");
        }

        ValidateSelection(plan.Selection, screenshot.Width, screenshot.Height);

        using var cropped = new Mat(screenshot, plan.Selection);
        if (!Cv2.ImEncode(".png", cropped, out var imageBytes))
        {
            throw new IOException("Failed to encode the template image.");
        }

        var jsonDirectory = Path.GetDirectoryName(plan.JsonPath)
                            ?? throw new InvalidOperationException("The Recognition.json path has no parent directory.");
        var imageDirectory = Path.GetDirectoryName(plan.ImagePath)
                             ?? throw new InvalidOperationException("The template image path has no parent directory.");
        Directory.CreateDirectory(jsonDirectory);
        Directory.CreateDirectory(imageDirectory);

        var operationId = Guid.NewGuid().ToString("N");
        var jsonTempPath = Path.Combine(jsonDirectory, $".{Path.GetFileName(plan.JsonPath)}.{operationId}.tmp");
        var imageTempPath = Path.Combine(imageDirectory, $".{Path.GetFileName(plan.ImagePath)}.{operationId}.tmp");
        var jsonBackupPath = jsonTempPath + ".bak";
        var imageBackupPath = imageTempPath + ".bak";
        var jsonExisted = File.Exists(plan.JsonPath);
        var imageExisted = File.Exists(plan.ImagePath);
        var jsonCommitted = false;
        var imageCommitted = false;
        var keepJsonBackup = false;
        var keepImageBackup = false;

        try
        {
            File.WriteAllText(jsonTempPath, plan.JsonContent, Utf8WithoutBom);
            File.WriteAllBytes(imageTempPath, imageBytes);

            if (jsonExisted)
            {
                File.Copy(plan.JsonPath, jsonBackupPath, true);
            }

            if (imageExisted)
            {
                File.Copy(plan.ImagePath, imageBackupPath, true);
            }

            // 先提交图片，确保 JSON 生效时引用的文件已经存在。
            File.Move(imageTempPath, plan.ImagePath, true);
            imageCommitted = true;

            File.Move(jsonTempPath, plan.JsonPath, true);
            jsonCommitted = true;
        }
        catch (Exception writeException)
        {
            var jsonRestored = RestoreFile(plan.JsonPath, jsonBackupPath, jsonExisted, jsonCommitted);
            var imageRestored = RestoreFile(plan.ImagePath, imageBackupPath, imageExisted, imageCommitted);
            keepJsonBackup = !jsonRestored && File.Exists(jsonBackupPath);
            keepImageBackup = !imageRestored && File.Exists(imageBackupPath);
            if (!jsonRestored || !imageRestored)
            {
                throw new IOException(
                    $"Failed to write template assets and fully roll back. Check the target files; retained backups: {jsonBackupPath}, {imageBackupPath}",
                    writeException);
            }

            throw;
        }
        finally
        {
            TryDelete(jsonTempPath);
            TryDelete(imageTempPath);
            if (!keepJsonBackup)
            {
                TryDelete(jsonBackupPath);
            }

            if (!keepImageBackup)
            {
                TryDelete(imageBackupPath);
            }
        }
    }

    public static string GetImageOutputPath(string assetsRootPath, string templateFileName)
    {
        if (string.IsNullOrWhiteSpace(assetsRootPath) || string.IsNullOrWhiteSpace(templateFileName))
        {
            return string.Empty;
        }

        try
        {
            return Path.GetFullPath(Path.Combine(assetsRootPath.Trim(), FallbackResolutionFolder, templateFileName.Trim()));
        }
        catch
        {
            return string.Empty;
        }
    }

    private static JObject LoadOrCreateRoot(string jsonPath)
    {
        if (!File.Exists(jsonPath))
        {
            return new JObject
            {
                ["version"] = 1,
                ["objects"] = new JObject()
            };
        }

        var json = File.ReadAllText(jsonPath, Encoding.UTF8);
        try
        {
            return JObject.Parse(json);
        }
        catch (JsonException ex)
        {
            throw new InvalidOperationException($"Invalid Recognition.json format: {ex.Message}", ex);
        }
    }

    private static JObject GetOrCreateObjects(JObject root)
    {
        if (root["objects"] is JObject objects)
        {
            return objects;
        }

        if (root["objects"] != null)
        {
            throw new InvalidOperationException("The objects property in Recognition.json must be a JSON object.");
        }

        objects = new JObject();
        root["objects"] = objects;
        return objects;
    }

    private static IReadOnlyList<string> FindConflicts(JObject objects, string objectName, string templateFileName, string imagePath)
    {
        var conflicts = new List<string>();
        if (objects.Property(objectName, StringComparison.Ordinal) != null)
        {
            conflicts.Add($"Object configuration “{objectName}” already exists");
        }

        if (File.Exists(imagePath))
        {
            conflicts.Add($"Template image “{imagePath}” already exists");
        }

        var otherReferences = objects.Properties()
            .Where(property => !string.Equals(property.Name, objectName, StringComparison.Ordinal))
            .Where(property => property.Value is JObject objectConfig
                               && string.Equals(
                                   objectConfig["template"]?.Value<string>(),
                                   templateFileName,
                                   StringComparison.OrdinalIgnoreCase))
            .Select(property => property.Name)
            .ToList();
        if (otherReferences.Count > 0)
        {
            conflicts.Add($"The template image is also referenced by these objects: {string.Join(", ", otherReferences)}");
        }

        return conflicts;
    }

    private static JObject BuildObjectConfig(RecognitionTemplateDraft draft, string templateFileName)
    {
        var config = new JObject
        {
            ["type"] = RecognitionTypes.TemplateMatch.ToString(),
            ["template"] = templateFileName,
            ["reference"] = new JObject
            {
                ["size"] = new JArray(draft.ReferenceWidth, draft.ReferenceHeight),
                ["bbox"] = $"rect({draft.Selection.X}, {draft.Selection.Y}, {draft.Selection.Width}, {draft.Selection.Height})"
            }
        };

        if (draft.Threshold != RecognitionTemplateDraft.DefaultThreshold)
        {
            config["threshold"] = draft.Threshold;
        }

        if (draft.Use3Channels)
        {
            config["use3Channels"] = true;
        }

        if (draft.TemplateMatchMode != RecognitionTemplateDraft.DefaultTemplateMatchMode)
        {
            config["templateMatchMode"] = draft.TemplateMatchMode.ToString();
        }

        if (draft.UseMask)
        {
            config["useMask"] = true;
            var maskColor = draft.MaskColor.Trim();
            if (ColorTranslator.FromHtml(maskColor).ToArgb() != Color.FromArgb(0, 255, 0).ToArgb())
            {
                config["maskColor"] = maskColor;
            }
        }

        if (draft.DrawOnWindow)
        {
            config["draw"] = true;
        }

        if (draft.MaxMatchCount != RecognitionTemplateDraft.DefaultMaxMatchCount)
        {
            config["maxMatchCount"] = draft.MaxMatchCount;
        }

        if (draft.UseBinaryMatch)
        {
            config["useBinaryMatch"] = true;
            if (draft.BinaryThreshold != RecognitionTemplateDraft.DefaultBinaryThreshold)
            {
                config["binaryThreshold"] = draft.BinaryThreshold;
            }
        }

        var search = new JObject();
        if (draft.SearchAnchorMode != RecognitionTemplateDraft.DefaultSearchAnchorMode)
        {
            search["anchor"] = draft.SearchAnchorMode.ToString();
        }

        if (draft.ReferenceSearchBox is { } searchBox)
        {
            search["box"] = $"rect({searchBox.X}, {searchBox.Y}, {searchBox.Width}, {searchBox.Height})";
        }

        if (draft.SearchExpandPercent is { } expandPercent)
        {
            search["expandPercent"] = BuildExpandPercentArray(expandPercent);
        }
        else if (draft.SearchExpandWidth != RecognitionTemplateDraft.DefaultSearchExpand
                 || draft.SearchExpandHeight != RecognitionTemplateDraft.DefaultSearchExpand)
        {
            search["expand"] = new JArray(draft.SearchExpandWidth, draft.SearchExpandHeight);
        }

        if (search.HasValues)
        {
            config["search"] = search;
        }

        return config;
    }

    /// <summary>
    /// 按 XAML Thickness 的顺序生成最短百分比扩展数组：
    /// 四边相同输出 1 项，左右和上下分别相同输出 2 项，否则按左、上、右、下输出 4 项。
    /// </summary>
    private static JArray BuildExpandPercentArray(SearchExpandRatio ratio)
    {
        // 仅在数值确实相同时压缩参数，避免为了缩短 JSON 而丢失微小但明确配置的四边差异。
        if (ratio.Left.Equals(ratio.Top)
            && ratio.Left.Equals(ratio.Right)
            && ratio.Left.Equals(ratio.Bottom))
        {
            return new JArray(ratio.Left);
        }

        if (ratio.Left.Equals(ratio.Right) && ratio.Top.Equals(ratio.Bottom))
        {
            return new JArray(ratio.Left, ratio.Top);
        }

        return new JArray(ratio.Left, ratio.Top, ratio.Right, ratio.Bottom);
    }

    private static string NormalizeJsonPath(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Select or enter the Recognition.json file path.");
        }

        var fullPath = Path.GetFullPath(path.Trim());
        if (!string.Equals(Path.GetExtension(fullPath), ".json", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Recognition configuration files must use the .json extension.");
        }

        return fullPath;
    }

    private static string NormalizeDirectoryPath(string path, string displayName)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException($"Select or enter {displayName}.");
        }

        return Path.GetFullPath(path.Trim());
    }

    private static void ValidateObjectName(string objectName)
    {
        if (string.IsNullOrWhiteSpace(objectName))
        {
            throw new ArgumentException("Enter an object key.");
        }
    }

    private static void ValidateTemplateFileName(string templateFileName)
    {
        if (string.IsNullOrWhiteSpace(templateFileName))
        {
            throw new ArgumentException("Enter a template image filename.");
        }

        if (!string.Equals(Path.GetFileName(templateFileName), templateFileName, StringComparison.Ordinal)
            || templateFileName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            throw new ArgumentException("The template image must be a filename without directories or invalid characters.");
        }

        if (!string.Equals(Path.GetExtension(templateFileName), ".png", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Template images must use the .png extension.");
        }
    }

    private static void ValidateRecognitionParameters(RecognitionTemplateDraft draft)
    {
        ValidateSelection(draft.Selection, draft.ReferenceWidth, draft.ReferenceHeight, "Template selection");
        if (draft.Threshold is < 0 or > 1)
        {
            throw new ArgumentException("The template matching threshold must be between 0 and 1.");
        }

        if (draft.ReferenceSearchBox is { } searchBox)
        {
            ValidateSelection(searchBox, draft.ReferenceWidth, draft.ReferenceHeight, "Custom search area");
        }

        if (draft.SearchExpandPercent is { } expandPercent)
        {
            if (!expandPercent.IsValid)
            {
                throw new ArgumentException("All search expansion ratios must be finite, nonnegative numbers.");
            }
        }
        else if (draft.SearchExpandWidth < 0 || draft.SearchExpandHeight < 0)
        {
            throw new ArgumentException("Search expansion pixels cannot be negative.");
        }

        var effectiveSearchRegion = GetEffectiveSearchRegion(draft);
        if (effectiveSearchRegion.Width < draft.Selection.Width
            || effectiveSearchRegion.Height < draft.Selection.Height)
        {
            throw new ArgumentException("After expansion and clipping, the search area must contain the template selection.");
        }

        if (draft.MaxMatchCount != -1 && draft.MaxMatchCount < 1)
        {
            throw new ArgumentException("Maximum matches must be -1 or a positive integer.");
        }

        if (draft.BinaryThreshold is < 0 or > 255)
        {
            throw new ArgumentException("The binary threshold must be between 0 and 255.");
        }

        if (draft.UseMask)
        {
            if (string.IsNullOrWhiteSpace(draft.MaskColor))
            {
                throw new ArgumentException("Enter a mask color when masking is enabled.");
            }

            try
            {
                _ = ColorTranslator.FromHtml(draft.MaskColor.Trim());
            }
            catch (Exception ex)
            {
                throw new ArgumentException("The mask color must be a valid HTML color, such as #00FF00.", ex);
            }
        }
    }

    private static void ValidateSelection(Rect selection, int imageWidth, int imageHeight, string displayName = "Template selection")
    {
        if (imageWidth <= 0 || imageHeight <= 0)
        {
            throw new ArgumentException("Invalid reference canvas dimensions.");
        }

        if (selection.Width <= 0 || selection.Height <= 0)
        {
            throw new ArgumentException($"The width and height of {displayName} must be greater than 0.");
        }

        if (selection.X < 0 || selection.Y < 0
            || selection.Right > imageWidth || selection.Bottom > imageHeight)
        {
            throw new ArgumentException($"{displayName} is outside the screenshot bounds.");
        }
    }

    /// <summary>
    /// 在编辑器参考画布上计算最终搜索区域，用于保存前校验。
    /// 百分比扩展优先于像素扩展，计算规则与运行时识别保持一致。
    /// </summary>
    private static Rect GetEffectiveSearchRegion(RecognitionTemplateDraft draft)
    {
        var baseRegion = draft.ReferenceSearchBox ?? draft.Selection;
        double left;
        double top;
        double right;
        double bottom;
        if (draft.SearchExpandPercent is { } ratio)
        {
            left = draft.ReferenceWidth * ratio.Left;
            top = draft.ReferenceHeight * ratio.Top;
            right = draft.ReferenceWidth * ratio.Right;
            bottom = draft.ReferenceHeight * ratio.Bottom;
        }
        else
        {
            left = right = draft.SearchExpandWidth;
            top = bottom = draft.SearchExpandHeight;
        }

        var x1 = (int)Math.Round(Math.Clamp(baseRegion.Left - left, 0d, draft.ReferenceWidth));
        var y1 = (int)Math.Round(Math.Clamp(baseRegion.Top - top, 0d, draft.ReferenceHeight));
        var x2 = (int)Math.Round(Math.Clamp(baseRegion.Right + right, 0d, draft.ReferenceWidth));
        var y2 = (int)Math.Round(Math.Clamp(baseRegion.Bottom + bottom, 0d, draft.ReferenceHeight));
        return new Rect(x1, y1, Math.Max(0, x2 - x1), Math.Max(0, y2 - y1));
    }

    private static void EnsureChildPath(string directory, string childPath)
    {
        var directoryPrefix = directory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                              + Path.DirectorySeparatorChar;
        if (!childPath.StartsWith(directoryPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("The template image path is outside the target asset directory.");
        }
    }

    private static bool RestoreFile(string destinationPath, string backupPath, bool existed, bool committed)
    {
        if (!committed)
        {
            return true;
        }

        try
        {
            if (existed)
            {
                if (!File.Exists(backupPath))
                {
                    return false;
                }

                File.Copy(backupPath, destinationPath, true);
            }
            else if (!existed && File.Exists(destinationPath))
            {
                File.Delete(destinationPath);
            }

            return true;
        }
        catch
        {
            return false;
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // 临时文件清理失败不覆盖主要保存结果。
        }
    }
}
