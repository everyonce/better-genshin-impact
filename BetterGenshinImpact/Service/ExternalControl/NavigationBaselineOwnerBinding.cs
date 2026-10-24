using System;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Borrowed reference identities plus process metadata; this object owns/disposes no runtime or backend.</summary>
internal sealed record NavigationBaselineOwnerBinding(
    object Runtime, object Capture, object Input, int ChildProcessId, int WindowsSessionId,
    string ChildNonce, int GameProcessId, long GameStartedAtUtcTicks, string CaptureType, string? ReadbackMode)
{
    /// <summary>Direct reference equality is necessary; matching PID or serialized metadata alone is insufficient.</summary>
    internal bool Matches(NavigationBaselineOwnerBinding other) =>
        ReferenceEquals(Runtime, other.Runtime) && ReferenceEquals(Capture, other.Capture) && ReferenceEquals(Input, other.Input)
        && ChildProcessId == other.ChildProcessId && WindowsSessionId == other.WindowsSessionId
        && string.Equals(ChildNonce, other.ChildNonce, StringComparison.Ordinal)
        && GameProcessId == other.GameProcessId && GameStartedAtUtcTicks == other.GameStartedAtUtcTicks
        && string.Equals(CaptureType, other.CaptureType, StringComparison.Ordinal)
        && string.Equals(ReadbackMode, other.ReadbackMode, StringComparison.Ordinal);

    /// <summary>Incomplete proof is allowed for no continuation; reverse admission fails closed instead of inferring it.</summary>
    internal bool Complete => Runtime is not null && Capture is not null && Input is not null
        && ChildProcessId > 0 && WindowsSessionId > 0 && GameProcessId > 0 && GameStartedAtUtcTicks > 0
        && Guid.TryParseExact(ChildNonce, "N", out var nonce) && nonce != Guid.Empty
        && !string.IsNullOrEmpty(CaptureType) && ReadbackMode is "blocking" or "poll_single_v1";
}
