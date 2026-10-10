using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.Common;
using Microsoft.Extensions.Logging;

namespace BetterGenshinImpact.GameTask.AutoGeniusInvokation;

public class AutoGeniusInvokationTask(GeniusInvokationTaskParam taskParam) : ISoloTask
{
    public string Name => "自动七圣召唤";

    public Task Start(CancellationToken ct)
    {
        try
        {
            // 读取策略信息
            var duel = ScriptParser.Parse(taskParam.StrategyContent);
            duel.Run(ct);
        }
        catch (System.Exception e)
        {
            TaskControl.Logger.LogDebug(e, "Automatic Genius Invokation task error");
            TaskControl.Logger.LogError("Automatic Genius Invokation task error: {Exception}", e.Message);
        }
        return Task.CompletedTask;
    }
}
