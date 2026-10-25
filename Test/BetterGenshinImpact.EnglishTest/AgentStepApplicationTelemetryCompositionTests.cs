using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json.Linq;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Prepared inert tests for the actual private composition seam; no GameRuntime or InputHub is constructed.</summary>
public sealed class AgentStepApplicationTelemetryCompositionTests
{
    /// <summary>Without application opt-in the original telemetry call and bookkeeping happen exactly once.</summary>
    [Fact]
    public void LegacyCallRetainsTelemetryAndBookkeeping()
    {
        var rows = new List<AgentInputCall>();
        var telemetry = new AgentInputCallObserver { Sink = rows.Add };
        var input = Subject(telemetry, null); var calls = 0; var held = false;
        Invoke(input, () => { calls++; held = true; });
        Assert.Equal(1, calls); Assert.True(held);
        Assert.Equal(new[] { "started", "returned" }, rows.Select(row => row.Stage));
        Assert.False(telemetry.Incomplete);
    }

    /// <summary>Application evidence and telemetry refer to one returned backend operation, never two dispatches.</summary>
    [Fact]
    public void BothObserversShareOneReturnedOperation()
    {
        var rows = new List<AgentInputCall>(); var telemetry = new AgentInputCallObserver { Sink = rows.Add };
        long ticks = 1000; var proof = Proof(() => ++ticks); var input = Subject(telemetry, proof); var calls = 0;
        Invoke(input, () => calls++); proof.HeldCompleted();
        var finished = proof.Finish(State(), "backend", true);
        Assert.Equal(1, calls); Assert.Equal(2, rows.Count);
        Assert.Equal("returned", (string?)Assert.Single((JArray)finished["calls"]!)["stage"]);
        Assert.Equal("complete_returned", (string?)finished["outcome"]);
    }

    /// <summary>A failed telemetry sink still cannot suppress or duplicate backend success or poison application evidence.</summary>
    [Fact]
    public void TelemetryFailureRemainsNonthrowing()
    {
        var telemetry = new AgentInputCallObserver { Sink = _ => throw new InvalidOperationException("diagnostic") };
        long ticks = 1000; var proof = Proof(() => ++ticks); var input = Subject(telemetry, proof); var calls = 0;
        Invoke(input, () => calls++); proof.HeldCompleted();
        Assert.Equal(1, calls); Assert.True(telemetry.Incomplete);
        Assert.Equal("complete_returned", (string?)proof.Finish(State(), "backend", true)["outcome"]);
    }

    /// <summary>A post-return evidence clock failure cannot undo real bookkeeping or relabel successful backend telemetry.</summary>
    [Fact]
    public void PostCallClockFailureRetainsReturnedTrackedState()
    {
        var rows = new List<AgentInputCall>(); var telemetry = new AgentInputCallObserver { Sink = rows.Add };
        var reads = 0; var expected = new ApplicationException("clock");
        var proof = Proof(() => ++reads == 3 ? throw expected : 1000 + reads);
        var input = Subject(telemetry, proof); var calls = 0; var held = false;
        var error = Assert.Throws<TargetInvocationException>(() => Invoke(input, () => { calls++; held = true; }));
        Assert.Same(expected, error.InnerException); Assert.Equal(1, calls); Assert.True(held);
        Assert.Equal(new[] { "started", "returned" }, rows.Select(row => row.Stage));
        Assert.False(telemetry.ExecutionUncertain);
    }

    /// <summary>The original backend exception survives both failed telemetry and failed application error recording.</summary>
    [Fact]
    public void BackendExceptionIsNeverReplacedByEitherObserver()
    {
        var telemetry = new AgentInputCallObserver { Sink = _ => throw new ApplicationException("diagnostic") };
        var reads = 0; var proof = Proof(() => ++reads >= 3 ? throw new ApplicationException("clock") : 1000 + reads);
        var input = Subject(telemetry, proof); var expected = new InvalidOperationException("backend"); var calls = 0;
        var error = Assert.Throws<TargetInvocationException>(() => Invoke(input, () => { calls++; throw expected; }));
        Assert.Same(expected, error.InnerException); Assert.Equal(1, calls);
        Assert.True(telemetry.Incomplete); Assert.True(telemetry.ExecutionUncertain);
    }

    /// <summary>A pre-dispatch evidence clock regression prevents every telemetry/backend invocation.</summary>
    [Fact]
    public void PreCallClockRegressionDoesNotDispatch()
    {
        var rows = new List<AgentInputCall>(); var telemetry = new AgentInputCallObserver { Sink = rows.Add };
        long ticks = 1001; var proof = Proof(() => ticks--); var input = Subject(telemetry, proof); var calls = 0;
        var error = Assert.Throws<TargetInvocationException>(() => Invoke(input, () => calls++));
        Assert.IsType<InvalidOperationException>(error.InnerException); Assert.Equal(0, calls); Assert.Empty(rows);
    }

    /// <summary>Allocate only the object holding the two observer fields; runtime construction/native access is deliberately absent.</summary>
    private static RuntimeAgentInput Subject(AgentInputCallObserver telemetry, AgentStepApplicationEvidence? proof)
    {
        var input = (RuntimeAgentInput)RuntimeHelpers.GetUninitializedObject(typeof(RuntimeAgentInput));
        typeof(RuntimeAgentInput).GetField("<Telemetry>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(input, telemetry);
        typeof(RuntimeAgentInput).GetField("_applicationProof", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(input, proof);
        return input;
    }

    /// <summary>Invoke the production method directly using only an inert delegate and the installed observer fields.</summary>
    private static void Invoke(RuntimeAgentInput input, Action action) => typeof(RuntimeAgentInput)
        .GetMethod("ApplicationCall", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(input, ["keyDown", "W", 0, 0, action]);

    /// <summary>Use the original bounded proof with a deterministic fake monotonic clock.</summary>
    private static AgentStepApplicationEvidence Proof(Func<long> clock) => new(clock, State(), "backend", 1000);

    /// <summary>Known empty bookkeeping is software state only.</summary>
    private static JObject State() => new() { ["keys"] = new JArray(), ["generation"] = 0L, ["complete"] = true };
}
