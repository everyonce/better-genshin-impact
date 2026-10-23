using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using BetterGenshinImpact.Helpers;
using Microsoft.Extensions.Logging;
using Microsoft.Win32;

namespace BetterGenshinImpact.Service.ChildSession;

/// <summary>Explicit automation entry points; all UI/session state changes remain on the WPF dispatcher.</summary>
public sealed partial class ChildSessionService
{
    /// <summary>Prevent reconnects or notifications from restoring the host without an explicit show request.</summary>
    private bool _automationKeepMinimized = CommandLineOptions.Instance.AutomationMode;
    /// <summary>One bounded connection/child launch at a time.</summary>
    private Task? _automationStartTask;
    /// <summary>Cancel the currently pending connection without logging off an existing child session.</summary>
    private CancellationTokenSource? _automationStartCancellation;

    /// <summary>Machine-readable connection/launch result, independent of localized UI status text.</summary>
    public string AutomationState { get; private set; } = "idle";
    /// <summary>Last structured workflow failure; credentials are never included.</summary>
    public string? AutomationError { get; private set; }
    /// <summary>Whether the host window is currently minimized; query only on the UI dispatcher.</summary>
    public bool IsWindowMinimized => _desktopWindow?.WindowState == WindowState.Minimized;

    /// <summary>Start the real RDP connection and its BetterGI child without blocking the control pipe.</summary>
    public void BeginAutomationStart()
    {
        ThrowIfDisposed();
        if (!CommandLineOptions.Instance.AutomationMode || !_instanceService.Context.IsRoot)
            throw new InvalidOperationException("RDP automation requires an explicitly automated primary instance.");
        if (_automationStartTask is { IsCompleted: false }) return;
        _automationStartCancellation?.Dispose();
        _automationStartCancellation = new CancellationTokenSource(TimeSpan.FromSeconds(75));
        _automationStartTask = StartAutomationCoreAsync(_automationStartCancellation.Token);
    }

    /// <summary>Cancel a pending connection; preserve the Windows session, its game, and logged-in applications.</summary>
    public void CancelAutomationStart()
    {
        _automationStartCancellation?.Cancel();
    }

    /// <summary>Minimize without disconnecting RDP or stealing main-desktop focus.</summary>
    public void MinimizeWindow()
    {
        ThrowIfDisposed();
        _automationKeepMinimized = true;
        ShowDesktopWindow(EnsureDesktopWindow());
        RefreshState("RDP host minimized; connection remains active.");
    }

    /// <summary>Run standard-token work only in the currently connected child session.</summary>
    public Task LaunchStandardCommandAsync(uint expectedSessionId, string executablePath,
        IReadOnlyList<string> arguments, string workingDirectory)
    {
        ThrowIfDisposed();
        RefreshState();
        var actualSessionId = GetRequiredChildSessionId();
        if (!_instanceService.Context.IsRoot || ConnectedState != 1
            || actualSessionId != expectedSessionId || actualSessionId == _instanceService.Context.WindowsSessionId)
            throw new InvalidOperationException("The requested connected child session is no longer available.");
        return ChildSessionProcessLauncher.LaunchStandardAsync(actualSessionId, executablePath, arguments, workingDirectory);
    }

    /// <summary>Keep the existing credential UI/authentication flow while reporting failures to automation callers.</summary>
    private async Task StartAutomationCoreAsync(CancellationToken cancellationToken)
    {
        AutomationState = "connecting";
        AutomationError = null;
        try
        {
            // This per-user RDP client setting retains display updates while minimized.
            // It does not unlock Windows, authenticate, or bypass the server's RDP guard.
            using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Terminal Server Client"))
                key.SetValue("RemoteDesktop_SuppressWhenMinimized", 2, RegistryValueKind.DWord);
            MinimizeWindow();
            await StartAsync(cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            RefreshState();
            if (ConnectedState != 1 || ChildSessionId is null)
            {
                AutomationState = "connection_failed";
                AutomationError = _lastConnectionFailure is null
                    ? "RDP login did not complete. Use showChildSession for the normal Windows login UI."
                    : $"RDP connection failed ({_lastConnectionFailure.ErrorCode}). {_lastConnectionFailure.Message}";
                return;
            }
            AutomationState = "launching_child";
            await LaunchBetterGiAsync();
            cancellationToken.ThrowIfCancellationRequested();
            AutomationState = "child_launch_dispatched";
        }
        catch (OperationCanceledException)
        {
            _autoLaunchBetterGiPending = false;
            _initialConnectionRetriesRemaining = 0;
            AutomationState = "cancelled";
            AutomationError = "RDP startup was cancelled or exceeded its 75-second deadline.";
        }
        catch (Exception exception)
        {
            AutomationState = "failed";
            AutomationError = exception.GetBaseException().Message;
            _logger.LogWarning(exception, "Automated RDP startup failed");
        }
        finally
        {
            if (!_disposed) RefreshState();
        }
    }

    /// <summary>Reconnections must not restore a host explicitly kept minimized.</summary>
    private void OnAutomationWindowStateChanged(object? sender, EventArgs e)
    {
        if (_automationKeepMinimized && _desktopWindow is { WindowState: not WindowState.Minimized })
            _desktopWindow.WindowState = WindowState.Minimized;
    }
}
