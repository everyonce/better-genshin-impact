using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Pulonia.Models;

/// <summary>
/// A detached, read-only view of a schema-2-era history document. This is deliberately not a current run record.
/// No API converts it to an executable request, current state, or resumable snapshot.
/// </summary>
public sealed class PuloniaLegacyHistoryRecord
{
    /// <summary>Exact source bytes, including any UTF-8 BOM and original formatting.</summary>
    private readonly byte[] _originalBytes;
    /// <summary>Validated legacy facts; callers only receive deep copies.</summary>
    private readonly JObject _document;

    /// <summary>The legacy envelope format selected by its required request GUID and exact historical grammar.</summary>
    public string Format => "pulonia-run-schema2-era-v1";
    /// <summary>Exact original byte count, independent of the parsed JSON representation.</summary>
    public int OriginalByteCount => _originalBytes.Length;
    /// <summary>SHA-256 of the exact source bytes, not of a reserialized projection.</summary>
    public string OriginalSha256 { get; }
    /// <summary>A defensive byte copy; changing it never changes the retained evidence.</summary>
    public byte[] OriginalBytes => (byte[])_originalBytes.Clone();
    /// <summary>A detached full legacy document, including removed fields and presence/absence distinctions.</summary>
    public JObject OriginalDocument => (JObject)_document.DeepClone();
    /// <summary>The unchanged plan identity from the original request.</summary>
    public string PlanId { get; }
    /// <summary>The original serialized request GUID, retained even though current requests omit it.</summary>
    public string RequestIdOriginal { get; }
    /// <summary>The canonical request GUID alias; no new identity is generated.</summary>
    public string RequestId { get; }
    /// <summary>The original serialized run GUID.</summary>
    public string RunIdOriginal { get; }
    /// <summary>The GUID N-form alias matching the original history filename and effect attempt identities.</summary>
    public string RunId { get; }
    /// <summary>The exact optional original parent run identity.</summary>
    public string? ResumedFromRunIdOriginal { get; }
    /// <summary>The optional parent GUID N-form alias; it never authorizes resumption.</summary>
    public string? ResumedFromRunId { get; }
    /// <summary>Original display name, without reading a current plan.</summary>
    public string PlanName => _document.Value<string>("plan_name")!;
    /// <summary>The historical recorded status, not a new outcome judgment.</summary>
    public PuloniaTaskRunStatus Status { get; }
    /// <summary>Original submission timestamp for ordering read-only results.</summary>
    public DateTimeOffset SubmittedAt { get; }
    /// <summary>Original snapshot string; no model, cache, account or resource is loaded from it.</summary>
    public string SnapshotJson => _document.Value<string>("snapshot_json")!;
    /// <summary>Detached request facts, including original server and world-owner fields when present.</summary>
    public JObject Request => (JObject)_document["request"]!.DeepClone();
    /// <summary>Detached unsettled intent and all rule/scope/effect reservations, without resolution.</summary>
    public JObject? OperationIntent => _document["operation_intent"] is JObject value ? (JObject)value.DeepClone() : null;
    /// <summary>Whether the historical confirmed-effects field was actually present.</summary>
    public bool HasConfirmedEffects => _document.Property("confirmed_effects") is not null;
    /// <summary>Detached confirmed-effect facts, without adapting legacy scope/window semantics.</summary>
    public JArray ConfirmedEffects => _document["confirmed_effects"] is JArray value ? (JArray)value.DeepClone() : new JArray();
    /// <summary>True when recorded fields retain pending or unresolved outcomes; false is not a physical-input claim.</summary>
    public bool HasUnresolvedFacts { get; }
    /// <summary>Every legacy projection is permanently non-resumable through this API.</summary>
    public bool CanResume => false;
    /// <summary>No legacy projection can be admitted to scheduling through this API.</summary>
    public bool CanSchedule => false;
    /// <summary>Explicit preserved reasons that a current execution/resumption has not been qualified.</summary>
    public IReadOnlyList<string> ResumeBlockReasons { get; }

    /// <summary>Freeze validated facts and original bytes without creating a current model.</summary>
    internal PuloniaLegacyHistoryRecord(byte[] originalBytes, JObject document, string planId,
        Guid requestId, Guid runId, Guid? resumedFrom, PuloniaTaskRunStatus status,
        DateTimeOffset submittedAt, bool unresolved, string[] reasons)
    {
        _originalBytes = (byte[])originalBytes.Clone();
        _document = (JObject)document.DeepClone();
        OriginalSha256 = Convert.ToHexString(SHA256.HashData(_originalBytes)).ToLowerInvariant();
        PlanId = planId;
        RequestIdOriginal = document.Value<string>("request_id")!;
        RequestId = requestId.ToString("N");
        RunIdOriginal = document.Value<string>("run_id")!;
        RunId = runId.ToString("N");
        ResumedFromRunIdOriginal = document.Value<string>("resumed_from_run_id");
        ResumedFromRunId = resumedFrom?.ToString("N");
        Status = status;
        SubmittedAt = submittedAt;
        HasUnresolvedFacts = unresolved;
        ResumeBlockReasons = Array.AsReadOnly((string[])reasons.Clone());
    }
}
