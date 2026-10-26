using System;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>Upgrade-only two-phase hold; ordinary startup has both signals already completed.</summary>
public sealed class PuloniaStartupHold
{
    /// <summary>State is not read before explicit resume requests initialization.</summary>
    private readonly TaskCompletionSource _initialization = new(TaskCreationOptions.RunContinuationsAsynchronously);
    /// <summary>Queue/trigger work waits for initialization and fresh identity checks.</summary>
    private readonly TaskCompletionSource _execution = new(TaskCreationOptions.RunContinuationsAsynchronously);
    /// <summary>Create the shared hold without delaying Host.StartAsync.</summary>
    public PuloniaStartupHold(bool held)
    {
        if (!held) { _initialization.TrySetResult(); _execution.TrySetResult(); }
    }
    /// <summary>Inspectable even while initialization is pending, failed or cancelled.</summary>
    public bool IsHeld => !_execution.Task.IsCompletedSuccessfully;
    /// <summary>Await execution permission, with service shutdown cancellation.</summary>
    public Task WaitAsync(CancellationToken token) => _execution.Task.WaitAsync(token);
    /// <summary>Await the explicit state-read phase without releasing work.</summary>
    internal Task WaitForInitializationAsync(CancellationToken token) => _initialization.Task.WaitAsync(token);
    /// <summary>Begin parsing; scheduling remains held.</summary>
    internal void AllowInitialization() => _initialization.TrySetResult();
    /// <summary>Release only after the caller has checked parsed state and current identities.</summary>
    internal void Release() => _execution.TrySetResult();
    /// <summary>Protect direct mutations as well as background loops.</summary>
    public void RequireReleased()
    {
        if (IsHeld) throw new InvalidOperationException("Pulonia scheduling is held after upgrade; explicit verified resume is required.");
    }
}
