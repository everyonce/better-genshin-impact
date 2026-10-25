using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Exact v1 JSON grammar shared with the detached Python ledger; no input authority or activation switch.</summary>
internal static partial class AgentStepApplicationWire
{
    /// <summary>The native owner integration is absent; production negotiation must remain unavailable.</summary>
    internal static bool Available => false;
    /// <summary>Reviewed serialized record, channel and combined header limits.</summary>
    internal const int RecordBytes = 8192, Records = 32, BatchRecords = 4, HeaderBytes = 4 * 1024 * 1024;
    /// <summary>One untransformed native interval; aliases are not silently remapped.</summary>
    internal const string Mode = "native-single-50ms-v1";
    /// <summary>Existing aliases collapse to the same VK; v1 authority admits only the canonical spelling.</summary>
    internal static readonly string[] Aliases = ["SHIFT", "CONTROL", "ESC"];

    /// <summary>Reject malformed or uncertain evidence before publishing dependent state.</summary>
    internal static void Require(bool condition, string reason)
    {
        if (!condition) throw new InvalidOperationException(reason);
    }

    /// <summary>Parse bounded JSON without duplicate properties or automatic date interpretation.</summary>
    internal static JObject Parse(string json, int limit)
    {
        Require(Encoding.UTF8.GetByteCount(json) <= limit, "json_capacity");
        // Validate strict JSON syntax first; Json.NET also accepts comments, single quotes and trailing commas.
        using var syntax = System.Text.Json.JsonDocument.Parse(json, new System.Text.Json.JsonDocumentOptions
            { MaxDepth = 16, AllowTrailingCommas = false, CommentHandling = System.Text.Json.JsonCommentHandling.Disallow });
        using var reader = new JsonTextReader(new System.IO.StringReader(json)) { DateParseHandling = DateParseHandling.None, MaxDepth = 16 };
        var value = JObject.Load(reader, new JsonLoadSettings { DuplicatePropertyNameHandling = DuplicatePropertyNameHandling.Error });
        Require(!reader.Read(), "trailing_json");
        return value;
    }

    /// <summary>Detach an ASCII JSON value with sorted object fields and exact integer types.</summary>
    internal static string Freeze(JToken value, int limit)
    {
        JToken Sort(JToken item) => item switch
        {
            JObject obj => new JObject(obj.Properties().OrderBy(p => p.Name, StringComparer.Ordinal).Select(p => new JProperty(p.Name, Sort(p.Value)))),
            JArray array => new JArray(array.Select(Sort)),
            _ => item.DeepClone()
        };
        var text = JsonConvert.SerializeObject(Sort(value), Formatting.None, new JsonSerializerSettings { StringEscapeHandling = StringEscapeHandling.EscapeNonAscii });
        Require(text.All(c => c < 128) && Encoding.ASCII.GetByteCount(text) <= limit, "json_capacity");
        return text;
    }

    /// <summary>Do not allow bool/int or int/float coercion at a detached submission boundary.</summary>
    internal static bool Same(JToken? left, JToken? right)
    {
        if (left is null || right is null || left.Type != right.Type) return false;
        if (left is JObject a && right is JObject b)
            return a.Count == b.Count && a.Properties().All(p => Same(p.Value, b[p.Name]));
        if (left is JArray x && right is JArray y)
            return x.Count == y.Count && x.Zip(y).All(p => Same(p.First, p.Second));
        if (left.Type == JTokenType.Float)
            return BitConverter.DoubleToInt64Bits(left.Value<double>()) == BitConverter.DoubleToInt64Bits(right.Value<double>());
        return JToken.DeepEquals(left, right);
    }

    /// <summary>Every protocol object has a closed field set.</summary>
    internal static void Fields(JObject value, params string[] names) =>
        Require(value.Count == names.Length && names.All(n => value.ContainsKey(n)), "fields");

    /// <summary>Bound exact UTF-8 identifiers; DEL is excluded by the reviewed reservation correction.</summary>
    internal static string Text(JToken? value, int max = 128)
    {
        Require(value?.Type == JTokenType.String, "text");
        var text = (string)value!;
        Require(text.Length > 0 && new UTF8Encoding(false, true).GetByteCount(text) <= max && text.All(c => c >= 32 && c != 127), "text");
        return text;
    }

    /// <summary>Accept only an integer token inside the supplied inclusive range.</summary>
    internal static long Integer(JToken? value, long minimum = 0, long maximum = long.MaxValue)
    {
        Require(value?.Type == JTokenType.Integer, "integer");
        var n = value!.Value<long>(); Require(n >= minimum && n <= maximum, "integer"); return n;
    }

    /// <summary>Require a lowercase SHA256 digest, not a client model label.</summary>
    internal static void Digest(JToken? value)
    {
        var text = Text(value, 64); Require(text.Length == 64 && text.All(c => "0123456789abcdef".Contains(c)), "digest");
    }

    /// <summary>Validate exact keys and reserved combinations using the unchanged controller allowlist.</summary>
    internal static string[] Keys(JToken? value, int maximum, bool policy = true)
    {
        Require(value is JArray, "keys"); var array = (JArray)value!;
        var keys = array.Select(v => Text(v, 16)).ToArray();
        Require(keys.Length <= maximum && keys.Distinct(StringComparer.Ordinal).Count() == keys.Length && keys.All(AgentActionController.AllowedKeys.Contains), "keys");
        Require(!policy || !(keys.Any(k => k is "CONTROL" or "LCONTROL") && keys.Any(k => k is "ESC" or "ESCAPE")), "reserved_hotkey");
        return keys;
    }

    /// <summary>Check immutable server-supplied lease/backend/clock values before constructing an outbox.</summary>
    internal static void Configuration(JObject config)
    {
        Fields(config, "version", "mode", "sessionId", "ownerEpoch", "channelId", "backendId", "backendEpoch", "buildSha256", "clockKind", "sessionOriginTicks", "clockFrequency", "allowedKeys");
        Require((Integer(config["version"]) == 1 && Text(config["mode"]) == Mode || Integer(config["version"]) == 2 && Text(config["mode"]) == QueuedMode) && Text(config["clockKind"]) == "windows_qpc", "version_clock_mode");
        foreach (var name in new[] { "sessionId", "ownerEpoch", "channelId", "backendId", "backendEpoch" }) Text(config[name]);
        Digest(config["buildSha256"]); Integer(config["sessionOriginTicks"], 1); Integer(config["clockFrequency"], 1, 1_000_000_000_000);
        Require(!Keys(config["allowedKeys"], AgentActionController.AllowedKeys.Count, false).Intersect(Aliases).Any(), "alias_authority");
        Freeze(config, 4096);
    }

    /// <summary>Check the complete reviewed binding and exact original wire request without reserializing floating clocks.</summary>
    private static JObject BindingV1(AgentRequest request, JObject config)
    {
        Require(request.StepApplication is JObject && request.RawApplicationRequest is JObject, "binding_required");
        var extension = request.StepApplication!;
        Fields(extension, "version", "submissionJson", "binding"); Require(Integer(extension["version"]) == 1, "extension_version");
        var submission = Text(extension["submissionJson"], 16384);
        Require(submission.All(c => c < 128), "submission_ascii");
        var original = Parse(submission, 16384); var actual = (JObject)request.RawApplicationRequest!.DeepClone();
        actual.Remove("stepApplication"); actual.Remove("stepApplicationsAck");
        Require(Same(original, actual), "submission_wire_mismatch");
        var names = new[] { "version", "command", "sessionId", "ownerEpoch", "goalVersion", "requestId", "frameId", "observedAtMs", "expiresAtMs", "modelId", "steps" };
        Fields(original, original.ContainsKey("startBeforeMs") ? names.Append("startBeforeMs").ToArray() : names);
        Require(Integer(original["version"]) == 1 && Text(original["command"]) == "action", "submission_command");
        Integer(original["goalVersion"]); Integer(original["frameId"]);
        foreach (var name in new[] { "sessionId", "ownerEpoch", "requestId", "modelId" }) Text(original[name]);
        foreach (var name in new[] { "observedAtMs", "expiresAtMs", "startBeforeMs" })
            if (original.TryGetValue(name, out var timestamp))
                Require((timestamp.Type is JTokenType.Integer or JTokenType.Float) && double.IsFinite(timestamp.Value<double>()), "submission_time");
        var bound = extension["binding"] as JObject ?? throw new InvalidOperationException("binding");
        Fields(bound, "identity", "requestId", "submissionSha256", "model", "intervalCount", "stepIndex", "step");
        Digest(bound["submissionSha256"]);
        Require((string?)bound["submissionSha256"] == Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(submission))).ToLowerInvariant(), "submission_digest");
        var identity = (JObject)bound["identity"]!;
        Fields(identity, "sessionId", "ownerEpoch", "sourceEpoch", "modelId", "goalVersion", "controlEpoch", "policyGoalVersion", "readinessEpoch", "frameId");
        foreach (var name in new[] { "sessionId", "ownerEpoch", "sourceEpoch", "modelId" }) Text(identity[name]);
        foreach (var name in new[] { "goalVersion", "controlEpoch", "policyGoalVersion", "readinessEpoch", "frameId" }) Integer(identity[name]);
        foreach (var name in new[] { "sessionId", "ownerEpoch", "goalVersion", "modelId", "frameId" }) Require(Same(identity[name], original[name]), "binding_identity");
        foreach (var name in new[] { "sessionId", "ownerEpoch" }) Require(Same(identity[name], config[name]), "binding_lease");
        Text(bound["requestId"]); Require(Same(bound["requestId"], original["requestId"]), "binding_request");
        Require(Integer(bound["intervalCount"]) == 1 && Integer(bound["stepIndex"]) == 0 && request.Steps.Length == 1, "single_interval");
        var step = (JObject)bound["step"]!; Fields(step, "durationMs", "keys", "mouseDx", "mouseDy");
        Require(Integer(step["durationMs"]) == 50 && Same(original["steps"], new JArray(step.DeepClone())), "transformed_submission");
        var keys = Keys(step["keys"], 6);
        Require(!keys.Intersect(Aliases).Any() && keys.All(k => Keys(config["allowedKeys"], AgentActionController.AllowedKeys.Count, false).Contains(k)), "negotiated_keys");
        Integer(step["mouseDx"], -65535, 65535); Integer(step["mouseDy"], -65535, 65535);
        var model = (JObject)bound["model"]!; Fields(model, "checkpointSha256", "profile", "mapping");
        Digest(model["checkpointSha256"]); Text(model["profile"]); Require(Text(model["mapping"]) == "native-raw-to-one-step-v1", "mapping");
        return Parse(Freeze(bound, 3072), 3072);
    }
}
