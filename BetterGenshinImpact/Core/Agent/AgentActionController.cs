using System;
using System.Collections.Generic;
using System.Linq;
using BetterGenshinImpact.Core.Capture;

using System.Diagnostics;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>
/// Bounded, clock-driven action execution. Capture, model inference and transport never run under this lock.
/// A delayed tick cancels the chunk instead of replaying obsolete input transitions in a burst.
/// </summary>
/// <param name="input">Owned input boundary; tests use an in-memory sink.</param>
/// <param name="inputEnabled">Explicit input permission for this bridge invocation.</param>
/// <param name="monotonicClock">Optional session clock sampled inside the lock for readiness snapshots and first-input deadlines.</param>
/// <param name="desktopDcSourcePolicy">Startup-fixed desktop policy, or null for existing backends.</param>
/// <param name="trackedInputState">Optional detached bookkeeping provider, called under the input lock without another lock.</param>
public sealed class AgentActionController(IAgentInput input, bool inputEnabled, Func<double>? monotonicClock = null,
    string? desktopDcSourcePolicy = null, Func<AgentTrackedInputState>? trackedInputState = null)
{
    /// <summary>Preserve the existing policy-aware constructor signature for uninstrumented callers.</summary>
    public AgentActionController(IAgentInput input, bool inputEnabled, Func<double>? monotonicClock, string? desktopDcSourcePolicy)
        : this(input, inputEnabled, monotonicClock, desktopDcSourcePolicy, null)
    {
    }

    /// <summary>Preserve the existing three-argument constructor signature for non-desktop callers.</summary>
    public AgentActionController(IAgentInput input, bool inputEnabled, Func<double>? monotonicClock)
        : this(input, inputEnabled, monotonicClock, null)
    {
    }

    /// <summary>Maximum first-input authority age; legacy proposals retain the same existing age ceiling.</summary>
    public const double MaxActionStartAgeMs = 500;
    /// <summary>Canonical keys accepted by the narrow keyboard/mouse prototype.</summary>
    public static readonly IReadOnlySet<string> AllowedKeys = new HashSet<string>(
        Enumerable.Range('A', 26).Select(c => ((char)c).ToString())
            .Concat(Enumerable.Range(0, 10).Select(i => i.ToString()))
            .Concat(Enumerable.Range(1, 12).Select(i => $"F{i}"))
            .Concat(["SPACE", "SHIFT", "LSHIFT", "RSHIFT", "CONTROL", "LCONTROL", "ESC", "ESCAPE", "TAB",
                "LBUTTON", "RBUTTON", "MBUTTON", "UP", "DOWN", "LEFT", "RIGHT"]), StringComparer.Ordinal);
    /// <summary>Serializes proposals, lifecycle stops and input ticks.</summary>
    private readonly object _gate = new();
    /// <summary>Visual readiness and freshness share the input lock so a blocked frame wins over proposals.</summary>
    private readonly AgentWorldReadinessGate _world = new(desktopDcSourcePolicy);
    /// <summary>Only recent metadata is retained; raw frames use a separate latest-only slot.</summary>
    private readonly Dictionary<long, AgentObservation> _observations = new();
    /// <summary>Anti-replay entries live until their frame can no longer authorize any action.</summary>
    private readonly Dictionary<string, double> _requests = new(StringComparer.Ordinal);
    /// <summary>Bounded completed receipts awaiting consumption by the recorder/client.</summary>
    private readonly Queue<AgentExecutionReceipt> _receipts = new();
    /// <summary>Actually applied transitions for the active chunk.</summary>
    private readonly List<AgentAppliedStep> _applied = [];
    /// <summary>Currently active proposal; a new valid proposal replaces it.</summary>
    private AgentRequest? _active;
    /// <summary>Next interval index.</summary>
    private int _stepIndex;
    /// <summary>Acceptance and scheduling origin for the active proposal.</summary>
    private double _acceptedAt;
    /// <summary>Next interval boundary in server milliseconds.</summary>
    private double _nextStepAt;
    /// <summary>Whether this session can accept further proposals.</summary>
    private bool _stopped;
    /// <summary>Count of dropped receipts, exposed so incomplete recordings can be rejected.</summary>
    private long _droppedReceipts;
    /// <summary>Last observed viewport size; changing it invalidates coordinate-dependent proposals.</summary>
    private (int Width, int Height) _viewport;
    /// <summary>Reject inference results that arrive after a result based on a newer observation.</summary>
    private long _lastAcceptedFrameId;
    /// <summary>Absent by default; production enable is deliberately unavailable pending native-owner integration.</summary>
    private AgentStepApplicationOutbox? _stepApplications;

    /// <summary>Source/test composition seam. A future authenticated session must supply its exact QPC configuration.</summary>
    internal JObject ConfigureStepApplications(JObject config)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(_stepApplications is null && _active is null && !_stopped && input is IAgentApplicationInput, "application_idle_input");
            var actual = (IAgentApplicationInput)input;
            AgentStepApplicationWire.Require((string?)config["backendEpoch"] == actual.ApplicationBackendEpoch, "application_backend");
            _stepApplications = new AgentStepApplicationOutbox(config, actual.ApplicationTrackedState);
            return _stepApplications.Confirmation();
        }
    }

    /// <summary>Validate the complete ACK under the same lock as dispatch; no input is performed.</summary>
    internal void AcknowledgeStepApplications(JObject ack)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(_stepApplications is not null, "application_channel_unavailable");
            _stepApplications!.Acknowledge(ack);
        }
    }

    /// <summary>Snapshot detached retransmission data before transport writes, without draining terminal authority.</summary>
    internal JObject? StepApplicationExtensions()
    {
        lock (_gate) return _stepApplications?.Extensions();
    }

    /// <summary>Bounded retained call events; transport snapshots do not drain this ring.</summary>
    private readonly Queue<AgentInputCallEvent> _inputEvents = new();
    /// <summary>Maximum retained call stages, independent of terminal-receipt capacity.</summary>
    internal const int InputEventCapacity = 256;
    /// <summary>Most recently allocated event sequence.</summary>
    private long _inputSequence;
    /// <summary>Number of old records evicted; not an assertion that a consumer missed them.</summary>
    private long _inputEventsEvicted;
    /// <summary>Any failed observation remains visible until this controller ends.</summary>
    private bool _inputTelemetryComplete = true;
    /// <summary>Last valid telemetry clock, used only to reject malformed telemetry.</summary>
    private double _lastTelemetryAt;
    /// <summary>Latest call retains its request origin after replacement or cleanup.</summary>
    private AgentInputCallEvent? _lastInputEvent;
    /// <summary>Attempt identity is set before calling the backend, including partial failures.</summary>
    private int? _lastAttemptedStepIndex;
    /// <summary>Separate software dispatch status, including failures before any low-level call begins.</summary>
    private string _lastDispatchOutcome = "not_started";
    /// <summary>Call origin distinguishes dispatch from existing release reasons.</summary>
    private string _inputOrigin = "lifecycle";

    /// <summary>Observe a synchronous runtime callback under the existing reentrant input lock.</summary>
    internal void RecordInputCall(AgentInputCall call)
    {
        lock (_gate)
        {
            try
            {
                if (_inputSequence == long.MaxValue) { _inputTelemetryComplete = false; return; }
                var row = new AgentInputCallEvent(++_inputSequence, SampleTelemetryClock(), _active?.RequestId,
                    _active?.ModelId, _active?.FrameId, _lastAttemptedStepIndex, _inputOrigin, call);
                if (_inputEvents.Count == InputEventCapacity)
                {
                    _inputEvents.Dequeue();
                    if (_inputEventsEvicted < long.MaxValue) _inputEventsEvicted++;
                }
                _inputEvents.Enqueue(row);
                _lastInputEvent = row;
            }
            catch (Exception) { _inputTelemetryComplete = false; }
        }
    }

    /// <summary>Read readiness and detached telemetry without allowing a scheduler mutation between them.</summary>
    internal AgentWorldReadiness GetWorldReadinessAndExecutionSnapshot(out double sampledAtMs, out AgentExecutionContext context)
    {
        lock (_gate)
        {
            var readiness = GetWorldReadinessSnapshot(out sampledAtMs);
            context = ExecutionSnapshotUnderLock();
            return readiness;
        }
    }

    /// <summary>Snapshot after lock acquisition; this does not bypass a blocked backend operation.</summary>
    internal AgentExecutionContext GetExecutionContextSnapshot()
    {
        lock (_gate) return ExecutionSnapshotUnderLock();
    }

    /// <summary>Sample only the existing session clock; telemetry clock failure cannot alter input.</summary>
    private double? SampleTelemetryClock()
    {
        try
        {
            var value = monotonicClock?.Invoke();
            if (value is not { } now || !double.IsFinite(now) || now < _lastTelemetryAt)
            {
                _inputTelemetryComplete = false;
                return null;
            }
            _lastTelemetryAt = now;
            return now;
        }
        catch (Exception) { _inputTelemetryComplete = false; return null; }
    }

    /// <summary>Copy local bookkeeping only; the provider must not query the window or acquire another lock.</summary>
    private AgentExecutionContext ExecutionSnapshotUnderLock()
    {
        var sampled = SampleTelemetryClock();
        AgentTrackedInputState state;
        try
        {
            state = trackedInputState?.Invoke() ?? new([], true, "unavailable", true);
            state = state with { HeldKeys = state.HeldKeys.ToArray() };
            if (state.TelemetryIncomplete) _inputTelemetryComplete = false;
        }
        catch (Exception)
        {
            _inputTelemetryComplete = false;
            state = new([], true, "unavailable", true);
        }
        var active = _active is null ? null : new AgentActiveInputContext(_active.RequestId, _active.ModelId,
            _active.FrameId, _acceptedAt, _active.ExpiresAtMs, _active.StartBeforeMs, _nextStepAt, _stepIndex,
            _lastAttemptedStepIndex, _lastDispatchOutcome, _stepIndex < _active.Steps.Length ? _active.Steps[_stepIndex].Keys.ToArray() : null,
            _applied.Count == 0 ? null : _applied[^1].Keys.ToArray());
        return new(sampled, _inputTelemetryComplete && !state.TelemetryIncomplete, state, active, _lastInputEvent,
            _inputEvents.Count == 0 ? 0 : _inputEvents.Peek().Sequence, _inputSequence, _inputEventsEvicted, _inputEvents.ToArray());
    }

    /// <summary>Expose receipt loss without allowing the queue to grow without bound.</summary>
    public long DroppedReceipts { get { lock (_gate) return _droppedReceipts; } }

    /// <summary>Register capture metadata before publishing its corresponding image.</summary>
    public AgentWorldReadiness RegisterFrame(AgentObservation observation, double? checkedAtMs = null)
    {
        lock (_gate)
        {
            var now = checkedAtMs ?? observation.CapturedAtMs;
            if (_stopped) return _world.Invalidate(now, "session_stopped");
            var viewport = (observation.SourceWidth, observation.SourceHeight);
            if (_viewport != default && _viewport != viewport)
            {
                Finish("cancelled", "viewport_changed", observation.CapturedAtMs);
                _observations.Clear();
                _world.Invalidate(now, "viewport_changed");
            }
            _viewport = viewport;
            var readiness = _world.Observe(observation, now, input.IsAvailable);
            // Recheck after recognition admission so focus lost during this operation also revokes input.
            if (!input.IsAvailable) readiness = _world.Invalidate(now, "window_unavailable");
            if (!readiness.Ready)
            {
                ClearBlockedInput(now, readiness.Reason);
                return readiness;
            }
            _observations[observation.FrameId] = observation;
            while (_observations.Count > 128) _observations.Remove(_observations.Keys.Min());
            return readiness;
        }
    }

    /// <summary>Expose the current gate, expiring its evidence independently of inference and transport.</summary>
    public AgentWorldReadiness GetWorldReadiness(double now)
    {
        lock (_gate)
        {
            return ReadWorldReadiness(now, input.IsAvailable);
        }
    }

    /// <summary>Sample response time and immutable readiness together, after waiting for registration and focus checks.</summary>
    public AgentWorldReadiness GetWorldReadinessSnapshot(out double sampledAtMs)
    {
        lock (_gate)
        {
            if (monotonicClock is null)
                throw new InvalidOperationException("World readiness snapshots require a session clock.");
            var windowAvailable = input.IsAvailable;
            // A timestamp read before this lock can precede the newer capture whose readiness we return.
            if (!TryReadStartClock(0, out sampledAtMs))
                throw new InvalidOperationException("The world readiness session clock is invalid.");
            return ReadWorldReadiness(sampledAtMs, windowAvailable);
        }
    }

    /// <summary>Apply freshness and focus decisions while the caller holds the controller lock.</summary>
    private AgentWorldReadiness ReadWorldReadiness(double now, bool windowAvailable)
    {
        var readiness = windowAvailable ? _world.Get(now) : _world.Invalidate(now, "window_unavailable");
        if (!readiness.Ready) ClearBlockedInput(now, readiness.Reason);
        return readiness;
    }

    /// <summary>Missing captures or lifecycle events revoke input without ending the hot stream.</summary>
    public void InvalidateWorld(double now, string reason)
    {
        lock (_gate)
        {
            _world.Invalidate(now, reason);
            ClearBlockedInput(now, reason);
        }
    }

    /// <summary>Discard queued/held actions and pre-release observations; fresh world captures can resume.</summary>
    public void Release(double now)
    {
        lock (_gate)
        {
            _world.Invalidate(now, "client_release", forceNewEpoch: true);
            _observations.Clear();
            Finish("cancelled", "client_release", now);
            if (monotonicClock is not null)
            {
                // Captures acquired while key release was blocked cannot confirm the resumed world.
                if (!TryReadStartClock(now, out var completedAt))
                    throw new InvalidOperationException("The input release session clock is invalid.");
                _world.Invalidate(completedAt, "client_release");
            }
        }
    }

    /// <summary>Validate an immutable proposal before it can become the current input plan.</summary>
    public string? Submit(AgentRequest request, double now) => Submit(request, now, out _);

    /// <summary>Return the actual acceptance-clock sample so transport and final receipts agree.</summary>
    public string? Submit(AgentRequest request, double now, out double acceptedAtMs)
    {
        acceptedAtMs = now;
        lock (_gate)
        {
            if (_stopped) return "session_stopped";
            if (desktopDcSourcePolicy == DesktopCapturePolicy.ObserveOnly) return "capture_policy_observe_only";
            if (!inputEnabled) return "input_disabled";
            if (!input.IsAvailable)
            {
                InvalidateWorld(now, "window_unavailable");
                return "window_unavailable";
            }
            if (!GetWorldReadiness(now).Ready) return "world_not_ready";
            if (string.IsNullOrWhiteSpace(request.RequestId) || request.RequestId.Length > 128) return "invalid_request_id";
            foreach (var expired in _requests.Where(entry => entry.Value <= now).Select(entry => entry.Key).ToArray())
                _requests.Remove(expired);
            if (_requests.ContainsKey(request.RequestId)) return "replayed_request";
            if (_requests.Count >= 4096) return "too_many_recent_requests";
            if (string.IsNullOrWhiteSpace(request.ModelId) || request.ModelId.Length > 256) return "invalid_model_id";
            if (!_observations.TryGetValue(request.FrameId, out var frame)) return "unknown_frame";
            if (request.FrameId < _lastAcceptedFrameId) return "superseded_frame";
            if (!double.IsFinite(request.ObservedAtMs) || Math.Abs(frame.CapturedAtMs - request.ObservedAtMs) > 0.001)
                return "observation_timestamp_mismatch";
            var authorityTime = frame.HostSnapshot?.StartedAtMs ?? frame.SourceFrame?.FreshnessAtMs ?? frame.CapturedAtMs;
            if (!double.IsFinite(authorityTime) || !double.IsFinite(now) || now < authorityTime ||
                now - authorityTime > MaxActionStartAgeMs) return "stale_frame";
            if (!double.IsFinite(request.ExpiresAtMs) || request.ExpiresAtMs <= now ||
                request.ExpiresAtMs > authorityTime + 750) return "invalid_deadline";
            if (request.Steps is null || request.Steps.Length is < 1 or > 6) return "invalid_steps";
            var duration = 0;
            foreach (var step in request.Steps)
            {
                if (step is null || step.DurationMs is < 33 or > 100) return "invalid_interval";
                if (step.Keys is null || step.Keys.Length > 12 || step.Keys.Any(k => k is null || !AllowedKeys.Contains(k)))
                    return "invalid_keys";
                if (step.Keys.Any(k => k is "CONTROL" or "LCONTROL") && step.Keys.Any(k => k is "ESC" or "ESCAPE"))
                    return "reserved_hotkey";
                if (Math.Abs((long)step.MouseDx) > frame.SourceWidth || Math.Abs((long)step.MouseDy) > frame.SourceHeight)
                    return "invalid_mouse_delta";
                duration += step.DurationMs;
            }
            if (request.StartBeforeMs is { } startBefore)
            {
                if (!double.IsFinite(startBefore) || startBefore <= authorityTime ||
                    startBefore > authorityTime + MaxActionStartAgeMs || startBefore > request.ExpiresAtMs)
                    return "invalid_start_deadline";
                // Include lock and validation delay in admission without changing legacy omitted-field behavior.
                if (!TryReadStartClock(now, out now)) return "invalid_start_clock";
                if (now >= startBefore) return "start_deadline_expired";
                if (!GetWorldReadiness(now).Ready) return "world_not_ready";
            }
            if (duration > 250 || now + duration > request.ExpiresAtMs) return "invalid_horizon";
            JObject? applicationBinding = null;
            if (_stepApplications is not null)
            {
                if (_active is not null) return "step_application_active_horizon";
                try { applicationBinding = _stepApplications.CheckSubmission(request); }
                catch (Exception) { return "invalid_step_application_binding"; }
            }
            else if (request.HasStepApplicationEnvelope) return "step_applications_unavailable";
            // Retain through the maximum possible deadline for this frame, not just the supplied deadline.
            _requests.Add(request.RequestId, authorityTime + 750);
            _lastAcceptedFrameId = request.FrameId;
            // A replacement preserves held-state continuity until the next tick, but records the interrupted chunk.
            Finish("replaced", "newer_proposal", now, release: false);
            if (applicationBinding is not null) _stepApplications!.Admitted(request.RequestId, applicationBinding);
            var active = request with { Steps = request.Steps.Select(s => s with { Keys = s.Keys.ToArray() }).ToArray(),
                RawApplicationRequest = (JObject?)request.RawApplicationRequest?.DeepClone() };
            // A record copy preserves presence flags; assigning an absent null would falsely opt a legacy request in.
            if (request.StepApplication is { } envelope)
                active = active with { StepApplication = (JObject)envelope.DeepClone() };
            _active = active;
            _acceptedAt = now;
            acceptedAtMs = now;
            _nextStepAt = now;
            _stepIndex = 0;
            _lastAttemptedStepIndex = null;
            _lastDispatchOutcome = "not_started";
            return null;
        }
    }

    /// <summary>Advance input independently of model/network work; callers tick approximately every 10 ms.</summary>
    public void Tick(double now)
    {
        lock (_gate)
        {
            if (!GetWorldReadiness(now).Ready) return;
            if (_active is null) return;
            if (now >= _active.ExpiresAtMs) { Finish("cancelled", "deadline_expired", now); return; }
            if (_stepIndex == 0 && _active.StartBeforeMs is { } startBefore)
            {
                // Sample after lock/focus checks, immediately before dispatching the first input intent.
                // Once the first interval starts, this deadline never truncates its existing hold/horizon.
                var minimumStartAt = Math.Max(now, _acceptedAt);
                if (!TryReadStartClock(minimumStartAt, out var startAt))
                {
                    Finish("cancelled", "invalid_start_clock", double.IsFinite(minimumStartAt) ? minimumStartAt : _acceptedAt);
                    return;
                }
                now = startAt;
                if (now >= startBefore) { Finish("cancelled", "start_deadline_expired", now); return; }
                // This pure gate read adds no blocking window query after the final clock sample.
                var readiness = _world.Get(now);
                if (!readiness.Ready) { ClearBlockedInput(now, readiness.Reason); return; }
            }
            // An optional first-step clock may advance past acceptance after this tick waited on the lock.
            if (now < _nextStepAt) return;
            if (_stepIndex >= _active.Steps.Length) { Finish("completed", "horizon_complete", now); return; }
            // Never compress several missed transitions into one late frame.
            if (now - _nextStepAt > 50) { Finish("cancelled", "scheduler_late", now); return; }
            var step = _active.Steps[_stepIndex];
            _lastAttemptedStepIndex = _stepIndex;
            var priorOrigin = _inputOrigin;
            _inputOrigin = "dispatch";
            _lastDispatchOutcome = "started";
            try
            {
                if (_stepApplications is null)
                {
                    input.SetHeldKeys(step.Keys);
                    if (step.MouseDx != 0 || step.MouseDy != 0) input.MoveMouse(step.MouseDx, step.MouseDy);
                }
                else
                {
                    // Reserve before any backend call. The same controller gate covers proof and publication.
                    var actual = (IAgentApplicationInput)input;
                    AgentStepApplicationEvidence? proof = null;
                    try
                    {
                        proof = _stepApplications.Reserve(_active.RequestId, actual, Stopwatch.GetTimestamp);
                        // Reservation validation is additional work; do not spend it outside the first-step deadline.
                        if (_stepIndex == 0 && _active.StartBeforeMs is { } applicationDeadline)
                        {
                            if (!TryReadStartClock(Math.Max(now, _acceptedAt), out var applicationStart))
                            {
                                _stepApplications.Poison(); Finish("cancelled", "invalid_start_clock", now); return;
                            }
                            now = applicationStart;
                            if (now >= applicationDeadline)
                            {
                                _stepApplications.Poison(); Finish("cancelled", "start_deadline_expired", now); return;
                            }
                            var applicationReadiness = _world.Get(now);
                            if (!applicationReadiness.Ready)
                            {
                                _stepApplications.Poison(); ClearBlockedInput(now, applicationReadiness.Reason); return;
                            }
                        }
                        actual.BeginApplication(proof);
                        input.SetHeldKeys(step.Keys); proof.HeldCompleted();
                        if (step.MouseDx != 0 || step.MouseDy != 0) input.MoveMouse(step.MouseDx, step.MouseDy);
                        actual.EndApplication(true, step.Keys);
                        _stepApplications.Complete(_active.RequestId, proof.Finish(actual.ApplicationTrackedState, actual.ApplicationBackendEpoch, true));
                    }
                    catch
                    {
                        // Neither a backend error nor an instrumentation failure may retry input or mask the primary error.
                        try
                        {
                            actual.EndApplication(false, step.Keys);
                            if (proof is not null) _stepApplications.Complete(_active.RequestId, proof.Finish(actual.ApplicationTrackedState, actual.ApplicationBackendEpoch, false));
                        }
                        catch { _stepApplications.Poison(); }
                        _stepApplications.Poison(); throw;
                    }
                }
                _applied.Add(new AgentAppliedStep(_stepIndex, now, step.Keys.ToArray(), step.MouseDx, step.MouseDy));
                _stepIndex++;
                _nextStepAt += step.DurationMs;
                _lastDispatchOutcome = "returned";
            }
            catch (Exception) { _lastDispatchOutcome = "failed"; throw; }
            finally { _inputOrigin = priorOrigin; }
        }
    }

    /// <summary>A failed, nonfinite or regressing optional clock cannot authorize first input.</summary>
    private bool TryReadStartClock(double minimum, out double sampled)
    {
        sampled = minimum;
        try
        {
            sampled = monotonicClock?.Invoke() ?? minimum;
            return double.IsFinite(minimum) && double.IsFinite(sampled) && sampled >= minimum;
        }
        catch (Exception)
        {
            return false;
        }
    }

    /// <summary>Drain bounded execution receipts; dropped-count metadata must accompany recordings.</summary>
    public AgentExecutionReceipt[] DrainReceipts()
    {
        lock (_gate)
        {
            var result = _receipts.ToArray();
            _receipts.Clear();
            return result;
        }
    }

    /// <summary>End the session and release held input immediately, including transport failure paths.</summary>
    public void Stop(double now, string reason)
    {
        lock (_gate)
        {
            _stopped = true;
            _world.Invalidate(now, "session_stopped");
            _observations.Clear();
            Finish("cancelled", reason, now);
        }
    }

    /// <summary>A blocked gate revokes every older observation before any later proposal can be accepted.</summary>
    private void ClearBlockedInput(double now, string reason)
    {
        _observations.Clear();
        if (_active is not null) Finish("cancelled", reason, now);
    }

    /// <summary>Record final outcome before clearing the active chunk and its applied transitions.</summary>
    private void Finish(string status, string reason, double now, bool release = true)
    {
        var priorOrigin = _inputOrigin;
        _inputOrigin = "release:" + reason;
        var releaseOutcome = release ? "unknown" : "not_requested";
        try
        {
            if (release && inputEnabled) { input.ReleaseAll(); releaseOutcome = "returned_unverified"; }
        }
        finally
        {
            if (_active is not null)
            {
                if (_stepApplications is not null)
                {
                    try { _stepApplications.Terminal(_active.RequestId, status, reason, now, releaseOutcome, Stopwatch.GetTimestamp); }
                    catch { _stepApplications.Poison(); } // Preserve legacy/input exceptions and retain loss explicitly.
                }
                if (_receipts.Count == 256) { _receipts.Dequeue(); _droppedReceipts++; }
                _receipts.Enqueue(new AgentExecutionReceipt(_active.RequestId, _active.ModelId, _active.FrameId,
                    status, reason, _acceptedAt, now, _applied.ToArray()));
            }
            _active = null;
            _applied.Clear();
            _lastAttemptedStepIndex = null;
            _lastDispatchOutcome = "not_started";
            _inputOrigin = priorOrigin;
        }
    }
}
