using BetterGenshinImpact.Model;
using BetterGenshinImpact.Service.Interface;
using BetterGenshinImpact.View.Windows;
using Microsoft.Extensions.Logging;
using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Wpf.Ui.Violeta.Controls;

namespace BetterGenshinImpact.Service;

/// <summary>
/// English distributions use this fork's releases. The upstream installer and
/// MirrorChyan channels replace the entire application with an upstream build.
/// </summary>
public class UpdateService : IUpdateService
{
    public const string EnglishReleasesUrl = "https://github.com/everyonce/better-genshin-impact/releases";
    private readonly ILogger<UpdateService> _logger;

    public UpdateService(IConfigService configService)
    {
        _logger = App.GetLogger<UpdateService>();
    }

    public async Task CheckUpdateAsync(UpdateOption option)
    {
        // This portable fork has no automatic installer/update feed. Do not send
        // startup checks to upstream or advertise an upstream build as an upgrade.
        if (option.Trigger != UpdateTrigger.Manual) return;
        var answer = await ThemedMessageBox.ShowAsync(
            "This English build uses manual updates. Download and unpack a newer English build separately.\n\n" +
            "If the fork's release page is empty, no downloadable update has been published.\n\nOpen the release page?",
            "English build updates",
            System.Windows.MessageBoxButton.YesNo);
        if (answer != System.Windows.MessageBoxResult.Yes) return;
        try
        {
            Process.Start(new ProcessStartInfo(EnglishReleasesUrl) { UseShellExecute = true });
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Could not open the English release page");
            await ThemedMessageBox.InformationAsync(
                $"Download English builds from {EnglishReleasesUrl}\n\nThe release page could not be opened: {exception.Message}");
        }
    }
}
