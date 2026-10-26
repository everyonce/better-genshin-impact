using System;
using System.IO;
using System.Linq;
using BetterGenshinImpact.Pulonia.Models;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>Only an entirely empty schema-2 state has a lossless, automatic schema-4 mapping.</summary>
internal static class PuloniaTaskStateCompatibility
{
    /// <summary>Return an empty upgraded state, or null for current format; never erase old executable/uncertain data.</summary>
    internal static PuloniaTaskState? ReadEmptyLegacy(string json)
    {
        using var reader = new JsonTextReader(new StringReader(json)) { DateParseHandling = DateParseHandling.None, MaxDepth = 256 };
        var root = JObject.Load(reader, new JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });
        if (reader.Read()) throw new JsonReaderException("Unexpected data after state.json.");
        if (root["schema_version"]?.Type != JTokenType.Integer)
            throw new PuloniaTaskStateCompatibilityException("Missing or invalid schema version.");
        var version = root.Value<int>("schema_version");
        if (version == PuloniaTaskState.CurrentSchemaVersion) return null;
        if (version != 2) throw new PuloniaTaskStateCompatibilityException($"Unsupported schema version {version}.");

        string[] collections = ["pending_requests", "pending_archives", "ledger", "uncertain_operations", "trigger_states"];
        var allowed = collections.Concat(["schema_version", "sequence", "active_run"]).ToHashSet(StringComparer.Ordinal);
        if (root.Properties().Any(property => !allowed.Contains(property.Name))
            || root["sequence"]?.Type != JTokenType.Integer || root.Value<long>("sequence") < 0
            || root["active_run"]?.Type != JTokenType.Null
            || collections.Any(name => root[name] is not JArray { Count: 0 }))
            throw new PuloniaTaskStateCompatibilityException("Schema 2 is not provably empty; no state was converted.");
        // Identity-bearing records, ledger facts and cursors are all absent; only the exact sequence remains.
        return new PuloniaTaskState { Sequence = root.Value<long>("sequence") };
    }
}
