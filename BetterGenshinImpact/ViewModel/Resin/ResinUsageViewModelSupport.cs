using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using BetterGenshinImpact.GameTask.AutoBoss;
using BetterGenshinImpact.GameTask.AutoDomain;
using BetterGenshinImpact.GameTask.AutoLeyLineOutcrop;
using BetterGenshinImpact.GameTask.AutoStygianOnslaught;
using BetterGenshinImpact.GameTask.Common.Resin;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.GameTask.SoloTask;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.ViewModel.Resin;

/// <summary>树脂界面读取参数快照和解析任务能力的公共规则，不改写输入 JSON。</summary>
public static class ResinUsageViewModelSupport
{
    /// <summary>缺失、null 或格式错误时使用独立默认副本；合法结构中的无效业务值保留供编辑器提示。</summary>
    public static ResinUsage Read(JToken? value, ResinUsageCapability capability)
    {
        if (value is not JObject) return capability.Defaults;
        try { return SoloTaskJson.Deserialize<ResinUsage>(value.ToString(Newtonsoft.Json.Formatting.None)); }
        catch (System.Text.Json.JsonException) { return capability.Defaults; }
    }

    /// <summary>根据独立任务标识或 Pulonia 任务类型返回任务名与同一份能力声明。</summary>
    public static (string Name, ResinUsageCapability Capability)? GetTask(string? taskType)
        => taskType switch
        {
            "auto_domain" or "solo.auto_domain" => ("自动秘境", AutoDomainTask.ResinCapability),
            "auto_stygian_onslaught" or "solo.auto_stygian_onslaught" => ("自动幽境危战", AutoStygianOnslaughtTask.ResinCapability),
            "auto_boss" or "solo.auto_boss" => ("自动首领讨伐", AutoBossTask.ResinCapability),
            "auto_ley_line_outcrop" or "solo.auto_ley_line_outcrop" => ("自动地脉花", AutoLeyLineOutcropTask.ResinCapability),
            _ => null
        };

    /// <summary>Localize presentation only; task validation and Chinese OCR names remain unchanged.</summary>
    public static string? Problem(ResinUsage value, ResinUsageCapability capability)
    {
        var problem = value.Validate(capability);
        if (problem is null) return null;
        // Match only the task formatter's four named templates, without re-running its policy.
        foreach (var kind in ResinKinds.InOrder)
        {
            var name = ResinUsageText.DisplayName(kind);
            foreach (var template in new[] { "{0}领奖次数须为 0–999。", "此任务不能使用{0}，领奖次数须为 0。", "此任务不能使用{0}。", "此任务必须开启{0}。" })
                if (problem == string.Format(template, name))
                    return string.Format(I18nService.Instance.Translate(template), I18nService.Instance.Translate(name));
        }
        return I18nService.Instance.Translate(problem);
    }

    /// <summary>Render the same validated order/count/tier summary using localized display fragments.</summary>
    public static string Summary(ResinUsage value, ResinUsageCapability capability)
    {
        if (Problem(value, capability) is { } problem) return problem;
        var kinds = ResinKinds.InOrder.Where(kind => value.Mode == ResinUsageMode.PerType
            ? value.Counts[kind] > 0 : value.Allowed[kind]);
        var sequence = string.Join(" → ", kinds.Select(kind => value.Mode == ResinUsageMode.PerType
            ? string.Format(I18nService.Instance.Translate("{0} {1} 次"), I18nService.Instance.Translate(ResinUsageText.ShortName(kind)), value.Counts[kind])
            : I18nService.Instance.Translate(ResinUsageText.ShortName(kind))));
        var summary = value.Mode switch
        {
            ResinUsageMode.Exhaust => string.Format(I18nService.Instance.Translate("刷至树脂耗尽 · {0}"), sequence),
            ResinUsageMode.RunCount => string.Format(I18nService.Instance.Translate("领奖 {0} 次 · {1}"), value.RunCount, sequence),
            _ => sequence
        };
        return value.OriginalTier == OriginalResinTier.Default ? summary
            : string.Format(I18nService.Instance.Translate("{0} · 原粹{1}"), summary, I18nService.Instance.Translate(ResinUsageText.TierDisplayName(value.OriginalTier)));
    }

    /// <summary>Translate the crafting display without changing its legacy nonpositive-value meaning.</summary>
    public static string CraftSummary(int keep)
        => keep <= 0 ? I18nService.Instance.Translate("按默认数量合成")
            : string.Format(I18nService.Instance.Translate("合成后保留 {0} 原粹树脂"), keep);

    /// <summary>Translate the actual task-provided row description, including its named fallback and exhaust suffix.</summary>
    public static string KindDescription(ResinKind kind, ResinUsageMode mode, ResinUsageCapability capability)
    {
        var description = ResinUsageText.KindDescription(kind, mode, capability);
        var name = ResinUsageText.DisplayName(kind);
        if (description == $"此任务不能使用{name}")
            return string.Format(I18nService.Instance.Translate("此任务不能使用{0}"), I18nService.Instance.Translate(name));
        const string untilEmpty = "，直到用完";
        return description.EndsWith(untilEmpty, StringComparison.Ordinal)
            ? string.Format(I18nService.Instance.Translate("{0}，直到用完"), I18nService.Instance.Translate(description[..^untilEmpty.Length]))
            : I18nService.Instance.Translate(description);
    }

    /// <summary>Localize the existing replenish/direct confirmation without changing the enabled resin.</summary>
    public static string EnableSupplementMessage(ResinKind kind, ResinKindSupport support)
        => string.Format(I18nService.Instance.Translate(support == ResinKindSupport.Replenish
            ? "刷至树脂耗尽时，原粹不足 40 会持续用{0}补充，直到用完。\n确定开启吗？"
            : "刷至树脂耗尽时，浓缩和原粹不足后会持续使用{0}，直到用完。\n确定开启吗？"),
            I18nService.Instance.Translate(ResinUsageText.DisplayName(kind)));

    /// <summary>Render the enabled supplement list in the existing combined exhaust confirmation.</summary>
    public static string SwitchToExhaustMessage(IEnumerable<ResinKind> kinds)
        => string.Format(I18nService.Instance.Translate("已开启{0}。刷至树脂耗尽会持续使用它们，直到用完。\n是否继续使用？"),
            string.Join(I18nService.Instance.Translate("、"), kinds.Select(kind => I18nService.Instance.Translate(ResinUsageText.DisplayName(kind)))));

    /// <summary>静态 Schema 字段工厂没有 DI，允许显式注入，否则仅在真实应用中获取服务；隔离容器和离屏测试不启动 App。</summary>
    public static IResinSettingsDialogs? ResolveDialogs(IResinSettingsDialogs? dialogs)
    {
        if (dialogs is not null || Application.Current is not App) return dialogs;
        try { return App.GetService<IResinSettingsDialogs>(); }
        catch (InvalidOperationException) { return null; }
    }
}
