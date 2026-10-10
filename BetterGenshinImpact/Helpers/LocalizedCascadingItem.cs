using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using BetterGenshinImpact.Service.I18n;
using Wpf.Ui.Violeta.Controls;

namespace BetterGenshinImpact.Helpers;

/// <summary>A stable selection identity with a language-dependent label and an untouched game key.</summary>
public sealed class LocalizedCascadingItem : ICascadingItem, INotifyPropertyChanged
{
    private readonly Func<string> _label;
    public LocalizedCascadingItem(string key, IEnumerable<ICascadingItem>? children = null)
        : this(() => I18nService.Instance.Translate(key), children) { }
    public LocalizedCascadingItem(Func<string> label, IEnumerable<ICascadingItem>? children = null)
    {
        _label = label;
        // Materialize once: converters and the control must see the same option instances.
        Children = children?.ToList();
        PropertyChangedEventManager.AddHandler(I18nService.Instance, OnLanguageChanged, nameof(I18nService.Revision));
    }
    public string Label => _label();
    public object? Tag { get; init; }
    public IEnumerable<ICascadingItem>? Children { get; }
    public event PropertyChangedEventHandler? PropertyChanged;
    private void OnLanguageChanged(object? sender, PropertyChangedEventArgs e) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Label)));
}
