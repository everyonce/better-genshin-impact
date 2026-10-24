using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise restart ownership and response failures without processes, capture, game input, or a WPF application.</summary>
public sealed class IdleRestartReservationTests
{
    /// <summary>Service construction and read-only request handling must not initialize application task facilities.</summary>
    [Fact]
    public async Task ReadOnlyRequestDoesNotResolveTaskSemaphore()
    {
        var reservation = new ExternalControlRestartReservation(() => throw new Exception("No restart was requested."));
        Assert.False(reservation.BlocksAdmission);
        await reservation.GuardRequestAsync(() => Task.CompletedTask, () => throw new Exception("No shutdown was committed."));
    }

    /// <summary>A task that wins admission must remain untouched and prevent the replacement launch.</summary>
    [Fact]
    public void ExistingTaskCannotBeInterruptedByRestart()
    {
        using var tasks = new SemaphoreSlim(0, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        Assert.Null(reservation.TryLaunch(() => throw new Exception("runtime must not be reserved"),
            () => throw new Exception("no runtime reservation"), () => false, () => new object()));
        Assert.Equal(0, tasks.CurrentCount);
        Assert.False(reservation.BlocksAdmission);
    }

    /// <summary>All no-launch paths restore both owned gates, including cancellation and a failed Process.Start equivalent.</summary>
    [Theory]
    [InlineData("runtime_busy")]
    [InlineData("other_work")]
    [InlineData("null_launch")]
    [InlineData("throw_launch")]
    [InlineData("cancel_launch")]
    public void PrecommitFailureReleasesBothReservations(string failure)
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var runtimeHeld = false;
        var released = 0;
        object? Launch() => failure switch
        {
            "throw_launch" => throw new InvalidOperationException("launch failed"),
            "cancel_launch" => throw new OperationCanceledException(),
            _ => null
        };
        try
        {
            Assert.Null(reservation.TryLaunch(() => runtimeHeld = failure != "runtime_busy",
                () => { runtimeHeld = false; released++; }, () => failure == "other_work", Launch));
        }
        catch (Exception exception) when (failure is "throw_launch" or "cancel_launch")
        {
            Assert.IsAssignableFrom<Exception>(exception);
        }
        Assert.False(runtimeHeld);
        Assert.Equal(failure == "runtime_busy" ? 0 : 1, released);
        Assert.Equal(1, tasks.CurrentCount);
        Assert.False(reservation.BlocksAdmission);
        Assert.False(reservation.Committed);
    }

    /// <summary>The final busy check runs with both gates already held, so no worker task can acquire in the launch gap.</summary>
    [Fact]
    public async Task CommittedLaunchKeepsTaskAndRuntimeAdmissionClosed()
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var runtimeHeld = false;
        var process = new object();
        Assert.Same(process, reservation.TryLaunch(() => runtimeHeld = true, () => runtimeHeld = false,
            () => { Assert.Equal(0, tasks.CurrentCount); Assert.True(runtimeHeld); return false; }, () => process));
        Assert.True(reservation.Committed);
        Assert.True(reservation.BlocksAdmission);
        Assert.False(await Task.Run(() => tasks.Wait(0)));
        Assert.Null(reservation.TryLaunch(() => throw new Exception("no second admission"), () => { }, () => false, () => new object()));
        Assert.True(runtimeHeld);
        Assert.Equal(0, tasks.CurrentCount);
    }

    /// <summary>Response construction, serialization, write, and cancellation all retain the shutdown obligation after launch.</summary>
    [Theory]
    [InlineData("status")]
    [InlineData("serialization")]
    [InlineData("write")]
    [InlineData("cancellation")]
    public async Task EveryPostcommitResponseFailureStillSchedulesShutdown(string stage)
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var runtimeHeld = false;
        var shutdown = 0;
        await Assert.ThrowsAnyAsync<Exception>(() => reservation.GuardRequestAsync(async () =>
        {
            Assert.NotNull(reservation.TryLaunch(() => runtimeHeld = true, () => runtimeHeld = false,
                () => false, () => new object()));
            await Task.Yield();
            throw stage switch
            {
                "serialization" => new JsonException("response serialization failed"),
                "write" => new IOException("pipe write failed"),
                "cancellation" => new OperationCanceledException("request deadline"),
                _ => new InvalidOperationException("status construction failed")
            };
        }, () => shutdown++));
        Assert.Equal(1, shutdown);
        Assert.True(reservation.Committed);
        Assert.True(runtimeHeld);
        Assert.Equal(0, tasks.CurrentCount);
    }

    /// <summary>A failed request that never launches must not shut down an otherwise healthy child.</summary>
    [Fact]
    public async Task PrecommitResponseFailureDoesNotScheduleShutdown()
    {
        using var tasks = new SemaphoreSlim(1, 1);
        var reservation = new ExternalControlRestartReservation(tasks);
        var shutdown = 0;
        await Assert.ThrowsAsync<IOException>(() => reservation.GuardRequestAsync(
            () => throw new IOException("before launch"), () => shutdown++));
        Assert.Equal(0, shutdown);
        Assert.Equal(1, tasks.CurrentCount);
    }

    /// <summary>Exercise the actual queued runtime-start body after its stop wait without initializing application services.</summary>
    [Fact]
    public async Task QueuedRuntimeStartRechecksReservationAfterItsWaits()
    {
        var runtime = (GameRuntimeService)RuntimeHelpers.GetUninitializedObject(typeof(GameRuntimeService));
        using var startLock = new SemaphoreSlim(1, 1);
        var stopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
        typeof(GameRuntimeService).GetField("_startLock", flags)!.SetValue(runtime, startLock);
        typeof(GameRuntimeService).GetField("_stopTask", flags)!.SetValue(runtime, stopped.Task);
        var pending = (Task<GameRuntime?>)typeof(GameRuntimeService).GetMethod("StartCoreAsync", flags)!
            .Invoke(runtime, [CancellationToken.None, 0L])!;
        Assert.False(pending.IsCompleted);
        typeof(GameRuntimeService).GetField("_restartReserved", flags)!.SetValue(runtime, true);
        stopped.SetResult();
        Assert.Null(await pending);
        Assert.Equal(1, startLock.CurrentCount);
    }

    /// <summary>Only a pinned restart may carry a complete version-one expectation; omission retains legacy protocol behavior.</summary>
    [Fact]
    public void ContractRequiresExactCommandAndTargetPins()
    {
        var now = DateTimeOffset.UtcNow;
        var request = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(), Command = "restartApp",
            CreatedAtUnixMs = now.ToUnixTimeMilliseconds(), TargetProcessId = 1, TargetWindowsSessionId = 3, TargetNonce = "child" };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
        var expected = new ExternalControlIdleRestart { Version = 1, TargetDirectory = @"D:\artifacts\release-r19\BetterGI-English-win-x64",
            ExeSha256 = new string('a', 64), DllSha256 = new string('b', 64) };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request with { IdleRestart = expected }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Command = "startPilot", IdleRestart = expected }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request with { IdleRestart = null }, now));
        foreach (var invalid in new[] { expected with { Version = 2 }, expected with { TargetDirectory = "relative" },
                     expected with { ExeSha256 = "bad" }, expected with { DllSha256 = null } })
            Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request with { IdleRestart = invalid }, now));
        using var wire = JsonDocument.Parse(ExternalControlProtocol.SerializeResponse(new ExternalControlResponse {
            Status = new ExternalControlStatus { IdleRestartVersion = 1 } }));
        Assert.Equal(1, wire.RootElement.GetProperty("status").GetProperty("idleRestartVersion").GetInt32());
    }

    /// <summary>Another invocation can overwrite the shared manifest, but cannot redirect a request-bound launch.</summary>
    [Fact]
    public void ConcurrentManifestReplacementCannotRedirectPreparedTarget()
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-idle-restart-" + Guid.NewGuid().ToString("N"));
        try
        {
            var current = Path.Combine(root, "release-r18", "BetterGI-English-win-x64");
            Directory.CreateDirectory(Path.Combine(current, "User", "ExternalControl"));
            ExternalControlIdleRestart Package(int number)
            {
                var target = Path.Combine(root, "release-r" + number, "BetterGI-English-win-x64");
                Directory.CreateDirectory(Path.Combine(target, "User", "ExternalControl"));
                File.WriteAllText(Path.Combine(target, "BetterGI.exe"), "synthetic executable " + number);
                File.WriteAllText(Path.Combine(target, "BetterGI.dll"), "synthetic assembly " + number);
                File.WriteAllText(Path.Combine(target, "User", "ExternalControl", "enable-quest-control.json"),
                    "{\"version\":1,\"enabled\":true,\"allowAppRestart\":true}");
                return new ExternalControlIdleRestart { Version = 1, TargetDirectory = target,
                    ExeSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(target, "BetterGI.exe")))),
                    DllSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(target, "BetterGI.dll")))) };
            }
            var first = Package(19);
            var second = Package(20);
            var manifest = Path.Combine(current, ExternalControlRestart.ManifestPath);
            File.WriteAllText(manifest, JsonSerializer.Serialize(first));
            var prepared = ExternalControlRestart.Prepare(current, 123, true, first);
            File.WriteAllText(manifest, JsonSerializer.Serialize(second));
            Assert.Equal(first.TargetDirectory, prepared.WorkingDirectory);
            Assert.Throws<InvalidOperationException>(() => ExternalControlRestart.Prepare(current, 123, true, first));
            Assert.Equal(second.TargetDirectory, ExternalControlRestart.Prepare(current, 123, true, second).WorkingDirectory);
            Assert.Equal(second.TargetDirectory, ExternalControlRestart.Prepare(current, 123).WorkingDirectory);
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
