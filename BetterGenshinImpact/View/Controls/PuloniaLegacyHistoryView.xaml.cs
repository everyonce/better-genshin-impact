using System.Windows.Controls;

namespace BetterGenshinImpact.View.Controls;

/// <summary>Read-only legacy display; the page supplies a distinct view model as DataContext.</summary>
public partial class PuloniaLegacyHistoryView : UserControl
{
    /// <summary>Initialize layout only; all bounded reads are view-model commands.</summary>
    public PuloniaLegacyHistoryView() => InitializeComponent();
}
