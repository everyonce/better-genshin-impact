using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Recognition.OCR;
using BetterGenshinImpact.Core.Recognition.ONNX;
using BetterGenshinImpact.Core.Simulator.Extensions;
using BetterGenshinImpact.GameTask.AutoDomain.TrainingGuide;
using BetterGenshinImpact.GameTask.AutoFight.Assets;
using BetterGenshinImpact.GameTask.AutoFight.Model;
using BetterGenshinImpact.GameTask.AutoFight.Script;
using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.AutoPick.Assets;
using BetterGenshinImpact.GameTask.Common.Map;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.Notification;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.Core.Mask;
using Microsoft.Extensions.Logging;
using OpenCvSharp;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoTrackPath;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Common.Job;
using BetterGenshinImpact.Service.Notification.Model.Enum;
using static BetterGenshinImpact.GameTask.Common.TaskControl;
using static Vanara.PInvoke.Kernel32;
using static Vanara.PInvoke.User32;
using Microsoft.Extensions.Localization;
using System.Globalization;
using System.Text.RegularExpressions;
using BetterGenshinImpact.GameTask.AutoArtifactSalvage;
using System.Collections.ObjectModel;
using BetterGenshinImpact.Core.Script.Dependence;
using BetterGenshinImpact.GameTask.AutoDomain.Model;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Common.Reward;
using Compunet.YoloSharp;
using Microsoft.Extensions.DependencyInjection;
using BetterGenshinImpact.GameTask.AutoCombo;
using BetterGenshinImpact.GameTask.AutoCombo.ComboBuild;
using BetterGenshinImpact.GameTask.AutoCombo.ComboRun;
using BetterGenshinImpact.GameTask.AutoFight;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.GameTask.SoloTask;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.View.Pages.SoloTaskSettings;
using BetterGenshinImpact.ViewModel.SoloTaskSettings;

namespace BetterGenshinImpact.GameTask.AutoDomain;

/// <summary>
/// 自动秘境独立任务：传送并进入秘境，循环执行战斗、寻找石化古树、领取奖励，结束后可选分解圣遗物。
/// 业务设置全部来自 <see cref="AutoDomainParam"/>，结果附带本次识别到的奖励汇总。
/// </summary>
[SoloTaskInfo(TaskId, "自动秘境", Group = "树脂与战斗", Order = 210, OneDragonOrder = 3)]
[SoloTaskSettingsView(typeof(AutoDomainSettingsView), typeof(AutoDomainSettingsViewModel))]
public partial class AutoDomainTask : ISoloTask<AutoDomainParam, RewardSummary>
{
    /// <summary>
    /// 任务稳定标识。
    /// </summary>
    public const string TaskId = "auto_domain";

    /// <summary>
    /// 原因码：领取奖励后长时间未检测到秘境结束（通常是背包物品已满）。
    /// </summary>
    public const string DomainEndNotDetectedReason = "domain_end_not_detected";

    /// <summary>
    /// 本次运行使用的运行环境
    /// </summary>
    private readonly GameRuntime _runtime;

    /// <summary>
    /// 配置根，由创建方传入。只用于读取非本任务的全局设置（按键、拾取键、连招构建等），秘境业务设置来自 <see cref="_taskParam"/>
    /// </summary>
    private readonly AllConfig _allConfig;

    /// <summary>
    /// 配置根。静态方法没有创建方可以传参，暂时读配置根（见 task-context-removal.md 第 5 节）
    /// </summary>
    private static AllConfig Config => ConfigService.Config!;

    /// <summary>
    /// 本次运行的任务参数，在 <see cref="RunAsync"/> 开头赋值
    /// </summary>
    private AutoDomainParam _taskParam = null!;

    private BgiYoloPredictor _predictor = null!;

    /// <summary>
    /// TXT 战斗策略解析结果；使用 JSON 或自动连招策略时为 null
    /// </summary>
    private CombatScriptBag? _combatScriptBag;

    /// <summary>
    /// JSON 战斗策略文件路径；不是 JSON 策略时为 null
    /// </summary>
    private string? _jsonCombatStrategyPath;

    /// <summary>策略为自动连招（LLM 行为树）时为 true：进本前调用 LLM 建树，循环战斗中 Tick 该树</summary>
    private bool _useComboStrategy;

    /// <summary>建树任务：未配置 PartyName 时进本前启动、与传送进本并行；配置了 PartyName 时为 null，进本后切队再启动</summary>
    private Task<ComboTreeSession>? _comboBuildTask;

    /// <summary>后台建树的取消源：链接主令牌，秘境流程结束时取消，避免宿主异常退出后建树白跑</summary>
    private CancellationTokenSource? _comboBuildCts;
    private readonly Dictionary<string, int> _rewardSummary = new();

    private CancellationToken _ct;

    private ObservableCollection<OneDragonFlowConfig> ConfigList = [];

    private readonly string challengeCompletedLocalizedString;
    private readonly string autoLeavingLocalizedString;
    private readonly string skipLocalizedString;
    private readonly string leyLineDisorderLocalizedString;
    private readonly string clickanywheretocloseLocalizedString;
    private readonly string matchingChallengeString;
    private readonly string rapidformationString;
    private readonly string limitedFullyString;
    private readonly string limitedFullyAllString;
    private readonly string singlePlayerChallengeString;
    private readonly string startChallengeString;
    private readonly string retryDomainPromptPattern;
    private readonly string petrifiedTreeString;
    private readonly string insufficientCountString;
    private readonly string replenishResinString;
    private readonly string cancelButtonString;

    /// <summary>
    /// 指定树脂使用次数时的树脂使用记录，在 <see cref="Initialize"/> 中按参数建立
    /// </summary>
    private List<ResinUseRecord> _resinPriorityListWhenSpecifyUse = [];

    /// <summary>创建秘境任务。业务参数在 <see cref="RunAsync"/> 中传入，这里只做与参数无关的本地化初始化。</summary>
    /// <param name="runtime">本次运行使用的运行环境</param>
    /// <param name="config">配置根</param>
    public AutoDomainTask(GameRuntime runtime, AllConfig config)
    {
        _runtime = runtime;
        _allConfig = config;

        IStringLocalizer<AutoDomainTask> stringLocalizer =
            App.GetService<IStringLocalizer<AutoDomainTask>>() ?? throw new NullReferenceException();
        CultureInfo cultureInfo = new CultureInfo(config.OtherConfig.GameCultureInfoName);
        this.challengeCompletedLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "挑战达成");
        this.autoLeavingLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "自动退出");
        this.skipLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "Skip");
        this.leyLineDisorderLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "地脉异常");
        this.clickanywheretocloseLocalizedString = stringLocalizer.WithCultureGet(cultureInfo, "点击任意位置关闭");
        this.matchingChallengeString = stringLocalizer.WithCultureGet(cultureInfo, "匹配挑战");
        this.rapidformationString = stringLocalizer.WithCultureGet(cultureInfo, "快速编队");
        this.limitedFullyString = stringLocalizer.WithCultureGet(cultureInfo, "限时全部开放");
        this.limitedFullyAllString = stringLocalizer.WithCultureGet(cultureInfo, "限时开放");
        this.singlePlayerChallengeString = stringLocalizer.WithCultureGet(cultureInfo, "单人挑战");
        this.startChallengeString = stringLocalizer.WithCultureGet(cultureInfo, "开始挑战");
        this.retryDomainPromptPattern = stringLocalizer.WithCultureGet(cultureInfo, "是否仍要.*挑战.*秘境");
        this.petrifiedTreeString = stringLocalizer.WithCultureGet(cultureInfo, "石化古树");
        this.insufficientCountString = stringLocalizer.WithCultureGet(cultureInfo, "数量不足");
        this.replenishResinString = stringLocalizer.WithCultureGet(cultureInfo, "补充原粹树脂");
        this.cancelButtonString = stringLocalizer.WithCultureGet(cultureInfo, "取消");
    }

    /// <summary>
    /// 解析"使用"按键的本地化匹配串。独立于实例字段，因为 <see cref="PressUseResin(GameRuntime, List{Region}, string, string)"/>
    /// 是 static 的，且被 AutoLeyLineOutcropTask/AutoStygianOnslaughtTask 等其他任务类共享调用。
    /// </summary>
    private static string ResolveUseButtonPattern()
    {
        IStringLocalizer<AutoDomainTask> stringLocalizer =
            App.GetService<IStringLocalizer<AutoDomainTask>>() ?? throw new NullReferenceException();
        CultureInfo cultureInfo = new CultureInfo(Config.OtherConfig.GameCultureInfoName);
        return stringLocalizer.WithCultureGet(cultureInfo, "使用");
    }

    /// <summary>
    /// 解析树脂名称的本地化匹配串，同一个 idiom 用于 <see cref="PressUseResin(GameRuntime, List{Region}, string, string)"/>。
    /// <paramref name="resinName"/> 是内部使用的中文 key（20/40 原粹树脂已在调用前折叠为"原粹树脂"）；
    /// 若资源里没有对应条目（如 zh-Hans，或调用方已经传入本地化后的值），本地化器会原样回退返回入参本身，
    /// 因此对已本地化的调用方（future PR-B）是无操作的、向后兼容的。
    /// </summary>
    private static string ResolveResinNamePattern(string resinName)
    {
        IStringLocalizer<AutoDomainTask> stringLocalizer =
            App.GetService<IStringLocalizer<AutoDomainTask>>() ?? throw new NullReferenceException();
        CultureInfo cultureInfo = new CultureInfo(Config.OtherConfig.GameCultureInfoName);
        return stringLocalizer.WithCultureGet(cultureInfo, resinName);
    }

    private RecognitionObject GetConfirmRa(params string[] targetText)
    {
        using var screenArea = _runtime.CaptureToRectArea();
        var x = (int)(screenArea.Width * 0.5);
        var y = (int)(screenArea.Height * 0.5);
        var width = (int)(screenArea.Width * 0.5);
        var height = (int)(screenArea.Height * 0.5);
        return RecognitionObject.OcrMatch(x, y, width, height, targetText);
    }

    /// <summary>
    /// 按 1080P 坐标移动鼠标并左键单击。与原 GlobalMethod.Click 在默认 1920x1080 脚本尺寸下的行为一致，
    /// 但直接使用本运行环境换算坐标，不依赖脚本宿主 GlobalMethod 的静态分辨率设置
    /// </summary>
    /// <param name="x">1080P 下的横坐标</param>
    /// <param name="y">1080P 下的纵坐标</param>
    private void Click1080P(double x, double y)
    {
        _runtime.GameRegion1080PPosMove(x, y);
        InputHub.Foreground.Mouse.LeftButtonDown().Sleep(60).LeftButtonUp();
    }

    /// <summary>
    /// 按本次参数完成依赖参数的初始化：解析战斗策略、校验秘境与指定树脂配置、建立树脂使用记录。
    /// </summary>
    /// <param name="param">本次运行的任务参数</param>
    /// <returns>参数不满足业务要求时返回失败结果；初始化成功返回 null</returns>
    private SoloTaskResult? Initialize(AutoDomainParam param)
    {
        _useComboStrategy = false;
        _jsonCombatStrategyPath = null;
        _combatScriptBag = null;
        _comboBuildTask = null;
        _guideDomainName = null;

        // 1. 解析战斗策略路径：JS、旧入口传入的是已存在的路径；任务计划保存的可能是策略名，需要先解析
        var strategyPath = param.CombatStrategyPath;
        if (!System.IO.File.Exists(strategyPath) && !System.IO.Directory.Exists(strategyPath))
        {
            if (!CombatStrategyResolver.TryResolve(strategyPath, out var resolvedPath))
            {
                return SoloTaskResult.Failed(SoloTaskReasons.StrategyNotFound, $"战斗策略不存在：{strategyPath}");
            }

            strategyPath = resolvedPath;
        }

        // 2. 选择了具体秘境时必须能找到传送点。未选择秘境（站在秘境门口直接开始）与“根据提升指南选择秘境”保持原有流程
        if (!string.IsNullOrEmpty(param.DomainName)
            && param.DomainName != DevelopmentGuideOption
            && !MapLazyAssets.Get().DomainPositionMap.ContainsKey(param.DomainName))
        {
            return SoloTaskResult.Failed(SoloTaskReasons.InvalidParameter, $"未找到对应的秘境{param.DomainName}的传送点。");
        }

        // 3. 指定树脂使用次数时至少要配置一种树脂的次数，否则后续无法刷取
        if (param.SpecifyResinUse && !HasAnySpecifiedResinUseCount(param))
        {
            return SoloTaskResult.Failed(SoloTaskReasons.InvalidParameter, "你选择了指定树脂刷取次数，请至少配置一种树脂的刷取次数！");
        }

        // 4. 按策略类型选择战斗引擎：自动连招 / JSON / TXT
        if (AutoFightParam.ComboStrategyName.Equals(strategyPath))
        {
            _useComboStrategy = true;
            Logger.LogInformation("自动秘境：检测到自动连招策略，将使用LLM行为树");
        }
        else if (strategyPath.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
        {
            _jsonCombatStrategyPath = strategyPath;
            Logger.LogInformation("自动秘境：检测到JSON策略文件，将使用JSON战斗引擎");
        }
        else
        {
            _combatScriptBag = CombatScriptParser.ReadAndParse(strategyPath);
        }

        // 5. 建立指定树脂使用记录（未指定时为空列表）
        _resinPriorityListWhenSpecifyUse = ResinUseRecord.BuildFromDomainParam(param);
        return null;
    }

    /// <summary>
    /// 判断指定树脂使用模式下是否至少配置了一种树脂的刷取次数，条件与 <see cref="ResinUseRecord.BuildFromDomainParam(AutoDomainParam)"/> 一致。
    /// </summary>
    /// <param name="param">本次运行的任务参数</param>
    /// <returns>至少一种树脂次数大于 0 时返回 true</returns>
    private static bool HasAnySpecifiedResinUseCount(AutoDomainParam param)
    {
        return param.CondensedResinUseCount > 0
               || param.OriginalResin40UseCount > 0
               || param.OriginalResin20UseCount > 0
               || param.OriginalResinUseCount > 0
               || param.TransientResinUseCount > 0
               || param.FragileResinUseCount > 0;
    }

    /// <summary>
    /// 运行自动秘境。参数无效或策略不存在时返回失败结果；秘境流程正常结束返回未确认结果并附带奖励汇总；取消时抛出 OperationCanceledException。
    /// </summary>
    /// <param name="param">本次运行的任务参数</param>
    /// <param name="ct">本次运行的取消令牌</param>
    /// <returns>任务结果，数据为本次识别到的奖励汇总</returns>
    public async Task<SoloTaskResult<RewardSummary>> RunAsync(AutoDomainParam param, CancellationToken ct)
    {
        _taskParam = param;
        _ct = ct;
        _rewardSummary.Clear();
        // Training targets belong to this run, never to a previous task instance.
        _guideCustomTargets = TrainingGuide.TrainingGuideCustomTargets.Parse(param.TrainingTargetsJson);

        // 依赖参数的初始化（原构造函数中的策略解析、树脂记录等）
        var initFailure = Initialize(param);
        if (initFailure != null)
        {
            Logger.LogError("自动秘境：{Msg}", initFailure.Message);
            return initFailure;
        }

        using var predictor = App.ServiceProvider.GetRequiredService<BgiOnnxFactory>().CreateYoloPredictor(BgiOnnxModel.BgiTree);
        _predictor = predictor;
        _guidePlanning = _guideCustomTargets != null ||
            (_taskParam.DomainName == TrainingGuideOption && _taskParam.TrainingGuideCalculateRunsEnabled);
        using var diagnostics = TrainingGuideDiagnostics.Begin(_guidePlanning && _taskParam.TrainingGuideDiagnosticsEnabled, Logger);
        if (TrainingGuideDiagnostics.Enabled)
        {
            Logger.LogInformation("培养计划详细判断保存至 {Path}，按日期统一记录", TrainingGuideDiagnostics.DirectoryPath);
            TrainingGuideDiagnostics.Detail("培养任务开始：{StartedAt:O}", DateTime.Now);
        }
        ResetTrainingGuideState();

        Init();
        CheckGuideRewardResolution();

        // 自动吃药只在本次秘境期间启用，返回（含异常）时撤销
        using var autoEatLease = _taskParam.AutoEat ? TaskTriggerDispatcher.Instance().AddTrigger("AutoEat") : null;

            Notify.Event(NotificationEvent.DomainStart).Success(I18nService.Instance.Translate("自动秘境启动"));

        // 自动连招：秘境外识别队伍后启动 LLM 后台建树，
        // 建树与传送进本并行，战斗启动前在 StartComboFight 中等待其完成；
        // 建树令牌链接主令牌，秘境流程结束（含异常退出）时在 finally 中取消
        if (_useComboStrategy)
        {
            if (string.IsNullOrEmpty(_taskParam.PartyName))
            {
                var avatars = await AutoComboBuildTask.EnsureMainUiAndRecognizeTeamAsync(_runtime, _allConfig, Logger, ct);
                Logger.LogInformation("自动秘境：识别队伍：{Avatars}，后台启动 LLM 建树", string.Join("、", avatars.Select(a => a.Name)));

                var config = _allConfig.AutoComboBuildConfig;
                _comboBuildCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                _comboBuildTask = AutoComboBuildTask.BuildComboTreeAsync(avatars, config, Logger, _comboBuildCts.Token);
            }
        }

        try
        {
            // 复活重试
            for (var i = 0; i < _taskParam.ReviveRetryCount; i++)
            {
                try
                {
                    if (_guidePlanning) await RunTrainingGuidePlan();
                    else await DoDomain();
                    // 其他场景不重试
                    break;
                }
                catch (RetryException e)
                {
                    // 只有选择了秘境的时候才会重试
                    if (!string.IsNullOrEmpty(_taskParam.DomainName))
                    {
                        var msg = e.Message;
                        if (msg.Contains("复活"))
                        {
                            msg = "存在角色死亡，复活后重试秘境...";
                        }

                        Logger.LogWarning("Auto domain: {Text}", msg);
                        await _runtime.Delay(2000, ct);
                        Notify.Event(NotificationEvent.DomainRetry).Error(msg);
                        continue;
                    }

                    throw;
                }
            }


            await _runtime.Delay(2000, ct);
            await Bv.WaitForMainUi(_runtime, _ct, 30);
            await _runtime.Delay(2000, ct);

            await ArtifactSalvage();
            Notify.Event(NotificationEvent.DomainEnd).Success("自动秘境结束");
            // 没有确认奖励已到账的手段，按未确认结束返回，并附带本次识别到的奖励汇总
            return SoloTaskResult.Unverified(RewardSummary.From(_rewardSummary), "秘境流程已结束。");
        }
        finally
        {
            // 正常结束时建树任务早已完成（已在按 F 前 await），取消是空操作；异常退出时立即掐断后台 LLM 请求
            if (_comboBuildCts != null)
            {
                await _comboBuildCts.CancelAsync();
                _comboBuildCts.Dispose();
                _comboBuildCts = null;
            }
        }
    }

    private async Task DoDomain()
    {
        // 传送到秘境
        await TpDomain();
        // 切换队伍
        // await SwitchParty(_taskParam.PartyName);

        // 前置进入秘境
        await EnterDomain();

        var combatScenes = new CombatScenes(_runtime, _allConfig);
        for (var i = 0; i < _taskParam.DomainRoundNum; i++)
        {
            // 0. 关闭秘境提示
            Logger.LogDebug("0. Close the domain prompt");
            await CloseDomainTip();

            if (_useComboStrategy)
            {
                ESkillCdTracker.Clear();
                // 自动连招策略：战斗引擎内部初始化队伍，无需TXTSpecific步骤

                // PartyName 非空：切队发生在 EnterDomain 的秘境挑战页，
                // 此时再根据切换后的实际战斗队伍进行构建
                if (_comboBuildTask == null)
                {
                    var avatars = await AutoComboBuildTask.EnsureMainUiAndRecognizeTeamAsync(_runtime, _allConfig, Logger, _ct);
                    Logger.LogInformation("自动秘境：识别队伍：{Avatars}，启动 LLM 建树", string.Join("、", avatars.Select(a => a.Name)));

                    var config = _allConfig.AutoComboBuildConfig;
                    _comboBuildCts = CancellationTokenSource.CreateLinkedTokenSource(_ct);
                    _comboBuildTask = AutoComboBuildTask.BuildComboTreeAsync(avatars, config, Logger, _comboBuildCts!.Token);
                }

                if (!_comboBuildTask.IsCompleted)
                {
                    Logger.LogInformation("Auto domain: {Text}", "0. Wait for LLM tree generation to finish");
                }
                await _comboBuildTask; // 建树失败在此抛出快速结束任务，结果由 StartComboFight 内再次 await 获取

                // 1. 走到钥匙处启动
                Logger.LogInformation("Auto domain: {Text}", "1. Walk to the key to start");
                await WalkToPressF();

                // 2. 执行战斗（LLM行为树）
                Logger.LogInformation("Auto domain: {Text}", "2. Run the combat strategy (auto combo)");
                await StartComboFight();
            }
            else if (_jsonCombatStrategyPath != null)
            {
                ESkillCdTracker.Clear();
                // JSON策略：战斗引擎内部初始化队伍，无需TXTSpecific步骤
                // 1. 走到钥匙处启动
                Logger.LogInformation("Auto domain: {Text}", "1. Walk to the key to start");
                await WalkToPressF();

                // 2. 执行战斗（JSON战斗引擎）
                Logger.LogInformation("Auto domain: {Text}", "2. Run the combat strategy (JSON)");
                await StartJsonFight();
            }
            else
            {
                //0.5. 初始化队伍，只执行一次
                if (i == 0)
                {
                    combatScenes = new CombatScenes(_runtime, _allConfig).InitializeTeam(_runtime.CaptureToRectArea());
                }

                RetryTeamInit(combatScenes);

                // 0. 切换到第一个角色
                var combatCommands = FindCombatScriptAndSwitchAvatar(combatScenes);

                // 1. 走到钥匙处启动
                Logger.LogInformation("Auto domain: {Text}", "1. Walk to the key to start");
                await WalkToPressF();

                // 2. 执行战斗（战斗线程、视角线程、检测战斗完成线程）
                Logger.LogInformation("Auto domain: {Text}", "2. Run the combat strategy");
                await StartFight(combatScenes, combatCommands);
                combatScenes.AfterTask();
            }
            EndFightWait();

            // 3. 寻找石化古树 并左右移动直到石化古树位于屏幕中心
            Logger.LogInformation("Auto domain: {Text}", "3. Find the petrified tree");
            await FindPetrifiedTree();

            // 4. 走到石化古树处
            Logger.LogInformation("Auto domain: {Text}", "4. Go to the petrified tree");
            await WalkToPressF();

            // 5. 快速领取奖励并判断是否有下一轮
            Logger.LogInformation("Auto domain: {Text}", "5. Claim the reward");
            if (!await GettingTreasure())
            {
                if (_guidePlanning && _guideNextAction == GuideNextAction.AdvancePlan)
                    Logger.LogInformation("培养计划：当前入口执行结束，退出后按缓存计划选择下一步");
                else
                    Logger.LogInformation("Resin depleted or the configured number of runs reached; ending auto domain");
                break;
            }
        }
    }

    private void Init()
    {
        LogScreenResolution();

        if (_taskParam.SpecifyResinUse)
        {
            Logger.LogInformation("→ {Text} use the specified resin", "Auto domain, ");
        }
        else
        {
            Logger.LogInformation("→ {Text} stop after all Condensed and Original Resin is used", "Auto domain, ");
        }
    }

    private void LogScreenResolution()
    {
        var gameScreenSize = SystemControl.GetGameScreenRect(_runtime.Window.Handle);
        if (gameScreenSize.Width * 9 != gameScreenSize.Height * 16)
        {
            Logger.LogError("The game window resolution is not 16:9. Current resolution: {Width}x{Height}. Auto domain may not work correctly at other aspect ratios.",
                gameScreenSize.Width, gameScreenSize.Height);
            throw new Exception("The game window resolution is not 16:9");
        }

        if (gameScreenSize.Width < 1920 || gameScreenSize.Height < 1080)
        {
            Logger.LogWarning("The game window resolution is below 1920x1080. Current resolution: {Width}x{Height}. Auto domain may not work correctly at this resolution.",
                gameScreenSize.Width, gameScreenSize.Height);
        }
    }

    private void RetryTeamInit(CombatScenes combatScenes)
    {
        if (!combatScenes.CheckTeamInitialized())
        {
            combatScenes.InitializeTeam(_runtime.CaptureToRectArea());
            if (!combatScenes.CheckTeamInitialized())
            {
                throw new Exception("Failed to recognize party members. Retry against a darker background, such as at night in-game, or force-select the current party members.");
            }
        }
    }

    private async Task TpDomain()
    {
        // 初次进入及切换目标共用传送路径，不复用上一轮画面坐标。
        _guideEntryPositions.Clear();
        if (_taskParam.DomainName == TrainingGuideOption && !_guidePlanning)
        {
            _guideDomainName = null;
            _guideDomainName = (await ScanGuideDomains(firstOnly: true)).FirstOrDefault()
                ?? throw new InvalidOperationException("提升指南：没有可用的材料秘境，停止任务");
        }
        // 传送到秘境
        if (!string.IsNullOrEmpty(_guideDomainName ?? _taskParam.DomainName))
        {
            if (MapLazyAssets.Get().DomainPositionMap.TryGetValue(_guideDomainName ?? _taskParam.DomainName, out var domainPosition))
            {
                Logger.LogInformation("自动秘境：传送到秘境{Text}", _guideDomainName ?? _taskParam.DomainName);
                await new TpTask(_runtime, _allConfig, _ct).Tp(domainPosition.X, domainPosition.Y);
                await _runtime.Delay(1000, _ct);
                if (!await Bv.WaitForMainUi(_runtime, _ct) && _guidePlanning)
                    throw new InvalidOperationException("传送后未确认回到主界面，停止接近秘境入口");

                await ApproachDomainEntrance(_guideDomainName ?? _taskParam.DomainName);
                await _runtime.Delay(300, _ct);

            }
            else
            {
                Logger.LogError("Auto domain: no teleport waypoint found for domain {Text}", _taskParam.DomainName);
                throw new Exception($"No teleport waypoint found for domain {_taskParam.DomainName}");
            }
        }
    }

    /// <summary>
    /// 接近秘境入口；已有交互提示时无需移动，普通任务和培养计划共用此逻辑。
    /// </summary>
    private async Task ApproachDomainEntrance(string domainName)
    {
        var menuFound = false;
        AutoPickAssets pickAssets;
        using (var gameCaptureRegion = _runtime.CaptureToRectArea())
        {
            pickAssets = AutoPickAssets.Get(gameCaptureRegion, _allConfig.AutoPickConfig.PickKey);
            using var interaction = gameCaptureRegion.Find(pickAssets.PickRo);
            if (interaction.IsExist()) return;
        }
        try
        {
            if ("芬德尼尔之顶".Equals(domainName))
            {
                menuFound = await NewRetry.WaitForElementAppear(_runtime,
                    pickAssets.PickRo,
                    () => InputHub.Foreground.SimulateAction(GIActions.MoveBackward, KeyType.KeyDown),
                    _ct,
                    20,
                    500
                );
                InputHub.Foreground.SimulateAction(GIActions.MoveBackward, KeyType.KeyUp);
            }
            else if ("无妄引咎密宫".Equals(domainName))
            {
                InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyDown);
                await _runtime.Delay(500, _ct);
                InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyUp);

                menuFound = await NewRetry.WaitForElementAppear(_runtime,
                    pickAssets.PickRo,
                    () => InputHub.Foreground.SimulateAction(GIActions.MoveLeft, KeyType.KeyDown),
                    _ct,
                    20,
                    500
                );
                InputHub.Foreground.SimulateAction(GIActions.MoveLeft, KeyType.KeyUp);
            }
            else if ("太山府".Equals(domainName))
            {
                menuFound = await NewRetry.WaitForElementAppear(_runtime,
                    pickAssets.PickRo,
                    () => { },
                    _ct,
                    20,
                    500
                );
            }
            else
            {
                menuFound = await NewRetry.WaitForElementAppear(_runtime,
                    pickAssets.PickRo,
                    () => InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyDown),
                    _ct,
                    20,
                    500
                );
                InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyUp);
            }

        }
        finally
        {
            InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyUp);
            InputHub.Foreground.SimulateAction(GIActions.MoveBackward, KeyType.KeyUp);
            InputHub.Foreground.SimulateAction(GIActions.MoveLeft, KeyType.KeyUp);
        }

        if (!menuFound)
        {
            throw new Exception("请检查是否在秘境门前");
        }
    }

    /// <summary>
    /// 切换队伍
    /// </summary>
    /// <param name="partyName"></param>
    /// <returns></returns>
    private async Task<bool> SwitchParty(string? partyName)
    {
        if (!string.IsNullOrEmpty(partyName))
        {
            var b = await new SwitchPartyTask(_runtime).Start(partyName, _ct);
            await _runtime.Delay(500, _ct);
            return b;
        }

        return true;
    }

    private async Task EnterDomain()
    {
        AutoFightAssets fightAssets;
        AutoPickAssets pickAssets;
        using (var gameCaptureRegion = _runtime.CaptureToRectArea())
        {
            fightAssets = AutoFightAssets.Get(gameCaptureRegion);
            pickAssets = AutoPickAssets.Get(gameCaptureRegion, _allConfig.AutoPickConfig.PickKey);
        }

        var domainName = _guideDomainName ?? _taskParam.DomainName;
        if (!string.IsNullOrEmpty(domainName)
            && MapLazyAssets.Get().DomainPositionMap.TryGetValue(domainName, out var domainPosition)
            && "至冬".Equals(domainPosition.Country, StringComparison.Ordinal))
        {
            var domainOptionName = domainPosition.Name ?? domainName;
            Logger.LogInformation("Auto domain: using text OCR to select the Nod-Krai domain interaction option: {Text}", domainOptionName);
            if (!await new ChooseFOptionTask(_runtime, _allConfig).SingleSelectText(domainOptionName, _ct))
            {
                Logger.LogWarning("未能通过文本OCR选择秘境，直接F");
                await NewRetry.WaitForElementDisappear(_runtime,
                    pickAssets.PickRo,
                    () => InputHub.Foreground.Keyboard.KeyPress(pickAssets.PickVk),
                    _ct,
                    20,
                    500
                );
            }

            // 交互输入生效和截图源刷新都存在延迟，等待交互键消失后再识别秘境菜单。
            await NewRetry.WaitForElementDisappear(_runtime,
                pickAssets.PickRo,
                (Action?)null,
                _ct,
                20,
                500
            );
        }
        else
        {
            await NewRetry.WaitForElementDisappear(_runtime,
                pickAssets.PickRo,
                () => InputHub.Foreground.Keyboard.KeyPress(pickAssets.PickVk),
                _ct,
                20,
                500
            );
        }
        // 培养指南只等待入口菜单，不在选择前检查挑战按钮或解锁状态。
        using var menuScreen = _runtime.CaptureToRectArea();
        var menuFound = await NewRetry.WaitForElementAppear(_runtime,
            (_guidePlanning || _taskParam.DomainName == TrainingGuideOption)
                ? RecognitionObject.OcrMatch(0, 0, menuScreen.Width * .47, menuScreen.Height * .12, "秘境入口")
                : GetConfirmRa(singlePlayerChallengeString),
            null,//只等待,不执行操作
            _ct,
            20,
            500
        );
        if (!menuFound)
        {
            if (_guidePlanning || _taskParam.DomainName == TrainingGuideOption)
                throw new InvalidOperationException("未确认秘境入口菜单，停止培养任务");
            Logger.LogWarning("The Solo Challenge button did not appear; check that the domain page is open");
        }

        using var limitedFullyStringRa = _runtime.CaptureToRectArea();
        var limitedFullyStringRaocrList =
            limitedFullyStringRa.FindMulti(RecognitionObject.Ocr(0, 0, limitedFullyStringRa.Width * 0.5,
                limitedFullyStringRa.Height * 0.5));
        var limitedFullyStringRaocrListdone = limitedFullyStringRaocrList.LastOrDefault(t =>
            Regex.IsMatch(t.Text, this.limitedFullyString) || Regex.IsMatch(t.Text, this.limitedFullyAllString));
        // 检测是否为限时全开秘境
        if (limitedFullyStringRaocrListdone != null)
        {
            Logger.LogInformation("Auto domain: {Text}", "Detected the all-domains-open event");
        }
        foreach (var region in limitedFullyStringRaocrList) region.Dispose();

        var serverTime = ServerTimeHelper.GetServerTimeNow();
        if (_guidePlanning || _taskParam.DomainName == TrainingGuideOption)
        {
            var allOpen = serverTime is { DayOfWeek: DayOfWeek.Sunday, Hour: >= 4 }
                || serverTime is { DayOfWeek: DayOfWeek.Monday, Hour: < 4 }
                || limitedFullyStringRaocrListdone != null;
            await SelectTrainingGuideLevel(allOpen);
        }
        else if (serverTime is { DayOfWeek: DayOfWeek.Sunday, Hour: >= 4 } || serverTime is { DayOfWeek: DayOfWeek.Monday, Hour: < 4 } || limitedFullyStringRaocrListdone != null)
        {
            using var ra0 = _runtime.CaptureToRectArea();
            using var artifactArea = ra0.Find(RecognitionAssets.Get("AutoFight", "ArtifactArea", ra0)); //检测是否为圣遗物副本
            if (artifactArea.IsEmpty())
            {
                if (int.TryParse(_taskParam.SundaySelectedValue, out int sundaySelectedValue))
                {
                    if (sundaySelectedValue > 0)
                    {
                        Logger.LogInformation(limitedFullyStringRaocrListdone != null ? "Auto domain: all-domains-open reward index {sundaySelectedValue}" : "Auto domain: Sunday domain reward index set to {sundaySelectedValue}", sundaySelectedValue);
                        using var abnormalscreenRa = _runtime.CaptureToRectArea();
                        _runtime.GameRegion1080PPosMove(abnormalscreenRa.Width / 4, abnormalscreenRa.Height / 2); //移到左侧
                        for (var i = 0; i < 100; i++)
                        {
                            InputHub.Foreground.Mouse.VerticalScroll(-1);
                            await _runtime.Delay(10, _ct);
                        }

                        await _runtime.Delay(400, _ct);

                        using var abnormalRa = _runtime.CaptureToRectArea();
                        var ocrList =
                            abnormalRa.FindMulti(RecognitionObject.Ocr(0, 0, abnormalRa.Width * 0.5,
                                abnormalRa.Height));
                        var done = ocrList.LastOrDefault(t =>
                            Regex.IsMatch(t.Text, this.leyLineDisorderLocalizedString));
                        if (done != null)
                        {
                            await _runtime.Delay(300, _ct);

                            switch (sundaySelectedValue)
                            {
                                case 1:
                                    Click1080P(done.X, done.Y - abnormalRa.Height / 5);
                                    break;
                                case 2:
                                    Click1080P(done.X, done.Y - abnormalRa.Height / 10);
                                    break;
                                case 3:
                                    Click1080P(done.X, done.Y);
                                    break;
                                default:
                                    Logger.LogWarning("Invalid sundaySelectedValue value: {sundaySelectedValue}",
                                        sundaySelectedValue);
                                    break;
                            }
                        }
                    }
                    else
                    {
                        Logger.LogInformation(limitedFullyStringRaocrListdone != null ? "Auto domain: no specific reward configured for the all-domains-open event" : "Auto domain: no specific reward configured for Sunday domains");
                    }
                }
                else
                {
                    Logger.LogWarning(_taskParam.SundaySelectedValue == "" ? "No domain reward index is set" : "Invalid domain reward index; check the configuration page");
                }
            }

            await _runtime.Delay(300, _ct);
        }

        // 点击单人挑战确认并等待队伍界面--使用图像模版匹配的方法，也可以使用文字OCR的方法识别“单人挑战”直到消失
        await NewRetry.WaitForElementAppear(_runtime,
            ElementRecognition.Get("PartyBtnChooseView", _runtime.SystemInfo),
            () =>
            {
                using var ra = _runtime.CaptureToRectArea();
                var ra2 = ra.Find(RecognitionAssets.Get("AutoFight", "Confirm", ra));
                if (!ra2.IsEmpty())
                {
                    ra2.Click();
                    ra2.Dispose();
                    Logger.LogInformation("Auto domain: clicking {Text}", singlePlayerChallengeString);
                }

                using var confirmRectArea2 = ra.Find(RecognitionObject.Ocr(ra.Width * 0.263, ra.Height * 0.32,
                    ra.Width - ra.Width * 0.263 * 2, ra.Height - ra.Height * 0.32 - ra.Height * 0.353));
                if (confirmRectArea2.IsExist() && Regex.IsMatch(confirmRectArea2.Text, retryDomainPromptPattern))
                {
                    Logger.LogWarning("Auto domain: resin shortage prompt detected: {Text}", confirmRectArea2.Text);
                    throw new Exception("Not enough resin; auto domain is stopping");
                }
            },
            _ct,
            10,
            1000
        );

        // 等待队伍选择界面出现
        var teamUiFound = await NewRetry.WaitForElementAppear(_runtime,
            ElementRecognition.Get("PartyBtnChooseView", _runtime.SystemInfo),
            () => { Logger.LogInformation("自动秘境：进入 {Text}", "队伍选择界面"); },
            _ct,
            10,
            1000
        );
        if (!teamUiFound)
        {
            Logger.LogWarning("The party selection screen did not appear; skipping team switch");
        }
        else
        {
            await SwitchParty(_taskParam.PartyName);
        }

        // 点击开始挑战确认并等待“开始挑战”文字消失
        var startFightFound = await NewRetry.WaitForElementDisappear(_runtime,
            GetConfirmRa(startChallengeString),
            screen =>
            {
                screen.Find(RecognitionAssets.Get("AutoFight", "Confirm", screen), ra =>
                {
                    ra.Click();
                    ra.Dispose();
                    Logger.LogInformation("Auto domain: clicking {Text}", startChallengeString);
                });
            },
            _ct,
            10,
            1000
        );
        if (!startFightFound)
        {
            Logger.LogWarning("The Start Challenge button did not appear or could not be clicked");
        }

        // 载入
        await _runtime.Delay(1000, _ct);
    }

    private async Task CloseDomainTip()
    {
        //先等待秘境提示出现,如果直接出现Enter也属于完成条件
        var domainTipFound = await NewRetry.WaitForAction(_runtime, () =>
        {
            using var ra = _runtime.CaptureToRectArea();

            var ocrList = ra.FindMulti(RecognitionObject.Ocr(0, ra.Height * 0.2, ra.Width, ra.Height * 0.6));
            var ocrListLeft = ra.Find(RecognitionAssets.Get("AutoFight", "AbnormalIcon", ra));
            return (ocrList.Any(t => t.Text.Contains(leyLineDisorderLocalizedString) ||
                                     t.Text.Contains(clickanywheretocloseLocalizedString))) || ocrListLeft.IsExist();
        }, _ct, 40, 500);
        if (!domainTipFound)
        {
            Logger.LogWarning("The domain prompt did not appear or could not be clicked");
        }

        //持续点击，直到左下角出现目标文字
        var leftBottomFound = await NewRetry.WaitForAction(_runtime, () =>
        {
            using var ra = _runtime.CaptureToRectArea();
            var ocrList = ra.FindMulti(RecognitionObject.Ocr(0, ra.Height * 0.2, ra.Width, ra.Height * 0.6));
            // 查找目标文字
            var done = ocrList.FirstOrDefault(t =>
                Regex.IsMatch(t.Text, this.leyLineDisorderLocalizedString) ||
                Regex.IsMatch(t.Text, this.clickanywheretocloseLocalizedString));
            if (done != null)
            {
                done.Click();
                done.Dispose();
                Logger.LogInformation("Auto domain: clicking {Text}", done.Text);
            }

            // 检查左下角区域是否还存在目标文字，消失则继续，存在则结束
            using var leftBottom = _runtime.CaptureToRectArea();
            var leftBottomOcr = leftBottom.Find(RecognitionAssets.Get("AutoFight", "AbnormalIcon", leftBottom));
            return leftBottomOcr.IsExist();
        }, _ct, 20, 500);
        if (!leftBottomFound)
        {
            //尝试随意点击一下右下角
            _runtime.GameRegion1080PPosClick(1515, 892);
            Logger.LogWarning("秘境提示未出现或未能点击。");
        }

        await _runtime.Delay(500, _ct);
    }

    private List<CombatCommand> FindCombatScriptAndSwitchAvatar(CombatScenes combatScenes)
    {
        var combatCommands = _combatScriptBag.FindCombatScript(combatScenes.GetAvatars());
        var avatar = combatScenes.SelectAvatar(combatCommands[0].Name);
        avatar?.SwitchWithoutCts();
        _runtime.Sleep(200);
        return combatCommands;
    }

    /// <summary>
    /// 走到钥匙处启动
    /// </summary>
    private async Task WalkToPressF()
    {
        if (_ct.IsCancellationRequested)
        {
            return;
        }

        await Task.Run((Action)(() =>
        {
            InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyDown);
            _runtime.Sleep(30, _ct);
            // 组合键好像不能直接用 postmessage
            if (!_taskParam.WalkToF)
            {
                InputHub.Foreground.SimulateAction(GIActions.SprintKeyboard, KeyType.KeyDown);
            }

            try
            {
                var startTime = DateTime.Now;
                while (!_ct.IsCancellationRequested)
                {
                    using var gameCaptureRegion = _runtime.CaptureToRectArea();
                    var pickAssets = AutoPickAssets.Get(gameCaptureRegion, _allConfig.AutoPickConfig.PickKey);
                    using var fRectArea = gameCaptureRegion.Find(pickAssets.PickRo);
                    if (fRectArea.IsEmpty())
                    {
                        _runtime.Sleep(100, _ct);
                    }
                    else
                    {
                        Logger.LogInformation("Interaction key detected");
                        InputHub.Foreground.Keyboard.KeyPress(pickAssets.PickVk);
                        break;
                    }

                    // 超时直接放弃整个秘境
                    if (DateTime.Now - startTime > TimeSpan.FromSeconds(60))
                    {
                        Logger.LogWarning("Auto domain: {Text}", "Timed out while moving to the target. If a domain was selected, it will be retried after teleporting");
                        Avatar.TpForRecover(_runtime, _allConfig, _ct, new RetryException("Timed out while moving to the target; teleport to a Statue of The Seven, then retry the domain"));
                    }
                }
            }
            finally
            {
                InputHub.Foreground.SimulateAction(GIActions.MoveForward, KeyType.KeyUp);
                _runtime.Sleep(50);
                if (!_taskParam.WalkToF)
                {
                    InputHub.Foreground.SimulateAction(GIActions.SprintKeyboard, KeyType.KeyUp);
                }
            }
        }), _ct);
    }

    private Task StartFight(CombatScenes combatScenes, List<CombatCommand> combatCommands)
    {
        CancellationTokenSource cts = new();
        _ct.Register(cts.Cancel);
        combatScenes.BeforeTask(cts.Token);
        // 战斗操作
        var combatTask = new Task(() =>
        {
            try
            {
                AutoFightTask.FightStatusFlag = true;
                while (!cts.Token.IsCancellationRequested)
                {
                    // 通用化战斗策略
                    foreach (var command in combatCommands)
                    {
                        command.Execute(combatScenes);
                    }
                }
            }
            catch (NormalEndException e)
            {
                Logger.LogInformation("Combat action interrupted: {Msg}", e.Message);
            }
            catch (Exception e)
            {
                Logger.LogWarning(e.Message);
                throw;
            }
            finally
            {
                Logger.LogInformation("Auto-combat thread ended");
                InputHub.ReleaseAll();
                AutoFightTask.FightStatusFlag = false;
            }
        }, cts.Token);

        // 对局结束检测
        var domainEndTask = DomainEndDetectionTask(cts);
        // 自动吃药
        // var autoEatRecoveryHpTask = AutoEatRecoveryHpTask(cts.Token);
        combatTask.Start();
        domainEndTask.Start();
        // autoEatRecoveryHpTask.Start();
        return Task.WhenAll(combatTask, domainEndTask);
    }

    /// <summary>
    /// 自动连招战斗入口：Tick 后台构建的连招行为树（注入建树会话，不读静态暂存），
    /// 秘境的DomainEndDetectionTask通过CancellationToken控制战斗结束。
    /// </summary>
    private async Task StartComboFight()
    {
        CancellationTokenSource cts = new();
        _ct.Register(cts.Cancel);

        // 建树已在 WalkToPressF 前汇合完成，此处 await 已完成的任务同步返回结果
        var comboTreeSession = await _comboBuildTask!;

        // 抑制其自带的结束检测（FightFinishDetectEnabled=false），由秘境的DomainEndDetectionTask控制战斗结束
        var comboTask = new AutoComboRunTask(_runtime, _allConfig, comboTreeSession);
        var comboParam = new AutoFightParam { FightFinishDetectEnabled = false };

        var domainEndTask = DomainEndDetectionTask(cts);

        var combatTask = Task.Run(async () =>
        {
            try
            {
                // 组合调用使用 RunAsync，保留子任务异常向外传播的语义
                var result = await comboTask.RunAsync(comboParam, cts.Token);
                if (result.Kind == SoloTaskResultKind.Failed)
                {
                    Logger.LogWarning("自动连招战斗任务失败：{Msg}", result.Message);
                }
            }
            catch (RetryException)
            {
                // 复活/恢复信号必须传回 RunAsync 的重试循环，复活后重试秘境
                await cts.CancelAsync();
                throw;
            }
            catch (OperationCanceledException)
            {
                // 对局结束取消战斗，正常流程
            }
            catch (Exception e)
            {
                Logger.LogWarning("Auto-combo combat task failed: {Msg}", e.Message);
            }
        }, cts.Token);

        domainEndTask.Start();
        await Task.WhenAll(combatTask, domainEndTask);
    }

    /// <summary>
    /// JSON策略战斗入口：委托给AutoFightJsonTask，抑制其自带的结束检测和拾取逻辑，
    /// 秘境的DomainEndDetectionTask通过CancellationToken控制战斗结束。
    /// </summary>
    private async Task StartJsonFight()
    {
        CancellationTokenSource cts = new();
        _ct.Register(cts.Cancel);

        var jsonParam = new AutoFightParam
        {
            CombatStrategyPath = _jsonCombatStrategyPath!,
            FightFinishDetectEnabled = false,
            ExpBasedPickupEnabled = false,
            KazuhaPickupEnabled = false,
            PickDropsAfterFightEnabled = false,
            Timeout = 600,
        };

        var jsonTask = new AutoFightJsonTask(_runtime, _allConfig);

        var domainEndTask = DomainEndDetectionTask(cts);

        var combatTask = Task.Run(async () =>
        {
            try
            {
                // 组合调用使用 RunAsync，保留子任务异常向外传播的语义
                var result = await jsonTask.RunAsync(jsonParam, cts.Token);
                if (result.Kind == SoloTaskResultKind.Failed)
                {
                    Logger.LogWarning("JSON战斗任务失败：{Msg}", result.Message);
                }
            }
            catch (RetryException)
            {
                // 复活/恢复信号必须传回 RunAsync 的重试循环，复活后重试秘境
                await cts.CancelAsync();
                throw;
            }
            catch (OperationCanceledException)
            {
                // 对局结束取消战斗，正常流程
            }
            catch (Exception e)
            {
                Logger.LogWarning("JSON combat task failed: {Msg}", e.Message);
            }
        }, cts.Token);

        domainEndTask.Start();
        await Task.WhenAll(combatTask, domainEndTask);
    }

    private void EndFightWait()
    {
        if (_ct.IsCancellationRequested)
        {
            return;
        }

        // 沿用本次运行参数中的战后等待，不能重新读取其他页面的值。
        var s = _taskParam.FightEndDelay;
        if (s > 0)
        {
            Logger.LogInformation("Waiting {Second} seconds after combat ends", s);
            _runtime.Sleep((int)(s * 1000), _ct);
        }
    }

    /// <summary>
    /// 对局结束检测
    /// </summary>
    private Task DomainEndDetectionTask(CancellationTokenSource cts)
    {
        return new Task(async () =>
        {
            try
            {
                while (!_ct.IsCancellationRequested)
                {
                    if (IsDomainEnd())
                    {
                        await cts.CancelAsync();
                        break;
                    }

                    await _runtime.Delay(1000, cts.Token);
                }
            }
            catch
            {
            }
        }, cts.Token);
    }

    private bool IsDomainEnd()
    {
        using var ra = _runtime.CaptureToRectArea();

        var fightAssets = AutoFightAssets.Get(ra);
        var endTipsRect = ra.DeriveCrop(fightAssets.EndTipsUpperRect);
        var text = OcrFactory.Paddle.Ocr(endTipsRect.SrcMat);
        if (Regex.IsMatch(text, this.challengeCompletedLocalizedString))
        {
            Logger.LogInformation("Domain completion prompt detected (challenge completed); ending the domain");
            return true;
        }

        endTipsRect = ra.DeriveCrop(fightAssets.EndTipsRect);
        text = OcrFactory.Paddle.Ocr(endTipsRect.SrcMat);
        if (Regex.IsMatch(text, this.autoLeavingLocalizedString))
        {
            Logger.LogInformation("Domain completion prompt detected (automatic exit countdown); ending the domain");
            return true;
        }

        return false;
    }

    private Task AutoEatRecoveryHpTask(CancellationToken ct)
    {
        return new Task(async () =>
        {
            if (!_taskParam.AutoEat)
            {
                return;
            }

            if (!IsTakeFood())
            {
                Logger.LogInformation("“{Tool}” is not equipped; automatic healing at critical HP is disabled", "NRE (Menu 30)");
                return;
            }

            try
            {
                while (!_ct.IsCancellationRequested)
                {
                    using var capture = _runtime.CaptureToRectArea();
                    if (Bv.CurrentAvatarIsLowHp(capture))
                    {
                        // 模拟按键 "Z"
                        InputHub.Foreground.SimulateAction(GIActions.QuickUseGadget);
                        Logger.LogInformation("Critical HP detected; pressing Z to use food");
                        // TODO 吃饱了会一直吃
                    }

                    await _runtime.Delay(500, ct);
                }
            }
            catch (Exception e)
            {
                Logger.LogDebug(e, "Error while checking automatic healing at critical HP");
            }
        }, ct);
    }

    private bool IsTakeFood()
    {
        // 获取图像
        using var ra = _runtime.CaptureToRectArea();
        // 识别道具图标下是否是数字
        var s = _runtime.SystemInfo.AssetScale;
        var countArea = ra.DeriveCrop(1800 * s, 845 * s, 40 * s, 20 * s);
        var count = OcrFactory.Paddle.OcrWithoutDetector(countArea.CacheGreyMat);
        return int.TryParse(count, out _);
    }

    /// <summary>
    /// 旋转视角后寻找石化古树
    /// </summary>
    private Task FindPetrifiedTree()
    {
        CancellationTokenSource treeCts = new();
        _ct.Register(treeCts.Cancel);
        // 中键回正视角
        InputHub.Foreground.Mouse.MiddleButtonClick();
        _runtime.Sleep(900, _ct);

        // 左右移动直到石化古树位于屏幕中心任务
        var moveAvatarTask = MoveAvatarHorizontallyTask(treeCts);

        // 锁定东方向视角线程
        var lockCameraToEastTask = LockCameraToEastTask(treeCts, moveAvatarTask);
        lockCameraToEastTask.Start();
        return Task.WhenAll(moveAvatarTask, lockCameraToEastTask);
    }

    private Task MoveAvatarHorizontallyTask(CancellationTokenSource treeCts)
    {
        return new Task(() =>
        {
            var keyConfig = _allConfig.KeyBindingsConfig;
            var moveLeftKey = keyConfig.MoveLeft.ToVK();
            var moveRightKey = keyConfig.MoveRight.ToVK();
            var moveForwardKey = keyConfig.MoveForward.ToVK();
            var captureArea = _runtime.SystemInfo.ScaleMax1080PCaptureRect;
            var middleX = captureArea.Width / 2;
            var leftKeyDown = false;
            var rightKeyDown = false;
            var noDetectCount = 0;
            var prevKey = moveLeftKey;
            var backwardsAndForwardsCount = 0;
            while (!_ct.IsCancellationRequested)
            {
                using var capture = _runtime.CaptureToRectArea();
                var treeRect = DetectTree(capture);
                if (treeRect != default)
                {
                    var treeMiddleX = treeRect.X + treeRect.Width / 2;
                    if (treeRect.X + treeRect.Width < middleX && !_taskParam.ShortMovement)
                    {
                        backwardsAndForwardsCount = 0;
                        // 树在左边 往左走
                        Debug.WriteLine($"Tree is on the left; moving left {treeMiddleX}  {middleX}");
                        if (rightKeyDown)
                        {
                            // 先松开D键
                            InputHub.Foreground.Keyboard.KeyUp(moveRightKey);
                            rightKeyDown = false;
                        }

                        if (!leftKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyDown(moveLeftKey);
                            leftKeyDown = true;
                        }
                    }
                    else if (treeRect.X > middleX && !_taskParam.ShortMovement)
                    {
                        backwardsAndForwardsCount = 0;
                        // 树在右边 往右走
                        Debug.WriteLine($"Tree is on the right; moving right {treeMiddleX}  {middleX}");
                        if (leftKeyDown)
                        {
                            // 先松开A键
                            InputHub.Foreground.Keyboard.KeyUp(moveLeftKey);
                            leftKeyDown = false;
                        }

                        if (!rightKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyDown(moveRightKey);
                            rightKeyDown = true;
                        }
                    }
                    else
                    {
                        // 树在中间 松开所有键
                        if (rightKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyUp(moveRightKey);
                            prevKey = moveRightKey;
                            rightKeyDown = false;
                        }

                        if (leftKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyUp(moveLeftKey);
                            prevKey = moveLeftKey;
                            leftKeyDown = false;
                        }

                        // 松开按键后使用小碎步移动
                        if (treeMiddleX < middleX)
                        {
                            if (prevKey == moveRightKey)
                            {
                                backwardsAndForwardsCount++;
                            }

                            InputHub.Foreground.Keyboard.KeyDown(moveLeftKey);
                            _runtime.Sleep(60);
                            InputHub.Foreground.Keyboard.KeyUp(moveLeftKey);
                            prevKey = moveLeftKey;
                        }
                        else if (treeMiddleX > middleX)
                        {
                            if (prevKey == moveLeftKey)
                            {
                                backwardsAndForwardsCount++;
                            }

                            InputHub.Foreground.Keyboard.KeyDown(moveRightKey);
                            _runtime.Sleep(60);
                            InputHub.Foreground.Keyboard.KeyUp(moveRightKey);
                            prevKey = moveRightKey;
                        }
                        else
                        {
                            InputHub.Foreground.Keyboard.KeyDown(moveForwardKey);
                            _runtime.Sleep(60);
                            InputHub.Foreground.Keyboard.KeyUp(moveForwardKey);
                            _runtime.Sleep(500, _ct);
                            treeCts.Cancel();
                            break;
                        }
                    }
                }
                else
                {
                    backwardsAndForwardsCount = 0;
                    // 左右巡逻
                    noDetectCount++;
                    if (noDetectCount > 40)
                    {
                        if (leftKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyUp(moveLeftKey);
                            leftKeyDown = false;
                        }

                        if (!rightKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyDown(moveRightKey);
                            rightKeyDown = true;
                        }
                    }
                    else
                    {
                        if (rightKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyUp(moveRightKey);
                            rightKeyDown = false;
                        }

                        if (!leftKeyDown)
                        {
                            InputHub.Foreground.Keyboard.KeyDown(moveLeftKey);
                            leftKeyDown = true;
                        }
                    }
                }

                if (backwardsAndForwardsCount >= _taskParam.LeftRightMoveTimes)
                {
                    // 左右移动5次说明已经在树中心了
                    InputHub.Foreground.Keyboard.KeyDown(moveForwardKey);
                    _runtime.Sleep(60);
                    InputHub.Foreground.Keyboard.KeyUp(moveForwardKey);
                    _runtime.Sleep(500, _ct);
                    treeCts.Cancel();
                    break;
                }

                _runtime.Sleep(60, _ct);
            }

            _runtime.MaskWindowDrawingBoard.ClearAll();
        });
    }

    private Rect DetectTree(ImageRegion region)
    {
        var result = _predictor.Predictor.Detect(region.CacheImage);
        var list = new List<MaskWindowDrawingShape>();
        foreach (var box in result)
        {
            var rect = new Rect(box.Bounds.X, box.Bounds.Y, box.Bounds.Width, box.Bounds.Height);
            list.Add(region.ToMaskWindowDrawingRect(rect));
        }

        region.DrawingBoard.Set("TreeBox", list);

        if (list.Count > 0)
        {
            var box = result[0];
            return new Rect(box.Bounds.X, box.Bounds.Y, box.Bounds.Width, box.Bounds.Height);
        }

        return default;
    }

    private Task LockCameraToEastTask(CancellationTokenSource cts, Task moveAvatarTask)
    {
        return new Task(() =>
        {
            var continuousCount = 0; // 连续东方向次数
            var started = false;
            while (!cts.Token.IsCancellationRequested)
            {
                using var captureRegion = _runtime.CaptureToRectArea();
                var angle = CameraOrientation.Compute(captureRegion.SrcMat);
                CameraOrientation.DrawDirection(captureRegion, angle);
                if (angle is >= 356 or <= 4)
                {
                    // 算作对准了
                    continuousCount++;
                    // 360 度 东方向视角
                    if (continuousCount > 5)
                    {
                        if (!started && moveAvatarTask.Status != TaskStatus.Running)
                        {
                            started = true;
                            moveAvatarTask.Start();
                        }
                    }
                }
                else
                {
                    continuousCount = 0;
                }

                if (angle <= 180)
                {
                    // 左移视角
                    var moveAngle = (int)Math.Round(angle);
                    if (moveAngle > 2)
                    {
                        moveAngle *= 2;
                    }

                    InputHub.Foreground.Mouse.MoveMouseBy(-moveAngle, 0);
                }
                else if (angle is > 180 and < 360)
                {
                    // 右移视角
                    var moveAngle = 360 - (int)Math.Round(angle);
                    if (moveAngle > 2)
                    {
                        moveAngle *= 2;
                    }

                    InputHub.Foreground.Mouse.MoveMouseBy(moveAngle, 0);
                }

                _runtime.Sleep(100, _ct);
            }

            Logger.LogInformation("锁定东方向视角线程结束");
            _runtime.MaskWindowDrawingBoard.ClearAll();
        });
    }

    /// <summary>
    /// 领取奖励
    /// </summary>
    private async Task<bool> GettingTreasure()
    {
        _guideRoundResin = 0;
        _guideRoundRewards = null;
        bool isLastTurn = false;
        // 等待窗口弹出
        await _runtime.Delay(300, _ct);

        // 1. OCR 直到确认弹出框弹出
        bool chooseResinPrompt = await NewRetry.WaitForAction(_runtime, () =>
        {
            using var ra = _runtime.CaptureToRectArea();
            var regionList = ra.FindMulti(RecognitionObject.Ocr(ra.Width * 0.25, ra.Height * 0.2, ra.Width * 0.5, ra.Height * 0.6));
            var res = regionList.FirstOrDefault(t => Regex.IsMatch(t.Text, petrifiedTreeString));
            if (res != null)
            {
                // 解决水龙王按下左键后没松开，然后后续点击按下就没反应了，界面上点一下
                res.Click();
                return true;
            }

            return false;
        }, _ct, 10, 500);
        Debug.WriteLine("识别到选择树脂页");
        await _runtime.Delay(800, _ct);

        // 再 OCR 一次，弹出框，确认当前是否有原粹树脂
        using var ra2 = _runtime.CaptureToRectArea();
        var textListInPrompt = ra2.FindMulti(RecognitionObject.Ocr(ra2.Width * 0.25, ra2.Height * 0.2, ra2.Width * 0.5, ra2.Height * 0.6));
        if (textListInPrompt.Any(t => Regex.IsMatch(t.Text, insufficientCountString, RegexOptions.IgnoreCase) || Regex.IsMatch(t.Text, replenishResinString, RegexOptions.IgnoreCase)))
        {
            // 没有原粹树脂，直接退出秘境
            Logger.LogInformation("Auto domain: Original Resin depleted; exiting the domain");
            await ExitDomain();
            return false;
        }

        if (chooseResinPrompt)
        {
            using var ra3 = _runtime.CaptureToRectArea();

            if (!_taskParam.SpecifyResinUse)
            {
                // 自动刷干树脂
                // 识别树脂状况
                var resinStatus = ResinStatus.RecogniseFromRegion(ra3, _runtime.SystemInfo, OcrFactory.Paddle);
                resinStatus.Print(Logger);

                if (resinStatus is { CondensedResinCount: <= 0, OriginalResinCount: < 20 })
                {
                    Logger.LogWarning("Not enough resin");
                    await ExitDomain();
                    return false;
                }

                bool resinUsed = false;
                if (_guidePlanning && _guideActivePlan != null)
                {
                    resinUsed = await UseTrainingGuideResin(resinStatus);
                }
                else if (resinStatus.CondensedResinCount > 0)
                {
                    (resinUsed, _) = PressUseResin(_runtime, ra3, "浓缩树脂");
                    if (resinUsed && _guidePlanning) _guideRoundResin = 60;
                    resinStatus.CondensedResinCount -= 1;
                }
                else if (resinStatus.OriginalResinCount >= 20)
                {
                    (resinUsed, var num) = PressUseResin(_runtime, ra3, "原粹树脂");
                    if (resinUsed && _guidePlanning) _guideRoundResin = num;
                    resinStatus.OriginalResinCount -= num;
                }

                if (!resinUsed)
                {
                    Logger.LogWarning("Auto domain: no usable resin found; possible causes: {Msg1} or {Msg2}.", "Not enough resin", "OCR recognition failed");
                    await ExitDomain();
                    return false;
                }

                if (resinStatus is { CondensedResinCount: <= 0, OriginalResinCount: < 20 })
                {
                    // 没树脂了就是最后一回合了
                    isLastTurn = true;
                }
            }
            else
            {
                // 指定使用树脂
                // 按优先级使用
                int successCount = 0;
                foreach (var record in _resinPriorityListWhenSpecifyUse)
                {
                    if (record.RemainCount > 0)
                    {
                        if (record.Name == "原粹树脂20" || record.Name == "原粹树脂40")
                        {
                            int expectedNum = record.Name == "原粹树脂20" ? 20 : 40;
                            bool switched;
                            try
                            {
                                switched = SwitchOriginalResinType(expectedNum, _ct);
                            }
                            catch (RetryException)
                            {
                                Logger.LogWarning("Auto domain: timed out retrying a switch to Original Resin; skipping {Name}", record.Name);
                                switched = false;
                            }

                            if (!switched)
                            {
                                continue;
                            }
                        }

                        await _runtime.Delay(400, _ct);
                        using var claimCapture = _runtime.CaptureToRectArea();
                        var claimTexts = claimCapture.FindMulti(RecognitionObject.Ocr(claimCapture.Width * .25,
                            claimCapture.Height * .2, claimCapture.Width * .5, claimCapture.Height * .6));
                        bool success;
                        int usedAmount;
                        try
                        {
                            if (_guidePlanning && record.Name.StartsWith("原粹树脂", StringComparison.Ordinal))
                            {
                                var resinRow = claimTexts.FirstOrDefault(t => Regex.IsMatch(t.Text, ResolveResinNamePattern("原粹树脂")));
                                var amounts = resinRow == null ? Array.Empty<int>() : Regex.Matches(resinRow.Text, @"(?<!\d)(20|40)(?!\d)")
                                    .Select(m => int.Parse(m.Value)).Distinct().ToArray();
                                var expected = record.Name == "原粹树脂20" ? 20 : record.Name == "原粹树脂40" ? 40 : 0;
                                if (amounts.Length != 1 || (expected != 0 && amounts[0] != expected))
                                    throw new InvalidOperationException("未确认原粹树脂消耗档位，停止领取");
                            }
                            (success, usedAmount) = PressUseResin(_runtime, claimTexts, record.Name);
                        }
                        finally { foreach (var text in claimTexts) text.Dispose(); }
                        if (success)
                        {
                            if (_guidePlanning) _guideRoundResin = record.Name.StartsWith("原粹树脂", StringComparison.Ordinal) ? usedAmount : 60;
                            record.RemainCount -= 1;
                            Logger.LogInformation("Auto domain: farming {Name}, run {Re}/{Max}", record.Name, record.MaxCount - record.RemainCount, record.MaxCount);
                            successCount++;
                            break;
                        }
                    }
                }

                if (_resinPriorityListWhenSpecifyUse.Sum(o => o.RemainCount) <= 0)
                {
                    // 全部刷完
                    isLastTurn = true;
                }

                if (successCount == 0)
                {
                    // 没有找到对应的树脂
                    Logger.LogWarning("Auto domain: the available resin options cannot satisfy the configured claim counts. The configured number of runs may be too high; exiting the domain.");
                    Logger.LogInformation("Current farming progress: {ResinList}", string.Join(", ", _resinPriorityListWhenSpecifyUse.Select(o => $"{o.Name}({o.MaxCount - o.RemainCount}/{o.MaxCount})")));
                    await ExitDomain();
                    return false;
                }
            }
        }
        else
        {
            // 如果没有选择树脂的提示，说明只有原粹树脂
            // 继续向下执行
        }
        
        Notify.Event(NotificationEvent.DomainReward).Success(I18nService.Instance.Translate("自动秘境奖励"));

        _runtime.Sleep(1000, _ct);
        await TryRecognizeRewardResult();
        if (_guidePlanning && UpdateGuideAfterReward(isLastTurn)) isLastTurn = true;

        for (var i = 0; i < 30; i++)
        {
            using var ra = _runtime.CaptureToRectArea();
            if (_guidePlanning && isLastTurn)
            {
                using var plannedExit = ra.Find(RecognitionAssets.Get("AutoFight", "Exit", ra));
                if (plannedExit.IsExist())
                {
                    plannedExit.Click();
                    return false;
                }
            }
            // 优先点击继续
            using var confirmRectArea = ra.Find(RecognitionAssets.Get("AutoFight", "Confirm", ra));
            if (!confirmRectArea.IsEmpty())
            {
                if (isLastTurn)
                {
                    // 最后一回合 退出
                    using var exitRectArea = ra.Find(RecognitionAssets.Get("AutoFight", "Exit", ra));
                    if (!exitRectArea.IsEmpty())
                    {
                        exitRectArea.Click();
                        return false;
                    }
                }
                else
                {
                    if (!chooseResinPrompt)
                    {
                        // TODO 前面没有弹框的情况下，意味着只有原粹树脂，要再识别一次右上角确认树脂余量，没有余量直接退出
                    }

                    // 有体力继续
                    confirmRectArea.Click();
                    await _runtime.Delay(60, _ct); // 双击
                    confirmRectArea.Click();

                    if (!chooseResinPrompt)
                    {
                        // 真没树脂了还有提示兜底
                        await _runtime.Delay(900, _ct);
                        using var noResinPromptCapture = _runtime.CaptureToRectArea();
                        var textListInNoResinPrompt = noResinPromptCapture.FindMulti(RecognitionObject.Ocr(ra2.Width * 0.25, ra2.Height * 0.2, ra2.Width * 0.5, ra2.Height * 0.6));
                        if (textListInNoResinPrompt.Any(t => Regex.IsMatch(t.Text, retryDomainPromptPattern)))
                        {
                            var cancelBtn = textListInNoResinPrompt.FirstOrDefault(t => Regex.IsMatch(t.Text, cancelButtonString));
                            if (cancelBtn != null)
                            {
                                cancelBtn.Click();
                                return false;
                            }
                        }
                    }

                    return true;
                }
            }

            _runtime.Sleep(300, _ct);
        }

        // 业务原因提前结束：携带失败结果，继承 NormalEndException，旧入口的“正常结束”语义不变
        throw new SoloTaskAbortException(SoloTaskResult.Failed(DomainEndNotDetectedReason, "No domain completion detected; the inventory may be full"));
    }

    private async Task TryRecognizeRewardResult()
    {
        if (!_taskParam.ShouldRecognizeRewards() || (_guideRewardResolutionUnsupported && !_taskParam.RewardRecognitionEnabled))
        {
            return;
        }

        try
        {
            if (!await WaitForRewardResultReady())
            {
                Logger.LogWarning("Auto domain: no exit button found on the reward screen; skipping reward recognition for this run");
                return;
            }

            // 使用多页识别（自动检测是否需要翻页）
            Logger.LogInformation("自动秘境：开始奖励识别");
            var useRewardsForPlanning = _guidePlanning && GuideRewardRecognitionEnabled;
            var rewards = RewardResultRecognizer.Instance.RecognizeMultiPage(_runtime,
                requireReliableCounts: useRewardsForPlanning,
                allowUnreliableCount: useRewardsForPlanning ? TrainingGuideRewardPolicy.IsCommonReward : null);
            if (useRewardsForPlanning)
                _guideRoundRewards = new Dictionary<string, int>(rewards);

            RewardResultRecognizer.MergeIntoSummary(_rewardSummary, rewards);

            if (rewards.Count > 0)
            {
                Logger.LogInformation("Auto domain: reward recognition results for this run: {Rewards}",
                    string.Join(", ", rewards.Select(r => $"{r.Key} x{r.Value}")));
            }
            else
            {
                Logger.LogWarning("Auto domain: no rewards recognized for this run");
            }
        }
        catch (Exception e) when (e is not OperationCanceledException and not NormalEndException)
        {
            Logger.LogWarning(e, "Auto domain: reward recognition failed; skipping the reward summary for this run");
        }
    }

    private async Task<bool> WaitForRewardResultReady()
    {
        for (var i = 0; i < 20; i++)
        {
            using var capture = _runtime.CaptureToRectArea();
            using var exitRegion = capture.Find(RecognitionAssets.Get("AutoFight", "Exit", capture));
            if (exitRegion.IsExist())
            {
                return true;
            }
            await _runtime.Delay(300, _ct);
        }
        return false;
    }

    private async Task ExitDomain()
    {
        InputHub.Foreground.Keyboard.KeyPress(VK.VK_ESCAPE);
        await _runtime.Delay(500, _ct);
        InputHub.Foreground.Keyboard.KeyPress(VK.VK_ESCAPE);
        await _runtime.Delay(800, _ct);
        using var capture = _runtime.CaptureToRectArea();
        Bv.ClickBlackConfirmButton(capture);
    }

    /// <summary>
    /// 在树脂选择弹框中识别并点击指定树脂的使用按键
    /// </summary>
    /// <param name="runtime">运行环境</param>
    /// <param name="ra">完整游戏截图</param>
    /// <param name="resinName">树脂名称（内部中文 key）</param>
    /// <param name="logPrefix">日志前缀</param>
    /// <returns>(是否使用成功, 消耗数量)</returns>
    public static (bool, int) PressUseResin(GameRuntime runtime, ImageRegion ra, string resinName, string logPrefix = "自动秘境")
    {
        var regionList = ra.FindMulti(RecognitionObject.Ocr(ra.Width * 0.25, ra.Height * 0.2, ra.Width * 0.5, ra.Height * 0.6));
        return PressUseResin(runtime, regionList, resinName, logPrefix);
    }

    /// <summary>
    /// 在已识别的弹框文字中找到指定树脂的使用按键并点击
    /// </summary>
    /// <param name="runtime">运行环境</param>
    /// <param name="regionList">树脂选择弹框的 OCR 结果</param>
    /// <param name="resinName">树脂名称（内部中文 key）</param>
    /// <param name="logPrefix">日志前缀</param>
    /// <returns>(是否使用成功, 消耗数量)</returns>
    public static (bool, int) PressUseResin(GameRuntime runtime, List<Region> regionList, string resinName, string logPrefix = "自动秘境")
    {
        if (resinName == "原粹树脂20" || resinName == "原粹树脂40")
        {
            resinName = "原粹树脂";
        }

        // resinName 折叠后仍是内部中文 key（GetResinNum 的分支判断依赖这个中文字面量），
        // 这里只本地化用于匹配 OCR 文本的模式，不改变 resinName 本身
        var resinNamePattern = ResolveResinNamePattern(resinName);
        var resinKey = regionList.FirstOrDefault(t => Regex.IsMatch(t.Text, resinNamePattern));
        if (resinKey != null)
        {
            // 找到树脂名称对应的按键，关键词为使用，是同一行的（高度相交）
            var useButtonPattern = ResolveUseButtonPattern();
            var useList = regionList.Where(t => Regex.IsMatch(t.Text, useButtonPattern)).ToList();
            if (useList.Count != 0)
            {
                // 找到使用按键
                var useKey = useList.FirstOrDefault(t => t.X > runtime.SystemInfo.ScaleMax1080PCaptureRect.Width / 2
                                                         && IsHeightOverlap(t, resinKey));
                if (useKey != null)
                {
                    // 点击使用
                    useKey.Click();
                    // 解决水龙王按下左键后没松开，然后后续点击按下就没反应了。使用双击
                    runtime.Sleep(60);
                    useKey.Click();
                    var num = GetResinNum(resinKey, resinName, logPrefix);
                    Logger.LogInformation("{LogPrefix}: using {ResinName}, amount: {Num}", logPrefix, resinName, num);
                    return (true, num);
                }
                else
                {
                    Logger.LogWarning("{LogPrefix}: could not find the use button for {ResinName}", logPrefix, resinName);
                }
            }
            else
            {
                Logger.LogWarning("{LogPrefix}: could not find the use button for {ResinName}", logPrefix, resinName);
            }
        }

        return (false, 0);
    }

    private bool SwitchOriginalResinType(int expectedNum, CancellationToken ct)
    {
        return NewRetry.Do(() =>
        {
            using var ra0 = _runtime.CaptureToRectArea();
            var regionList = ra0.FindMulti(RecognitionObject.Ocr(ra0.Width * 0.25, ra0.Height * 0.2, ra0.Width * 0.5, ra0.Height * 0.6));
            var has20 = regionList.Any(t => t.Text.Contains("20"));
            var has40 = regionList.Any(t => t.Text.Contains("40"));
            if (expectedNum == 20 && has20)
            {
                Logger.LogInformation("Auto domain: switched to using 20 Original Resin");
                return true;
            }

            if (expectedNum == 40 && has40)
            {
                Logger.LogInformation("Auto domain: switched to using 40 Original Resin");
                return true;
            }

            //切换20/40原粹树脂的按钮是亮的
            var clickable = ra0.Find(RecognitionAssets.Get("AutoDomain", "ResinSwitchBtn", ra0.Width, ra0.Height));
            if (clickable.IsExist())
            {
                Logger.LogDebug("Auto domain: switching the amount of Original Resin to use");
                clickable.Click();
            }

            //切换20/40原粹树脂的按钮是暗的
            var disabled = ra0.Find(RecognitionAssets.Get("AutoDomain", "ResinSwitchBtnNoActive", ra0.Width, ra0.Height));
            if (disabled.IsExist())
            {
                Logger.LogWarning("Auto domain: failed to change the amount of Original Resin to use, possibly due to insufficient resin. Current target: {Num}", expectedNum);
                return false; // 不可点击  
            }

            throw new RetryException("Button not detected"); // 继续重试
        }, TimeSpan.FromMilliseconds(500), 10);
    }

    private static int GetResinNum(Region region, string resinName, string logPrefix)
    {
        if (resinName == "原粹树脂")
        {
            if (region.Text.Contains("20"))
            {
                return 20;
            }
            else if (region.Text.Contains("40"))
            {
                return 40;
            }
            else
            {
                Logger.LogWarning("{LogPrefix}: could not recognize the Original Resin cost; assuming 20", logPrefix);
                return 20;
            }
        }
        else if (resinName == "浓缩树脂" || resinName == "脆弱树脂" || resinName == "须臾树脂")
        {
            return 1;
        }
        else
        {
            throw new ArgumentException("Unknown resin name");
        }
    }

    /// <summary>
    /// 判断两个区域在垂直方向上是否有重叠
    /// </summary>
    private static bool IsHeightOverlap(Region region1, Region region2)
    {
        int region1Top = region1.Y;
        int region1Bottom = region1.Y + region1.Height;
        int region2Top = region2.Y;
        int region2Bottom = region2.Y + region2.Height;

        // 检查区域是否在垂直方向上重叠
        return (region1Top <= region2Bottom && region1Bottom >= region2Top);
    }

    private async Task ArtifactSalvage()
    {
        if (!_taskParam.AutoArtifactSalvage)
        {
            return;
        }

        if (!int.TryParse(_taskParam.MaxArtifactStar, out var star))
        {
            star = 4;
        }

        await new AutoArtifactSalvageTask(_runtime).RunAsync(new AutoArtifactSalvageTaskParam(star, javaScript: null, artifactSetFilter: null, maxNumToCheck: null, recognitionFailurePolicy: null), _ct);
    }
}
