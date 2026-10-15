using System;
using BetterGenshinImpact.GameTask.AutoPathing;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using System.Threading.Tasks;
using System.Threading;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Common;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;

namespace BetterGenshinImpact.Core.Script.Dependence;

public class AutoPathingScript
{
    private object? _config = null;
    private string _rootPath;
    private readonly LimitedFile _autoPathingFile;

    public AutoPathingScript(string rootPath, object? config)
    {
        _config = config;
        _rootPath = rootPath;
        _autoPathingFile = new LimitedFile(Global.Absolute(@"User\AutoPathing"));
    }

    public async Task Run(string json)
    {
        try
        {
            var task = PathingTask.BuildFromJson(json);
            var pathExecutor = new PathExecutor(CancellationContext.Instance.Cts.Token);
            if (_config != null && _config is PathingPartyConfig patyConfig)
            {
                pathExecutor.PartyConfig = patyConfig;
            }

            await pathExecutor.Pathing(task);
        }
        catch (Exception e)
        {
            TaskControl.Logger.LogDebug(e,"An error occurred while executing pathing.");
            TaskControl.Logger.LogError("An error occurred while executing pathing: {Msg}",e.Message);
        }
    }

    /// <summary>
    /// Executes a quest route with dialogue skipping and route auto-pickup disabled.
    /// Unlike <see cref="Run"/>, errors and cancellation are allowed to reach the caller.
    /// </summary>
    public async Task RunForQuest(string json)
    {
        await RunQuestCore(json, CancellationContext.Instance.Cts.Token);
    }

    /// <summary>Runs a quest route with a local deadline without cancelling the owning script.</summary>
    public Task RunForQuestBounded(string json, int timeoutMilliseconds, CancellationToken cancellationToken)
        => RunBoundedQuest(token => RunQuestCore(json, token, true), InputHub.ReleaseAll,
            CancellationContext.Instance.Cts.Token, cancellationToken, timeoutMilliseconds);

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
        cancellationToken.ThrowIfCancellationRequested();
        var task = PathingTask.BuildFromJson(json);
        var pathExecutor = new PathExecutor(cancellationToken)
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

        await pathExecutor.Pathing(task);
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

    public async Task RunFile(string path)
    {
        try
        {
            var json = await new LimitedFile(_rootPath).ReadText(path);
            await Run(json);
        }
        catch (Exception e)
        {
            TaskControl.Logger.LogDebug(e,"An error occurred while reading the file.");
            TaskControl.Logger.LogError("An error occurred while reading the file: {Msg}",e.Message);
        }
    }

    /// <summary>
    /// 从已订阅的内容中获取文件
    /// </summary>
    /// <param name="path">在 `\User\AutoPathing` 目录下获取文件</param>
    public async Task RunFileFromUser(string path)
    {
        var json = await AutoPathingFile.ReadText(path);
        await Run(json);
    }

    /// <summary>
    /// 判断 AutoPathing 目录下的路径是否存在
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的路径</param>
    /// <returns>存在返回 true，否则返回 false</returns>
    public bool IsExists(string subPath) => AutoPathingFile.IsExists(subPath);

    /// <summary>
    /// 判断 AutoPathing 目录下的路径是否为文件
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的路径</param>
    /// <returns>是文件返回 true，否则返回 false</returns>
    public bool IsFile(string subPath) => AutoPathingFile.IsFile(subPath);

    /// <summary>
    /// 判断 AutoPathing 目录下的路径是否为文件夹
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的路径</param>
    /// <returns>是文件夹返回 true，否则返回 false</returns>
    public bool IsFolder(string subPath) => AutoPathingFile.IsFolder(subPath);

    /// <summary>
    /// 读取 AutoPathing 目录下指定文件夹的内容（非递归方式）
    /// 目录不存在时返回空数组，不会自动创建目录
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的子目录路径，默认为相对根目录</param>
    /// <returns>文件夹内所有文件和文件夹的相对路径数组，出错时返回空数组</returns>
    public string[] ReadPathSync(string subPath = "./") => AutoPathingFile.ReadPathSync(subPath);

    /// <summary>
    /// 读取 AutoPathing 目录下指定文件的文本内容
    /// </summary>
    /// <param name="subPath">相对于 User\AutoPathing 的文件路径</param>
    /// <returns>文件文本内容，读取失败时返回空字符串</returns>
    public string ReadTextSync(string subPath) => AutoPathingFile.ReadTextSync(subPath);

    /// <summary>
    /// LimitedFile 实例，用于操作 AutoPathing 目录
    /// </summary>
    private LimitedFile AutoPathingFile => _autoPathingFile;
}
