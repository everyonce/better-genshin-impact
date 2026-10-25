using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.GameTask.Runtime;
using System;
using System.Collections.Generic;
using System.Linq;
using Vanara.PInvoke;
using Newtonsoft.Json.Linq;
using BetterGenshinImpact.Core.Input.Backends.Win32;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Maps canonical model inputs into the single InputHub owner for a bound runtime.</summary>
internal sealed class RuntimeAgentInput(GameRuntime runtime) : IAgentInput, IAgentApplicationInput
{
    /// <summary>Only transitions are sent; consecutive intervals can retain a held key.</summary>
    private readonly HashSet<User32.VK> _held = [];
    /// <summary>Exact backend/channel captured for this one runtime; no later backend may inherit its authority.</summary>
    private readonly IInputBackend _applicationBackend = runtime.Input;
    /// <summary>Per-input-instance epoch, independent of model/client labels.</summary>
    private readonly string _applicationEpoch = Guid.NewGuid().ToString("N");
    /// <summary>Only the controller may install one bounded proof during its dispatch critical section.</summary>
    private AgentStepApplicationEvidence? _applicationProof;
    /// <summary>Legacy calls/releases make authority bookkeeping uncertain; no release infers physical state.</summary>
    private bool _applicationKnown = true;
    /// <summary>Completed evaluation generation and exact prior requested key order.</summary>
    private long _applicationGeneration;
    /// <summary>Empty constructor state is local software bookkeeping only.</summary>
    private string[] _applicationKeys = [];

    /// <inheritdoc />
    public string ApplicationBackendEpoch => ReferenceEquals(InputHub.Backend, _applicationBackend) &&
        ReferenceEquals(runtime.Input, _applicationBackend) && _applicationBackend.Foreground.GetType() == typeof(SendInputChannel)
        ? _applicationEpoch : "backend_changed_or_unsupported";

    /// <inheritdoc />
    public JObject ApplicationTrackedState => new() { ["keys"] = new JArray(_applicationKnown ? _applicationKeys : _held.Select(KeyName).ToArray()),
        ["generation"] = _applicationGeneration, ["complete"] = _applicationKnown };

    /// <inheritdoc />
    public void BeginApplication(AgentStepApplicationEvidence proof)
    {
        AgentStepApplicationWire.Require(_applicationProof is null && _applicationKnown && ApplicationBackendEpoch == _applicationEpoch, "application_input_state");
        _applicationProof = proof;
    }

    /// <inheritdoc />
    public void EndApplication(bool completed, string[] desired)
    {
        _applicationProof = null;
        _applicationKnown = completed && ApplicationBackendEpoch == _applicationEpoch && _held.SetEquals(desired.Select(ToVirtualKey));
        if (_applicationKnown) { _applicationGeneration = checked(_applicationGeneration + 1); _applicationKeys = desired.ToArray(); }
    }

    /// <summary>Canonical VK spelling is used only after aliases have been excluded from this authority mode.</summary>
    private static string KeyName(User32.VK key) => key.ToString()[3..];

    /// <summary>Keep telemetry around the original backend/bookkeeping operation; application proof observes its return.</summary>
    private void ApplicationCall(string operation, string? key, int dx, int dy, Action invoke)
    {
        // The tracked mutation stays inside telemetry and precedes fallible application post-call clocks.
        // Telemetry still absorbs its own observer failures and never replaces a backend exception.
        if (_applicationProof is null) Telemetry.Invoke(operation, key, dx, dy, invoke);
        else _applicationProof.Call(operation, key, dx, dy, () => Telemetry.Invoke(operation, key, dx, dy, invoke));
    }

    /// <summary>Optional observation is synchronous and never changes a backend call's result.</summary>
    internal AgentInputCallObserver Telemetry { get; } = new();

    /// <summary>Read only while the controller lock serializes this runtime's input calls.</summary>
    internal AgentTrackedInputState ReadTrackedState() => new(
        _held.Select(key => key.ToString()[3..]).OrderBy(key => key, StringComparer.Ordinal).ToArray(),
        Telemetry.ExecutionUncertain || Telemetry.Incomplete, Telemetry.ReleaseOutcome, Telemetry.Incomplete);

    /// <inheritdoc />
    public bool IsAvailable => (!runtime.IsDesktopCapture || runtime.AllowsDesktopController && runtime.Capture.IsCapturing && runtime.Window.IsForeground) &&
        !runtime.IsStopping && runtime.Window.IsAlive && !runtime.Window.IsMinimized &&
        (!runtime.Window.RequiresForeground || runtime.Window.IsForeground) && ReferenceEquals(InputHub.Backend, runtime.Input);

    /// <inheritdoc />
    public void SetHeldKeys(string[] keys)
    {
        if (_applicationProof is null) _applicationKnown = false;
        runtime.ThrowIfDesktopControllerUnavailable();
        if (!IsAvailable) throw new InvalidOperationException("The agent's game window is unavailable.");
        var desired = keys.Select(ToVirtualKey).ToHashSet();
        var channel = InputHub.Foreground;
        foreach (var key in _held.Except(desired).ToArray())
        {
            ApplicationCall(IsMouseButton(key) ? "buttonUp" : "keyUp", key.ToString()[3..], 0, 0, () =>
            {
                channel.Keyboard.KeyUp(key);
                _held.Remove(key);
            });
        }
        foreach (var key in desired.Except(_held).ToArray())
        {
            runtime.ThrowIfDesktopControllerUnavailable();
            ApplicationCall(IsMouseButton(key) ? "buttonDown" : "keyDown", key.ToString()[3..], 0, 0, () =>
            {
                channel.Keyboard.KeyDown(key);
                _held.Add(key);
            });
        }
    }

    /// <inheritdoc />
    public void MoveMouse(int dx, int dy)
    {
        runtime.ThrowIfDesktopControllerUnavailable();
        if (!IsAvailable) throw new InvalidOperationException("The agent's game window is unavailable.");
        ApplicationCall("mouseMove", null, dx, dy, () => InputHub.Foreground.Mouse.MoveMouseBy(dx, dy));
    }

    /// <inheritdoc />
    public void ReleaseAll()
    {
        _applicationKnown = false;
        // A stopped runtime must never release keys on a newly attached backend.
        var sameBackend = ReferenceEquals(InputHub.Backend, runtime.Input);
        Telemetry.Invoke("releaseAll", null, 0, 0, () =>
        {
            if (sameBackend) InputHub.ReleaseAll();
            _held.Clear();
        }, sameBackend ? "returned_unverified" : "skipped_backend_changed");
    }

    /// <summary>Match the existing keyboard-interface forwarding for the allowed mouse virtual keys.</summary>
    private static bool IsMouseButton(User32.VK key) => key is User32.VK.VK_LBUTTON or User32.VK.VK_RBUTTON or User32.VK.VK_MBUTTON;

    /// <summary>Normalize documented aliases without accepting arbitrary Windows hotkeys.</summary>
    private static User32.VK ToVirtualKey(string key) => key switch
    {
        "ESC" or "ESCAPE" => User32.VK.VK_ESCAPE,
        "SHIFT" or "LSHIFT" => User32.VK.VK_LSHIFT,
        "CONTROL" or "LCONTROL" => User32.VK.VK_LCONTROL,
        _ => Enum.Parse<User32.VK>("VK_" + key)
    };
}

/// <summary>Small synchronous observer shared with inert fixtures; it never retries or suppresses a backend exception.</summary>
internal sealed class AgentInputCallObserver
{
    /// <summary>Controller-owned callback, installed once before starting any session loop.</summary>
    internal Action<AgentInputCall>? Sink { get; set; }
    /// <summary>Runtime-local operation ID; distinct from the controller event sequence.</summary>
    private long _callId;
    /// <summary>Observation failure is reported without changing input success or failure.</summary>
    internal bool Incomplete { get; private set; }
    /// <summary>Latched uncertainty is never cleared by an aggregate release.</summary>
    internal bool ExecutionUncertain { get; private set; }
    /// <summary>Aggregate return does not certify any individual release.</summary>
    internal string ReleaseOutcome { get; private set; } = "not_requested";

    /// <summary>Observe exactly one unchanged operation, including its original bookkeeping, without adding a lock.</summary>
    internal void Invoke(string operation, string? key, int dx, int dy, Action action, string returnedStage = "returned")
    {
        var id = _callId;
        if (_callId == long.MaxValue) Incomplete = true;
        else id = ++_callId;
        if (operation == "releaseAll")
        {
            ExecutionUncertain = true;
            ReleaseOutcome = "started";
        }
        Emit(id, operation, "started", key, dx, dy, null);
        try
        {
            action();
        }
        catch (Exception error)
        {
            ExecutionUncertain = true;
            if (operation == "releaseAll") ReleaseOutcome = "failed";
            Emit(id, operation, "failed", key, dx, dy, error.GetType().Name);
            throw;
        }
        if (operation == "releaseAll") ReleaseOutcome = returnedStage;
        Emit(id, operation, returnedStage, key, dx, dy, null);
    }

    /// <summary>Diagnostic exceptions cannot change the outcome of the observed input operation.</summary>
    private void Emit(long id, string operation, string stage, string? key, int dx, int dy, string? error)
    {
        try { Sink?.Invoke(new AgentInputCall(id, operation, stage, key, dx, dy,
            error is { Length: > 128 } ? error[..128] : error)); }
        catch (Exception) { Incomplete = true; }
    }
}
