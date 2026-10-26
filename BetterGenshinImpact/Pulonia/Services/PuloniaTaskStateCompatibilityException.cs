using System;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>A valid but incompatible state is a scheduling hold, never evidence for backup rollback or deletion.</summary>
public sealed class PuloniaTaskStateCompatibilityException(string detail) : InvalidOperationException(
    "Pulonia scheduling is on a compatibility hold. Preserve state.json, its backup and all history; " +
    "existing identities and unresolved operations require an explicit migration. " + detail)
{
}
