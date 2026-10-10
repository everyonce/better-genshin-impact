using BetterGenshinImpact.Core.Input;
using System;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.Core.Simulator.Extensions;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.Helpers;
using Microsoft.Extensions.Localization;
using Microsoft.Extensions.Logging;
using Vanara.PInvoke;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.Common.Job;

/// <summary>
/// 领取长效历练点奖励
/// </summary>
public class ClaimEncounterPointsRewardsTask
{
    private readonly ReturnMainUiTask _returnMainUiTask = new();

    private readonly string commissionsLocalizedString;

    public ClaimEncounterPointsRewardsTask()
    {
        IStringLocalizer<ClaimEncounterPointsRewardsTask> stringLocalizer = App.GetService<IStringLocalizer<ClaimEncounterPointsRewardsTask>>() ?? throw new NullReferenceException();
        CultureInfo cultureInfo = new CultureInfo(TaskContext.Instance().Config.OtherConfig.GameCultureInfoName);
        this.commissionsLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "委托");
    }

    public async Task Start(CancellationToken ct)
    {
        try
        {
            await DoOnce(ct);
        }
        catch (Exception e)
        {
            Logger.LogDebug(e, "Failed to claim long-term encounter point rewards");
            Logger.LogError("Failed to claim long-term encounter point rewards: {Msg}", e.Message);
        }
    }

    public async Task DoOnce(CancellationToken ct)
    {
        await _returnMainUiTask.Start(ct);

        await Delay(200, ct);

        InputHub.Background.SimulateAction(GIActions.OpenAdventurerHandbook); // F1 开书

        await Delay(1000, ct);

        var assetScale = TaskContext.Instance().SystemInfo.AssetScale;

        var earlyClaim = false; // 无需点击委托直接领取
        // 找委托按钮
        var f1Success = await NewRetry.WaitForAction(() =>
        {
            using var ra = CaptureToRectArea();

            var ocrList = ra.FindMulti(RecognitionObject.Ocr(0, 0, 380 * assetScale, ra.Height));

            var wt = ocrList.FirstOrDefault(txt => Regex.IsMatch(txt.Text, this.commissionsLocalizedString));

            if (wt != null)
            {
                using var claimCapture = CaptureToRectArea();
                if (ClickClaimBtn(claimCapture))
                {
                    earlyClaim = true;
                    return true;
                }

                wt.Click();
                return true;
            }

            return false;
        }, ct, 5);

        if (!f1Success)
        {
            Logger.LogError("{F} Commission button not found; failed to open the Adventurer Handbook with F1", "Encounter points: ");
            return;
        }

        if (earlyClaim)
        {
            // 已经领取过
            await Delay(1000, ct);

            // TODO 截图并通知
            return;
        }

        await Delay(1000, ct);

        // 领取
        using var claimCapture = CaptureToRectArea();
        if (ClickClaimBtn(claimCapture))
        {
            await Delay(1000, ct);

            // TODO 截图并通知
        }

        // 关闭
        await _returnMainUiTask.Start(ct);
    }

    private static bool ClickClaimBtn(ImageRegion ra2)
    {
        var claimBtn = ra2.Find(ElementRecognition.Get("BtnClaimEncounterPointsRewards", ra2));
        if (claimBtn.IsExist())
        {
            claimBtn.Click();
            Logger.LogInformation("{F} Claim long-term encounter point rewards", "Encounter points: ");


            return true;
        }
        else
        {
            Logger.LogInformation("{F} Claim encounter point reward button not found", "Encounter points: ");
            return false;
        }
    }
}
