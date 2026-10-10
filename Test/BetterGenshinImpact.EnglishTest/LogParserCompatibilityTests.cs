using Parser = BetterGenshinImpact.GameTask.LogParse.LogParse;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class LogParserCompatibilityTests
{
    [Fact]
    public void BuiltInFarmingGuideUsesEnglishCaptionsAndPreservesItsReference()
    {
        var html = BetterGenshinImpact.GameTask.LogParse.TravelsDiaryDetailManager.generHtmlMessage();
        Assert.Contains("<html lang='en'>", html);
        Assert.Contains("<h1>Farming Statistics Guide</h1>", html);
        Assert.Contains("https://www.bilibili.com/video/BV1Cr4y1e7wJ", html);
        Assert.DoesNotMatch("[\\u4e00-\\u9fff]", html);
    }

    [Theory]
    [InlineData(0, "0s")]
    [InlineData(60, "1m")]
    [InlineData(3600, "1h 0m")]
    [InlineData(3661.25, "1h 1m 1.25s")]
    public void ReportDurationsUseEnglishUnits(double seconds, string expected) =>
        Assert.Equal(expected, Parser.ConvertSecondsToTime(seconds));

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public void ChineseAndEnglishLogsProduceTheSameTaskRecords(bool english, bool javaScript)
    {
        const string groupName = "my group[1]";
        const string taskName = "custom route (test).json";
        var messages = english
            ? new[]
            {
                $"Configuration group \"{groupName}\" loaded with 1 scripts; starting execution",
                $"→ Starting {(javaScript ? "JavaScript" : "pathing task")}: \"{taskName}\"",
                "Interaction or pickup: \"薄荷\"",
                "This pathing script did not complete normally.",
                "Revival screen detected; a character has been defeated. Traveling to a Statue of The Seven to revive",
                "Teleport failed; retrying 2 times",
                "Combat ended due to timeout",
                "This route has become stuck three times. Retrying it once or abandoning it",
                "Possibly stuck; attempting to get free...",
                "An error occurred while executing the script: \"example error\"",
                $"→ Script finished: \"{taskName}\", elapsed: 1 min 2.000 sec",
                $"Configuration group \"{groupName}\" finished"
            }
            : new[]
            {
                $"配置组 \"{groupName}\" 加载完成，共1个脚本，开始执行",
                $"→ 开始执行{(javaScript ? "JS脚本" : "地图追踪任务")}: \"{taskName}\"",
                "交互或拾取：\"薄荷\"",
                "此追踪脚本未正常走完！",
                "检测到复苏界面，存在角色被击败，前往七天神像复活",
                "传送失败，重试 2 次",
                "战斗超时结束",
                "此路线出现3次卡死，重试一次路线或放弃此路线！",
                "疑似卡死，尝试脱离...",
                "执行脚本时发生异常: \"example error\"",
                $"→ 脚本执行结束: \"{taskName}\", 耗时: 1分2.000秒",
                $"配置组 \"{groupName}\" 执行结束"
            };
        var lines = new List<(string, string)>();
        for (var i = 0; i < messages.Length; i++)
        {
            lines.Add(($"[12:00:{i:00}.000] [INF] [Primary:S1:P2:T3] Source", "2026-10-10"));
            lines.Add((messages[i], "2026-10-10"));
        }

        var group = Assert.Single(Parser.Parse(lines));
        Assert.Equal(groupName, group.Name);
        Assert.Equal(new DateTime(2026, 10, 10, 12, 0, 0), group.StartDate);
        Assert.Equal(new DateTime(2026, 10, 10, 12, 0, 11), group.EndDate);
        var task = Assert.Single(group.ConfigTaskList);
        Assert.Equal(taskName, task.Name);
        Assert.Equal(new DateTime(2026, 10, 10, 12, 0, 1), task.StartDate);
        Assert.Equal(new DateTime(2026, 10, 10, 12, 0, 10), task.EndDate);
        Assert.Equal(1, task.Picks["薄荷"]);
        Assert.False(task.Fault.PathingSuccessEnd);
        Assert.Equal(1, task.Fault.ReviveCount);
        Assert.Equal(2, task.Fault.TeleportFailCount);
        Assert.Equal(1, task.Fault.BattleTimeoutCount);
        Assert.Equal(1, task.Fault.RetryCount);
        Assert.Equal(1, task.Fault.StuckCount);
        Assert.Equal(1, task.Fault.ErrCount);
    }
}
