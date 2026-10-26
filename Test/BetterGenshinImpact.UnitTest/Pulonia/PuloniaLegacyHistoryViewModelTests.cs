using System.Security.Cryptography;
using System.Text;
using BetterGenshinImpact.Pulonia.Executors;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.ViewModel.Pages;
using Microsoft.Extensions.Logging.Abstractions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Synthetic temporary-file browser tests; no application, account, game, or native image service is created.</summary>
public sealed class PuloniaLegacyHistoryViewModelTests : IDisposable
{
    /// <summary>Every test owns only this fresh temporary filesystem root.</summary>
    private readonly string _root = Path.Combine(Path.GetTempPath(), "bgi-legacy-history-view-" + Guid.NewGuid().ToString("N"));
    /// <summary>Original dashed run ID reused from the strict legacy reader fixture.</summary>
    private const string Run = "87654321-abcd-4321-bcde-0123456789ab";
    /// <summary>Original dashed request ID reused from the strict legacy reader fixture.</summary>
    private const string Request = "12345678-abcd-4321-bcde-0123456789ab";
    /// <summary>Fixed historical timestamp, unrelated to the current machine or game.</summary>
    private const string Stamp = "2026-10-24T12:34:56+08:00";

    /// <summary>Constructing the browser must not inspect or create a persistence directory.</summary>
    [Fact]
    public void ConstructionDoesNotReadOrCreateStorage()
    {
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        Assert.False(Directory.Exists(_root));
        Assert.Empty(vm.Records);
        Assert.Empty(vm.Failures);
        Assert.False(vm.HasSelectedRecord);
        Assert.False(vm.IsRefreshing);
    }

    /// <summary>Selection retains both original identity forms, bytes/hash, and unresolved facts without current-run conversion.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SelectionPreservesOriginalEvidence(bool withIntent)
    {
        var path = await WriteHistory(Fixture(withIntent));
        var original = await File.ReadAllBytesAsync(path);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        var row = Assert.Single(vm.Records);
        Assert.Equal(withIntent, row.HasUnresolvedFacts);
        vm.SelectedRecord = row;
        Assert.True(vm.HasSelectedRecord);
        Assert.Equal(Request, row.Record.RequestIdOriginal);
        Assert.Equal(Guid.Parse(Request).ToString("N"), row.Record.RequestId);
        Assert.Equal(Run, row.Record.RunIdOriginal);
        Assert.Equal(Guid.Parse(Run).ToString("N"), row.RunLabel);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(original)).ToLowerInvariant(), row.Record.OriginalSha256);
        Assert.Equal(original, row.Record.OriginalBytes);
        Assert.False(row.Record.CanResume);
        Assert.False(row.Record.CanSchedule);
        Assert.Contains(vm.OverviewFields, f => f.Label == "原始字节 SHA-256" && f.Value == row.Record.OriginalSha256);
        Assert.Equal(original, await File.ReadAllBytesAsync(path));
        AssertPreviewBounded(vm);
    }

    /// <summary>Display must not normalize absent, explicit null, and empty-array facts into one value.</summary>
    [Fact]
    public async Task MissingNullAndEmptyFactsRemainDistinct()
    {
        var data = Fixture();
        data.Remove("resumed_from_run_id");
        data["operation_intent"] = JValue.CreateNull();
        data["confirmed_effects"] = new JArray();
        await WriteHistory(data);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        vm.SelectedRecord = Assert.Single(vm.Records);
        Assert.Equal("[absent]", vm.FactFields.Single(f => f.Label == "原始父运行标识").Value);
        Assert.Equal("null", vm.FactFields.Single(f => f.Label == "未解决操作意图").Value);
        Assert.Equal("[]", vm.FactFields.Single(f => f.Label == "原始确认效果").Value);
        Assert.False(vm.IsPreviewTruncated);
        AssertPreviewBounded(vm);
    }

    /// <summary>A large opaque snapshot and title produce only bounded preview strings while their original bytes remain exact.</summary>
    [Fact]
    public async Task LargeOpaqueSnapshotAndListLabelAreBounded()
    {
        var data = Fixture();
        data["plan_name"] = new string('界', 100_000);
        var snapshot = JObject.Parse(data.Value<string>("snapshot_json")!);
        snapshot["root_task"]!["parameters"]!["opaque"] = new string('界', 1_000_000) + "END_SENTINEL";
        data["snapshot_json"] = snapshot.ToString(Formatting.None);
        var path = await WriteHistory(data);
        var original = await File.ReadAllBytesAsync(path);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        var row = Assert.Single(vm.Records);
        vm.SelectedRecord = row;
        Assert.Equal(PuloniaLegacyHistoryViewModel.ListLabelLimit, row.PlanLabel.Length);
        Assert.EndsWith("…", row.PlanLabel);
        Assert.True(vm.IsPreviewTruncated);
        var preview = vm.FactFields.Single(f => f.Label == "原始快照文本（不执行）").Value;
        Assert.NotEmpty(preview);
        Assert.DoesNotContain("END_SENTINEL", preview);
        Assert.Contains("END_SENTINEL", row.Record.SnapshotJson);
        Assert.Equal(original, row.Record.OriginalBytes);
        Assert.Equal(original, await File.ReadAllBytesAsync(path));
        AssertPreviewBounded(vm);
    }

    /// <summary>Large escaped/non-ASCII fact text is bounded at JSON writing, including all overview and fact labels.</summary>
    [Fact]
    public async Task LargeFactJsonSharesTheSamePreviewBudget()
    {
        var data = Fixture();
        data["request"]!["parameter_overrides"]!["large"] = new JObject { ["text"] = string.Concat(Enumerable.Repeat("界\"\n", 100_000)) + "END_SENTINEL" };
        await WriteHistory(data);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        vm.SelectedRecord = Assert.Single(vm.Records);
        Assert.True(vm.IsPreviewTruncated);
        Assert.DoesNotContain(vm.FactFields, f => f.Value.Contains("END_SENTINEL", StringComparison.Ordinal));
        AssertPreviewBounded(vm);
    }

    /// <summary>Exact-ID mode replaces the bounded list, while Refresh restores the list and preserves an existing selection.</summary>
    [Fact]
    public async Task ExactReadReplacesListAndRefreshRestoresIt()
    {
        await WriteHistory(Fixture(planId: "first"), "first");
        await WriteHistory(Fixture(planId: "second"), "second");
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        Assert.Equal(2, vm.RecordCount);
        vm.ExactPlanId = "second";
        vm.ExactRunId = Guid.Parse(Run).ToString("N");
        await vm.LoadExactAsync();
        Assert.Equal("second", Assert.Single(vm.Records).Record.PlanId);
        Assert.Same(vm.Records[0], vm.SelectedRecord);
        Assert.Equal("按标识读取的单条旧版记录", vm.ModeMessage);
        await vm.RefreshAsync();
        Assert.Equal(2, vm.RecordCount);
        Assert.Equal("second", vm.SelectedRecord!.Record.PlanId);
        Assert.Equal("有界旧版记录列表", vm.ModeMessage);
    }

    /// <summary>A missing or invalid exact identity clears prior rows/details and reports failure without normalization or creation.</summary>
    [Theory]
    [InlineData("missing", "87654321abcd4321bcde0123456789ab", false)]
    [InlineData("../escape", "87654321abcd4321bcde0123456789ab", true)]
    [InlineData("plan", "not-a-guid", true)]
    public async Task MissingOrInvalidExactReadCannotLeaveStaleSelection(string plan, string run, bool failed)
    {
        var path = await WriteHistory(Fixture());
        var before = await File.ReadAllBytesAsync(path);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        vm.SelectedRecord = Assert.Single(vm.Records);
        vm.ExactPlanId = plan;
        vm.ExactRunId = run;
        await vm.LoadExactAsync();
        Assert.Empty(vm.Records);
        Assert.Null(vm.SelectedRecord);
        Assert.Empty(vm.OverviewFields);
        Assert.Empty(vm.FactFields);
        Assert.Equal(failed ? 1 : 0, vm.FailureCount);
        Assert.False(vm.IsRefreshing);
        Assert.Equal(before, await File.ReadAllBytesAsync(path));
        Assert.False(Directory.Exists(Path.Combine(_root, "history", "missing")));
    }

    /// <summary>Corrupt records remain untouched and visible as diagnostics alongside readable evidence.</summary>
    [Fact]
    public async Task CorruptFileIsReportedWithoutRepairingOrHidingGoodRows()
    {
        var good = await WriteHistory(Fixture());
        var bad = Path.Combine(_root, "history", "plan", "ffffffffffffffffffffffffffffffff.json");
        var corrupt = Encoding.UTF8.GetBytes("{\"request_id\":");
        await File.WriteAllBytesAsync(bad, corrupt);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        Assert.Single(vm.Records);
        Assert.NotEmpty(vm.Failures);
        Assert.All(vm.Failures, f => { Assert.InRange(f.Label.Length, 0, 96); Assert.InRange(f.Value.Length, 0, 1024); });
        Assert.Equal(corrupt, await File.ReadAllBytesAsync(bad));
        Assert.True(File.Exists(good));
        Assert.False(File.Exists(bad + ".bak"));
    }

    /// <summary>The bounded directory-list diagnostic is visible, but a valid exact-ID read remains available.</summary>
    [Fact]
    public async Task DirectoryLimitIsVisibleAndDoesNotDisableExactRead()
    {
        for (var index = 0; index < 129; index++) Directory.CreateDirectory(Path.Combine(_root, "history", "p" + index));
        var path = await WriteHistory(Fixture(planId: "outside"), "outside");
        var before = await File.ReadAllBytesAsync(path);
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        Assert.Contains(vm.Failures, f => f.Value.Contains("directory", StringComparison.OrdinalIgnoreCase));
        Assert.InRange(vm.FailureCount, 1, 129);
        vm.ExactPlanId = "outside";
        vm.ExactRunId = Guid.Parse(Run).ToString("N");
        await vm.LoadExactAsync();
        Assert.Equal("outside", Assert.Single(vm.Records).Record.PlanId);
        Assert.Empty(vm.Failures);
        Assert.Equal(before, await File.ReadAllBytesAsync(path));
    }

    /// <summary>Refreshing after a synthetic source is removed cannot retain its stale selected preview.</summary>
    [Fact]
    public async Task RefreshDropsMissingSelectionAndItsPreview()
    {
        var path = await WriteHistory(Fixture());
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        vm.SelectedRecord = Assert.Single(vm.Records);
        File.Delete(path); // The fixture owns this file; the browser never deletes it.
        await vm.RefreshAsync();
        Assert.Empty(vm.Records);
        Assert.Null(vm.SelectedRecord);
        Assert.Empty(vm.OverviewFields);
        Assert.Empty(vm.FactFields);
        Assert.Equal(0, vm.PreviewUtf8ByteCount);
    }

    /// <summary>Cancellation before acquiring the read gate leaves existing evidence intact and does not poison the next read.</summary>
    [Fact]
    public async Task CanceledReadDoesNotClearEvidenceOrPoisonTheGate()
    {
        await WriteHistory(Fixture());
        using var store = new PuloniaTaskStore(_root);
        var vm = new PuloniaLegacyHistoryViewModel(store);
        await vm.RefreshAsync();
        var row = Assert.Single(vm.Records);
        vm.SelectedRecord = row;
        using var canceled = new CancellationTokenSource();
        canceled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => vm.RefreshAsync(canceled.Token));
        Assert.Same(row, vm.SelectedRecord);
        Assert.False(vm.IsRefreshing);
        await vm.RefreshAsync();
        Assert.Single(vm.Records);
    }

    /// <summary>The real populated-state startup hold stays active while this independent browser reads old evidence.</summary>
    [Fact]
    public async Task LegacyHistoryIsReadableWithoutLiftingPopulatedStateHold()
    {
        var historyPath = await WriteHistory(Fixture(withIntent: true));
        var historyBytes = await File.ReadAllBytesAsync(historyPath);
        var statePath = Path.Combine(_root, "state.json");
        var oldState = JObject.Parse(PuloniaTaskJson.WriteState(new PuloniaTaskState { Sequence = 37 }));
        oldState["schema_version"] = 2;
        oldState["uncertain_operations"] = new JArray(new JObject { ["operation_id"] = "unknown-outcome" });
        var stateBytes = Encoding.UTF8.GetBytes(oldState.ToString());
        await File.WriteAllBytesAsync(statePath, stateBytes);
        using var store = new PuloniaTaskStore(_root);
        // This is the existing synthetic hold fixture: no definitions can run, and no game runtime is supplied.
        await using (var service = new PuloniaTaskService(store, new PuloniaTaskBuilder(store),
            [new PuloniaCSharpTaskExecutor(new PuloniaCSharpTaskRegistry())],
            new PuloniaGameTaskCoordinator(null!), new TaskStopService(NullLogger<TaskStopService>.Instance)))
        {
            Assert.Empty(await service.ListRunsAsync().WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.Contains("compatibility hold", service.RecoveryNotice);
            var vm = new PuloniaLegacyHistoryViewModel(store);
            await vm.RefreshAsync();
            vm.SelectedRecord = Assert.Single(vm.Records);
            Assert.True(vm.SelectedRecord.HasUnresolvedFacts);
            Assert.False(vm.SelectedRecord.Record.CanResume);
            await Assert.ThrowsAsync<InvalidOperationException>(() => service.EnqueueAsync(new PuloniaTaskRequest { PlanId = "plan" }));
            await Assert.ThrowsAsync<InvalidOperationException>(() => service.CheckTriggersAsync([]));
            Assert.Contains("compatibility hold", service.RecoveryNotice);
        }
        Assert.Equal(stateBytes, await File.ReadAllBytesAsync(statePath));
        Assert.Equal(historyBytes, await File.ReadAllBytesAsync(historyPath));
        Assert.False(File.Exists(statePath + ".bak"));
        Assert.False(File.Exists(statePath + ".schema2.original"));
    }

    /// <summary>Assert the combined view payload, rather than bounding each field independently.</summary>
    private static void AssertPreviewBounded(PuloniaLegacyHistoryViewModel vm)
    {
        Assert.InRange(vm.PreviewUtf8ByteCount, 0, PuloniaLegacyHistoryViewModel.PreviewUtf8Limit);
        Assert.InRange(vm.OverviewFields.Concat(vm.FactFields).Sum(f => f.Value.Length), 0, PuloniaLegacyHistoryViewModel.PreviewCharacterLimit);
    }

    /// <summary>Write one synthetic old-format history file under this fixture's owned root.</summary>
    private async Task<string> WriteHistory(JObject data, string plan = "plan")
    {
        var directory = Path.Combine(_root, "history", plan);
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, Guid.Parse(data.Value<string>("run_id")!).ToString("N") + ".json");
        await File.WriteAllBytesAsync(path, Encoding.UTF8.GetBytes(data.ToString(Formatting.Indented) + "\n"));
        return path;
    }

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

    /// <summary>Delete only this fixture's temporary directory after all read handles and services have closed.</summary>
    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
