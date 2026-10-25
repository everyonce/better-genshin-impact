using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>V2 keeps exact admitted schedules and bounded ACK-independent facts; no model or backend call occurs here.</summary>
internal sealed partial class AgentStepApplicationOutbox
{
    /// <summary>At most 32 immutable admission objects, including their original acceptance and fixed interval.</summary>
    private readonly Dictionary<string, string> _queuedAdmissions = new(StringComparer.Ordinal);
    /// <summary>Small complete summaries survive ACK without retaining every call array a second time.</summary>
    private Dictionary<string, string> _queuedComplete = new(StringComparer.Ordinal);
    /// <summary>Only terminals offered by the bounded batch may be acknowledged.</summary>
    private readonly HashSet<string> _queuedVisibleTerminals = new(StringComparer.Ordinal);
    /// <summary>A normal final release closes submissions without falsifying prior complete application facts.</summary>
    internal bool ClosedForSubmission { get; private set; }
    /// <summary>Version comes only from the exact configured channel, never from a submission.</summary>
    internal bool IsQueuedMode => (long?)AgentStepApplicationWire.Parse(_config, 4096)["version"] == 2;

    /// <summary>Close further submissions while permitting truthful final record retention and draining.</summary>
    internal void CloseQueued() { lock (_gate) ClosedForSubmission = true; }

    /// <summary>Detached admission is transport metadata, not an application receipt.</summary>
    internal JObject? QueuedAdmission(string requestId)
    {
        lock (_gate) return _queuedAdmissions.TryGetValue(requestId, out var raw) ? AgentStepApplicationWire.Parse(raw, 1024) : null;
    }

    /// <summary>Return the exact completed link even when the application retransmission bytes were ACKed.</summary>
    internal JObject CompleteLink(string requestId)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(_queuedComplete.ContainsKey(requestId), "queued_predecessor_incomplete");
            var summary = AgentStepApplicationWire.Parse(_queuedComplete[requestId], 2048);
            var binding = AgentStepApplicationWire.Parse(_bindings[requestId], 3072);
            return new JObject { ["requestId"] = requestId, ["applicationSequence"] = summary["sequence"]!.DeepClone(),
                ["submissionSha256"] = binding["submissionSha256"]!.DeepClone() };
        }
    }

    /// <summary>Validate queue identity and all predictable serialized bounds before admission mutates any state.</summary>
    internal (string Binding, string Admission) CheckQueuedAdmission(JObject bound, string? predecessor, double admittedAt, double start, double end)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(IsQueuedMode && !Lost && !ClosedForSubmission, "queued_closed");
            foreach (var value in new[] { admittedAt, start, end }) AgentStepApplicationWire.Finite(value);
            AgentStepApplicationWire.Require(admittedAt >= 0 && start >= admittedAt && end == start + 50 && end > start, "queued_schedule");
            if (predecessor is null)
                AgentStepApplicationWire.Require(_bindings.Count == 0 && bound["queueAfter"]!.Type == JTokenType.Null && admittedAt == start, "queued_initial");
            else
            {
                AgentStepApplicationWire.Require(admittedAt < start && AgentStepApplicationWire.Same(bound["queueAfter"], CompleteLink(predecessor)), "queued_link_mismatch");
                var prior = AgentStepApplicationWire.Parse(_bindings[predecessor], 3072);
                var oldIdentity = (JObject)prior["identity"]!.DeepClone(); oldIdentity.Remove("frameId");
                var newIdentity = (JObject)bound["identity"]!.DeepClone(); newIdentity.Remove("frameId");
                AgentStepApplicationWire.Require(AgentStepApplicationWire.Same(oldIdentity, newIdentity)
                    && AgentStepApplicationWire.Same(prior["model"], bound["model"]), "queued_identity_drift");
                var schedule = QueuedAdmission(predecessor)!;
                AgentStepApplicationWire.Require(start == (double?)schedule["scheduledEndMs"], "queued_boundary");
                AgentStepApplicationWire.Require(QueuedTerminalReservation(prior, bound) <= 4096, "queued_terminal_budget");
            }
            var config = AgentStepApplicationWire.Parse(_config, 4096);
            AgentStepApplicationWire.Require(ReservationSize(bound, config, AgentStepApplicationWire.Parse(_tracked, 1024), 32) <= 8192,
                "reservation_byte_budget");
            AgentStepApplicationWire.Require(QueuedTerminalReservation(bound, null) <= 4096, "queued_terminal_budget");
            // Freeze the exact complete admission before the controller enters its ownership branch.
            // Retention consumes these same strings; it does not reconstruct a potentially different object.
            var admission = new JObject { ["version"] = 2, ["channelId"] = config["channelId"]!.DeepClone(),
                ["requestId"] = bound["requestId"]!.DeepClone(), ["state"] = bound["queueAfter"]!.Type == JTokenType.Null ? "active" : "queued",
                ["queueAfter"] = bound["queueAfter"]!.DeepClone(), ["admittedAtMs"] = admittedAt, ["scheduledStartMs"] = start, ["scheduledEndMs"] = end };
            return (AgentStepApplicationWire.Freeze(bound, 3072), AgentStepApplicationWire.Freeze(admission, 1024));
        }
    }

    /// <summary>Retain detached binding and schedule only after controller admission has passed every gate.</summary>
    internal void AdmittedQueued(string requestId, (string Binding, string Admission) prepared)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(!_queuedAdmissions.ContainsKey(requestId) && !_bindings.ContainsKey(requestId)
                && _bindings.Count < 32 && !Lost && !ClosedForSubmission, "queued_admission_once");
            _bindings.Add(requestId, prepared.Binding); _queuedAdmissions.Add(requestId, prepared.Admission);
        }
    }

    /// <summary>Preallocate the handoff's bounded application and terminal authority before any successor call.</summary>
    internal AgentStepApplicationEvidence ReserveHandoff(string predecessor, string successor, IAgentApplicationInput input, Func<long> clock)
    {
        lock (_gate)
        {
            AgentStepApplicationWire.Require(!ClosedForSubmission && _terminals.Count < 32 && !_terminalAcks.Contains(predecessor)
                && !_terminals.ContainsKey(predecessor), "queued_terminal_capacity");
            var link = CompleteLink(predecessor);
            var bound = AgentStepApplicationWire.Parse(_bindings[successor], 3072);
            AgentStepApplicationWire.Require(AgentStepApplicationWire.Same(bound["queueAfter"], link)
                && _next == (long)link["applicationSequence"]! + 1, "queued_sequence");
            AgentStepApplicationWire.Require(QueuedTerminalReservation(AgentStepApplicationWire.Parse(_bindings[predecessor], 3072), bound) <= 4096,
                "queued_terminal_budget");
            return Reserve(successor, input, clock);
        }
    }

    /// <summary>Build and validate a detached v2 row using the exact inherited complete-call predicate.</summary>
    private JObject QueuedRecord(string requestId, JObject evidence)
    {
        AgentStepApplicationWire.Require(!Lost && _pending == requestId, "application_ticket");
        var row = (JObject)evidence.DeepClone(); var config = AgentStepApplicationWire.Parse(_config, 4096);
        row["version"] = 2; row["sequence"] = _applications[requestId]; row["channelId"] = config["channelId"]!.DeepClone();
        row["backendEpoch"] = config["backendEpoch"]!.DeepClone(); row["binding"] = AgentStepApplicationWire.Parse(_bindings[requestId], 3072);
        row["clock"] = Clock(config); ValidateEvidence(row, config); return row;
    }

    /// <summary>Small exact generation/clock facts retained for a future queue link and unchanged-key evaluation.</summary>
    private static string QueuedSummary(JObject row) => AgentStepApplicationWire.Freeze(new JObject
    {
        ["sequence"] = row["sequence"]!.DeepClone(), ["trackedAfter"] = row["trackedAfter"]!.DeepClone(),
        ["publicationTicks"] = row["publicationTicks"]!.DeepClone(), ["callsReturnedTicks"] = row["callsReturnedTicks"]!.DeepClone()
    }, 2048);

    /// <summary>Retain an initial or failed successor application without inventing a successful handoff.</summary>
    private void CompleteQueued(string requestId, JObject evidence)
    {
        lock (_gate)
        {
            try
            {
                var row = QueuedRecord(requestId, evidence);
                var raw = AgentStepApplicationWire.Freeze(row, 8192);
                var tracked = AgentStepApplicationWire.Freeze(row["trackedAfter"]!, 1024);
                var complete = (string?)row["outcome"] == "complete_returned";
                var summary = complete ? QueuedSummary(row) : null;
                _records.Add(_applications[requestId], raw);
                if (summary is not null) _queuedComplete.Add(requestId, summary);
                _tracked = tracked; _last = (long)row["publicationTicks"]!; _pending = null;
                if (!complete) Poison();
            }
            catch { Poison(); throw; }
        }
    }

    /// <summary>Publish Q and the linked no-release P terminal atomically after both immutable objects fit and validate.</summary>
    internal void CompleteHandoff(string predecessor, string successor, JObject evidence, double checkedAt, double endedAt, Func<long> clock)
    {
        lock (_gate)
        {
            try
            {
                var row = QueuedRecord(successor, evidence);
                AgentStepApplicationWire.Require((string?)row["outcome"] == "complete_returned", "queued_incomplete");
                var old = AgentStepApplicationWire.Parse(_queuedComplete[predecessor], 2048);
                var priorSchedule = QueuedAdmission(predecessor)!; var nextSchedule = QueuedAdmission(successor)!;
                AgentStepApplicationWire.Require(AgentStepApplicationWire.Same(old["trackedAfter"], row["trackedBefore"])
                    && (long)row["sequence"]! == (long)old["sequence"]! + 1
                    && AgentStepApplicationWire.Same(row["binding"]!["queueAfter"], CompleteLink(predecessor)), "queued_predecessor");
                AgentStepApplicationWire.Finite(checkedAt); AgentStepApplicationWire.Finite(endedAt);
                var boundary = (double)priorSchedule["scheduledEndMs"]!; var end = (double)nextSchedule["scheduledEndMs"]!;
                AgentStepApplicationWire.Require(boundary == (double)nextSchedule["scheduledStartMs"]!
                    && end == boundary + 50 && checkedAt >= boundary && endedAt >= checkedAt && endedAt < end, "queued_completion_deadline");
                var published = clock(); AgentStepApplicationWire.Require(published >= (long)row["publicationTicks"]!, "terminal_clock");
                var transition = new JObject { ["successor"] = new JObject { ["requestId"] = successor,
                        ["applicationSequence"] = row["sequence"]!.DeepClone(), ["submissionSha256"] = row["binding"]!["submissionSha256"]!.DeepClone() },
                    ["boundaryMs"] = boundary, ["successorScheduledEndMs"] = end, ["dispatchCheckedAtMs"] = checkedAt,
                    ["successorCallsReturnedTicks"] = row["callsReturnedTicks"]!.DeepClone() };
                var terminal = QueuedTerminal(predecessor, "completed", "horizon_handoff", endedAt, "not_requested", published, transition);
                var raw = AgentStepApplicationWire.Freeze(row, 8192); var terminalRaw = AgentStepApplicationWire.Freeze(terminal, 4096);
                var tracked = AgentStepApplicationWire.Freeze(row["trackedAfter"]!, 1024); var summary = QueuedSummary(row);
                // Prepare every collection allocation before the visible swap. No observer runs between these assignments.
                var records = new SortedDictionary<long, string>(_records) { { _applications[successor], raw } };
                var terminals = new Dictionary<string, string>(_terminals, StringComparer.Ordinal) { { predecessor, terminalRaw } };
                var summaries = new Dictionary<string, string>(_queuedComplete, StringComparer.Ordinal) { { successor, summary } };
                AgentStepApplicationWire.Require(!_terminalAcks.Contains(predecessor), "terminal_once");
                _records = records; _terminals = terminals; _queuedComplete = summaries;
                _tracked = tracked; _last = published; _pending = null;
            }
            catch { Poison(); throw; }
        }
    }

    /// <summary>Assemble a v2 terminal from retained authority, never from client timing or inferred physical release.</summary>
    private JObject QueuedTerminal(string requestId, string status, string reason, double endedAt, string releaseOutcome, long published, JObject? transition)
    {
        AgentStepApplicationWire.Require(!_terminals.ContainsKey(requestId) && !_terminalAcks.Contains(requestId), "terminal_once");
        var sequence = _applications.GetValueOrDefault(requestId);
        var retained = sequence != 0 && (_records.ContainsKey(sequence) || sequence <= _ack);
        return new JObject { ["version"] = 2, ["channelId"] = AgentStepApplicationWire.Parse(_config, 4096)["channelId"]!.DeepClone(),
            ["binding"] = AgentStepApplicationWire.Parse(_bindings[requestId], 3072), ["applicationSequences"] = retained ? new JArray(sequence) : new JArray(),
            ["status"] = status, ["reason"] = reason, ["publicationTicks"] = published, ["legacyEndedAtMs"] = endedAt,
            ["releaseOutcome"] = releaseOutcome, ["transition"] = transition };
    }

    /// <summary>Record normal closure or cancellation, allowing lost channels to drain without restoring authority.</summary>
    private void TerminalQueued(string requestId, string status, string reason, double endedAt, string releaseOutcome, Func<long> clock)
    {
        lock (_gate)
        {
            ClosedForSubmission = true;
            try
            {
                var now = clock(); AgentStepApplicationWire.Require(now >= _last && double.IsFinite(endedAt), "terminal_clock");
                AgentStepApplicationWire.Text(new JValue(reason), 128);
                AgentStepApplicationWire.Require((status is "completed" or "cancelled") && (releaseOutcome is "returned_unverified" or "unknown"), "queued_terminal_status");
                var terminal = QueuedTerminal(requestId, status, reason, endedAt, releaseOutcome, now, null);
                _terminals.Add(requestId, AgentStepApplicationWire.Freeze(terminal, 4096)); _last = now;
                if (releaseOutcome == "unknown") Poison();
            }
            catch { Poison(); throw; }
        }
    }

    /// <summary>Validate all ACK fields and every terminal dependency before deleting any retained row.</summary>
    private void AcknowledgeQueued(JObject ack)
    {
        lock (_gate)
        {
            var config = AgentStepApplicationWire.Parse(_config, 4096);
            AgentStepApplicationWire.Fields(ack, "version", "channelId", "through", "terminalRequestIds"); AgentStepApplicationWire.Freeze(ack, 4096);
            AgentStepApplicationWire.Require(AgentStepApplicationWire.Integer(ack["version"]) == 2
                && AgentStepApplicationWire.Same(ack["channelId"], config["channelId"]), "ack_channel");
            var through = AgentStepApplicationWire.Integer(ack["through"], _ack, _next - 1);
            AgentStepApplicationWire.Require(ack["terminalRequestIds"] is JArray ids && ids.Count <= 4, "terminal_ack_count");
            var names = ((JArray)ack["terminalRequestIds"]!).Select(v => AgentStepApplicationWire.Text(v)).ToArray();
            AgentStepApplicationWire.Require(names.Distinct().Count() == names.Length, "terminal_ack_duplicate");
            foreach (var name in names)
            {
                if (_terminalAcks.Contains(name)) continue;
                AgentStepApplicationWire.Require(_queuedVisibleTerminals.Contains(name) && _terminals.ContainsKey(name), "terminal_ack_unknown");
                var terminal = AgentStepApplicationWire.Parse(_terminals[name], 4096);
                if (terminal["transition"] is JObject transition)
                    AgentStepApplicationWire.Require((long)transition["successor"]!["applicationSequence"]! <= through, "terminal_ack_dependency");
            }
            for (var n = _ack + 1; n <= through; n++) AgentStepApplicationWire.Require(_records.ContainsKey(n), "ack_gap");
            for (var n = _ack + 1; n <= through; n++) _records.Remove(n);
            _ack = through;
            foreach (var name in names) { _terminals.Remove(name); _terminalAcks.Add(name); }
        }
    }

    /// <summary>A terminal never outruns its own application or a linked successor in the four-row retransmission window.</summary>
    private JObject QueuedExtensions()
    {
        lock (_gate)
        {
            var config = AgentStepApplicationWire.Parse(_config, 4096); var window = _records.Take(4).ToArray();
            var through = window.Length == 0 ? _ack : window[^1].Key;
            var terminals = _terminals.Select(pair => (pair.Key, Row: AgentStepApplicationWire.Parse(pair.Value, 4096)))
                .Where(pair => ((JArray)pair.Row["applicationSequences"]!).All(value => (long)value <= through)
                    && (pair.Row["transition"] is not JObject link || (long)link["successor"]!["applicationSequence"]! <= through)).Take(4).ToArray();
            foreach (var terminal in terminals) _queuedVisibleTerminals.Add(terminal.Key);
            return new JObject { ["stepApplications"] = new JObject { ["version"] = 2, ["channelId"] = config["channelId"]!.DeepClone(),
                ["acknowledgedThrough"] = _ack, ["nextReservedSequence"] = _next, ["authorityLost"] = Lost,
                ["closedForSubmission"] = ClosedForSubmission, ["unpublished"] = _pending is null ? 0 : 1,
                ["records"] = new JArray(window.Select(v => AgentStepApplicationWire.Parse(v.Value, 8192))) },
                ["stepApplicationTerminals"] = new JArray(terminals.Select(v => v.Row)) };
        }
    }

    /// <summary>Constructive conservative terminal witness; elapsed doubles use a longer signed finite representation.</summary>
    internal int QueuedTerminalReservation(JObject bound, JObject? successor)
    {
        var link = successor is null ? null : new JObject { ["successor"] = new JObject { ["requestId"] = successor["requestId"]!.DeepClone(),
                ["applicationSequence"] = 32, ["submissionSha256"] = successor["submissionSha256"]!.DeepClone() },
            ["boundaryMs"] = double.MinValue, ["successorScheduledEndMs"] = double.MinValue,
            ["dispatchCheckedAtMs"] = double.MinValue, ["successorCallsReturnedTicks"] = long.MaxValue };
        return AgentStepApplicationWire.Freeze(new JObject { ["version"] = 2,
            ["channelId"] = AgentStepApplicationWire.Parse(_config, 4096)["channelId"]!.DeepClone(), ["binding"] = bound.DeepClone(),
            ["applicationSequences"] = new JArray(32), ["status"] = "cancelled", ["reason"] = new string('\u0080', 64),
            ["publicationTicks"] = long.MaxValue, ["legacyEndedAtMs"] = double.MinValue,
            ["releaseOutcome"] = "returned_unverified", ["transition"] = link }, 65536).Length;
    }
}
