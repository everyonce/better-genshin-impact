using System;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;
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
    /// <param name="runtime">要检查的运行环境</param>
    /// <param name="msg">功能名称，用于日志</param>
    public static void CheckGameResolution(GameRuntime runtime, string msg = "")
    {
        var gameScreenSize = SystemControl.GetGameScreenRect(runtime.Window.Handle);
        if (gameScreenSize.Width * 9 != gameScreenSize.Height * 16)
        {
            TaskControl.Logger.LogError("The game window is not 16:9. Current resolution: {Width}x{Height}. The {Msg} feature requires a 16:9 resolution.", gameScreenSize.Width, gameScreenSize.Height, msg);
            throw new Exception("The game window resolution is not 16:9");
        }
    }
}