using BetterGenshinImpact.Pulonia.Executors;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Remote;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.Service.ExternalControl;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Serializes process-wide remote ownership fixtures with the existing loopback host tests.</summary>
[CollectionDefinition("Pulonia remote ownership", DisableParallelization = true)]
public sealed class PuloniaRemoteOwnershipCollection
{
}

/// <summary>Managed fake transports and executors prove remote admission and idle-restart exclusion.</summary>
[Collection("Pulonia remote ownership")]
public sealed class PuloniaRemoteOwnershipTests
{
    /// <summary>Registration is visible before worker dispatch, including a game node waiting for execution.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void PendingRegistrationBlocksRestart_AndDispatchFailureDrains(bool game)
    {
        var transport = new FinishTransport();
        var logger = new CallbackLogger(() =>
        {
            Assert.True(PuloniaRemoteNodeHost.HasActiveNodes);
            Assert.False(PuloniaRemoteNodeHost.TryReserveRestart());
            throw new InvalidOperationException("inert dispatch failure");
        });
        var host = Host(transport, new PuloniaCSharpTaskRegistry(), logger);
        var error = Assert.Throws<InvalidOperationException>(() => host.Start(Start(game)));
        Assert.Equal("inert dispatch failure", error.Message);
        Assert.False(PuloniaRemoteNodeHost.HasActiveNodes);
    }

    /// <summary>Pure execution, cancellation and failure remain owned until the final reply attempt ends.</summary>
    [Theory]
    [InlineData("success")]
    [InlineData("failure")]
    [InlineData("cancel")]
    public async Task PureNodeAndFinalPublicationBlockRestart(string outcome)
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var proceed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var registry = new PuloniaCSharpTaskRegistry();
        registry.Register("test.op", async (_, _, ct) =>
        {
            entered.TrySetResult();
            await proceed.Task.WaitAsync(ct);
            if (outcome == "failure") throw new InvalidOperationException("inert node failure");
            return PuloniaTaskOutcome.Success("inert success");
        });
        var transport = new FinishTransport();
        var host = Host(transport, registry);
        var start = Start(false);
        host.Start(start);
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.True(PuloniaRemoteNodeHost.HasActiveNodes);
            Assert.False(PuloniaRemoteNodeHost.TryReserveRestart());
            Assert.Throws<InvalidOperationException>(() => host.Start(start));
            if (outcome == "cancel") host.Cancel(start.ExecutionId);
            else proceed.TrySetResult();
            await transport.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.True(PuloniaRemoteNodeHost.HasActiveNodes);
            Assert.False(PuloniaRemoteNodeHost.TryReserveRestart());
            Assert.Equal(outcome switch
            {
                "success" => PuloniaRemoteNodeResultKind.Completed,
                "failure" => PuloniaRemoteNodeResultKind.Failed,
                _ => PuloniaRemoteNodeResultKind.Cancelled
            }, transport.Result!.ResultKind);
        }
        finally
        {
            host.Cancel(start.ExecutionId);
            proceed.TrySetResult();
            transport.Release.TrySetResult();
            await DrainedAsync();
        }
    }

    /// <summary>The actual existing restart reservation holds admission on commit and releases it on failure.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void RestartReservationAndRemoteAdmissionAreMutuallyExclusive(bool committed)
    {
        using var semaphore = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(semaphore);
        var transportCalls = 0;
        var host = new PuloniaRemoteNodeHost(() => { transportCalls++; return new FinishTransport(); }, [],
            new PuloniaGameTaskCoordinator(null!), new TaskStopService(NullLogger<TaskStopService>.Instance),
            NullLogger<PuloniaRemoteNodeHost>.Instance);
        try
        {
            var result = reservation.TryLaunch(PuloniaRemoteNodeHost.TryReserveRestart,
                PuloniaRemoteNodeHost.ReleaseRestartReservation, () => PuloniaRemoteNodeHost.HasActiveNodes, () =>
                {
                    Assert.Throws<InvalidOperationException>(() => host.Start(Start(false)));
                    return committed ? new object() : null;
                });
            Assert.Equal(committed, result is not null);
            Assert.Equal(committed, reservation.Committed);
            Assert.Equal(0, transportCalls);
            if (committed) Assert.False(PuloniaRemoteNodeHost.TryReserveRestart());
            else Assert.True(PuloniaRemoteNodeHost.TryReserveRestart());
        }
        finally { PuloniaRemoteNodeHost.ReleaseRestartReservation(); }
    }

    /// <summary>Build a complete synthetic dispatch without files, native runtime or account lookup.</summary>
    private static PuloniaRemoteNodeStart Start(bool game)
    {
        var task = new PuloniaTaskPreparedTask("plan", "task", "task", "task", "inert", "csharp", true,
            null, null, new JObject { ["operation"] = "test.op" }, new Dictionary<string, string>(), new PuloniaTaskPolicy(), []);
        var snapshot = new PuloniaTaskSnapshot("plan", 1, DateTimeOffset.UtcNow, null, task,
            new Dictionary<string, string>(), new Dictionary<string, string>());
        return new PuloniaRemoteNodeStart { ExecutionId = Guid.NewGuid(), Kind = PuloniaRemoteNodeKind.Task,
            RunId = "run_inert", TaskAddress = "task", Attempt = 1, RequiresGameSession = game,
            TaskJson = PuloniaTaskJson.Write(task), SnapshotJson = snapshot.ToJson() };
    }

    /// <summary>Construct the real node host with only fake transport and pure C# executor dependencies.</summary>
    private static PuloniaRemoteNodeHost Host(FinishTransport transport, PuloniaCSharpTaskRegistry registry,
        ILogger<PuloniaRemoteNodeHost>? logger = null) => new(() => transport, [new PuloniaCSharpTaskExecutor(registry)],
            new PuloniaGameTaskCoordinator(null!), new TaskStopService(NullLogger<TaskStopService>.Instance),
            logger ?? NullLogger<PuloniaRemoteNodeHost>.Instance);

    /// <summary>Wait only for the managed worker's final census release, with a finite failure deadline.</summary>
    private static async Task DrainedAsync()
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (PuloniaRemoteNodeHost.HasActiveNodes) await Task.Delay(1, timeout.Token);
    }

    /// <summary>A source-only managed transport holds the final publication until explicitly released by the test.</summary>
    private sealed class FinishTransport : IPuloniaRemoteTransport
    {
        /// <summary>Signals entry to the result publication.</summary>
        internal TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        /// <summary>Owns the sole publication wait.</summary>
        internal TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        /// <summary>The actual host-produced terminal result.</summary>
        internal PuloniaRemoteNodeFinished? Result { get; private set; }
        /// <inheritdoc />
        public event Action<int>? RemoteInstanceDisconnected { add { } remove { } }
        /// <inheritdoc />
        public event Action? RootConnectionLost { add { } remove { } }
        /// <inheritdoc />
        public int? ResolveTargetProcessId(PuloniaTaskExecutionTarget target) => null;
        /// <inheritdoc />
        public Task StartRemoteNodeAsync(int processId, PuloniaRemoteNodeStart start, CancellationToken ct) => throw new NotSupportedException();
        /// <inheritdoc />
        public Task CancelRemoteNodeAsync(int processId, Guid executionId, CancellationToken ct) => throw new NotSupportedException();
        /// <inheritdoc />
        public async Task FinishRemoteNodeAsync(PuloniaRemoteNodeFinished finished, CancellationToken ct)
        {
            Result = finished;
            Entered.TrySetResult();
            await Release.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
        }
    }

    /// <summary>Observe the real pre-dispatch boundary without scheduling a worker or touching game state.</summary>
    private sealed class CallbackLogger(Action callback) : ILogger<PuloniaRemoteNodeHost>
    {
        /// <inheritdoc />
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        /// <inheritdoc />
        public bool IsEnabled(LogLevel logLevel) => true;
        /// <inheritdoc />
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter) => callback();
    }
}
