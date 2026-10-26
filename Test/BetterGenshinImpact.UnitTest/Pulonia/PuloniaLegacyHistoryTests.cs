using System.Security.Cryptography;
using System.Text;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Synthetic legacy documents and owned temporary files only; no executor, model, account or game is loaded.</summary>
public sealed class PuloniaLegacyHistoryTests : IDisposable
{
    /// <summary>Fixed old run identity; its N form is the actual historical filename/effect alias.</summary>
    private const string Run = "87654321-abcd-4321-bcde-0123456789ab";
    /// <summary>Fixed removed request identity, distinct from the run identity.</summary>
    private const string Request = "12345678-abcd-4321-bcde-0123456789ab";
    /// <summary>Stable synthetic historical timestamp, with an explicit offset.</summary>
    private const string Stamp = "2026-10-24T12:34:56+08:00";
    /// <summary>Only this test instance owns this directory.</summary>
    private readonly string _root = Path.Combine(Path.GetTempPath(), "bgi-legacy-history-" + Guid.NewGuid().ToString("N"));

    /// <summary>Old removed facts, snapshots and bytes stay exact and permanently non-executable.</summary>
    [Fact]
    public void CompleteLegacyProjectionPreservesBytesAliasesAndUncertainty()
    {
        var document = Fixture(withIntent: true);
        var bytes = new UTF8Encoding(true).GetPreamble().Concat(Bytes(document)).ToArray();
        var record = PuloniaLegacyHistoryReader.Read(bytes, "plan", Guid.Parse(Run).ToString("N"));
        Assert.Equal(bytes, record.OriginalBytes);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(), record.OriginalSha256);
        Assert.Equal(Run, record.RunIdOriginal);
        Assert.Equal(Guid.Parse(Run).ToString("N"), record.RunId);
        Assert.Equal(Request, record.RequestIdOriginal);
        Assert.Equal(Guid.Parse(Request).ToString("N"), record.RequestId);
        Assert.Equal("account_" + Guid.Parse(Request).ToString("N"), record.Request.Value<string>("world_owner_account_id"));
        Assert.Equal("legacy-server", record.Request.Value<string>("server"));
        Assert.Equal("legacy/world/owner", record.OperationIntent!["reservations"]![0]!.Value<string>("scope_key"));
        Assert.Equal("legacy/account/owner", record.ConfirmedEffects[0]!["entry"]!.Value<string>("scope_key"));
        Assert.Equal(document.Value<string>("snapshot_json"), record.SnapshotJson);
        Assert.Equal(PuloniaTaskRunStatus.Succeeded, record.Status);
        Assert.True(record.HasUnresolvedFacts); // Succeeded cannot settle a retained operation intent.
        Assert.False(record.CanResume);
        Assert.False(record.CanSchedule);
        Assert.Contains("legacy_operation_reservations_retained", record.ResumeBlockReasons);
        Assert.Contains("legacy_effect_scope_semantics_not_migrated", record.ResumeBlockReasons);
        Assert.IsNotType<PuloniaTaskRunRecord>((object)record);
    }

    /// <summary>No returned mutable collection or input array can change retained facts or their hash.</summary>
    [Fact]
    public void ProjectionIsDetachedFromAllCallerMutations()
    {
        var bytes = Bytes(Fixture(withIntent: true));
        var record = PuloniaLegacyHistoryReader.Read(bytes);
        var expected = record.OriginalBytes;
        bytes[0] = 0;
        record.OriginalBytes[1] = 0;
        record.OriginalDocument["run_id"] = "changed";
        record.Request["server"] = "changed";
        record.OperationIntent!["task_address"] = "changed";
        record.ConfirmedEffects.Clear();
        Assert.Equal(expected, record.OriginalBytes);
        Assert.Equal(Run, record.OriginalDocument.Value<string>("run_id"));
        Assert.Equal("legacy-server", record.Request.Value<string>("server"));
        Assert.Equal("root/task", record.OperationIntent.Value<string>("task_address"));
        Assert.Single(record.ConfirmedEffects);
    }

    /// <summary>Old optional absence remains visible rather than being rewritten into purported facts.</summary>
    [Fact]
    public void AbsentOldEffectsAndParentStayAbsent()
    {
        var document = Fixture();
        foreach (var key in new[] { "confirmed_effects", "node_results", "completed_task_addresses", "resumed_from_run_id", "operation_intent" }) document.Remove(key);
        var record = PuloniaLegacyHistoryReader.Read(Bytes(document));
        Assert.False(record.HasConfirmedEffects);
        Assert.Empty(record.ConfirmedEffects);
        Assert.Null(record.ResumedFromRunId);
        Assert.Null(record.OriginalDocument.Property("confirmed_effects"));
        Assert.False(record.HasUnresolvedFacts);
        Assert.Contains("snapshot_execution_not_requalified", record.ResumeBlockReasons);
        Assert.False(record.CanResume);
    }

    /// <summary>Historical statuses are display facts; pending/unknown ones remain explicitly classified.</summary>
    [Theory]
    [InlineData(0, true)]
    [InlineData(1, true)]
    [InlineData(2, true)]
    [InlineData(3, false)]
    [InlineData(4, false)]
    [InlineData(5, false)]
    [InlineData(6, false)]
    [InlineData(7, true)]
    [InlineData(8, true)]
    [InlineData(9, false)]
    public void RecordedStatusNeverGrantsResume(int status, bool unresolved)
    {
        var document = Fixture(); document["status"] = status;
        var record = PuloniaLegacyHistoryReader.Read(Bytes(document));
        Assert.Equal(unresolved, record.HasUnresolvedFacts);
        Assert.False(record.CanResume); Assert.False(record.CanSchedule);
    }

    /// <summary>A terminal outer status cannot hide unverified or partial node results.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(6)]
    public void UnverifiedNodeOutcomeRemainsVisible(int outcome)
    {
        var document = Fixture(); document["node_results"]![0]!["outcome_kind"] = outcome;
        Assert.True(PuloniaLegacyHistoryReader.Read(Bytes(document)).HasUnresolvedFacts);
    }

    /// <summary>Strict old structural fields reject missing/null/coerced/foreign facts without altering their source.</summary>
    [Theory]
    [InlineData("unknown")]
    [InlineData("missing_request")]
    [InlineData("zero_request")]
    [InlineData("non_d_run")]
    [InlineData("bool_status")]
    [InlineData("unknown_status")]
    [InlineData("null_nodes")]
    [InlineData("null_effects")]
    [InlineData("unknown_request")]
    [InlineData("bool_server")]
    [InlineData("invalid_owner")]
    [InlineData("bad_snapshot")]
    [InlineData("snapshot_plan")]
    [InlineData("effect_run")]
    [InlineData("duplicate_effect")]
    [InlineData("intent_run")]
    [InlineData("unknown_reservation")]
    [InlineData("timestamp_without_offset")]
    public void StrictLegacyEnvelopeRejectsContradictions(string kind)
    {
        var document = Fixture(withIntent: true);
        switch (kind)
        {
            case "unknown": document["schema_version"] = 4; break;
            case "missing_request": document.Remove("request_id"); break;
            case "zero_request": document["request_id"] = Guid.Empty.ToString("D"); break;
            case "non_d_run": document["run_id"] = Guid.Parse(Run).ToString("N"); break;
            case "bool_status": document["status"] = true; break;
            case "unknown_status": document["status"] = 99; break;
            case "null_nodes": document["node_results"] = JValue.CreateNull(); break;
            case "null_effects": document["confirmed_effects"] = JValue.CreateNull(); break;
            case "unknown_request": document["request"]!["execution_target"] = new JObject(); break;
            case "bool_server": document["request"]!["server"] = true; break;
            case "invalid_owner": document["request"]!["world_owner_account_id"] = "../outside"; break;
            case "bad_snapshot": document["snapshot_json"] = "{"; break;
            case "snapshot_plan":
                var snapshot = JObject.Parse(document.Value<string>("snapshot_json")!); snapshot["plan_id"] = "other";
                document["snapshot_json"] = snapshot.ToString(); break;
            case "effect_run": document["confirmed_effects"]![0]!["entry"]!["task_run_id"] = Run + ":root/task"; break;
            case "duplicate_effect": ((JArray)document["confirmed_effects"]!).Add(document["confirmed_effects"]![0]!.DeepClone()); break;
            case "intent_run": document["operation_intent"]!["run_id"] = Request; break;
            case "unknown_reservation": document["operation_intent"]!["reservations"]![0]!["resolved"] = true; break;
            case "timestamp_without_offset": document["submitted_at"] = "2026-10-24T12:34:56"; break;
        }
        var bytes = Bytes(document); var exact = (byte[])bytes.Clone();
        Assert.ThrowsAny<JsonException>(() => PuloniaLegacyHistoryReader.Read(bytes));
        Assert.Equal(exact, bytes);
    }

    /// <summary>Duplicate properties are rejected before conversion, including nested request facts.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void DuplicateAndTrailingRootsAreRejected(bool trailing)
    {
        var json = Fixture().ToString(Formatting.None);
        json = trailing ? json + " {}" : json.Replace("\"server\":\"legacy-server\"", "\"server\":\"legacy-server\",\"server\":\"cn\"");
        Assert.ThrowsAny<JsonException>(() => PuloniaLegacyHistoryReader.Read(Encoding.UTF8.GetBytes(json)));
    }

    /// <summary>Old safe long IDs are preserved for read-only display, with no truncation or regeneration.</summary>
    [Theory]
    [InlineData(32)]
    [InlineData(40)]
    [InlineData(96)]
    public void LegacyPlanIdentityRemainsExact(int length)
    {
        var plan = new string('p', length);
        var record = PuloniaLegacyHistoryReader.Read(Bytes(Fixture(planId: plan)), plan, Guid.Parse(Run).ToString("N"));
        Assert.Equal(plan, record.PlanId);
        Assert.False(record.CanResume);
    }

    /// <summary>Both plan directory and run filename are required identity joins, not hints.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void HistoricalPathMismatchIsRejected(bool plan)
        => Assert.ThrowsAny<JsonException>(() => PuloniaLegacyHistoryReader.Read(Bytes(Fixture()),
            plan ? "other" : "plan", plan ? Guid.Parse(Run).ToString("N") : Guid.Parse(Request).ToString("N")));

    /// <summary>Parent aliases retain the exact original GUID and normalized lookup identity independently.</summary>
    [Fact]
    public void ParentRunAliasDoesNotBecomeResumeAuthority()
    {
        var document = Fixture(); document["resumed_from_run_id"] = Request;
        var record = PuloniaLegacyHistoryReader.Read(Bytes(document));
        Assert.Equal(Request, record.ResumedFromRunIdOriginal);
        Assert.Equal(Guid.Parse(Request).ToString("N"), record.ResumedFromRunId);
        Assert.False(record.CanResume);
    }

    /// <summary>Legacy diagnostic text is preserved verbatim and never treated as an ownership identity.</summary>
    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    public void OldDiagnosticTextRemainsVerbatim(string text)
    {
        var doc = Fixture();
        doc["request"]!["source"] = text;
        doc["node_results"]![0]!["message"] = text;
        var record = PuloniaLegacyHistoryReader.Read(Bytes(doc));
        Assert.Equal(text, record.Request.Value<string>("source"));
        Assert.Equal(text, record.OriginalDocument["node_results"]![0]!.Value<string>("message"));
        Assert.False(record.CanResume);
    }

    /// <summary>Mixed current/legacy/corrupt records can be inspected without state access, migration or any write.</summary>
    [Fact]
    public async Task StoreReadOnlyListingPreservesFilesAndSkipsCurrentEnvelopes()
    {
        var file = await WriteHistoryAsync(Fixture());
        var original = await File.ReadAllBytesAsync(file);
        var directory = Path.GetDirectoryName(file)!;
        await File.WriteAllTextAsync(Path.Combine(directory, "run_current.json"), "{\"run_id\":\"run_current\"}");
        var corrupt = Path.Combine(directory, Guid.Parse(Request).ToString("N") + ".json");
        await File.WriteAllTextAsync(corrupt, "{\"request_id\":null}");
        var state = Path.Combine(_root, "state.json"); await File.WriteAllTextAsync(state, "must not be read or rewritten");
        using var store = new PuloniaTaskStore(_root);
        var listed = await store.ListLegacyHistoryWithFailuresAsync();
        var record = Assert.Single(listed.Items); Assert.Single(listed.Failures);
        var loaded = await store.LoadLegacyHistoryRecordAsync("plan", record.RunId);
        Assert.Equal(record.OriginalSha256, loaded!.OriginalSha256);
        Assert.Equal(original, await File.ReadAllBytesAsync(file));
        Assert.Equal("must not be read or rewritten", await File.ReadAllTextAsync(state));
        Assert.False(File.Exists(state + ".bak"));
        Assert.False(record.CanSchedule);
    }

    /// <summary>The old envelope remains rejected by the unchanged executable-history API.</summary>
    [Fact]
    public async Task LegacyRecordCannotEnterCurrentHistoryLoader()
    {
        await WriteHistoryAsync(Fixture());
        using var store = new PuloniaTaskStore(_root);
        await Assert.ThrowsAnyAsync<JsonException>(() => store.LoadHistoryRecordAsync("plan", Guid.Parse(Run).ToString("N")));
        Assert.NotNull(await store.LoadLegacyHistoryRecordAsync("plan", Guid.Parse(Run).ToString("N")));
    }

    /// <summary>Explicit reads refuse invalid path components and leave missing files absent.</summary>
    [Fact]
    public async Task ReadPathValidationAndMissingFileAreNonMutating()
    {
        using var store = new PuloniaTaskStore(_root);
        await Assert.ThrowsAnyAsync<JsonException>(() => store.LoadLegacyHistoryRecordAsync("../outside", Guid.Parse(Run).ToString("N")));
        await Assert.ThrowsAnyAsync<JsonException>(() => store.LoadLegacyHistoryRecordAsync("plan", Run));
        Assert.Null(await store.LoadLegacyHistoryRecordAsync("plan", Guid.Parse(Run).ToString("N")));
        Assert.False(Directory.Exists(_root));
    }

    /// <summary>Oversized source files remain intact and are rejected before allocating their payload.</summary>
    [Fact]
    public async Task FileSizeLimitPreservesOversizedSource()
    {
        var file = await WriteHistoryAsync(Fixture());
        using (var stream = new FileStream(file, FileMode.Open, FileAccess.Write)) stream.SetLength(PuloniaLegacyHistoryReader.MaxRecordBytes + 1L);
        using var store = new PuloniaTaskStore(_root);
        await Assert.ThrowsAnyAsync<JsonException>(() => store.LoadLegacyHistoryRecordAsync("plan", Guid.Parse(Run).ToString("N")));
        Assert.Equal(PuloniaLegacyHistoryReader.MaxRecordBytes + 1L, new FileInfo(file).Length);
    }

    /// <summary>Bounded listing reports the omitted tail rather than silently claiming a complete history census.</summary>
    [Fact]
    public async Task ListingLimitIsExplicitAndPreservesEveryFile()
    {
        var directory = Path.Combine(_root, "history", "plan"); Directory.CreateDirectory(directory);
        for (var i = 0; i <= PuloniaTaskStore.LegacyHistoryListFileLimit; i++)
            await File.WriteAllTextAsync(Path.Combine(directory, $"run_{i}.json"), "{}");
        using var store = new PuloniaTaskStore(_root);
        var listed = await store.ListLegacyHistoryWithFailuresAsync();
        Assert.Empty(listed.Items);
        Assert.Single(listed.Failures);
        Assert.Contains("listing_file_limit", listed.Failures[0].Message);
        Assert.Equal(PuloniaTaskStore.LegacyHistoryListFileLimit + 1, Directory.EnumerateFiles(directory).Count());
    }

    /// <summary>Empty and invalid directories count toward the listing limit without any file or state reads.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DirectoryListingLimitCountsEveryPlanEntry(bool invalid)
    {
        var root = Path.Combine(_root, "history");
        for (var i = 0; i <= PuloniaTaskStore.LegacyHistoryListDirectoryLimit; i++)
            Directory.CreateDirectory(Path.Combine(root, (invalid ? "INVALID_" : "plan_") + i));
        using var store = new PuloniaTaskStore(_root);
        var listed = await store.ListLegacyHistoryWithFailuresAsync();
        Assert.Empty(listed.Items);
        Assert.Single(listed.Failures.Where(failure => failure.Message.Contains("listing_directory_limit", StringComparison.Ordinal)));
        Assert.Equal(invalid ? PuloniaTaskStore.LegacyHistoryListDirectoryLimit + 1 : 1, listed.Failures.Count);
        Assert.Equal(PuloniaTaskStore.LegacyHistoryListDirectoryLimit + 1, Directory.GetDirectories(root).Length);
        Assert.Empty(Directory.GetFiles(root, "*", SearchOption.AllDirectories));
    }

    /// <summary>Write one synthetic old file to the exact historical directory/filename only.</summary>
    private async Task<string> WriteHistoryAsync(JObject document)
    {
        var plan = document["request"]!.Value<string>("plan_id")!;
        var file = Path.Combine(_root, "history", plan, Guid.Parse(document.Value<string>("run_id")!).ToString("N") + ".json");
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        await File.WriteAllBytesAsync(file, Bytes(document));
        return file;
    }

    /// <summary>Serialize only synthetic JSON data, never an executable/current run model.</summary>
    private static byte[] Bytes(JObject document) => Encoding.UTF8.GetBytes(document.ToString(Formatting.Indented) + "\n");

    /// <summary>Construct the exact old record/request/intent/effect field shapes from pinned schema-2 source.</summary>
    private static JObject Fixture(bool withIntent = false, string planId = "plan")
    {
        var policy = new JObject { ["timeout_seconds"] = JValue.CreateNull(), ["failure_behavior"] = JValue.CreateNull(),
            ["max_retries"] = JValue.CreateNull(), ["retry_delay_seconds"] = JValue.CreateNull() };
        var originalTask = new JObject { ["id"] = "root", ["name"] = "Original group", ["task_type"] = "group",
            ["path"] = JValue.CreateNull(), ["resource_version"] = JValue.CreateNull(), ["is_enabled"] = true,
            ["is_expanded"] = true, ["parameters"] = new JObject(), ["children"] = new JArray(),
            ["preset_id"] = JValue.CreateNull(), ["policy"] = policy.DeepClone(), ["source"] = JValue.CreateNull(),
            ["parameter_overrides"] = new JArray() };
        var originalPlan = new JObject { ["id"] = planId, ["schema_version"] = 2, ["revision"] = 7,
            ["name"] = "Synthetic legacy plan", ["description"] = JValue.CreateNull(), ["purpose"] = 0,
            ["root_task"] = originalTask, ["triggers"] = new JArray(), ["accounts"] = new JArray() };
        var prepared = new JObject { ["plan_id"] = planId, ["task_id"] = "root", ["source_task_id"] = "root",
            ["task_address"] = "root", ["name"] = "Original group", ["task_type"] = "group", ["is_enabled"] = true,
            ["path"] = JValue.CreateNull(), ["resource_version"] = JValue.CreateNull(), ["parameters"] = new JObject(),
            ["parameter_sources"] = new JObject(), ["policy"] = policy, ["children"] = new JArray() };
        var snapshot = new JObject { ["plan_id"] = planId, ["revision"] = 7, ["prepared_at"] = Stamp,
            ["account_id"] = "account_" + Guid.Parse(Request).ToString("N"), ["genshin_account_json"] = "{\"image_version\":\"original\"}",
            ["root_task"] = prepared, ["plan_json_by_id"] = new JObject { [planId] = originalPlan.ToString(Formatting.None) },
            ["preset_json_by_id"] = new JObject() };
        var evidence = new JObject { ["kind"] = "executor", ["source"] = "legacy", ["occurred_at"] = Stamp,
            ["data"] = new JObject { ["preserved"] = true } };
        return new JObject
        {
            ["verified_uid"] = "123456789", ["request_id"] = Request, ["run_id"] = Run,
            ["request"] = new JObject { ["plan_id"] = planId, ["account_id"] = "account_" + Guid.Parse(Request).ToString("N"),
                ["world_owner_account_id"] = "account_" + Guid.Parse(Request).ToString("N"), ["server"] = "legacy-server",
                ["server_utc_offset_minutes"] = 480, ["timeout_seconds"] = 90, ["parameter_overrides"] = new JObject(),
                ["source"] = "csharp", ["target_task_id"] = JValue.CreateNull(), ["trigger_id"] = JValue.CreateNull(),
                ["occurrence_utc"] = JValue.CreateNull(), ["deadline_utc"] = JValue.CreateNull(),
                ["trigger_activated_at_utc"] = JValue.CreateNull(), ["busy_policy"] = 0 },
            ["plan_name"] = "Synthetic legacy plan", ["snapshot_json"] = snapshot.ToString(Formatting.None),
            ["status"] = 3, ["current_task_address"] = "root/task", ["message"] = "recorded completion",
            ["submitted_at"] = Stamp, ["started_at"] = Stamp, ["finished_at"] = Stamp,
            ["node_results"] = new JArray(new JObject { ["task_address"] = "root/task", ["task_name"] = "old task",
                ["task_type"] = "legacy.task", ["attempt"] = 1, ["status"] = 1, ["message"] = "recorded",
                ["started_at"] = Stamp, ["finished_at"] = Stamp, ["data"] = new JObject(), ["outcome_kind"] = 0,
                ["evidence"] = new JArray(evidence.DeepClone()), ["reason_code"] = JValue.CreateNull() }),
            ["confirmed_effects"] = new JArray(new JObject { ["task_address"] = "root/task", ["attempt"] = 1,
                ["entry"] = new JObject { ["event_key"] = "original-event", ["scope_key"] = "legacy/account/owner",
                    ["effect_key"] = "original-resource", ["window_key"] = "weekly:old", ["units"] = 2,
                    ["occurred_at"] = Stamp, ["next_eligible_at"] = JValue.CreateNull(),
                    ["task_run_id"] = Guid.Parse(Run).ToString("N") + ":root/task", ["evidence"] = evidence.DeepClone() } }),
            ["completed_task_addresses"] = new JArray("earlier/task"), ["resume_from_task_address"] = JValue.CreateNull(),
            ["resumed_from_run_id"] = JValue.CreateNull(),
            ["operation_intent"] = withIntent ? new JObject { ["run_id"] = Run, ["task_address"] = "root/task",
                ["rule_ids"] = new JArray("original-rule"), ["created_at"] = Stamp,
                ["reservations"] = new JArray(new JObject { ["rule_id"] = "original-rule", ["scope_key"] = "legacy/world/owner", ["effect_key"] = "original-resource" }) }
                : JValue.CreateNull()
        };
    }

    /// <summary>Remove only this test's temporary directory after all read-only handles have closed.</summary>
    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
