using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.AutoTrackPath;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.Common.Job;
using Vanara.PInvoke;
using BetterGenshinImpact.GameTask.AutoFishing;
using BetterGenshinImpact.ViewModel.Pages;
using System;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using OpenCvSharp;
using static BetterGenshinImpact.GameTask.Common.TaskControl;
using BetterGenshinImpact.GameTask.Common.Map;
using BetterGenshinImpact.GameTask.Common.Map.Maps.Base;

using BetterGenshinImpact.GameTask.Common.Exceptions;
using BetterGenshinImpact.GameTask.Common.Map.Maps;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.Helpers.Extensions;
using BetterGenshinImpact.Helpers;
using Microsoft.Extensions.Logging;
using System.Text.Json;
using System.IO;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Core.Script.Dependence;

public class Genshin
{
    private RECT captureAreaRect = TaskContext.Instance().SystemInfo.CaptureAreaRect;
    private readonly ILogger<Genshin> _logger = App.GetLogger<Genshin>();

    /// <summary>
    /// 游戏宽度
    /// </summary>
    public int Width => captureAreaRect.Width;

    /// <summary>
    /// 游戏高度
    /// </summary>
    public int Height => captureAreaRect.Height;

    /// <summary>Whether the bound game window is currently receiving foreground input.</summary>
    public bool IsGameForeground => SystemControl.IsGenshinImpactActive();

    /// <summary>Whether this BetterGI process runs in a Remote Desktop session.</summary>
    public bool IsRemoteDesktopSession => System.Windows.Forms.SystemInformation.TerminalServerSession;

    /// <summary>
    /// Read-only snapshot of the bound game window and its RDP desktop geometry, returned as JSON
    /// so scripts can parse it into a plain JavaScript object. This does not focus, resize, or capture.
    /// </summary>
    public string GetGameWindowInfo()
    {
        var handle = TaskContext.Instance().GameHandle;
        if (handle == IntPtr.Zero)
        {
            throw new InvalidOperationException("No bound game window is available.");
        }

        int? boundGameProcessId;
        using (var gameProcess = SystemControl.GetProcessByHandle(handle))
        {
            boundGameProcessId = gameProcess?.Id;
        }

        if (boundGameProcessId is null)
        {
            throw new InvalidOperationException("Could not identify the process that owns the bound game window.");
        }

        var outer = SystemControl.GetWindowRect(handle);
        if (outer.Width <= 0 || outer.Height <= 0)
        {
            throw new InvalidOperationException("Could not read the bound game window bounds.");
        }

        if (!User32.GetClientRect(handle, out var clientRect))
        {
            throw new InvalidOperationException("Could not read the bound game client rectangle.");
        }

        POINT clientOrigin = default;
        if (!User32.ClientToScreen(handle, ref clientOrigin))
        {
            throw new InvalidOperationException("Could not locate the bound game client rectangle on the desktop.");
        }

        var client = new RECT(clientOrigin.X, clientOrigin.Y,
            clientOrigin.X + clientRect.Width, clientOrigin.Y + clientRect.Height);
        var screen = System.Windows.Forms.Screen.FromHandle(handle);
        var monitor = ToRect(screen.Bounds);
        var virtualDesktop = ToRect(System.Windows.Forms.SystemInformation.VirtualScreen);
        var style = (int)User32.GetWindowLong(handle, User32.WindowLongFlags.GWL_STYLE);

        var info = new
        {
            betterGiProcessId = Environment.ProcessId,
            gameProcessId = boundGameProcessId.Value,
            windowsSessionId = WindowsSessionId,
            isRemoteDesktopSession = IsRemoteDesktopSession,
            isForeground = SystemControl.IsGenshinImpactActive(),
            isMinimized = SystemControl.IsGenshinImpactMinimized(),
            focusDiagnostics = GameWindowFocus.GetDiagnostics(handle),
            desktop = new
            {
                virtualBounds = ToSimpleBounds(virtualDesktop),
                monitorBounds = ToSimpleBounds(monitor),
                monitorDevice = screen.DeviceName
            },
            gameWindow = new
            {
                outerBounds = ToSimpleBounds(outer),
                clientBounds = ToSimpleBounds(client),
                clientWidth = client.Width,
                clientHeight = client.Height,
                hasCaption = (style & 0x00C00000) != 0,
                hasThickFrame = (style & 0x00040000) != 0,
                isPopup = (style & unchecked((int)0x80000000)) != 0,
                style
            },
            fillsDesktop = BoundsMatch(client, virtualDesktop),
            outerFillsDesktop = BoundsMatch(outer, virtualDesktop),
            fillsMonitor = BoundsMatch(client, monitor),
            outerFillsMonitor = BoundsMatch(outer, monitor)
        };

        return JsonSerializer.Serialize(info);
    }

    internal static bool BoundsMatch(RECT actual, RECT expected, int tolerance = 1) =>
        Math.Abs(actual.Left - expected.Left) <= tolerance
        && Math.Abs(actual.Top - expected.Top) <= tolerance
        && Math.Abs(actual.Right - expected.Right) <= tolerance
        && Math.Abs(actual.Bottom - expected.Bottom) <= tolerance;

    private static RECT ToRect(System.Drawing.Rectangle rectangle) =>
        new(rectangle.Left, rectangle.Top, rectangle.Right, rectangle.Bottom);

    private static object ToSimpleBounds(RECT rectangle) => new
    {
        left = rectangle.Left,
        top = rectangle.Top,
        right = rectangle.Right,
        bottom = rectangle.Bottom,
        width = rectangle.Width,
        height = rectangle.Height
    };

    /// <summary>The host BetterGI process, for local controller liveness checks.</summary>
    public int BetterGiProcessId => Environment.ProcessId;

    /// <summary>The Windows session running this script, for execution evidence.</summary>
    public int WindowsSessionId
    {
        get
        {
            using var process = System.Diagnostics.Process.GetCurrentProcess();
            return process.SessionId;
        }
    }

    /// <summary>Focuses the bound game and verifies focus before a supervised script sends input.</summary>
    public async Task FocusGame()
    {
        CancellationContext.Instance.Cts.Token.ThrowIfCancellationRequested();
        var handle = TaskContext.Instance().GameHandle;
        if (!GameWindowFocus.TryFocus(handle, out var failure))
        {
            throw new InvalidOperationException($"{failure} No scripted input was sent.");
        }
        CancellationContext.Instance.Cts.Token.ThrowIfCancellationRequested();
        await GlobalMethod.Sleep(50);
        if (!IsGameForeground) throw new InvalidOperationException("The bound game window lost foreground after activation. No scripted input was sent.");
    }

    /// <summary>
    /// 游戏窗口大小相比1080P的缩放比例
    /// </summary>
    public double ScaleTo1080PRatio { get; } = TaskContext.Instance().SystemInfo.ScaleTo1080PRatio;

    /// <summary>
    /// 系统屏幕的DPI缩放比例
    /// </summary>
    public double ScreenDpiScale => TaskContext.Instance().DpiScale;
    
    /// <summary>
    /// 通过 OCR 识别当前角色的 UID
    /// </summary>
    /// <returns>UID 数字，如果识别失败则返回 0</returns>
    public Task<int> Uid()
    {
        return Task.FromResult(Bv.Uid());
    }
    
    public Lazy<NavigationInstance> LazyNavigationInstance { get; } = new(() =>
    {
        var matchingMethod = TaskContext.Instance().Config.PathingConditionConfig.MapMatchingMethod;
        Navigation.WarmUp(matchingMethod);
        return new NavigationInstance();
    });

    /// <summary>
    /// 传送到指定位置
    /// </summary>
    /// <param name="x"></param>
    /// <param name="y"></param>
    /// <returns></returns>
    public async Task Tp(double x, double y)
    {
        await new TpTask(CancellationContext.Instance.Cts.Token).Tp(x, y);
    }

    public async Task Tp(double x, double y, string mapName, bool force)
    {
        await new TpTask(CancellationContext.Instance.Cts.Token).Tp(x, y, mapName, force);
    }

    public async Task Tp(double x, double y, bool force)
    {
        await new TpTask(CancellationContext.Instance.Cts.Token).Tp(x, y, MapTypes.Teyvat.ToString(), force);
    }

    /// <summary>
    /// 传送到指定位置
    /// </summary>
    /// <param name="x"></param>
    /// <param name="y"></param>
    /// <returns></returns>
    public async Task Tp(string x, string y)
    {
        double.TryParse(x, out var dx);
        double.TryParse(y, out var dy);
        await Tp(dx, dy);
    }

    public async Task Tp(string x, string y, bool force)
    {
        double.TryParse(x, out var dx);
        double.TryParse(y, out var dy);
        await Tp(dx, dy, force);
    }


    #region 大地图操作

    /// <summary>
    /// 移动大地图到指定坐标
    /// </summary>
    /// <remarks>
    /// 与内置传送功能不同，此方法不会多次重试。
    /// 为避免初次中心点识别失败，建议先使用 SetBigMapZoomLevel 设置合适的大地图缩放等级。
    /// </remarks>
    /// <param name="x">目标X坐标</param>
    /// <param name="y">目标Y坐标</param>
    /// <param name="forceCountry">强制指定移动大地图时先切换的国家，默认为null</param>
    public async Task MoveMapTo(double x, double y, string? forceCountry = null)
    {
        TpTask tpTask = new TpTask(CancellationContext.Instance.Cts.Token);
        await tpTask.CheckInBigMapUi();
        await tpTask.SwitchRecentlyCountryMap(x, y, forceCountry);
        await tpTask.MoveMapTo(x, y, MapTypes.Teyvat.ToString());
    }

    /// <summary>
    /// 点击大地图上的指定坐标。
    /// </summary>
    /// <remarks>
    /// 该方法会先把目标移动到大地图的可点击安全区域，再执行一次点击。
    /// </remarks>
    /// <param name="x">目标X坐标。</param>
    /// <param name="y">目标Y坐标。</param>
    /// <param name="forceCountry">强制指定移动大地图时先切换的国家，默认为null。</param>
    public async Task ClickMapPoint(double x, double y, string? forceCountry = null)
    {
        TpTask tpTask = new TpTask(CancellationContext.Instance.Cts.Token);
        await tpTask.CheckInBigMapUi();
        await tpTask.SwitchRecentlyCountryMap(x, y, forceCountry);
        await tpTask.ClickMapPoint(x, y, MapTypes.Teyvat.ToString());
    }

    /// <summary>
    /// 移动大地图到指定坐标
    /// </summary>
    /// <remarks>
    /// 与内置传送功能不同，此方法不会多次重试。
    /// 为避免初次中心点识别失败，建议先使用 SetBigMapZoomLevel 设置合适的大地图缩放等级。
    /// </remarks>
    /// <param name="x">目标X坐标</param>
    /// <param name="y">目标Y坐标</param>
    /// <param name="mapName">指定要移动的大地图</param>
    public async Task MoveIndependentMapTo(int x, int y, string mapName, string? forceCountry = null)
    {
        TpTask tpTask = new TpTask(CancellationContext.Instance.Cts.Token);
        await tpTask.CheckInBigMapUi();
        // 切换地区
        if (mapName == MapTypes.Teyvat.ToString())
        {
            // 计算传送点位置离哪张地图切换后的中心点最近，切换到该地图
            await tpTask.SwitchRecentlyCountryMap(x, y, forceCountry);
        }
        else
        {
            // 直接切换地区
            await tpTask.SwitchArea(MapTypesExtensions.ParseFromName(mapName).GetDescription());
        }
        await tpTask.MoveMapTo(x, y, mapName);
    }

    /// <summary>
    /// 获取当前大地图缩放等级
    /// </summary>
    /// <returns>当前大地图缩放等级，范围1.0-6.0</returns>
    public double GetBigMapZoomLevel()
    {
        TpTask tpTask = new(CancellationContext.Instance.Cts.Token);
        using var capture = CaptureToRectArea();
        return tpTask.GetBigMapZoomLevel(capture);
    }

    /// <summary>
    /// 将大地图缩放等级设置为指定值
    /// </summary>
    /// <remarks>
    /// 缩放等级说明：
    /// - 数值范围：1.0(最大地图) 到 6.0(最小地图)
    /// - 缩放效果：数值越大，地图显示范围越广，细节越少
    /// - 缩放位置：1.0 对应缩放条最上方，6.0 对应缩放条最下方
    /// - 推荐范围：建议在 2.0 到 5.0 之间调整，过大或过小可能影响操作
    /// </remarks>
    /// <param name="zoomLevel">目标缩放等级，范围 1.0-6.0</param>
    public async Task SetBigMapZoomLevel(double zoomLevel)
    {
        TpTask tpTask = new(CancellationContext.Instance.Cts.Token);
        double currentZoomLevel = GetBigMapZoomLevel();
        await tpTask.AdjustMapZoomLevel(currentZoomLevel, zoomLevel);
    }

    /// <summary>
    /// 传送到用户指定的七天神像
    /// </summary>
    public async Task TpToStatueOfTheSeven()
    {
        TpTask tpTask = new TpTask(CancellationContext.Instance.Cts.Token);
        await tpTask.TpToStatueOfTheSeven();
    }

    /// <summary>
    /// 获取当前在大地图上的位置坐标
    /// </summary>
    /// <returns>包含X和Y坐标的Point2f结构体</returns>
    public Point2f? GetPositionFromBigMap()
    {
        TpTask tpTask = new TpTask(CancellationContext.Instance.Cts.Token);
        return tpTask.GetPositionFromBigMap(MapTypes.Teyvat.ToString());
    }

    /// <summary>
    /// 获取当前在大地图上的位置坐标
    /// </summary>
    /// <param name="mapName">大地图名称</param>
    /// <returns>包含X和Y坐标的Point2f结构体</returns>
    public Point2f? GetPositionFromBigMap(string mapName)
    {
        TpTask tpTask = new TpTask(CancellationContext.Instance.Cts.Token);
        return tpTask.GetPositionFromBigMap(mapName);
    }

    /// <summary>
    /// 获取当前在小地图上的位置坐标
    /// </summary>
    /// <returns>包含X和Y坐标的Point2f结构体</returns>
    public Point2f? GetPositionFromMap()
    {
        return GetPositionFromMap(MapTypes.Teyvat.ToString());
    }
    
    public Point2f? GetPositionFromMapWithMatchingMethod(string matchingMethod)
    {
        return GetPositionFromMapWithMatchingMethod(nameof(MapTypes.Teyvat), matchingMethod);
    }

    public float GetCameraOrientation()
    {
        using var imageRegion = CaptureToRectArea();
        return CameraOrientation.Compute(imageRegion.SrcMat);
    }

    /// <summary>
    /// 获取当前在小地图上的位置坐标，如果缓存时间内有匹配成功的坐标优先返回缓存坐标，否则调用NavigationInstance的getPositionStable
    /// </summary>
    /// <param name="mapName">大地图名称</param>
    /// <param name="cacheTimeMs">缓存时间，单位毫秒，默认900ms</param>
    /// <returns>包含X和Y坐标的Point2f结构体</returns>
    public Point2f? GetPositionFromMap(string mapName, int cacheTimeMs = 900)
    {
        var matchingMethod = TaskContext.Instance().Config.PathingConditionConfig.MapMatchingMethod;
        return GetPositionFromMapWithMatchingMethod(mapName,matchingMethod, cacheTimeMs);
    }
    
    public Point2f? GetPositionFromMapWithMatchingMethod(string mapName, string matchingMethod, int cacheTimeMs = 900)
    {
        using var imageRegion = CaptureToRectArea();
        if (!Bv.IsInMainUi(imageRegion))
        {
            throw new InvalidOperationException("Cannot recognize minimap coordinates while not on the main screen.");
        }
        return MapManager.GetMap(mapName, matchingMethod)
            .ConvertImageCoordinatesToGenshinMapCoordinates(LazyNavigationInstance.Value
                .GetPositionStableByCache(imageRegion, mapName, matchingMethod, cacheTimeMs));
    }
    
    /// <summary>
    /// 获取当前在小地图上的位置坐标, 局部匹配, 需要世界坐标, 在坐标附近匹配, 失败不进行全局匹配
    /// </summary>
    /// <param name="mapName">大地图名称</param>
    /// <param name="x">世界坐标x</param>
    /// <param name="y">世界坐标y</param>
    /// <returns>包含X和Y坐标的Point2f结构体</returns>
    public Point2f? GetPositionFromMap(string mapName, float x, float y)
    {
        using var imageRegion = CaptureToRectArea();
        if (!Bv.IsInMainUi(imageRegion))
        {
            throw new InvalidOperationException("Cannot recognize minimap coordinates while not on the main screen.");
        }
        var matchingMethod = TaskContext.Instance().Config.PathingConditionConfig.MapMatchingMethod;
        var sceneMap = MapManager.GetMap(mapName, matchingMethod);
        var navigationInstance = LazyNavigationInstance.Value;
        var pos = sceneMap.ConvertGenshinMapCoordinatesToImageCoordinates(new Point2f(x, y));
        navigationInstance.SetPrevPosition(pos.X, pos.Y);
        return sceneMap.ConvertImageCoordinatesToGenshinMapCoordinates(navigationInstance.GetPosition(imageRegion, mapName, matchingMethod));
    }

    /// <summary>
    /// Read a fogged Teyvat minimap only near a separately verified position. A null result
    /// means the image, fog mask, or match failed verification; no global search is attempted.
    /// </summary>
    public Point2f? GetFogAwareTeyvatPosition(float expectedX, float expectedY)
    {
        if (!float.IsFinite(expectedX) || !float.IsFinite(expectedY)) return null;
        using var imageRegion = CaptureToRectArea();
        if (!Bv.IsInMainUi(imageRegion)) return null;
        var map = MapManager.GetMap(MapTypes.Teyvat, "TemplateMatch") as SceneBaseMapByTemplateMatch;
        if (map is null) return null;
        using var miniMap = new Mat(imageRegion.SrcMat, MapAssets.Get(imageRegion).MimiMapRect);
        var expectedImage = map.ConvertGenshinMapCoordinatesToImageCoordinates(new Point2f(expectedX, expectedY));
        var result = map.GetFogAwareLocalPosition(miniMap, expectedImage, "MapBack_2");
        return result == default ? null : map.ConvertImageCoordinatesToGenshinMapCoordinates(result);
    }

    /// <summary>
    /// One bounded diagnostic capture. The returned match is computed from the exact PNG
    /// written here, so offline replay can explain a rejected live position gate.
    /// </summary>
    public SceneBaseMapByTemplateMatch.FogAwareMatchDiagnostic GetFogAwareTeyvatPositionTrace(
        float expectedX, float expectedY, string traceId)
    {
        if (!float.IsFinite(expectedX) || !float.IsFinite(expectedY)
            || !Regex.IsMatch(traceId ?? "", "^[A-Za-z0-9-]{1,64}$"))
            return new() { Failure = "invalid-trace-argument" };
        using var imageRegion = CaptureToRectArea();
        if (!Bv.IsInMainUi(imageRegion)) return new() { Failure = "not-main-ui" };
        var map = MapManager.GetMap(MapTypes.Teyvat, "TemplateMatch") as SceneBaseMapByTemplateMatch;
        if (map is null) return new() { Failure = "map-unavailable" };
        var rect = MapAssets.Get(imageRegion).MimiMapRect;
        using var miniMap = new Mat(imageRegion.SrcMat, rect);
        var directory = Path.Combine(AppContext.BaseDirectory, "User", "JsScript", "ActOnePilot", "diagnostics");
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "fog-" + traceId + ".png");
        if (File.Exists(path) || Directory.GetFiles(directory, "fog-*.png").Length >= 16)
            return new() { Failure = "trace-cap-or-existing", LayerId = "MapBack_2" };
        var capturedAtUtc = DateTime.UtcNow.ToString("o");
        if (!Cv2.ImWrite(path, miniMap)) return new() { Failure = "trace-write", LayerId = "MapBack_2" };
        var expectedImage = map.ConvertGenshinMapCoordinatesToImageCoordinates(new Point2f(expectedX, expectedY));
        var diagnostic = map.GetFogAwareLocalPositionDiagnostic(miniMap, expectedImage, "MapBack_2");
        diagnostic.CropPath = path;
        diagnostic.CropX = rect.X;
        diagnostic.CropY = rect.Y;
        diagnostic.CropWidth = rect.Width;
        diagnostic.CropHeight = rect.Height;
        diagnostic.CapturedAtUtc = capturedAtUtc;
        return diagnostic;
    }

    public string GetFogAwareTeyvatPositionTraceJson(float expectedX, float expectedY, string traceId) =>
        JsonSerializer.Serialize(GetFogAwareTeyvatPositionTrace(expectedX, expectedY, traceId),
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });

    #endregion 大地图操作

    /// <summary>
    /// 切换队伍
    /// </summary>
    /// <param name="partyName">队伍界面自定义的队伍名称</param>
    /// <returns></returns>
    public async Task<bool> SwitchParty(string partyName)
    {
        try
        {
            return await new SwitchPartyTask().Start(partyName, CancellationContext.Instance.Cts.Token);
        }
        catch (PartySetupFailedException)
        {
            return false;//释放失败状态给调用方，否则失败后会退出任务。
        }
    }

    /// <summary>
    /// 按槽位重组当前队伍角色。
    /// </summary>
    /// <param name="slot1">1 号位角色名。</param>
    /// <param name="slot2">2 号位角色名。</param>
    /// <param name="slot3">3 号位角色名。</param>
    /// <param name="slot4">4 号位角色名。</param>
    /// <param name="usePhysicalSlots">是否将 slot1-slot4 解释为队伍物理槽位；false 时按当前玩家可控角色顺序解释。</param>
    /// <returns>完成保存并返回主界面返回 true；参数无效、目标角色未找到或流程失败返回 false。</returns>
    /// <remarks>
    /// 未传入的槽位默认跳过；空字符串表示跳过对应槽位。
    /// 物理槽位调用示例：<c>await genshin.SwitchCharacter("胡桃", "夜兰", "", "钟离");</c>
    /// 可控顺序调用示例：<c>await genshin.SwitchCharacter("胡桃", "夜兰", "", "", false);</c>
    /// 该方法表示重组队伍槽位角色，不是按数字键切换当前出战角色。
    /// </remarks>
    public async Task<bool> SwitchCharacter(
        string slot1 = "",
        string slot2 = "",
        string slot3 = "",
        string slot4 = "",
        bool usePhysicalSlots = true)
    {
        try
        {
            return await new SwitchCharacterStateMachineTask().Start(
                slot1,
                slot2,
                slot3,
                slot4,
                usePhysicalSlots,
                CancellationContext.Instance.Cts.Token);
        }
        catch (PartySetupFailedException ex)
        {
            _logger.LogError(ex, "Failed to switch characters: {Message}", ex.Message);
            return false;
        }
    }

    /// <summary>
    /// 清除当前调度器的队伍缓存
    /// </summary>
    public void ClearPartyCache()
    {
        RunnerContext.Instance.ClearCombatScenes();
    }


    /// <summary>
    /// 自动点击空月祝福
    /// </summary>
    /// <returns></returns>
    public async Task BlessingOfTheWelkinMoon()
    {
        await new BlessingOfTheWelkinMoonTask().Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 持续对话并选择目标选项
    /// </summary>
    /// <param name="option">选项文本</param>
    /// <param name="skipTimes">跳过次数</param>
    /// <param name="isOrange">是否为橙色选项</param>
    /// <returns></returns>
    public async Task ChooseTalkOption(string option, int skipTimes = 10, bool isOrange = false)
    {
        await new ChooseTalkOptionTask().SingleSelectText(option, CancellationContext.Instance.Cts.Token, skipTimes, isOrange);
    }

    /// <summary>
    /// 一键领取纪行奖励
    /// </summary>
    /// <returns></returns>
    public async Task ClaimBattlePassRewards()
    {
        await new ClaimBattlePassRewardsTask().Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 领取长效历练点奖励
    /// </summary>
    /// <returns></returns>
    public async Task ClaimEncounterPointsRewards()
    {
        await new ClaimEncounterPointsRewardsTask().Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 前往冒险家协会领取奖励
    /// </summary>
    /// <param name="country">国家名称</param>
    /// <returns></returns>
    public async Task GoToAdventurersGuild(string country)
    {
        await new GoToAdventurersGuildTask().Start(country, CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 前往合成台
    /// </summary>
    /// <param name="country">国家名称</param>
    /// <returns></returns>
    public async Task GoToCraftingBench(string country)
    {
        await new GoToCraftingBenchTask().GoToCraftingBench(country, CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 前往合成台合成浓缩树脂
    /// </summary>
    /// <param name="country">国家名称</param>
    /// <returns></returns>
    public async Task GoCraftResin(string country)
    {
        await new GoToCraftingBenchTask().GoCraftResin(country, CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 在当前已打开的合成界面中合成指定材料。
    /// </summary>
    /// <param name="materialName">目标成品材料名。</param>
    /// <param name="quantity">目标合成个数，必须大于 0。</param>
    /// <param name="materialType">材料筛选类型；为空时从物品模型 CSV 中读取。</param>
    /// <returns>合成执行结果。</returns>
    public async Task<CraftMaterialResult> CraftMaterial(string materialName, int quantity, string? materialType = null)
    {
        return await new CraftMaterialTask(materialName, quantity, materialType).Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 返回主界面
    /// </summary>
    /// <returns></returns>
    public async Task ReturnMainUi()
    {
        await new ReturnMainUiTask().Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 钓鱼
    /// </summary>
    /// <returns></returns>
    public async Task AutoFishing(int fishingTimePolicy = 0)
    {
        var taskSettingsPageViewModel = App.GetService<TaskSettingsPageViewModel>();
        if (taskSettingsPageViewModel == null)
        {
            throw new ArgumentNullException(nameof(taskSettingsPageViewModel), "The internal view model object is null.");
        }

        var param = AutoFishingTaskParam.BuildFromConfig(TaskContext.Instance().Config.AutoFishingConfig, taskSettingsPageViewModel.SaveScreenshotOnKeyTick);
        param.FishingTimePolicy = (FishingTimePolicy)fishingTimePolicy;
        await new AutoFishingTask(param).Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 重新登录原神
    /// </summary>
    /// <returns></returns>
    public async Task Relogin()
    {
        await new ExitAndReloginJob().Start(CancellationContext.Instance.Cts.Token);
    }
    
    /// <summary>
    /// 进出千星奇域
    /// </summary>
    /// <returns></returns>
    public async Task WonderlandCycle()
    {
        await new EnterAndExitWonderlandJob().Start(CancellationContext.Instance.Cts.Token);
    }

    /// <summary>
    /// 调整时间
    /// </summary>
    /// <param name="hour">目标小时(0-24)</param>
    /// <param name="minute">目标分钟(0-59)</param>
    /// <param name="skip">是否跳过动画（默认为否）</param>
    /// <returns></returns>
    public async Task SetTime(int hour, int minute, bool skip = false)
    {
        if ( hour < 0 || hour > 24)
            throw new ArgumentException($"Invalid hour value: {hour}. It must be an integer from 0 to 24.", nameof(hour));
        if (minute < 0 || minute > 59)
            throw new ArgumentException($"Invalid minute value: {minute}. It must be an integer from 0 to 59.", nameof(minute));
        await new SetTimeTask().Start(hour, minute, CancellationContext.Instance.Cts.Token, skip);
    }
    
    /// <summary>
    /// 调整时间
    /// </summary>
    /// <param name="hour">目标小时(0-24的字符类型)</param>
    /// <param name="minute">目标分钟(0-59的字符类型)</param>
    /// <param name="skip">是否跳过动画（默认为否）</param>
    /// <returns></returns>
    public async Task SetTime(string hour, string minute, bool skip = false)
    {
        if (!int.TryParse(hour, out var h) || h < 0 || h > 24)
            throw new ArgumentException($"Invalid hour value: {hour}. It must be an integer from 0 to 24.", nameof(hour));
        if (!int.TryParse(minute, out var m) || m < 0 || m > 59)
            throw new ArgumentException($"Invalid minute value: {minute}. It must be an integer from 0 to 59.", nameof(minute));
        await new SetTimeTask().Start(h, m, CancellationContext.Instance.Cts.Token, skip);
    }

    // /// <summary>
    // /// 莉奈娅挖矿，调试使用，暂时注释
    // /// </summary>
    // /// <param name="mineCount">射箭次数，默认1</param>
    // /// <param name="scanRounds">大循环寻矿次数。不传则默认5；传单个数字时与射箭次数相同</param>
    // public async Task StartMining(int? mineCount = null, int? scanRounds = null)
    // {
    //     var actualMine = mineCount ?? 1;
    //     var actualScan = scanRounds ?? (mineCount ?? 5);
    //     if (actualScan < actualMine) actualScan = actualMine;
    //     await new LinneaMiningTask(actualScan, actualMine).Start(CancellationContext.Instance.Cts.Token);
    // }
}
