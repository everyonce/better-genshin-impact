using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.View.Controls;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class DynamicControlTests
{
    [Fact]
    public void CascadeSelectorTranslatesPresentationAndPreservesRawSelection() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var rawOptions = new Dictionary<string, List<string>>
        {
            ["启动"] = ["停止"]
        };
        var selector = new CascadeSelector { CascadeOptions = rawOptions, SelectedValue = "停止" };

        Assert.Equal("Stop", selector.SelectedDisplayValue);
        Assert.Equal("停止", selector.SelectedValue);
        Assert.Same(rawOptions, selector.CascadeOptions);
        Assert.Equal("启动", selector.FirstLevelOptions.Single());
        Assert.Equal("停止", selector.SecondLevelOptions.Single());

        var list = Assert.IsAssignableFrom<ListView>(typeof(CascadeSelector)
            .GetField("FirstLevelListView", BindingFlags.Instance | BindingFlags.NonPublic)!
            .GetValue(selector));
        list.ItemTemplate.Seal();
        var label = Assert.IsType<TextBlock>(list.ItemTemplate.LoadContent());
        label.DataContext = "启动";
        Drain();
        Assert.Equal("Start", label.Text);

        Exception? workerFailure = null;
        var worker = new Thread(() =>
        {
            try { I18nService.Instance.ChangeLanguage("zh-Hans"); }
            catch (Exception e) { workerFailure = e; }
        }) { IsBackground = true };
        worker.Start();
        Assert.True(worker.Join(TimeSpan.FromSeconds(5)));
        if (workerFailure != null) ExceptionDispatchInfo.Capture(workerFailure).Throw();
        Drain();
        Assert.Equal("停止", selector.SelectedDisplayValue);
        Assert.Equal("停止", selector.SelectedValue);
        Assert.Equal("启动", label.Text);
        I18nService.Instance.ChangeLanguage("en");
        Drain();
    });

    [Fact]
    public void TwoStateButtonTranslatesDefaultsAndRefreshesOnWorkerLanguageChange() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var enableCommand = new RoutedCommand();
        var disableCommand = new RoutedCommand();
        var button = new TwoStateButton
        {
            EnableCommand = enableCommand,
            DisableCommand = disableCommand
        };

        button.IsChecked = true;
        Assert.Equal("Stop", button.Content);
        Assert.Same(disableCommand, button.Command);
        button.IsChecked = false;
        Assert.Equal("Start", button.Content);
        Assert.Same(enableCommand, button.Command);

        Exception? workerFailure = null;
        var worker = new Thread(() =>
        {
            try { I18nService.Instance.ChangeLanguage("zh-Hans"); }
            catch (Exception e) { workerFailure = e; }
        }) { IsBackground = true };
        worker.Start();
        Assert.True(worker.Join(TimeSpan.FromSeconds(5)));
        if (workerFailure != null) ExceptionDispatchInfo.Capture(workerFailure).Throw();
        Drain();

        Assert.Equal("启动", button.Content);
        Assert.Same(enableCommand, button.Command);
        button.IsChecked = true;
        Assert.Equal("停止", button.Content);
        Assert.Same(disableCommand, button.Command);
        I18nService.Instance.ChangeLanguage("en");
        Drain();
        Assert.Equal("Stop", button.Content);
        Assert.Same(disableCommand, button.Command);
    });

    private static void Drain() => Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);

    private static void RunSta(Action action)
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try { action(); }
            catch (Exception e) { failure = e; }
            finally { Dispatcher.CurrentDispatcher.InvokeShutdown(); }
        }) { IsBackground = true };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(20)), "Dynamic control localization test timed out.");
        if (failure != null) ExceptionDispatchInfo.Capture(failure).Throw();
    }
}
