using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.Model;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Vanara.PInvoke;
using BetterGenshinImpact.Service.I18n;
using Wpf.Ui.Violeta.Controls;

namespace BetterGenshinImpact.GameTask.QuickClaimReward;

public class OneKeyClaimRewardTask : Singleton<OneKeyClaimRewardTask>
{
    public const string ClickOnceMode = "点按一次";
    public const string HoldMode = "按住持续";

    private const int MaxClickCountPerRun = 30;
    private const int ScrollChunkSize = 10;
    private const int MaxBlankContinueChecks = 3;
    private const int ScrollRenderDelayMilliseconds = 120;
    private static readonly ILogger<OneKeyClaimRewardTask> Logger = App.GetLogger<OneKeyClaimRewardTask>();

    private readonly object _taskLock = new();
    private CancellationTokenSource? _cts;
    private Task? _claimTask;
    private volatile bool _isKeyDown;
    private DateTime _lastNoRewardLogTime = DateTime.MinValue;

    public void KeyDown()
    {
        if (_isKeyDown)
        {
            return;
        }

        _isKeyDown = true;
        if (!CanRun())
        {
            return;
        }

        if (IsHoldMode())
        {
            StartHoldTask();
        }
        else
        {
            StartClickOnceTask();
        }
    }

    public void KeyUp()
    {
        _isKeyDown = false;
        if (IsHoldMode())
        {
            _cts?.Cancel();
        }
    }

    private static bool CanRun()
    {
        if (!TaskContext.Instance().IsInitialized)
        {
            Toast.Warning(I18nService.Instance.Translate("请先启动"));
            return false;
        }

        return SystemControl.IsGenshinImpactActiveByProcess();
    }

    private void StartClickOnceTask()
    {
        lock (_taskLock)
        {
            if (_claimTask is { IsCompleted: false })
            {
                return;
            }

            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            _claimTask = Task.Run(() => ClaimCurrentPageAsync(_cts.Token));
        }
    }

    private void StartHoldTask()
    {
        lock (_taskLock)
        {
            if (_claimTask is { IsCompleted: false })
            {
                return;
            }

            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            _claimTask = Task.Run(() => ClaimWhileHoldingAsync(_cts.Token));
        }
    }

    private async Task ClaimCurrentPageAsync(CancellationToken ct)
    {
        try
        {
            var clickCount = 0;
            while (!ct.IsCancellationRequested && clickCount < MaxClickCountPerRun)
            {
                if (!await TryClaimOneRewardAsync(ct))
                {
                    break;
                }

                clickCount++;
                await Delay(180, ct);
            }

            if (clickCount == 0)
            {
                Logger.LogInformation("One-key reward claim: no claim icon found");
            }
            else
            {
                Logger.LogInformation("One-key reward claim: clicked {Count} claim icons this run", clickCount);
            }

            if (clickCount >= MaxClickCountPerRun)
            {
                Logger.LogWarning("One-key reward claim: reached the per-run click limit of {Count}; check whether claimable icons remain on the current screen", MaxClickCountPerRun);
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception e)
        {
            Logger.LogWarning(e, "One-key reward claim failed: {Message}", e.Message);
        }
    }

    private async Task ClaimWhileHoldingAsync(CancellationToken ct)
    {
        Logger.LogInformation("One-key reward claim: starting continuous claiming");
        try
        {
            while (!ct.IsCancellationRequested)
            {
                if (await TryClaimOneRewardAsync(ct))
                {
                    await Delay(180, ct);
                    continue;
                }

                if (CanScrollDown())
                {
                    LogNoReward("One-key reward claim: no claim icon found; scrolling down");
                    ScrollDown(ct);
                    await Delay(ScrollRenderDelayMilliseconds, ct);
                }
                else
                {
                    LogNoReward("One-key reward claim: no claim icon found");
                    await Delay(260, ct);
                }
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception e)
        {
            Logger.LogWarning(e, "One-key reward claim failed during continuous claiming: {Message}", e.Message);
        }
        finally
        {
            Logger.LogInformation("One-key reward claim: continuous claiming stopped");
        }
    }

    private async Task<bool> TryClaimOneRewardAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();

        using var capture = TaskControl.CaptureToRectArea();
        var candidate = FindRewardCandidates(capture).FirstOrDefault();
        if (candidate == null)
        {
            return false;
        }

        candidate.Region.Click();
        Logger.LogInformation("One-key reward claim: clicked {IconName} icon", candidate.Name);
        await PressEscIfBlankContinueShownAsync(ct);
        return true;
    }

    private static List<RewardCandidate> FindRewardCandidates(ImageRegion capture)
    {
        var candidates = new List<RewardCandidate>();

        candidates.AddRange(capture.FindMulti(RecognitionAssets.Get("QuickClaimReward", "ClaimText", capture))
            .Select(region => new RewardCandidate(region, "领取")));
        candidates.AddRange(capture.FindMulti(RecognitionAssets.Get("QuickClaimReward", "ClaimGift", capture))
            .Select(region => new RewardCandidate(region, "礼物领取")));

        return [.. candidates.OrderBy(candidate => candidate.Region.Top).ThenBy(candidate => candidate.Region.Left)];
    }

    private static async Task PressEscIfBlankContinueShownAsync(CancellationToken ct)
    {
        for (var i = 0; i < MaxBlankContinueChecks; i++)
        {
            await Delay(160, ct);

            using var capture = TaskControl.CaptureToRectArea();
            using var continueTip = capture.Find(RecognitionAssets.Get("QuickClaimReward", "ClickBlankContinue", capture));
            if (continueTip.IsEmpty())
            {
                continue;
            }

            InputHub.Foreground.Keyboard.KeyPress(User32.VK.VK_ESCAPE);
            Logger.LogInformation("One-key reward claim: detected the continue prompt and pressed ESC");
            await Delay(220, ct);
            return;
        }
    }

    private void LogNoReward(string message)
    {
        if ((DateTime.Now - _lastNoRewardLogTime).TotalSeconds < 2)
        {
            return;
        }

        _lastNoRewardLogTime = DateTime.Now;
        Logger.LogInformation(message);
    }

    private static bool IsHoldMode()
    {
        return TaskContext.Instance().Config.MacroConfig.OneKeyClaimRewardHotkeyMode == HoldMode;
    }

    private static bool CanScrollDown()
    {
        var config = TaskContext.Instance().Config.MacroConfig;
        return config.OneKeyClaimRewardHotkeyMode == HoldMode && config.OneKeyClaimRewardScrollDownEnabled;
    }

    private static void ScrollDown(CancellationToken ct)
    {
        var amount = Math.Max(1, Math.Abs(TaskContext.Instance().Config.MacroConfig.OneKeyClaimRewardScrollDownAmount));
        while (amount > 0)
        {
            ct.ThrowIfCancellationRequested();
            var scrollAmount = Math.Min(amount, ScrollChunkSize);
            InputHub.Foreground.Mouse.VerticalScroll(-scrollAmount);
            amount -= scrollAmount;
        }
    }

    private static async Task Delay(int millisecondsDelay, CancellationToken ct)
    {
        if (millisecondsDelay <= 0)
        {
            return;
        }

        await Task.Delay(millisecondsDelay, ct);
    }

    private sealed record RewardCandidate(Region Region, string Name);
}
