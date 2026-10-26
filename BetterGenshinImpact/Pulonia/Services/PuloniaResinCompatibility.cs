using System;
using System.Linq;
using BetterGenshinImpact.GameTask.Common.Resin;
using BetterGenshinImpact.GameTask.SoloTask;
using BetterGenshinImpact.Pulonia.Models;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>
/// Resolves only the four known legacy resin families after parameter inheritance. Source bags are never modified;
/// unresolved defaults and non-equivalent policies require an explicit user decision before preparation succeeds.
/// </summary>
public static class PuloniaResinCompatibility
{
    /// <summary>Shared names for the legacy per-kind family; values must come from the effective input, never global configuration.</summary>
    private static readonly string[] PerKind = ["specify_resin_use", "original_resin_use_count", "condensed_resin_use_count", "transient_resin_use_count", "fragile_resin_use_count"];

    /// <summary>Domain also had independent attempt and exact-tier limits, which are not interchangeable with reward counts.</summary>
    private static readonly string[] Domain = [.. PerKind, "original_resin20_use_count", "original_resin40_use_count", "domain_round_num", "resin_priority_list"];

    /// <summary>The old priority list had no execution consumer; originals remain in the plan/preset source bags.</summary>
    private static readonly string[] Stygian = [.. PerKind, "resin_priority_list"];

    /// <summary>Only these old Boss fields participate in resin resolution.</summary>
    private static readonly string[] Boss = ["specify_run_count", "run_count", "use_transient_resin", "use_fragile_resin"];

    /// <summary>The old synthesizer flag had no execution consumer; it is not a request to add an operation.</summary>
    private static readonly string[] LeyLine = ["is_resin_exhaustion_mode", "open_mode_count_min", "count", "use_transient_resin", "use_fragile_resin", "is_go_to_synthesizer"];

    /// <summary>Allow legacy public fields only for their exact task family, never arbitrary JSON aliases.</summary>
    public static bool IsLegacyField(string taskType, string name) => Fields(taskType).Contains(name, StringComparer.Ordinal);

    /// <summary>
    /// Normalize the folded base and active weekday bags. Each sparse day is overlaid on the original folded fields,
    /// then mapped once; converting the base first would erase the sibling legacy fields the day inherits.
    /// On refusal return the complete original effective bag and an English diagnostic for nonthrowing preview.
    /// </summary>
    public static JObject Resolve(string taskType, JObject effective, bool userProvidedResin,
        out string? diagnostic, out bool baseConverted)
    {
        diagnostic = null;
        baseConverted = false;
        if (Fields(taskType).Length == 0) return (JObject)effective.DeepClone();
        try
        {
            var result = NormalizeBag(taskType, effective, userProvidedResin, out baseConverted);
            if (IsFalse(effective["weekday_overrides_enabled"])
                || effective["weekday_overrides"] is not JObject weekly)
                return result;

            var normalizedDays = (JObject)weekly.DeepClone();
            for (var day = 0; day < 7; day++)
            {
                var key = day.ToString(System.Globalization.CultureInfo.InvariantCulture);
                if (weekly[key] is not JObject overlay || IsFalse(overlay["enabled"])
                    || !overlay.Properties().Any(p => IsLegacyField(taskType, p.Name)))
                    continue;
                try
                {
                    var folded = Overlay(effective, overlay);
                    var normalized = NormalizeBag(taskType, folded,
                        userProvidedResin || overlay.ContainsKey("resin_usage"), out _);
                    var projected = (JObject)overlay.DeepClone();
                    RemoveLegacy(taskType, projected);
                    if (normalized.TryGetValue("resin_usage", out var usage))
                        projected["resin_usage"] = usage.DeepClone();
                    normalizedDays[key] = projected;
                }
                catch (PuloniaTaskValidationException ex)
                {
                    throw Refuse(taskType, $"weekday_overrides[{key}]: {ex.Message}");
                }
            }
            result["weekday_overrides"] = normalizedDays;
            return result;
        }
        catch (PuloniaTaskValidationException ex)
        {
            diagnostic = ex.Message;
            baseConverted = false;
            return (JObject)effective.DeepClone();
        }
    }

    /// <summary>Use the same top-level weekday precedence in preparation and execution; enabled is scheduling metadata.</summary>
    public static JObject Overlay(JObject effective, JObject day)
    {
        var result = (JObject)effective.DeepClone();
        foreach (var field in day.Properties().Where(p => p.Name != "enabled"))
            result[field.Name] = field.Value.DeepClone();
        return result;
    }

    /// <summary>Execution may consume newly prepared values but must not convert an immutable historical snapshot in place.</summary>
    public static void RequirePrepared(string taskType, JObject parameters)
    {
        if (parameters.Properties().Any(p => IsLegacyField(taskType, p.Name)))
            throw Refuse(taskType, "Legacy resin fields in a prepared snapshot require fresh preparation; historical snapshots are not converted.");
    }

    /// <summary>Exact family lookup keeps similarly named parameters of scripts and other tasks untouched.</summary>
    private static string[] Fields(string taskType) => taskType switch
    {
        "solo.auto_domain" => Domain,
        "solo.auto_stygian_onslaught" => Stygian,
        "solo.auto_boss" => Boss,
        "solo.auto_ley_line_outcrop" => LeyLine,
        _ => []
    };

    /// <summary>Remove only recognized obsolete execution keys from the detached effective projection.</summary>
    private static void RemoveLegacy(string taskType, JObject values)
    {
        foreach (var name in Fields(taskType)) values.Remove(name);
    }

    /// <summary>Map one complete effective family once, after strict scalar and semantic checks.</summary>
    private static JObject NormalizeBag(string taskType, JObject values, bool userProvidedResin, out bool converted)
    {
        converted = false;
        var result = (JObject)values.DeepClone();
        if (!values.Properties().Any(p => IsLegacyField(taskType, p.Name))) return result;

        // 9999 remains finite: old/current constructors assign it and both task loops still enforce DomainRoundNum.
        // Removing only an explicit 9999 therefore retains the same bound through the current deserializer's constructor.
        // Any other explicit limit is independent of resin policy and cannot be silently replaced by that constructor default.
        if (taskType == "solo.auto_domain" && values.ContainsKey("domain_round_num")
            && Integer(taskType, values, "domain_round_num", 0, int.MaxValue) != 9999)
            throw Refuse(taskType, "domain_round_num is an independent attempt limit; its explicit value cannot be discarded or converted into a reward count. Review this constraint before removing the old field.");

        // Presence, including explicit null, wins. Capability defaults alone do not constitute a user choice.
        RemoveLegacy(taskType, result);
        if (userProvidedResin) return result;
        var active = Fields(taskType).Where(name => name is not "domain_round_num" and not "resin_priority_list" and not "is_go_to_synthesizer");
        if (!active.Any(values.ContainsKey)) return result;

        ResinUsage usage;
        if (taskType is "solo.auto_domain" or "solo.auto_stygian_onslaught")
        {
            var specified = Boolean(taskType, values, "specify_resin_use");
            var original = Count(taskType, values, "original_resin_use_count");
            var condensed = Count(taskType, values, "condensed_resin_use_count");
            var transient = Count(taskType, values, "transient_resin_use_count");
            var fragile = Count(taskType, values, "fragile_resin_use_count");
            if (taskType == "solo.auto_domain")
            {
                var original20 = Count(taskType, values, "original_resin20_use_count");
                var original40 = Count(taskType, values, "original_resin40_use_count");
                // Old 40 meant exactly 40, whereas Prefer40 can fall back. Mixed quotas also lose independent counters.
                if (original40 != 0 || (original != 0 && original20 != 0))
                    throw Refuse(taskType, "Exact 40-resin or mixed original-resin quotas have no lossless current tier policy. Choose resin_usage explicitly.");
                usage = ResinUsageLegacyMapper.FromDomain(specified, original, condensed, transient, fragile,
                    original20, original40, out var warning);
                if (warning is not null) throw Refuse(taskType, "The legacy Domain tiers cannot be represented without losing separate quotas.");
            }
            else usage = ResinUsageLegacyMapper.FromStygian(specified, original, condensed, transient, fragile);
            if (specified && usage.Counts.Original + condensed + transient + fragile == 0)
                throw Refuse(taskType, "A specified legacy resin policy must retain at least one positive claim count.");
        }
        else if (taskType == "solo.auto_boss")
        {
            var specified = Boolean(taskType, values, "specify_run_count");
            var count = Count(taskType, values, "run_count");
            var transient = Boolean(taskType, values, "use_transient_resin");
            var fragile = Boolean(taskType, values, "use_fragile_resin");
            if (!specified && (transient || fragile))
                throw Refuse(taskType, "Legacy Boss exhaustion with resin supplements was invalid; conversion cannot silently enable it.");
            if (specified && count == 0) throw Refuse(taskType, "A specified legacy Boss claim count must be positive.");
            usage = ResinUsageLegacyMapper.FromBoss(specified, count, transient, fragile);
        }
        else
        {
            var exhaustion = Boolean(taskType, values, "is_resin_exhaustion_mode");
            var minimum = Boolean(taskType, values, "open_mode_count_min");
            var count = Count(taskType, values, "count");
            var transient = Boolean(taskType, values, "use_transient_resin");
            var fragile = Boolean(taskType, values, "use_fragile_resin");
            if ((!exhaustion || minimum) && count == 0)
                throw Refuse(taskType, "The effective legacy Ley Line claim count must be positive.");
            usage = ResinUsageLegacyMapper.FromLeyLine(exhaustion, minimum, count, transient, fragile);
        }
        result["resin_usage"] = JObject.Parse(SoloTaskJson.Serialize(usage));
        converted = true;
        return result;
    }

    /// <summary>A missing field is an unresolved old default, not false, zero, or a current capability default.</summary>
    private static JToken Required(string taskType, JObject values, string name)
        => values.TryGetValue(name, out var value) ? value
            : throw Refuse(taskType, $"Missing legacy field '{name}'; its old effective default is unresolved. Supply the complete legacy settings or choose resin_usage explicitly.");

    /// <summary>Reject null, strings and numeric Boolean coercion while preserving an explicit false.</summary>
    private static bool Boolean(string taskType, JObject values, string name)
    {
        var value = Required(taskType, values, name);
        return value.Type == JTokenType.Boolean ? value.Value<bool>()
            : throw Refuse(taskType, $"Legacy field '{name}' must be a Boolean; null is not an absent value.");
    }

    /// <summary>Keep zero distinct from absence, reject overflow and never clamp or round.</summary>
    private static int Integer(string taskType, JObject values, string name, int minimum, int maximum)
    {
        var value = Required(taskType, values, name);
        if (value.Type != JTokenType.Integer || !int.TryParse(value.ToString(),
                System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var count)
            || count < minimum || count > maximum)
            throw Refuse(taskType, $"Legacy field '{name}' must be an integer from {minimum} through {maximum}; null is not an absent value.");
        return count;
    }

    /// <summary>The compatible current count domain is bounded even for retained inactive legacy counts.</summary>
    private static int Count(string taskType, JObject values, string name) => Integer(taskType, values, name, 0, 999);

    /// <summary>Only an actual Boolean false disables a projection; malformed scheduling fields remain for existing validation.</summary>
    private static bool IsFalse(JToken? value) => value?.Type == JTokenType.Boolean && !value.Value<bool>();

    /// <summary>Compatibility diagnostics remain English and retain the task-family context without leaking source bags.</summary>
    private static PuloniaTaskValidationException Refuse(string taskType, string reason)
        => new(taskType, $"Resin compatibility: {reason}");
}
