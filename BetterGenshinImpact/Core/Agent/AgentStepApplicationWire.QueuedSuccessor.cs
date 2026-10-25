using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Explicit queued-mode grammar; v1 remains a separate exact branch and neither mode enables itself.</summary>
internal static partial class AgentStepApplicationWire
{
    /// <summary>Only one untransformed 50 ms successor may be admitted ahead of its fixed boundary.</summary>
    internal const string QueuedMode = "native-single-50ms-queued-v2";

    /// <summary>Select the already confirmed version, never a request-provided upgrade.</summary>
    internal static JObject Binding(AgentRequest request, JObject config)
    {
        if (Integer(config["version"]) == 2) return BindingQueued(request, config);
        Require(!request.HasQueueAfter, "queue_version_unavailable");
        return BindingV1(request, config);
    }

    /// <summary>A link identifies exactly one retained immutable application, not model publication.</summary>
    internal static void Link(JToken value, bool allowNull = false)
    {
        if (allowNull && value.Type == JTokenType.Null) return;
        Require(value is JObject, "queue_link");
        var link = (JObject)value;
        Fields(link, "requestId", "applicationSequence", "submissionSha256");
        Text(link["requestId"]); Integer(link["applicationSequence"], 1, Records); Digest(link["submissionSha256"]);
    }

    /// <summary>All transition clock values retain original finite double samples, without inferred simultaneity.</summary>
    internal static void Finite(double value) => Require(double.IsFinite(value), "queued_clock");

    /// <summary>V2 extends only the explicit canonical field sets; complete v1 scalar and call constraints remain.</summary>
    private static JObject BindingQueued(AgentRequest request, JObject config)
    {
        Require(request.StepApplication is JObject && request.RawApplicationRequest is JObject, "binding_required");
        var extension = request.StepApplication!;
        Fields(extension, "version", "submissionJson", "binding"); Require(Integer(extension["version"]) == 2, "extension_version");
        var submission = Text(extension["submissionJson"], 16384);
        Require(submission.All(c => c < 128), "submission_ascii");
        var original = Parse(submission, 16384); var actual = (JObject)request.RawApplicationRequest!.DeepClone();
        actual.Remove("stepApplication"); actual.Remove("stepApplicationsAck");
        Require(Same(original, actual), "submission_wire_mismatch");
        var names = new[] { "version", "command", "sessionId", "ownerEpoch", "goalVersion", "requestId", "frameId", "observedAtMs", "expiresAtMs", "modelId", "steps" };
        Fields(original, names.Concat(new[] { "startBeforeMs", "queueAfter" }).ToArray());
        Require(request.HasQueueAfter && Same(original["queueAfter"], (JToken?)request.QueueAfter ?? JValue.CreateNull()), "queue_presence");
        Link(original["queueAfter"]!, true);
        Require(Integer(original["version"]) == 1 && Text(original["command"]) == "action", "submission_command");
        Integer(original["goalVersion"]); Integer(original["frameId"]);
        foreach (var name in new[] { "sessionId", "ownerEpoch", "requestId", "modelId" }) Text(original[name]);
        foreach (var name in new[] { "observedAtMs", "expiresAtMs", "startBeforeMs" })
            if (original.TryGetValue(name, out var timestamp))
                Require((timestamp.Type is JTokenType.Integer or JTokenType.Float) && double.IsFinite(timestamp.Value<double>()), "submission_time");
        var bound = extension["binding"] as JObject ?? throw new InvalidOperationException("binding");
        Fields(bound, "identity", "requestId", "submissionSha256", "model", "intervalCount", "stepIndex", "step", "queueAfter");
        Require(Same(bound["queueAfter"], original["queueAfter"]), "queue_binding");
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
        // Internal callers cannot detach valid JSON but dispatch a separately mutated DTO.
        Require(request.Version == 1 && request.Command == "action" && request.SessionId == (string?)original["sessionId"]
            && request.OwnerEpoch == (string?)original["ownerEpoch"] && request.RequestId == (string?)original["requestId"]
            && request.ModelId == (string?)original["modelId"] && request.GoalVersion == (long?)original["goalVersion"]
            && request.FrameId == (long?)original["frameId"] && request.ObservedAtMs == (double?)original["observedAtMs"]
            && request.ExpiresAtMs == (double?)original["expiresAtMs"] && request.StartBeforeMs == (double?)original["startBeforeMs"]
            && request.Steps[0].DurationMs == 50 && request.Steps[0].Keys.SequenceEqual(keys)
            && request.Steps[0].MouseDx == (int?)step["mouseDx"] && request.Steps[0].MouseDy == (int?)step["mouseDy"], "queued_dto_mismatch");
        Freeze(actual, 65536);
        return Parse(Freeze(bound, 3072), 3072);
    }
}
