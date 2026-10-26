using System;
using System.Diagnostics;
using System.Linq;
using System.Runtime.ExceptionServices;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Default-off v2 scheduling: one active interval and one immutable successor, never renewable holds.</summary>
public sealed partial class AgentActionController
{
    /// <summary>The only admitted successor; not yet an application and never a replacement of active diagnostics.</summary>
    private AgentRequest? _queued;
    /// <summary>Original queue admission time, independent of the fixed successor start.</summary>
    private double _queuedAcceptedAt;
    /// <summary>Immutable consumed source authority for active and queued requests.</summary>
    private double _activeAuthority, _queuedAuthority;
    /// <summary>The chain's original readiness epoch; any interruption prevents further input.</summary>
    private long _queuedReadinessEpoch;
    /// <summary>Only a guarded Q call or its cleanup overrides P's retained active telemetry identity.</summary>
    private AgentRequest? _queuedDispatchOrigin;
    /// <summary>The real QPC sampler is the default; the internal configuration seam accepts an inert fake clock.</summary>
    private Func<long> _queuedClock = Stopwatch.GetTimestamp;
    /// <summary>Bounded raw owners and separate failures survive partial publication until controller retirement.</summary>
    private AgentStepApplicationEvidence? _queuedFailedProof;
    /// <summary>Actual detached evidence survives serialization or paired-publication failure.</summary>
    private JObject? _queuedFailedEvidence;
    /// <summary>At most the active and queued request are retained after a failure; no retry authority.</summary>
    private AgentRequest[] _queuedClosedRequests = [];
    /// <summary>Complete Q calls remain in Q's legacy cancellation receipt if the paired publication fails.</summary>
    private AgentAppliedStep? _queuedAppliedStep;
    /// <summary>A closed channel never retries the same aggregate cleanup after an exception.</summary>
    private bool _queuedCleanupAttempted;
    /// <summary>Primary input/observation failure must not be replaced by cleanup or publication errors.</summary>
    private Exception? _queuedPrimaryFailure, _queuedCleanupFailure, _queuedPublicationFailure;

    /// <summary>Return immutable admission metadata only for the explicitly configured v2 channel.</summary>
    internal JObject? QueuedAdmission(string requestId)
    {
        lock (_gate) return _stepApplications?.IsQueuedMode == true ? _stepApplications.QueuedAdmission(requestId) : null;
    }

    /// <summary>Validate fixed schedule/link/source facts after all unchanged general submission gates.</summary>
    private string? SubmitQueued(AgentRequest request, AgentObservation frame, double authority, double now, out double acceptedAt)
    {
        acceptedAt = now;
        var box = _stepApplications!;
        if (box.Lost || box.ClosedForSubmission) return "queued_closed";
        if (_queued is not null) return "queued_slot_occupied";
        if (!request.HasQueueAfter || request.StartBeforeMs is not { } firstStart) return "queued_fields_required";
        var start = _active is null ? now : _nextStepAt;
        if (request.Steps.Length != 1 || request.Steps[0].DurationMs != 50 || firstStart > authority + 100
            || request.ExpiresAtMs > authority + 150 || start >= firstStart || start + 50 > request.ExpiresAtMs
            || start + 50 <= start) return "queued_native_deadline";
        if (_active is not null && (_stepIndex != 1 || now >= start || start >= _active.ExpiresAtMs)) return "queued_predecessor_not_ready";
        JObject binding;
        (string Binding, string Admission) prepared;
        try
        {
            binding = box.CheckSubmission(request);
            var identity = binding["identity"]!;
            var sourceEpoch = frame.HostSnapshot?.CaptureEpoch ?? frame.SourceFrame?.CaptureEpoch;
            var readiness = _world.Get(now);
            AgentStepApplicationWire.Require(sourceEpoch is not null && (string?)identity["sourceEpoch"] == sourceEpoch
                && (long?)identity["readinessEpoch"] == readiness.Epoch && readiness.Ready, "queued_source_readiness");
            prepared = box.CheckQueuedAdmission(binding, _active?.RequestId, now, start, start + 50);
        }
        catch (Exception) { return "invalid_queued_application_binding"; }
        // All scalar/grammar/capacity checks precede ownership changes. Every nested mutable operand is detached.
        var detached = request with { Steps = request.Steps.Select(s => s with { Keys = s.Keys.ToArray() }).ToArray(),
            StepApplication = (JObject)request.StepApplication!.DeepClone(),
            QueueAfter = (JObject?)request.QueueAfter?.DeepClone(),
            RawApplicationRequest = (JObject)request.RawApplicationRequest!.DeepClone() };
        try
        {
            box.AdmittedQueued(request.RequestId, prepared);
            _requests.Add(request.RequestId, authority + 750); _lastAcceptedFrameId = request.FrameId;
            if (_active is null)
            {
                _active = detached; _acceptedAt = now; _nextStepAt = start; _activeAuthority = authority;
                _queuedReadinessEpoch = (long)binding["identity"]!["readinessEpoch"]!;
                _stepIndex = 0; _lastAttemptedStepIndex = null; _lastDispatchOutcome = "not_started";
            }
            else { _queued = detached; _queuedAcceptedAt = now; _queuedAuthority = authority; }
        }
        catch (Exception error)
        {
            _queuedPrimaryFailure ??= error; box.Poison(); throw;
        }
        return null;
    }

    /// <summary>Validate the immutable source and still-unconsumed first-start deadline immediately before calls.</summary>
    private string? QueuedStartCheck(AgentRequest request, double authority, double boundary, double now, bool successor)
    {
        if (_stepApplications!.Lost || _stepApplications.ClosedForSubmission) return "queued_closed";
        if (!_world.Get(now).Ready || _world.Get(now).Epoch != _queuedReadinessEpoch) return "world_not_ready";
        if (now < authority || request.StartBeforeMs is not { } first || now >= first
            || first > authority + 100 || request.ExpiresAtMs > authority + 150) return "start_deadline_expired";
        if (now >= request.ExpiresAtMs || now >= boundary + 50 || boundary + 50 > request.ExpiresAtMs) return "deadline_expired";
        // P's already-consumed startBefore is deliberately not part of a successor boundary check.
        if (successor && now >= _active!.ExpiresAtMs) return "predecessor_deadline_expired";
        if (now - boundary > 50) return "scheduler_late";
        return null;
    }

    /// <summary>One due action only. No timer wait, input retry, late queue admission, or B-to-now schedule reset.</summary>
    private void TickQueued(double now)
    {
        if (!GetWorldReadiness(now).Ready || _active is null) return;
        var box = _stepApplications!;
        if (box.Lost || box.ClosedForSubmission) { FinishQueued("cancelled", "queued_closed", now); return; }
        if (now >= _active.ExpiresAtMs) { FinishQueued("cancelled", "deadline_expired", now); return; }
        if (now < _nextStepAt) return;
        var successor = _stepIndex == 1;
        if (successor && _queued is null) { FinishQueued("completed", "horizon_complete", now); return; }
        var target = successor ? _queued! : _active;
        var authority = successor ? _queuedAuthority : _activeAuthority;
        var boundary = _nextStepAt;
        var admitted = successor ? _queuedAcceptedAt : _acceptedAt;
        var actual = (IAgentApplicationInput)input;
        AgentStepApplicationEvidence? proof = null;
        JObject? evidence = null;
        var began = false; var ended = false; var retained = false;
        var priorOrigin = _inputOrigin; var priorRequest = _queuedDispatchOrigin;
        try
        {
            // Window/backend checks may take time; the final elapsed clock is sampled after reservation as well.
            if (!input.IsAvailable) { FinishQueued("cancelled", "window_unavailable", now); return; }
            if (!TryReadStartClock(Math.Max(now, admitted), out now)) { FinishQueued("cancelled", "invalid_start_clock", admitted); return; }
            var reason = QueuedStartCheck(target, authority, boundary, now, successor);
            if (reason is not null) { FinishQueued("cancelled", reason, now); return; }
            proof = successor ? box.ReserveHandoff(_active.RequestId, target.RequestId, actual, _queuedClock)
                              : box.Reserve(target.RequestId, actual, _queuedClock);
            if (!input.IsAvailable) { box.Poison(); FinishQueued("cancelled", "window_unavailable", now); return; }
            if (!TryReadStartClock(now, out var finalStart)) { box.Poison(); FinishQueued("cancelled", "invalid_start_clock", now); return; }
            now = finalStart; reason = QueuedStartCheck(target, authority, boundary, now, successor);
            if (reason is not null) { box.Poison(); FinishQueued("cancelled", reason, now); return; }
            // P stays active until the pair is retained, but every Q backend call carries Q's actual identity.
            _queuedDispatchOrigin = target; _lastAttemptedStepIndex = 0; _inputOrigin = "dispatch"; _lastDispatchOutcome = "started";
            var step = target.Steps[0];
            actual.BeginApplication(proof); began = true;
            input.SetHeldKeys(step.Keys); proof.HeldCompleted();
            if (step.MouseDx != 0 || step.MouseDy != 0) input.MoveMouse(step.MouseDx, step.MouseDy);
            actual.EndApplication(true, step.Keys); ended = true;
            var appliedStep = new AgentAppliedStep(0, now, step.Keys.ToArray(), step.MouseDx, step.MouseDy);
            if (successor) _queuedAppliedStep = appliedStep; else _applied.Add(appliedStep);
            evidence = proof.Finish(actual.ApplicationTrackedState, actual.ApplicationBackendEpoch, true);
            var availableAfter = input.IsAvailable;
            if (!TryReadStartClock(now, out var completedAt)) throw new InvalidOperationException("queued_completion_clock");
            var expired = completedAt >= boundary + 50 || completedAt >= target.ExpiresAtMs
                || (successor && completedAt >= _active.ExpiresAtMs)
                || !availableAfter || !_world.Get(completedAt).Ready || _world.Get(completedAt).Epoch != _queuedReadinessEpoch;
            if (expired)
            {
                // Software calls did return; preserve that fact, but never call the late transition successful.
                box.Complete(target.RequestId, evidence); retained = true;
                box.Poison(); FinishQueued("cancelled", "queued_completion_expired", completedAt); return;
            }
            if (successor)
            {
                box.CompleteHandoff(_active.RequestId, target.RequestId, evidence, now, completedAt, _queuedClock); retained = true;
                EnqueueQueuedReceipt(_active, "completed", "horizon_handoff", _acceptedAt, completedAt, _applied.ToArray());
                _active = target; _acceptedAt = admitted; _activeAuthority = authority; _queued = null; _applied.Clear();
                _applied.Add(appliedStep); _queuedAppliedStep = null;
            }
            else { box.Complete(target.RequestId, evidence); retained = true; }
            _stepIndex = 1; _nextStepAt = boundary + 50; _lastDispatchOutcome = "returned";
        }
        catch (Exception error)
        {
            _queuedPrimaryFailure ??= error; _queuedFailedProof = proof; _queuedFailedEvidence = evidence;
            _lastDispatchOutcome = "failed";
            // Never repeat a successful EndApplication or input call after a publication failure.
            try
            {
                if (began && !ended) actual.EndApplication(false, target.Steps[0].Keys);
                if (proof is not null && !retained && !box.Lost)
                {
                    evidence ??= proof.Finish(actual.ApplicationTrackedState, actual.ApplicationBackendEpoch, false);
                    _queuedFailedEvidence = evidence; box.Complete(target.RequestId, evidence);
                }
            }
            catch (Exception publication) { _queuedPublicationFailure ??= publication; }
            box.Poison(); FinishQueued("cancelled", "queued_dispatch_failed", now, error);
            throw;
        }
        finally
        {
            // Reserved failures remain owned even when no backend call began.
            if (box.Lost && proof is not null) { _queuedFailedProof ??= proof; _queuedFailedEvidence ??= evidence; }
            _queuedDispatchOrigin = priorRequest; _inputOrigin = priorOrigin;
        }
    }

    /// <summary>Same bounded legacy recorder, with an explicit no-release reason only after a retained Q/P pair.</summary>
    private void EnqueueQueuedReceipt(AgentRequest request, string status, string reason, double admitted, double ended, AgentAppliedStep[] applied)
    {
        if (_receipts.Count == 256) { _receipts.Dequeue(); _droppedReceipts++; }
        _receipts.Enqueue(new AgentExecutionReceipt(request.RequestId, request.ModelId, request.FrameId, status, reason, admitted, ended, applied));
    }

    /// <summary>One aggregate release covers P and an admitted Q; failures never restore known tracking or mask primary errors.</summary>
    private void FinishQueued(string status, string reason, double now, Exception? primary = null)
    {
        var box = _stepApplications!; box.CloseQueued();
        if (_queuedCleanupAttempted) return;
        _queuedCleanupAttempted = true;
        // A queued dispatch can finish while stop waits for _gate; timestamp the terminal operation here.
        // Clock failure must never prevent the already-required input release.
        if (monotonicClock is not null && TryReadStartClock(now, out var terminalAt)) now = terminalAt;
        var active = _active; var queued = _queued;
        _queuedClosedRequests = new[] { active, queued }.Where(v => v is not null).Cast<AgentRequest>().ToArray();
        var priorOrigin = _inputOrigin; _inputOrigin = "release:" + reason;
        var releaseOutcome = "unknown"; Exception? cleanup = null;
        try { if (inputEnabled) { input.ReleaseAll(); releaseOutcome = "returned_unverified"; } }
        catch (Exception error) { cleanup = error; _queuedCleanupFailure ??= error; box.Poison(); }
        finally
        {
            // P has its actual applied steps; a never-dispatched Q remains explicitly empty.
            foreach (var request in _queuedClosedRequests)
            {
                var isActive = ReferenceEquals(request, active);
                var requestStatus = isActive ? status : "cancelled";
                try { box.Terminal(request.RequestId, requestStatus, reason, now, releaseOutcome, _queuedClock); }
                catch (Exception error) { _queuedPublicationFailure ??= error; box.Poison(); }
                EnqueueQueuedReceipt(request, requestStatus, reason, isActive ? _acceptedAt : _queuedAcceptedAt, now,
                    isActive ? _applied.ToArray() : _queuedAppliedStep is { } applied ? [applied] : []);
            }
            _active = null; _queued = null; _applied.Clear(); _stepIndex = 0;
            _lastAttemptedStepIndex = null; _inputOrigin = priorOrigin;
            _lastDispatchOutcome = box.Lost ? "failed" : "not_started";
        }
        if (cleanup is not null && primary is null) ExceptionDispatchInfo.Capture(cleanup).Throw();
    }
}
