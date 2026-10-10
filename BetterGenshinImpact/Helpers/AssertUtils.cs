using System;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using Microsoft.Extensions.Logging;

namespace BetterGenshinImpact.Helpers;

public class AssertUtils
{
    public static void IsTrue(bool b, string msg)
    {
        if (!b)
        {
            throw new System.Exception(msg);
        }
    }
    
    
    /// <summary>
    /// 强制要求游戏分辨率检查
    /// 要求功能必须处于启用状态
    /// </summary>
    public static void CheckGameResolution(string msg = "")
    {
        var gameScreenSize = SystemControl.GetGameScreenRect(TaskContext.Instance().GameHandle);
        if (gameScreenSize.Width * 9 != gameScreenSize.Height * 16)
        {
            TaskControl.Logger.LogError("The game window is not 16:9. Current resolution: {Width}x{Height}. The {Msg} feature requires a 16:9 resolution.", gameScreenSize.Width, gameScreenSize.Height, msg);
            throw new Exception("The game window resolution is not 16:9");
        }
    }
}