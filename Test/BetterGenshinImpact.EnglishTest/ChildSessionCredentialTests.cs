using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Windows.Controls;
using BetterGenshinImpact.Service.ChildSession;
using BetterGenshinImpact.View.Windows;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class ChildSessionCredentialTests
{
    [Fact]
    public void PasswordIsExcludedFromJsonAndDiagnosticText()
    {
        const string fakeSecret = "test-only-not-a-real-credential";
        var credential = (ChildSessionCredential)Activator.CreateInstance(typeof(ChildSessionCredential),
            BindingFlags.Instance | BindingFlags.NonPublic, null, ["TEST\\user", fakeSecret], null)!;

        Assert.DoesNotContain(fakeSecret, System.Text.Json.JsonSerializer.Serialize(credential));
        Assert.DoesNotContain(fakeSecret, Newtonsoft.Json.JsonConvert.SerializeObject(credential));
        Assert.DoesNotContain(fakeSecret, credential.ToString());
    }

    [Theory]
    [InlineData("", "test")]
    [InlineData("  ", "test")]
    [InlineData("TEST\\user", "")]
    public void IncompleteInputIsRejectedBeforeCredentialManagerAccess(string user, string password)
    {
        Assert.ThrowsAny<ArgumentException>(() => ChildSessionCredentials.Save(user, password));
    }

    [Fact]
    public void PasswordEditorStartsEmptyAndClearsOnClose()
    {
        Exception? error = null;
        var thread = new Thread(() =>
        {
            try
            {
                var dialog = new ChildSessionCredentialsWindow();
                var passwordBox = Assert.IsType<PasswordBox>(dialog.FindName("PasswordBox"));
                Assert.Equal("", passwordBox.Password);
                passwordBox.Password = "test-only-not-a-real-credential";
                dialog.Close();
                Assert.Equal("", passwordBox.Password);
            }
            catch (Exception exception) { error = exception; }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(10)));
        if (error is not null) ExceptionDispatchInfo.Capture(error).Throw();
    }
}
