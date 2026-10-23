using System;
using System.Collections.Generic;
using System.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>
/// Bounded, clock-driven action execution. Capture, model inference and transport never run under this lock.
/// A delayed tick cancels the chunk instead of replaying obsolete input transitions in a burst.
/// </summary>
public sealed class AgentActionController(IAgentInput input, bool inputEnabled)
{
    /// <summary>Canonical keys accepted by the narrow keyboard/mouse prototype.</summary>
    public static readonly IReadOnlySet<string> AllowedKeys = new HashSet<string>(
        Enumerable.Range('A', 26).Select(c => ((char)c).ToString())
            .Concat(Enumerable.Range(0, 10).Select(i => i.ToString()))
            .Concat(Enumerable.Range(1, 12).Select(i => $"F{i}"))
            .Concat(["SPACE", "SHIFT", "LSHIFT", "CONTROL", "LCONTROL", "ESC", "ESCAPE", "TAB",
                "LBUTTON", "RBUTTON", "MBUTTON", "UP", "DOWN", "LEFT", "RIGHT"]), StringComparer.Ordinal);
    /// <summary>Serializes proposals, lifecycle stops and input ticks.</summary>
    private readonly object _gate = new();
    /// <summary>Visual readiness and freshness share the input lock so a blocked frame wins over proposals.</summary>
    private readonly AgentWorldReadinessGate _world = new();
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
            var readiness = input.IsAvailable ? _world.Get(now) : _world.Invalidate(now, "window_unavailable");
            if (!readiness.Ready) ClearBlockedInput(now, readiness.Reason);
            return readiness;
        }
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
        }
    }

    /// <summary>Validate an immutable proposal before it can become the current input plan.</summary>
    public string? Submit(AgentRequest request, double now)
    {
        lock (_gate)
        {
            if (_stopped) return "session_stopped";
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
            var authorityTime = frame.SourceFrame?.CapturedAtMs ?? frame.CapturedAtMs;
            if (!double.IsFinite(now) || now < authorityTime || now - authorityTime > 500) return "stale_frame";
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
            if (duration > 250 || now + duration > request.ExpiresAtMs) return "invalid_horizon";
            // Retain through the maximum possible deadline for this frame, not just the supplied deadline.
            _requests.Add(request.RequestId, authorityTime + 750);
            _lastAcceptedFrameId = request.FrameId;
            // A replacement preserves held-state continuity until the next tick, but records the interrupted chunk.
            Finish("replaced", "newer_proposal", now, release: false);
            _active = request with { Steps = request.Steps.Select(s => s with { Keys = s.Keys.ToArray() }).ToArray() };
            _acceptedAt = now;
            _nextStepAt = now;
            _stepIndex = 0;
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
            if (now < _nextStepAt) return;
            if (_stepIndex >= _active.Steps.Length) { Finish("completed", "horizon_complete", now); return; }
            // Never compress several missed transitions into one late frame.
            if (now - _nextStepAt > 50) { Finish("cancelled", "scheduler_late", now); return; }
            var step = _active.Steps[_stepIndex];
            input.SetHeldKeys(step.Keys);
            if (step.MouseDx != 0 || step.MouseDy != 0) input.MoveMouse(step.MouseDx, step.MouseDy);
            _applied.Add(new AgentAppliedStep(_stepIndex, now, step.Keys.ToArray(), step.MouseDx, step.MouseDy));
            _stepIndex++;
            _nextStepAt += step.DurationMs;
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
        try
        {
            if (release && inputEnabled) input.ReleaseAll();
        }
        finally
        {
            if (_active is not null)
            {
                if (_receipts.Count == 256) { _receipts.Dequeue(); _droppedReceipts++; }
                _receipts.Enqueue(new AgentExecutionReceipt(_active.RequestId, _active.ModelId, _active.FrameId,
                    status, reason, _acceptedAt, now, _applied.ToArray()));
            }
            _active = null;
            _applied.Clear();
        }
    }
}
