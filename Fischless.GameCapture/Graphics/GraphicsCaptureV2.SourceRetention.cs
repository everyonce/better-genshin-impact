using Fischless.GameCapture.Graphics.Helpers;
using SharpDX.Direct3D11;
using Windows.Graphics.Capture;

namespace Fischless.GameCapture.Graphics;

/// <summary>Isolated diagnostic opt-in: preserve the selected WGC buffer through readback without changing admission.</summary>
public partial class GraphicsCaptureV2
{
    /// <summary>Start-fixed setting; absent means the deployed disposal path remains in use.</summary>
    private bool _sourceRetentionEnabled;
    /// <summary>A failed admitted experiment cannot retry storage or release uncertain GPU ownership early.</summary>
    private bool _sourceRetentionFaulted;
    /// <summary>At most one selected source, independent of slot metadata and the active-call count.</summary>
    private WgcRetainedSourceLease? _retainedSourceLease;
    /// <summary>Bounded diagnostic counters reset only after the previous session has fully retired.</summary>
    private int _sourceLeaseAcquired, _sourceLeaseReleased;
    /// <summary>Last explicit release boundary; it is not a GPU-completion claim during teardown.</summary>
    private string? _sourceLeaseReleaseReason;

    /// <summary>Reject unsupported experimental settings before touching an existing capture lifetime.</summary>
    private static bool ParseSourceRetention(IDictionary<string, object>? settings)
    {
        if (settings is null || !settings.TryGetValue("ExperimentalSourceRetention", out var value)) return false;
        return value is string text && text == "hold-until-readback-v1"
            ? true : throw new ArgumentException("Unknown experimental source retention setting.");
    }

    /// <summary>Fail closed if an unresolved source could be overwritten or resized; callers already hold _lock.</summary>
    private void EnsureSourceRetentionCanRender()
    {
        if (_sourceRetentionEnabled && (_sourceRetentionFaulted || _retainedSourceLease is not null))
            throw new InvalidOperationException("Experimental source lease is unresolved.");
    }

    /// <summary>Transfer only the chosen stable-geometry frame before its surface can submit GPU reads.</summary>
    private bool RetainSelectedSource(Direct3D11CaptureFrame frame, GameCaptureSourceInfo source)
    {
        if (!_sourceRetentionEnabled) return false;
        EnsureSourceRetentionCanRender();
        if (_generation?.IsActive != true || source.CaptureEpoch != _generation.Epoch)
            throw new InvalidOperationException("Experimental source generation changed.");
        _retainedSourceLease = new WgcRetainedSourceLease(frame, source);
        _sourceLeaseAcquired++;
        return true;
    }

    /// <summary>Transfer the queried surface; if attachment fails, dispose the still-local wrapper.</summary>
    private bool RetainSelectedSurface(Texture2D surface)
    {
        if (!_sourceRetentionEnabled) return false;
        try
        {
            (_retainedSourceLease ?? throw new InvalidOperationException("Missing retained source frame."))
                .AttachSurface(surface);
            return true;
        }
        catch { surface.Dispose(); throw; }
    }

    /// <summary>Quarantine this admitted generation without taking lifecycleGate or changing active-call counts.</summary>
    private void FaultSourceRetention(WgcCaptureGeneration? admittedGeneration)
    {
        if (!_sourceRetentionEnabled || admittedGeneration is null) return;
        lock (_lock)
        {
            if (!ReferenceEquals(_generation, admittedGeneration)) return;
            _sourceRetentionFaulted = true;
            _readbackSlot?.Fault();
            InvalidatePublishedFrames();
            // Keep frame/surface and native staging fields until the normal pump retirement.
        }
    }

    /// <summary>Successful Unmap is the experiment's release boundary; no idle source enters _activeCaptures.</summary>
    private void CompleteSourceRetention(WgcCaptureGeneration? admittedGeneration, GameCaptureSourceInfo? completedSource)
    {
        if (!_sourceRetentionEnabled) return;
        lock (_lock)
        {
            if (!ReferenceEquals(_generation, admittedGeneration) || _retainedSourceLease is null
                || !ReferenceEquals(_retainedSourceLease.Source, completedSource))
                throw new InvalidOperationException("Experimental completed source ownership changed.");
            ReleaseSourceRetention("successful_unmap");
        }
    }

    /// <summary>Detach the field before disposal so errors cannot cause a second release or permit reuse.</summary>
    private void ReleaseSourceRetention(string reason)
    {
        var lease = _retainedSourceLease;
        _retainedSourceLease = null;
        if (lease is null) return;
        _sourceLeaseReleaseReason = reason;
        _sourceLeaseReleased++;
        try { lease.Release(); }
        catch { _sourceRetentionFaulted = true; throw; }
    }

    /// <summary>Read metadata only; teardown release is explicitly distinct from successful readback.</summary>
    public object GetExperimentalSourceRetentionSnapshot()
    {
        lock (_lock)
            return new
            {
                mode = _sourceRetentionEnabled ? "hold-until-readback-v1" : "disabled",
                faulted = _sourceRetentionFaulted, held = _retainedSourceLease is not null,
                sourceInfo = _retainedSourceLease?.Source, acquired = _sourceLeaseAcquired,
                releaseAttempts = _sourceLeaseReleased, lastReleaseReason = _sourceLeaseReleaseReason
            };
    }
}
