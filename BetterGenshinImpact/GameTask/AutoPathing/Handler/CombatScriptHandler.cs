using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.AutoFight.Script;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using Microsoft.Extensions.Logging;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.AutoPathing.Handler;

public class CombatScriptHandler : IActionHandler
{
    public async Task RunAsync(CancellationToken ct, WaypointForTrack? waypointForTrack = null, object? config = null)
    {
        if (waypointForTrack is { CombatScript: not null })
        {
            Logger.LogInformation("Executing {Text}", "Simple combat strategy script");
            var combatScript = waypointForTrack.CombatScript;
            var combatScenes = await RunnerContext.Instance.GetCombatScenes(ct);
            if (combatScenes == null)
            {
                Logger.LogError("Party recognition was not initialized successfully");
                return;
            }

            combatScenes.BeforeTask(ct);
            await CombatScriptExecutor.ExecuteAsync(combatScript, ct, Logger, combatScenes);
        }
        else
        {
            Logger.LogError("The strategy script action_params content is empty");
        }
    }

    // private static bool IsOnlyCurrentAvatar(CombatScript combatScript)
    // {
    //     var isCurrentAvatar = false;
    //     if (combatScript.AvatarNames.Count == 1)
    //     {
    //         foreach (var avatarName in combatScript.AvatarNames)
    //         {
    //             if (avatarName == CombatScriptParser.CurrentAvatarName)
    //             {
    //                 isCurrentAvatar = true;
    //                 break;
    //             }
    //         }
    //     }
    //
    //     return isCurrentAvatar;
    // }
}
