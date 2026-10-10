using System;
using System.ComponentModel;
using System.Windows;
using System.Windows.Input;
using BetterGenshinImpact.Service.I18n;
using Wpf.Ui.Controls;

namespace BetterGenshinImpact.View.Controls;

public class TwoStateButton : Button
{
    public TwoStateButton()
    {
        if (TryFindResource(typeof(Button)) is Style style)
        {
            Style = style;
        }

        Loaded += OnLoaded;
        PropertyChangedEventManager.AddHandler(I18nService.Instance, OnLanguageChanged, nameof(I18nService.Revision));
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        UpdateButton();
    }

    private static void OnIsCheckedChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is TwoStateButton button)
        {
            button.UpdateButton();
        }
    }

    private void OnLanguageChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (Dispatcher.HasShutdownStarted || Dispatcher.HasShutdownFinished)
        {
            return;
        }

        if (Dispatcher.CheckAccess())
        {
            UpdateButton();
        }
        else
        {
            Dispatcher.BeginInvoke(new Action(() =>
            {
                if (!Dispatcher.HasShutdownStarted && !Dispatcher.HasShutdownFinished)
                {
                    UpdateButton();
                }
            }));
        }
    }

    private static void OnContentChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is TwoStateButton button)
        {
            button.UpdateButton();
        }
    }

    private static readonly DependencyProperty IsCheckedProperty = DependencyProperty.Register(nameof(IsChecked), typeof(bool), typeof(TwoStateButton), new PropertyMetadata(false, OnIsCheckedChanged));

    public bool IsChecked
    {
        get => (bool)GetValue(IsCheckedProperty);
        set => SetValue(IsCheckedProperty, value);
    }

    private static readonly DependencyProperty EnableContentProperty = DependencyProperty.Register(nameof(EnableContent), typeof(object), typeof(TwoStateButton), new PropertyMetadata("启动", OnContentChanged));

    public object EnableContent
    {
        get => GetValue(EnableContentProperty);
        set => SetValue(EnableContentProperty, value);
    }

    private static readonly DependencyProperty EnableIconProperty = DependencyProperty.Register(nameof(EnableIcon), typeof(IconElement), typeof(TwoStateButton), new PropertyMetadata(null));

    public IconElement EnableIcon
    {
        get => (IconElement)GetValue(EnableIconProperty);
        set => SetValue(EnableIconProperty, value);
    }

    private static readonly DependencyProperty EnableCommandProperty = DependencyProperty.Register(nameof(EnableCommand), typeof(ICommand), typeof(TwoStateButton), new PropertyMetadata(null));

    public ICommand EnableCommand
    {
        get => (ICommand)GetValue(EnableCommandProperty);
        set => SetValue(EnableCommandProperty, value);
    }

    private static readonly DependencyProperty DisableContentProperty = DependencyProperty.Register(nameof(DisableContent), typeof(object), typeof(TwoStateButton), new PropertyMetadata("停止", OnContentChanged));

    public object DisableContent
    {
        get => GetValue(DisableContentProperty);
        set => SetValue(DisableContentProperty, value);
    }

    private static readonly DependencyProperty DisableIconProperty = DependencyProperty.Register(nameof(DisableIcon), typeof(IconElement), typeof(TwoStateButton), new PropertyMetadata(null));

    public IconElement DisableIcon
    {
        get => (IconElement)GetValue(DisableIconProperty);
        set => SetValue(DisableIconProperty, value);
    }

    private static readonly DependencyProperty DisableCommandProperty = DependencyProperty.Register(nameof(DisableCommand), typeof(ICommand), typeof(TwoStateButton), new PropertyMetadata(null));

    public ICommand DisableCommand
    {
        get => (ICommand)GetValue(DisableCommandProperty);
        set => SetValue(DisableCommandProperty, value);
    }

    private void UpdateButton()
    {
        if (IsChecked)
        {
            Command = DisableCommand;
            Content = GetDisplayContent(DisableContent);
            Icon = DisableIcon;
        }
        else
        {
            Command = EnableCommand;
            Content = GetDisplayContent(EnableContent);
            Icon = EnableIcon;
        }
    }

    private static object? GetDisplayContent(object? value) =>
        value is string text ? OptionDisplay.Translate(text) : value;
}
