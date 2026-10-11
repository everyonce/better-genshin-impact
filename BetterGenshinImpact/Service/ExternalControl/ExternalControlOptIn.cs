using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace BetterGenshinImpact.Service.ExternalControl;

internal sealed record ExternalControlOptIn
{
    [JsonPropertyName("version")]
    public int Version { get; init; }

    [JsonPropertyName("enabled")]
    public bool Enabled { get; init; }

    [JsonPropertyName("allowAppRestart")]
    public bool AllowAppRestart { get; init; }

    internal static bool IsEnabled(string json)
    {
        try
        {
            var setting = JsonSerializer.Deserialize<ExternalControlOptIn>(json);
            return setting is { Version: 1, Enabled: true };
        }
        catch (JsonException)
        {
            return false;
        }
    }

    internal static bool IsAppRestartEnabled(string json)
    {
        try
        {
            var setting = JsonSerializer.Deserialize<ExternalControlOptIn>(json);
            return setting is { Version: 1, Enabled: true, AllowAppRestart: true };
        }
        catch (JsonException)
        {
            return false;
        }
    }

    internal static bool TryRead(string path)
        => TryRead(path, IsEnabled);

    internal static bool TryReadAppRestart(string path)
        => TryRead(path, IsAppRestartEnabled);

    private static bool TryRead(string path, Func<string, bool> validator)
    {
        try
        {
            var info = new FileInfo(path);
            return info.Exists
                   && info.Length is > 0 and <= 4096
                   && validator(File.ReadAllText(path));
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }
}
