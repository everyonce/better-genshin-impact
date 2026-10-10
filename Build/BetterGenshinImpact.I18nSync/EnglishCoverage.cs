using System.Text.RegularExpressions;
using System.Xml.Linq;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.I18nSync;

internal static class EnglishCoverage
{
    internal static int Check(string projectDirectory)
    {
        var scan = I18nScanner.Scan(projectDirectory);
        var json = JObject.Parse(File.ReadAllText(Path.Combine(projectDirectory, "User", "I18n", "en.json")),
            new Newtonsoft.Json.Linq.JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });
        var chinese = new Regex(@"[\u3400-\u9fff]");
        var errors = new List<string>();
        foreach (var key in scan.Keys.Where(key => chinese.IsMatch(key)))
            if (string.IsNullOrWhiteSpace(json.Value<string>(key))) errors.Add($"Missing English translation: {key}");
        foreach (var property in json.Properties())
        {
            if (property.Value.Type != JTokenType.String || string.IsNullOrWhiteSpace(property.Value.Value<string>()))
                errors.Add($"Invalid/empty English value: {property.Name}");
            else if (chinese.IsMatch(property.Value.Value<string>()!))
                errors.Add($"Chinese remains in English value: {property.Name}");
        }
        foreach (var strategyDirectory in new[] { "AutoFight", "AutoGeniusInvokation" })
        {
            var directory = Path.Combine(projectDirectory, "User", strategyDirectory);
            if (!Directory.Exists(directory)) continue;
            foreach (var file in Directory.EnumerateFiles(directory, "*.txt", SearchOption.AllDirectories))
            {
                var label = Path.ChangeExtension(Path.GetRelativePath(directory, file), null);
                if (chinese.IsMatch(label) && string.IsNullOrWhiteSpace(json.Value<string>(label)))
                    errors.Add($"Missing bundled strategy display translation: {label}");
            }
        }
        var visibleAttributes = new HashSet<string>(StringComparer.Ordinal)
        { "Text", "Content", "Header", "ToolTip", "Title", "PlaceholderText", "Watermark", "Description", "EnableContent", "DisableContent" };
        foreach (var file in Directory.EnumerateFiles(Path.Combine(projectDirectory, "View"), "*.xaml", SearchOption.AllDirectories))
        {
            var document = XDocument.Load(file);
            foreach (var attribute in document.Descendants().Attributes())
                if (visibleAttributes.Contains(attribute.Name.LocalName) && chinese.IsMatch(attribute.Value)
                    && !attribute.Value.StartsWith('{'))
                    errors.Add($"Untranslated XAML {Path.GetRelativePath(projectDirectory, file)}: {attribute.Name}={attribute.Value}");
            foreach (var node in document.DescendantNodes().OfType<XText>())
                if (chinese.IsMatch(node.Value))
                    errors.Add($"Untranslated XAML text {Path.GetRelativePath(projectDirectory, file)}: {node.Value.Trim()}");
        }
        Console.WriteLine($"English coverage: {scan.XamlFileCount} XAML files, {scan.CodeFileCount} C# files, {scan.Keys.Count} static keys, {json.Count} English entries.");
        foreach (var error in errors) Console.Error.WriteLine(error);
        Console.WriteLine($"{errors.Count} coverage errors. Dynamic/user-authored content requires separate review.");
        return errors.Count == 0 ? 0 : 1;
    }
}
