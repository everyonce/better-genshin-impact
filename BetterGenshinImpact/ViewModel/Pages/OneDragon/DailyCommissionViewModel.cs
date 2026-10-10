using BetterGenshinImpact.Service.I18n;
﻿using CommunityToolkit.Mvvm.ComponentModel;

namespace BetterGenshinImpact.ViewModel.Pages.OneDragon;

public partial class DailyCommissionViewModel : OneDragonBaseViewModel
{
    public override string Title { get; } = I18nService.Instance.Translate("每日委托");
}
