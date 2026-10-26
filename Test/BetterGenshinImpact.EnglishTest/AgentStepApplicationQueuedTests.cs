using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Prepared in-memory v2 producer tests. No stream, GameRuntime, native backend or numerical model is constructed.</summary>
public sealed class AgentStepApplicationQueuedTests
{
    /// <summary>Negotiation stays unavailable, and omission/null preserve their distinct meanings.</summary>
    [Fact]
    public void DisabledCapabilityAndQueuePresenceRemainExplicit()
    {
        Assert.False(AgentStepApplicationWire.Available);
        var omitted = JsonConvert.DeserializeObject<AgentRequest>("{}")!;
        var explicitNull = JsonConvert.DeserializeObject<AgentRequest>("{\"queueAfter\":null}")!;
        Assert.False(omitted.HasQueueAfter); Assert.True(explicitNull.HasQueueAfter);
        Assert.False((explicitNull with { RequestId = "copy" }).QueueAfter is not null);
        Assert.DoesNotContain("QueueAfter", JsonConvert.SerializeObject(omitted), StringComparison.Ordinal);
        Assert.Contains("QueueAfter", JsonConvert.SerializeObject(explicitNull), StringComparison.Ordinal);
    }

    /// <summary>The separately configured v1 branch neither queues nor accepts any v2 marker.</summary>
    [Fact]
    public void V1CannotUpgradeFromAnAction()
    {
        var f = new Fixture(version: 1); var request = f.Request("p", null);
        Assert.Equal("queue_version_unavailable", f.Controller.Submit(request, f.Now));
        Assert.Empty(f.Applications()); Assert.Equal(0, f.Input.HeldEvaluations);
    }

    /// <summary>A complete empty evaluation creates authority without inventing a low-level call.</summary>
    [Fact]
    public void NoopInitialApplicationKeepsFixedSchedule()
    {
        var f = new Fixture(); var p = f.Request("p", null, keys: []);
        Assert.Null(f.Controller.Submit(p, 130)); f.Controller.Tick(130);
        var row = Assert.Single(f.Applications()); Assert.Empty((JArray)row["calls"]!);
        Assert.Equal("returned", (string?)row["heldEvaluation"]);
        Assert.Equal(180.0, (double)f.Controller.QueuedAdmission("p")!["scheduledEndMs"]!);
    }

    /// <summary>Admission before P's complete software application is not a valid chain link.</summary>
    [Fact]
    public void QueueRequiresAppliedPredecessor()
    {
        var f = new Fixture(); Assert.Null(f.Controller.Submit(f.Request("p", null), 130));
        f.Now = 131;
        Assert.Equal("queued_predecessor_not_ready", f.Controller.Submit(f.Request("q", Fixture.Link("p", 1, new string('a', 64))), 131));
        Assert.Equal(0, f.Input.HeldEvaluations);
    }

    /// <summary>Exactly one successor is retained; a third request cannot overwrite either original owner.</summary>
    [Fact]
    public void QueuedAdmissionDoesNotReplacePOrAcceptAThird()
    {
        var f = new Fixture(); f.StartP(); var q = f.Request("q", f.PLink());
        f.Now = 140; Assert.Null(f.Controller.Submit(q, 140));
        var a = f.Controller.QueuedAdmission("q")!;
        Assert.Equal("queued", (string?)a["state"]); Assert.Equal(140.0, (double)a["admittedAtMs"]!);
        Assert.Equal(180.0, (double)a["scheduledStartMs"]!); Assert.Equal(230.0, (double)a["scheduledEndMs"]!);
        Assert.Equal("p", Field<AgentRequest>(f.Controller, "_active")!.RequestId);
        Assert.Equal("queued_slot_occupied", f.Controller.Submit(f.Request("r", f.PLink()), 140));
        Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>A caller mutation after acceptance cannot change Q's detached keys or predecessor link.</summary>
    [Fact]
    public void QueuedOperandsAreDetached()
    {
        var f = new Fixture(); f.StartP(); var q = f.QueueQ();
        q.Steps[0].Keys[0] = "A"; q.QueueAfter!["requestId"] = "foreign";
        f.At(180); Assert.Equal(new[] { "W" }, f.Input.Keys);
        Assert.Equal("p", (string?)f.Applications()[1]["binding"]!["queueAfter"]!["requestId"]);
    }

    /// <summary>At B, inherited keys need another complete evaluation, never an artificial up/down pair or release.</summary>
    [Fact]
    public void HandoffAtomicallyLinksQAndKeepsInheritedKeys()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); var calls = f.Input.BackendCalls;
        f.At(180); var rows = f.Applications(); var terminal = Assert.Single(f.Terminals());
        Assert.Equal(2, rows.Count); Assert.Equal(2, f.Input.HeldEvaluations); Assert.Equal(calls, f.Input.BackendCalls);
        Assert.Equal(0, f.Input.Releases); Assert.Empty((JArray)rows[1]["calls"]!);
        Assert.Equal("horizon_handoff", (string?)terminal["reason"]); Assert.Equal("not_requested", (string?)terminal["releaseOutcome"]);
        Assert.Equal(2L, (long)terminal["transition"]!["successor"]!["applicationSequence"]!);
        Assert.True((long)terminal["publicationTicks"]! >= (long)rows[1]["publicationTicks"]!);
        Assert.Equal(rows[1]["callsReturnedTicks"], terminal["transition"]!["successorCallsReturnedTicks"]);
        Assert.Equal("horizon_handoff", Assert.Single(f.Controller.DrainReceipts()).Reason);
        f.At(230); Assert.Equal(1, f.Input.Releases); Assert.True(f.Batch()["closedForSubmission"]!.Value<bool>());
        Assert.False(f.Batch()["authorityLost"]!.Value<bool>());
    }

    /// <summary>P's consumed first-start deadline must not truncate the active hold or reject its valid Q.</summary>
    [Fact]
    public void ConsumedPStartDeadlineIsNotRechecked()
    {
        var f = new Fixture(); f.StartP(startBefore: 150); f.QueueQ(); f.At(180);
        Assert.Equal("horizon_handoff", (string?)Assert.Single(f.Terminals())["reason"]);
    }

    /// <summary>One late tick preserves B+50, while a fully missed successor interval can never dispatch.</summary>
    [Theory]
    [InlineData(185.0, true)]
    [InlineData(230.0, false)]
    [InlineData(231.0, false)]
    public void LateTickNeverRenewsTheScheduledEnd(double now, bool applies)
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.At(now);
        Assert.Equal(applies ? 2 : 1, f.Input.HeldEvaluations);
        if (applies) Assert.Equal(230.0, Field<double>(f.Controller, "_nextStepAt"));
        else Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>Q first-start, consumed source and P expiry boundaries remain separate strict checks.</summary>
    [Theory]
    [InlineData(180.0, 250.0)]
    [InlineData(200.0, 229.0)]
    [InlineData(201.0, 250.0)]
    [InlineData(200.0, 251.0)]
    public void InvalidQueueDeadlinesAreRejectedBeforeAnyQCall(double first, double expiry)
    {
        var f = new Fixture(); f.StartP(); f.Now = 140;
        Assert.NotNull(f.Controller.Submit(f.Request("q", f.PLink(), startBefore: first, expires: expiry), 140));
        Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>The final post-reservation clock can cancel Q without calling its backend or extending P.</summary>
    [Fact]
    public void ReservationDelayCannotSpendQStartDeadline()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); var reads = 0;
        f.ClockOverride = () => ++reads == 1 ? 180 : 200; f.Now = 180;
        f.Controller.Tick(180); Assert.Equal(1, f.Input.HeldEvaluations);
        Assert.True(f.Batch()["authorityLost"]!.Value<bool>()); Assert.Equal(1, (int)f.Batch()["unpublished"]!);
        Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>No admitted queue is waited for after B; no-queue closure is an ordinary terminal.</summary>
    [Fact]
    public void MissingOrLateQueueClosesWithoutExtension()
    {
        var f = new Fixture(); f.StartP(); f.Now = 180;
        Assert.Equal("queued_predecessor_not_ready", f.Controller.Submit(f.Request("q", f.PLink()), 180));
        f.Controller.Tick(180); Assert.Equal("horizon_complete", (string?)Assert.Single(f.Terminals())["reason"]);
        Assert.Equal(JTokenType.Null, Assert.Single(f.Terminals())["transition"]!.Type);
        Assert.Equal("queued_closed", f.Controller.Submit(f.Request("r", null), 180));
    }

    /// <summary>A Q call returning after its fixed end is retained but cannot produce a positive handoff.</summary>
    [Fact]
    public void SlowReturnedQIsCancelledWithActualCallsRetained()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.Input.AfterHeld = () => f.Now = 230;
        f.At(180); Assert.Equal(2, f.Applications().Count); Assert.True(f.Batch()["authorityLost"]!.Value<bool>());
        Assert.All(f.Terminals(), t => Assert.Equal(JTokenType.Null, t["transition"]!.Type));
        Assert.Equal(1, f.Input.Releases);
        Assert.Single(f.Controller.DrainReceipts().Single(r => r.RequestId == "q").AppliedSteps);
    }

    /// <summary>Actual Q backend telemetry is labeled Q even though P stays active until paired retention.</summary>
    [Fact]
    public void QTelemetryUsesQOriginAndCallsOnlyOnce()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(keys: ["A"]); f.At(180);
        var events = f.Controller.GetExecutionContextSnapshot().Events;
        var q = events.Where(e => e.RequestId == "q").ToArray();
        Assert.Equal(4, q.Length); Assert.All(q, e => Assert.Equal(0, e.StepIndex));
        Assert.Equal(3, f.Input.BackendCalls); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>Partial Q and cleanup failures keep the backend error primary and make only one aggregate release attempt.</summary>
    [Fact]
    public void FailedQAndCleanupRetainBothErrorsWithoutRetry()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(dx: 1); f.Input.ThrowMouse = true; f.Input.ThrowRelease = true;
        f.Now = 180; var error = Assert.Throws<InvalidOperationException>(() => f.Controller.Tick(180));
        Assert.Same(f.Input.MouseError, error); Assert.Equal(1, f.Input.Releases);
        Assert.Same(f.Input.ReleaseError, Field<Exception>(f.Controller, "_queuedCleanupFailure"));
        Assert.Equal("partial_failed", (string?)f.Applications()[1]["outcome"]);
        Assert.True(f.Batch()["authorityLost"]!.Value<bool>()); Assert.All(f.Terminals(), t => Assert.Equal(JTokenType.Null, t["transition"]!.Type));
        f.Controller.Stop(181, "stop"); Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>A failed paired-publication clock preserves Q's returned proof, pending slot, owners, and primary error.</summary>
    [Fact]
    public void PairClockFailureCannotPublishHalfAHandoff()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.Input.AfterEnd = () => f.ThrowAfterQpcReads = 2;
        f.Now = 180; Assert.Throws<InvalidOperationException>(() => f.Controller.Tick(180));
        Assert.Single(f.Applications()); Assert.True(f.Batch()["authorityLost"]!.Value<bool>());
        Assert.Equal(1, (int)f.Batch()["unpublished"]!); Assert.Equal(1, f.Input.Releases);
        Assert.NotNull(Field<AgentStepApplicationEvidence>(f.Controller, "_queuedFailedProof"));
        Assert.NotNull(Field<JObject>(f.Controller, "_queuedFailedEvidence"));
        Assert.DoesNotContain(f.Terminals(), t => (string?)t["reason"] == "horizon_handoff");
    }

    /// <summary>Readiness loss terminates both identities without dispatching Q or renewing any source clock.</summary>
    [Fact]
    public void ReadinessLossCancelsQueuedSuccessor()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.Controller.InvalidateWorld(150, "world_blocked");
        Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(1, f.Input.Releases);
        Assert.Equal(2, f.Terminals().Count); Assert.Empty((JArray)f.Terminals().Single(t => (string?)t["binding"]!["requestId"] == "q")["applicationSequences"]!);
    }

    /// <summary>A stop sampled before queued admission cannot timestamp either terminal before its owner existed.</summary>
    [Fact]
    public void QueuedStopRefreshesStaleCallerTime()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.Now = 150;
        f.Controller.Stop(125, "client_stop");
        var receipts = f.Controller.DrainReceipts();
        Assert.Equal(2, receipts.Length);
        Assert.All(receipts, receipt => Assert.Equal(150, receipt.EndedAtMs));
        Assert.Single(receipts.Single(receipt => receipt.RequestId == "p").AppliedSteps);
        Assert.Empty(receipts.Single(receipt => receipt.RequestId == "q").AppliedSteps);
        Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>An earlier ReleaseAll latches unknown software state and prevents first v2 configuration.</summary>
    [Fact]
    public void FirstEnableCannotLaunderReleaseUncertainty()
    {
        var f = new Fixture(configure: false); f.Input.ReleaseAll();
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureStepApplications(Config(), f.Qpc));
        Assert.Equal(0, f.Input.HeldEvaluations);
    }

    /// <summary>Every chain identity except frame ID and every original model contract field is fixed.</summary>
    [Theory]
    [InlineData("controlEpoch")]
    [InlineData("modelId")]
    [InlineData("sourceEpoch")]
    public void QueueIdentityDriftIsRejected(string field)
    {
        var f = new Fixture(); f.StartP(); var q = f.Request("q", f.PLink());
        q.StepApplication!["binding"]!["identity"]![field] = field == "controlEpoch" ? new JValue(2) : new JValue("changed");
        f.Now = 140; Assert.NotNull(f.Controller.Submit(q, 140)); Assert.Equal(1, f.Input.HeldEvaluations);
    }

    /// <summary>Queue links cannot change scalar types or refer to another request/sequence/digest.</summary>
    [Theory]
    [InlineData("requestId")]
    [InlineData("applicationSequence")]
    [InlineData("submissionSha256")]
    public void WrongQueueLinkIsRejected(string field)
    {
        var f = new Fixture(); f.StartP(); var link = f.PLink();
        link[field] = field == "applicationSequence" ? new JValue(1.0) : new JValue("wrong");
        f.Now = 140; Assert.NotNull(f.Controller.Submit(f.Request("q", link), 140));
        Assert.Equal(1, f.Input.HeldEvaluations);
    }

    /// <summary>ACKed application bytes may be removed while their immutable complete queue-link facts remain.</summary>
    [Fact]
    public void QueueCanReferenceAnAlreadyAckedCompleteApplication()
    {
        var f = new Fixture(); f.StartP(); var link = f.PLink();
        f.Controller.AcknowledgeStepApplications(Ack(1)); Assert.Empty(f.Applications());
        f.Now = 140; Assert.Null(f.Controller.Submit(f.Request("q", link), 140)); f.At(180);
        Assert.Single(f.Applications()); Assert.Equal("horizon_handoff", (string?)Assert.Single(f.Terminals())["reason"]);
    }

    /// <summary>A malformed terminal ACK cannot delete an otherwise valid application prefix.</summary>
    [Fact]
    public void AckIsAtomicAndCannotPreackAnUnpublishedTerminal()
    {
        var f = new Fixture(); f.StartP(); var before = AgentStepApplicationWire.Freeze(f.Controller.StepApplicationExtensions()!, 65536);
        Assert.Throws<InvalidOperationException>(() => f.Controller.AcknowledgeStepApplications(Ack(1, "p")));
        Assert.Equal(before, AgentStepApplicationWire.Freeze(f.Controller.StepApplicationExtensions()!, 65536));
        f.QueueQ(); f.At(180); _ = f.Terminals();
        Assert.Throws<InvalidOperationException>(() => f.Controller.AcknowledgeStepApplications(Ack(1, "p")));
        f.Controller.AcknowledgeStepApplications(Ack(2, "p")); f.Controller.AcknowledgeStepApplications(Ack(2, "p"));
        Assert.Empty(f.Applications()); Assert.Empty(f.Terminals());
    }

    /// <summary>Long identifiers are rejected by pre-call reservation rather than growing protocol caps.</summary>
    [Fact]
    public void OversizedBindingCannotReachBackendCalls()
    {
        var f = new Fixture(); var p = f.Request("p", null);
        p.StepApplication!["binding"]!["model"]!["profile"] = new string('\u0080', 65);
        Assert.NotNull(f.Controller.Submit(p, 130)); Assert.Equal(0, f.Input.HeldEvaluations);
    }

    /// <summary>Six actual controller applications cannot expose a terminal whose Q lies beyond the four-row batch.</summary>
    [Fact]
    public void TerminalWindowWaitsForItsSuccessorApplication()
    {
        var f = new Fixture(); f.StartP(); var previous = "p";
        var box = Field<AgentStepApplicationOutbox>(f.Controller, "_stepApplications")!;
        for (var i = 1; i <= 5; i++)
        {
            var boundary = 130 + i * 50; f.Refresh(boundary - 20);
            var next = "q" + i; Assert.Null(f.Controller.Submit(f.Request(next, box.CompleteLink(previous)), f.Now));
            f.At(boundary); previous = next;
        }
        Assert.Equal(4, f.Applications().Count); Assert.Equal(3, f.Terminals().Count);
        Assert.All(f.Terminals(), t => Assert.True((long)t["transition"]!["successor"]!["applicationSequence"]! <= 4));
        var terminalIds = f.Terminals().Select(t => (string)t["binding"]!["requestId"]!).ToArray();
        f.Controller.AcknowledgeStepApplications(Ack(4, terminalIds));
        Assert.Equal(2, f.Applications().Count); Assert.Equal(2, f.Terminals().Count);
        Assert.All(f.Terminals(), t => Assert.InRange((long)t["transition"]!["successor"]!["applicationSequence"]!, 5, 6));
    }

    /// <summary>Backend drift is detected by the real reservation before Q performs a held-state evaluation.</summary>
    [Fact]
    public void BackendDriftCannotDispatchQueuedWork()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.Input.Backend = "drift"; f.Now = 180;
        Assert.Throws<InvalidOperationException>(() => f.Controller.Tick(180));
        Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(1, f.Input.Releases);
        Assert.True(f.Batch()["authorityLost"]!.Value<bool>());
    }

    /// <summary>Even a correctly linked envelope cannot dispatch a different detached DTO operand.</summary>
    [Fact]
    public void ExactWireAndDtoMustMatch()
    {
        var f = new Fixture(); var request = f.Request("p", null) with { Steps = [new() { DurationMs = 50, Keys = ["A"] }] };
        Assert.NotNull(f.Controller.Submit(request, 130)); Assert.Equal(0, f.Input.HeldEvaluations);
    }

    /// <summary>Inspect a retained owner only, without invoking any private execution method.</summary>
    private static T? Field<T>(object owner, string name) => (T?)owner.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(owner);

    /// <summary>Idle observation ticks do not destroy the known-empty first-enable state.</summary>
    [Fact]
    public void IdleTicksBeforeSubmissionDoNotReleaseOrRearm()
    {
        var f = new Fixture(); f.At(131); f.At(132);
        Assert.Equal(0, f.Input.Releases); Assert.True((bool)f.Input.ApplicationTrackedState["complete"]!);
        Assert.False((bool)f.Batch()["closedForSubmission"]!);
        f.StartP(); Assert.Single(f.Applications());
    }

    /// <summary>Even locally known held keys are not a fresh known-empty activation state.</summary>
    [Fact]
    public void FirstEnableRejectsKnownHeldState()
    {
        var f = new Fixture(configure: false); f.Input.Keys = ["W"];
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureStepApplications(Config(), f.Qpc));
        Assert.Equal(0, f.Input.Releases); Assert.Equal(new[] { "W" }, f.Input.Keys);
    }

    /// <summary>Existing byte caps remain exact and count escaped ASCII serialization before publication.</summary>
    [Theory]
    [InlineData(8192)] [InlineData(4096)] [InlineData(65536)] [InlineData(4194304)]
    public void ExactSerializationCapRejectsOneAdditionalByte(int limit)
    {
        var value = new JObject { ["x"] = new string('x', limit - 8) };
        Assert.Equal(limit, AgentStepApplicationWire.Freeze(value, limit).Length);
        value["x"] = (string)value["x"]! + "x";
        Assert.Throws<InvalidOperationException>(() => AgentStepApplicationWire.Freeze(value, limit));
    }

    /// <summary>Only one original 50 ms interval is eligible; DTO changes never normalize into that contract.</summary>
    [Theory]
    [InlineData(49)] [InlineData(51)] [InlineData(100)]
    public void NonNativeDurationsFailBeforeCalls(int duration)
    {
        var f = new Fixture(); var request = f.Request("p", null);
        request = request with { Steps = [request.Steps[0] with { DurationMs = duration }] };
        Assert.NotNull(f.Controller.Submit(request, f.Now)); Assert.Equal(0, f.Input.HeldEvaluations);
    }

    /// <summary>The boundary is fixed and a sub-boundary tick cannot apply an already queued request.</summary>
    [Fact]
    public void JustBeforeBoundaryKeepsOnlyPThenExactBoundaryAppliesQ()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.At(179.999);
        Assert.Single(f.Applications()); Assert.Empty(f.Terminals()); f.At(180);
        Assert.Equal(2, f.Applications().Count); Assert.Single(f.Terminals());
    }

    /// <summary>Changed held keys and mouse retain the exact old-up/new-down/mouse call order once.</summary>
    [Fact]
    public void ChangedKeySetAndMouseKeepOriginalCallOrder()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(["A"], 2); f.At(180);
        var calls = (JArray)f.Applications()[1]["calls"]!;
        Assert.Equal(new[] { "keyUp", "keyDown", "mouseMove" }, calls.Select(v => (string)v["operation"]!));
        Assert.Equal(new[] { "W", "A", null }, calls.Select(v => (string?)v["key"]));
        Assert.Equal(4, f.Input.BackendCalls); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>Each actual evaluation failure is retained, closes submission, and never retries cleanup.</summary>
    [Theory]
    [InlineData("keyUp")] [InlineData("keyDown")] [InlineData("held")] [InlineData("end")]
    public void DispatchFailuresRetainTheOriginalErrorAndOneCleanup(string point)
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(["A"]);
        f.Input.FailAt = point;
        Assert.Same(f.Input.EvaluationError, Assert.Throws<InvalidOperationException>(() => f.At(180)));
        Assert.Equal(1, f.Input.Releases); Assert.True((bool)f.Batch()["authorityLost"]!);
        Assert.True((bool)f.Batch()["closedForSubmission"]!); Assert.Empty(f.Terminals().Where(v => (string?)v["reason"] == "horizon_handoff"));
        f.At(181); f.Controller.Stop(182, "test_stop"); Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>Closed fields and typed queue sequence are checked before the controller may own a request.</summary>
    [Fact]
    public void StrictParserRejectsDuplicateQueueAndBindingFields()
    {
        Assert.Throws<Newtonsoft.Json.JsonReaderException>(() => AgentStepApplicationWire.Parse("{\"queueAfter\":null,\"queueAfter\":null}", 1024));
        var f = new Fixture(); var request = f.Request("p", null);
        request.StepApplication!["binding"]!["unexpected"] = true;
        Assert.NotNull(f.Controller.Submit(request, f.Now)); Assert.Equal(0, f.Input.BackendCalls);
    }

    /// <summary>Shared canonical request bytes are admitted without normalizing their link or numerical types.</summary>
    [Fact]
    public void SharedCanonicalRequestsDriveTheSameFixedHandoff()
    {
        var f = new Fixture();
        var p = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.RequestP, 65536);
        var q = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.RequestQ, 65536);
        Assert.Null(f.Controller.Submit(p.ToObject<AgentRequest>()! with { RawApplicationRequest = p }, 130)); f.At(130);
        f.Now = 140; Assert.Null(f.Controller.Submit(q.ToObject<AgentRequest>()! with { RawApplicationRequest = q }, 140)); f.At(180);
        Assert.Equal(2, f.Applications().Count); Assert.Equal("horizon_handoff", (string?)Assert.Single(f.Terminals())["reason"]);
    }

    /// <summary>Bind the scalar capacity witness to the actual conservative production reservation method.</summary>
    [Fact]
    public void ActualReservationMatchesThe8192And8193ScalarWitness()
    {
        var row = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.Reservation, 8192);
        var method = typeof(AgentStepApplicationOutbox).GetMethod("ReservationSize", BindingFlags.Static | BindingFlags.NonPublic)!;
        var bound = (JObject)row["binding"]!; var config = Config();
        foreach (var property in ((JObject)row["clock"]!).Properties()) config[property.Name] = property.Value.DeepClone();
        config["channelId"] = row["channelId"]!.DeepClone(); config["backendEpoch"] = row["backendEpoch"]!.DeepClone();
        Assert.Equal(8192, (int)method.Invoke(null, [bound, config, (JObject)row["trackedBefore"]!, 32L])!);
        bound = (JObject)AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.OverflowQ, 65536)["stepApplication"]!["binding"]!;
        Assert.Equal(8193, (int)method.Invoke(null, [bound, config, (JObject)row["trackedBefore"]!, 32L])!);
    }

    /// <summary>Actual bounded configuration/bindings reach the reservation boundary without violating text grammar.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void ValidBoundedIdentifiersExerciseThePredispatchReservation(bool overflow)
    {
        var config = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.ReservationConfig, 4096);
        var f = new Fixture(configuration: config);
        var p = AgentStepApplicationWire.Parse(overflow ? AgentStepApplicationQueuedWireFixtures.OverflowP : AgentStepApplicationQueuedWireFixtures.ReservationP, 65536);
        var q = AgentStepApplicationWire.Parse(overflow ? AgentStepApplicationQueuedWireFixtures.OverflowQ : AgentStepApplicationQueuedWireFixtures.ReservationQ, 65536);
        Assert.Null(f.Controller.Submit(p.ToObject<AgentRequest>()! with { RawApplicationRequest = p }, 130)); f.At(130);
        f.Now = 140; var reason = f.Controller.Submit(q.ToObject<AgentRequest>()! with { RawApplicationRequest = q }, 140);
        if (overflow) Assert.NotNull(reason); else Assert.Null(reason);
        Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>A snapshot made during calls contains a pending Q and cannot expose a successful P terminal early.</summary>
    [Fact]
    public void SnapshotDuringQCallsCannotSeeHalfAHandoff()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); JObject? inside = null;
        f.Input.AfterHeld = () => inside = f.Controller.StepApplicationExtensions(); f.At(180);
        Assert.NotNull(inside); Assert.Single((JArray)inside!["stepApplications"]!["records"]!);
        Assert.Equal(1, (int)inside["stepApplications"]!["unpublished"]!); Assert.Empty((JArray)inside["stepApplicationTerminals"]!);
        Assert.Equal(2, f.Applications().Count); Assert.Single(f.Terminals());
    }

    /// <summary>A successful call return after P expires cannot create a positive no-release P terminal.</summary>
    [Fact]
    public void QCallReturnCannotOverrunTheStillActivePExpiry()
    {
        var f = new Fixture(); Assert.Null(f.Controller.Submit(f.Request("p", null, startBefore: 190, expires: 190), 130)); f.At(130); f.QueueQ();
        f.Input.AfterEnd = () => f.Now = 190; f.At(180);
        Assert.Equal(2, f.Applications().Count); Assert.Equal(1, f.Input.Releases);
        Assert.True((bool)f.Batch()["authorityLost"]!); Assert.Empty(f.Terminals().Where(v => (string?)v["reason"] == "horizon_handoff"));
    }

    /// <summary>Thirty-two real fake-input applications exhaust attempts permanently, even after contiguous ACK drainage.</summary>
    [Fact]
    public void ThirtyTwoApplicationsCannotRecycleAttemptsAfterAck()
    {
        var f = new Fixture(); f.StartP(); var previous = "p";
        var box = Field<AgentStepApplicationOutbox>(f.Controller, "_stepApplications")!;
        for (var n = 2; n <= 32; n++)
        {
            var boundary = 130 + (n - 1) * 50; f.Refresh(boundary - 20);
            var next = "q" + n; Assert.Null(f.Controller.Submit(f.Request(next, box.CompleteLink(previous)), f.Now));
            f.At(boundary); previous = next;
        }
        Assert.Equal(32, f.Input.HeldEvaluations); Assert.Equal(33, (int)f.Batch()["nextReservedSequence"]!);
        for (var through = 4; through <= 32; through += 4) { _ = f.Applications(); f.Controller.AcknowledgeStepApplications(Ack(through)); }
        f.Refresh(1710); Assert.NotNull(f.Controller.Submit(f.Request("fresh", box.CompleteLink(previous)), f.Now));
        Assert.Equal(32, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>The preserved H01 overlarge admission is refused before any active P or channel ownership changes.</summary>
    [Fact]
    public void OversizedAdmissionLeavesActivePAndOutboxUntouched()
    {
        var config = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.OldReservationConfig, 4096);
        var p = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.OldReservationP, 65536);
        var q = AgentStepApplicationWire.Parse(AgentStepApplicationQueuedWireFixtures.OldReservationQ, 65536);
        var f = new Fixture(configuration: config);
        Assert.Null(f.Controller.Submit(p.ToObject<AgentRequest>()! with { RawApplicationRequest = p }, 130)); f.At(130);
        var box = Field<AgentStepApplicationOutbox>(f.Controller, "_stepApplications")!;
        var bound = box.CheckSubmission(q.ToObject<AgentRequest>()! with { RawApplicationRequest = q });
        var admission = AdmissionShape(config, q, 140, 180);
        Assert.Equal(1328, AgentStepApplicationWire.Freeze(admission, 4096).Length);
        f.Now = 140;
        var active = Field<AgentRequest>(f.Controller, "_active");
        var snapshot = AdmissionState(f, box);
        Assert.Throws<InvalidOperationException>(() => box.CheckQueuedAdmission(bound, (string)p["requestId"]!, 140, 180, 230));
        Assert.Equal(snapshot, AdmissionState(f, box));
        Assert.Equal("invalid_queued_application_binding", f.Controller.Submit(q.ToObject<AgentRequest>()! with { RawApplicationRequest = q }, 140));
        Assert.Equal(snapshot, AdmissionState(f, box)); Assert.Same(active, Field<AgentRequest>(f.Controller, "_active"));
        Assert.Null(f.Controller.QueuedAdmission((string)q["requestId"]!)); Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
        Assert.False(box.Lost); Assert.False(box.ClosedForSubmission); Assert.Null(Field<Exception>(f.Controller, "_queuedPrimaryFailure"));
        f.At(180); Assert.Equal(1, f.Input.Releases); Assert.Equal("horizon_complete", (string?)Assert.Single(f.Terminals())["reason"]);
    }

    /// <summary>Exact admission1024 accepts;1025 refuses while the identical8192 record reservation remains within its cap.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void CompleteAdmissionBoundaryIsPredispatchAndNonMutating(bool overflow)
    {
        var config = AgentStepApplicationWire.Parse(overflow ? AgentStepApplicationQueuedWireFixtures.Admission1025Configuration : AgentStepApplicationQueuedWireFixtures.Admission1024Configuration, 4096);
        var p = AgentStepApplicationWire.Parse(overflow ? AgentStepApplicationQueuedWireFixtures.Admission1025RequestP : AgentStepApplicationQueuedWireFixtures.Admission1024RequestP, 65536);
        var q = AgentStepApplicationWire.Parse(overflow ? AgentStepApplicationQueuedWireFixtures.Admission1025RequestQ : AgentStepApplicationQueuedWireFixtures.Admission1024RequestQ, 65536);
        var expected = overflow ? AgentStepApplicationQueuedWireFixtures.Admission1025AdmissionQ : AgentStepApplicationQueuedWireFixtures.Admission1024AdmissionQ;
        Assert.Equal(overflow ? 1025 : 1024, expected.Length);
        Assert.Equal(expected, AgentStepApplicationWire.Freeze(AdmissionShape(config, q, 140, 180), 4096));
        var f = new Fixture(configuration: config);
        Assert.Null(f.Controller.Submit(p.ToObject<AgentRequest>()! with { RawApplicationRequest = p }, 130)); f.At(130);
        var box = Field<AgentStepApplicationOutbox>(f.Controller, "_stepApplications")!;
        var method = typeof(AgentStepApplicationOutbox).GetMethod("ReservationSize", BindingFlags.Static | BindingFlags.NonPublic)!;
        Assert.Equal(8192, (int)method.Invoke(null, [q["stepApplication"]!["binding"]!, config, f.Input.ApplicationTrackedState, 32L])!);
        f.Now = 140;
        var before = AdmissionState(f, box); var reason = f.Controller.Submit(q.ToObject<AgentRequest>()! with { RawApplicationRequest = q }, 140);
        if (overflow) { Assert.Equal("invalid_queued_application_binding", reason); Assert.Equal(before, AdmissionState(f, box)); }
        else { Assert.Null(reason); Assert.Equal(expected, AgentStepApplicationWire.Freeze(f.Controller.QueuedAdmission((string)q["requestId"]!)!, 1024)); }
        Assert.False(box.Lost); Assert.False(box.ClosedForSubmission); Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>Retention consumes the exact prevalidated immutable strings even if the detached input JObject changes.</summary>
    [Fact]
    public void PreparedAdmissionAndBindingAreFrozenBeforeRetention()
    {
        var f = new Fixture(); f.StartP(); f.Now = 140;
        var q = f.Request("q", f.PLink()); var box = Field<AgentStepApplicationOutbox>(f.Controller, "_stepApplications")!;
        var bound = box.CheckSubmission(q); var prepared = box.CheckQueuedAdmission(bound, "p", 140, 180, 230);
        bound["requestId"] = "mutated"; ((JObject)bound["queueAfter"]!)["requestId"] = "mutated";
        box.AdmittedQueued("q", prepared);
        Assert.Same(prepared.Admission, Field<Dictionary<string, string>>(box, "_queuedAdmissions")!["q"]);
        Assert.Same(prepared.Binding, Field<Dictionary<string, string>>(box, "_bindings")!["q"]);
        Assert.Equal("q", (string?)box.QueuedAdmission("q")!["requestId"]);
        Assert.Equal("p", (string?)box.QueuedAdmission("q")!["queueAfter"]!["requestId"]);
        Assert.Equal(1, f.Input.HeldEvaluations); Assert.Equal(0, f.Input.Releases);
    }

    /// <summary>Outbox-only six-application window fixture: a native owner cannot advance this far past unseen Q evidence.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void OrdinaryFinalTerminalWaitsForItsOwnApplicationWindow(bool cancelled)
    {
        var f = new Fixture(); f.StartP(); var previous = "p";
        var box = Field<AgentStepApplicationOutbox>(f.Controller, "_stepApplications")!;
        for (var i = 1; i <= 5; i++)
        {
            var boundary = 130 + i * 50; f.Refresh(boundary - 20);
            var next = "q" + i; Assert.Null(f.Controller.Submit(f.Request(next, box.CompleteLink(previous)), f.Now));
            f.At(boundary); previous = next;
        }
        if (cancelled) { f.Now = 400; f.Controller.Stop(400, "fixture_cancel"); } else f.At(430);
        Assert.Equal(1, f.Input.Releases); Assert.True(box.ClosedForSubmission); Assert.False(box.Lost);
        var first = f.Terminals(); Assert.Equal(3, first.Count); Assert.DoesNotContain(first, t => (string?)t["binding"]!["requestId"] == "q5");
        Assert.All(first, t => Assert.All((JArray)t["applicationSequences"]!, n => Assert.InRange((long)n, 1, 4)));
        f.Controller.AcknowledgeStepApplications(Ack(4, first.Select(t => (string)t["binding"]!["requestId"]!).ToArray()));
        Assert.Equal(new long[] { 5, 6 }, f.Applications().Select(r => (long)r["sequence"]!).ToArray());
        var second = f.Terminals(); Assert.Equal(3, second.Count);
        var final = Assert.Single(second.Where(t => (string?)t["binding"]!["requestId"] == "q5"));
        Assert.Equal(JTokenType.Null, final["transition"]!.Type); Assert.Equal(6L, (long)Assert.Single((JArray)final["applicationSequences"]!));
        Assert.Equal(cancelled ? "cancelled" : "completed", (string?)final["status"]);
        Assert.Equal(cancelled ? "fixture_cancel" : "horizon_complete", (string?)final["reason"]);
        var retained = AgentStepApplicationWire.Freeze(final, 4096);
        f.Controller.AcknowledgeStepApplications(Ack(6));
        Assert.Empty(f.Applications()); Assert.Equal(retained, AgentStepApplicationWire.Freeze(f.Terminals().Single(t => (string?)t["binding"]!["requestId"] == "q5"), 4096));
        f.Controller.AcknowledgeStepApplications(Ack(6, second.Select(t => (string)t["binding"]!["requestId"]!).ToArray()));
        Assert.Empty(f.Terminals()); Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>A never-dispatched Q cancellation has no own-row dependency and remains eligible beside P's row.</summary>
    [Fact]
    public void EmptyOwnApplicationTerminalRemainsVisible()
    {
        var f = new Fixture(); f.StartP(); f.QueueQ(); f.Controller.Stop(150, "fixture_cancel");
        var q = Assert.Single(f.Terminals().Where(t => (string?)t["binding"]!["requestId"] == "q"));
        Assert.Empty((JArray)q["applicationSequences"]!); Assert.Equal(JTokenType.Null, q["transition"]!.Type);
        Assert.Single(f.Applications()); Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>Reconstruct the complete admission solely for comparison with the retained scalar fixtures.</summary>
    private static JObject AdmissionShape(JObject config, JObject request, double admitted, double start) => new()
    {
        ["version"] = 2, ["channelId"] = config["channelId"]!.DeepClone(), ["requestId"] = request["requestId"]!.DeepClone(),
        ["state"] = request["queueAfter"]!.Type == JTokenType.Null ? "active" : "queued", ["queueAfter"] = request["queueAfter"]!.DeepClone(),
        ["admittedAtMs"] = admitted, ["scheduledStartMs"] = start, ["scheduledEndMs"] = start + 50
    };

    /// <summary>Bounded exact snapshot of the ownership and outbox fields that a clean refusal must preserve.</summary>
    private static string AdmissionState(Fixture fixture, AgentStepApplicationOutbox box) => JsonConvert.SerializeObject(new
    {
        active = Field<AgentRequest>(fixture.Controller, "_active"), queued = Field<AgentRequest>(fixture.Controller, "_queued"),
        requests = Field<Dictionary<string, double>>(fixture.Controller, "_requests"),
        lastFrame = Field<long>(fixture.Controller, "_lastAcceptedFrameId"),
        bindings = Field<Dictionary<string, string>>(box, "_bindings"), admissions = Field<Dictionary<string, string>>(box, "_queuedAdmissions"),
        records = Field<SortedDictionary<long, string>>(box, "_records"), terminals = Field<Dictionary<string, string>>(box, "_terminals"),
        next = Field<long>(box, "_next"), pending = Field<string>(box, "_pending"), box.Lost, box.ClosedForSubmission
    });

    /// <summary>Typed version-two ACK; terminals name only already offered retained facts.</summary>
    private static JObject Ack(long through, params string[] terminals) => new() { ["version"] = 2, ["channelId"] = "channel", ["through"] = through, ["terminalRequestIds"] = new JArray(terminals) };

    /// <summary>Exact fake QPC identity, with no platform or native backend dependency.</summary>
    internal static JObject Config(int version = 2) => new() { ["version"] = version,
        ["mode"] = version == 2 ? AgentStepApplicationWire.QueuedMode : AgentStepApplicationWire.Mode,
        ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["channelId"] = "channel", ["backendId"] = "win32-sendinput",
        ["backendEpoch"] = "backend", ["buildSha256"] = new string('a', 64), ["clockKind"] = "windows_qpc", ["sessionOriginTicks"] = 1L,
        ["clockFrequency"] = 1000L, ["allowedKeys"] = new JArray("W", "A", "LBUTTON") };

    /// <summary>A source-faithful in-memory controller and two valid source observations.</summary>
    private sealed class Fixture
    {
        /// <summary>Elapsed-ms clock; independent QPC samples remain separately observed.</summary>
        internal double Now = 130;
        /// <summary>Optional deterministic admission/reservation delay.</summary>
        internal Func<double>? ClockOverride;
        /// <summary>Failure injection after a fixed number of remaining raw QPC reads.</summary>
        internal int? ThrowAfterQpcReads;
        /// <summary>Monotone fake raw ticks; no hardware timer is queried.</summary>
        private long _ticks = 1000;
        /// <summary>Current immutable fixture source; refresh never changes an already admitted request.</summary>
        private long _frameId = 2;
        /// <summary>Separate acquisition-start and request timestamp, matching the real source authority choice.</summary>
        private double _capturedAt = 120, _sourceAt = 100;
        /// <summary>Actual in-memory backend operand and reviewed controller subject.</summary>
        internal readonly FakeInput Input = new();
        /// <summary>Production controller, configured through its internal disabled-feature test seam.</summary>
        internal readonly AgentActionController Controller;
        /// <summary>Native source epoch uses the same exact GUID grammar as current readiness.</summary>
        private const string Epoch = "11111111111111111111111111111111";
        /// <summary>Prepare only known fake readiness; no session or input lifecycle runs.</summary>
        internal Fixture(int version = 2, bool configure = true, JObject? configuration = null)
        {
            Controller = new AgentActionController(Input, true, () => ClockOverride?.Invoke() ?? Now);
            Input.Telemetry.Sink = Controller.RecordInputCall;
            Controller.RegisterFrame(new(1, 80, 1920, 1080, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame(Epoch, 1000000900, 90, 60)));
            Assert.True(Controller.RegisterFrame(new(2, 120, 1920, 1080, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame(Epoch, 1000001300, 130, 100))).Ready);
            if (configuration is not null)
            {
                Input.Backend = (string)configuration["backendEpoch"]!;
                // Custom fixture origins must precede the same fake clock's first dispatch sample.
                _ticks = Math.Max(_ticks, (long)configuration["sessionOriginTicks"]!);
            }
            if (configure) Controller.ConfigureStepApplications(configuration ?? Config(version), Qpc);
        }
        /// <summary>Separate deterministic proof clock with an explicit injected failure.</summary>
        internal long Qpc()
        {
            if (ThrowAfterQpcReads is { } count) { if (count == 0) throw new InvalidOperationException("qpc_failure"); ThrowAfterQpcReads = count - 1; }
            return ++_ticks;
        }
        /// <summary>Advance one original controller tick.</summary>
        internal void At(double value) { Now = value; Controller.Tick(value); }
        /// <summary>Publish a genuinely newer fake source without renewing a previous frame's timestamp.</summary>
        internal void Refresh(double value)
        {
            Now = value; _frameId++; _capturedAt = value; _sourceAt = value - 20;
            Assert.True(Controller.RegisterFrame(new(_frameId, value, 1920, 1080, AgentWorldEvidence.WorldHud, 0,
                new AgentSourceFrame(Epoch, 1000001300 + (_frameId - 2) * 500, value + 10, _sourceAt))).Ready);
        }
        /// <summary>Complete P before creating any successor link.</summary>
        internal void StartP(double startBefore = 200) { Assert.Null(Controller.Submit(Request("p", null, startBefore: startBefore), Now)); Controller.Tick(Now); }
        /// <summary>Retain Q while keeping P active and unchanged.</summary>
        internal AgentRequest QueueQ(string[]? keys = null, int dx = 0)
        {
            Now = 140; var q = Request("q", PLink(), keys, dx); Assert.Null(Controller.Submit(q, Now)); return q;
        }
        /// <summary>Detached application batch returned by the real outbox.</summary>
        internal JObject Batch() => (JObject)Controller.StepApplicationExtensions()!["stepApplications"]!;
        /// <summary>Detached complete/partial applications; observations do not ACK them.</summary>
        internal JArray Applications() => (JArray)Batch()["records"]!;
        /// <summary>Detached terminal window with real dependency filtering.</summary>
        internal JArray Terminals() => (JArray)Controller.StepApplicationExtensions()!["stepApplicationTerminals"]!;
        /// <summary>The actual first application's immutable digest supplies the queue link.</summary>
        internal JObject PLink() => Link("p", 1, (string)Applications()[0]["binding"]!["submissionSha256"]!);
        /// <summary>Construct the exact closed link grammar.</summary>
        internal static JObject Link(string request, long sequence, string digest) => new() { ["requestId"] = request, ["applicationSequence"] = sequence, ["submissionSha256"] = digest };
        /// <summary>Build exact detached canonical JSON and its typed binding before the real server validator sees it.</summary>
        internal AgentRequest Request(string id, JObject? after, string[]? keys = null, int dx = 0, double? startBefore = null, double? expires = null)
        {
            var step = new JObject { ["durationMs"] = 50, ["keys"] = new JArray(keys ?? ["W"]), ["mouseDx"] = dx, ["mouseDy"] = 0 };
            var source = new JObject { ["version"] = 1, ["command"] = "action", ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["goalVersion"] = 1,
                ["requestId"] = id, ["frameId"] = _frameId, ["observedAtMs"] = _capturedAt, ["expiresAtMs"] = expires ?? _sourceAt + 150, ["startBeforeMs"] = startBefore ?? _sourceAt + 100,
                ["modelId"] = "model", ["steps"] = new JArray(step.DeepClone()), ["queueAfter"] = after?.DeepClone() };
            var raw = AgentStepApplicationWire.Freeze(source, 16384);
            var binding = new JObject { ["identity"] = new JObject { ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["sourceEpoch"] = Epoch,
                    ["modelId"] = "model", ["goalVersion"] = 1, ["controlEpoch"] = 1, ["policyGoalVersion"] = 1,
                    ["readinessEpoch"] = Controller.GetWorldReadiness(Now).Epoch, ["frameId"] = _frameId },
                ["requestId"] = id, ["submissionSha256"] = Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(raw))).ToLowerInvariant(),
                ["model"] = new JObject { ["checkpointSha256"] = new string('b', 64), ["profile"] = "original", ["mapping"] = "native-raw-to-one-step-v1" },
                ["intervalCount"] = 1, ["stepIndex"] = 0, ["step"] = step, ["queueAfter"] = after?.DeepClone() };
            var extension = new JObject { ["version"] = 2, ["submissionJson"] = raw, ["binding"] = binding };
            var wire = (JObject)source.DeepClone(); wire["stepApplication"] = extension.DeepClone();
            return source.ToObject<AgentRequest>()! with { StepApplication = extension, RawApplicationRequest = wire };
        }
    }

    /// <summary>In-memory held-state backend whose synchronous telemetry and proof wrap the same single call.</summary>
    private sealed class FakeInput : IAgentInput, IAgentApplicationInput
    {
        /// <summary>Current proof, generation and known state.</summary>
        private AgentStepApplicationEvidence? _proof;
        /// <summary>Only successful complete evaluation advances this local generation.</summary>
        private long _generation;
        /// <summary>Release cannot establish known neutral state.</summary>
        private bool _known = true;
        /// <summary>Exact desired held-key order, never a physical keyboard query.</summary>
        internal string[] Keys = [];
        /// <summary>Finite evaluation, backend and release counts expose duplicate calls.</summary>
        internal int HeldEvaluations, BackendCalls, Releases;
        /// <summary>Controlled failures and post-return delays.</summary>
        internal bool ThrowMouse, ThrowRelease;
        /// <summary>One fixed evaluation seam may throw the same retained exception object.</summary>
        internal string? FailAt;
        /// <summary>Fixed fake exception, independent from mouse and aggregate cleanup errors.</summary>
        internal readonly InvalidOperationException EvaluationError = new("evaluation_failure");
        /// <summary>A changed backend is an explicit failure, never a new accepted epoch.</summary>
        internal string Backend = "backend";
        /// <summary>Optional fake callbacks after software evaluation or generation update.</summary>
        internal Action? AfterHeld, AfterEnd;
        /// <summary>Primary and cleanup errors remain distinguishable by object identity.</summary>
        internal readonly InvalidOperationException MouseError = new("mouse_failure"), ReleaseError = new("release_failure");
        /// <summary>Production telemetry observer used with an in-memory sink.</summary>
        internal readonly AgentInputCallObserver Telemetry = new();
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <inheritdoc />
        public string ApplicationBackendEpoch => Backend;
        /// <inheritdoc />
        public JObject ApplicationTrackedState => new() { ["keys"] = new JArray(Keys), ["generation"] = _generation, ["complete"] = _known };
        /// <inheritdoc />
        public void BeginApplication(AgentStepApplicationEvidence proof) { Assert.Null(_proof); Assert.True(_known); _proof = proof; }
        /// <inheritdoc />
        public void EndApplication(bool completed, string[] desired) { _proof = null; _known = completed; if (completed) { if (FailAt == "end") throw EvaluationError; Keys = desired.ToArray(); _generation++; AfterEnd?.Invoke(); } }
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys)
        {
            HeldEvaluations++;
            foreach (var key in Keys.Except(keys).ToArray()) Call(key.EndsWith("BUTTON", StringComparison.Ordinal) ? "buttonUp" : "keyUp", key, 0, 0, () => Keys = Keys.Where(k => k != key).ToArray());
            foreach (var key in keys.Except(Keys).ToArray()) Call(key.EndsWith("BUTTON", StringComparison.Ordinal) ? "buttonDown" : "keyDown", key, 0, 0, () => Keys = Keys.Append(key).ToArray());
            if (FailAt == "held") throw EvaluationError;
            AfterHeld?.Invoke();
        }
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => Call("mouseMove", null, dx, dy, () => { if (ThrowMouse) throw MouseError; });
        /// <inheritdoc />
        public void ReleaseAll() { Releases++; _known = false; if (ThrowRelease) throw ReleaseError; Keys = []; }
        /// <summary>Wrap precisely one fake backend/bookkeeping operation in both unchanged observers.</summary>
        private void Call(string operation, string? key, int dx, int dy, Action action) => _proof!.Call(operation, key, dx, dy,
            () => Telemetry.Invoke(operation, key, dx, dy, () => { BackendCalls++; if (FailAt == operation) throw EvaluationError; action(); }));
    }
}
