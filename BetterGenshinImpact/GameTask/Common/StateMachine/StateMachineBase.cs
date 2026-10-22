using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.GameTask.Runtime;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.Common.StateMachine;

using static TaskControl;

/// <summary>
/// 状态处理器基础结果。
/// </summary>
public enum StateHandlerStatus
{
    Success,
    Wait,
    Retry,
    Fail
}

/// <summary>
/// 状态处理器返回结果，决定状态机如何处理当前状态。
/// 可通过 SuccessTo 指定本次动作允许到达的邻接状态。
/// </summary>
public readonly struct StateHandlerResult
{
    private StateHandlerResult(StateHandlerStatus status, IReadOnlyList<Enum> targetStates)
    {
        Status = status;
        TargetStates = targetStates;
    }

    /// <summary>
    /// 基础处理结果。
    /// </summary>
    public StateHandlerStatus Status { get; }

    /// <summary>
    /// 本次动作允许到达的目标状态集合。
    /// 空集合表示使用当前状态的全部邻接状态。
    /// </summary>
    public IReadOnlyList<Enum> TargetStates { get; }

    public static StateHandlerResult Success { get; } = Create(StateHandlerStatus.Success);

    public static StateHandlerResult Wait { get; } = Create(StateHandlerStatus.Wait);

    public static StateHandlerResult Retry { get; } = Create(StateHandlerStatus.Retry);

    public static StateHandlerResult Fail { get; } = Create(StateHandlerStatus.Fail);

    /// <summary>
    /// 创建成功结果，并将目标收窄到当前状态图中的指定邻接状态。
    /// </summary>
    public static StateHandlerResult SuccessTo<TState>(params TState[] targetStates)
        where TState : struct, Enum
    {
        if (targetStates == null || targetStates.Length == 0)
        {
            throw new ArgumentException("SuccessTo requires at least one target state", nameof(targetStates));
        }

        var distinctTargets = targetStates
            .Cast<Enum>()
            .Distinct()
            .ToArray();
        return new StateHandlerResult(StateHandlerStatus.Success, Array.AsReadOnly(distinctTargets));
    }

    private static StateHandlerResult Create(StateHandlerStatus status)
    {
        return new StateHandlerResult(status, Array.Empty<Enum>());
    }
}

/// <summary>
/// 状态处理器委托
/// </summary>
public delegate Task<StateHandlerResult> StateHandlerDelegate<in TContext>(TContext context);

/// <summary>
/// 状态检测器标记。检测器方法签名必须为 bool Method(ImageRegion ra)。
/// </summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class StateDetectorAttribute(object state) : Attribute
{
    public object State { get; } = state;

    /// <summary>
    /// 检测顺序，数值越小越先检测。
    /// </summary>
    public int Order { get; set; }
}

/// <summary>
/// 状态处理器标记。处理器方法签名必须为 Task&lt;StateHandlerResult&gt; Method(TContext context)。
/// </summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class StateHandlerAttribute(object state) : Attribute
{
    public object State { get; } = state;

    /// <summary>
    /// 当前状态的重试次数上限，未设置时使用状态机默认值。
    /// </summary>
    public int RetryTimes { get; set; } = -1;

    /// <summary>
    /// 当前状态的重试时间上限（毫秒），与 RetryTimes 互斥。
    /// </summary>
    public int RetryTimeout { get; set; } = -1;

    /// <summary>
    /// 当前状态触发重试后的下一轮循环间隔（毫秒）。
    /// </summary>
    public int RetryInterval { get; set; } = -1;

    /// <summary>
    /// 当前状态 Handler 返回 Success 后，源状态持续可见多久才触发当前状态重试（毫秒）。
    /// </summary>
    public int TransitionTimeout { get; set; } = -1;
}

/// <summary>
/// 未知状态处理器标记。处理器方法签名必须为 Task&lt;StateHandlerResult&gt; Method(TContext context)。
/// </summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class UnknownStateHandlerAttribute : Attribute
{
}

/// <summary>
/// 有限状态机基类
/// 
/// 为什么使用状态机：
/// - 游戏自动化涉及大量界面切换，传统的 if-else 难以维护
/// - 状态机将每个界面抽象为状态，状态转换关系清晰可追踪
/// - 闭环确认机制确保操作真正生效，而不是盲目点击
/// 
/// 为什么使用注册模式：
/// - 将"状态图"与"状态处理逻辑"分离，便于修改和调试
/// - 状态图在一处定义，避免分散在代码各处难以维护
/// - 检测器注册使状态机能自动选择最优检测策略
/// 
/// 为什么 Handler 返回 StateHandlerResult：
/// - 状态机需要知道操作结果来决定下一步行为
/// - Success/Wait/Retry/Fail 四种结果覆盖所有场景
/// - 状态机统一处理等待和重试逻辑，Handler 只关注操作本身
/// 
/// 详细使用文档见 StateMachine/README.md
/// </summary>
public abstract class StateMachineBase<TState, TContext> where TState : struct, Enum
{
    private enum StateTransitionWaitStatus
    {
        ReachedTarget,
        RetryCurrentState,
        IntermediateTimeout
    }

    private readonly struct StateTransitionWaitResult(StateTransitionWaitStatus status, TState state = default)
    {
        public StateTransitionWaitStatus Status { get; } = status;

        public TState State { get; } = state;
    }

    /// <summary>
    /// 由子类实现以提供 Logger
    /// </summary>
    protected abstract ILogger Logger { get; }

    /// <summary>
    /// 状态机所属的运行环境，状态检测截图与循环等待都只使用它
    /// </summary>
    private readonly GameRuntime _runtime;

    protected CancellationToken _ct;

    /// <summary>
    /// 创建绑定到指定运行环境的状态机
    /// </summary>
    /// <param name="runtime">运行环境</param>
    protected StateMachineBase(GameRuntime runtime)
    {
        _runtime = runtime;
    }

    /// <summary>
    /// 当前状态
    /// </summary>
    public TState CurrentState { get; protected set; }

    /// <summary>
    /// 当前状态已累计的重试次数。首次执行当前状态 Handler 时为 0。
    /// </summary>
    protected int CurrentStateRetryCount { get; private set; }

    /// <summary>
    /// 当前状态的重试次数上限。使用时间策略时为 0。
    /// </summary>
    protected int CurrentStateRetryLimit { get; private set; }

    /// <summary>
    /// 当前状态的重试超时时间（毫秒）。为 null 时表示当前状态使用次数上限。
    /// </summary>
    protected int? CurrentStateRetryTimeout { get; private set; }

    /// <summary>
    /// 当前状态是否使用重试超时策略。
    /// </summary>
    protected bool CurrentStateRetryUsesTimeout => CurrentStateRetryTimeout.HasValue;

    /// <summary>
    /// 当前状态触发重试后的下一轮循环间隔（毫秒）。
    /// </summary>
    protected int CurrentStateRetryInterval { get; private set; }

    /// <summary>
    /// 当前状态 Handler 返回 Success 后，源状态持续可见多久才触发当前状态重试（毫秒）。
    /// </summary>
    protected int CurrentStateTransitionTimeout { get; private set; }

    /// <summary>
    /// 状态处理器注册表
    /// </summary>
    private readonly Dictionary<TState, StateHandlerDelegate<TContext>> _stateHandlers = new();

    /// <summary>
    /// 状态检测器注册表 - 每个状态对应一个检测函数
    /// 检测函数接收截图，返回 true 表示匹配
    /// </summary>
    private readonly Dictionary<TState, Func<ImageRegion, bool>> _stateDetectors = new();

    /// <summary>
    /// 状态邻接关系表 - 记录每个状态可能转换到的下一个状态
    /// 用于优化状态检测：只检测当前状态可能到达的状态
    /// </summary>
    private readonly Dictionary<TState, TState[]> _stateTransitions = new();

    /// <summary>
    /// 状态重试上限表 - 未注册时使用运行状态机传入的默认重试次数
    /// </summary>
    private readonly Dictionary<TState, int> _stateRetryLimits = new();

    /// <summary>
    /// 状态重试超时表 - 注册后与重试次数上限互斥
    /// </summary>
    private readonly Dictionary<TState, int> _stateRetryTimeouts = new();

    /// <summary>
    /// 状态重试间隔表 - 未注册时使用状态机循环间隔
    /// </summary>
    private readonly Dictionary<TState, int> _stateRetryIntervals = new();

    /// <summary>
    /// 源状态保持超时表 - 未注册时使用默认源状态保持超时
    /// </summary>
    private readonly Dictionary<TState, int> _stateTransitionTimeouts = new();

    /// <summary>
    /// 未知状态处理器
    /// </summary>
    private StateHandlerDelegate<TContext>? _unknownStateHandler;

    /// <summary>
    /// 默认状态检测间隔（毫秒）
    /// </summary>
    protected virtual int DefaultDetectionInterval => 300;

    /// <summary>
    /// 默认源状态保持超时（毫秒）
    /// </summary>
    protected virtual int DefaultTransitionTimeout => 3000;

    /// <summary>
    /// 默认中间态转换超时（毫秒）
    /// </summary>
    protected virtual int DefaultIntermediateTransitionTimeout => 120000;

    /// <summary>
    /// 默认最大重试次数
    /// </summary>
    protected virtual int DefaultMaxRetries => 3;

    /// <summary>
    /// 状态机循环间隔（毫秒）
    /// </summary>
    protected virtual int StateMachineLoopInterval => 200;

    #region 状态处理器注册

    /// <summary>
    /// 注册状态处理器
    /// </summary>
    /// <param name="state">状态</param>
    /// <param name="handler">处理器</param>
    protected void RegisterStateHandler(TState state, StateHandlerDelegate<TContext> handler)
    {
        _stateHandlers[state] = handler;
    }

    /// <summary>
    /// 注册多个状态处理器
    /// </summary>
    protected void RegisterStateHandlers(params (TState state, StateHandlerDelegate<TContext> handler)[] handlers)
    {
        foreach (var (state, handler) in handlers)
        {
            _stateHandlers[state] = handler;
        }
    }

    /// <summary>
    /// 注册未知状态处理器（可选）
    /// 当检测到 Unknown 状态或未注册处理器的状态时调用
    /// </summary>
    protected void RegisterUnknownStateHandler(StateHandlerDelegate<TContext> handler)
    {
        _unknownStateHandler = handler;
    }

    /// <summary>
    /// 扫描当前任务类中带 Attribute 的方法，自动注册状态检测器、处理器和未知状态处理器。
    /// </summary>
    protected void RegisterStateMethodsByAttribute()
    {
        var methods = GetType()
            .GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
            .Where(method => !method.IsSpecialName)
            .ToArray();

        var detectorStates = new HashSet<TState>();
        var detectors = methods
            .Select(method => (method, attribute: method.GetCustomAttribute<StateDetectorAttribute>()))
            .Where(item => item.attribute != null)
            .OrderBy(item => item.attribute!.Order)
            .ThenBy(item => item.method.Name, StringComparer.Ordinal);

        foreach (var (method, attribute) in detectors)
        {
            var state = ConvertAttributeState(attribute!.State, method);
            if (!detectorStates.Add(state))
            {
                throw new InvalidOperationException($"Multiple detectors are registered for state {state}");
            }

            ValidateDetectorMethod(method);
            RegisterStateDetector(state, (Func<ImageRegion, bool>)method.CreateDelegate(typeof(Func<ImageRegion, bool>), this));
        }

        var handlerStates = new HashSet<TState>();
        var handlers = methods
            .Select(method => (method, attribute: method.GetCustomAttribute<StateHandlerAttribute>()))
            .Where(item => item.attribute != null)
            .OrderBy(item => item.method.Name, StringComparer.Ordinal);

        foreach (var (method, attribute) in handlers)
        {
            var state = ConvertAttributeState(attribute!.State, method);
            if (!handlerStates.Add(state))
            {
                throw new InvalidOperationException($"Multiple handlers are registered for state {state}");
            }

            ValidateHandlerMethod(method);
            RegisterStateHandler(state, (StateHandlerDelegate<TContext>)method.CreateDelegate(typeof(StateHandlerDelegate<TContext>), this));
            RegisterHandlerOptions(state, attribute, method);
        }

        var unknownHandlers = methods
            .Where(method => method.GetCustomAttribute<UnknownStateHandlerAttribute>() != null)
            .ToArray();
        if (unknownHandlers.Length > 1)
        {
            throw new InvalidOperationException("Only one unknown-state handler can be registered");
        }

        if (unknownHandlers.Length == 1)
        {
            var method = unknownHandlers[0];
            ValidateHandlerMethod(method);
            RegisterUnknownStateHandler((StateHandlerDelegate<TContext>)method.CreateDelegate(typeof(StateHandlerDelegate<TContext>), this));
        }
    }

    private static TState ConvertAttributeState(object state, MethodInfo method)
    {
        if (state is TState typedState)
        {
            return typedState;
        }

        if (state == null)
        {
            throw new InvalidOperationException($"Method {method.Name} must have a state");
        }

        var stateTypeName = state.GetType().Name;
        throw new InvalidOperationException($"The state type {stateTypeName} of method {method.Name} does not match the state machine state type {typeof(TState).Name}");
    }

    private static void ValidateDetectorMethod(MethodInfo method)
    {
        var parameters = method.GetParameters();
        if (method.ReturnType != typeof(bool) ||
            parameters.Length != 1 ||
            parameters[0].ParameterType != typeof(ImageRegion))
        {
            throw new InvalidOperationException($"The state detector {method.Name} must have the signature bool {method.Name}(ImageRegion ra)");
        }
    }

    private static void ValidateHandlerMethod(MethodInfo method)
    {
        var parameters = method.GetParameters();
        if (method.ReturnType != typeof(Task<StateHandlerResult>) ||
            parameters.Length != 1 ||
            parameters[0].ParameterType != typeof(TContext))
        {
            throw new InvalidOperationException($"The state handler {method.Name} must have the signature Task<StateHandlerResult> {method.Name}({typeof(TContext).Name} context)");
        }
    }

    private void RegisterHandlerOptions(TState state, StateHandlerAttribute attribute, MethodInfo method)
    {
        if (attribute.RetryTimes == 0)
        {
            throw new InvalidOperationException($"RetryTimes for state handler {method.Name} must be greater than 0");
        }

        if (attribute.RetryTimeout == 0)
        {
            throw new InvalidOperationException($"RetryTimeout for state handler {method.Name} must be greater than 0");
        }

        if (attribute.RetryTimes > 0 && attribute.RetryTimeout > 0)
        {
            throw new InvalidOperationException($"RetryTimes and RetryTimeout cannot both be set for state handler {method.Name}");
        }

        if (attribute.RetryTimes > 0)
        {
            RegisterStateRetryLimit(state, attribute.RetryTimes);
        }

        if (attribute.RetryTimeout > 0)
        {
            RegisterStateRetryTimeout(state, attribute.RetryTimeout);
        }

        if (attribute.RetryInterval == 0)
        {
            throw new InvalidOperationException($"RetryInterval for state handler {method.Name} must be greater than 0");
        }

        if (attribute.RetryInterval > 0)
        {
            RegisterStateRetryInterval(state, attribute.RetryInterval);
        }

        if (attribute.TransitionTimeout == 0)
        {
            throw new InvalidOperationException($"TransitionTimeout for state handler {method.Name} must be greater than 0");
        }

        if (attribute.TransitionTimeout > 0)
        {
            RegisterStateTransitionTimeout(state, attribute.TransitionTimeout);
        }
    }

    #endregion

    #region 状态转换注册【推荐 - 有限状态机核心】

    /// <summary>
    /// 注册状态转换关系【推荐】
    /// 这是有限状态机的核心 - 定义每个状态可能转换到的下一个状态
    /// 
    /// 优势：
    /// 1. 状态检测只检测邻接状态，大幅提升性能
    /// 2. 状态流程清晰可见，便于维护
    /// 3. 自动排除不可能的状态转换
    /// </summary>
    /// <param name="fromState">源状态</param>
    /// <param name="toStates">可能的目标状态数组（邻接状态）</param>
    protected void RegisterStateTransition(TState fromState, params TState[] toStates)
    {
        ValidateStateTransition(fromState, toStates);
        _stateTransitions[fromState] = toStates;
    }

    /// <summary>
    /// 批量注册状态转换关系【推荐】
    /// </summary>
    protected void RegisterStateTransitions(params (TState from, TState[] to)[] transitions)
    {
        foreach (var (from, to) in transitions)
        {
            RegisterStateTransition(from, to);
        }
    }

    private static void ValidateStateTransition(TState fromState, TState[] toStates)
    {
        if (toStates == null || toStates.Length == 0)
        {
            throw new InvalidOperationException($"At least one adjacent state must be registered for state {fromState}; do not register a transition if this is a terminal node");
        }

        if (toStates.Any(state => EqualityComparer<TState>.Default.Equals(state, fromState)))
        {
            throw new InvalidOperationException($"The adjacent states of {fromState} cannot include itself");
        }
    }

    /// <summary>
    /// 获取当前状态可能转换到的状态列表
    /// 如果未注册，返回 null（表示需要检测所有状态）
    /// </summary>
    protected TState[]? GetPossibleNextStates()
    {
        return _stateTransitions.TryGetValue(CurrentState, out var states) ? states : null;
    }

    #endregion

    #region 状态重试上限注册

    /// <summary>
    /// 注册指定状态的重试上限，用于覆盖状态机运行时传入的默认重试次数
    /// </summary>
    protected void RegisterStateRetryLimit(TState state, int maxRetries)
    {
        if (maxRetries <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxRetries), "The state retry limit must be greater than 0");
        }

        _stateRetryLimits[state] = maxRetries;
        _stateRetryTimeouts.Remove(state);
    }

    /// <summary>
    /// 批量注册指定状态的重试上限
    /// </summary>
    protected void RegisterStateRetryLimits(params (TState state, int maxRetries)[] retryLimits)
    {
        foreach (var (state, maxRetries) in retryLimits)
        {
            RegisterStateRetryLimit(state, maxRetries);
        }
    }

    private int GetMaxRetriesForState(TState state, int defaultMaxRetries)
    {
        return _stateRetryLimits.TryGetValue(state, out var maxRetries) ? maxRetries : defaultMaxRetries;
    }

    /// <summary>
    /// 注册指定状态的重试超时时间，用于替代次数上限。
    /// </summary>
    protected void RegisterStateRetryTimeout(TState state, int timeoutMs)
    {
        if (timeoutMs <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(timeoutMs), "The state retry timeout must be greater than 0");
        }

        _stateRetryTimeouts[state] = timeoutMs;
        _stateRetryLimits.Remove(state);
    }

    /// <summary>
    /// 批量注册指定状态的重试超时时间
    /// </summary>
    protected void RegisterStateRetryTimeouts(params (TState state, int timeoutMs)[] retryTimeouts)
    {
        foreach (var (state, timeoutMs) in retryTimeouts)
        {
            RegisterStateRetryTimeout(state, timeoutMs);
        }
    }

    /// <summary>
    /// 注册指定状态触发重试后的下一轮循环间隔，未注册时使用 StateMachineLoopInterval。
    /// </summary>
    protected void RegisterStateRetryInterval(TState state, int intervalMs)
    {
        if (intervalMs <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(intervalMs), "The state retry interval must be greater than 0");
        }

        _stateRetryIntervals[state] = intervalMs;
    }

    /// <summary>
    /// 注册指定状态 Handler 返回 Success 后，源状态持续可见多久才触发当前状态重试。
    /// </summary>
    protected void RegisterStateTransitionTimeout(TState state, int timeoutMs)
    {
        if (timeoutMs <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(timeoutMs), "The source-state hold timeout must be greater than 0");
        }

        _stateTransitionTimeouts[state] = timeoutMs;
    }

    private (bool useTimeout, int value) GetRetryPolicyForState(TState state, int defaultMaxRetries)
    {
        if (_stateRetryTimeouts.TryGetValue(state, out var timeoutMs))
        {
            return (true, timeoutMs);
        }

        return (false, GetMaxRetriesForState(state, defaultMaxRetries));
    }

    private int GetRetryIntervalForState(TState state)
    {
        return _stateRetryIntervals.TryGetValue(state, out var intervalMs) ? intervalMs : StateMachineLoopInterval;
    }

    private int GetTransitionTimeoutForState(TState state)
    {
        return _stateTransitionTimeouts.TryGetValue(state, out var timeoutMs) ? timeoutMs : DefaultTransitionTimeout;
    }

    private void RecordStateRetry(string reason, (bool useTimeout, int value) retryPolicy, Stopwatch stateRetryStopwatch)
    {
        CurrentStateRetryCount++;

        if (retryPolicy.useTimeout)
        {
            var elapsedMilliseconds = stateRetryStopwatch.ElapsedMilliseconds;
            if (elapsedMilliseconds >= retryPolicy.value)
            {
                Logger.LogError("State {State} {Reason}; retry timeout limit of {Max} ms reached, marking as failed",
                    CurrentState, reason, retryPolicy.value);
                throw new InvalidOperationException($"State {CurrentState} reached the retry timeout limit of {retryPolicy.value} ms");
            }

            Logger.LogWarning("State {State} {Reason}; continuing retries within the timeout window (attempt {Count}, elapsed {Elapsed}/{Max} ms)",
                CurrentState, reason, CurrentStateRetryCount, elapsedMilliseconds, retryPolicy.value);
            return;
        }

        if (CurrentStateRetryCount >= retryPolicy.value)
        {
            Logger.LogError("State {State} {Reason}; retry limit of {Max} reached, marking as failed",
                CurrentState, reason, retryPolicy.value);
            throw new InvalidOperationException($"State {CurrentState} reached the retry limit of {retryPolicy.value}");
        }

        Logger.LogWarning("State {State} {Reason}; retrying the current state (attempt {Count}/{Max})",
            CurrentState, reason, CurrentStateRetryCount, retryPolicy.value);
    }

    #endregion

    #region 状态机运行

    /// <summary>
    /// 初始化状态机
    /// </summary>
    protected void Initialize(CancellationToken ct, TState initialState = default)
    {
        _ct = ct;
        CurrentState = initialState;
    }

    /// <summary>
    /// 运行状态机直到达到任一目标状态
    /// 这是核心方法，封装了 switch-case 逻辑
    /// </summary>
    /// <param name="context">上下文对象</param>
    /// <param name="targetStates">目标状态（到达任一即停止）</param>
    /// <param name="maxIterations">最大迭代次数（防止无限循环）</param>
    /// <param name="maxRetries">默认单个状态最大重试次数，可通过 RegisterStateRetryLimit 覆盖指定状态</param>
    /// <exception cref="InvalidOperationException">Handler 返回 Fail、重试超限、中间态等待超时或达到最大迭代次数时抛出</exception>
    protected async Task RunStateMachineUntil(TContext context, TState[] targetStates, int maxIterations = 1000, int maxRetries = 5)
    {
        Logger.LogInformation("========== State machine started; target states: {Targets} ==========",
            string.Join(", ", targetStates));

        CurrentStateRetryCount = 0;
        CurrentStateRetryLimit = maxRetries;
        CurrentStateRetryTimeout = null;
        CurrentStateRetryInterval = StateMachineLoopInterval;
        CurrentStateTransitionTimeout = DefaultTransitionTimeout;
        TState lastRetryState = default;
        var stateRetryStopwatch = Stopwatch.StartNew();

        for (int iteration = 0; iteration < maxIterations; iteration++)
        {
            _ct.ThrowIfCancellationRequested();

            // 检测当前实际状态
            RefreshCurrentState();

            // 状态变化时重置重试计数
            if (!EqualityComparer<TState>.Default.Equals(CurrentState, lastRetryState))
            {
                CurrentStateRetryCount = 0;
                lastRetryState = CurrentState;
                stateRetryStopwatch.Restart();
            }

            // 检查是否到达目标状态
            if (targetStates.Contains(CurrentState))
            {
                Logger.LogInformation("========== State machine completed; reached target state: {State} ==========", CurrentState);
                return;
            }

            Logger.LogDebug("State machine iteration {Iteration}; current state: {State}", iteration, CurrentState);
            var retryPolicy = GetRetryPolicyForState(CurrentState, maxRetries);
            var retryInterval = GetRetryIntervalForState(CurrentState);
            var transitionTimeout = GetTransitionTimeoutForState(CurrentState);
            CurrentStateRetryLimit = retryPolicy.useTimeout ? 0 : retryPolicy.value;
            CurrentStateRetryTimeout = retryPolicy.useTimeout ? retryPolicy.value : null;
            CurrentStateRetryInterval = retryInterval;
            CurrentStateTransitionTimeout = transitionTimeout;
            var nextLoopInterval = StateMachineLoopInterval;

            // 执行状态处理器
            if (_stateHandlers.TryGetValue(CurrentState, out var handler))
            {
                var result = await handler(context);

                switch (result.Status)
                {
                    case StateHandlerStatus.Success:
                        // 成功：等待指定的目标状态，或当前状态的全部邻接状态。
                        var transitionResult = result.TargetStates.Count > 0
                            ? await WaitStateTransitionTo(result.TargetStates, transitionTimeout)
                            : await WaitNextStateTransition(transitionTimeout);
                        switch (transitionResult.Status)
                        {
                            case StateTransitionWaitStatus.ReachedTarget:
                                CurrentStateRetryCount = 0; // 成功转换后重置重试计数
                                stateRetryStopwatch.Restart();
                                break;

                            case StateTransitionWaitStatus.RetryCurrentState:
                                RecordStateRetry("Source state remained visible; retrying the current state", retryPolicy, stateRetryStopwatch);
                                nextLoopInterval = retryInterval;
                                break;

                            case StateTransitionWaitStatus.IntermediateTimeout:
                                throw new InvalidOperationException($"Timed out waiting for an intermediate-state transition from state {CurrentState}");
                        }
                        break;

                    case StateHandlerStatus.Wait:
                        // 可预期的等待：状态机继续循环，重新检测状态。
                        Logger.LogDebug("Handler returned Wait; the state machine will continue waiting");
                        break;

                    case StateHandlerStatus.Retry:
                        // 意外失败重试：检查重试次数。
                        RecordStateRetry("Handler returned Retry", retryPolicy, stateRetryStopwatch);
                        nextLoopInterval = retryInterval;
                        break;

                    case StateHandlerStatus.Fail:
                        // 失败：抛出异常。
                        throw new InvalidOperationException($"Handler for state {CurrentState} returned Fail");
                }
            }
            else if (!EqualityComparer<TState>.Default.Equals(CurrentState, default) && _unknownStateHandler != null)
            {
                Logger.LogWarning("No handler is registered for state {State}; using the unknown-state handler", CurrentState);
                await _unknownStateHandler(context);
            }
            else if (_unknownStateHandler != null)
            {
                await _unknownStateHandler(context);
            }
            else
            {
                Logger.LogWarning("No handler is registered for state {State}; skipping", CurrentState);
            }

            await _runtime.Delay(nextLoopInterval, _ct);
        }

        Logger.LogError("State machine reached the maximum iteration count of {Max}; target states: {Targets}; current state: {State}",
            maxIterations, string.Join(", ", targetStates), CurrentState);
        throw new InvalidOperationException($"State machine reached the maximum iteration count of {maxIterations} without reaching target states: {string.Join(", ", targetStates)}");
    }

    /// <summary>
    /// 运行状态机直到达到单个目标状态
    /// </summary>
    protected Task RunStateMachineUntil(TContext context, TState targetState, int maxIterations = 1000)
    {
        return RunStateMachineUntil(context, new[] { targetState }, maxIterations);
    }

    #endregion

    #region 状态检测器注册

    /// <summary>
    /// 注册状态检测器
    /// 检测器接收截图区域，返回 true 表示当前处于该状态
    /// </summary>
    /// <param name="state">状态</param>
    /// <param name="detector">检测函数，接收 ImageRegion，返回 true 表示匹配</param>
    protected void RegisterStateDetector(TState state, Func<ImageRegion, bool> detector)
    {
        _stateDetectors[state] = detector;
    }

    /// <summary>
    /// 批量注册状态检测器【推荐】
    /// 注意：检测顺序影响性能，建议将快速检测的状态放在前面
    /// </summary>
    protected void RegisterStateDetectors(params (TState state, Func<ImageRegion, bool> detector)[] detectors)
    {
        foreach (var (state, detector) in detectors)
        {
            _stateDetectors[state] = detector;
        }
    }

    #endregion

    #region 核心状态检测方法

    /// <summary>
    /// 检测当前UI状态（完整检测）
    /// 基于注册的检测器，遍历所有注册的状态检测器
    /// 只截图一次，复用给所有检测器
    /// </summary>
    /// <returns>检测到的状态，如果都不匹配返回 default</returns>
    protected TState DetectCurrentState()
    {
        using var ra = _runtime.CaptureToRectArea();
        foreach (var (state, detector) in _stateDetectors)
        {
            if (detector(ra))
            {
                return state;
            }
        }
        return default;
    }

    /// <summary>
    /// 在候选状态中检测当前状态
    /// 只检测 candidateStates 中的状态，跳过其他状态
    /// 只截图一次，复用给所有检测器
    /// </summary>
    /// <param name="candidateStates">候选状态列表</param>
    /// <returns>检测到的状态，如果不在候选列表中则返回 default</returns>
    protected TState DetectStateAmong(TState[] candidateStates)
    {
        using var ra = _runtime.CaptureToRectArea();
        foreach (var state in candidateStates)
        {
            if (_stateDetectors.TryGetValue(state, out var detector) && detector(ra))
            {
                return state;
            }
        }
        return default;
    }

    /// <summary>
    /// 更新当前状态（通过检测）
    /// 严格模式：只检测邻接状态，不回退到全状态检测
    /// </summary>
    protected void RefreshCurrentState()
    {
        // 如果当前状态有注册邻接关系，只检测可能的下一个状态
        var possibleStates = GetPossibleNextStates();
        TState detected;

        if (possibleStates != null && possibleStates.Length > 0)
        {
            // 严格 FSM：只检测邻接状态
            detected = DetectStateAmong(possibleStates);
        }
        else
        {
            // 没有邻接状态定义时（如初始状态），回退到全状态检测
            detected = DetectCurrentState();
        }

        if (!EqualityComparer<TState>.Default.Equals(detected, default))
        {
            CurrentState = detected;
        }
    }

    /// <summary>
    /// 等待任一目标状态出现（内部方法）
    /// </summary>
    /// <param name="observedStates">可观察状态数组，应包含源状态和可接受的目标状态</param>
    /// <param name="timeoutMs">超时时间（毫秒）</param>
    /// <returns>转换等待结果</returns>
    private async Task<StateTransitionWaitResult> WaitAnyStateTransition(TState[] observedStates, int? timeoutMs = null)
    {
        var timeout = timeoutMs ?? DefaultTransitionTimeout;
        var sourceState = CurrentState;
        var transitionTargetStates = observedStates
            .Where(state => !EqualityComparer<TState>.Default.Equals(state, sourceState))
            .ToArray();

        if (transitionTargetStates.Length == 0)
        {
            Logger.LogWarning("State {State} has no adjacent states other than itself to wait for", sourceState);
            return new StateTransitionWaitResult(StateTransitionWaitStatus.RetryCurrentState);
        }

        var sourceVisibleStopwatch = Stopwatch.StartNew();
        var intermediateStopwatch = Stopwatch.StartNew();
        var intermediateTimeout = Math.Max(timeout, DefaultIntermediateTransitionTimeout);

        while (sourceVisibleStopwatch.ElapsedMilliseconds < timeout &&
               intermediateStopwatch.ElapsedMilliseconds < intermediateTimeout)
        {
            _ct.ThrowIfCancellationRequested();

            // 只检测目标状态和源状态
            var currentState = DetectStateAmong(observedStates);
            if (transitionTargetStates.Contains(currentState))
            {
                CurrentState = currentState;
                Logger.LogDebug("Transitioned to state {State}", currentState);
                return new StateTransitionWaitResult(StateTransitionWaitStatus.ReachedTarget, currentState);
            }

            if (EqualityComparer<TState>.Default.Equals(currentState, sourceState))
            {
                intermediateStopwatch.Restart();
            }
            else
            {
                sourceVisibleStopwatch.Restart();
            }

            await _runtime.Delay(DefaultDetectionInterval, _ct);
        }

        if (sourceVisibleStopwatch.ElapsedMilliseconds >= timeout)
        {
            Logger.LogWarning("Source state {State} remained visible for more than {Timeout} ms; retrying the current state, expecting one of: {Expected}",
                sourceState, timeout, string.Join(",", transitionTargetStates));
            return new StateTransitionWaitResult(StateTransitionWaitStatus.RetryCurrentState);
        }
        else
        {
            Logger.LogWarning("Timed out waiting {Timeout} ms for an intermediate state; expecting one of: {Expected}",
                intermediateTimeout, string.Join(",", transitionTargetStates));
            return new StateTransitionWaitResult(StateTransitionWaitStatus.IntermediateTimeout);
        }
    }

    /// <summary>
    /// 等待转换到 Handler 指定的目标状态集合。
    /// </summary>
    private async Task<StateTransitionWaitResult> WaitStateTransitionTo(IReadOnlyList<Enum> targetStates, int? timeoutMs = null)
    {
        var possibleStates = GetPossibleNextStates();
        if (possibleStates == null || possibleStates.Length == 0)
        {
            throw new InvalidOperationException($"No adjacent states are registered for current state {CurrentState}; SuccessTo cannot be used");
        }

        var typedTargetStates = new TState[targetStates.Count];
        for (var i = 0; i < targetStates.Count; i++)
        {
            if (targetStates[i] is not TState typedState)
            {
                throw new InvalidOperationException($"SuccessTo target type {targetStates[i].GetType().Name} for state {CurrentState} does not match the state machine state type {typeof(TState).Name}");
            }

            if (!possibleStates.Contains(typedState))
            {
                throw new InvalidOperationException($"SuccessTo target {typedState} for state {CurrentState} is not a valid adjacent state");
            }

            if (!_stateDetectors.ContainsKey(typedState))
            {
                throw new InvalidOperationException($"No state detector is registered for SuccessTo target {typedState} of state {CurrentState}");
            }

            typedTargetStates[i] = typedState;
        }

        var observedStates = typedTargetStates
            .Concat(new[] { CurrentState })
            .Distinct()
            .ToArray();
        return await WaitAnyStateTransition(observedStates, timeoutMs);
    }

    /// <summary>
    /// 等待转换到邻接状态（使用状态转换关系）。
    /// 自动使用当前状态注册的邻接状态作为期望状态。
    /// </summary>
    /// <param name="timeoutMs">超时时间（毫秒）</param>
    /// <returns>转换等待结果</returns>
    private async Task<StateTransitionWaitResult> WaitNextStateTransition(int? timeoutMs = null)
    {
        var possibleStates = GetPossibleNextStates();
        if (possibleStates == null || possibleStates.Length == 0)
        {
            Logger.LogWarning("No adjacent states are registered for current state {State}; expected states cannot be determined", CurrentState);
            return new StateTransitionWaitResult(StateTransitionWaitStatus.RetryCurrentState);
        }

        var observedStates = possibleStates
            .Concat(new[] { CurrentState })
            .Distinct()
            .ToArray();
        return await WaitAnyStateTransition(observedStates, timeoutMs);
    }

    /// <summary>
    /// 等待转换到邻接状态（使用状态转换关系）
    /// 自动使用当前状态注册的邻接状态作为期望状态
    /// </summary>
    /// <param name="timeoutMs">超时时间（毫秒）</param>
    /// <returns>转换到的状态；没有注册邻接状态、源状态保持超时或中间态等待超时时返回 default</returns>
    protected async Task<TState> EnsureNextStateTransition(int? timeoutMs = null)
    {
        var result = await WaitNextStateTransition(timeoutMs);
        return result.Status == StateTransitionWaitStatus.ReachedTarget ? result.State : default;
    }

    #endregion
}
