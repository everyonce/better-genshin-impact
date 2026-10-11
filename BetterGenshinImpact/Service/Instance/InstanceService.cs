using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Interop;
using BetterGenshinImpact.Core.Monitor;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.Instance.MessageHandlers;
using BetterGenshinImpact.Service.Interface;
using BetterGenshinImpact.ViewModel.Pages;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Service.Instance;

public sealed class InstanceService : IHostedService, IAsyncDisposable
{
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan ReconnectDelay = TimeSpan.FromSeconds(1);

    private readonly InstanceBootstrap _bootstrap;
    private readonly ILogger<InstanceService> _logger;
    private readonly InstanceMessageState _messageState = new();
    private readonly InstanceRequestHandler _requestHandler;
    private readonly RelativeMouseMessageHandler _relativeMouseMessageHandler;
    private readonly CancellationTokenSource _lifetimeCancellationTokenSource = new();
    private readonly ConcurrentQueue<string[]> _pendingActivations = new();
    private readonly object _activationLock = new();
    private readonly object _rootConnectionLock = new();

    private Task? _acceptLoopTask;
    private Task? _rootConnectionLoopTask;
    private InstanceConnection? _rootConnection;
    private bool _applicationReady;
    private int _stopStarted;

    public InstanceService(
        InstanceBootstrap bootstrap,
        IServiceProvider serviceProvider,
        RawInputMonitor rawInputMonitor,
        IConfigService configService,
        ILogger<InstanceService> logger)
    {
        _bootstrap = bootstrap;
        _logger = logger;
        _relativeMouseMessageHandler = new RelativeMouseMessageHandler(
            Context,
            serviceProvider,
            rawInputMonitor,
            IsRootConnection,
            logger);
        if (Context.InstanceType == BetterGiInstanceType.Primary)
        {
            _relativeMouseMessageHandler.SetGameMouseModeEnabled(
                configService.Get().ChildSessionConfig.GameMouseModeEnabled);
        }
        _requestHandler = new InstanceRequestHandler(
            Context,
            _messageState,
            _relativeMouseMessageHandler,
            EnqueueActivation,
            DispatchWebViewMessage,
            logger);
    }

    public event EventHandler<WebViewMessageReceivedEventArgs>? WebViewMessageReceived;

    public InstanceContext Context => _bootstrap.Context;

    internal bool TryGetConnectedRoot(out InstanceEndpoint? endpoint)
    {
        lock (_rootConnectionLock)
        {
            endpoint = _rootConnection is { } connection && !connection.Completion.IsCompleted
                ? connection.RemoteEndpoint : null;
            return endpoint is { InstanceType: BetterGiInstanceType.Primary, WindowsSessionId: 1, ProcessId: > 0 };
        }
    }

    public bool IsGameMouseModeEnabled =>
        _relativeMouseMessageHandler.IsGameMouseModeEnabled;

    public void SetGameMouseModeEnabled(bool enabled)
    {
        _relativeMouseMessageHandler.SetGameMouseModeEnabled(enabled);
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        if (Context.InstanceType == BetterGiInstanceType.Primary)
        {
            var firstServer = _bootstrap.TakeFirstServer()
                              ?? throw new InvalidOperationException(
                                  "The root instance did not acquire the initial named pipe server.");
            _acceptLoopTask = AcceptLoopAsync(
                firstServer,
                _lifetimeCancellationTokenSource.Token);
        }
        else
        {
            _rootConnectionLoopTask = RootConnectionLoopAsync(
                _bootstrap.TakeFirstRootConnection(),
                _lifetimeCancellationTokenSource.Token);
        }

        _logger.LogInformation(
            "Instance IPC v2 started: {InstanceType}, process {ProcessId}, session {SessionId}, root pipe {PipeName}",
            Context.InstanceType,
            Context.ProcessId,
            Context.WindowsSessionId,
            Context.RootPipeName);
        return Task.CompletedTask;
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        if (Interlocked.Exchange(ref _stopStarted, 1) != 0)
        {
            return;
        }

        _lifetimeCancellationTokenSource.Cancel();
        _relativeMouseMessageHandler.Stop();

        InstanceConnection? rootConnection;
        lock (_rootConnectionLock)
        {
            rootConnection = _rootConnection;
            _rootConnection = null;
        }
        if (rootConnection is not null)
        {
            await rootConnection.DisposeAsync().ConfigureAwait(false);
        }

        var connections = _messageState.BetterGiConnectionsBySession.Values
            .Concat(_messageState.WebViewConnectionsByProcessId.Values)
            .Select(x => x.Connection)
            .Distinct()
            .ToArray();
        foreach (var connection in connections)
        {
            await connection.DisposeAsync().ConfigureAwait(false);
        }

        await AwaitBackgroundTaskAsync(_acceptLoopTask).ConfigureAwait(false);
        await AwaitBackgroundTaskAsync(_rootConnectionLoopTask).ConfigureAwait(false);
    }

    public void MarkApplicationReady()
    {
        var pendingActivations = new List<string[]>();
        lock (_activationLock)
        {
            _applicationReady = true;
            while (_pendingActivations.TryDequeue(out var args))
            {
                pendingActivations.Add(args);
            }
        }

        foreach (var args in pendingActivations)
        {
            DispatchActivation(args);
        }
    }

    public async Task<InstanceEndpoint[]> GetVisibleWebViewsAsync(
        CancellationToken cancellationToken = default)
    {
        if (Context.InstanceType == BetterGiInstanceType.Primary)
        {
            return _messageState.WebViewConnectionsByProcessId.Values
                .Select(x => x.Endpoint)
                .OrderBy(x => x.InstanceName, StringComparer.OrdinalIgnoreCase)
                .ThenBy(x => x.ProcessId)
                .ToArray();
        }
        if (Context.InstanceType == BetterGiInstanceType.WebView)
        {
            return [];
        }

        var rootConnection = GetRequiredRootConnection();
        var response = await rootConnection.SendRequestAsync(
            InstanceOperations.WebViewList,
            null,
            RequestTimeout,
            cancellationToken).ConfigureAwait(false);
        EnsureSuccessfulResponse(response);
        return response.Data?.ToObject<WebViewListResponse>(InstanceIpcProtocol.Serializer)
                   ?.Endpoints
               ?? [];
    }

    public async Task SendWebViewMessageAsync(
        int targetProcessId,
        string operation,
        JToken? data = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(operation))
        {
            throw new ArgumentException("The WebView operation name cannot be empty.", nameof(operation));
        }
        if (Context.InstanceType == BetterGiInstanceType.WebView)
        {
            throw new InvalidOperationException("A WebView cannot send messages to another WebView.");
        }

        if (Context.InstanceType == BetterGiInstanceType.Primary)
        {
            if (!_messageState.WebViewConnectionsByProcessId.TryGetValue(
                    targetProcessId,
                    out var target))
            {
                throw new InvalidOperationException(
                    $"WebView process {targetProcessId} is not currently online.");
            }

            var targetResponse = await target.Connection.SendRequestAsync(
                InstanceOperations.WebViewMessage,
                new WebViewMessage
                {
                    SourceProcessId = Context.ProcessId,
                    Operation = operation,
                    Data = data
                },
                RequestTimeout,
                cancellationToken).ConfigureAwait(false);
            EnsureSuccessfulResponse(targetResponse);
            return;
        }

        var rootConnection = GetRequiredRootConnection();
        var response = await rootConnection.SendRequestAsync(
            InstanceOperations.WebViewSend,
            new WebViewSendRequest
            {
                TargetProcessId = targetProcessId,
                Operation = operation,
                Data = data
            },
            RequestTimeout,
            cancellationToken).ConfigureAwait(false);
        EnsureSuccessfulResponse(response);
    }

    internal async Task<InstanceIpcEnvelope?> HandleRequestAsync(
        InstanceConnection connection,
        InstanceIpcEnvelope request,
        CancellationToken cancellationToken)
    {
        return await _requestHandler.HandleAsync(
            connection,
            request,
            cancellationToken).ConfigureAwait(false);
    }

    internal bool ReceiveRelativeMouseBatch(
        InstanceConnection connection,
        ulong firstSequence,
        IReadOnlyList<RelativeMouseSample> samples)
    {
        return _relativeMouseMessageHandler.HandleBatch(
            connection,
            firstSequence,
            samples);
    }

    internal void ReceiveRelativeMouseResult(
        InstanceConnection connection,
        RelativeMouseResult result)
    {
        _relativeMouseMessageHandler.HandleResult(connection, result);
    }

    private bool IsRootConnection(InstanceConnection connection)
    {
        lock (_rootConnectionLock)
        {
            return ReferenceEquals(_rootConnection, connection);
        }
    }

    internal void ConnectionClosed(InstanceConnection connection)
    {
        if (Context.InstanceType == BetterGiInstanceType.Primary
            && connection.RemoteEndpoint is { } endpoint)
        {
            if (endpoint.InstanceType == BetterGiInstanceType.ChildSession
                && _messageState.BetterGiConnectionsBySession.TryGetValue(
                    endpoint.WindowsSessionId,
                    out var child)
                && ReferenceEquals(child.Connection, connection))
            {
                _messageState.BetterGiConnectionsBySession.TryRemove(
                    endpoint.WindowsSessionId,
                    out _);
                _relativeMouseMessageHandler.RemoveTarget(endpoint.WindowsSessionId);
                _logger.LogInformation(
                    "Desktop session BetterGI disconnected: process {ProcessId}, session {SessionId}",
                    endpoint.ProcessId,
                    endpoint.WindowsSessionId);
            }
            else if (endpoint.InstanceType == BetterGiInstanceType.WebView
                     && _messageState.WebViewConnectionsByProcessId.TryGetValue(
                         endpoint.ProcessId,
                         out var webView)
                     && ReferenceEquals(webView.Connection, connection))
            {
                _messageState.WebViewConnectionsByProcessId.TryRemove(
                    endpoint.ProcessId,
                    out _);
                _logger.LogInformation(
                    "WebView disconnected: process {ProcessId}, session {SessionId}",
                    endpoint.ProcessId,
                    endpoint.WindowsSessionId);
            }
        }

        lock (_rootConnectionLock)
        {
            if (ReferenceEquals(_rootConnection, connection))
            {
                _rootConnection = null;
            }
        }

        _ = connection.DisposeAsync().AsTask();
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync(CancellationToken.None).ConfigureAwait(false);
        _lifetimeCancellationTokenSource.Dispose();
        _bootstrap.Dispose();
    }

    private async Task AcceptLoopAsync(
        NamedPipeServerStream firstServer,
        CancellationToken cancellationToken)
    {
        NamedPipeServerStream? server = firstServer;
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                server ??= InstancePipeFactory.CreateServer(
                    Context.RootPipeName,
                    firstPipeInstance: false);
                try
                {
                    await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    break;
                }

                var connection = new InstanceConnection(server, this, _logger);
                server = null;
                connection.Start(cancellationToken);
                _ = ObserveAcceptedConnectionAsync(connection);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            if (!cancellationToken.IsCancellationRequested)
            {
                _logger.LogError(exception, "Root instance named pipe listener terminated unexpectedly");
            }
        }
        finally
        {
            server?.Dispose();
        }
    }

    private static async Task ObserveAcceptedConnectionAsync(InstanceConnection connection)
    {
        await connection.Completion.ConfigureAwait(false);
    }

    private async Task RootConnectionLoopAsync(
        InitialRootConnection? initialRootConnection,
        CancellationToken cancellationToken)
    {
        var pendingInitialConnection = initialRootConnection;
        var includeActivationArguments = pendingInitialConnection is null;
        var restartFromProcessId = CommandLineOptions.Instance.RestartFromProcessId;

        while (!cancellationToken.IsCancellationRequested)
        {
            InstanceConnection? connection = null;
            try
            {
                ConnectionOpenResponse openResponse;
                if (pendingInitialConnection is not null)
                {
                    openResponse = pendingInitialConnection.Response;
                    connection = new InstanceConnection(
                        pendingInitialConnection.Client,
                        this,
                        _logger);
                    pendingInitialConnection = null;
                }
                else
                {
                    var client = new NamedPipeClientStream(
                        ".",
                        Context.RootPipeName,
                        PipeDirection.InOut,
                        PipeOptions.Asynchronous | PipeOptions.WriteThrough);
                    await client.ConnectAsync(cancellationToken).ConfigureAwait(false);
                    connection = new InstanceConnection(client, this, _logger);
                    connection.Start(cancellationToken);

                    var openResult = await connection.SendRequestAsync(
                        InstanceOperations.ConnectionOpen,
                        new ConnectionOpenRequest
                        {
                            RequestedType = Context.InstanceType,
                            InstanceName = Context.InstanceName,
                            RestartFromProcessId = restartFromProcessId,
                            Arguments = includeActivationArguments
                                ? Environment.GetCommandLineArgs()
                                : []
                        },
                        RequestTimeout,
                        cancellationToken).ConfigureAwait(false);
                    EnsureSuccessfulResponse(openResult);
                    openResponse =
                        openResult.Data?.ToObject<ConnectionOpenResponse>(
                            InstanceIpcProtocol.Serializer)
                        ?? throw new InvalidDataException("The root instance connection response is missing data.");
                }

                if (openResponse.Disposition
                    == ConnectionOpenDisposition.ActivationForwarded)
                {
                    RequestApplicationShutdown();
                    return;
                }
                if (openResponse.AssignedType != Context.InstanceType)
                {
                    throw new InvalidOperationException(
                        $"The root instance assigned a mismatched client type: {openResponse.AssignedType}.");
                }

                Context.SetRootSessionId(openResponse.RootSessionId);
                if (!connection.HasServerIdentity(openResponse.RootProcessId, openResponse.RootSessionId))
                    throw new IOException("The connected root pipe does not match the registered root process and session.");
                DateTimeOffset rootStartedAt = default;
                try
                {
                    using var rootProcess = Process.GetProcessById(openResponse.RootProcessId);
                    rootStartedAt = new DateTimeOffset(rootProcess.StartTime.ToUniversalTime());
                }
                catch (Exception exception) when (exception is ArgumentException or InvalidOperationException or Win32Exception)
                {
                    _logger.LogDebug(exception, "Root process creation time is unavailable; external host restart will be disabled.");
                }
                connection.RemoteEndpoint = new InstanceEndpoint
                {
                    InstanceType = BetterGiInstanceType.Primary,
                    ProcessId = openResponse.RootProcessId,
                    WindowsSessionId = openResponse.RootSessionId,
                    StartedAt = rootStartedAt
                };
                if (!connection.IsStarted)
                {
                    connection.Start(cancellationToken);
                }
                if (connection.Completion.IsCompleted)
                {
                    throw new IOException("The root instance connection closed before registration completed.");
                }

                lock (_rootConnectionLock)
                {
                    _rootConnection = connection;
                }

                includeActivationArguments = false;
                restartFromProcessId = null;
                _logger.LogInformation(
                    "Connected to the BetterGI root instance: process {ProcessId}, session {SessionId}",
                    openResponse.RootProcessId,
                    openResponse.RootSessionId);

                if (Context.InstanceType == BetterGiInstanceType.ChildSession)
                {
                    var subscribeResponse = await connection.SendRequestAsync(
                        InstanceOperations.RelativeMouseSubscribe,
                        null,
                        RequestTimeout,
                        cancellationToken).ConfigureAwait(false);
                    EnsureSuccessfulResponse(subscribeResponse);
                }

                await connection.Completion.ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is IOException
                                              or UnauthorizedAccessException
                                              or TimeoutException
                                              or OperationCanceledException
                                              or ObjectDisposedException)
            {
                if (!cancellationToken.IsCancellationRequested)
                {
                    _logger.LogWarning(
                        exception,
                        "Failed to connect to the BetterGI root instance; retrying later: {PipeName}",
                        Context.RootPipeName);
                }
            }
            catch (Exception exception) when (exception is InvalidOperationException
                                              or InvalidDataException)
            {
                if (!cancellationToken.IsCancellationRequested)
                {
                    _logger.LogError(
                        exception,
                        "Unrecoverable protocol error while connecting to the BetterGI root instance; stopping retries: {PipeName}",
                        Context.RootPipeName);
                    RequestApplicationShutdown();
                }
                return;
            }
            finally
            {
                lock (_rootConnectionLock)
                {
                    if (ReferenceEquals(_rootConnection, connection))
                    {
                        _rootConnection = null;
                    }
                }

                if (connection is not null)
                {
                    await connection.DisposeAsync().ConfigureAwait(false);
                }
            }

            if (!cancellationToken.IsCancellationRequested)
            {
                await Task.Delay(ReconnectDelay, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private InstanceConnection GetRequiredRootConnection()
    {
        lock (_rootConnectionLock)
        {
            return _rootConnection
                   ?? throw new InvalidOperationException("Not currently connected to a BetterGI root instance.");
        }
    }

    private void EnqueueActivation(string[] args)
    {
        lock (_activationLock)
        {
            if (!_applicationReady)
            {
                _pendingActivations.Enqueue(args);
                return;
            }
        }

        DispatchActivation(args);
    }

    private void DispatchActivation(string[] args)
    {
        Application.Current?.Dispatcher.BeginInvoke(new Action(() =>
        {
            var mainWindow = Application.Current.MainWindow;
            mainWindow?.Show();
            mainWindow?.Activate();
            if (mainWindow is not null)
            {
                SystemControl.RestoreWindow(new WindowInteropHelper(mainWindow).Handle);
            }

            var commandLineOptions = CommandLineOptions.Parse(args);
            App.GetService<HomePageViewModel>()?.HandleActivation(commandLineOptions);
        }));
    }

    private void DispatchWebViewMessage(WebViewMessage message)
    {
        WebViewMessageReceived?.Invoke(
            this,
            new WebViewMessageReceivedEventArgs(
                message.SourceProcessId,
                message.Operation,
                message.Data));
    }

    private static void RequestApplicationShutdown()
    {
        var application = Application.Current;
        if (application is null)
        {
            Environment.Exit(0);
            return;
        }

        _ = application.Dispatcher.BeginInvoke(new Action(application.Shutdown));
    }

    private static void EnsureSuccessfulResponse(InstanceIpcEnvelope response)
    {
        if (response.Success == true)
        {
            return;
        }

        throw new InvalidOperationException(
            response.ErrorMessage ?? response.ErrorCode ?? "The instance IPC request failed.");
    }

    private static async Task AwaitBackgroundTaskAsync(Task? task)
    {
        if (task is null)
        {
            return;
        }
        try
        {
            await task.ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is IOException
                                          or OperationCanceledException
                                          or ObjectDisposedException)
        {
            // HostedService 停止期间的正常清理。
        }
    }
}

public sealed class WebViewMessageReceivedEventArgs(
    int sourceProcessId,
    string operation,
    JToken? data) : EventArgs
{
    public int SourceProcessId { get; } = sourceProcessId;

    public string Operation { get; } = operation;

    public JToken? Data { get; } = data;
}
