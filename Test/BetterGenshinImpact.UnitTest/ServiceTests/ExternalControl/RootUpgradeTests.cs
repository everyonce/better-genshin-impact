using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Pulonia.Executors;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.Service.ExternalControl;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.DependencyInjection;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

/// <summary>Inactive upgrade tests: no Application, process lookup, RDP, capture, task execution or UI.</summary>
public sealed class RootUpgradeTests
{
    /// <summary>A complete per-process binding is parsed without changing ordinary startup.</summary>
    [Fact]
    public void StartupBindingIsExplicitAndOrdinaryStartupIsUnchanged()
    {
        var normal = CommandLineOptions.Parse(["test", "--automation", "--desktopClone"]);
        Assert.Null(normal.UpgradeSession);
        var bound = CommandLineOptions.Parse(["test", "--automation", "--desktopClone", "--upgrade-session", "3",
            "--upgrade-game-pid", "42", "--upgrade-game-start", "134372565238254837"]);
        Assert.True(bound.AutomationMode);
        Assert.Equal(3, bound.UpgradeSession!.SessionId);
        Assert.Equal(42, bound.UpgradeSession.GameProcessId);
        Assert.False(bound.HasTaskArgs);
    }

    /// <summary>Partial, duplicated, task-bearing and child-role startup must never silently downgrade.</summary>
    [Theory]
    [InlineData("--upgrade-session 3")]
    [InlineData("--upgrade-session 3 --upgrade-game-pid 42 --upgrade-game-start 1 --upgrade-session 3")]
    [InlineData("--upgrade-session 3 --upgrade-game-pid 42 --upgrade-game-start 1 start")]
    [InlineData("--upgrade-session 3 --upgrade-game-pid 42 --upgrade-game-start 1 --instance childsession")]
    [InlineData("--upgrade-session 0 --upgrade-game-pid 42 --upgrade-game-start 1")]
    [InlineData("--upgrade-session 3 --upgrade-game-pid 42 --upgrade-game-start -1")]
    public void MalformedStartupCannotBecomeAnOrdinaryLaunch(string suffix)
        => Assert.ThrowsAny<ArgumentException>(() => CommandLineOptions.Parse(
            new[] { "test", "--automation", "--desktopClone" }.Concat(suffix.Split(' ')).ToArray()));

    /// <summary>The new mode always requires both existing independent automation and clone options.</summary>
    [Fact]
    public void UpgradeCannotBeEnabledByLifetimeFieldsAlone()
        => Assert.Throws<ArgumentException>(() => CommandLineOptions.Parse(["test", "--upgrade-session", "3",
            "--upgrade-game-pid", "42", "--upgrade-game-start", "1"]));

    /// <summary>PID reuse, session reuse, game exit and unrelated executables all fail the same native facts predicate.</summary>
    [Theory]
    [InlineData(42, 3, 2, "GenshinImpact", false)]
    [InlineData(43, 3, 1, "GenshinImpact", false)]
    [InlineData(42, 4, 1, "GenshinImpact", false)]
    [InlineData(42, 3, 1, "BetterGI", false)]
    [InlineData(42, 3, 1, "GenshinImpact", true)]
    public void ReusedOrForeignGameLifetimeIsRejected(int pid, int session, long birth, string name, bool exited)
        => Assert.Throws<InvalidOperationException>(() => new UpgradeSessionBinding(3, 42, 1).VerifyGame(pid, session, birth, name, exited));

    /// <summary>Both supported game names remain valid only with all exact native identity fields.</summary>
    [Fact]
    public void ExactExistingGameFactsAreAccepted()
    {
        var binding = new UpgradeSessionBinding(3, 42, 1);
        binding.VerifyGame(42, 3, 1, "GenshinImpact", false);
        binding.VerifyGame(42, 3, 1, "YuanShen", false);
    }

    /// <summary>The held path returns an incomplete cancellable task; it does not synchronously block service construction.</summary>
    [Fact]
    public async Task StartupHoldIsCancelableAndCannotAdmitWork()
    {
        var hold = new PuloniaStartupHold(true);
        using var stopped = new CancellationTokenSource();
        var waiting = hold.WaitAsync(stopped.Token);
        Assert.False(waiting.IsCompleted);
        Assert.Throws<InvalidOperationException>(hold.RequireReleased);
        stopped.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => waiting);
        Assert.True(hold.IsHeld);
        Assert.True(new PuloniaStartupHold(false).WaitAsync(CancellationToken.None).IsCompletedSuccessfully);
    }

    /// <summary>Actual service construction/exit behind the hold leaves opaque legacy bytes and backups untouched.</summary>
    [Fact]
    public async Task HeldCoordinatorDoesNotRecoverOrPublishLegacyStore()
    {
        var directory = Path.Combine(Path.GetTempPath(), "root-upgrade-store-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var path = Path.Combine(directory, "state.json");
            var bytes = "opaque legacy or partial state; deliberately not parsed"u8.ToArray();
            await File.WriteAllBytesAsync(path, bytes);
            using var store = new PuloniaTaskStore(directory);
            var service = new PuloniaTaskService(store, new PuloniaTaskBuilder(store), [],
                new PuloniaGameTaskCoordinator(null!), new TaskStopService(NullLogger<TaskStopService>.Instance),
                startupHold: new PuloniaStartupHold(true));
            // App registers the interface factory only. Resume must use that same coordinator, not another concrete owner.
            using var services = new ServiceCollection().AddSingleton<IPuloniaTaskService>(service).BuildServiceProvider();
            Assert.Same(service, ExternalControlService.UpgradeCoordinator(services));
            await Assert.ThrowsAsync<InvalidOperationException>(() => service.EnqueueAsync(new PuloniaTaskRequest { PlanId = "plan" }));
            await Assert.ThrowsAsync<InvalidOperationException>(() => service.CheckTriggersAsync([]));
            await service.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(2));
            Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
            Assert.False(File.Exists(path + ".bak"));
            Assert.False(File.Exists(path + ".schema2.original"));
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    /// <summary>Explicit initialization does not release the execution hold or erase unresolved legacy ownership.</summary>
    [Fact]
    public async Task IncompatibleStateRefusesExplicitResumeAndPreservesFiles()
    {
        var directory = Path.Combine(Path.GetTempPath(), "upgrade-resume-incompatible-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var state = Newtonsoft.Json.Linq.JObject.Parse(PuloniaTaskJson.WriteState(new PuloniaTaskState()));
            state["schema_version"] = 2;
            state["uncertain_operations"] = new Newtonsoft.Json.Linq.JArray(new Newtonsoft.Json.Linq.JObject { ["operation_id"] = "unresolved" });
            var path = Path.Combine(directory, "state.json");
            var bytes = System.Text.Encoding.UTF8.GetBytes(state.ToString());
            await File.WriteAllBytesAsync(path, bytes);
            using var store = new PuloniaTaskStore(directory);
            var hold = new PuloniaStartupHold(true);
            await using var service = new PuloniaTaskService(store, new PuloniaTaskBuilder(store), [],
                new PuloniaGameTaskCoordinator(null!), new TaskStopService(NullLogger<TaskStopService>.Instance), startupHold: hold);
            await Assert.ThrowsAnyAsync<InvalidOperationException>(() => service.PrepareUpgradeResumeAsync(CancellationToken.None));
            Assert.True(hold.IsHeld);
            Assert.False(hold.WaitAsync(CancellationToken.None).IsCompleted);
            Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    /// <summary>An exception from the first irreversible native attempt cannot release gates or permit another attempt.</summary>
    [Fact]
    public async Task UncertainRetirementKeepsReservationAndSchedulesChildExit()
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var attempts = 0;
        var releases = 0;
        var shutdowns = 0;
        var first = new InvalidOperationException("synthetic Kill failure");
        var seen = await Assert.ThrowsAsync<InvalidOperationException>(() => reservation.GuardRequestAsync(() =>
        {
            reservation.TryLaunch<object>(() => true, () => releases++, () => false,
                () => { attempts++; throw first; }, commitBeforeLaunch: true);
            return Task.CompletedTask;
        }, () => shutdowns++));
        Assert.Same(first, seen);
        Assert.True(reservation.Committed);
        Assert.Equal(0, tasks.CurrentCount);
        Assert.Equal(0, releases);
        Assert.Equal(1, shutdowns);
        Assert.Null(reservation.TryLaunch<object>(() => true, () => releases++, () => false, () => { attempts++; return new(); }));
        Assert.Equal(1, attempts);
    }

    /// <summary>A busy pre-attempt check releases only the reservation it acquired; no retirement is attempted.</summary>
    [Fact]
    public void BusyRetirementReleasesOnlyItsUncommittedReservation()
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var releases = 0;
        Assert.Null(reservation.TryLaunch<object>(() => true, () => releases++, () => true,
            () => throw new Exception("must not attempt"), commitBeforeLaunch: true));
        Assert.False(reservation.BlocksAdmission);
        Assert.Equal(1, tasks.CurrentCount);
        Assert.Equal(1, releases);
    }

    /// <summary>Ordinary restart still commits only after a successful non-null launch.</summary>
    [Fact]
    public void OrdinaryFailedLaunchKeepsItsOriginalRollbackBoundary()
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var releases = 0;
        Assert.Throws<InvalidOperationException>(() => reservation.TryLaunch<object>(() => true, () => releases++, () => false,
            () => throw new InvalidOperationException("launch refused")));
        Assert.False(reservation.Committed);
        Assert.Equal(1, releases);
        Assert.Equal(1, tasks.CurrentCount);
    }

    /// <summary>Wire presence/type guards precede process/file access and reject cross-command data.</summary>
    [Fact]
    public void RootExpectationRejectsNullMissingAndCrossCommandUse()
    {
        var json = "{\"version\":1,\"requestId\":\"" + Guid.NewGuid() + "\",\"createdAtUnixMs\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            + ",\"targetProcessId\":12,\"targetWindowsSessionId\":3,\"targetNonce\":\"n\",\"command\":\"retireRootForUpgrade\"";
        foreach (var suffix in new[] { "}", ",\"rootUpgrade\":null}" })
        {
            var request = JsonSerializer.Deserialize<ExternalControlRequest>(json + suffix, ExternalControlProtocol.JsonOptions)!;
            Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request, DateTimeOffset.UtcNow));
        }
        var other = JsonSerializer.Deserialize<ExternalControlRequest>((json + ",\"rootUpgrade\":null}").Replace("retireRootForUpgrade", "stopPilot"), ExternalControlProtocol.JsonOptions)!;
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(other, DateTimeOffset.UtcNow));
    }

    /// <summary>The pinned-hash branch needs both exact binaries; it does not weaken legacy task-manifest validation.</summary>
    [Fact]
    public void PinnedPackageValidationIsSeparateFromFixedRecoveryTask()
    {
        var root = Path.Combine(Path.GetTempPath(), "root-upgrade-package-" + Guid.NewGuid().ToString("N"));
        var app = Path.Combine(root, "artifacts", "release-r1", "BetterGI-English-win-x64");
        Directory.CreateDirectory(Path.Combine(root, ".git"));
        Directory.CreateDirectory(Path.Combine(app, "User", "ExternalControl"));
        try
        {
            File.WriteAllText(Path.Combine(app, "User", "ExternalControl", "enable-quest-control.json"), "{\"version\":1,\"enabled\":true,\"allowAppRestart\":true}");
            File.WriteAllBytes(Path.Combine(app, "BetterGI.exe"), [1, 2]);
            File.WriteAllBytes(Path.Combine(app, "BetterGI.dll"), [3, 4]);
            var exe = Convert.ToHexString(SHA256.HashData(new byte[] { 1, 2 })).ToLowerInvariant();
            var dll = Convert.ToHexString(SHA256.HashData(new byte[] { 3, 4 })).ToLowerInvariant();
            var plan = ExternalControlRecovery.CreateValidatedRecoveryPlan(app, exe, dll);
            var expected = new RootUpgradeExpectation { ProcessId = 1, WindowsSessionId = 2, StartedFileTime = 3,
                AppDirectory = app, ExeSha256 = exe, DllSha256 = dll };
            expected.Verify(1, 2, 3, app, plan.ExeSha256, plan.DllSha256);
            Assert.Throws<InvalidOperationException>(() => expected.Verify(1, 2, 4, app, exe, dll));
            Assert.Throws<InvalidOperationException>(() => (expected with { ExeSha256 = new string('0', 64) }).Verify(1, 2, 3, app, exe, dll));
            Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(app, exe, null));
            Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(app, exe, new string('0', 64)));
            Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(app));
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
