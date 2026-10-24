using SharpDX;
using Vanara.PInvoke;

namespace Fischless.GameCapture.Graphics.Helpers;

/// <summary>One generation's metadata reservation. Native staging ownership stays in GraphicsCaptureV2.</summary>
internal sealed class WgcReadbackSlot
{
    /// <summary>The only generation allowed to submit or publish through this slot.</summary>
    private readonly Guid _epoch;
    /// <summary>Never reused within this generation, even after a failed submission.</summary>
    private long _nextSubmission;
    /// <summary>Ambiguous native work permanently prevents reuse until a new Start creates another slot.</summary>
    internal bool IsFaulted { get; private set; }
    /// <summary>Stopped slots cannot publish after delayed work completes.</summary>
    internal bool IsStopped { get; private set; }
    /// <summary>One immutable reservation or null; it never owns the aliased native staging resource.</summary>
    internal GameCapturePendingReadback? Pending { get; private set; }

    /// <summary>Create a slot for one nonempty capture epoch.</summary>
    internal WgcReadbackSlot(Guid epoch)
    {
        if (epoch == Guid.Empty) throw new ArgumentException("A capture epoch is required.", nameof(epoch));
        _epoch = epoch;
    }

    /// <summary>Parse the exact Start setting; missing always resets to the original blocking mode.</summary>
    internal static GameCaptureReadbackMode ReadMode(Dictionary<string, object>? settings)
    {
        if (settings is null || !settings.TryGetValue("ReadbackMode", out var value)) return GameCaptureReadbackMode.Blocking;
        return value switch
        {
            "blocking" => GameCaptureReadbackMode.Blocking,
            "poll_single_v1" => GameCaptureReadbackMode.PollSingleV1,
            _ => throw new ArgumentException("ReadbackMode must be exactly blocking or poll_single_v1.", nameof(settings))
        };
    }

    /// <summary>Reserve before the native copy, so a partial submission cannot be retried accidentally.</summary>
    internal GameCapturePendingReadback Begin(GameCaptureSourceInfo source, long submittedAtTicks,
        int width, int height, RECT? captureRect)
    {
        EnsureActive();
        if (Pending is not null) throw new InvalidOperationException("A staging copy is already pending.");
        if (source.CaptureEpoch != _epoch || source.SourceTimestamp100ns <= 0 || source.AcquiredAtStopwatchTicks <= 0
            || submittedAtTicks < source.AcquiredAtStopwatchTicks || width <= 0 || height <= 0)
            throw new ArgumentException("Invalid pending source, geometry or submission clock.");
        Pending = new GameCapturePendingReadback(checked(++_nextSubmission), source, submittedAtTicks, width, height, captureRect);
        return Pending;
    }

    /// <summary>One actual Map attempt; busy never copies/unmaps/commits, and successful Unmap precedes publication.</summary>
    internal bool TryComplete(Func<DataBox> map, Action<DataBox> copy, Action unmap,
        Action<GameCapturePendingReadback> publish)
    {
        EnsureActive();
        var pending = Pending ?? throw new InvalidOperationException("No staging copy is pending.");
        try
        {
            var mapped = map();
            if (mapped.IsEmpty) return false;
            try { copy(mapped); }
            finally { unmap(); }
            // A close/cancellation observed while native work ran must not become a completed cache.
            EnsureActive();
            if (!ReferenceEquals(Pending, pending)) throw new InvalidOperationException("The readback reservation changed.");
            publish(pending);
            Pending = null;
            return true;
        }
        catch { Fault(); throw; }
    }

    /// <summary>Latch uncertainty; no later poll can retry the native copy or revive its source.</summary>
    internal void Fault() { IsFaulted = true; Pending = null; }
    /// <summary>Forget the alias after active callers drain; never Map or wait to retire pending GPU work.</summary>
    internal void Stop() { IsStopped = true; Pending = null; }
    /// <summary>Reject every operation on retired or faulted state.</summary>
    private void EnsureActive()
    {
        if (IsStopped || IsFaulted) throw new InvalidOperationException("The readback slot is stopped or faulted.");
    }
}
