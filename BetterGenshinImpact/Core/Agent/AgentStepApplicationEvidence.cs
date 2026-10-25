using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>One controller-gated input attempt, observing only actual channel returns; never physical delivery.</summary>
internal sealed class AgentStepApplicationEvidence
{
    /// <summary>Exact QPC sampler; the session owns its origin and frequency separately.</summary>
    private readonly Func<long> _clock;
    /// <summary>Bounded ordered observations; no external event observers run during input.</summary>
    private readonly List<JObject> _calls = [];
    /// <summary>Last successfully sampled QPC tick.</summary>
    private long _last;
    /// <summary>Detached immutable pre-dispatch tracked bookkeeping.</summary>
    private readonly string _before;
    /// <summary>Expected backend instance epoch.</summary>
    private readonly string _backend;
    /// <summary>Actual pre-evaluation time, not caller Tick(now).</summary>
    internal long Started { get; }
    /// <summary>A successful held-state evaluation includes a zero-transition/no-op evaluation.</summary>
    internal long? HeldReturned { get; private set; }

    /// <summary>Create after reserving capacity, under the controller gate and before input calls.</summary>
    internal AgentStepApplicationEvidence(Func<long> clock, JObject before, string backend, long minimum)
    {
        _clock = clock; _last = minimum; _before = AgentStepApplicationWire.Freeze(before, 1024); _backend = backend; Started = Now();
    }

    /// <summary>A failed/regressing clock prohibits positive evidence.</summary>
    internal long Now()
    {
        var value = _clock(); AgentStepApplicationWire.Require(value >= _last, "application_clock_regressed"); _last = value; return value;
    }

    /// <summary>Wrap exactly one real channel invocation. A backend exception remains the primary exception.</summary>
    internal void Call(string operation, string? key, int dx, int dy, Action invoke)
    {
        AgentStepApplicationWire.Require(_calls.Count < 19, "application_call_capacity");
        var start = Now();
        try { invoke(); }
        catch
        {
            try { Add("failed", start, Now()); } catch { /* Failed evidence remains uncertain; preserve the input exception. */ }
            throw;
        }
        Add("returned", start, Now());
        void Add(string stage, long begin, long end) => _calls.Add(new JObject
        {
            ["callId"] = _calls.Count + 1, ["operation"] = operation,
            // A nullable string creates a String token; mouse evidence needs JSON null before serialization.
            ["key"] = key is null ? JValue.CreateNull() : new JValue(key),
            ["mouseDx"] = dx, ["mouseDy"] = dy, ["startedTicks"] = begin, ["finishedTicks"] = end, ["stage"] = stage
        });
    }

    /// <summary>Mark the return of SetHeldKeys even when the desired set was inherited or empty.</summary>
    internal void HeldCompleted() => HeldReturned = Now();

    /// <summary>Construct detached call evidence from actual tracked state; uncertainty cannot become positive authority.</summary>
    internal JObject Finish(JObject after, string backendAfter, bool success)
    {
        var returned = success ? (long?)Now() : null;
        var publication = Now();
        return new JObject
        {
            ["dispatchStartedTicks"] = Started, ["heldReturnedTicks"] = HeldReturned,
            ["callsReturnedTicks"] = returned, ["publicationTicks"] = publication,
            ["trackedBefore"] = AgentStepApplicationWire.Parse(_before, 1024), ["trackedAfter"] = after.DeepClone(),
            ["backendBefore"] = _backend, ["backendAfter"] = backendAfter,
            ["heldEvaluation"] = HeldReturned.HasValue ? "returned" : "failed", ["calls"] = new JArray(_calls.Select(v => v.DeepClone())),
            ["outcome"] = success ? "complete_returned" : "partial_failed", ["evidenceComplete"] = success, ["executionUncertain"] = !success
        };
    }
}

/// <summary>Separate optional instrumentation seam; legacy IAgentInput behavior remains unchanged.</summary>
internal interface IAgentApplicationInput
{
    /// <summary>Stable, exact local backend epoch or an explicit drift marker.</summary>
    string ApplicationBackendEpoch { get; }
    /// <summary>Detached known bookkeeping; it never queries physical key state.</summary>
    JObject ApplicationTrackedState { get; }
    /// <summary>Install one bounded proof only while the existing controller gate is held.</summary>
    void BeginApplication(AgentStepApplicationEvidence proof);
    /// <summary>Remove observation and advance bookkeeping only after complete evaluation.</summary>
    void EndApplication(bool completed, string[] desired);
}
