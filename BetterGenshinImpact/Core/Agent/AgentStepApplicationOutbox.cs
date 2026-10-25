using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Bounded immutable application/terminal publication. Callers serialize control changes using the controller gate.</summary>
internal sealed class AgentStepApplicationOutbox
{
    /// <summary>Only detached outbox state is protected here; no input or transport callback runs under this lock.</summary>
    private readonly object _gate = new();
    /// <summary>Immutable validated lease/configuration bytes.</summary>
    private readonly string _config;
    /// <summary>Application records retransmitted until contiguous ledger ACK.</summary>
    private readonly SortedDictionary<long, string> _records = new();
    /// <summary>Versioned terminal links retransmitted until exact validated terminal ACK.</summary>
    private readonly Dictionary<string, string> _terminals = new(StringComparer.Ordinal);
    /// <summary>Immutable submitted bindings; this channel has at most 32 attempts and cannot recycle.</summary>
    private readonly Dictionary<string, string> _bindings = new(StringComparer.Ordinal);
    /// <summary>Actual application sequence, absent for cancellation before dispatch.</summary>
    private readonly Dictionary<string, long> _applications = new(StringComparer.Ordinal);
    /// <summary>Acknowledged terminal IDs remain bounded anti-replay entries.</summary>
    private readonly HashSet<string> _terminalAcks = new(StringComparer.Ordinal);
    /// <summary>Only the newest dispatch can be reserved and unresolved.</summary>
    private string? _pending;
    /// <summary>Next sequence is assigned before dispatch.</summary>
    private long _next = 1;
    /// <summary>Contiguous ledger ACK; independent of model-history publication.</summary>
    private long _ack;
    /// <summary>Latest immutable complete bookkeeping snapshot.</summary>
    private string _tracked;
    /// <summary>Last publication/dispatch tick within the exact configuration clock.</summary>
    private long _last;
    /// <summary>Any evidence failure permanently prohibits additional authority on this object.</summary>
    internal bool Lost { get; private set; }

    /// <summary>Construct only for an explicitly opted-in idle channel; production negotiation is currently unavailable.</summary>
    internal AgentStepApplicationOutbox(JObject config, JObject initial)
    {
        AgentStepApplicationWire.Configuration(config); Tracked(initial);
        AgentStepApplicationWire.Require(initial["complete"]!.Value<bool>(), "unknown_initial_state");
        _config = AgentStepApplicationWire.Freeze(config, 4096); _tracked = AgentStepApplicationWire.Freeze(initial, 1024);
        _last = config["sessionOriginTicks"]!.Value<long>();
    }

    /// <summary>Exact confirmation object consumed by the unchanged H02 ClientLedger.</summary>
    internal JObject Confirmation() => new()
    {
        ["configuration"] = AgentStepApplicationWire.Parse(_config, 4096), ["initialTracked"] = AgentStepApplicationWire.Parse(_tracked, 1024),
        ["limits"] = new JObject { ["recordBytes"] = 8192, ["retainedRecords"] = 32, ["batchRecords"] = 4, ["channelAttempts"] = 32, ["headerBytes"] = 4194304 }
    };

    /// <summary>Validate and detach the exact submission before the controller mutates its active proposal.</summary>
    internal JObject CheckSubmission(AgentRequest request)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(!Lost && _bindings.Count < 32 && !_bindings.ContainsKey(request.RequestId), "application_channel_unavailable");
            return AgentStepApplicationWire.Binding(request, AgentStepApplicationWire.Parse(_config, 4096));
        }
    }

    /// <summary>Keep the previously validated exact binding when ordinary controller admission succeeds.</summary>
    internal void Admitted(string requestId, JObject binding)
    {
        lock (_gate) _bindings.Add(requestId, AgentStepApplicationWire.Freeze(binding, 3072));
    }

    /// <summary>Reserve the complete 8 KiB slot and worst-case grammar before any input evaluation.</summary>
    internal AgentStepApplicationEvidence Reserve(string requestId, IAgentApplicationInput input, Func<long> clock)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(!Lost && _pending is null && _next <= 32 && _records.Count < 32 && !_applications.ContainsKey(requestId), "application_reservation");
            var before = input.ApplicationTrackedState; Tracked(before);
            AgentStepApplicationWire.Require(before["complete"]!.Value<bool>() && AgentStepApplicationWire.Freeze(before, 1024) == _tracked, "application_predecessor");
            AgentStepApplicationWire.Require(before["generation"]!.Value<long>() < long.MaxValue, "application_generation_exhausted");
            var config = AgentStepApplicationWire.Parse(_config, 4096);
            AgentStepApplicationWire.Require(input.ApplicationBackendEpoch == (string?)config["backendEpoch"], "application_backend");
            var bound = AgentStepApplicationWire.Parse(_bindings[requestId], 3072);
            AgentStepApplicationWire.Require(ReservationSize(bound, config, before, _next) <= 8192, "reservation_byte_budget");
            var proof = new AgentStepApplicationEvidence(clock, before, input.ApplicationBackendEpoch, _last);
            _pending = requestId; _applications.Add(requestId, _next++); return proof;
        }
    }

    /// <summary>Retain actual full or partial evidence once; failed serialization keeps the unresolved reservation.</summary>
    internal void Complete(string requestId, JObject evidence)
    {
        lock (_gate)
        {
            try
            {
                AgentStepApplicationWire.Require(!Lost && _pending == requestId, "application_ticket");
                var row = (JObject)evidence.DeepClone(); var config = AgentStepApplicationWire.Parse(_config, 4096);
                row["version"] = 1; row["sequence"] = _applications[requestId]; row["channelId"] = config["channelId"]!.DeepClone(); row["backendEpoch"] = config["backendEpoch"]!.DeepClone();
                row["binding"] = AgentStepApplicationWire.Parse(_bindings[requestId], 3072); row["clock"] = Clock(config);
                ValidateEvidence(row, config);
                var raw = AgentStepApplicationWire.Freeze(row, 8192); _records.Add(_applications[requestId], raw);
                _tracked = AgentStepApplicationWire.Freeze(row["trackedAfter"]!, 1024); _last = row["publicationTicks"]!.Value<long>(); _pending = null;
                if ((string?)row["outcome"] != "complete_returned") Lost = true;
            }
            catch { Lost = true; throw; }
        }
    }

    /// <summary>Retain uncertainty without retrying input or discarding a reserved slot.</summary>
    internal void Poison() { lock (_gate) Lost = true; }

    /// <summary>Publish a separate exact terminal link after the legacy release attempt, never a physical release claim.</summary>
    internal void Terminal(string requestId, string status, string reason, double endedAt, string releaseOutcome, Func<long> clock)
    {
        lock (_gate)
        {
            try
            {
                AgentStepApplicationWire.Require(!_terminals.ContainsKey(requestId) && !_terminalAcks.Contains(requestId), "terminal_once");
                var now = clock(); AgentStepApplicationWire.Require(now >= _last && double.IsFinite(endedAt), "terminal_clock");
                var config = AgentStepApplicationWire.Parse(_config, 4096);
                // A reserved but unpublished attempt has no authoritative application sequence yet.
                var sequence = _applications.GetValueOrDefault(requestId);
                var hasRecord = sequence != 0 && (_records.ContainsKey(sequence) || sequence <= _ack);
                var terminal = new JObject { ["version"] = 1, ["channelId"] = config["channelId"]!.DeepClone(), ["binding"] = AgentStepApplicationWire.Parse(_bindings[requestId], 3072),
                    ["applicationSequences"] = hasRecord ? new JArray(sequence) : new JArray(), ["status"] = status, ["reason"] = reason,
                    ["publicationTicks"] = now, ["legacyEndedAtMs"] = endedAt, ["releaseOutcome"] = releaseOutcome };
                _terminals.Add(requestId, AgentStepApplicationWire.Freeze(terminal, 4096)); _last = now;
            }
            catch { Lost = true; throw; }
        }
    }

    /// <summary>Validate the whole versioned ACK before changing either retained channel; duplicates are idempotent.</summary>
    internal void Acknowledge(JObject ack)
    {
        lock (_gate)
        {
            var config = AgentStepApplicationWire.Parse(_config, 4096);
            AgentStepApplicationWire.Fields(ack, "version", "channelId", "through", "terminalRequestIds");
            AgentStepApplicationWire.Freeze(ack, 4096);
            AgentStepApplicationWire.Require(AgentStepApplicationWire.Integer(ack["version"]) == 1 && AgentStepApplicationWire.Same(ack["channelId"], config["channelId"]), "ack_channel");
            var through = AgentStepApplicationWire.Integer(ack["through"], _ack, _next - 1);
            AgentStepApplicationWire.Require(ack["terminalRequestIds"] is JArray ids && ids.Count <= 4, "terminal_ack_count");
            var names = ((JArray)ack["terminalRequestIds"]!).Select(v => AgentStepApplicationWire.Text(v)).ToArray();
            AgentStepApplicationWire.Require(names.Distinct().Count() == names.Length && names.All(n => _terminals.ContainsKey(n) || _terminalAcks.Contains(n)), "terminal_ack_unknown");
            for (var n = _ack + 1; n <= through; n++) AgentStepApplicationWire.Require(_records.ContainsKey(n), "ack_gap");
            for (var n = _ack + 1; n <= through; n++) _records.Remove(n);
            _ack = through;
            foreach (var name in names) { _terminals.Remove(name); _terminalAcks.Add(name); }
        }
    }

    /// <summary>Return fresh detached batch views; neither application nor terminal evidence is destructively drained.</summary>
    internal JObject Extensions()
    {
        lock (_gate)
        {
            var config = AgentStepApplicationWire.Parse(_config, 4096);
            return new JObject
            {
                ["stepApplications"] = new JObject { ["version"] = 1, ["channelId"] = config["channelId"]!.DeepClone(), ["acknowledgedThrough"] = _ack,
                    ["nextReservedSequence"] = _next, ["authorityLost"] = Lost, ["unpublished"] = _pending is null ? 0 : 1,
                    ["records"] = new JArray(_records.Take(4).Select(v => AgentStepApplicationWire.Parse(v.Value, 8192))) },
                ["stepApplicationTerminals"] = new JArray(_terminals.Take(4).Select(v => AgentStepApplicationWire.Parse(v.Value, 4096)))
            };
        }
    }

    /// <summary>Exact three-field QPC identity; elapsed milliseconds use the same retained session origin.</summary>
    private static JObject Clock(JObject config) => new(config.Properties().Where(p => p.Name is "clockKind" or "sessionOriginTicks" or "clockFrequency").Select(p => new JProperty(p.Name, p.Value.DeepClone())));

    /// <summary>Validate the software bookkeeping grammar, including uncertainty and monotone generations.</summary>
    private static void Tracked(JObject value)
    {
        AgentStepApplicationWire.Fields(value, "keys", "generation", "complete"); AgentStepApplicationWire.Keys(value["keys"], 12);
        AgentStepApplicationWire.Integer(value["generation"]); AgentStepApplicationWire.Require(value["complete"]?.Type == JTokenType.Boolean, "tracked_complete");
    }

    /// <summary>Recompute full returned-call coverage before serializing positive authority.</summary>
    private void ValidateEvidence(JObject row, JObject config)
    {
        var start = AgentStepApplicationWire.Integer(row["dispatchStartedTicks"], _last);
        var published = AgentStepApplicationWire.Integer(row["publicationTicks"], start);
        var before = (JObject)row["trackedBefore"]!; var after = (JObject)row["trackedAfter"]!; Tracked(before); Tracked(after);
        AgentStepApplicationWire.Require(AgentStepApplicationWire.Freeze(before, 1024) == _tracked, "reservation_state_changed");
        var complete = (string?)row["outcome"] == "complete_returned";
        var calls = (JArray)row["calls"]!; AgentStepApplicationWire.Require(calls.Count <= 19, "call_capacity");
        var previous = start;
        foreach (var call in calls)
        {
            AgentStepApplicationWire.Integer(call["callId"], 1, 19);
            var began = AgentStepApplicationWire.Integer(call["startedTicks"], previous, published);
            previous = AgentStepApplicationWire.Integer(call["finishedTicks"], began, published);
        }
        if (!complete)
        {
            AgentStepApplicationWire.Require(row["callsReturnedTicks"]!.Type == JTokenType.Null && row["evidenceComplete"]!.Value<bool>() == false && row["executionUncertain"]!.Value<bool>(), "uncertain_evidence");
            return;
        }
        var held = AgentStepApplicationWire.Integer(row["heldReturnedTicks"], start, published);
        var returned = AgentStepApplicationWire.Integer(row["callsReturnedTicks"], Math.Max(held, previous), published);
        AgentStepApplicationWire.Require(before["complete"]!.Value<bool>() && after["complete"]!.Value<bool>() && after["generation"]!.Value<long>() == checked(before["generation"]!.Value<long>() + 1)
            && (string?)row["heldEvaluation"] == "returned" && row["evidenceComplete"]!.Value<bool>() && !row["executionUncertain"]!.Value<bool>()
            && AgentStepApplicationWire.Same(row["backendBefore"], config["backendEpoch"]) && AgentStepApplicationWire.Same(row["backendAfter"], config["backendEpoch"]), "incomplete_evidence");
        var desired = (JObject)row["binding"]!["step"]!;
        AgentStepApplicationWire.Require(AgentStepApplicationWire.Same(after["keys"], desired["keys"]), "tracked_desired");
        var oldKeys = AgentStepApplicationWire.Keys(before["keys"], 12); var newKeys = AgentStepApplicationWire.Keys(desired["keys"], 6);
        var expected = oldKeys.Except(newKeys).Select(k => (Down: false, Key: k)).Concat(newKeys.Except(oldKeys).Select(k => (Down: true, Key: k))).ToHashSet();
        var seen = new HashSet<(bool Down, string Key)>(); var mouse = 0; var downSeen = false;
        for (var i = 0; i < calls.Count; i++)
        {
            var call = calls[i]; AgentStepApplicationWire.Require(call["callId"]!.Value<long>() == i + 1 && (string?)call["stage"] == "returned", "call_identity_stage");
            if ((string?)call["operation"] == "mouseMove")
            {
                mouse++; AgentStepApplicationWire.Require(call["key"]!.Type == JTokenType.Null && call["startedTicks"]!.Value<long>() >= held
                    && AgentStepApplicationWire.Same(call["mouseDx"], desired["mouseDx"]) && AgentStepApplicationWire.Same(call["mouseDy"], desired["mouseDy"]), "mouse_coverage");
            }
            else
            {
                var key = AgentStepApplicationWire.Text(call["key"], 16); var op = (string)call["operation"]!; var down = op.EndsWith("Down", StringComparison.Ordinal);
                var expectedOp = (key is "LBUTTON" or "RBUTTON" or "MBUTTON" ? "button" : "key") + (down ? "Down" : "Up");
                AgentStepApplicationWire.Require(mouse == 0 && (down || !downSeen) && op == expectedOp && call["finishedTicks"]!.Value<long>() <= held
                    && call["mouseDx"]!.Value<int>() == 0 && call["mouseDy"]!.Value<int>() == 0 && seen.Add((down, key)), "key_coverage"); downSeen |= down;
            }
        }
        AgentStepApplicationWire.Require(seen.SetEquals(expected) && mouse == ((desired["mouseDx"]!.Value<int>() == 0 && desired["mouseDy"]!.Value<int>() == 0) ? 0 : 1), "complete_call_coverage");
    }

    /// <summary>Port of the reviewed H02 conservative grammar witness; a full slot is retained independently of actual record size.</summary>
    private static int ReservationSize(JObject bound, JObject config, JObject before, long sequence)
    {
        var biggest = AgentActionController.AllowedKeys.OrderByDescending(k => k.Length).ThenBy(k => k, StringComparer.Ordinal).Take(12);
        var call = new JObject { ["callId"] = long.MaxValue, ["operation"] = "buttonDown", ["key"] = "LCONTROL", ["mouseDx"] = -65535, ["mouseDy"] = -65535,
            ["startedTicks"] = long.MaxValue, ["finishedTicks"] = long.MaxValue, ["stage"] = "returned" };
        var row = new JObject { ["version"] = 1, ["sequence"] = sequence, ["channelId"] = config["channelId"]!.DeepClone(), ["backendEpoch"] = config["backendEpoch"]!.DeepClone(),
            ["binding"] = bound.DeepClone(), ["clock"] = Clock(config), ["dispatchStartedTicks"] = long.MaxValue, ["heldReturnedTicks"] = long.MaxValue,
            ["callsReturnedTicks"] = long.MaxValue, ["publicationTicks"] = long.MaxValue, ["trackedBefore"] = before.DeepClone(),
            ["trackedAfter"] = new JObject { ["keys"] = new JArray(biggest), ["generation"] = long.MaxValue, ["complete"] = false },
            ["backendBefore"] = new string('\u0080', 64), ["backendAfter"] = new string('\u0080', 64), ["heldEvaluation"] = "returned",
            ["calls"] = new JArray(Enumerable.Range(0, 19).Select(_ => call.DeepClone())), ["outcome"] = "complete_returned", ["evidenceComplete"] = false, ["executionUncertain"] = false };
        return AgentStepApplicationWire.Freeze(row, 65536).Length;
    }
}
