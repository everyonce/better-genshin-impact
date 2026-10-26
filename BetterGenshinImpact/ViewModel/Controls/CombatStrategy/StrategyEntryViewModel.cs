using System;
using BetterGenshinImpact.GameTask.AutoFight.Strategy;
using BetterGenshinImpact.Service.I18n;
using CommunityToolkit.Mvvm.ComponentModel;

namespace BetterGenshinImpact.ViewModel.Controls.CombatStrategy;

/// <summary>策略浏览器中的一行，承载后台读取的副标题及当前选中状态。</summary>
public partial class StrategyEntryViewModel : ObservableObject
{
    /// <summary>不可变目录节点。</summary>
    public CombatStrategyNode Node { get; }
    /// <summary>文件夹或文件图标文字。</summary>
    public string Icon => Node.IsFolder ? "📁" : IsCurrent ? "✓" : "";
    /// <summary>类型或子树计数。</summary>
    public string Badge => Node.IsFolder ? $"{Node.FileCount}  ›" : HasError ? I18nService.Instance.Translate("解析失败") : Node.Strategy?.Kind switch
    {
        CombatStrategyKind.Txt => "txt", CombatStrategyKind.Json => "JSON", _ => I18nService.Instance.Translate("键鼠"),
    };
    /// <summary>角色、录制信息或搜索结果路径。</summary>
    [ObservableProperty] private string _subtitle = "";
    /// <summary>是否解析失败。</summary>
    [ObservableProperty] private bool _hasError;
    /// <summary>是否为当前选中策略。</summary>
    [ObservableProperty] private bool _isCurrent;

    /// <summary>Translate only known metadata labels; preserve names, author text, durations and counts.</summary>
    internal static string LocalizeSummary(string summary, CombatStrategyKind? kind)
    {
        const string error = "解析失败：";
        if (summary.StartsWith(error, StringComparison.Ordinal))
            return string.Format(I18nService.Instance.Translate("解析失败：{0}"), I18nService.Instance.Translate(summary[error.Length..]));
        if (kind == CombatStrategyKind.Json && summary.StartsWith("作者 ", StringComparison.Ordinal))
            return string.Format(I18nService.Instance.Translate("作者 {0}"), summary[3..]);
        if (kind == CombatStrategyKind.KeyMouse)
        {
            const string size = "文件大小 ";
            if (summary.StartsWith(size, StringComparison.Ordinal))
                return string.Format(I18nService.Instance.Translate("文件大小 {0}"), summary[size.Length..]);
            const string duration = "时长 ";
            const string events = " 个事件";
            if (summary.StartsWith(duration, StringComparison.Ordinal) && summary.EndsWith(events, StringComparison.Ordinal))
            {
                var parts = summary[duration.Length..^events.Length].Split(" · ", StringSplitOptions.None);
                if (parts.Length == 2)
                    return string.Format(I18nService.Instance.Translate("时长 {0} · {1} 个事件"), parts[0], parts[1]);
            }
        }
        return summary;
    }

    /// <summary>创建列表行。</summary>
    public StrategyEntryViewModel(CombatStrategyNode node) => Node = node;
    /// <summary>刷新状态图标。</summary>
    partial void OnIsCurrentChanged(bool value) => OnPropertyChanged(nameof(Icon));
    /// <summary>刷新错误标签。</summary>
    partial void OnHasErrorChanged(bool value) => OnPropertyChanged(nameof(Badge));
}
