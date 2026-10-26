using BetterGenshinImpact.GameTask.AutoBoss;
using BetterGenshinImpact.GameTask.AutoDomain;
using BetterGenshinImpact.GameTask.AutoLeyLineOutcrop;
using BetterGenshinImpact.GameTask.AutoStygianOnslaught;
using BetterGenshinImpact.GameTask.Common.Resin;
using BetterGenshinImpact.GameTask.SoloTask;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.ViewModel.Pages.Pulonia;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Synthetic source bags only: no application configuration, runtime, captures, or account data.</summary>
public sealed class PuloniaResinCompatibilityTests
{
    /// <summary>Capability defaults cannot eclipse legacy data inherited across all source layers.</summary>
    [Fact]
    public void Resolver_FoldsPresetGroupNodeReferenceAndCallBeforeMapping()
    {
        var preset = new PuloniaTaskPreset { Id = "pre-old", TaskType = "solo.auto_boss", Values = Boss() };
        preset.Values.Remove("run_count");
        var task = TaskFor("solo.auto_boss", new JObject { ["run_count"] = 3 });
        var group = Override(task.TaskType, new JObject { ["run_count"] = 2 });
        var reference = Override(task.TaskType, new JObject { ["run_count"] = 4 });
        var call = new JObject { ["run_count"] = 5 };
        var originals = new JArray(preset.Values.DeepClone(), task.Parameters.DeepClone(), group.Values.DeepClone(), reference.Values.DeepClone(), call.DeepClone());

        var result = PuloniaParameterResolver.Resolve(task, Definition(task.TaskType), preset.Id, preset,
            new IReadOnlyList<PuloniaTaskParameterOverride>[] { new[] { group } }, new[] { reference }, call);

        Assert.Null(result.CompatibilityError);
        Assert.False(result.HasUndeclaredPublicOverride);
        Assert.Equal(5, result.Parameters["resin_usage"]!.Value<int>("run_count"));
        Assert.Equal("RunCount", result.Parameters["resin_usage"]!.Value<string>("mode"));
        Assert.Equal(PuloniaParameterLayer.LegacyCompatibility, result.Sources["resin_usage"].Layer);
        Assert.False(result.Parameters.ContainsKey("run_count"));
        Assert.True(JToken.DeepEquals(originals, new JArray(preset.Values, task.Parameters, group.Values, reference.Values, call)));
    }

    /// <summary>Any user layer using the new format, even below a later old field, wins by presence rather than truthiness.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Resolver_UserFormatIncludingNullWinsOverLaterLegacy(bool useNull)
    {
        var preset = new PuloniaTaskPreset
        {
            Id = "pre-new", TaskType = "solo.auto_boss",
            Values = new JObject { ["resin_usage"] = useNull ? JValue.CreateNull() : NewUsage(7) }
        };
        var task = TaskFor(preset.TaskType, new JObject { ["run_count"] = 3, ["use_fragile_resin"] = JValue.CreateNull() });
        var result = PuloniaParameterResolver.Resolve(task, Definition(task.TaskType), preset.Id, preset, []);
        Assert.Null(result.CompatibilityError);
        Assert.True(JToken.DeepEquals(preset.Values["resin_usage"], result.Parameters["resin_usage"]));
        Assert.Equal(PuloniaParameterLayer.Preset, result.Sources["resin_usage"].Layer);
        Assert.False(result.Parameters.ContainsKey("use_fragile_resin"));
        PuloniaTaskValidator.ValidateParameters(result.Parameters, Definition(task.TaskType).ParameterSchema, "test");
    }

    /// <summary>A partial legacy input never borrows a guessed field from the current mode's defaults.</summary>
    [Fact]
    public void Resolver_MissingLegacyFieldRetainsRawEffectiveBagAndEnglishDiagnostic()
    {
        var task = TaskFor("solo.auto_boss", new JObject { ["run_count"] = 0 });
        var result = Resolve(task);
        Assert.Contains("Missing legacy field 'specify_run_count'", result.CompatibilityError);
        Assert.Equal(0, result.Parameters.Value<int>("run_count"));
        Assert.Equal(0, task.Parameters.Value<int>("run_count"));
        Assert.Throws<PuloniaTaskValidationException>(result.RequireCompatible);
    }

    /// <summary>Null, strings, floating numbers and numeric Booleans do not coerce into legacy fields.</summary>
    [Theory]
    [InlineData("specify_run_count", "null")]
    [InlineData("specify_run_count", "0")]
    [InlineData("specify_run_count", "\"false\"")]
    [InlineData("run_count", "null")]
    [InlineData("run_count", "2.0")]
    [InlineData("run_count", "\"2\"")]
    [InlineData("run_count", "1000")]
    [InlineData("run_count", "-1")]
    public void Resolver_RefusesInvalidScalarsWithoutReplacingThem(string name, string json)
    {
        var values = Boss(); values[name] = JToken.Parse(json);
        var result = Resolve(TaskFor("solo.auto_boss", values));
        Assert.Contains("Resin compatibility:", result.CompatibilityError);
        Assert.True(JToken.DeepEquals(values[name], result.Parameters[name]));
    }

    /// <summary>Explicit false and zero remain valid retained settings in old exhaustion mode.</summary>
    [Fact]
    public void Resolver_PreservesFalseModeAndZeroHiddenCount()
    {
        var values = Boss(); values["specify_run_count"] = false; values["run_count"] = 0;
        var result = Resolve(TaskFor("solo.auto_boss", values));
        Assert.Null(result.CompatibilityError);
        var usage = result.Parameters["resin_usage"]!;
        Assert.Equal("Exhaust", usage.Value<string>("mode"));
        Assert.Equal(0, usage.Value<int>("run_count"));
        Assert.False(usage["allowed"]!.Value<bool>("fragile"));
    }

    /// <summary>Zero is retained as data but cannot silently turn an active finite policy into successful preparation.</summary>
    [Theory]
    [InlineData("solo.auto_domain")]
    [InlineData("solo.auto_stygian_onslaught")]
    [InlineData("solo.auto_boss")]
    [InlineData("solo.auto_ley_line_outcrop")]
    public void Resolver_RejectsZeroActiveClaimBudget(string type)
    {
        var values = type switch
        {
            "solo.auto_domain" => Domain(),
            "solo.auto_stygian_onslaught" => PerKind(),
            "solo.auto_boss" => Boss(),
            _ => new JObject { ["is_resin_exhaustion_mode"] = false, ["open_mode_count_min"] = false,
                ["count"] = 0, ["use_transient_resin"] = false, ["use_fragile_resin"] = false }
        };
        if (values.ContainsKey("condensed_resin_use_count")) values["condensed_resin_use_count"] = 0;
        if (values.ContainsKey("run_count")) values["run_count"] = 0;
        var expected = type is "solo.auto_domain" or "solo.auto_stygian_onslaught"
            ? "at least one positive claim count" : "must be positive";
        Assert.Contains(expected, Resolve(TaskFor(type, values)).CompatibilityError);
    }

    /// <summary>Formerly invalid Boss exhaustion cannot become a valid replenishment loop through migration.</summary>
    [Theory]
    [InlineData("use_transient_resin")]
    [InlineData("use_fragile_resin")]
    public void Resolver_RefusesBossExhaustionWithSupplements(string flag)
    {
        var values = Boss(); values["specify_run_count"] = false; values[flag] = true;
        Assert.Contains("Legacy Boss exhaustion", Resolve(TaskFor("solo.auto_boss", values)).CompatibilityError);
    }

    /// <summary>The pure mapper's safe exact-20 branch remains available, preserving all other counts.</summary>
    [Fact]
    public void Resolver_MapsDomainOnly20WithoutChangingOtherCounts()
    {
        var values = Domain(); values["original_resin20_use_count"] = 2;
        var result = Resolve(TaskFor("solo.auto_domain", values));
        Assert.Null(result.CompatibilityError);
        Assert.Equal("Only20", result.Parameters["resin_usage"]!.Value<string>("original_tier"));
        Assert.Equal(2, result.Parameters["resin_usage"]!["counts"]!.Value<int>("original"));
        Assert.False(result.Parameters.ContainsKey("domain_round_num"));
        Assert.False(values.ContainsKey("domain_round_num"));
    }

    /// <summary>Hard-40, mixed quotas and independent attempt caps are not silently flattened, even with a new resin object.</summary>
    [Theory]
    [InlineData("original_resin40_use_count", 1)]
    [InlineData("original_resin_use_count", 1)]
    [InlineData("domain_round_num", 0)]
    [InlineData("domain_round_num", 3)]
    public void Resolver_RefusesNonEquivalentDomainLimits(string name, int value)
    {
        var values = Domain(); values["original_resin20_use_count"] = 2; values[name] = value;
        var result = Resolve(TaskFor("solo.auto_domain", values));
        Assert.NotNull(result.CompatibilityError);
        Assert.Equal(value, result.Parameters.Value<int>(name));
        if (name == "domain_round_num")
        {
            values["resin_usage"] = NewUsage(1);
            Assert.Contains("independent attempt limit", Resolve(TaskFor("solo.auto_domain", values)).CompatibilityError);
        }
    }

    /// <summary>Explicit 9999 and omission select the same current constructor-bound projection; source pins prove the retained loop bound.</summary>
    [Fact]
    public void Resolver_Explicit9999MatchesOmittedFiniteBoundProjection()
    {
        var omitted = Domain();
        var explicitLimit = (JObject)omitted.DeepClone(); explicitLimit["domain_round_num"] = 9999;
        var without = Resolve(TaskFor("solo.auto_domain", omitted));
        var withLimit = Resolve(TaskFor("solo.auto_domain", explicitLimit));
        Assert.Null(withLimit.CompatibilityError);
        Assert.True(JToken.DeepEquals(without.Parameters, withLimit.Parameters));
        Assert.False(withLimit.Parameters.ContainsKey("domain_round_num"));
        Assert.Equal(9999, explicitLimit.Value<int>("domain_round_num"));
    }

    /// <summary>Old false per-kind mode retains hidden counts and uses the mapper's direct-resin exhaustion policy.</summary>
    [Fact]
    public void Resolver_MapsStygianFalseWithoutLosingHiddenCounts()
    {
        var values = PerKind(); values["specify_resin_use"] = false; values["fragile_resin_use_count"] = 8;
        var result = Resolve(TaskFor("solo.auto_stygian_onslaught", values));
        Assert.Null(result.CompatibilityError);
        Assert.Equal("Exhaust", result.Parameters["resin_usage"]!.Value<string>("mode"));
        Assert.Equal(8, result.Parameters["resin_usage"]!["counts"]!.Value<int>("fragile"));
        Assert.False(result.Parameters["resin_usage"]!["allowed"]!.Value<bool>("fragile"));
    }

    /// <summary>All four old Ley Line switch combinations keep their documented effective mode.</summary>
    [Theory]
    [InlineData(false, false, "RunCount")]
    [InlineData(false, true, "RunCount")]
    [InlineData(true, false, "Exhaust")]
    [InlineData(true, true, "RunCount")]
    public void Resolver_MapsLeyLineModes(bool exhaustion, bool minimum, string expected)
    {
        var values = new JObject
        {
            ["is_resin_exhaustion_mode"] = exhaustion, ["open_mode_count_min"] = minimum,
            ["count"] = 4, ["use_transient_resin"] = false, ["use_fragile_resin"] = true,
            ["is_go_to_synthesizer"] = JValue.CreateNull()
        };
        var result = Resolve(TaskFor("solo.auto_ley_line_outcrop", values));
        Assert.Null(result.CompatibilityError);
        Assert.Equal(expected, result.Parameters["resin_usage"]!.Value<string>("mode"));
        Assert.Equal(4, result.Parameters["resin_usage"]!.Value<int>("run_count"));
        Assert.True(result.Parameters["resin_usage"]!["allowed"]!.Value<bool>("fragile"));
        Assert.False(result.Parameters.ContainsKey("is_go_to_synthesizer"));
        Assert.Equal(JTokenType.Null, values["is_go_to_synthesizer"]!.Type);
    }

    /// <summary>Unknown names and same-spelling fields in another task family still reach the existing strict schema.</summary>
    [Fact]
    public void Resolver_DoesNotBroadenFamilyOrUnknownPropertyAdmission()
    {
        var values = Boss(); values["unexpected"] = new JObject { ["count"] = 1 };
        var result = Resolve(TaskFor("solo.auto_boss", values));
        Assert.True(JToken.DeepEquals(values["unexpected"], result.Parameters["unexpected"]));
        Assert.Throws<PuloniaTaskValidationException>(() => PuloniaTaskValidator.ValidateParameters(result.Parameters,
            Definition("solo.auto_boss").ParameterSchema, "test"));
        var foreign = PuloniaResinCompatibility.Resolve("sample.echo", values, false, out var error, out var mapped);
        Assert.Null(error); Assert.False(mapped); Assert.True(JToken.DeepEquals(values, foreign));
        Assert.False(PuloniaResinCompatibility.IsLegacyField("solo.auto_boss", "specify_resin_use"));
    }

    /// <summary>Legacy aliases cross references only when the exact family exposes its current resin parameter.</summary>
    [Fact]
    public void Resolver_ReferenceUnknownOrPrivateOverrideStillRefusesWholeItem()
    {
        var task = TaskFor("solo.auto_boss", Boss());
        var bad = Override(task.TaskType, new JObject { ["run_count"] = 9, ["unlisted"] = true });
        var result = PuloniaParameterResolver.Resolve(task, Definition(task.TaskType), null, null, [], [bad]);
        Assert.True(result.HasUndeclaredPublicOverride);
        Assert.Equal(2, result.Parameters["resin_usage"]!.Value<int>("run_count"));
        var privateDefinition = new PuloniaTaskDefinition { TaskType = task.TaskType, PublicParameters = [] };
        result = PuloniaParameterResolver.Resolve(task, privateDefinition, null, null, [],
            [Override(task.TaskType, new JObject { ["run_count"] = 9 })]);
        Assert.True(result.HasUndeclaredPublicOverride);
    }

    /// <summary>Weekday sparse fields inherit actual old siblings before mapping, then the execution overlay consumes the projection.</summary>
    [Fact]
    public void Resolver_WeekdayUsesOriginalFoldedFieldsAndDetachesOutput()
    {
        var values = Boss(); values["use_transient_resin"] = true;
        values["weekday_overrides"] = new JObject { ["1"] = new JObject { ["run_count"] = 4, ["enabled"] = true } };
        var before = values.DeepClone();
        var result = Resolve(TaskFor("solo.auto_boss", values));
        Assert.Null(result.CompatibilityError);
        var day = (JObject)result.Parameters["weekday_overrides"]!["1"]!;
        var selected = PuloniaResinCompatibility.Overlay(result.Parameters, day);
        PuloniaResinCompatibility.RequirePrepared("solo.auto_boss", selected);
        Assert.Equal(4, selected["resin_usage"]!.Value<int>("run_count"));
        Assert.True(selected["resin_usage"]!["allowed"]!.Value<bool>("transient"));
        Assert.Equal(2, result.Parameters["resin_usage"]!.Value<int>("run_count"));
        selected["resin_usage"]!["run_count"] = 8;
        Assert.Equal(4, day["resin_usage"]!.Value<int>("run_count"));
        Assert.True(JToken.DeepEquals(before, values));
    }

    /// <summary>Explicit current base or day format wins over inherited old fields without consulting a constructor.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Resolver_WeekdayExplicitFormatWins(bool explicitDay)
    {
        var values = Boss();
        var day = new JObject { ["run_count"] = 8 };
        if (explicitDay) day["resin_usage"] = JValue.CreateNull();
        else values["resin_usage"] = NewUsage(3);
        values["weekday_overrides"] = new JObject { ["2"] = day };
        var result = Resolve(TaskFor("solo.auto_boss", values));
        Assert.Null(result.CompatibilityError);
        var selected = result.Parameters["weekday_overrides"]!["2"]!["resin_usage"]!;
        if (explicitDay) Assert.Equal(JTokenType.Null, selected.Type);
        else Assert.Equal(3, selected.Value<int>("run_count"));
    }

    /// <summary>A partial old weekday cannot inherit an invented old count or switch from the new capability default.</summary>
    [Fact]
    public void Resolver_WeekdayMissingOldDefaultsHoldsPreparation()
    {
        var values = new JObject { ["weekday_overrides"] = new JObject { ["3"] = new JObject { ["run_count"] = 4 } } };
        var result = Resolve(TaskFor("solo.auto_boss", values));
        Assert.Contains("weekday_overrides[3]", result.CompatibilityError);
        Assert.Contains("Missing legacy field", result.CompatibilityError);
        Assert.True(JToken.DeepEquals(values["weekday_overrides"], result.Parameters["weekday_overrides"]));
    }

    /// <summary>Disabled schedules keep their actual source bags; enabling one later requires fresh compatible preparation.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Resolver_DisabledWeekdayRetainsUnresolvedRawValues(bool global)
    {
        var values = Domain();
        var day = new JObject { ["original_resin40_use_count"] = 7 };
        if (global) values["weekday_overrides_enabled"] = false;
        else day["enabled"] = false;
        values["weekday_overrides"] = new JObject { ["0"] = day };
        var result = Resolve(TaskFor("solo.auto_domain", values));
        Assert.Null(result.CompatibilityError);
        Assert.True(JToken.DeepEquals(day, result.Parameters["weekday_overrides"]!["0"]));
    }

    /// <summary>Historical prepared data is not reinterpreted merely because a new compatibility helper exists.</summary>
    [Fact]
    public void PreparedSnapshot_WithLegacyFieldsIsRejectedWithoutMutation()
    {
        var values = Boss(); var before = values.DeepClone();
        var ex = Assert.Throws<PuloniaTaskValidationException>(() => PuloniaResinCompatibility.RequirePrepared("solo.auto_boss", values));
        Assert.Contains("historical snapshots are not converted", ex.Message);
        Assert.True(JToken.DeepEquals(before, values));
    }

    /// <summary>Plan and preset serializers retain the raw legacy bags; normalization is only an effective projection.</summary>
    [Fact]
    public void SourceRoundTrip_PreservesPlanPresetAndUnrelatedTokens()
    {
        var values = Boss(); values["party_name"] = JValue.CreateNull(); values["custom"] = new JArray(false, 0, JValue.CreateNull());
        var plan = Plan(values);
        var preset = new PuloniaTaskPreset { Id = "pre-roundtrip", TaskType = "solo.auto_boss", Values = (JObject)values.DeepClone() };
        var loaded = PuloniaTaskJson.ReadPlan(PuloniaTaskJson.WritePlan(plan));
        var loadedPreset = PuloniaTaskJson.ReadPreset(PuloniaTaskJson.WritePreset(preset));
        Assert.True(JToken.DeepEquals(values, loaded.RootTask.Children[0].Parameters));
        Assert.True(JToken.DeepEquals(values, loadedPreset.Values));
        var result = Resolve(loaded.RootTask.Children[0]);
        Assert.Equal(JTokenType.Null, result.Parameters["party_name"]!.Type);
        Assert.True(JToken.DeepEquals(values["custom"], result.Parameters["custom"]));
        Assert.Equal(0, loaded.Revision);
    }

    /// <summary>Builder and preview consume the same normalized result; saved plan/preset JSON and identities remain unchanged.</summary>
    [Fact]
    public async Task BuilderAndPreview_ShareProjectionAndRetainPlanSource()
    {
        var directory = Path.Combine(Path.GetTempPath(), "bgi-resin-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store = new PuloniaTaskStore(directory);
            var plan = Plan(Boss()); var before = PuloniaTaskJson.WritePlan(plan);
            var definition = Definition("solo.auto_boss");
            var built = await new PuloniaTaskBuilder(store).BuildAsync(plan, new PuloniaTaskBuildOptions { Definitions = [definition] });
            var document = new PuloniaTaskPlanDocumentViewModel(plan, [], new PuloniaTaskClipboardService(), false);
            document.SetDefinitions([definition]);
            var node = document.EnumerateNodes().Single(n => n.Id == "tsk-resin");
            Assert.True(JToken.DeepEquals(built.RootTask.Children[0].Parameters, document.GetOneDragonParameters(node)));
            Assert.Equal("legacy-resin/pln-resin/tsk-root/tsk-resin", built.RootTask.Children[0].ParameterSources["resin_usage"]);
            Assert.Equal(before, PuloniaTaskJson.WritePlan(plan));
        }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, true); }
    }

    /// <summary>The actual builder rejects before execution and the nonthrowing preview displays the same English diagnostic.</summary>
    [Fact]
    public async Task BuilderAndPreview_ReportUnresolvedDefaults()
    {
        var directory = Path.Combine(Path.GetTempPath(), "bgi-resin-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store = new PuloniaTaskStore(directory);
            var plan = Plan(new JObject { ["run_count"] = 5 }); var definition = Definition("solo.auto_boss");
            var ex = await Assert.ThrowsAsync<PuloniaTaskValidationException>(() => new PuloniaTaskBuilder(store).BuildAsync(plan,
                new PuloniaTaskBuildOptions { Definitions = [definition] }));
            var document = new PuloniaTaskPlanDocumentViewModel(plan, [], new PuloniaTaskClipboardService(), false);
            document.SetDefinitions([definition]);
            Assert.EndsWith(document.GetOneDragonConfigurationSummary(document.EnumerateNodes().Single(n => n.Id == "tsk-resin")), ex.Message);
        }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, true); }
    }

    /// <summary>An explicit edit is resolved from raw source layers, so it can replace an unresolved old family without erasing it.</summary>
    [Fact]
    public void NodeSettings_ExplicitNewPolicyResolvesOldHoldWithoutChangingRawLegacyFields()
    {
        var plan = Plan(new JObject { ["run_count"] = 5 });
        var document = new PuloniaTaskPlanDocumentViewModel(plan, [], new PuloniaTaskClipboardService(), false);
        document.SetDefinitions([Definition("solo.auto_boss")]);
        var node = document.EnumerateNodes().Single(n => n.Id == "tsk-resin");
        Assert.Contains("Missing legacy field", document.GetOneDragonConfigurationSummary(node));
        Assert.True(document.ApplyNodeSettings(node, node.Name, true, 1, null, new JObject { ["resin_usage"] = NewUsage(7) }));
        Assert.Equal(5, node.Model.Parameters.Value<int>("run_count"));
        var preview = document.GetOneDragonParameters(node);
        Assert.Equal(7, preview["resin_usage"]!.Value<int>("run_count"));
        Assert.False(preview.ContainsKey("run_count"));
    }

    /// <summary>Use the production resolver's empty-layer form for independent cases.</summary>
    private static PuloniaParameterResolution Resolve(PuloniaTask task) => PuloniaParameterResolver.Resolve(task, Definition(task.TaskType), null, null, []);

    /// <summary>A complete old Boss bag; tests remove or overwrite only the field under examination.</summary>
    private static JObject Boss() => new() { ["specify_run_count"] = true, ["run_count"] = 2, ["use_transient_resin"] = false, ["use_fragile_resin"] = false };

    /// <summary>Complete old per-kind inputs with zero preserved for each inactive count.</summary>
    private static JObject PerKind() => new() { ["specify_resin_use"] = true, ["original_resin_use_count"] = 0, ["condensed_resin_use_count"] = 1, ["transient_resin_use_count"] = 0, ["fragile_resin_use_count"] = 0 };

    /// <summary>Domain has two extra explicit tier counters; no configuration default is constructed.</summary>
    private static JObject Domain() { var values = PerKind(); values["original_resin20_use_count"] = 0; values["original_resin40_use_count"] = 0; return values; }

    /// <summary>A current explicit Boss policy, created by the existing pure mapper.</summary>
    private static JObject NewUsage(int count) => JObject.Parse(SoloTaskJson.Serialize(ResinUsageLegacyMapper.FromBoss(true, count, false, false)));

    /// <summary>Actual registered parameter type metadata without constructing a task or consulting application configuration.</summary>
    private static PuloniaTaskDefinition Definition(string type)
    {
        var paramType = type switch
        {
            "solo.auto_domain" => typeof(AutoDomainParam),
            "solo.auto_stygian_onslaught" => typeof(AutoStygianOnslaughtParam),
            "solo.auto_ley_line_outcrop" => typeof(AutoLeyLineOutcropParam),
            _ => typeof(AutoBossParam)
        };
        return PuloniaSoloTestDefinitions.Create(type[5..], "Synthetic resin", paramType,
            new JObject { ["resin_usage"] = JObject.Parse(SoloTaskJson.Serialize(type == "solo.auto_boss" ? ResinCapabilities.Boss.Defaults : ResinCapabilities.Domain.Defaults)) });
    }

    /// <summary>A detached leaf source with stable test identity.</summary>
    private static PuloniaTask TaskFor(string type, JObject values) => new() { Id = "tsk-resin", TaskType = type, Parameters = values };

    /// <summary>Typed group or reference override for the same family.</summary>
    private static PuloniaTaskParameterOverride Override(string type, JObject values) => new() { TaskType = type, Values = values };

    /// <summary>A synthetic plan requiring no external resources or account state.</summary>
    private static PuloniaTaskPlan Plan(JObject values) => new()
    {
        Id = "pln-resin", Name = "Synthetic resin", RootTask = new PuloniaTask { Id = "tsk-root", Children = [TaskFor("solo.auto_boss", values)] }
    };
}
