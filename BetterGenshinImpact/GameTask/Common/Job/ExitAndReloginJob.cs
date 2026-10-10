using BetterGenshinImpact.Core.Input;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.AutoWood.Utils;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Model.Area;
using Microsoft.Extensions.Logging;
using Vanara.PInvoke;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.Common.Job;

public class ExitAndReloginJob
{
    private readonly Login3rdParty _login3rdParty = new();

    private static RecognitionObject GetAutoWoodRecognitionObject(string objectName)
    {
        return RecognitionAssets.Get("AutoWood", objectName);
    }

    public async Task Start(CancellationToken ct)
    {
        Logger.LogInformation("Exiting to the login screen");
        SystemControl.FocusWindow(TaskContext.Instance().GameHandle);

        // 等待菜单界面出现
        await NewRetry.WaitForElementAppear(
            GetAutoWoodRecognitionObject("MenuBag"),
            () => InputHub.Foreground.Keyboard.KeyPress(User32.VK.VK_ESCAPE),
            ct,
            10,
            1200
        );

        // 点击退出按钮并等待确认弹窗出现
        await NewRetry.WaitForElementAppear(
            GetAutoWoodRecognitionObject("Confirm"),
            () => GameCaptureRegion.GameRegionClick((size, scale) => (50 * scale, size.Height - 50 * scale)),
            ct,
            5,
            800
        );

        // 点击确认退出并等待确认弹窗消失
        await NewRetry.WaitForElementDisappear(
            GetAutoWoodRecognitionObject("Confirm"),
            screen =>
            {
                // 接收当前截图作为参数
                screen.Find(RecognitionAssets.Get("AutoWood", "Confirm", screen), ra =>
                {
                    ra.Click();
                    ra.Dispose();
                });
            },
            ct,
            5,
            1000
        );
        await Delay(1000, ct);

        //============== 重新登录流程 ==============
        Logger.LogInformation("Clicking Log In");
        _login3rdParty.RefreshAvailabled();
        if (_login3rdParty is { Type: Login3rdParty.The3rdPartyType.Bilibili, IsAvailabled: true })
        {
            // await Delay(1, ct);
            Thread.Sleep(100);
            _login3rdParty.Login(ct);
            Logger.LogInformation("Bilibili server mode enabled for logout and relogin");
        }

        // 等待进入游戏按钮出现并点击
        var enterGameAppear = await NewRetry.WaitForElementAppear(
            GetAutoWoodRecognitionObject("EnterGame"),
            () => { },
            ct,
            120,
            1000
        );
        if (!enterGameAppear)
        {
            throw new RetryException("Did not detect entry into the game");
        }

        // 点击进入游戏按钮直到它消失
        var waitForEnterGameRoDisappear = await NewRetry.WaitForElementDisappear(
            GetAutoWoodRecognitionObject("EnterGame"),
            () => GameCaptureRegion.GameRegion1080PPosClick(955, 666),
            ct,
            120,
            1000
        );
        if (!waitForEnterGameRoDisappear)
        {
            throw new RetryException("The Enter Game button did not disappear; it may not have been clicked");
        }


        // 等待主界面出现
        var mainUiFound = await NewRetry.WaitForElementAppear(
            ElementRecognition.Get("PaimonMenu"),
            () => { },
            ct,
            120,
            1000
        );

        if (mainUiFound)
        {
            Logger.LogInformation("Logout and relogin complete!");
        }
        else
        {
            Logger.LogWarning("Main screen not detected; login may not have completed");
        }

        await Delay(500, ct);
    }
}
