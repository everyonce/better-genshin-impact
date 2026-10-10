using BetterGenshinImpact.Core.Config;
using CommunityToolkit.Mvvm.ComponentModel;
using System;

namespace BetterGenshinImpact.Core.Script.Group;

[Serializable]
public partial class ScriptGroupConfig : ObservableObject
{
    [ObservableProperty]
    private PathingPartyConfig _pathingConfig = new();

    /// <summary>
    /// Shell 执行配置
    /// </summary>
    [ObservableProperty]
    private ShellConfig _shellConfig = new();
    
    /// <summary>
    /// 是否启用 Shell 执行配置
    /// </summary>
    [ObservableProperty]
    private bool _enableShellConfig;

    /// <summary>
    /// Allows this group to start before the game's main UI is available, for example during the initial tutorial.
    /// </summary>
    [ObservableProperty]
    private bool _allowNonMainUiStart;
}
