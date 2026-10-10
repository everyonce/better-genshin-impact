using System;
using System.Security.Principal;
using System.Windows;
using BetterGenshinImpact.Helpers.Ui;
using BetterGenshinImpact.Service.ChildSession;
using BetterGenshinImpact.Service.I18n;
using Wpf.Ui.Controls;

namespace BetterGenshinImpact.View.Windows;

public partial class ChildSessionCredentialsWindow : FluentWindow
{
    public ChildSessionCredentialsWindow()
    {
        InitializeComponent();
        using var identity = WindowsIdentity.GetCurrent();
        UserNameBox.Text = identity.Name;
        // Never retrieve a saved password to populate the editor.
        Loaded += (_, _) => PasswordBox.Focus();
        SourceInitialized += (_, _) => WindowHelper.TryApplySystemBackdrop(this);
    }

    private void OnSaveClick(object sender, RoutedEventArgs e)
    {
        using var password = PasswordBox.SecurePassword;
        if (string.IsNullOrWhiteSpace(UserNameBox.Text) || password.Length == 0)
        {
            ShowError("Enter your Windows user name and password.");
            return;
        }

        try
        {
            ChildSessionCredentials.Save(UserNameBox.Text, PasswordBox.Password);
        }
        catch (Exception)
        {
            PasswordBox.Clear();
            ShowError("Could not save the Windows sign-in. Check Windows Credential Manager and try again.");
            return;
        }

        PasswordBox.Clear();
        DialogResult = true;
    }

    private void ShowError(string message)
    {
        ThemedMessageBox.Show(I18nService.Instance.Translate(message),
            I18nService.Instance.Translate("Save Windows sign-in"),
            System.Windows.MessageBoxButton.OK, ThemedMessageBox.MessageBoxIcon.Warning,
            System.Windows.MessageBoxResult.OK, this);
    }

    protected override void OnClosed(EventArgs e)
    {
        PasswordBox.Clear();
        base.OnClosed(e);
    }
}
