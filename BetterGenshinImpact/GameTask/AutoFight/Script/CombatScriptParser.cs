using BetterGenshinImpact.GameTask.AutoFight.Config;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Extensions.Logging.Abstractions;

namespace BetterGenshinImpact.GameTask.AutoFight.Script;

public class CombatScriptParser
{
    public static string CurrentAvatarName = "当前角色";
    
    /// <summary>Read combat scripts without resolving application services.</summary>
    public static CombatScriptBag ReadAndParse(string path) => ReadAndParse(path, NullLogger.Instance);

    /// <summary>Read combat scripts and report parse failures through the caller-owned logger.</summary>
    public static CombatScriptBag ReadAndParse(string path, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        if (File.Exists(path))
        {
            // 防护性代码：防止 .json 策略文件被错误传入旧的 .txt 解析器
            if (path.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            {
                logger.LogError("This task does not support JSON strategies yet; use a TXT strategy");
                throw new Exception("This task does not support JSON strategies yet; use a TXT strategy");
            }

            return new CombatScriptBag(Parse(path, logger));
        }
        else if (Directory.Exists(path))
        {
            var files = Directory.GetFiles(path, "*.txt", SearchOption.AllDirectories);
            if (files.Length == 0)
            {
                logger.LogError("Combat script file not found: {Path}", path);
                throw new Exception("Combat script file not found");
            }

            var combatScripts = new List<CombatScript>();
            foreach (var file in files)
            {
                try
                {
                    combatScripts.Add(Parse(file, logger));
                }
                catch (Exception e)
                {
                    logger.LogWarning("Failed to parse combat script file: {Path}, {Msg}", file, e.Message);
                }
            }

            return new CombatScriptBag(combatScripts);
        }
        else
        {
            logger.LogError("Combat script file not found: {Path}", path);
            throw new Exception("Combat script file not found");
        }
    }

    /// <summary>Read one text script without resolving application services.</summary>
    public static CombatScript Parse(string path) => Parse(path, NullLogger.Instance);

    /// <summary>Read one text script using the caller-owned logger.</summary>
    public static CombatScript Parse(string path, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        var script = File.ReadAllText(path);
        var combatScript = ParseContext(script, logger);
        combatScript.Path = path;
        combatScript.Name = Path.GetFileNameWithoutExtension(path);
        return combatScript;
    }

    /// <summary>Parse text using a silent logger for metadata and data construction.</summary>
    public static CombatScript ParseContext(string context, bool validate = true, string? defaultAvatarName = null) => ParseContext(context, NullLogger.Instance, validate, defaultAvatarName);

    /// <summary>Parse text using the caller-owned logger; preserve validation and avatar defaults.</summary>
    public static CombatScript ParseContext(string context, ILogger logger, bool validate = true, string? defaultAvatarName = null)
    {
        ArgumentNullException.ThrowIfNull(logger);
        var lines = context.Split(["\r\n", "\r", "\n"], StringSplitOptions.RemoveEmptyEntries);
        var result = new List<string>();
        foreach (var line in lines)
        {
            var l = line.Trim()
                .Replace("（", "(")
                .Replace(")", ")")
                .Replace("，", ",");
            if (l.StartsWith("//") || l.StartsWith('#') || string.IsNullOrEmpty(l))
            {
                continue;
            }

            if (l.Contains(";"))
            {
                result.AddRange(l.Split(";", StringSplitOptions.RemoveEmptyEntries));
            }
            else
            {
                result.Add(l);
            }
        }

        return ParseLines(result, logger, validate, defaultAvatarName);
    }

    private static CombatScript ParseLines(List<string> lines, ILogger logger, bool validate = true, string? defaultAvatarName = null)
    {
        List<CombatCommand> combatCommands = [];
        HashSet<string> combatAvatarNames = [];
        foreach (var line in lines)
        {
            var oneLineCombatCommands = ParseLine(line, combatAvatarNames, logger, validate, defaultAvatarName);
            combatCommands.AddRange(oneLineCombatCommands);
        }

        var names = string.Join(",", combatAvatarNames);
        // logger.LogDebug("战斗脚本解析完成，共{Cnt}条指令，涉及角色：{Str}", combatCommands.Count, names);

        return new CombatScript(combatAvatarNames, combatCommands);
    }

    private static List<CombatCommand> ParseLine(string line, HashSet<string> combatAvatarNames, ILogger logger, bool validate = true, string? defaultAvatarName = null)
    {
        line = line.Trim();
        var oneLineCombatCommands = new List<CombatCommand>();
        // 以空格分隔角色和指令 截取第一个空格前的内容为角色名称，后面的为指令
        // 20241116更新 不输入角色名称时，直接以当前角色为准
        // 用括号嵌套深度查找角色分隔符：深度为 0 时的空格才是角色名和指令的分隔
        // 无角色前缀时（如 walk(s, 0.2)），所有空格都在括号内，separatorIndex 保持 -1
        var depth = 0;
        var separatorIndex = -1;
        for (var i = 0; i < line.Length; i++)
        {
            if (line[i] == '(') depth++;
            else if (line[i] == ')') depth--;
            else if (line[i] == ' ' && depth == 0)
            {
                separatorIndex = i;
                break;
            }
        }

        var character = defaultAvatarName ?? CurrentAvatarName;
        var commands = line;
        if (separatorIndex > 0)
        {
            character = line[..separatorIndex];
            character = DefaultAutoFightConfig.AvatarAliasToStandardName(character);
            commands = line[(separatorIndex + 1)..];
        }
        else
        {
            // 无显式前缀时，若提供了 defaultAvatarName 则对其标准化；否则走验证失败
            if (defaultAvatarName != null)
            {
                character = DefaultAutoFightConfig.AvatarAliasToStandardName(defaultAvatarName);
            }
            else if (validate)
            {
                logger.LogError("Invalid combat script format: separate the character and command with a space");
                throw new Exception("Invalid combat script format: separate the character and command with a space");
            }
        }

        oneLineCombatCommands.AddRange(ParseLineCommands(commands, character, logger));
        combatAvatarNames.Add(character);
        return oneLineCombatCommands;
    }

    /// <summary>Parse round selection without resolving application services.</summary>
    public static List<int> ParseRoundCommand(CombatCommand roundCommand) => ParseRoundCommand(roundCommand, NullLogger.Instance);

    /// <summary>Parse round selection using the caller-owned logger.</summary>
    public static List<int> ParseRoundCommand(CombatCommand roundCommand, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        // 解析round命令的入参，返回一个整数列表，代表在哪些回合执行后续指令
        // 支持Round(1)、Round(1,3,5)、Round(2-4)、Round(1,3-5)等格式
        var activatingRounds = new List<int>();
        if (roundCommand.Args == null || roundCommand.Args.Count == 0) {
            logger.LogError("round requires arguments specifying the rounds in which subsequent commands run; e.g. round(1) or round(1,3-5)");
            throw new ArgumentException("round requires arguments specifying the rounds in which subsequent commands run; e.g. round(1) or round(1,3-5)");
        }
        foreach (var arg in roundCommand.Args) {
            if (arg.Contains('-')) {
                // 范围
                var parts = arg.Split('-', StringSplitOptions.TrimEntries);
                if (parts.Length != 2) {
                    logger.LogError("Invalid round arguments; e.g. round(1-3)");
                    throw new ArgumentException("Invalid round arguments; e.g. round(1-3)");
                }
                var start = int.Parse(parts[0]);
                var end = int.Parse(parts[1]);
                if (start > end || start <= 0) {
                    logger.LogError("Invalid round arguments: the starting round must be greater than 0 and no greater than the ending round; e.g. round(1-3)");
                    throw new ArgumentException("Invalid round arguments: the starting round must be greater than 0 and no greater than the ending round; e.g. round(1-3)");
                }
                for (int i = start; i <= end; i++) {
                    activatingRounds.Add(i);
                }
            } else {
                // 单个回合
                var round = int.Parse(arg);
                if (round <= 0) {
                    logger.LogError("Invalid round arguments: the round number must be greater than 0; e.g. round(1)");
                    throw new ArgumentException("Invalid round arguments: the round number must be greater than 0; e.g. round(1)");
                }
                activatingRounds.Add(round);
            }
        }
        return activatingRounds;
    }

    /// <summary>Parse command groups without resolving application services.</summary>
    public static List<CombatCommand> ParseLineCommands(string lineWithoutAvatar, string avatarName) => ParseLineCommands(lineWithoutAvatar, avatarName, NullLogger.Instance);

    /// <summary>Parse command groups using the caller-owned logger.</summary>
    public static List<CombatCommand> ParseLineCommands(string lineWithoutAvatar, string avatarName, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        var parts = lineWithoutAvatar.Split("|", StringSplitOptions.RemoveEmptyEntries);
        var fullCombatCommands = new List<CombatCommand>();
        foreach (var part in parts)
        {
            var combatCommands = ParseLinePart(part, avatarName, logger);
            if (combatCommands.Count > 0 && combatCommands[0].Method == Method.Round) {
                // 遇到round指令，作为回合分隔符使用，不加入最终指令列表
                var roundCommand = combatCommands[0];
                var activatingRounds = ParseRoundCommand(roundCommand, logger);
                combatCommands.RemoveAt(0);
                foreach (var combatCommand in combatCommands) {
                    
                    combatCommand.ActivatingRound = activatingRounds;
                }
            }
            fullCombatCommands.AddRange(combatCommands);
        }
        // foreach (var combatCommand in fullCombatCommands)
        // {
        //     logger.LogDebug("解析战斗脚本命令：{cmd}", combatCommand.ToString());
        // }
        return fullCombatCommands;
    }

    /// <summary>Parse one command group without resolving application services.</summary>
    public static List<CombatCommand> ParseLinePart(string lineWithoutAvatar, string avatarName) => ParseLinePart(lineWithoutAvatar, avatarName, NullLogger.Instance);

    /// <summary>Parse one command group using the caller-owned logger.</summary>
    public static List<CombatCommand> ParseLinePart(string lineWithoutAvatar, string avatarName, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(logger);
        var oneLineCombatCommands = new List<CombatCommand>();
        var commandArray = lineWithoutAvatar.Split(",", StringSplitOptions.RemoveEmptyEntries);

        for (var i = 0; i < commandArray.Length; i++)
        {
            var command = commandArray[i];
            if (string.IsNullOrEmpty(command))
            {
                continue;
            }

            if (command.Contains('(') && !command.Contains(')'))
            {
                var j = i + 1;
                // 括号被逗号分隔，需要合并
                while (j < commandArray.Length)
                {
                    command += "," + commandArray[j];
                    if (command.Count("(".Contains) > 1)
                    {
                        logger.LogError("Invalid combat script format: unmatched parentheses in command {Cmd}", command);
                        throw new Exception("Invalid combat script format: unmatched parentheses in command");
                    }

                    if (command.Contains(')'))
                    {
                        i = j;
                        break;
                    }

                    j++;
                }

                if (!(command.Contains('(') && command.Contains(')')))
                {
                    logger.LogError("Invalid combat script format: incomplete parentheses in command {Cmd}", command);
                    throw new Exception("Invalid combat script format: incomplete parentheses in command");
                }
            }

            var combatCommand = new CombatCommand(avatarName, command, logger);
            oneLineCombatCommands.Add(combatCommand);
        }

        return oneLineCombatCommands;
    }
}
