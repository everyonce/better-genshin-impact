using BetterGenshinImpact.GameTask.AutoFight.Model;
using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using Microsoft.Extensions.Logging;
using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.AutoFight.Script;

public static class CombatScriptExecutor
{
    /// <summary>
    /// 执行简易战斗策略脚本。
    /// </summary>
    /// <param name="combatScript">已解析的策略</param>
    /// <param name="ct">取消令牌</param>
    /// <param name="logger">日志</param>
    /// <param name="combatScenes">
    /// 可选。传了则使用现成的 CombatScenes（由调用方管理生命周期）；
    /// 不传则在内部通过截图自动创建并管理生命周期。
    /// </param>
    public static async Task ExecuteAsync(
        CombatScript combatScript,
        CancellationToken ct,
        ILogger logger,
        CombatScenes? combatScenes = null)
    {
        var ownsScenes = false;
        try
        {
            if (combatScenes == null)
            {
                using var capture = CaptureToRectArea();
                combatScenes = new CombatScenes();
                ownsScenes = true;
                combatScenes.InitializeTeam(capture);
                if (!combatScenes.CheckTeamInitialized())
                {
                    logger.LogError("Party recognition was not initialized successfully");
                    return;
                }
            }

            // 仅在内部创建 CombatScenes 时设置 Avatar.Ct，外部传入时由调用方管理
            if (ownsScenes)
            {
                combatScenes.BeforeTask(ct);
            }

            // 提前校验是否存在策略要求的角色
            // 若脚本中有无前缀的命令（如 a(0.5)），解析后 AvatarNames 会包含 "当前角色" 占位符，
            // 此时跳过队伍校验是刻意设计：无前缀命令使用当前屏幕上角色，不要求特定角色在队伍中。
            if (!combatScript.AvatarNames.Contains(CombatScriptParser.CurrentAvatarName))
            {
                bool hasAvatar = combatScenes.GetAvatars().Any(avatar => combatScript.AvatarNames.Contains(avatar.Name));
                if (!hasAvatar)
                {
                    logger.LogError("The simple strategy script requires a character that is not present. The party must include one or more of these characters: {AvatarNames}", string.Join(", ", combatScript.AvatarNames));
                    return;
                }
            }

            try
            {
                // 通用化战斗策略
                for (var i = 0; i < combatScript.CombatCommands.Count; i++)
                {
                    var command = combatScript.CombatCommands[i];
                    var lastCommand = i == 0 ? command : combatScript.CombatCommands[i - 1];
                    ct.ThrowIfCancellationRequested();
                    command.Execute(combatScenes, lastCommand);
                }
            }
            catch (RetryException e)
            {
                logger.LogWarning("Retryable exception while executing simple strategy script: {Msg}; retrying...", e.Message);
                throw;
            }
            catch (Exception e)
            {
                logger.LogError(e, "Error while executing simple strategy script");
            }
        }
        finally
        {
            if (ownsScenes)
            {
                SafeDispose(combatScenes!, logger);
            }
        }
    }

    /// <summary>
    /// 安全释放 CombatScenes，异常仅记录不抛出，
    /// 避免释放异常覆盖 try 块中的原始异常。
    /// </summary>
    private static void SafeDispose(CombatScenes combatScenes, ILogger logger)
    {
        try
        {
            combatScenes.Dispose();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Exception while disposing combat scene resources");
        }
    }
}
