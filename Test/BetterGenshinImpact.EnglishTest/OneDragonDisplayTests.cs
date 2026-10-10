using System.IO;
using System.Runtime.ExceptionServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Threading;
using System.Xml.Linq;
using BetterGenshinImpact.Core.Script.Group;
using BetterGenshinImpact.Model;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.ViewModel.Pages;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class OneDragonDisplayTests
{
    public sealed class PickerState
    {
        public object[] ConfigList { get; set; } = [];
        public object? SelectedConfig { get; set; }
    }
    private static readonly XNamespace Wpf = "http://schemas.microsoft.com/winfx/2006/xaml/presentation";
    private static readonly XNamespace Xaml = "http://schemas.microsoft.com/winfx/2006/xaml";

    private static XDocument Page() => XDocument.Load(Path.Combine(AppContext.BaseDirectory,
        "ValidationSources", "OneDragonFlowPage.xaml"));

    // Load the production display markup, not a test copy of the binding. Page event
    // handlers and application styles are excluded; these tests never start the app/game.
    private static T LoadDisplay<T>(XElement productionElement) where T : FrameworkElement
    {
        var element = new XElement(productionElement);
        element.RemoveNodes();
        const string localNamespace = "clr-namespace:BetterGenshinImpact.Service.I18n";
        XNamespace assemblyNamespace = localNamespace + ";assembly=BetterGI";
        foreach (var attribute in element.Attributes().Where(a => a.Name.NamespaceName == localNamespace).ToList())
        {
            element.SetAttributeValue(assemblyNamespace + attribute.Name.LocalName, attribute.Value);
            attribute.Remove();
        }
        element.SetAttributeValue(XNamespace.Xmlns + "i18n", assemblyNamespace.NamespaceName);
        return Assert.IsType<T>(XamlReader.Parse(element.ToString()));
    }

    [Fact]
    public void ActualPopupAndTaskListTranslateEveryBuiltInTaskWithoutChangingIdentifiers() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var page = Page();
        var popup = page.Descendants(Wpf + "ItemsControl")
            .Single(e => (string?)e.Attribute(Xaml + "Name") == "ScriptGroupItemsControl");
        var checkboxMarkup = popup.Descendants(Wpf + "CheckBox").Single();
        var taskLabelMarkup = page.Descendants(Wpf + "TextBlock")
            .Single(e => (string?)e.Attribute("Text") is "{i18n:TB Name}" or "{Binding Name}");
        string[] expected = ["Claim Mail", "Craft Resin", "Auto Domain", "Auto Boss Hunt",
            "Auto Stygian Onslaught", "Auto Ley Line Blossom", "Claim Daily Rewards", "Claim Serenitea Pot Rewards"];
        Assert.Equal(expected.Length, OneDragonFlowViewModel.BuiltInTaskNames.Count);
        foreach (var (rawName, english) in OneDragonFlowViewModel.BuiltInTaskNames.Zip(expected))
        {
            var group = new ScriptGroup { Name = rawName };
            var checkbox = LoadDisplay<CheckBox>(checkboxMarkup);
            checkbox.DataContext = group;
            var task = new OneDragonTaskItem(rawName);
            var label = LoadDisplay<TextBlock>(taskLabelMarkup);
            label.DataContext = task;
            Drain();
            Assert.Equal(english, checkbox.Content);
            Assert.Equal(english, label.Text);
            Assert.Same(group, checkbox.Tag);
            checkbox.IsChecked = true;
            Assert.Equal(rawName, ((ScriptGroup)checkbox.Tag).Name);
            Assert.Equal(rawName, task.Name);
            I18nService.Instance.ChangeLanguage("zh-Hans");
            Drain();
            Assert.Equal(rawName, checkbox.Content);
            I18nService.Instance.ChangeLanguage("en");
            Drain();
            Assert.Equal(english, checkbox.Content);
        }
        var custom = LoadDisplay<CheckBox>(checkboxMarkup);
        custom.DataContext = new ScriptGroup { Name = "My evening routes" };
        Drain();
        Assert.Equal("My evening routes", custom.Content);
    });

    [Fact]
    public void ActualConfigPickerDisplaysEnglishDefaultAndPreservesSelectedObject() => RunSta(() =>
    {
        I18nService.Instance.ChangeLanguage("en");
        var markup = Page().Descendants(Wpf + "ComboBox")
            .Single(e => (string?)e.Attribute("ItemsSource") == "{Binding ConfigList}");
        var picker = LoadDisplay<ComboBox>(markup);
        var config = new { Name = "默认配置" };
        picker.DataContext = new PickerState { ConfigList = [config], SelectedConfig = config };
        Drain();
        picker.ItemTemplate.Seal();
        var label = Assert.IsType<TextBlock>(picker.ItemTemplate.LoadContent());
        label.DataContext = picker.SelectedItem;
        Drain();
        Assert.Equal("Default Configuration", label.Text);
        Assert.Same(config, picker.SelectedItem);
        Assert.Equal("默认配置", config.Name);
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
        Assert.True(thread.Join(TimeSpan.FromSeconds(20)), "One Dragon display test timed out.");
        if (failure != null) ExceptionDispatchInfo.Capture(failure).Throw();
    }
}
