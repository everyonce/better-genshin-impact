using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using BetterGenshinImpact.Pulonia.Models;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>
/// Strict reader for the produced schema-2-era run envelope. Historical run files have no schema field:
/// the required request_id GUID and exact old fields select this format. Snapshot execution remains unqualified.
/// </summary>
public static class PuloniaLegacyHistoryReader
{
    /// <summary>Explicit read-only admission ceiling; larger files remain on disk and receive a diagnostic.</summary>
    public const int MaxRecordBytes = 16 * 1024 * 1024;
    /// <summary>Decode only valid UTF-8; a leading UTF-8 BOM is retained in OriginalBytes.</summary>
    private static readonly UTF8Encoding _utf8 = new(false, true);

    /// <summary>Read a legacy record, optionally binding both original history directory and GUID filename.</summary>
    public static PuloniaLegacyHistoryRecord Read(byte[] bytes, string? expectedPlanId = null, string? expectedRunId = null)
    {
        ArgumentNullException.ThrowIfNull(bytes);
        Require(bytes.Length > 0 && bytes.Length <= MaxRecordBytes, "legacy_history_size");
        // Own the input before decoding so caller mutation cannot separate the retained bytes from parsed facts.
        var original = (byte[])bytes.Clone();
        var offset = original.AsSpan().StartsWith(new byte[] { 0xef, 0xbb, 0xbf }) ? 3 : 0;
        var root = Parse(_utf8.GetString(original, offset, original.Length - offset));
        Fields(root,
            "verified_uid request_id run_id request plan_name snapshot_json status current_task_address message submitted_at started_at finished_at node_results confirmed_effects completed_task_addresses resume_from_task_address resumed_from_run_id operation_intent",
            "request_id run_id request plan_name snapshot_json status message submitted_at");
        var requestId = GuidValue(root, "request_id");
        var runId = GuidValue(root, "run_id");
        var resumed = OptionalGuid(root, "resumed_from_run_id");
        var request = Object(root, "request");
        ValidateRequest(request);
        var planId = Text(request, "plan_id");
        ValidateLegacyId(planId);
        if (expectedPlanId is not null) Require(planId == expectedPlanId, "legacy_history_plan_identity");
        if (expectedRunId is not null) Require(runId.ToString("N") == expectedRunId, "legacy_history_filename_identity");
        Text(root, "plan_name");
        Text(root, "message");
        foreach (var key in new[] { "verified_uid", "current_task_address", "resume_from_task_address" }) OptionalText(root, key);
        var status = (PuloniaTaskRunStatus)Integer(root, "status", 0, 9);
        var submitted = Date(root, "submitted_at");
        OptionalDate(root, "started_at");
        OptionalDate(root, "finished_at");
        var snapshot = Text(root, "snapshot_json");
        ValidateSnapshot(snapshot, planId);
        var unresolved = status is PuloniaTaskRunStatus.Queued or PuloniaTaskRunStatus.Running
            or PuloniaTaskRunStatus.Cancelling or PuloniaTaskRunStatus.Interrupted or PuloniaTaskRunStatus.NeedsAttention;
        foreach (var token in OptionalArray(root, "node_results"))
            unresolved |= ValidateNode(AsObject(token, "node_result"));
        foreach (var token in OptionalArray(root, "completed_task_addresses")) StringValue(token, "completed_task_address");
        var effects = OptionalArray(root, "confirmed_effects");
        var eventKeys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var token in effects) ValidateEffect(AsObject(token, "confirmed_effect"), runId, eventKeys);
        if (root["operation_intent"] is { Type: not JTokenType.Null } intent)
        {
            ValidateIntent(AsObject(intent, "operation_intent"), runId);
            unresolved = true;
        }
        var reasons = new List<string> { "legacy_read_only_projection", "snapshot_execution_not_requalified" };
        if (unresolved) reasons.Add("legacy_pending_or_unresolved_outcome");
        if (root["operation_intent"] is JObject) reasons.Add("legacy_operation_reservations_retained");
        if (effects.Count != 0) reasons.Add("legacy_effect_scope_semantics_not_migrated");
        if (root.Property("confirmed_effects") is null) reasons.Add("legacy_confirmation_evidence_absent");
        if (request.Property("server") is not null || request.Property("world_owner_account_id") is not null)
            reasons.Add("legacy_request_ownership_fields_retained");
        if (expectedPlanId is null || expectedRunId is null) reasons.Add("history_path_not_bound");
        return new PuloniaLegacyHistoryRecord(original, root, planId, requestId, runId, resumed,
            status, submitted, unresolved, reasons.ToArray());
    }

    /// <summary>Recognize a candidate legacy envelope without constructing any current model.</summary>
    internal static bool HasLegacyMarker(byte[] bytes)
    {
        Require(bytes.Length > 0 && bytes.Length <= MaxRecordBytes, "legacy_history_size");
        var offset = bytes.AsSpan().StartsWith(new byte[] { 0xef, 0xbb, 0xbf }) ? 3 : 0;
        return Parse(_utf8.GetString(bytes, offset, bytes.Length - offset)).Property("request_id") is not null;
    }

    /// <summary>Retain the exact old safe identifier grammar, without consulting the current mutable validator.</summary>
    internal static void ValidateLegacyId(string id)
    {
        Require(Regex.IsMatch(id, "^[a-z0-9][a-z0-9_-]{0,95}\\z")
            && !Regex.IsMatch(id, "^(con|prn|aux|nul|com[0-9]|lpt[0-9])\\z"), "legacy_history_identifier");
    }

    /// <summary>Parse one object with duplicate-field, depth and trailing-root rejection.</summary>
    private static JObject Parse(string json)
    {
        using var reader = new JsonTextReader(new StringReader(json)) { DateParseHandling = DateParseHandling.None, MaxDepth = 256 };
        var value = JObject.Load(reader, new JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });
        if (reader.Read()) throw new JsonSerializationException("legacy_history_trailing_data");
        return value;
    }

    /// <summary>Validate the exact removed and retained request fields without creating a current request.</summary>
    private static void ValidateRequest(JObject request)
    {
        Fields(request, "plan_id account_id world_owner_account_id server server_utc_offset_minutes timeout_seconds parameter_overrides source target_task_id trigger_id occurrence_utc deadline_utc trigger_activated_at_utc busy_policy", "plan_id");
        ValidateLegacyId(Text(request, "plan_id"));
        foreach (var key in new[] { "account_id", "world_owner_account_id", "target_task_id", "trigger_id" })
            if (OptionalText(request, key) is { } id) ValidateLegacyId(id);
        if (request.Property("server") is not null) Text(request, "server");
        // Source is diagnostic text in the old request, not an ownership identifier.
        if (request.Property("source") is not null) Text(request, "source", allowEmpty: true);
        if (request.Property("server_utc_offset_minutes") is not null) Integer(request, "server_utc_offset_minutes", int.MinValue, int.MaxValue);
        if (request.Property("busy_policy") is not null) Integer(request, "busy_policy", 0, 2);
        if (request["timeout_seconds"] is { Type: not JTokenType.Null } timeout)
        {
            Require(timeout.Type is JTokenType.Float or JTokenType.Integer, "legacy_timeout_type");
            var seconds = timeout.Value<double>();
            Require(double.IsFinite(seconds) && seconds > 0, "legacy_timeout_value");
        }
        if (request.Property("parameter_overrides") is not null)
            foreach (var property in Object(request, "parameter_overrides").Properties()) AsObject(property.Value, "parameter_override");
        foreach (var key in new[] { "occurrence_utc", "deadline_utc", "trigger_activated_at_utc" }) OptionalDate(request, key);
    }

    /// <summary>Bind the outer snapshot identity while leaving original task/account/plan payloads uninterpreted and non-executable.</summary>
    private static void ValidateSnapshot(string json, string planId)
    {
        var snapshot = Parse(json);
        Fields(snapshot, "plan_id revision prepared_at account_id genshin_account_json root_task plan_json_by_id preset_json_by_id",
            "plan_id revision prepared_at root_task plan_json_by_id preset_json_by_id");
        Require(Text(snapshot, "plan_id") == planId, "legacy_snapshot_plan_identity");
        Integer(snapshot, "revision", 0, long.MaxValue);
        Date(snapshot, "prepared_at");
        OptionalText(snapshot, "account_id");
        OptionalText(snapshot, "genshin_account_json");
        Object(snapshot, "root_task");
        foreach (var key in new[] { "plan_json_by_id", "preset_json_by_id" })
            foreach (var property in Object(snapshot, key).Properties())
            {
                ValidateLegacyId(property.Name);
                StringValue(property.Value, key);
            }
        // No prepared task, current account, resource or embedded plan is deserialized for execution.
    }

    /// <summary>Validate recorded attempt metadata and preserve unverified/partial outcome distinctions.</summary>
    private static bool ValidateNode(JObject node)
    {
        Fields(node, "task_address task_name task_type attempt status message started_at finished_at data outcome_kind evidence reason_code",
            "task_address task_name task_type attempt status message started_at finished_at");
        foreach (var key in new[] { "task_address", "task_name", "task_type" }) Text(node, key);
        // Old node constructors retain the caller message verbatim, including an empty message.
        Text(node, "message", allowEmpty: true);
        Integer(node, "attempt", 0, int.MaxValue);
        var status = Integer(node, "status", 0, 5);
        Date(node, "started_at"); Date(node, "finished_at");
        if (node.Property("data") is not null) Object(node, "data");
        OptionalText(node, "reason_code");
        foreach (var evidence in OptionalArray(node, "evidence")) ValidateEvidence(AsObject(evidence, "node_evidence"));
        var outcome = node.Property("outcome_kind") is null ? -1 : Integer(node, "outcome_kind", 0, 6);
        return status == 5 || outcome is 1 or 2 or 6;
    }

    /// <summary>Require exact old GUID-N attempt joins while retaining every original scope and quota fact.</summary>
    private static void ValidateEffect(JObject effect, Guid runId, ISet<string> eventKeys)
    {
        Fields(effect, "task_address attempt entry", "task_address attempt entry");
        var address = Text(effect, "task_address"); Integer(effect, "attempt", 1, int.MaxValue);
        var entry = Object(effect, "entry");
        Fields(entry, "event_key scope_key effect_key window_key units occurred_at next_eligible_at task_run_id evidence",
            "event_key scope_key effect_key window_key occurred_at task_run_id");
        var key = Text(entry, "event_key"); Require(eventKeys.Add(key), "legacy_effect_duplicate_event");
        foreach (var name in new[] { "scope_key", "effect_key", "window_key" }) Text(entry, name);
        Require(Text(entry, "task_run_id") == $"{runId:N}:{address}", "legacy_effect_run_identity");
        if (entry.Property("units") is not null) Integer(entry, "units", 1, int.MaxValue);
        Date(entry, "occurred_at"); OptionalDate(entry, "next_eligible_at");
        if (entry.Property("evidence") is not null) ValidateEvidence(Object(entry, "evidence"));
    }

    /// <summary>Keep arbitrary evidence data inert while validating the stable evidence envelope.</summary>
    private static void ValidateEvidence(JObject evidence)
    {
        Fields(evidence, "kind source occurred_at data", "kind source occurred_at");
        Text(evidence, "kind"); Text(evidence, "source", allowEmpty: true); Date(evidence, "occurred_at");
        if (evidence.Property("data") is not null) Object(evidence, "data");
    }

    /// <summary>Preserve unsettled intent identity and every old rule/scope/effect reservation without releasing it.</summary>
    private static void ValidateIntent(JObject intent, Guid runId)
    {
        Fields(intent, "run_id task_address rule_ids reservations created_at", "run_id task_address created_at");
        Require(GuidValue(intent, "run_id") == runId, "legacy_intent_run_identity");
        Text(intent, "task_address"); Date(intent, "created_at");
        foreach (var rule in OptionalArray(intent, "rule_ids")) StringValue(rule, "intent_rule_id");
        foreach (var token in OptionalArray(intent, "reservations"))
        {
            var reservation = AsObject(token, "reservation");
            Fields(reservation, "rule_id scope_key effect_key", "rule_id scope_key effect_key");
            foreach (var key in new[] { "rule_id", "scope_key", "effect_key" }) Text(reservation, key);
        }
    }

    /// <summary>Reject unknown/missing typed fields; arbitrary user data is allowed only inside documented data bags.</summary>
    private static void Fields(JObject value, string allowed, string required)
    {
        var names = allowed.Split(' ').ToHashSet(StringComparer.Ordinal);
        Require(value.Properties().All(property => names.Contains(property.Name)), "legacy_history_unknown_field");
        Require(required.Split(' ', StringSplitOptions.RemoveEmptyEntries).All(name => value.Property(name) is not null), "legacy_history_missing_field");
    }

    /// <summary>Read a required object without coercion.</summary>
    private static JObject Object(JObject owner, string key) => AsObject(owner[key], key);
    /// <summary>Read an object token without coercion.</summary>
    private static JObject AsObject(JToken? token, string key) => token as JObject ?? throw new JsonSerializationException("legacy_object_" + key);
    /// <summary>Optional old collections may be absent, but explicit null is not absence.</summary>
    private static JArray OptionalArray(JObject owner, string key) => owner.Property(key) is null ? new JArray()
        : owner[key] as JArray ?? throw new JsonSerializationException("legacy_array_" + key);
    /// <summary>Read an exact string token, rejecting booleans/numbers and whitespace-only identities.</summary>
    private static string StringValue(JToken? token, string key, bool allowEmpty = false)
    {
        Require(token?.Type == JTokenType.String, "legacy_string_" + key);
        var value = token!.Value<string>()!;
        Require(allowEmpty || !string.IsNullOrWhiteSpace(value), "legacy_empty_" + key);
        return value;
    }
    /// <summary>Read a required text field.</summary>
    private static string Text(JObject owner, string key, bool allowEmpty = false) => StringValue(owner[key], key, allowEmpty);
    /// <summary>Read an optional nullable text field without losing its original document presence.</summary>
    private static string? OptionalText(JObject owner, string key) => owner[key] is null or { Type: JTokenType.Null }
        ? null : Text(owner, key, allowEmpty: true);
    /// <summary>Read a bounded integer token without accepting floating or string coercion.</summary>
    private static long Integer(JObject owner, string key, long min, long max)
    {
        var token = owner[key];
        Require(token?.Type == JTokenType.Integer, "legacy_integer_" + key);
        Require(long.TryParse(token!.ToString(Formatting.None), NumberStyles.Integer, CultureInfo.InvariantCulture, out var value)
            && value >= min && value <= max, "legacy_integer_range_" + key);
        return value;
    }
    /// <summary>Read a nonempty GUID in the old writer's D form; aliases are derived rather than generated.</summary>
    private static Guid GuidValue(JObject owner, string key)
    {
        Require(Guid.TryParseExact(Text(owner, key), "D", out var value) && value != Guid.Empty, "legacy_guid_" + key);
        return value;
    }
    /// <summary>Read the optional parent GUID without synthesizing an identity.</summary>
    private static Guid? OptionalGuid(JObject owner, string key) => owner[key] is null or { Type: JTokenType.Null } ? null : GuidValue(owner, key);
    /// <summary>Read an ISO timestamp as metadata only; no host clock or scheduling API is consulted.</summary>
    private static DateTimeOffset Date(JObject owner, string key)
    {
        var text = Text(owner, key);
        Require(Regex.IsMatch(text, "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,7})?(?:Z|[+-]\\d{2}:\\d{2})\\z") && DateTimeOffset.TryParse(text,
            CultureInfo.InvariantCulture, DateTimeStyles.None, out _), "legacy_date_" + key);
        return DateTimeOffset.Parse(text, CultureInfo.InvariantCulture, DateTimeStyles.None);
    }
    /// <summary>Validate optional nullable timestamps while retaining their raw representation.</summary>
    private static void OptionalDate(JObject owner, string key)
    {
        if (owner[key] is { Type: not JTokenType.Null }) Date(owner, key);
    }
    /// <summary>Use one explicit diagnostic exception type for malformed legacy data.</summary>
    private static void Require(bool condition, string message)
    {
        if (!condition) throw new JsonSerializationException(message);
    }
}
