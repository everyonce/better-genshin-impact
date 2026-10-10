using BetterGenshinImpact.Service.I18n;
namespace BetterGenshinImpact.Helpers.Extensions;

public static class BooleanExtension
{
    public static string ToChinese(this bool enabled)
    {
        return enabled ? I18nService.Instance.Translate("已开启") : I18nService.Instance.Translate("已关闭");
    }
}
