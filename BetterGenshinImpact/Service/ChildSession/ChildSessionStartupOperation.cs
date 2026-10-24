using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Helpers;

namespace BetterGenshinImpact.Service.ChildSession;

/// <summary>One immutable startup intent shared by the connection continuation and login callback.</summary>
internal sealed class ChildSessionStartupOperation(long generation, string mode, CancellationToken cancellationToken)
{
    /// <summary>Start only BetterGI's authenticated endpoint, without attaching or launching Genshin.</summary>
    internal const string ControlEndpoint = "controlEndpoint";
    /// <summary>Start the automated child and its game lifecycle.</summary>
    internal const string GameRuntime = "gameRuntime";
    /// <summary>Exact operation generation; delayed callbacks cannot adopt a subsequent request.</summary>
    internal long Generation { get; } = generation;
    /// <summary>Validated mode remains fixed for the operation's lifetime.</summary>
    internal string Mode { get; } = IsSupported(mode) ? mode : throw new ArgumentException("Unsupported child startup mode.", nameof(mode));
    /// <summary>The startup workflow owns cancellation, independently of a control pipe request.</summary>
    internal CancellationToken CancellationToken { get; } = cancellationToken;
    /// <summary>Retain the first launch outcome, including uncertain failure, rather than redispatching.</summary>
    private Task? _dispatch;

    /// <summary>Strict wire values; omitted requests are normalized separately to the legacy game startup.</summary>
    internal static bool IsSupported(string? mode) => mode is ControlEndpoint or GameRuntime;

    /// <summary>Automation without a start action is endpoint-only; explicit start retains game startup.</summary>
    internal static string FromAction(CommandLineAction action) => action == CommandLineAction.Start ? GameRuntime : ControlEndpoint;

    /// <summary>A game request can finish an endpoint bootstrap explicitly; endpoint-only requests cannot join game startup.</summary>
    internal static bool CanJoin(string requested, string? active) => IsSupported(requested) && IsSupported(active)
        && (requested == GameRuntime || active == ControlEndpoint);

    /// <summary>Validate the captured generation after acquiring the shared launch gate, then dispatch at most once.</summary>
    internal async Task DispatchAsync(SemaphoreSlim gate, Func<bool> isCurrent, Func<Task> dispatch)
    {
        await gate.WaitAsync(CancellationToken);
        try
        {
            CancellationToken.ThrowIfCancellationRequested();
            if (!isCurrent()) throw new OperationCanceledException("The child startup operation was superseded.");
            _dispatch ??= InvokeAsync(dispatch);
            await _dispatch;
        }
        finally { gate.Release(); }
    }

    /// <summary>Preserve a synchronous launch exception as the shared terminal outcome too.</summary>
    private static async Task InvokeAsync(Func<Task> dispatch) => await dispatch();
}
