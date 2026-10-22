using Newtonsoft.Json;
using System;
using System.Threading;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;
using Microsoft.Extensions.Logging;
using BetterGenshinImpact.Core.Script.Repositories;

namespace BetterGenshinImpact.Core.Script.Dependence;

public class AutoPathingScript
{
    private object? _config = null;
    private string _rootPath;
    private readonly LimitedFile _autoPathingFile;

    /// <summary>Pulonia 已确认来源；为空时继续使用原用户目录。</summary>
    private readonly ScriptRepositoryResourceContext? _repositoryResources;

    /// <summary>
    /// 当前脚本执行的取消令牌。
    /// </summary>
    private readonly CancellationToken _ct;

    /// <summary>
    /// 本次脚本运行使用的运行环境，执行路线时交给 PathExecutor
    /// </summary>
    private readonly GameRuntime _runtime;

    /// <summary>
    /// 配置根，执行路线时交给 PathExecutor（与脚本传入的队伍配置 _config 不同）
    /// </summary>
    private readonly AllConfig _allConfig;

    /// <summary>
    /// 创建自动寻路脚本宿主。
    /// </summary>
    /// <param name="runtime">本次脚本运行使用的运行环境</param>
    /// <param name="allConfig">配置根</param>
    /// <param name="rootPath">脚本工作目录</param>
    /// <param name="config">脚本使用的队伍配置（PathingPartyConfig），可为空</param>
    /// <param name="ct">当前脚本执行的取消令牌</param>
    /// <param name="repositoryResources">Pulonia 已确认来源；为空时使用原用户目录</param>
    public AutoPathingScript(GameRuntime runtime, AllConfig allConfig, string rootPath, object? config, CancellationToken ct,
        ScriptRepositoryResourceContext? repositoryResources = null)
    {
        _runtime = runtime;
        _allConfig = allConfig;
        _config = config;
        _rootPath = rootPath;
        _ct = ct;
        _repositoryResources = repositoryResources;
        _autoPathingFile = new LimitedFile(Global.Absolute(@"User\AutoPathing"));
    }

    public async Task<bool> Run(string json)
    {
        // 登记本轮 JS 宿主操作；脚本停止后必须等待业务方法真正退出再释放游戏所有权。
        using var scriptOperation = ScriptHostOperations.Enter();
        var task = PathingTask.BuildFromJson(json);
        var pathExecutor = new PathExecutor(_runtime, _allConfig, _ct);
        if (_config != null && _config is PathingPartyConfig patyConfig)
        {
            pathExecutor.PartyConfig = patyConfig;
        }

        // JS 对外仍返回 bool，成功语义统一读取本次路线结果，不读取执行器成员状态。
        var result = await pathExecutor.Pathing(task);
        _ct.ThrowIfCancellationRequested();
        return result.IsSuccess;
    }

    /// <summary>
    /// Executes a quest route with dialogue skipping and route auto-pickup disabled.
    /// Unlike <see cref="Run"/>, errors and cancellation are allowed to reach the caller.
    /// </summary>
    public async Task RunForQuest(string json)
    {
        await RunQuestCore(json, _ct);
    }

    /// <summary>Runs a quest route with a local deadline without cancelling the owning script.</summary>
    public Task RunForQuestBounded(string json, int timeoutMilliseconds, CancellationToken cancellationToken)
        => RunBoundedQuest(token => RunQuestCore(json, token, true), InputHub.ReleaseAll,
            _ct, cancellationToken, timeoutMilliseconds);

    internal static async Task RunBoundedQuest(Func<CancellationToken, Task> action, Action release,
        CancellationToken ownerToken, CancellationToken requestToken, int timeoutMilliseconds)
    {
        if (timeoutMilliseconds is < 100 or > 60000)
            throw new ArgumentOutOfRangeException(nameof(timeoutMilliseconds));
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ownerToken, requestToken);
        deadline.CancelAfter(timeoutMilliseconds);
        try
        {
            deadline.Token.ThrowIfCancellationRequested();
            await action(deadline.Token);
        }
        finally
        {
            release();
        }
    }

    private async Task RunQuestCore(string json, CancellationToken cancellationToken, bool boundedTravel = false)
    {
        using var scriptOperation = ScriptHostOperations.Enter();
        cancellationToken.ThrowIfCancellationRequested();
        var task = PathingTask.BuildFromJson(json);
        var pathExecutor = new PathExecutor(_runtime, _allConfig, cancellationToken)
        {
            ScriptControlsDialogue = true,
            PartyConfig = BuildQuestPartyConfig(_config is PathingPartyConfig config
                ? config
                : PathingPartyConfig.BuildDefault())
        };

        if (boundedTravel)
        {
            pathExecutor.PartyConfig.Enabled = true;
            pathExecutor.PartyConfig.PartyName = "";
            pathExecutor.PartyConfig.AutoFightEnabled = false;
        }

        var result = await pathExecutor.Pathing(task);
        cancellationToken.ThrowIfCancellationRequested();
        if (!result.IsSuccess) throw new InvalidOperationException(result.ErrorMessage ?? "Quest route did not complete.");
    }

    /// <summary>
    /// Creates route-local settings while preserving the supplied combat and movement settings.
    /// This is public so the cloning and safety guarantees can be tested without game state.
    /// </summary>
    public static PathingPartyConfig BuildQuestPartyConfig(PathingPartyConfig source)
    {
        ArgumentNullException.ThrowIfNull(source);
        var clone = JsonConvert.DeserializeObject<PathingPartyConfig>(JsonConvert.SerializeObject(source))
                    ?? throw new JsonSerializationException("Could not clone pathing party configuration.");
        clone.AutoSkipEnabled = false;
        clone.AutoPickEnabled = false;
        return clone;
    }

    public async Task<bool> RunFile(string path)
    {
        using var scriptOperation = ScriptHostOperations.Enter();
        var json = await new LimitedFile(_rootPath).ReadText(path);
        return await Run(json);
    }

    /// <summary>
    /// 从已订阅的内容中获取文件
    /// </summary>
    /// <param name="path">在 `\User\AutoPathing` 目录下获取文件</param>
    /// <remarks>Pulonia 映射到脚本已确认仓库版本的 pathing/；资源缺失时明确失败。</remarks>
    public async Task<bool> RunFileFromUser(string path)
    {
        using var scriptOperation = ScriptHostOperations.Enter();
        // Pulonia 不再自动订阅路线；内部调用与顶层任务读取同一个已确认来源版本。
        var json = _repositoryResources is null ? await AutoPathingFile.ReadText(path)
            : await Task.Run(() => _repositoryResources.ReadPathingText(path), _ct);
        return await Run(json);
    }

    /// <summary>
    /// 判断 AutoPathing 目录下的路径是否存在
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的路径</param>
    /// <returns>存在返回 true，否则返回 false</returns>
    public bool IsExists(string subPath) => _repositoryResources is null ? AutoPathingFile.IsExists(subPath)
        : _repositoryResources.IsPathingFile(subPath) || _repositoryResources.IsPathingDirectory(subPath);

    /// <summary>
    /// 判断 AutoPathing 目录下的路径是否为文件
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的路径</param>
    /// <returns>是文件返回 true，否则返回 false</returns>
    public bool IsFile(string subPath) => _repositoryResources?.IsPathingFile(subPath) ?? AutoPathingFile.IsFile(subPath);

    /// <summary>
    /// 判断 AutoPathing 目录下的路径是否为文件夹
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的路径</param>
    /// <returns>是文件夹返回 true，否则返回 false</returns>
    public bool IsFolder(string subPath) => _repositoryResources?.IsPathingDirectory(subPath) ?? AutoPathingFile.IsFolder(subPath);

    /// <summary>
    /// 读取 AutoPathing 目录下指定文件夹的内容（非递归方式）
    /// 目录不存在时返回空数组，不会自动创建目录
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的子目录路径，默认为相对根目录</param>
    /// <returns>文件夹内所有文件和文件夹的相对路径数组，出错时返回空数组</returns>
    /// <remarks>Pulonia 查询已确认仓库版本；该上下文目录缺失时抛出异常。</remarks>
    public string[] ReadPathSync(string subPath = "./") => _repositoryResources?.ReadPathingDirectory(subPath) ?? AutoPathingFile.ReadPathSync(subPath);

    /// <summary>
    /// 读取 AutoPathing 目录下指定文件的文本内容
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的文件路径</param>
    /// <returns>文件文本内容，读取失败时返回空字符串</returns>
    /// <remarks>Pulonia 读取已确认仓库版本；该上下文文件缺失时抛出异常。</remarks>
    public string ReadTextSync(string subPath) => _repositoryResources?.ReadPathingText(subPath) ?? AutoPathingFile.ReadTextSync(subPath);

    /// <summary>
    /// LimitedFile 实例，用于操作 AutoPathing 目录
    /// </summary>
    private LimitedFile AutoPathingFile => _autoPathingFile;
}
