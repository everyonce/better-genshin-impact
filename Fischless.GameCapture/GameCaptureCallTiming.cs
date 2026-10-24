using System.Diagnostics;

namespace Fischless.GameCapture;

/// <summary>
/// Fixed-size, invocation-local wall-clock evidence. Internal writers finish before return/throw;
/// timestamps are raw QPC ticks, not GPU execution times or replacement source timestamps.
/// </summary>
public sealed class GameCaptureCallTiming
{
    /// <summary>Schema for the bounded optional diagnostic contract.</summary>
    public int Version => 1;
    /// <summary>Frequency needed to interpret every local clock in this record.</summary>
    public long ClockFrequency { get; } = Stopwatch.Frequency;
    /// <summary>Managed caller identity; it does not identify a physical GPU execution context.</summary>
    public int ManagedThreadId { get; } = Environment.CurrentManagedThreadId;
    /// <summary>Method entry before either capture lock.</summary>
    public long StartedAtTicks { get; } = Stopwatch.GetTimestamp();
    /// <summary>Method completion after lock release, including null and exceptional exits.</summary>
    public long CompletedAtTicks { get; internal set; }
    /// <summary>True only when this call's zero-time monitor probe failed; false does not exclude descheduling before/during the probe.</summary>
    public bool? CaptureGateContended { get; internal set; }
    /// <summary>QPC immediately before the diagnostic-only zero-time monitor probe.</summary>
    public long? CaptureGateProbeStartedAtTicks { get; internal set; }
    /// <summary>QPC immediately after the probe, before any required blocking Enter.</summary>
    public long? CaptureGateProbeCompletedAtTicks { get; internal set; }
    /// <summary>Process-wide cumulative GC counters sampled before entering capture; null means no sample was taken.</summary>
    public GameCaptureGcSnapshot? GcBefore { get; internal set; }
    /// <summary>Process-wide counters after capture locks are released, including null/exceptional exits; delta is not thread/stage attribution.</summary>
    public GameCaptureGcSnapshot? GcAfter { get; internal set; }
    /// <summary>Single-flight lock acquired; preceding time includes contention and scheduling.</summary>
    public long? CaptureGateAcquiredAtTicks { get; internal set; }
    /// <summary>Initial state/lifecycle lock acquired after the single-flight lock.</summary>
    public long? StateLockAcquiredAtTicks { get; internal set; }
    /// <summary>Bounded native pool selection entry, including property reads and discarded-frame disposal; diagnostic and ordinary paths request the same frames.</summary>
    public long? PoolStartedAtTicks { get; internal set; }
    /// <summary>Bounded pool selection exit, also recorded if a pull, property read or discarded-frame disposal throws.</summary>
    public long? PoolCompletedAtTicks { get; internal set; }
    /// <summary>Geometry/render work begins after original first-acquisition stamping.</summary>
    public long? RenderStartedAtTicks { get; internal set; }
    /// <summary>Render helper exit after its original surface/frame disposal boundaries.</summary>
    public long? RenderCompletedAtTicks { get; internal set; }
    /// <summary>Pack/staging setup and command submission begins, after the cache decision.</summary>
    public long? SubmitStartedAtTicks { get; internal set; }
    /// <summary>Pack/staging command submission exits, including exceptional exits.</summary>
    public long? SubmitCompletedAtTicks { get; internal set; }
    /// <summary>Blocking readback Map entry; this wall interval may include driver/GPU waiting.</summary>
    public long? ReadbackMapStartedAtTicks { get; internal set; }
    /// <summary>Blocking readback Map exit, also recorded on failure.</summary>
    public long? ReadbackMapCompletedAtTicks { get; internal set; }
    /// <summary>CPU conversion/cache/copy work entry; cache hits have no readback Map.</summary>
    public long? CpuCopyStartedAtTicks { get; internal set; }
    /// <summary>CPU copy branch exit, including its original Unmap/disposal cleanup.</summary>
    public long? CpuCopyCompletedAtTicks { get; internal set; }
    /// <summary>Last entered stage, retained independently of the final outcome.</summary>
    public string LastStage { get; internal set; } = "capture_gate";
    /// <summary>frame, null, or threw; a successful native acquisition can still return cached pixels.</summary>
    public string Outcome { get; internal set; } = "in_progress";
    /// <summary>Only the bounded exception type is retained; no arbitrary native messages are copied.</summary>
    public string? ExceptionType { get; internal set; }
    /// <summary>First failing stage, even when the existing backend catches the exception and returns null/cache.</summary>
    public string? FailureStage { get; internal set; }
    /// <summary>not_called, empty, acquired, rejected_identity, or threw.</summary>
    public string PoolResult { get; internal set; } = "not_called";
    /// <summary>Native pull attempts in this selection, including null/throw; at most two.</summary>
    public int PoolPullCount { get; internal set; }
    /// <summary>Non-null frames obtained before inspecting their source/geometry; at most two.</summary>
    public int PoolFrameCount { get; internal set; }
    /// <summary>Disposal attempts for obtained frames not handed to the renderer, including failure cleanup; at most two, not proof that native Close succeeded.</summary>
    public int PoolDiscardedFrameCount { get; internal set; }
    /// <summary>Whether the returned pixels were copied from the existing CPU cache.</summary>
    public bool? CacheHit { get; internal set; }
    /// <summary>Whether this call entered the original frame-pool resize branch.</summary>
    public bool Recreated { get; internal set; }
    /// <summary>Selected conversion path, captured while holding the original state lock.</summary>
    public bool? CpuConvert { get; internal set; }
    /// <summary>Selected render path; diagnostics do not change the setting.</summary>
    public bool? DrawWrite { get; internal set; }
    /// <summary>Newest exact source accepted during pool selection, even if later geometry/disposal/render fails; null when none was accepted.</summary>
    public GameCaptureSourceInfo? AcquiredSource { get; internal set; }
    /// <summary>Exact identity of returned pixels, including immutable cached acquisition time.</summary>
    public GameCaptureSourceInfo? ReturnedSource { get; internal set; }

    /// <summary>Finalize a diagnostic invocation without intercepting or replacing its exception.</summary>
    internal static GameCaptureFrame? Run(Func<GameCaptureCallTiming, GameCaptureFrame?> capture,
        out GameCaptureCallTiming timing)
    {
        timing = new GameCaptureCallTiming();
        try
        {
            timing.GcBefore = GameCaptureGcSnapshot.Read();
            var frame = capture(timing);
            timing.Outcome = frame is null ? "null" : "frame";
            timing.ReturnedSource = frame?.SourceInfo;
            return frame;
        }
        catch (Exception error)
        {
            timing.Outcome = "threw";
            timing.RecordFailure(error);
            throw;
        }
        finally
        {
            timing.GcAfter = GameCaptureGcSnapshot.Read();
            timing.CompletedAtTicks = Stopwatch.GetTimestamp();
        }
    }

    /// <summary>Retain the original bounded failure before cleanup changes the current stage.</summary>
    internal void RecordFailure(Exception error)
    {
        if (ExceptionType is not null) return;
        FailureStage = LastStage;
        var name = error.GetType().Name;
        ExceptionType = name[..Math.Min(name.Length, 96)];
    }
}

/// <summary>
/// Bounded process-wide GC counter sample. Reads are sequential, not atomic; the QPC
/// boundaries locate sampling overhead and GC activity, not a pause of this particular caller.
/// </summary>
public readonly record struct GameCaptureGcSnapshot
{
    /// <summary>QPC immediately before reading cumulative counters; convert with the enclosing ClockFrequency.</summary>
    public long ReadStartedAtTicks { get; internal init; }
    /// <summary>QPC immediately after the final collection count read.</summary>
    public long ReadCompletedAtTicks { get; internal init; }
    /// <summary>GC.GetTotalPauseDuration().Ticks since process start; fixed 100ns TimeSpan units, not QPC ticks.</summary>
    public long TotalPauseDuration100ns { get; internal init; }
    /// <summary>Cumulative generation-zero collection count, as reported by GC.CollectionCount(0).</summary>
    public int Gen0Collections { get; internal init; }
    /// <summary>Cumulative generation-one collection count, as reported by GC.CollectionCount(1).</summary>
    public int Gen1Collections { get; internal init; }
    /// <summary>Cumulative generation-two collection count, as reported by GC.CollectionCount(2).</summary>
    public int Gen2Collections { get; internal init; }

    /// <summary>Diagnostic-only process counter reads; no collection, mode change or tuning is requested.</summary>
    internal static GameCaptureGcSnapshot Read()
    {
        var start = Stopwatch.GetTimestamp();
        var pause = GC.GetTotalPauseDuration().Ticks;
        var gen0 = GC.CollectionCount(0);
        var gen1 = GC.CollectionCount(1);
        var gen2 = GC.CollectionCount(2);
        var complete = Stopwatch.GetTimestamp();
        return new GameCaptureGcSnapshot { ReadStartedAtTicks = start, ReadCompletedAtTicks = complete,
            TotalPauseDuration100ns = pause, Gen0Collections = gen0, Gen1Collections = gen1, Gen2Collections = gen2 };
    }
}
