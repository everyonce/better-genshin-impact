using System.ComponentModel;
using System.Globalization;
using System.Runtime.ExceptionServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Threading;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.View.Converters;
using BetterGenshinImpact.View.Controls;
using Wpf.Ui.Violeta.Controls;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class DropdownLocalizationTests
{
    private enum ExampleOption { [Description("启动")] Start }

    [Fact]
    public void EnumSelectionRoundTripKeepsItsOriginalKeyValuePair()
    {
        var converter = new EnumToKVPConverter();
        var option = Assert.IsType<KeyValuePair<Enum, string>>(
            converter.Convert(ExampleOption.Start, typeof(object), null, CultureInfo.InvariantCulture));
        Assert.Equal("启动", option.Value);
        Assert.Equal(ExampleOption.Start, converter.ConvertBack(option, typeof(ExampleOption), null, CultureInfo.InvariantCulture));
        Assert.All(OptionTextConverter.Instance.ConvertBack("Start", [typeof(string), typeof(long)], null!, CultureInfo.InvariantCulture),
            value => Assert.Same(Binding.DoNothing, value));
    }

    [Fact]
    public void DisplayBindingChangesLanguageWithoutChangingSelectionOrSource() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        string[] source = ["启动", "my-script.json"];
        var comboBox = new ComboBox { ItemsSource = source, SelectedItem = source[0] };
        OptionDisplay.SetPath(comboBox, string.Empty);
        // A real items presenter seals the template before instantiating it.
        comboBox.ItemTemplate.Seal();
        var text = Assert.IsType<TextBlock>(comboBox.ItemTemplate.LoadContent());
        text.DataContext = comboBox.SelectedItem;
        DrainBindings();
        Assert.Equal("Start", text.Text);
        Assert.Same(source, comboBox.ItemsSource);
        Assert.Equal("启动", comboBox.SelectedItem);
        I18nService.Instance.ChangeLanguage("zh-Hans");
        DrainBindings();
        Assert.Equal("启动", text.Text);
        Assert.Equal("启动", source[0]);
        I18nService.Instance.ChangeLanguage("en");
        DrainBindings();
        Assert.Equal("Start", text.Text);
        Assert.Equal("my-script.json", OptionDisplay.Translate(source[1]));
        Assert.Equal("Start", OptionDisplay.Translate(ExampleOption.Start));
    });

    [Fact]
    public void CascadingLabelsRefreshWhileChildIdentityAndStoredNamesRemainStable() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var parent = new LocalizedCascadingItem("启动", Enumerable.Range(0, 1).Select(_ =>
            (ICascadingItem)new LocalizedCascadingItem("启动") { Tag = "无相之雷" }));
        var child = Assert.IsType<LocalizedCascadingItem>(parent.Children!.Single());
        Assert.Same(parent.Children!.Single(), parent.Children!.Single());
        Assert.Equal("Start", child.Label);
        Assert.Equal("无相之雷", new AutoBossNameToCascadingItemConverter().ConvertBack(child, typeof(string), null!, CultureInfo.InvariantCulture));
        Assert.Equal("无相之雷", new DomainNameToCascadingItemConverter().ConvertBack(child, typeof(string), null!, CultureInfo.InvariantCulture));
        var changed = false;
        child.PropertyChanged += (_, e) => changed |= e.PropertyName == nameof(child.Label);
        I18nService.Instance.ChangeLanguage("zh-Hans");
        Assert.True(changed);
        Assert.Equal("启动", child.Label);
        Assert.Equal("无相之雷", child.Tag);
        I18nService.Instance.ChangeLanguage("en");
    });

    private static void DrainBindings() => Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);

    [Fact]
    public void MultiSelectTranslatesSummaryAndKeepsOriginalSelectedValues() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var selected = new System.Collections.ObjectModel.ObservableCollection<string> { "启动" };
        var control = new MultiSelectComboBox { ItemsSource = new[] { "启动", "my-script.json" }, SelectedItems = selected };
        Assert.Equal("Start", control.SelectionText);
        I18nService.Instance.ChangeLanguage("zh-Hans");
        Assert.Equal("启动", control.SelectionText);
        Assert.Equal(new[] { "启动" }, selected);
        I18nService.Instance.ChangeLanguage("en");
        Assert.Equal("Start", control.SelectionText);
        selected.Add("my-script.json");
        Assert.Contains("my-script.json", control.SelectionText);
        Assert.Equal(new[] { "启动", "my-script.json" }, selected);
    });

    [Fact]
    public void MultiSelectLanguageChangeFromWorkerRefreshesOnOwnerDispatcher() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var selected = new System.Collections.ObjectModel.ObservableCollection<string> { "启动" };
        var control = new MultiSelectComboBox { ItemsSource = new[] { "启动" }, SelectedItems = selected };
        Exception? workerFailure = null;
        var worker = new Thread(() =>
        {
            try { I18nService.Instance.ChangeLanguage("zh-Hans"); }
            catch (Exception e) { workerFailure = e; }
        }) { IsBackground = true };
        worker.Start();
        Assert.True(worker.Join(TimeSpan.FromSeconds(5)));
        if (workerFailure != null) ExceptionDispatchInfo.Capture(workerFailure).Throw();
        // The worker must queue the refresh, not touch the owner's collection view.
        Assert.Equal("Start", control.SelectionText);
        DrainBindings();
        Assert.Equal("启动", control.SelectionText);
        Assert.Equal(new[] { "启动" }, selected);
        I18nService.Instance.ChangeLanguage("en");
    });

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
        Assert.True(thread.Join(TimeSpan.FromSeconds(20)), "WPF display test did not complete.");
        if (failure != null) ExceptionDispatchInfo.Capture(failure).Throw();
    }
}
