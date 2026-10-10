using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using BetterGenshinImpact.GameTask.AutoSkip;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using Microsoft.Extensions.Logging;
using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.AutoPick.Assets;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using Vanara.PInvoke;
using static BetterGenshinImpact.GameTask.Common.TaskControl;
using Microsoft.Extensions.Localization;
using BetterGenshinImpact.Helpers;
using System.Globalization;

namespace BetterGenshinImpact.GameTask.Common.Job;

public class GoToAdventurersGuildTask
{
    public string Name => "前往冒险家协会领取奖励";

    private readonly int _retryTimes = 1;

    private readonly ChooseTalkOptionTask _chooseTalkOptionTask = new();

    private readonly string dailyLocalizedString;
    private readonly string catherineLocalizedString;
    private readonly string expeditionLocalizedString;

    public GoToAdventurersGuildTask()
    {
        IStringLocalizer<GoToAdventurersGuildTask> stringLocalizer = App.GetService<IStringLocalizer<GoToAdventurersGuildTask>>() ?? throw new NullReferenceException();
        CultureInfo cultureInfo = new CultureInfo(TaskContext.Instance().Config.OtherConfig.GameCultureInfoName);
        this.dailyLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "每日");
        this.catherineLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "凯瑟琳");
        this.expeditionLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "探索");
    }

    public async Task Start(string country, CancellationToken ct, string? dailyRewardPartyName = null ,bool onlyDoOnce = false)
    {
        Logger.LogInformation("→ {Name} started", Name);
        for (int i = 0; i < _retryTimes; i++)
        {
            try
            {
                // 如果有好感队伍名称，先切换到好感队伍
                if (!string.IsNullOrEmpty(dailyRewardPartyName))
                {
                    await new SwitchPartyTask().Start(dailyRewardPartyName, ct);
                }

                if (!onlyDoOnce)
                {
                    // F1领取奖励
                    await new ClaimEncounterPointsRewardsTask().Start(ct);
                }

                await DoOnce(country, ct);
                break;
            }
            catch (Exception e)
            {
                Logger.LogError("Failed while traveling to the Adventurers Guild to claim rewards: " + e.Message);
                if (i == _retryTimes - 1)
                {
                    // 通知失败
                    throw;
                }
                else
                {
                    await Delay(1000, ct);
                    Logger.LogInformation("Retrying travel to the Adventurers Guild to claim rewards");
                }
            }
        }

        Logger.LogInformation("→ {Name} finished", Name);
    }

    public async Task DoOnce(string country, CancellationToken ct)
    {
        // 1. 走到冒险家协会并对话
        await GoToAdventurersGuild(country, ct);

        // 每日
        var res = await _chooseTalkOptionTask.SingleSelectText(this.dailyLocalizedString, ct, 10, true);
        if (res == TalkOptionRes.FoundAndClick)
        {
            Logger.LogInformation("▶ {Text}", "Claim Daily Commission rewards!");
            await Delay(800, ct);
            
            // 6.2 每日提示确认
            using var ra1 = CaptureToRectArea();
            if (Bv.ClickBlackConfirmButton(ra1))
            {
                Logger.LogInformation("Confirmation prompt detected and confirmed");
            }
            
            await _chooseTalkOptionTask.SelectLastOptionUntilEnd(ct, null, 3); // 点几下
            await Bv.WaitUntilFound(ElementRecognition.Get("PaimonMenu"), ct);
            await Delay(500, ct);
            InputHub.Background.Keyboard.KeyPress(User32.VK.VK_ESCAPE);
            await new ReturnMainUiTask().Start(ct);

            // 结束后重新打开
            await Delay(1200, ct);
            using var ra = CaptureToRectArea();
            if (!Bv.FindFAndPress(ra, text: this.catherineLocalizedString))
            {
                throw new Exception("Could not find the interaction button to talk to Katheryne");
            }
        }
        else if (res == TalkOptionRes.FoundButNotOrange)
        {
            Logger.LogInformation("▶ {Text} is incomplete or already claimed", "Claim Daily Commission rewards");
        }
        else
        {
            Logger.LogWarning("▶ Option not found: {Text}", "Claim Daily Commission rewards");
        }

        // 探索
        res = await _chooseTalkOptionTask.SingleSelectText(this.expeditionLocalizedString, ct, 10, true);
        if (res == TalkOptionRes.FoundAndClick)
        {
            await Delay(500, ct);
            new OneKeyExpeditionTask().Run();
        }
        else if (res == TalkOptionRes.FoundButNotOrange)
        {
            Logger.LogInformation("▶ {Text} is incomplete or already claimed", "Expedition dispatch");
        }
        else
        {
            Logger.LogWarning("▶ Option not found: {Text}", "Expedition dispatch");
        }

        // 如果最后还在对话界面，选择最后一个选项退出
        using var talkUiCapture = CaptureToRectArea();
        if (Bv.IsInTalkUi(talkUiCapture))
        {
            await _chooseTalkOptionTask.SelectLastOptionUntilEnd(ct);
            Logger.LogInformation("Exiting the current conversation");
        }
    }

    /// <summary>
    /// 前往冒险家协会
    /// </summary>
    /// <param name="country"></param>
    /// <param name="ct"></param>
    /// <returns></returns>
    public async Task GoToAdventurersGuild(string country, CancellationToken ct)
    {
        var task = PathingTask.BuildFromFilePath(Global.Absolute(@$"GameTask\Common\Element\Assets\Json\冒险家协会_{country}.json"));
        if (task == null)
        {
            throw new Exception("Failed to load the map tracking file");
        }
        var pathingTask = new PathExecutor(ct)
        {
            PartyConfig = new PathingPartyConfig
            {
                Enabled = true,
                AutoSkipEnabled = true
            },
            EndAction = region => Bv.FindFAndPress(region, text: this.catherineLocalizedString)
        };
        await pathingTask.Pathing(task);

        await Delay(600, ct);

        const int retryTalkTimes = 3;
        for (int i = 0; i < retryTalkTimes; i++)
        {
            using var ra = CaptureToRectArea();
            if (!Bv.IsInTalkUi(ra))
            {
                InputHub.Foreground.Keyboard.KeyPress(AutoPickAssets.Get(ra, TaskContext.Instance().Config.AutoPickConfig.PickKey).PickVk);
                await Delay(500, ct);

                if (i == retryTalkTimes - 1)
                {
                    throw new Exception("Failed to talk to Katheryne");
                }
            }
        }
    }
}
