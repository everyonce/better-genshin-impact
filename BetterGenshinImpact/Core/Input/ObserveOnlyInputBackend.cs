using System;

namespace BetterGenshinImpact.Core.Input;

/// <summary>Final input guard for an observation-only runtime; it never constructs native input channels.</summary>
public sealed class ObserveOnlyInputBackend : IInputBackend
{
    /// <inheritdoc />
    public InputBackendKind Kind => InputBackendKind.Win32;

    /// <summary>No foreground channel can be borrowed from an observation-only runtime.</summary>
    public IInputChannel Foreground => throw new InvalidOperationException("capture_policy_observe_only");

    /// <summary>No background channel can bypass the observation-only policy.</summary>
    public IInputChannel Background => throw new InvalidOperationException("capture_policy_observe_only");

    /// <summary>This backend has never held an input; old ownership is released before attachment.</summary>
    public void ReleaseAll() { }

    /// <summary>No native input resources are owned by this guard.</summary>
    public void Dispose() { }
}
