using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace BetterGenshinImpact.GameTask.AutoFight.Script;

/// <summary>
/// JSON 战斗策略解析器
/// </summary>
public static class JsonCombatStrategyParser
{
    /// <summary>
    /// 从文件解析 JSON 战斗策略
    /// </summary>
    /// <param name="path">策略文件路径</param>
    /// <returns>解析后的战斗策略</returns>
    /// <exception cref="FileNotFoundException">文件不存在</exception>
    /// <exception cref="InvalidOperationException">解析失败或格式错误</exception>
    public static JsonCombatStrategy ParseFile(string path) => ParseFile(path, NullLogger.Instance);

    /// <summary>Parse a JSON file with the caller-owned logger; metadata callers use the silent overload.</summary>
    public static JsonCombatStrategy ParseFile(string path, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        if (!File.Exists(path))
        {
            logger.LogError("JSON combat strategy file not found: {Path}", path);
            throw new FileNotFoundException("JSON combat strategy file not found", path);
        }

        var json = File.ReadAllText(path);
        return Parse(json, logger);
    }

    /// <summary>
    /// 从 JSON 字符串解析战斗策略
    /// </summary>
    /// <param name="json">JSON 字符串</param>
    /// <returns>解析后的战斗策略</returns>
    /// <exception cref="InvalidOperationException">解析失败或格式错误</exception>
    public static JsonCombatStrategy Parse(string json) => Parse(json, NullLogger.Instance);

    /// <summary>Parse JSON with the caller-owned logger without resolving application services.</summary>
    public static JsonCombatStrategy Parse(string json, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        JsonCombatStrategy? strategy;
        try
        {
            strategy = JsonConvert.DeserializeObject<JsonCombatStrategy>(json);
        }
        catch (JsonException ex)
        {
            logger.LogError("Failed to parse JSON combat strategy: {Msg}", ex.Message);
            throw new InvalidOperationException($"Invalid JSON combat strategy format: {ex.Message}", ex);
        }

        if (strategy == null)
        {
            logger.LogError("JSON combat strategy deserialized to null");
            throw new InvalidOperationException("Failed to deserialize JSON combat strategy");
        }

        if (strategy.Info == null)
        {
            logger.LogError("JSON combat strategy is missing the Info node");
            throw new InvalidOperationException("JSON combat strategy is missing the Info node");
        }

        if (strategy.Actions == null || strategy.Actions.Count == 0)
        {
            logger.LogError("JSON combat strategy is missing the Actions node or has no actions");
            throw new InvalidOperationException("No actions are defined in the JSON combat strategy");
        }

        // 校验动作合法性（名称需能作为条件标识符解析；index 允许重复）
        ValidateActions(strategy.Actions, logger);

        logger.LogInformation("Loaded JSON combat strategy: {Name}, {Count} actions",
            strategy.Info.Name, strategy.Actions.Count);

        return strategy;
    }

    /// <summary>
    /// 校验动作名称合法性。
    /// 动作名必须能作为条件表达式中的单个标识符解析（复用 <see cref="ConditionEvaluator.IsValidActionName"/>：
    /// 不能是布尔字面量 true/false、纯数字，不能含空白、逗号、运算符等，也不能与内置条件函数同名）。
    /// 允许不同动作使用相同 index（since/count 等按 index 查询时取最近一次执行的事件记录）。
    /// </summary>
    private static void ValidateActions(List<JsonAction> actions, ILogger logger)
    {
        var actionNames = actions.Where(a => !string.IsNullOrEmpty(a.Name)).Select(a => a.Name).ToList();
        foreach (var action in actions)
        {
            if (!string.IsNullOrEmpty(action.Name) && !ConditionEvaluator.IsValidActionName(action.Name, actionNames))
            {
                logger.LogError("Action name in JSON combat strategy cannot be parsed as a condition identifier (must not be a boolean literal, number, contain whitespace, commas, operators, etc., or match a built-in condition function): {Name}", action.Name);
                throw new InvalidOperationException($"Action name in JSON combat strategy cannot be parsed as a condition identifier: {action.Name}");
            }
        }
    }
}
