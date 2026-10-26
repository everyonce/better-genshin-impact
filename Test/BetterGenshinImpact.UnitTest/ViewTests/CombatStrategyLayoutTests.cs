using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Runtime.ExceptionServices;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using BetterGenshinImpact.GameTask.AutoFight.Strategy;
using BetterGenshinImpact.GameTask.Common.Resin;
using BetterGenshinImpact.View.Controls.CombatStrategy;
using BetterGenshinImpact.View.Controls.Resin;
using BetterGenshinImpact.ViewModel.Controls.CombatStrategy;
using BetterGenshinImpact.ViewModel.Resin;
using CommunityToolkit.Mvvm.Input;

namespace BetterGenshinImpact.UnitTest.ViewTests;

/// <summary>Serializes the process-wide WPF resources and binding trace listener.</summary>
[CollectionDefinition("Offscreen combat layout", DisableParallelization = true)]
public sealed class CombatStrategyLayoutCollection { }

/// <summary>Constructs real templates off-screen; never creates the application host or opens a window.</summary>
[Collection("Offscreen combat layout")]
public sealed class CombatStrategyLayoutTests
{
    /// <summary>Checks all three category templates, empty-result Runs and shared resin rows on one dedicated STA.</summary>
    [Fact]
    public void CategoryTemplatesAndResinEditors_ConstructAndStretchWithoutBindingErrors()
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try { CheckOnSta(); }
            catch (Exception error) { failure = ExceptionDispatchInfo.Capture(error); }
        }) { IsBackground = true, Name = "Offscreen combat layout" };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(30)), "Off-screen layout exceeded 30 seconds; stop this test host.");
        failure?.Throw();
    }

    /// <summary>Owns one plain Application, software rendering and temporary diagnostics; no App.xaml or services.</summary>
    private static void CheckOnSta()
    {
        Assert.Null(Application.Current);
        var oldRenderMode = RenderOptions.ProcessRenderMode;
        var trace = PresentationTraceSources.DataBindingSource;
        var oldLevel = trace.Switch.Level;
        using var errors = new BindingErrors();
        Application? application = null;
        RenderOptions.ProcessRenderMode = RenderMode.SoftwareOnly;
        trace.Switch.Level = SourceLevels.Error;
        trace.Listeners.Add(errors);
        try
        {
            application = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            // Only the same WPF-UI theme/control dictionaries used by App.xaml; no application constructor.
            // Typed references load WPF-UI before its compiled resource dictionaries are resolved.
            application.Resources.MergedDictionaries.Add(new Wpf.Ui.Markup.ThemesDictionary
            {
                Theme = Wpf.Ui.Appearance.ApplicationTheme.Dark
            });
            application.Resources.MergedDictionaries.Add(new Wpf.Ui.Markup.ControlsDictionary());
            CheckCategories();
            CheckResinEditors();
            Assert.Empty(application.Windows.Cast<Window>());
            Assert.Equal(RenderMode.SoftwareOnly, RenderOptions.ProcessRenderMode);
            Assert.True(errors.Text.Length == 0, errors.Text);
        }
        finally
        {
            // Restore shared diagnostics even when template construction, binding or layout fails.
            trace.Listeners.Remove(errors);
            trace.Switch.Level = oldLevel;
            try { application?.Shutdown(); }
            finally
            {
                RenderOptions.ProcessRenderMode = oldRenderMode;
                Dispatcher.CurrentDispatcher.InvokeShutdown();
            }
        }
    }

    /// <summary>Uses real category data with inert callbacks; no root VM Attach/Open, directory load or combo Refresh.</summary>
    private static void CheckCategories()
    {
        var browser = new StrategyBrowserViewModel(CombatStrategyKind.Txt, "Fixture text strategies", _ => UnexpectedAction());
        var node = new CombatStrategyNode
        {
            Name = "Fixture strategy", RelativePath = "fixture.txt", FileCount = 1,
            Strategy = new CombatStrategyRef(CombatStrategyKind.Txt, "fixture.txt", "fixture.txt", "Fixture strategy", true)
        };
        browser.Entries.Add(new StrategyEntryViewModel(node) { Subtitle = "In-memory fixture", IsCurrent = true });
        browser.Breadcrumb.Add(new CombatStrategyNode { Name = "Fixture root", RelativePath = "", IsFolder = true });
        var automatic = new AutoMatchCategoryViewModel(_ => UnexpectedAction(), UnexpectedAction);
        automatic.Scopes.Add(new AutoMatchScopeViewModel(
            new CombatStrategyNode { Name = "Fixture scope", RelativePath = "", IsFolder = true, FileCount = 2 }, true));
        var combo = new ComboCategoryViewModel(_ => UnexpectedAction()) { StatusText = "Fixture status; no runtime session read." };
        var alternatives = new StrategyBrowserViewModel(CombatStrategyKind.Json, "Alternative fixture", _ => UnexpectedAction()) { MatchCount = 2 };
        var categories = new StrategyCategoryViewModel[] { browser, automatic, combo };
        var types = new[] { typeof(StrategyBrowserView), typeof(AutoMatchView), typeof(ComboView) };
        for (var index = 0; index < categories.Length; index++)
        {
            var data = new PickerData(categories, categories[index], alternatives);
            var panel = new CombatStrategyPickerPanel { DataContext = data };
            var template = Assert.IsType<DataTemplate>(panel.FindResource(new DataTemplateKey(categories[index].GetType())));
            // Standalone child construction must not need resources from a parent that has not been attached yet.
            Assert.Equal(types[index], template.LoadContent().GetType());
            Layout(panel);
            var host = Assert.IsType<ContentControl>(panel.FindName("CategoryContent"));
            Assert.Equal(HorizontalAlignment.Stretch, host.HorizontalContentAlignment);
            Assert.Equal(VerticalAlignment.Stretch, host.VerticalContentAlignment);
            var child = Descendants(panel).OfType<FrameworkElement>().Single(view => view.GetType() == types[index]);
            Assert.True(host.ActualWidth > 400, "The category content column was squeezed.");
            Assert.InRange(Math.Abs(child.ActualWidth - host.ActualWidth), 0, 1);
            Assert.Same(categories[index], child.DataContext);
            if (ReferenceEquals(categories[index], browser))
            {
                Assert.Contains(Descendants(child).OfType<TextBlock>(), text => text.Text == node.Name);
                // Exercise the empty-result template's read-only Title/MatchCount Run bindings as well.
                browser.ApplySearch("no recorded data is read");
                Layout(panel);
                var runs = Descendants(child).OfType<TextBlock>().SelectMany(text => text.Inlines.OfType<Run>()).ToArray();
                Assert.Contains(runs, run => run.Text == alternatives.Title);
                Assert.Contains(runs, run => run.Text == "2");
                foreach (var run in runs)
                    if (BindingOperations.GetBinding(run, Run.TextProperty) is { } binding)
                        Assert.Equal(BindingMode.OneWay, binding.Mode);
            }
            if (ReferenceEquals(categories[index], automatic))
                Assert.Contains(Descendants(child).OfType<TextBlock>(), text => text.Text == automatic.Scopes[0].Name);
            if (ReferenceEquals(categories[index], combo))
                Assert.Contains(Descendants(child).OfType<TextBlock>(), text => text.Text == combo.StatusText);
        }
    }

    /// <summary>Constructs shared editors with finite in-memory values and rejects any confirmation callback.</summary>
    private static void CheckResinEditors()
    {
        foreach (var mode in Enum.GetValues<ResinUsageMode>())
        {
            var value = ResinCapabilities.Domain.Defaults;
            value.Mode = mode;
            value.RunCount = 7;
            value.Counts.Condensed = 2;
            var model = new ResinUsageEditorViewModel("Fixture task", ResinCapabilities.Domain, value,
                _ => throw new InvalidOperationException("Layout must not ask for confirmation."));
            var view = new ResinUsageEditorView(model);
            Layout(view);
            var rows = Descendants(view).OfType<ItemsControl>().Single(items => ReferenceEquals(items.ItemsSource, model.Kinds));
            Assert.Equal(4, rows.Items.Count);
            Assert.All(model.Kinds, kind => Assert.Contains(Descendants(view).OfType<TextBlock>(), text => text.Text == kind.DisplayName));
            Assert.True(view.ActualWidth >= 800);
            Assert.Equal(value, model.BuildValue());
            Assert.True(model.PendingConfirmation.IsCompletedSuccessfully);
        }
        var craft = new CraftResinEditorViewModel(40);
        Layout(new CraftResinEditorView(craft));
        Assert.Equal(40, craft.BuildValue());
    }

    /// <summary>Measures an unattached tree only: never shows a window/popup, attaches an HwndSource or sends input.</summary>
    private static void Layout(FrameworkElement view)
    {
        view.Measure(new Size(900, 900));
        view.Arrange(new Rect(0, 0, 900, 900));
        view.UpdateLayout();
        view.Dispatcher.Invoke(() => { }, DispatcherPriority.DataBind);
        view.UpdateLayout();
        Assert.Null(PresentationSource.FromVisual(view));
        Assert.True(double.IsFinite(view.ActualWidth) && double.IsFinite(view.ActualHeight));
    }

    /// <summary>Enumerates only already-created off-screen visual descendants.</summary>
    private static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
        {
            var child = VisualTreeHelper.GetChild(parent, index);
            yield return child;
            foreach (var descendant in Descendants(child)) yield return descendant;
        }
    }

    /// <summary>Any interaction during a layout-only test is a failure.</summary>
    private static void UnexpectedAction() => throw new InvalidOperationException("Layout must not execute commands.");

    /// <summary>Only the panel's binding surface; deliberately not its service-owning production root ViewModel.</summary>
    public sealed class PickerData
    {
        /// <summary>Disabled, fail-fast command shared by the fixture's noninteractive controls.</summary>
        private static ICommand Disabled { get; } = new RelayCommand(UnexpectedAction, () => false);
        /// <summary>Creates static category data without recorder, navigation or runtime dependencies.</summary>
        public PickerData(IEnumerable<StrategyCategoryViewModel> categories, StrategyCategoryViewModel selected, StrategyBrowserViewModel alternative)
        {
            Categories = new ObservableCollection<StrategyCategoryViewModel>(categories);
            SelectedCategory = selected;
            SearchAlternatives = [alternative];
        }
        /// <summary>Real category types select the real implicit DataTemplates.</summary>
        public ObservableCollection<StrategyCategoryViewModel> Categories { get; }
        /// <summary>Writable selection expected by the real ListView; never invokes a production selection callback.</summary>
        public StrategyCategoryViewModel SelectedCategory { get; set; }
        /// <summary>In-memory search text for the real editable search box.</summary>
        public string SearchText { get; set; } = "fixture";
        /// <summary>Read-only alternate category rows exercise the real Run templates.</summary>
        public IReadOnlyList<StrategyBrowserViewModel> SearchAlternatives { get; }
        /// <summary>No loading operation occurs.</summary>
        public bool IsLoading => false;
        /// <summary>No current strategy warning.</summary>
        public bool HasCurrentWarning => false;
        /// <summary>Empty warning text.</summary>
        public string CurrentWarning => "";
        /// <summary>No directory load error.</summary>
        public bool HasLoadError => false;
        /// <summary>Empty load error text.</summary>
        public string LoadError => "";
        /// <summary>The fixture search field is populated.</summary>
        public bool HasSearchText => true;
        /// <summary>Recorder features remain hidden.</summary>
        public bool IsKeyMouseCategory => false;
        /// <summary>Repository navigation remains hidden.</summary>
        public bool ShowRepository => false;
        /// <summary>Record management remains hidden.</summary>
        public bool ShowRecordManagement => false;
        /// <summary>Inert descriptive text.</summary>
        public string RecordHint => "Fixture only";
        /// <summary>Never refresh directories.</summary>
        public ICommand RefreshCommand => Disabled;
        /// <summary>Never open a folder.</summary>
        public ICommand OpenFolderCommand => Disabled;
        /// <summary>Never open a repository.</summary>
        public ICommand OpenRepositoryCommand => Disabled;
        /// <summary>Never record input.</summary>
        public ICommand RecordCommand => Disabled;
        /// <summary>Never navigate.</summary>
        public ICommand NavigateRecordCommand => Disabled;
        /// <summary>Search clearing is not executed.</summary>
        public ICommand ClearSearchCommand => Disabled;
        /// <summary>Category switching commands are not executed.</summary>
        public ICommand SwitchCategoryCommand => Disabled;
    }

    /// <summary>Collects WPF binding errors only while this isolated test owns the trace listener.</summary>
    private sealed class BindingErrors : TraceListener
    {
        /// <summary>Binding diagnostics produced on the dedicated STA.</summary>
        private readonly StringBuilder _text = new();
        /// <summary>Retained error text for the assertion.</summary>
        public string Text => _text.ToString();
        /// <inheritdoc />
        public override void Write(string? message) => _text.Append(message);
        /// <inheritdoc />
        public override void WriteLine(string? message) => _text.AppendLine(message);
    }
}
