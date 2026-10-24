using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.GameTask.Runtime;
using System;
using System.Collections.Generic;
using System.Linq;
using Vanara.PInvoke;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Maps canonical model inputs into the single InputHub owner for a bound runtime.</summary>
internal sealed class RuntimeAgentInput(GameRuntime runtime) : IAgentInput
{
    /// <summary>Only transitions are sent; consecutive intervals can retain a held key.</summary>
    private readonly HashSet<User32.VK> _held = [];

    /// <inheritdoc />
    public bool IsAvailable => (!runtime.IsDesktopCapture || runtime.AllowsDesktopController && runtime.Capture.IsCapturing && runtime.Window.IsForeground) &&
        !runtime.IsStopping && runtime.Window.IsAlive && !runtime.Window.IsMinimized &&
        (!runtime.Window.RequiresForeground || runtime.Window.IsForeground) && ReferenceEquals(InputHub.Backend, runtime.Input);

    /// <inheritdoc />
    public void SetHeldKeys(string[] keys)
    {
        runtime.ThrowIfDesktopControllerUnavailable();
        if (!IsAvailable) throw new InvalidOperationException("The agent's game window is unavailable.");
        var desired = keys.Select(ToVirtualKey).ToHashSet();
        var channel = InputHub.Foreground;
        foreach (var key in _held.Except(desired).ToArray())
        {
            channel.Keyboard.KeyUp(key);
            _held.Remove(key);
        }
        foreach (var key in desired.Except(_held).ToArray())
        {
            runtime.ThrowIfDesktopControllerUnavailable();
            channel.Keyboard.KeyDown(key);
            _held.Add(key);
        }
    }

    /// <inheritdoc />
    public void MoveMouse(int dx, int dy)
    {
        runtime.ThrowIfDesktopControllerUnavailable();
        if (!IsAvailable) throw new InvalidOperationException("The agent's game window is unavailable.");
        InputHub.Foreground.Mouse.MoveMouseBy(dx, dy);
    }

    /// <inheritdoc />
    public void ReleaseAll()
    {
        // A stopped runtime must never release keys on a newly attached backend.
        if (ReferenceEquals(InputHub.Backend, runtime.Input)) InputHub.ReleaseAll();
        _held.Clear();
    }

    /// <summary>Normalize documented aliases without accepting arbitrary Windows hotkeys.</summary>
    private static User32.VK ToVirtualKey(string key) => key switch
    {
        "ESC" or "ESCAPE" => User32.VK.VK_ESCAPE,
        "SHIFT" or "LSHIFT" => User32.VK.VK_LSHIFT,
        "CONTROL" or "LCONTROL" => User32.VK.VK_LCONTROL,
        _ => Enum.Parse<User32.VK>("VK_" + key)
    };
}
