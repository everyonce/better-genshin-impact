using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.Common;
using Microsoft.Extensions.Logging;
using System;
using static BetterGenshinImpact.GameTask.Common.TaskControl;
using static Vanara.PInvoke.User32;

namespace BetterGenshinImpact.GameTask.AutoSkip;

public class OneKeyExpeditionTask
{
    public void Run()
    {
        try
        {
            SystemControl.ActivateWindow();

            for (int i = 0; i < 2; i++)
            {
                // 1.全部领取
                var region = CaptureToRectArea(true);
                // Cv2.ImWrite($"log/ts.png", region.SrcMat);
                var ra = region.Find(RecognitionAssets.Get("AutoSkip", "Collect", region.Width, region.Height));
                if (!ra.IsEmpty())
                {
                    ra.Click();
                    Logger.LogInformation("Expeditions: {Text}", "Claim all");
                    Sleep(1100);
                    // 2.重新派遣
                    NewRetry.Do(() =>
                    {
                        Sleep(1);
                        region = CaptureToRectArea(true);
                        var ra2 = region.Find(RecognitionAssets.Get("AutoSkip", "Re", region.Width, region.Height));
                        if (ra2.IsEmpty())
                        {
                            throw new RetryException("No popup menu detected");
                        }
                        else
                        {
                            ra2.Click();
                            Logger.LogInformation("Expeditions: {Text}", "Dispatch again");
                        }
                    }, TimeSpan.FromSeconds(1), 3);

                    // 3.退出派遣页面 ESC
                    Sleep(500);
                    InputHub.Foreground.Keyboard.KeyPress(VK.VK_ESCAPE);
                    Logger.LogInformation("Expeditions: {Text}", "Completed");
                    break;
                }
                else
                {
                    Logger.LogInformation("Expeditions: {Text}", "Could not find the Claim button");
                    if (i == 0)
                    {
                        Logger.LogInformation("Expeditions: {Text}", "Retrying in 1 second");
                        Sleep(1000);
                    }
                    continue;
                }
            }
        }
        catch (Exception e)
        {
            Logger.LogInformation(e.Message);
        }
        finally
        {
            TaskContext.Instance().Runtime?.MaskWindowDrawingBoard.ClearAll();
        }
    }
}
