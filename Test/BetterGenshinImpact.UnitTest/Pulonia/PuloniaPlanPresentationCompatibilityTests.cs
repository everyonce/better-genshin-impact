using System.Text;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Synthetic-only legacy plan projection and transactional view-state persistence tests.</summary>
public sealed class PuloniaPlanPresentationCompatibilityTests : IDisposable
{
    /// <summary>Each case owns an isolated directory; no application user data is read.</summary>
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "bgi-plan-" + Guid.NewGuid().ToString("N"));

    /// <summary>Projection removes only node presentation and retains all executable token distinctions.</summary>
    [Fact]
    public async Task Migration_PreservesExecutableTokensRevisionAndExactOriginals()
    {
        var original = LegacyPlan();
        var expected = (JObject)original.DeepClone();
        expected["root_task"]!["is_expanded"]!.Parent!.Remove();
        expected["root_task"]!["children"]![0]!["is_expanded"]!.Parent!.Remove();
        var bytes = Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(original.ToString())).ToArray();
        var path = await WritePlanAsync(bytes);
        byte[] backup = [0, 255, 13, 10, 0];
        await File.WriteAllBytesAsync(path + ".bak", backup);
        using var store = new PuloniaTaskStore(_directory);

        var loaded = await store.LoadPlanAsync("legacy_plan");

        Assert.Equal(7, loaded!.Revision);
        Assert.Equal("legacy_plan", loaded.Id);
        Assert.Equal(0, store.PlanChangeVersion);
        Assert.True(JToken.DeepEquals(expected, JObject.Parse(await File.ReadAllTextAsync(path))));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path + ".presentation.original"));
        Assert.Equal(backup, await File.ReadAllBytesAsync(path + ".bak.presentation.original"));
        Assert.Equal(backup, await File.ReadAllBytesAsync(path + ".bak"));
        Assert.Equal(new[] { "root" }, (await store.LoadPlanViewStateAsync()).CollapsedTaskIds["legacy_plan"]);
        Assert.False(loaded.RootTask.Children[0].Parameters.Value<bool>("is_expanded"));
        Assert.Equal(JTokenType.Null, loaded.RootTask.Children[0].Parameters["nested"]!["is_expanded"]!.Type);
    }

    /// <summary>Explicit empty and nonempty sidecar entries both override the old presentation fields.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ExistingInitializedSidecarWins(bool hasCollapsedNode)
    {
        await WritePlanAsync(Encoding.UTF8.GetBytes(LegacyPlan().ToString()));
        using var store = new PuloniaTaskStore(_directory);
        var state = new PuloniaTaskPlanViewState();
        state.CollapsedTaskIds["legacy_plan"] = hasCollapsedNode ? ["leaf"] : [];
        await store.SavePlanViewStateAsync(state);
        var before = await File.ReadAllBytesAsync(Path.Combine(_directory, "plan-view-state.json"));

        await store.LoadPlanAsync("legacy_plan");

        Assert.Equal(before, await File.ReadAllBytesAsync(Path.Combine(_directory, "plan-view-state.json")));
        Assert.Equal(hasCollapsedNode ? new[] { "leaf" } : [],
            (await store.LoadPlanViewStateAsync()).CollapsedTaskIds["legacy_plan"]);
    }

    /// <summary>All-expanded legacy fields still create an explicit initialization entry.</summary>
    [Fact]
    public async Task AllExpandedLegacyPlanInitializesEmptyEntry()
    {
        var json = LegacyPlan(); json["root_task"]!["is_expanded"] = true;
        await WritePlanAsync(Encoding.UTF8.GetBytes(json.ToString()));
        using var store = new PuloniaTaskStore(_directory);
        await store.LoadPlanAsync("legacy_plan");
        var state = await store.LoadPlanViewStateAsync();
        Assert.True(state.CollapsedTaskIds.ContainsKey("legacy_plan"));
        Assert.Empty(state.CollapsedTaskIds["legacy_plan"]);
    }

    /// <summary>A plan replacement failure leaves the durable sidecar and exact old file available for retry.</summary>
    [Fact]
    public async Task FailedPlanReplacement_RetryDoesNotReseedSidecar()
    {
        var bytes = Encoding.UTF8.GetBytes(LegacyPlan().ToString());
        var path = await WritePlanAsync(bytes);
        using var store = new PuloniaTaskStore(_directory);
        // The ordinary Windows sharing rule denies only replacement, not reads or sidecar publication.
        using (var held = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            await Assert.ThrowsAsync<IOException>(() => store.LoadPlanAsync("legacy_plan"));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path + ".presentation.original"));
        Assert.Equal(new[] { "root" }, (await store.LoadPlanViewStateAsync()).CollapsedTaskIds["legacy_plan"]);
        var choice = new PuloniaTaskPlanViewState(); choice.CollapsedTaskIds["legacy_plan"] = [];
        await store.SavePlanViewStateAsync(choice);

        var recovered = await store.LoadPlanAsync("legacy_plan");

        Assert.Equal(7, recovered!.Revision);
        Assert.Empty((await store.LoadPlanViewStateAsync()).CollapsedTaskIds["legacy_plan"]);
        Assert.Null(JObject.Parse(await File.ReadAllTextAsync(path))["root_task"]!["is_expanded"]);
    }

    /// <summary>Sidecar publication failure must not change the legacy executable document.</summary>
    [Fact]
    public async Task FailedSidecarPublication_PreservesLegacyPlan()
    {
        var bytes = Encoding.UTF8.GetBytes(LegacyPlan().ToString());
        var path = await WritePlanAsync(bytes);
        Directory.CreateDirectory(Path.Combine(_directory, "plan-view-state.json"));
        using var store = new PuloniaTaskStore(_directory);
        await Assert.ThrowsAsync<IOException>(() => store.LoadPlanAsync("legacy_plan"));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path + ".presentation.original"));
    }

    /// <summary>Unreadable metadata and conflicting preservation evidence never permit partial publication.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task InvalidMetadataOrOriginalBlocksMigration(bool conflictingOriginal)
    {
        var bytes = Encoding.UTF8.GetBytes(LegacyPlan().ToString());
        var path = await WritePlanAsync(bytes);
        var evidence = conflictingOriginal ? path + ".presentation.original" : Path.Combine(_directory, "plan-view-state.json");
        await File.WriteAllTextAsync(evidence, conflictingOriginal ? "different-original" : "{}");
        using var store = new PuloniaTaskStore(_directory);
        if (conflictingOriginal)
            await Assert.ThrowsAsync<PuloniaTaskValidationException>(() => store.LoadPlanAsync("legacy_plan"));
        else
            await Assert.ThrowsAsync<JsonSerializationException>(() => store.LoadPlanAsync("legacy_plan"));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        Assert.Equal(conflictingOriginal ? "different-original" : "{}", await File.ReadAllTextAsync(evidence));
    }

    /// <summary>A conflicting backup archive blocks sidecar publication while preserving both original inputs.</summary>
    [Fact]
    public async Task ConflictingBackupOriginalBlocksBeforeSidecarPublication()
    {
        var bytes = Encoding.UTF8.GetBytes(LegacyPlan().ToString());
        var path = await WritePlanAsync(bytes);
        byte[] backup = [1, 2, 3];
        await File.WriteAllBytesAsync(path + ".bak", backup);
        await File.WriteAllTextAsync(path + ".bak.presentation.original", "different");
        using var store = new PuloniaTaskStore(_directory);
        await Assert.ThrowsAsync<PuloniaTaskValidationException>(() => store.LoadPlanAsync("legacy_plan"));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        Assert.Equal(backup, await File.ReadAllBytesAsync(path + ".bak"));
        Assert.False(File.Exists(Path.Combine(_directory, "plan-view-state.json")));
    }

    /// <summary>A filename/ID mismatch rejects before originals or sidecar state are written.</summary>
    [Fact]
    public async Task WrongFileIdentityNeverPublishesPresentation()
    {
        var bytes = Encoding.UTF8.GetBytes(LegacyPlan().ToString());
        var path = await WritePlanAsync(bytes, "other");
        using var store = new PuloniaTaskStore(_directory);
        await Assert.ThrowsAsync<PuloniaTaskValidationException>(() => store.LoadPlanAsync("other"));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        Assert.False(File.Exists(path + ".presentation.original"));
        Assert.False(File.Exists(Path.Combine(_directory, "plan-view-state.json")));
    }

    /// <summary>Sidecar merging preserves failed/unloaded plan choices, including initialized empty lists.</summary>
    [Fact]
    public async Task SidecarUpdatePreservesUnmentionedPlans()
    {
        using var store = new PuloniaTaskStore(_directory);
        var first = new PuloniaTaskPlanViewState();
        first.CollapsedTaskIds["unloaded"] = ["kept"];
        first.CollapsedTaskIds["already_expanded"] = [];
        await store.SavePlanViewStateAsync(first);
        var next = new PuloniaTaskPlanViewState(); next.CollapsedTaskIds["visible"] = [];
        await store.SavePlanViewStateAsync(next);
        var saved = await store.LoadPlanViewStateAsync();
        Assert.Equal(new[] { "kept" }, saved.CollapsedTaskIds["unloaded"]);
        Assert.Empty(saved.CollapsedTaskIds["already_expanded"]);
        Assert.Empty(saved.CollapsedTaskIds["visible"]);
    }

    /// <summary>Save uses the already-held gates and retains originals before its legitimate revision increment.</summary>
    [Fact]
    public async Task SaveLegacyPlanPreservesPresentationBeforeIncrementingRevision()
    {
        var bytes = Encoding.UTF8.GetBytes(LegacyPlan().ToString());
        var path = await WritePlanAsync(bytes);
        var plan = PuloniaTaskJson.ReadPlan(Encoding.UTF8.GetString(bytes));
        using var store = new PuloniaTaskStore(_directory);
        plan.Name = "Explicit edit";
        var saved = await store.SavePlanAsync(plan);
        Assert.Equal(8, saved.Revision);
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path + ".presentation.original"));
        Assert.Equal(new[] { "root" }, (await store.LoadPlanViewStateAsync()).CollapsedTaskIds["legacy_plan"]);
    }

    /// <summary>Current documents need no writer lock, rewrite or migration sidecar.</summary>
    [Fact]
    public async Task CurrentPlanReadRemainsReadOnly()
    {
        var original = LegacyPlan();
        original["root_task"]!["is_expanded"]!.Parent!.Remove();
        original["root_task"]!["children"]![0]!["is_expanded"]!.Parent!.Remove();
        var bytes = Encoding.UTF8.GetBytes(original.ToString());
        var path = await WritePlanAsync(bytes);
        using var held = new FileStream(Path.Combine(_directory, ".writer.lock"), FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None);
        using var store = new PuloniaTaskStore(_directory);
        Assert.Equal(7, (await store.LoadPlanAsync("legacy_plan"))!.Revision);
        Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        Assert.False(File.Exists(Path.Combine(_directory, "plan-view-state.json")));
        Assert.False(File.Exists(path + ".presentation.original"));
    }

    /// <summary>Modern alternate structural casing retains the existing serializer acceptance.</summary>
    [Fact]
    public void CurrentPlanWithoutPresentationKeepsOrdinarySerializerBehavior()
    {
        var json = LegacyPlan();
        var root = (JObject)json["root_task"]!;
        root["is_expanded"]!.Parent!.Remove();
        root["children"]![0]!["is_expanded"]!.Parent!.Remove();
        json.Remove("root_task"); json["ROOT_TASK"] = root;
        var loaded = PuloniaTaskJson.ReadPlan(json.ToString());
        Assert.Equal("root", loaded.RootTask.Id);
        Assert.Equal(7, loaded.Revision);
    }

    /// <summary>Legacy expansion is Boolean-only; coercion must not conceal invalid persisted data.</summary>
    [Theory]
    [InlineData("null")]
    [InlineData("0")]
    [InlineData("1")]
    [InlineData("\"false\"")]
    [InlineData("{}")]
    [InlineData("[]")]
    public void NonBooleanPresentationIsRejected(string value)
    {
        var json = LegacyPlan(); json["root_task"]!["is_expanded"] = JToken.Parse(value);
        Assert.Throws<PuloniaTaskValidationException>(() => PuloniaTaskJson.ReadPlan(json.ToString()));
    }

    /// <summary>Only the canonical node field is recognized; all other strict envelopes remain strict.</summary>
    [Theory]
    [InlineData("top")]
    [InlineData("policy")]
    [InlineData("unknown_node")]
    [InlineData("duplicate")]
    [InlineData("extra_root")]
    [InlineData("schema")]
    public void StrictRejectionOutsidePresentationIsPreserved(string kind)
    {
        var json = LegacyPlan();
        if (kind == "top") json["is_expanded"] = false;
        if (kind == "policy") json["root_task"]!["policy"] = new JObject { ["is_expanded"] = false };
        if (kind == "unknown_node") json["root_task"]!["unknown"] = false;
        if (kind == "schema") json["schema_version"] = 99;
        var text = json.ToString(Formatting.None);
        if (kind == "duplicate") text = text.Replace("\"is_expanded\":false", "\"is_expanded\":false,\"is_expanded\":true");
        if (kind == "extra_root") text += "{}";
        Assert.ThrowsAny<JsonException>(() => PuloniaTaskJson.ReadPlan(text));
    }

    /// <summary>Persisted identity compatibility includes historical account IDs without changing generators.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(32)]
    [InlineData(33)]
    [InlineData(96)]
    public void LegacyIdentityRangeIsAccepted(int length)
        => PuloniaTaskValidator.ValidateId(new string('a', length), "legacy");

    /// <summary>File naming restrictions and the legacy upper bound are not loosened.</summary>
    [Theory]
    [InlineData("")]
    [InlineData("CON")]
    [InlineData("con")]
    [InlineData("../plan")]
    [InlineData("Upper")]
    public void UnsafeIdentityIsRejected(string id)
        => Assert.Throws<PuloniaTaskValidationException>(() => PuloniaTaskValidator.ValidateId(id, "legacy"));

    /// <summary>The actual old generated account ID and long plan/task IDs keep their exact bindings.</summary>
    [Fact]
    public async Task LegacyLongIdsRoundTripWithoutReidentification()
    {
        var json = LegacyPlan(); var id = new string('p', 96); var taskId = new string('t', 96);
        var accountId = "account_0123456789abcdef0123456789abcdef";
        json["id"] = id; json["root_task"]!["id"] = taskId;
        json["accounts"] = new JArray(new JObject { ["account_id"] = accountId });
        await WritePlanAsync(Encoding.UTF8.GetBytes(json.ToString()), id);
        using var store = new PuloniaTaskStore(_directory);
        var loaded = await store.LoadPlanAsync(id);
        Assert.Equal(id, loaded!.Id); Assert.Equal(taskId, loaded.RootTask.Id);
        Assert.Equal(accountId, Assert.Single(loaded.Accounts).AccountId);
        Assert.Equal(new[] { taskId }, (await store.LoadPlanViewStateAsync()).CollapsedTaskIds[id]);
        Assert.Throws<PuloniaTaskValidationException>(() => PuloniaTaskValidator.ValidateId(new string('a', 97), "legacy"));
    }

    /// <summary>Projection enforces the existing tree depth before walking user-controlled descendants.</summary>
    [Theory]
    [InlineData(64, true)]
    [InlineData(65, false)]
    public void ExistingTreeDepthBoundRemains(int depth, bool accepted)
    {
        var json = LegacyPlan(); var node = (JObject)json["root_task"]!; node["children"] = new JArray();
        for (var i = 1; i <= depth; i++)
        {
            var child = new JObject { ["id"] = "node_" + i, ["name"] = "Group", ["task_type"] = "group", ["is_expanded"] = true };
            node["children"] = new JArray(child); node = child;
        }
        if (accepted) Assert.NotNull(PuloniaTaskJson.ReadPlan(json.ToString()));
        else Assert.Throws<PuloniaTaskValidationException>(() => PuloniaTaskJson.ReadPlan(json.ToString()));
    }

    /// <summary>Small explicit legacy writer-shaped fixture; parameters contain a namesake that must survive.</summary>
    private static JObject LegacyPlan() => JObject.Parse("""
        {"schema_version":2,"id":"legacy_plan","revision":7,"name":"Legacy",
         "root_task":{"id":"root","name":"Root","task_type":"group","is_expanded":false,
          "children":[{"id":"leaf","name":"Leaf","task_type":"csharp","is_enabled":false,"is_expanded":true,
           "parameters":{"operation":"sample.sum","values":[0],"is_expanded":false,"nested":{"is_expanded":null}}}]}}
        """);

    /// <summary>Write only this test's synthetic input, preserving caller-supplied original bytes.</summary>
    private async Task<string> WritePlanAsync(byte[] bytes, string id = "legacy_plan")
    {
        var folder = Path.Combine(_directory, "plans"); Directory.CreateDirectory(folder);
        var path = Path.Combine(folder, id + ".json"); await File.WriteAllBytesAsync(path, bytes); return path;
    }

    /// <summary>Clean only the test-owned temporary directory after all test handles have been released.</summary>
    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, recursive: true);
    }
}
