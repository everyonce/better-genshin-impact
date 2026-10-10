using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Service.I18n;
using Newtonsoft.Json;
using Xunit;
using Wpf.Ui.Violeta.Appearance;
using Wpf.Ui.Violeta.Controls;

[assembly: CollectionBehavior(DisableTestParallelization = true)]

namespace BetterGenshinImpact.EnglishTest;

public sealed class EnglishLocalizationTests : IDisposable
{
    private readonly string _originalPath = Global.StartUpPath;
    private readonly CultureInfo _originalCulture = CultureInfo.CurrentUICulture;
    private readonly CultureInfo? _originalThreadCulture = CultureInfo.DefaultThreadCurrentUICulture;
    private readonly string _temporaryPath = Path.Combine(Path.GetTempPath(), "BetterGI-EnglishTests", Guid.NewGuid().ToString("N"));

    public EnglishLocalizationTests()
    {
        Directory.CreateDirectory(Path.Combine(_temporaryPath, "User", "I18n"));
        Global.StartUpPath = _temporaryPath;
    }

    private static I18nService CreateService() =>
        (I18nService)Activator.CreateInstance(typeof(I18nService), nonPublic: true)!;

    [Fact]
    public void FreshConfigurationDefaultsToEnglishWithoutChangingGameLanguage()
    {
        var config = new OtherConfig();
        Assert.Equal("en", config.UiCultureInfoName);
        Assert.Equal("zh-Hans", config.GameCultureInfoName);
        Assert.Equal("Start", CreateService().Translate("启动"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("en")]
    [InlineData("en-US")]
    [InlineData("en-GB")]
    public void MissingEditableDictionaryStillUsesBundledEnglish(string? language)
    {
        var service = CreateService();
        service.ChangeLanguage(language);
        Assert.Equal("Start", service.Translate("启动"));
        Assert.Equal("my-script.json", service.Translate("my-script.json"));
    }

    [Fact]
    public void PartialOrEmptyCustomDictionaryDoesNotEraseBundledTranslations()
    {
        File.WriteAllText(Path.Combine(_temporaryPath, "User", "I18n", "en.json"),
            JsonConvert.SerializeObject(new Dictionary<string, string> { ["启动"] = "", ["保存"] = "Save changes" }));
        var service = CreateService();
        Assert.Equal("Start", service.Translate("启动"));
        Assert.Equal("Save changes", service.Translate("保存"));
    }

    [Fact]
    public void MalformedEditableDictionaryStillUsesBundledEnglish()
    {
        File.WriteAllText(Path.Combine(_temporaryPath, "User", "I18n", "en.json"), "{ broken json");
        Assert.Equal("Start", CreateService().Translate("启动"));
    }

    [Fact]
    public void ChangingLanguageNotifiesBindingsAndPreservesSourceKeys()
    {
        var service = CreateService();
        var notifications = 0;
        service.PropertyChanged += (_, args) => { if (args.PropertyName == nameof(I18nService.Revision)) notifications++; };
        service.ChangeLanguage("zh-Hans");
        Assert.Equal("启动", service.Translate("启动"));
        service.ChangeLanguage("en");
        Assert.Equal("Start", service.Translate("启动"));
        Assert.Equal("en", I18N.Culture.Name);
        Assert.Equal(2, notifications);
    }

    [Fact]
    public void BundledEnglishContainsNoBlankOrChineseValuesAndPreservesFormatArguments()
    {
        using var stream = typeof(I18nService).Assembly.GetManifestResourceStream("BetterGenshinImpact.English.json");
        Assert.NotNull(stream);
        using var reader = new StreamReader(stream!);
        var translations = JsonConvert.DeserializeObject<Dictionary<string, string>>(reader.ReadToEnd())!;
        Assert.True(translations.Count >= 1456);
        var placeholders = new Regex(@"(?<!\{)\{\d+(?:,[^}:]+)?(?::[^}]+)?\}(?!\})");
        foreach (var (key, value) in translations)
        {
            Assert.False(string.IsNullOrWhiteSpace(value), $"Empty English translation: {key}");
            Assert.False(Regex.IsMatch(value, @"[\u3400-\u9fff]"), $"Chinese remains in English translation: {key}");
            Assert.Equal(placeholders.Matches(key).Select(m => m.Value).Order(),
                placeholders.Matches(value).Select(m => m.Value).Order());
        }
    }

    public void Dispose()
    {
        Global.StartUpPath = _originalPath;
        CultureInfo.CurrentUICulture = _originalCulture;
        CultureInfo.DefaultThreadCurrentUICulture = _originalThreadCulture;
        Directory.Delete(_temporaryPath, recursive: true);
    }
}
