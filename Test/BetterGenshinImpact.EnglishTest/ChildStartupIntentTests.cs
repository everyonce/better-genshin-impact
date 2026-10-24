using System.Text;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.ChildSession;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Headless startup intent, shared launch admission and strict authenticated wire regressions.</summary>
public sealed class ChildStartupIntentTests
{
    /// <summary>Cold primary action selection and resulting child argv use the real command-line parser.</summary>
    [Theory]
    [InlineData(CommandLineAction.None, "controlEndpoint", " --automation")]
    [InlineData(CommandLineAction.Start, "gameRuntime", " --automation start")]
    public void ColdActionSelectsExactChildArguments(CommandLineAction action, string mode, string arguments)
    {
        Assert.Equal(mode, ChildSessionStartupOperation.FromAction(action));
        Assert.Equal(arguments, ChildSessionProcessLauncher.AutomationArguments(true, mode));
        var parsed = CommandLineOptions.Parse(["BetterGI.exe", .. arguments.Split(' ', StringSplitOptions.RemoveEmptyEntries)]);
        Assert.True(parsed.AutomationMode);
        Assert.Equal(action, parsed.Action);
    }

    /// <summary>Ordinary manual children and omitted legacy automation retain their previous arguments.</summary>
    [Theory]
    [InlineData(false, null, "")]
    [InlineData(true, null, " --automation start")]
    [InlineData(false, "controlEndpoint", "")]
    public void LegacyAndManualArgumentsArePreserved(bool automated, string? mode, string expected)
        => Assert.Equal(expected, ChildSessionProcessLauncher.AutomationArguments(automated, mode));

    /// <summary>Only a Game caller can join either active intent; it explicitly starts the endpoint's game later.</summary>
    [Theory]
    [InlineData("controlEndpoint", "controlEndpoint", true)]
    [InlineData("controlEndpoint", "gameRuntime", false)]
    [InlineData("controlEndpoint", null, false)]
    [InlineData("gameRuntime", "controlEndpoint", true)]
    [InlineData("gameRuntime", "gameRuntime", true)]
    [InlineData("gameRuntime", null, false)]
    public void ActiveIntentCompatibilityIsDirectional(string requested, string? active, bool expected)
        => Assert.Equal(expected, ChildSessionStartupOperation.CanJoin(requested, active));

    /// <summary>The direct continuation and delayed login callback share one outcome regardless of which reaches the gate first.</summary>
    [Theory]
    [InlineData("controlEndpoint", false)]
    [InlineData("controlEndpoint", true)]
    [InlineData("gameRuntime", false)]
    [InlineData("gameRuntime", true)]
    public async Task DirectAndLoginCallbackDispatchOnce(string mode, bool callbackFirst)
    {
        using var gate = new SemaphoreSlim(1);
        var operation = new ChildSessionStartupOperation(4, mode, CancellationToken.None);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var complete = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var paths = new List<string>();
        Task Dispatch(string path) => operation.DispatchAsync(gate, () => operation.Generation == 4, async () =>
        {
            paths.Add(path);
            Assert.Equal(mode == "controlEndpoint" ? " --automation" : " --automation start",
                ChildSessionProcessLauncher.AutomationArguments(true, operation.Mode));
            entered.SetResult();
            await complete.Task;
        });
        var first = Dispatch(callbackFirst ? "login" : "direct");
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        var second = Dispatch(callbackFirst ? "direct" : "login");
        Assert.False(second.IsCompleted);
        complete.SetResult();
        await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(3));
        Assert.Equal(new[] { callbackFirst ? "login" : "direct" }, paths);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>Cancellation and generation replacement while a callback waits cannot start a process after it owns the gate.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task QueuedCallbackRevalidatesCancellationAndGeneration(bool cancel)
    {
        using var gate = new SemaphoreSlim(0, 1);
        using var cancellation = new CancellationTokenSource();
        var operation = new ChildSessionStartupOperation(1, "controlEndpoint", cancellation.Token);
        long generation = 1;
        var calls = 0;
        var pending = operation.DispatchAsync(gate, () => generation == operation.Generation,
            () => { calls++; return Task.CompletedTask; });
        if (cancel) cancellation.Cancel(); else generation = 2;
        gate.Release();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending);
        Assert.Equal(0, calls);
        var next = new ChildSessionStartupOperation(2, "gameRuntime", CancellationToken.None);
        await next.DispatchAsync(gate, () => true, () => { calls++; return Task.CompletedTask; });
        Assert.Equal(1, calls);
    }

    /// <summary>An uncertain first dispatch failure is retained; the second launch path cannot retry it.</summary>
    [Fact]
    public async Task FailedDispatchIsNotReplayedByTheOtherPath()
    {
        using var gate = new SemaphoreSlim(1);
        var operation = new ChildSessionStartupOperation(1, "controlEndpoint", CancellationToken.None);
        var calls = 0;
        Task Launch() { calls++; throw new InvalidOperationException("uncertain COM dispatch"); }
        await Assert.ThrowsAsync<InvalidOperationException>(() => operation.DispatchAsync(gate, () => true, Launch));
        await Assert.ThrowsAsync<InvalidOperationException>(() => operation.DispatchAsync(gate, () => true, Launch));
        Assert.Equal(1, calls);
    }

    /// <summary>Exact valid intent participates in the request replay fingerprint; omission remains distinct legacy behavior.</summary>
    [Fact]
    public void WireFingerprintBindsIntentAndPreservesOmission()
    {
        var legacy = Request();
        var endpoint = legacy with { ChildStartupMode = "controlEndpoint" };
        var game = legacy with { ChildStartupMode = "gameRuntime" };
        foreach (var request in new[] { legacy, endpoint, game })
            Assert.Null(ExternalControlProtocol.ValidateRequest(request, DateTimeOffset.UtcNow));
        Assert.Equal(3, new[] { legacy, endpoint, game }.Select(ExternalControlProtocol.Fingerprint).Distinct().Count());
    }

    /// <summary>Reject aliases, null and intent on unrelated commands before any launch admission.</summary>
    [Theory]
    [InlineData("startChildSession", "null", "invalid_command_parameters")]
    [InlineData("startChildSession", "\"ControlEndpoint\"", "invalid_command_parameters")]
    [InlineData("startChildSession", "\"unknown\"", "invalid_command_parameters")]
    [InlineData("startChildGame", "\"controlEndpoint\"", "unexpected_command_parameters")]
    [InlineData("status", "null", "unexpected_command_parameters")]
    public void RejectsInvalidOrUnrelatedWireIntent(string command, string jsonValue, string error)
    {
        var json = $$"""{"version":1,"requestId":"{{Guid.NewGuid()}}","createdAtUnixMs":{{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}},"command":"{{command}}","childStartupMode":{{jsonValue}},"targetProcessId":1,"targetWindowsSessionId":2,"targetNonce":"epoch"}""";
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(json), out var request));
        Assert.Equal(error, ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
    }

    /// <summary>Build only a protocol value, without constructing WPF or opening a control endpoint.</summary>
    private static ExternalControlRequest Request() => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        Command = "startChildSession", TargetProcessId = 1, TargetWindowsSessionId = 2, TargetNonce = "epoch"
    };
}
