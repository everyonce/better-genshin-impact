using System.Text;
using BetterGenshinImpact.Pulonia.Executors;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.Service;
using Microsoft.Extensions.Logging.Abstractions;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Pure filesystem compatibility fixtures preserve old state and never invoke a game executor.</summary>
public sealed class PuloniaStateCompatibilityTests : IDisposable
{
    /// <summary>Every test owns a new temporary state directory.</summary>
    private readonly string _root = Path.Combine(Path.GetTempPath(), "bgi-state-compat-" + Guid.NewGuid().ToString("N"));
    /// <summary>The exact primary file under test.</summary>
    private string StatePath => Path.Combine(_root, "state.json");

    /// <summary>Build the exact schema-2 top-level grammar, including the old uncertainty collection.</summary>
    private static JObject EmptyLegacy(long sequence = 37)
    {
        var json = JObject.Parse(PuloniaTaskJson.WriteState(new PuloniaTaskState { Sequence = sequence }));
        json["schema_version"] = 2;
        json["uncertain_operations"] = new JArray();
        return json;
    }

    /// <summary>An entirely empty legacy state keeps its sequence and becomes current without new identities.</summary>
    [Fact]
    public void EmptyLegacyHasLosslessSequenceMapping()
    {
        var state = PuloniaTaskJson.ReadState(EmptyLegacy().ToString());
        Assert.Equal(4, state.SchemaVersion);
        Assert.Equal(37, state.Sequence);
        Assert.Empty(state.PendingRequests);
        Assert.Empty(state.PendingArchives);
        Assert.Empty(state.Ledger);
        Assert.Empty(state.TriggerStates);
        Assert.Null(state.ActiveRun);
    }

    /// <summary>Every identity, uncertainty or cursor-bearing collection requires a real semantic migration.</summary>
    [Theory]
    [InlineData("pending_requests")]
    [InlineData("pending_archives")]
    [InlineData("ledger")]
    [InlineData("uncertain_operations")]
    [InlineData("trigger_states")]
    [InlineData("active_run")]
    public void NonemptyLegacyDoesNotSilentlyDropRecords(string field)
    {
        var json = EmptyLegacy();
        var record = new JObject { ["run_id"] = "c0af6d72-d70f-4e41-8410-91a4025e1b6d" };
        json[field] = field == "active_run" ? record : new JArray(record);
        var error = Assert.Throws<PuloniaTaskStateCompatibilityException>(() => PuloniaTaskJson.ReadState(json.ToString()));
        Assert.Contains("not provably empty", error.Message);
        Assert.Contains("Preserve state.json", error.Message);
    }

    /// <summary>Missing, null and unknown legacy fields are not proof that old work is absent.</summary>
    [Theory]
    [InlineData("missing")]
    [InlineData("null")]
    [InlineData("unknown")]
    public void IncompleteLegacyCannotConvert(string kind)
    {
        var json = EmptyLegacy();
        if (kind == "missing") json.Remove("uncertain_operations");
        else if (kind == "null") json["uncertain_operations"] = JValue.CreateNull();
        else json["future_operation"] = new JObject();
        Assert.Throws<PuloniaTaskStateCompatibilityException>(() => PuloniaTaskJson.ReadState(json.ToString()));
    }

    /// <summary>A compatibility hold cannot roll back to a newer-looking empty backup or overwrite the original.</summary>
    [Fact]
    public async Task HeldPrimaryDoesNotFallbackOrPermitSave()
    {
        Directory.CreateDirectory(_root);
        var json = EmptyLegacy();
        json["uncertain_operations"] = new JArray(new JObject { ["operation_id"] = "unresolved" });
        var original = Encoding.UTF8.GetBytes(json.ToString());
        await File.WriteAllBytesAsync(StatePath, original);
        var backup = Encoding.UTF8.GetBytes(PuloniaTaskJson.WriteState(new PuloniaTaskState()));
        await File.WriteAllBytesAsync(StatePath + ".bak", backup);
        using var store = new PuloniaTaskStore(_root);
        await Assert.ThrowsAsync<PuloniaTaskStateCompatibilityException>(() => store.LoadStateAsync());
        await Assert.ThrowsAsync<PuloniaTaskStateCompatibilityException>(() => store.SaveStateAsync(new PuloniaTaskState()));
        Assert.Equal(original, await File.ReadAllBytesAsync(StatePath));
        Assert.Equal(backup, await File.ReadAllBytesAsync(StatePath + ".bak"));
    }

    /// <summary>First conversion preserves byte-exact BOM/whitespace and backup bytes across later v4 writes.</summary>
    [Fact]
    public async Task EmptyConversionPreservesBothOriginalFiles()
    {
        Directory.CreateDirectory(_root);
        var original = new UTF8Encoding(true).GetPreamble().Concat(Encoding.UTF8.GetBytes(EmptyLegacy().ToString() + "\n")).ToArray();
        var backup = Encoding.UTF8.GetBytes(EmptyLegacy(36).ToString() + " ");
        await File.WriteAllBytesAsync(StatePath, original);
        await File.WriteAllBytesAsync(StatePath + ".bak", backup);
        using var store = new PuloniaTaskStore(_root);
        var loaded = await store.LoadStateAsync();
        Assert.False(File.Exists(StatePath + ".schema-2.original"));
        await store.SaveStateAsync(loaded.State);
        loaded.State.Sequence++;
        await store.SaveStateAsync(loaded.State);
        Assert.Equal(original, await File.ReadAllBytesAsync(StatePath + ".schema-2.original"));
        Assert.Equal(backup, await File.ReadAllBytesAsync(StatePath + ".bak.schema-2.original"));
        Assert.Equal(4, JObject.Parse(await File.ReadAllTextAsync(StatePath)).Value<int>("schema_version"));
    }

    /// <summary>Loading only a backup still preserves it before a new primary is published.</summary>
    [Fact]
    public async Task BackupOnlyConversionPreservesItsSource()
    {
        Directory.CreateDirectory(_root);
        var backup = Encoding.UTF8.GetBytes(EmptyLegacy().ToString());
        await File.WriteAllBytesAsync(StatePath + ".bak", backup);
        using var store = new PuloniaTaskStore(_root);
        var loaded = await store.LoadStateAsync();
        Assert.True(loaded.RecoveredFromBackup);
        await store.SaveStateAsync(loaded.State);
        Assert.Equal(backup, await File.ReadAllBytesAsync(StatePath + ".bak.schema-2.original"));
    }

    /// <summary>Concurrent replacement and partial earlier preservation never overwrite original evidence.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ConversionRejectsChangedOrConflictingPreservation(bool archiveCollision)
    {
        Directory.CreateDirectory(_root);
        var original = Encoding.UTF8.GetBytes(EmptyLegacy().ToString());
        await File.WriteAllBytesAsync(StatePath, original);
        using var store = new PuloniaTaskStore(_root);
        var loaded = await store.LoadStateAsync();
        var conflictPath = archiveCollision ? StatePath + ".schema-2.original" : StatePath;
        await File.WriteAllTextAsync(conflictPath, "preserved conflicting bytes");
        await Assert.ThrowsAsync<PuloniaTaskStateCompatibilityException>(() => store.SaveStateAsync(loaded.State));
        Assert.Equal("preserved conflicting bytes", await File.ReadAllTextAsync(conflictPath));
        if (archiveCollision) Assert.Equal(original, await File.ReadAllBytesAsync(StatePath));
    }

    /// <summary>The application-facing service remains queryable while all scheduling and shutdown writes stay blocked.</summary>
    [Fact]
    public async Task ServiceHoldIsDiagnosticAndSurvivesDisposalWithoutWrites()
    {
        Directory.CreateDirectory(_root);
        var json = EmptyLegacy();
        json["uncertain_operations"] = new JArray(new JObject { ["operation_id"] = "unknown-outcome" });
        var original = Encoding.UTF8.GetBytes(json.ToString());
        await File.WriteAllBytesAsync(StatePath, original);
        var historyPath = Path.Combine(_root, "history", "plan", "legacy-run.json");
        Directory.CreateDirectory(Path.GetDirectoryName(historyPath)!);
        await File.WriteAllTextAsync(historyPath, "immutable historical data");
        using var store = new PuloniaTaskStore(_root);
        await using (var service = new PuloniaTaskService(store, new PuloniaTaskBuilder(store),
            [new PuloniaCSharpTaskExecutor(new PuloniaCSharpTaskRegistry())], new PuloniaGameTaskCoordinator(null!),
            new TaskStopService(NullLogger<TaskStopService>.Instance)))
        {
            Assert.Empty(await service.ListRunsAsync().WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.Contains("compatibility hold", service.RecoveryNotice);
            await Assert.ThrowsAsync<InvalidOperationException>(() => service.EnqueueAsync(new PuloniaTaskRequest { PlanId = "plan" }));
            await Assert.ThrowsAsync<InvalidOperationException>(() => service.CheckTriggersAsync([]));
        }
        Assert.Equal(original, await File.ReadAllBytesAsync(StatePath));
        Assert.Equal("immutable historical data", await File.ReadAllTextAsync(historyPath));
        Assert.False(File.Exists(StatePath + ".bak"));
        Assert.False(File.Exists(StatePath + ".schema-2.original"));
    }

    /// <summary>Clean only the test-owned temporary directory; no repository or user state is involved.</summary>
    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
