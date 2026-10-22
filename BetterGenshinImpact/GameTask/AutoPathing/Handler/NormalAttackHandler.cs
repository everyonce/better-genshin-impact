using BetterGenshinImpact.Core.Input;
using System;
using BetterGenshinImpact.Core.Simulator.Extensions;
using Microsoft.Extensions.Logging;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using static BetterGenshinImpact.GameTask.Common.TaskControl;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;

namespace BetterGenshinImpact.GameTask.AutoPathing.Handler;

/// <summary>
/// 触发普通攻击
/// </summary>
/// <param name="runtime">本次运行使用的运行环境</param>
[Obsolete]
public class NormalAttackHandler(GameRuntime runtime) : IActionHandler
{
    /// <summary>
    /// 本次运行使用的运行环境
    /// </summary>
    private readonly GameRuntime _runtime = runtime;

    public async Task RunAsync(CancellationToken ct, WaypointForTrack? waypointForTrack = null, object? config = null)
    {
        Logger.LogInformation("Executing {Text}", "Normal Attack");
        InputHub.Foreground.SimulateAction(GIActions.NormalAttack);
        await _runtime.Delay(1000, ct);
    }
}
