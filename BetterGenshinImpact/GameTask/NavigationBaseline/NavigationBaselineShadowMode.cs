using System;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One explicit capture-only archive; omission preserves the existing baseline.</summary>
internal static class NavigationBaselineShadowMode
{
    /// <summary>No model, input, independent capture loop, or live intent transport is enabled by this selector.</summary>
    internal const string Rgb192 = "rgb192-capture-only-v1";

    /// <summary>Validate before owner admission; explicit wire null is rejected by the request parser.</summary>
    internal static void Validate(string? mode, string timingContract, string capturePolicy)
    {
        if (mode is null) return;
        if (mode != Rgb192) throw new ArgumentException("unsupported_shadow_capture", nameof(mode));
        if (timingContract != NavigationBaselineTiming.V4 || capturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer)
            throw new ArgumentException("shadow_capture_requires_v4_task_owned_timer");
    }
}
