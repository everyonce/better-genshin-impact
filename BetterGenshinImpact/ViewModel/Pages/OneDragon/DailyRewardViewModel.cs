using BetterGenshinImpact.Service.I18n;
﻿using CommunityToolkit.Mvvm.ComponentModel;

namespace BetterGenshinImpact.ViewModel.Pages.OneDragon;

public partial class DailyRewardViewModel : OneDragonBaseViewModel
{
    public override string Title { get; } = I18nService.Instance.Translate("领取每日奖励");
}
