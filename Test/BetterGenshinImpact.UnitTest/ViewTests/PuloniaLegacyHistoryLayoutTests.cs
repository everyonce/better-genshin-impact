using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.ExceptionServices;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.View.Controls;
using BetterGenshinImpact.ViewModel.Pages.Pulonia;
using CommunityToolkit.Mvvm.Input;

namespace BetterGenshinImpact.UnitTest.ViewTests;

/// <summary>Serializes process-wide WPF resources; run this layout Fact in its own filtered test host.</summary>
[CollectionDefinition("Offscreen legacy history layout", DisableParallelization = true)]
public sealed class PuloniaLegacyHistoryLayoutCollection { }

/// <summary>Constructs the actual read-only history view without a store, application host, HWND or user data.</summary>
[Collection("Offscreen legacy history layout")]
public sealed class PuloniaLegacyHistoryLayoutTests
{
    /// <summary>Checks both viewport sizes, long labels and truncated facts in one plain-Application lifetime.</summary>
    [Fact]
    public void ReadOnlyHistory_ConstructsAtNormalAndNarrowSizesWithoutExecutingCommands()
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try { CheckOnSta(); }
            catch (Exception error) { failure = ExceptionDispatchInfo.Capture(error); }
        }) { IsBackground = true, Name = "Offscreen legacy history layout" };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(30)), "Off-screen history layout exceeded 30 seconds; stop this test host.");
        failure?.Throw();
    }

    /// <summary>Uses embedded translations and software-only WPF; the fixture path is never created or populated.</summary>
    private static void CheckOnSta()
    {
        Assert.Null(Application.Current);
        var oldPath = Global.StartUpPath;
        var fixturePath = Path.Combine(Path.GetTempPath(), "BetterGI-Offscreen-History-" + Guid.NewGuid().ToString("N"));
        Assert.False(Directory.Exists(fixturePath));
        var oldRenderMode = RenderOptions.ProcessRenderMode;
        var trace = PresentationTraceSources.DataBindingSource;
        var oldLevel = trace.Switch.Level;
        using var errors = new BindingErrors();
        Application? application = null;
        // I18nService checks User/I18n on first use: redirect before loading any view or markup extension.
        Global.StartUpPath = fixturePath;
        RenderOptions.ProcessRenderMode = RenderMode.SoftwareOnly;
        trace.Switch.Level = SourceLevels.Error;
        trace.Listeners.Add(errors);
        try
        {
            application = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            application.Resources.MergedDictionaries.Add(new Wpf.Ui.Markup.ThemesDictionary
            {
                Theme = Wpf.Ui.Appearance.ApplicationTheme.Dark
            });
            application.Resources.MergedDictionaries.Add(new Wpf.Ui.Markup.ControlsDictionary());
            var data = new HistoryData();
            var view = new PuloniaLegacyHistoryView { DataContext = data };
            Layout(view, new Size(1000, 760));
            // Expand display-only sections; no read/refresh command, selection callback or Loaded event is invoked.
            var expanders = Descendants(view).OfType<Expander>().ToArray();
            Assert.Equal(3, expanders.Length);
            foreach (var expander in expanders)
            {
                expander.ApplyTemplate();
                expander.IsExpanded = true;
            }
            foreach (var size in new[] { new Size(1000, 760), new Size(600, 700) })
            {
                Layout(view, size);
                // The real WPF-UI template reveals its content through a render-priority animation.
                foreach (var expander in expanders)
                {
                    Assert.True(expander.IsExpanded);
                    var content = Assert.IsType<Border>(expander.Template.FindName("ContentPresenterBorder", expander));
                    Assert.Equal(Visibility.Visible, content.Visibility);
                }
                CheckContent(view, data, size);
                CheckReadOnlyBindingsAndCommands(view, data);
            }
            Assert.Equal(0, data.CommandExecutions);
            Assert.Empty(application.Windows.Cast<Window>());
            Assert.Equal(RenderMode.SoftwareOnly, RenderOptions.ProcessRenderMode);
            Assert.False(Directory.Exists(fixturePath));
            Assert.True(errors.Text.Length == 0, errors.Text);
        }
        finally
        {
            trace.Listeners.Remove(errors);
            trace.Switch.Level = oldLevel;
            Global.StartUpPath = oldPath;
            try { application?.Shutdown(); }
            finally
            {
                RenderOptions.ProcessRenderMode = oldRenderMode;
                Dispatcher.CurrentDispatcher.InvokeShutdown();
            }
        }
    }

    /// <summary>Checks the real list/detail templates and bounded selected text rather than a recreated XAML sample.</summary>
    private static void CheckContent(PuloniaLegacyHistoryView view, HistoryData data, Size size)
    {
        var list = Assert.IsType<ListBox>(view.FindName("LegacyRecordList"));
        var details = Assert.IsAssignableFrom<FrameworkElement>(view.FindName("LegacyDetails"));
        Assert.Same(data.Records, list.ItemsSource);
        Assert.Same(data.SelectedRecord, list.SelectedItem);
        Assert.Equal(2, list.Items.Count);
        Assert.InRange(list.ActualWidth, 160, size.Width);
        Assert.InRange(details.ActualWidth, 260, size.Width);
        Assert.InRange(list.TranslatePoint(new Point(), view).X + list.ActualWidth, 0, size.Width + 1);
        Assert.InRange(details.TranslatePoint(new Point(), view).X + details.ActualWidth, 0, size.Width + 1);
        foreach (var name in new[] { "LegacyOverview", "LegacyFacts", "LegacyFailures" })
            Assert.IsAssignableFrom<ItemsControl>(view.FindName(name));
        var notice = Assert.IsAssignableFrom<FrameworkElement>(view.FindName("LegacyTruncationNotice"));
        Assert.Equal(Visibility.Visible, notice.Visibility);
        var text = Descendants(view).OfType<TextBlock>().ToArray();
        Assert.Contains(text, block => block.Text == data.Records[0].PlanLabel);
        Assert.All(Descendants(list).OfType<TextBlock>(), block => Assert.InRange(block.ActualWidth, 0, list.ActualWidth));
        Assert.Contains(text, block => block.Text == data.StatusMessage);
        Assert.Contains(text, block => block.Text == data.ModeMessage);
        var values = Descendants(view).OfType<TextBox>()
            .Where(box => box.DataContext is PuloniaTaskHistoryField).ToArray();
        Assert.NotEmpty(values);
        foreach (var field in data.OverviewFields.Concat(data.FactFields).Concat(data.Failures))
            Assert.Contains(values, box => ReferenceEquals(box.DataContext, field) && box.Text == field.Value);
        Assert.Contains(values, box => box.Text == data.TruncatedJson);
        Assert.All(values, box =>
        {
            Assert.True(box.IsReadOnly);
            Assert.InRange(box.ActualHeight, 0, 180);
            Assert.InRange(box.ActualWidth, 0, size.Width);
        });
        Assert.True(Encoding.UTF8.GetByteCount(data.TruncatedJson) < 64 * 1024);
        Assert.EndsWith("[synthetic preview truncated]", data.TruncatedJson);
        Assert.False(view.IsLoaded);
        Assert.Null(PresentationSource.FromVisual(view));
    }

    /// <summary>Allows only readonly display bindings and the two inert read commands; edit fields/selection remain explicit.</summary>
    private static void CheckReadOnlyBindingsAndCommands(PuloniaLegacyHistoryView view, HistoryData data)
    {
        var nodes = Descendants(view).Prepend(view).OfType<FrameworkElement>().ToArray();
        // ScrollViewer templates contain RepeatButton scrolling commands; those are not history actions.
        var readButtons = nodes.OfType<Button>().Where(button => button.Command is not null).ToArray();
        Assert.Equal(2, readButtons.Length);
        foreach (var button in readButtons)
        {
            var binding = Assert.IsType<Binding>(BindingOperations.GetBindingBase(button, ButtonBase.CommandProperty));
            Assert.Contains(binding.Path.Path, new[] { nameof(HistoryData.RefreshCommand), nameof(HistoryData.LoadExactCommand) });
            Assert.Equal(BindingMode.OneWay, binding.Mode);
            Assert.Same(data.ReadCommand, button.Command);
            Assert.False(button.Command.CanExecute(button.CommandParameter));
        }
        Assert.Empty(nodes.OfType<MenuItem>());
        foreach (var node in nodes)
        {
            Assert.Empty(node.InputBindings.Cast<InputBinding>());
            Assert.Empty(node.CommandBindings.Cast<CommandBinding>());
            CheckTextContextMenu(node);
            if (BindingOperations.GetBinding(node, UIElement.VisibilityProperty) is { } visibility
                && visibility.Path.Path is "HasSelectedRecord" or "IsPreviewTruncated" or "IsRefreshing" or "HasUnresolvedFacts")
                Assert.Equal(BindingMode.OneWay, visibility.Mode);
            if (node is TextBlock block)
            {
                CheckDisplayBinding(block, TextBlock.TextProperty);
                foreach (var run in block.Inlines.OfType<Run>()) CheckDisplayBinding(run, Run.TextProperty);
            }
            if (node is ItemsControl items && ReferenceEquals(items.DataContext, data))
                CheckDisplayBinding(items, ItemsControl.ItemsSourceProperty);
            if (node is TextBox box && box.DataContext is PuloniaTaskHistoryField)
            {
                Assert.True(box.IsReadOnly);
                Assert.Equal("Value", BindingOperations.GetBinding(box, TextBox.TextProperty)?.Path.Path);
                CheckDisplayBinding(box, TextBox.TextProperty);
            }
        }
        var list = (ListBox)view.FindName("LegacyRecordList");
        Assert.Equal(BindingMode.TwoWay, BindingOperations.GetBinding(list, Selector.SelectedItemProperty)?.Mode);
        var edits = nodes.OfType<TextBox>().Where(box => ReferenceEquals(box.DataContext, data) && !box.IsReadOnly).ToArray();
        Assert.Equal(2, edits.Length);
        foreach (var edit in edits)
        {
            var binding = Assert.IsType<Binding>(BindingOperations.GetBindingBase(edit, TextBox.TextProperty));
            Assert.Contains(binding.Path.Path, new[] { nameof(HistoryData.ExactPlanId), nameof(HistoryData.ExactRunId) });
            Assert.Equal(BindingMode.TwoWay, binding.Mode);
        }
    }

    /// <summary>Allows only the unopened stock text menu; readonly facts reject mutation without clipboard access.</summary>
    private static void CheckTextContextMenu(FrameworkElement node)
    {
        if (node is not TextBox box)
        {
            Assert.Null(node.ContextMenu);
            return;
        }
        var menu = Assert.IsType<ContextMenu>(box.ContextMenu);
        Assert.False(menu.IsOpen);
        Assert.Empty(menu.InputBindings.Cast<InputBinding>());
        Assert.Empty(menu.CommandBindings.Cast<CommandBinding>());
        // WPF-UI's DefaultControlContextMenu is exactly these routed text commands, not history actions.
        var commands = new[] { ApplicationCommands.Copy, ApplicationCommands.Cut, ApplicationCommands.Paste };
        Assert.Equal(commands.Length, menu.Items.Count);
        for (var index = 0; index < commands.Length; index++)
        {
            var item = Assert.IsType<MenuItem>(menu.Items[index]);
            Assert.Same(commands[index], item.Command);
            Assert.Null(item.CommandTarget);
            Assert.Null(item.CommandParameter);
            Assert.Empty(item.Items);
            Assert.Empty(item.InputBindings.Cast<InputBinding>());
            Assert.Empty(item.CommandBindings.Cast<CommandBinding>());
        }
        if (box.DataContext is not PuloniaTaskHistoryField field) return;
        Assert.True(box.IsReadOnly);
        Assert.NotEmpty(box.Text);
        var text = box.Text;
        var value = field.Value;
        var selectionStart = box.SelectionStart;
        var selectionLength = box.SelectionLength;
        try
        {
            // Select only synthetic in-memory text; do not focus, open a menu or execute any command.
            box.SelectAll();
            Assert.True(ApplicationCommands.Copy.CanExecute(null, box));
            // WPF checks IsReadOnly before consulting clipboard data for Paste.
            Assert.False(ApplicationCommands.Cut.CanExecute(null, box));
            Assert.False(ApplicationCommands.Paste.CanExecute(null, box));
            Assert.Equal(text, box.Text);
            Assert.Equal(value, field.Value);
        }
        finally { box.Select(selectionStart, selectionLength); }
    }

    /// <summary>Rejects implicit/default/two-way text and collection bindings, including translated multi-bindings.</summary>
    private static void CheckDisplayBinding(DependencyObject target, DependencyProperty property)
    {
        switch (BindingOperations.GetBindingBase(target, property))
        {
            case Binding binding:
                Assert.Equal(BindingMode.OneWay, binding.Mode);
                break;
            case MultiBinding multiple:
                Assert.Equal(BindingMode.OneWay, multiple.Mode);
                break;
        }
    }

    /// <summary>Measures only an unattached visual tree; no window, popup, HwndSource or native activation.</summary>
    private static void Layout(FrameworkElement view, Size size)
    {
        view.Measure(size);
        view.Arrange(new Rect(new Point(), size));
        view.UpdateLayout();
        // DataBind (8) runs before Render (7): drain the existing template animation/render work too.
        // No storyboard, visibility or template is replaced; this remains an unloaded software-only tree.
        view.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
        view.UpdateLayout();
        Assert.Null(PresentationSource.FromVisual(view));
        Assert.InRange(Math.Abs(view.ActualWidth - size.Width), 0, 1);
        Assert.True(double.IsFinite(view.ActualHeight));
    }

    /// <summary>Enumerates only already constructed offscreen descendants.</summary>
    private static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
        {
            var child = VisualTreeHelper.GetChild(parent, index);
            yield return child;
            foreach (var descendant in Descendants(child)) yield return descendant;
        }
    }

    /// <summary>Only the view's binding surface: no production view model, record parser, store or executable history type.</summary>
    public sealed class HistoryData
    {
        /// <summary>Builds bounded synthetic display text without reading any history or resource file.</summary>
        public HistoryData()
        {
            ReadCommand = new RelayCommand(() =>
            {
                CommandExecutions++;
                throw new InvalidOperationException("Layout must not execute even a history read command.");
            }, () => false);
            Records = [new HistoryRow("Long recorded plan " + new string('L', 240), true), new HistoryRow("Second synthetic record", false)];
            SelectedRecord = Records[0];
            TruncatedJson = "{\n  \"opaque_snapshot\": \"" + new string('x', 8192) + "\n[synthetic preview truncated]";
            OverviewFields = [new("Long synthetic label " + new string('l', 160), Records[0].PlanLabel), new("Original hash", new string('a', 64))];
            FactFields = [new("Opaque snapshot preview", TruncatedJson), new("Recorded uncertainty", "Missing confirmation remains unresolved.")];
            Failures = [new("Synthetic read failure", "fixture.json: intentionally unavailable; no real file was opened.")];
        }
        /// <summary>Only in-memory list items.</summary>
        public ObservableCollection<HistoryRow> Records { get; }
        /// <summary>The only selected item; setter satisfies the real two-way selection binding without callbacks.</summary>
        public HistoryRow? SelectedRecord { get; set; }
        /// <summary>Read-only overview fields.</summary>
        public IReadOnlyList<PuloniaTaskHistoryField> OverviewFields { get; }
        /// <summary>Read-only selected fact fields.</summary>
        public IReadOnlyList<PuloniaTaskHistoryField> FactFields { get; }
        /// <summary>Read-only synthetic failure fields.</summary>
        public IReadOnlyList<PuloniaTaskHistoryField> Failures { get; }
        /// <summary>Selected detail text visibly marked as incomplete; this is not a parser or truncator qualification.</summary>
        public string TruncatedJson { get; }
        /// <summary>Details remain visible.</summary>
        public bool HasSelectedRecord => true;
        /// <summary>Exercises the production incomplete-preview notice.</summary>
        public bool IsPreviewTruncated => true;
        /// <summary>No asynchronous operation is running.</summary>
        public bool IsRefreshing => false;
        /// <summary>Explicit synthetic status.</summary>
        public string StatusMessage => "Synthetic records only; no files read and no runtime authority.";
        /// <summary>Explicit source mode.</summary>
        public string ModeMessage => "In-memory layout fixture";
        /// <summary>Read-only list count.</summary>
        public int RecordCount => Records.Count;
        /// <summary>Read-only failure count.</summary>
        public int FailureCount => Failures.Count;
        /// <summary>Editable exact-plan input, never submitted.</summary>
        public string ExactPlanId { get; set; } = "synthetic-plan";
        /// <summary>Editable original run alias, never submitted.</summary>
        public string ExactRunId { get; set; } = "00000000000000000000000000000001";
        /// <summary>Visible label only, deliberately not an actual storage location.</summary>
        public string StorageDirectory => "Synthetic history location (not opened)";
        /// <summary>Tracks any forbidden command invocation.</summary>
        public int CommandExecutions { get; private set; }
        /// <summary>Shared disabled command; invocation always fails.</summary>
        public ICommand ReadCommand { get; }
        /// <summary>Never refreshes files during layout.</summary>
        public ICommand RefreshCommand => ReadCommand;
        /// <summary>Never resolves an exact file during layout.</summary>
        public ICommand LoadExactCommand => ReadCommand;
    }

    /// <summary>Only readonly row labels; never an executable/current run record.</summary>
    public sealed class HistoryRow(string planLabel, bool unresolved)
    {
        /// <summary>Bounded synthetic plan label.</summary>
        public string PlanLabel => planLabel;
        /// <summary>Synthetic identifier label.</summary>
        public string RunLabel => "00000000000000000000000000000001";
        /// <summary>Recorded-text label, not the current clock.</summary>
        public string TimeLabel => "Recorded fixture timestamp";
        /// <summary>Recorded historical status, not current activity.</summary>
        public string StatusLabel => "Recorded Running (synthetic)";
        /// <summary>Exercises the unresolved-facts display.</summary>
        public bool HasUnresolvedFacts => unresolved;
    }

    /// <summary>Retains binding diagnostics only while this isolated test owns the listener.</summary>
    private sealed class BindingErrors : TraceListener
    {
        /// <summary>Small diagnostic text collected on the fixture's STA.</summary>
        private readonly StringBuilder _text = new();
        /// <summary>Actual diagnostics for the final assertion.</summary>
        public string Text => _text.ToString();
        /// <inheritdoc />
        public override void Write(string? message) => _text.Append(message);
        /// <inheritdoc />
        public override void WriteLine(string? message) => _text.AppendLine(message);
    }
}
