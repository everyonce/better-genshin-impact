using System.Text.RegularExpressions;

namespace BetterGenshinImpact.GameTask;

internal static class GenshinStartArguments
{
    private const string ChildSessionArguments =
        "-screen-fullscreen 0 -popupwindow -screen-width 1920 -screen-height 1080";

    private static readonly Regex ChildSessionOverriddenArgumentRegex = new(
        @"(?<!\S)(?:-popupwindow|(?:-screen-(?:width|height|fullscreen)|-window-mode)(?:\s*=\s*(?:""[^""]*""|\S+)|\s+(?:""[^""]*""|(?!-)\S+))?)(?=\s|$)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.Compiled);

    internal static string Build(string? configuredArguments, bool isChildSession)
    {
        var arguments = configuredArguments?.Trim() ?? string.Empty;
        if (!isChildSession)
        {
            return arguments;
        }

        arguments = ChildSessionOverriddenArgumentRegex.Replace(arguments, string.Empty).Trim();
        return string.IsNullOrEmpty(arguments)
            ? ChildSessionArguments
            : $"{arguments} {ChildSessionArguments}";
    }
}
