using System;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>Pure legacy account-image pin validation; no image decoder, credentials or runtime service is invoked.</summary>
internal static class PuloniaGenshinAccountImageProvenance
{
    /// <summary>Accept the old writer's lowercase SHA-256 text, or a null pin for the immutable-path policy.</summary>
    internal static void ValidateVersion(string? version)
    {
        if (version is not null && !Regex.IsMatch(version, "^[0-9a-f]{64}\\z"))
            throw new InvalidOperationException("The legacy account image_version must be a lowercase SHA-256 digest or null.");
    }

    /// <summary>Verify the caller-owned byte span before it is passed unchanged to decoding; null does not create a hash claim.</summary>
    internal static void Verify(ReadOnlySpan<byte> bytes, string? version)
    {
        ValidateVersion(version);
        if (version is not null && Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != version)
            throw new InvalidOperationException("账号图片版本已变化，不能执行旧运行快照。");
    }
}
