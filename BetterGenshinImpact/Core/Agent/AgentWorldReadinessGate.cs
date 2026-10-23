using System;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Conservative world admission: immediate blocking, two fresh positive captures to resume.</summary>
public sealed class AgentWorldReadinessGate
{
    /// <summary>One transient HUD match cannot resume a paused controller.</summary>
    public const int ConfirmationFrames = 2;
    /// <summary>A frozen capture/recognition loop loses input authority independently of model latency.</summary>
    public const double MaxAgeMs = 150;
    /// <summary>Latest source-specific decision, including blocked and confirming observations.</summary>
    private AgentWorldReadiness _current = new(false, "world_unchecked", 0, 0, 0, 0, 0);
    /// <summary>One generation per interruption; blocked polling never advances it repeatedly.</summary>
    private long _epoch;
    /// <summary>Consecutive positive captures since the most recent interruption.</summary>
    private int _confirmations;
    /// <summary>Reject late publication of captures started before a release or focus interruption.</summary>
    private double _invalidThroughMs = double.NegativeInfinity;
    /// <summary>Captures cannot be reused as the second confirmation.</summary>
    private long _lastFrameId = -1;
    /// <summary>Last valid native source, retained across pauses to prevent duplicate confirmations.</summary>
    private AgentSourceFrame? _lastSource;

    /// <summary>Assess immutable server capture evidence; caller serializes access with the input lock.</summary>
    public AgentWorldReadiness Observe(AgentObservation frame, double checkedAtMs, bool windowAvailable = true)
    {
        if (!double.IsFinite(checkedAtMs) || !double.IsFinite(frame.CapturedAtMs) ||
            !double.IsFinite(frame.RecognitionMs) || frame.RecognitionMs < 0 || frame.CapturedAtMs < 0 ||
            checkedAtMs < frame.CapturedAtMs || frame.CapturedAtMs < _current.SourceCapturedAtMs ||
            frame.FrameId <= _lastFrameId)
            return Block(double.IsFinite(checkedAtMs) ? checkedAtMs : _current.CheckedAtMs, "invalid_world_observation");

        _lastFrameId = frame.FrameId;
        var previousCapture = AuthorityTime(_current);
        _current = new(false, "world_confirming", frame.FrameId, frame.CapturedAtMs, checkedAtMs, frame.RecognitionMs, _epoch, frame.SourceFrame);
        // Keep exact-frame telemetry while focus is absent, without creating a new positive confirmation.
        if (!windowAvailable) return Invalidate(checkedAtMs, "window_unavailable");
        var capturedAt = frame.SourceFrame?.CapturedAtMs ?? frame.CapturedAtMs;
        var repeatedSource = false;
        if (frame.SourceFrame is { } source)
        {
            // Reject invalid clock metadata without poisoning the last valid source or moving interruption cutoffs.
            // A microsecond tolerance covers the documented cross-thread QPC ordering/100ns conversion precision.
            if (!Guid.TryParseExact(source.CaptureEpoch, "N", out var epoch) || epoch == Guid.Empty || source.Timestamp100ns <= 0 ||
                !double.IsFinite(source.CapturedAtMs) || !double.IsFinite(source.AcquiredAtMs) ||
                source.CapturedAtMs > source.AcquiredAtMs + 0.001 || source.AcquiredAtMs > checkedAtMs + 0.001)
                return Block(checkedAtMs, "invalid_source_timing");
            if (_lastSource is { } previous)
            {
                if (source.CaptureEpoch != previous.CaptureEpoch)
                    Block(checkedAtMs, "source_epoch_changed", true);
                else
                {
                    if (source.Timestamp100ns < previous.Timestamp100ns || source.CapturedAtMs < previous.CapturedAtMs ||
                        source.Timestamp100ns == previous.Timestamp100ns && source.CapturedAtMs != previous.CapturedAtMs)
                        return Block(checkedAtMs, "source_timing_regressed");
                    repeatedSource = source.Timestamp100ns == previous.Timestamp100ns;
                }
            }
            _lastSource = source;
        }
        else if (_lastSource is not null)
        {
            // A known source cannot silently downgrade to poll-time freshness midway through the same stream.
            return Block(checkedAtMs, "source_timing_missing");
        }
        if (capturedAt <= _invalidThroughMs)
        {
            return Block(checkedAtMs, "world_observation_invalidated");
        }
        if (checkedAtMs - capturedAt > MaxAgeMs)
            return Block(checkedAtMs, "world_observation_stale");
        if (frame.WorldEvidence != AgentWorldEvidence.WorldHud)
        {
            var reason = frame.WorldEvidence switch
            {
                AgentWorldEvidence.HudMissing => "world_hud_missing",
                AgentWorldEvidence.BlockingUi => "world_overlay_detected",
                AgentWorldEvidence.RecognitionFailed => "world_recognition_failed",
                _ => "world_unchecked"
            };
            // A visual block excludes older source images, not every later image delayed behind recognition.
            _invalidThroughMs = Math.Max(_invalidThroughMs, capturedAt);
            return Block(checkedAtMs, reason);
        }

        // Cached pixels may remain ready within their original age, but can never provide another confirmation.
        if (repeatedSource)
            return _current = _current with { Ready = _confirmations == ConfirmationFrames,
                Reason = _confirmations == ConfirmationFrames ? "world_ready" : "world_confirming" };

        // Confirmation is consecutive in time as well as in frame sequence.
        if (capturedAt - previousCapture > MaxAgeMs && _confirmations > 0)
        {
            // A gap can happen between two capture calls even if no input tick ran in between.
            _epoch++;
            _confirmations = 0;
            _current = _current with { Epoch = _epoch };
        }
        _confirmations = Math.Min(ConfirmationFrames, _confirmations + 1);
        var ready = _confirmations == ConfirmationFrames;
        return _current = _current with { Ready = ready, Reason = ready ? "world_ready" : "world_confirming" };
    }

    /// <summary>Close a previously positive gate when no fresh recognition arrives.</summary>
    public AgentWorldReadiness Get(double now)
    {
        if ((_current.Ready || _confirmations > 0) && now - AuthorityTime(_current) > MaxAgeMs)
            return Block(now, "world_observation_stale");
        return _current;
    }

    /// <summary>Invalidate in-flight captures as well as previously published frames on an interruption.</summary>
    public AgentWorldReadiness Invalidate(double now, string reason, bool forceNewEpoch = false)
    {
        _invalidThroughMs = Math.Max(_invalidThroughMs, now);
        return Block(now, reason, forceNewEpoch);
    }

    /// <summary>Close the gate without letting rejected/delayed observations continually advance the cutoff.</summary>
    private AgentWorldReadiness Block(double now, string reason, bool forceNewEpoch = false)
    {
        if (forceNewEpoch || _current.Ready || _confirmations > 0) _epoch++;
        _confirmations = 0;
        return _current = _current with { Ready = false, Reason = reason, CheckedAtMs = now, Epoch = _epoch };
    }

    /// <summary>Unknown backends retain the explicitly labeled host-request fallback.</summary>
    private static double AuthorityTime(AgentWorldReadiness readiness) => readiness.SourceFrame?.CapturedAtMs ?? readiness.SourceCapturedAtMs;
}
