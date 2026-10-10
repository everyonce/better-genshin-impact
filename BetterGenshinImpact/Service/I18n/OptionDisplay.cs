using System;
using System.ComponentModel;
using System.Globalization;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Markup;

namespace BetterGenshinImpact.Service.I18n;

/// <summary>
/// Translates only an option's presentation. ItemsSource and selection retain their original
/// objects, so configuration values, script names and game-recognition keys are never rewritten.
/// </summary>
public static class OptionDisplay
{
    public static readonly DependencyProperty PathProperty = DependencyProperty.RegisterAttached(
        "Path", typeof(string), typeof(OptionDisplay), new PropertyMetadata(null, OnPathChanged));

    public static string? GetPath(DependencyObject target) => (string?)target.GetValue(PathProperty);
    public static void SetPath(DependencyObject target, string value) => target.SetValue(PathProperty, value);

    private static void OnPathChanged(DependencyObject target, DependencyPropertyChangedEventArgs args)
    {
        if (target is not ComboBox comboBox || args.NewValue is not string path) return;
        var text = new FrameworkElementFactory(typeof(TextBlock));
        text.SetBinding(TextBlock.TextProperty, CreateBinding(new Binding(path)));
        comboBox.ItemTemplate = new DataTemplate { VisualTree = text };
    }

    public static MultiBinding CreateBinding(Binding valueBinding)
    {
        valueBinding.Mode = BindingMode.OneWay;
        var binding = new MultiBinding { Mode = BindingMode.OneWay, Converter = OptionTextConverter.Instance };
        binding.Bindings.Add(valueBinding);
        binding.Bindings.Add(new Binding(nameof(I18nService.Revision)) { Source = I18nService.Instance });
        return binding;
    }

    public static string Translate(object? value)
    {
        if (value == null || value == DependencyProperty.UnsetValue) return string.Empty;
        var key = value is Enum enumeration
            ? enumeration.GetType().GetField(enumeration.ToString())?.GetCustomAttribute<DescriptionAttribute>()?.Description
                ?? enumeration.ToString()
            : value.ToString() ?? string.Empty;
        return I18nService.Instance.Translate(key);
    }
}

public sealed class OptionTextConverter : IMultiValueConverter
{
    public static OptionTextConverter Instance { get; } = new();
    public object Convert(object[] values, Type targetType, object parameter, CultureInfo culture) =>
        OptionDisplay.Translate(values.Length > 0 ? values[0] : null);
    public object[] ConvertBack(object value, Type[] targetTypes, object parameter, CultureInfo culture) =>
        Array.ConvertAll(targetTypes, _ => Binding.DoNothing);
}

/// <summary>One-way translation of a bound display value, refreshed when the UI language changes.</summary>
[MarkupExtensionReturnType(typeof(object))]
public sealed class TBExtension : MarkupExtension
{
    public TBExtension() { }
    public TBExtension(string path) => Path = path;
    [ConstructorArgument("path")]
    public string Path { get; set; } = string.Empty;
    public object TargetNullValue { get; set; } = DependencyProperty.UnsetValue;
    public override object ProvideValue(IServiceProvider serviceProvider) =>
        OptionDisplay.CreateBinding(new Binding(Path) { TargetNullValue = TargetNullValue }).ProvideValue(serviceProvider);
}
