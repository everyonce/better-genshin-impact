using System.Globalization;
using System.Runtime.CompilerServices;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.ViewModel.Windows;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Protect the translated RDP control that restores manual mouse and keyboard input.</summary>
public sealed class ChildSessionControlCenterLocalizationTests : IDisposable
{
    /// <summary>Restore the caller's UI language after changing the shared translation service.</summary>
    private readonly CultureInfo _originalCulture = CultureInfo.CurrentUICulture;

    /// <summary>Preserve the default UI culture used by other tests and worker threads.</summary>
    private readonly CultureInfo? _originalThreadCulture = CultureInfo.DefaultThreadCurrentUICulture;

    /// <summary>Exercise the same English translation service used by the RDP menu.</summary>
    public ChildSessionControlCenterLocalizationTests()
    {
        I18nService.Instance.ChangeLanguage("en");
    }

    /// <summary>Both actions must be readable and explain whether local input will be restored or blocked.</summary>
    [Theory]
    [InlineData(false, "Watch Mode", "View the virtual desktop without sending mouse or keyboard input.")]
    [InlineData(true, "Control Mode", "Exit Watch Mode and restore mouse and keyboard control.")]
    public void WatchModeMenuExplainsTheAvailableInputAction(bool watchModeEnabled, string expectedHeader, string expectedToolTip)
    {
        var viewModel = CreatePresentationModel();
        viewModel.IsWatchModeEnabled = watchModeEnabled;

        Assert.Equal(expectedHeader, viewModel.WatchModeMenuHeader);
        Assert.Equal(expectedToolTip, viewModel.WatchModeMenuToolTip);
    }

    /// <summary>A mode change must refresh the action text and tooltip already bound by the menu.</summary>
    [Fact]
    public void WatchModeChangeRefreshesBothMenuBindings()
    {
        var viewModel = CreatePresentationModel();
        var changedProperties = new List<string?>();
        viewModel.PropertyChanged += (_, args) => changedProperties.Add(args.PropertyName);

        viewModel.IsWatchModeEnabled = true;

        Assert.Contains(nameof(viewModel.WatchModeMenuHeader), changedProperties);
        Assert.Contains(nameof(viewModel.WatchModeMenuToolTip), changedProperties);
        Assert.Equal("Control Mode", viewModel.WatchModeMenuHeader);

        changedProperties.Clear();
        viewModel.IsWatchModeEnabled = false;

        Assert.Contains(nameof(viewModel.WatchModeMenuHeader), changedProperties);
        Assert.Contains(nameof(viewModel.WatchModeMenuToolTip), changedProperties);
        Assert.Equal("Watch Mode", viewModel.WatchModeMenuHeader);
    }

    /// <summary>Test the pure presentation properties without starting RDP services or dispatcher timers.</summary>
    private static ChildSessionWindowViewModel CreatePresentationModel() =>
        (ChildSessionWindowViewModel)RuntimeHelpers.GetUninitializedObject(typeof(ChildSessionWindowViewModel));

    /// <summary>Restore shared localization state so this fixture cannot change later test behavior.</summary>
    public void Dispose()
    {
        I18nService.Instance.ChangeLanguage(_originalCulture.Name);
        CultureInfo.CurrentUICulture = _originalCulture;
        CultureInfo.DefaultThreadCurrentUICulture = _originalThreadCulture;
    }
}
