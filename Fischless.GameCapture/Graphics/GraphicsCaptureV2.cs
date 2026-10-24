using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Fischless.GameCapture.Graphics.Helpers;
using SharpDX.Direct3D11;
using Vanara.PInvoke;
using Windows.Foundation;
using Windows.Foundation.Metadata;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using OpenCvSharp;
using SharpDX;
using SharpDX.D3DCompiler;
using SharpDX.DXGI;

// 部分设计参考 FFmpeg 的 WGC 捕获实现（libavfilter/vsrc_gfxcapture_winrt.cpp，LGPL-2.1-or-later）

namespace Fischless.GameCapture.Graphics;

public partial class GraphicsCaptureV2(bool captureHdr = false) : IGameCapture, IGameCaptureDiagnostics, IGameCaptureReadback
{
    // BGR Mat 池：有界 ConcurrentQueue，FIFO 回收
    private const int MaxPoolSize = 16;
    private readonly ConcurrentQueue<Mat> _bgrQueue = new();
    private bool _bgrPoolClosed = true;
    private readonly HashSet<Mat> _bgrBorrowed = new();

    private nint _hWnd;

    private Direct3D11CaptureFramePool? _captureFramePool;
    /// <summary>Cached instance delegate for the bounded selector; reads the current pool under _lock.</summary>
    private Func<Direct3D11CaptureFrame?>? _takeNextFrame;
    private GraphicsCaptureItem? _captureItem;
    private GraphicsCaptureSession? _captureSession;
    private IDirect3DDevice? _d3dDevice;

    public bool IsCapturing { get; private set; }

    private ResourceRegion? _region;
    private RECT? _captureRect;

    // HDR 相关
    private bool _isHdrEnabled = captureHdr;
    private DirectXPixelFormat _pixelFormat;
    private Texture2D? _hdrOutputTexture;
    private ComputeShader? _hdrComputeShader;
    private UnorderedAccessView? _hdrOutputUav;

    private readonly object _lock = new();
    /// <summary>Serializes lifecycle calls while Stop releases _lock to let readbacks finish.</summary>
    private readonly object _lifecycleGate = new();

    // FFmpeg gfxcapture 式限流：MinUpdateInterval 把 DWM 推帧率限到消费需求率（26100+，接口 QI 调用，见 TryApplyMinUpdateInterval）
    private Windows.Graphics.SizeInt32 _capSize;
    private long _minUpdateIntervalHns;   // 默认 0 = 不启用限流，WinRT TimeSpan（100ns 单位）

    // IGraphicsCaptureSession5 {67C0EA62-1F85-5061-925A-239BE0AC09CB}
    private static readonly Guid GraphicsCaptureSession5Iid = new("67C0EA62-1F85-5061-925A-239BE0AC09CB");

    // vtable 布局：IUnknown 0-2 + IInspectable 3-5 + get_MinUpdateInterval 6 + put_MinUpdateInterval 7
    private const int PutMinUpdateIntervalVtableSlot = 7;

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int PutMinUpdateIntervalDelegate(IntPtr pThis, long duration);

    // BGR24 打包四件套见上方字段；消费被 _captureGate 串行化，单块 staging buffer 即安全

    // 单飞闸门：并发消费方逐个进入
    private readonly object _captureGate = new();

    // 在途捕获数（正持锁外 Map/读回）。Stop 与尺寸 Recreate 销毁 staging 前必须等其归零；仅锁内访问
    private int _activeCaptures;

    // 无新帧跳过读回：消费时 TryGetNextFrame 为空（池已排空，无新内容），克隆缓存直接返回，
    // 避免对旧内容重复 GPU/PCIe 回读空转。缓存常建：每次消费新帧时写入缓存 + 克隆给消费者
    private Mat? _cachedBgr;
    private long _cachedFrameTs;         // 缓存内容对应的帧时间戳
    /// <summary>Metadata belonging to cached BGR pixels, never relabelled by a later acquisition.</summary>
    private GameCaptureSourceInfo? _cachedSourceInfo;
    /// <summary>RECT published with polling-mode cached pixels, never borrowed from a later refill.</summary>
    private RECT? _cachedCaptureRect;
    /// <summary>Per-Start callback lifetime and immutable source high-water mark.</summary>
    private WgcCaptureGeneration? _generation;
    /// <summary>Generation-bound arrival delegate, unsubscribed on its WinRT owner thread.</summary>
    private TypedEventHandler<Direct3D11CaptureFramePool, object>? _frameArrivedHandler;
    /// <summary>Generation-bound close delegate; delayed events cannot stop a replacement session.</summary>
    private TypedEventHandler<GraphicsCaptureItem, object>? _captureClosedHandler;

    // BGR24 打包（GPU 完成颜色转换与打包，CPU 免转换；回读量 8.3→6.2MB -25%）
    private ComputeShader? _packCs;
    private SharpDX.Direct3D11.Buffer? _packCb;           // uint4 dims（W,H,total,0），Dynamic
    private SharpDX.Direct3D11.Buffer? _packGpuBuf;       // 打包结果（GPU），StructuredBuffer<uint>
    private UnorderedAccessView? _packUav;
    private SharpDX.Direct3D11.Buffer? _packStagingBuf;   // CPU 可读副本（Staging）

    // 注意：SharpDX Compile(string) 用 StringToHGlobalAnsi + 字符数当字节数，非 ASCII 字符
    // （如中文注释）会把源码尾部截断导致 FXC 编译失败——此字符串内必须保持纯 ASCII
    private const string PackShaderSrc = @"
        cbuffer cb : register(b0) { uint4 dims; }   // x=W y=H z=total
        Texture2D<float4> src : register(t0);
        RWStructuredBuffer<uint> outBuf : register(u0);
        [numthreads(64,1,1)]
        void main_cs(uint3 dt : SV_DispatchThreadID)
        {
            uint p = dt.x * 4;                       // 4 pixels/thread = 12 bytes = 3 aligned dwords
            if (p >= dims.z) return;
            uint bc[4]; uint gc[4]; uint rc[4];
            [unroll]
            for (uint k = 0; k < 4; ++k)
            {
                uint idx = p + k;
                uint x = idx % dims.x;
                uint y = idx / dims.x;
                float4 px = src.Load(int3(x, y, 0)); // B8G8R8A8 auto-swizzled: px.x=R px.y=G px.z=B
                bc[k] = (uint)(saturate(px.z) * 255.0f + 0.5f);
                gc[k] = (uint)(saturate(px.y) * 255.0f + 0.5f);
                rc[k] = (uint)(saturate(px.x) * 255.0f + 0.5f);
            }
            uint o = p / 4 * 3;                      // group base (bytes) -> dword index, 4-byte aligned
            outBuf[o + 0] = bc[0] | (gc[0] << 8)  | (rc[0] << 16) | (bc[1] << 24);
            outBuf[o + 1] = gc[1] | (rc[1] << 8)  | (bc[2] << 16) | (gc[2] << 24);
            outBuf[o + 2] = rc[2] | (bc[3] << 8)  | (gc[3] << 16) | (rc[3] << 24);
        }
    ";

    // 单 GPU 广播源：消费时按需用像素着色器一次 draw 渲染写入（FFmpeg gfxcapture 同款）。
    // 旧版到达时写入旨在减少跨进程同步等待；现在所有 D3D 工作归消费线程，避免回调线程持设备锁。
    // 绘制与回读延迟需分别实测，不能沿用旧版到达侧写入的耗时结论。
    private Texture2D? _gpuTexture;
    private RenderTargetView? _gpuTextureRtv;
    private long _gpuFrameTs;            // _gpuTexture 当前内容对应帧的时间戳（_lock 内写）
    /// <summary>Source metadata published atomically with the GPU pixels and their timestamp.</summary>
    private GameCaptureSourceInfo? _gpuSourceInfo;

    // draw 写入资源（FFmpeg gfxcapture 的全屏三角形 + 采样，客户区裁剪折进 UV 窗口）
    private VertexShader? _drawVs;
    private PixelShader? _drawPs;
    private SamplerState? _drawSampler;
    private SharpDX.Direct3D11.Buffer? _drawCb;

    private const string DrawShaderSrc = @"
        cbuffer cb : register(b0) { float4 uvWindow; }
        Texture2D t0 : register(t0);
        SamplerState s0 : register(s0);
        struct VSOut { float4 pos : SV_Position; float2 uv : TEXCOORD0; };
        VSOut main_vs(uint id : SV_VertexID) {
            VSOut o;
            o.pos = float4(id == 2 ? 3.0 : -1.0, id == 1 ? 3.0 : -1.0, 0, 1);
            o.uv = lerp(uvWindow.xy, uvWindow.zw, float2((o.pos.x + 1) * 0.5, 1 - (o.pos.y + 1) * 0.5));
            return o;
        }
        float4 main_ps(VSOut i) : SV_Target { return t0.Sample(s0, i.uv); }
    ";

    // A/B 开关：true = FFmpeg 式 draw 写入；false = 旧版 CopySubresourceRegion 拷贝写入
    private bool _useDrawWrite = true;

    // A/B 开关（settings 键 UseCpuConvert）：true = 旧 BGRA staging + CPU CvtColor；false = GPU 打包 BGR24
    private bool _useCpuConvert;

    // CPU 转换回退路径（_useCpuConvert=true 时启用）：BGRA 整帧 staging，Map 后 CvtColor
    private Texture2D? _stagingTexture;

    // 诊断计数（仅 _captureGate 内访问）：定位刷新/占用问题时用 DebugView 查看
    private long _diagTicks;
    private long _diagFrames;
    private long _diagCacheHits;
    private long _diagRecreates;

    // Recreate 连续失败计数（消费线程 _captureGate 内访问）：失败时用于作废缓存与日志告警
    private int _recreateFailures;

    // Capture 返回空的节流日志时间点（Environment.TickCount64 毫秒）
    private long _lastNullLogMs;

    // WGC WinRT 对象（帧池/会话/捕获项）具有线程亲和性：Win10 上跨线程 Recreate 抛
    // RPC_E_WRONG_THREAD。建池/Recreate/销毁统一路由到本实例专属泵线程执行
    // （ffmpeg gfxcapture 的 wgc_thread 同款方案）。
    // 泵线程是会话级资源；Stop 排队最终清理并关闭队列，下一 Start 仅在旧会话清理完成后重建。
    /// <summary>Owns a fixed queue and worker for the current session.</summary>
    private WgcCapturePump? _wgcPump;
    /// <summary>Pending retirement retains resources while a timed-out native call is still running.</summary>
    private Task? _pumpRetirement;
    /// <summary>Dispose is terminal, although Stop followed by Start is supported.</summary>
    private bool _disposed;

    // 泵线程同步派发的等待上限（FFmpeg run_on_wgc_thread 为 1s，此处略放宽以覆盖冷启动建设备/会话）
    private static readonly TimeSpan WgcDispatchTimeout = TimeSpan.FromSeconds(2);

    /// <summary>
    /// 在 WGC 专属泵线程上同步执行动作；调用方持 _lock，泵动作不取此锁。
    /// 超时只结束调用方的等待，不能取消已开始的 WinRT 操作；随后必须走有序退役清理。
    /// </summary>
    private void RunOnWgcThread(Action action)
    {
        _wgcPump ??= new WgcCapturePump();
        _wgcPump.Run(action, WgcDispatchTimeout);
    }
    private double _sumPackMs;
    private double _sumCopyMs;
    private double _sumStageMs;
    private double _sumCvtMs;
    private double _sumMapMs;
    private double _sumCloneMs;

    public void Dispose()
    {
        lock (_lifecycleGate)
        lock (_lock)
        {
            _disposed = true;
            StopCore();
        }
        GC.SuppressFinalize(this);
    }

    public void Start(nint hWnd, Dictionary<string, object>? settings = null)
    {
            // 全程持锁，防并发双 Start 泄漏 framepool/session（Monitor 可重入，内部 Stop 安全）
        lock (_lifecycleGate)
        lock (_lock)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            StartCore(hWnd, settings);
        }
    }

    private void StartCore(nint hWnd, Dictionary<string, object>? settings = null)
    {
        // Validate before touching the old lifetime; omitted settings always choose blocking.
        var readbackMode = WgcReadbackSlot.ReadMode(settings);
        if (!StopCore())
            throw new InvalidOperationException("The previous WGC session is still retiring; retry after its native operation finishes.");
        try
        {
            var generation = new WgcCaptureGeneration();
            _generation = generation;
            ReadbackMode = readbackMode;
            _readbackSlot = readbackMode == GameCaptureReadbackMode.PollSingleV1
                ? new WgcReadbackSlot(generation.Epoch) : null;
            _hWnd = hWnd;

            // 最小化窗口 DWM 不合成内容，WGC 不会推帧；不阻止启动（还原窗口后自动恢复），仅提示便于定位
            if (User32.IsIconic(_hWnd))
            {
                Debug.WriteLine("[WGC V2] 目标窗口处于最小化状态，恢复窗口后截图才会生效");
            }

            // 识别节拍可通过 settings 传入（键 MinUpdateIntervalMs，毫秒）；0 = 不启用限流
            if (settings?.TryGetValue("MinUpdateIntervalMs", out var intervalObj) == true)
            {
                try
                {
                    var ms = Convert.ToInt64(intervalObj);
                    _minUpdateIntervalHns = ms > 0 ? ms * 10_000L : 0;
                }
                catch
                {
                    // 非法值忽略，保持默认
                }
            }

            // 到达侧写入方式开关（A/B 对比用）
            if (settings?.TryGetValue("DisableDrawWrite", out var disableDrawWriteObj) == true)
            {
                try
                {
                    _useDrawWrite = !Convert.ToBoolean(disableDrawWriteObj);
                }
                catch
                {
                    // 非法值忽略
                }
            }

            // 颜色转换开关（A/B 对比/回退用）：true = 旧 BGRA staging + CPU CvtColor；false = GPU 打包 BGR24
            if (settings?.TryGetValue("UseCpuConvert", out var useCpuConvertObj) == true)
            {
                try
                {
                    _useCpuConvert = Convert.ToBoolean(useCpuConvertObj);
                }
                catch
                {
                    // 非法值忽略
                }
            }

            (_region, _captureRect) = GetGameScreenInfo(hWnd);

            // Capture remains unavailable until pump creation has completed successfully.
            // WGC WinRT 对象具有线程亲和性（Win10 上跨线程 Recreate 抛 RPC_E_WRONG_THREAD），
            // 建池/Recreate/销毁统一路由到本实例专属泵线程执行（ffmpeg wgc_thread 同款方案）
            RunOnWgcThread(() =>
            {
                try
                {
                    _captureItem = CaptureHelper.CreateItemForWindow(_hWnd);
                }
                catch (Exception e)
                {
                    throw new InvalidOperationException(
                        $"创建 WGC 捕获器失败，hWnd=0x{_hWnd.ToInt64():X8}，可能原因：窗口句柄失效、游戏窗口被最小化/未启动、或被其他应用/系统不支持图形捕获", e);
                }

                if (_captureItem == null)
                {
                    throw new InvalidOperationException("Failed to create capture item.");
                }

                _capSize = _captureItem.Size;

                _d3dDevice = Direct3D11Helper.CreateDevice();

                // CreateFreeThreaded 契约：帧池对象可跨线程访问，不依赖 DispatcherQueue/消息泵；
                // TryGetNextFrame 由消费线程调用（FFmpeg gfxcapture 同款需求驱动模型），
                // Recreate/销毁则必须回到本泵线程执行
                try
                {
                    if (!_isHdrEnabled)
                    {
                        throw new Exception();
                    }

                    _pixelFormat = DirectXPixelFormat.R16G16B16A16Float;
                    _captureFramePool = Direct3D11CaptureFramePool.CreateFreeThreaded(
                        _d3dDevice,
                        _pixelFormat,
                        2,
                        _captureItem.Size);
                }
                catch (Exception)
                {
                    _pixelFormat = DirectXPixelFormat.B8G8R8A8UIntNormalized;
                    _captureFramePool = Direct3D11CaptureFramePool.CreateFreeThreaded(
                        _d3dDevice,
                        _pixelFormat,
                        2,
                        _captureItem.Size);
                    _isHdrEnabled = false;
                }

                _captureClosedHandler = (_, _) => CaptureItemOnClosed(generation);
                _frameArrivedHandler = (_, _) => generation.SignalArrival();
                _captureItem.Closed += _captureClosedHandler;
                _captureFramePool.FrameArrived += _frameArrivedHandler;

                _captureSession = _captureFramePool.CreateCaptureSession(_captureItem);
                if (ApiInformation.IsPropertyPresent("Windows.Graphics.Capture.GraphicsCaptureSession",
                        nameof(GraphicsCaptureSession.IsCursorCaptureEnabled)))
                {
                    _captureSession.IsCursorCaptureEnabled = false;
                }

                if (ApiInformation.IsWriteablePropertyPresent("Windows.Graphics.Capture.GraphicsCaptureSession",
                        nameof(GraphicsCaptureSession.IsBorderRequired)))
                {
                    _captureSession.IsBorderRequired = false;
                }

                // FFmpeg gfxcapture 同款：StartCapture 前设置最小更新间隔，把推帧率限到消费需求率
                TryApplyMinUpdateInterval(_captureSession);

                _captureSession.StartCapture();
            });
            if (!generation.IsActive)
                throw new InvalidOperationException("The WGC capture item closed during startup.");
            Debug.WriteLine($"[WGC V2] Start 完成: hdr={_isHdrEnabled}, fmt={_pixelFormat}, minUpdateInterval={(_minUpdateIntervalHns > 0 ? $"{_minUpdateIntervalHns / 10000.0:0.##}ms" : "off")}, capSize={_capSize.Width}x{_capSize.Height}");
            IsCapturing = true;
            lock (_lock)
            {
                _bgrPoolClosed = false;
            }
        }
        catch
        {
            Stop();
            throw;
        }
    }

    private static (ResourceRegion? Region, RECT? CaptureRect) GetGameScreenInfo(nint hWnd)
    {
        var exStyle = User32.GetWindowLong(hWnd, User32.WindowLongFlags.GWL_EXSTYLE);
        if ((exStyle & (int)User32.WindowStylesEx.WS_EX_TOPMOST) != 0)
        {
            return (null, null);
        }

        ResourceRegion region = new();
        DwmApi.DwmGetWindowAttribute<RECT>(hWnd, DwmApi.DWMWINDOWATTRIBUTE.DWMWA_EXTENDED_FRAME_BOUNDS,
            out var windowRect);
        User32.GetClientRect(hWnd, out var clientRect);
        POINT point = default;
        User32.ClientToScreen(hWnd, ref point);

        region.Left = point.X > windowRect.Left ? point.X - windowRect.Left : 0;
        region.Top = point.Y > windowRect.Top ? point.Y - windowRect.Top : 0;
        region.Right = region.Left + clientRect.Width;
        region.Bottom = region.Top + clientRect.Height;
        region.Front = 0;
        region.Back = 1;

        var left = windowRect.Left;
        var top = windowRect.Top + windowRect.Height - clientRect.Height;
        var right = left + clientRect.Width;
        var bottom = top + clientRect.Height;

        return (region, new RECT(left, top, right, bottom));
    }

    private Texture2D ProcessHdrTexture(Texture2D hdrTexture)
    {
        var device = hdrTexture.Device;
        var context = device.ImmediateContext;

        var width = hdrTexture.Description.Width;
        var height = hdrTexture.Description.Height;

        // V2 消费侧需要从输出纹理读原始字节打包：UNORM 资源 + 同格式显式视图（浮点往返精确还原字节）
        _hdrOutputTexture ??= Direct3D11Helper.CreateOutputTexture(device, width, height);
        _hdrOutputUav ??= new UnorderedAccessView(device, _hdrOutputTexture);
        _hdrComputeShader ??= new ComputeShader(device, ShaderBytecode.Compile(HdrToSdrShader.Content, "CS_HDRtoSDR", "cs_5_0"));

        using var inputSrv = new ShaderResourceView(device, hdrTexture);

        context.ComputeShader.Set(_hdrComputeShader);
        context.ComputeShader.SetShaderResource(0, inputSrv);
        context.ComputeShader.SetUnorderedAccessView(0, _hdrOutputUav);

        var threadGroupCountX = (int)Math.Ceiling(width / 16.0);
        var threadGroupCountY = (int)Math.Ceiling(height / 16.0);

        context.Dispatch(threadGroupCountX, threadGroupCountY, 1);

        // 解绑，避免后续 CopyResource 触发 read/write hazard
        context.ComputeShader.SetUnorderedAccessView(0, null);
        context.ComputeShader.SetShaderResource(0, null);
        context.ComputeShader.Set(null);

        return _hdrOutputTexture;
    }

    private void EnsureGpuTexture(SharpDX.Direct3D11.Device device, int width, int height, ResourceRegion? region)
    {
        var w = region == null ? width : region.Value.Right - region.Value.Left;
        var h = region == null ? height : region.Value.Bottom - region.Value.Top;

        if (_gpuTexture == null ||
            _gpuTexture.Description.Width != w ||
            _gpuTexture.Description.Height != h)
        {
            _gpuTextureRtv?.Dispose();
            _gpuTextureRtv = null;
            _gpuTexture?.Dispose();
            _gpuTexture = new Texture2D(device, new Texture2DDescription
            {
                Width = w,
                Height = h,
                MipLevels = 1,
                ArraySize = 1,
                Format = Format.B8G8R8A8_UNorm,
                SampleDescription = new SampleDescription(1, 0),
                Usage = ResourceUsage.Default,
                CpuAccessFlags = CpuAccessFlags.None,
                BindFlags = BindFlags.RenderTarget | BindFlags.ShaderResource,
                OptionFlags = ResourceOptionFlags.None,
            });
            _gpuTextureRtv = new RenderTargetView(device, _gpuTexture);
        }
    }

    private void EnsureDrawResources(SharpDX.Direct3D11.Device device)
    {
        if (_drawVs != null) return;

        using var vsBlob = ShaderBytecode.Compile(DrawShaderSrc, "main_vs", "vs_5_0");
        using var psBlob = ShaderBytecode.Compile(DrawShaderSrc, "main_ps", "ps_5_0");
        _drawVs = new VertexShader(device, vsBlob);
        _drawPs = new PixelShader(device, psBlob);
        _drawSampler = new SamplerState(device, new SamplerStateDescription
        {
            Filter = Filter.MinMagMipLinear,
            AddressU = TextureAddressMode.Clamp,
            AddressV = TextureAddressMode.Clamp,
            AddressW = TextureAddressMode.Clamp,
            // 结构体默认值 0 对 D3D11_COMPARISON_FUNC 是非法枚举，必须显式设置（否则 CreateSamplerState E_INVALIDARG）
            ComparisonFunction = Comparison.Never,
            MinimumLod = 0,
            MaximumLod = float.MaxValue,
        });
        _drawCb = new SharpDX.Direct3D11.Buffer(device, 16, ResourceUsage.Dynamic, BindFlags.ConstantBuffer, CpuAccessFlags.Write, ResourceOptionFlags.None, 0);
    }

    private void EnsurePackResourcesLocked(SharpDX.Direct3D11.Device device, int width, int height)
    {
        var bytes = ((width * height + 3) / 4) * 12; // 每 4 像素由 shader 固定写入 3 个 dword，按组取整避免末组 UAV 越界
        if (_packGpuBuf != null && _packGpuBuf.Description.SizeInBytes == bytes) return;

        _packUav?.Dispose();
        _packGpuBuf?.Dispose();
        _packStagingBuf?.Dispose();

        _packCs ??= new ComputeShader(device, ShaderBytecode.Compile(PackShaderSrc, "main_cs", "cs_5_0"));
        _packCb ??= new SharpDX.Direct3D11.Buffer(device, 16, ResourceUsage.Dynamic, BindFlags.ConstantBuffer, CpuAccessFlags.Write, ResourceOptionFlags.None, 0);
        _packGpuBuf = new SharpDX.Direct3D11.Buffer(device, bytes, ResourceUsage.Default, BindFlags.UnorderedAccess, CpuAccessFlags.None, ResourceOptionFlags.BufferStructured, 4);
        // structured buffer 的 UAV 描述必须显式给出（Format=Unknown），否则驱动可能拒绝
        _packUav = new UnorderedAccessView(device, _packGpuBuf, new UnorderedAccessViewDescription
        {
            Format = Format.Unknown,
            Dimension = UnorderedAccessViewDimension.Buffer,
            Buffer = new UnorderedAccessViewDescription.BufferResource
            {
                FirstElement = 0,
                ElementCount = bytes / 4,
                Flags = UnorderedAccessViewBufferFlags.None,
            },
        });
        _packStagingBuf = new SharpDX.Direct3D11.Buffer(device, bytes, ResourceUsage.Staging, BindFlags.None, CpuAccessFlags.Read, ResourceOptionFlags.BufferStructured, 4);
    }

    // CPU 转换回退路径：BGRA 整帧 staging 纹理（尺寸变化重建）
    private void EnsureStagingTextureLocked(SharpDX.Direct3D11.Device device, int width, int height)
    {
        if (_stagingTexture == null || _stagingTexture.Description.Width != width ||
            _stagingTexture.Description.Height != height)
        {
            _stagingTexture?.Dispose();
            _stagingTexture = Direct3D11Helper.CreateStagingTexture(device, width, height, null);
        }
    }

    private static void HandleSharpDxError(SharpDXException e)
    {
        Debug.WriteLine($"SharpDXException: {e.Descriptor}");
        if (e.ResultCode == SharpDX.DXGI.ResultCode.DeviceRemoved || e.ResultCode == SharpDX.DXGI.ResultCode.DeviceReset)
        {
            Debug.WriteLine($"[WGC] D3D 设备丢失 ({e.ResultCode})，后续捕获可能失效，等待上层重建");
        }
    }

    // FrameArrived is intentionally signal-only through the generation-bound delegate above:
    // no device calls and no _lock acquisition on the WinRT callback thread.

    /// <summary>
    /// 主动从双缓冲池中最多取出两帧，选择最新有效帧并绘制到广播纹理（消费线程调用，必须持 <see cref="_lock"/>）。
    /// 返回 false 表示无新帧或本帧被跳过（缓存帧仍有效）；true 表示已绘制并更新 <see cref="_gpuFrameTs"/>。
    /// </summary>
    private bool TryRenderNewFrameLocked(GameCaptureCallTiming? timing)
    {
        // The same bounded selector serves ordinary/diagnostic capture; only its chosen frame
        // reaches geometry/render work. Discarded sources still advance the generation high-water.
        Direct3D11CaptureFrame? acquiredFrame;
        GameCaptureSourceInfo? sourceInfo = null;
        var contentSize = _capSize;
        try
        {
            acquiredFrame = WgcFrameSelection.TakeNewest(_takeNextFrame ??= TakeNextFrame,
                static frame => frame.SystemRelativeTime.Ticks, static frame => frame.ContentSize,
                _generation, _capSize, out sourceInfo, out contentSize, timing);
        }
        catch
        {
            // A newer geometry may already be known when superseded-frame disposal fails.
            // Preserve the iconic exception, but never return old-bounds pixels after such failure.
            if (sourceInfo is not null &&
                (contentSize.Width != _capSize.Width || contentSize.Height != _capSize.Height) &&
                !User32.IsIconic(_hWnd))
                InvalidatePublishedFrames();
            throw;
        }
        using var frame = acquiredFrame;
        if (frame is null) return false;

        // This is acquisition time, not event arrival, frame rendering, or the current consumer poll time.
        // The selector retained the chosen source's original stamp; do not read/restamp it here.
        var frameTs = sourceInfo!.SourceTimestamp100ns;
        if (timing is not null)
        {
            timing.LastStage = "render";
            timing.RenderStartedAtTicks = Stopwatch.GetTimestamp();
        }

        // ContentSize 变化 → Recreate + 刷新客户区（FFmpeg gfxcapture 同款，在消费侧执行）
        if (contentSize.Width != _capSize.Width || contentSize.Height != _capSize.Height)
        {
            // 最小化窗口的 ContentSize 会缩成图标尺寸，此时不 Recreate（对齐 V1 的 IsIconic 保护）：
            // 保留现有资源与缓存帧继续供图，窗口还原后尺寸再变化时自然恢复
            if (User32.IsIconic(_hWnd))
            {
                return false;
            }

            // Geometry/resource changes must not fall back to pixels labelled with old bounds.
            // Invalidate before Recreate or disposal can fail; retain the source high-water mark.
            InvalidatePublishedFrames();
            _diagRecreates++;
            if (timing is not null) timing.Recreated = true;
            Debug.WriteLine($"[WGC V2] Recreate: {_capSize.Width}x{_capSize.Height} -> {contentSize.Width}x{contentSize.Height}");

            // Recreate 必须在帧池的创建线程上执行（跨线程抛 RPC_E_WRONG_THREAD）；
            // 失败异常交由 Capture() 的阶段0兜底记录并跳过本帧
            // 此处池必然存在：上方 TryGetNextFrame 即在其上成功取帧（且与 Stop 持 _lock 互斥）
            var framePool = _captureFramePool!;
            try
            {
                RunOnWgcThread(() => framePool.Recreate(_d3dDevice, _pixelFormat, 2, contentSize));
                _recreateFailures = 0;
            }
            catch (Exception e)
            {
                timing?.RecordFailure(e);
                // FFmpeg gfxcapture 同款哲学：Recreate 失败必须响亮。池未建成时 _capSize 保持旧值，
                // 后续帧继续重试；同时作废广播帧与缓存时间戳，让 Capture 返回空（上层按截图失败处理），
                // 而不是持续输出变尺寸前的旧画面（静默冻结）
                _recreateFailures++;
                InvalidatePublishedFrames();
                if (_wgcPump?.IsFaulted == true)
                {
                    // Recreate may still be executing. Stop further pool/device access and retire
                    // after this frame has been disposed by the method's using declaration.
                    IsCapturing = false;
                    _generation?.Deactivate();
                }
                Debug.WriteLine($"[WGC V2] Recreate 失败（连续 {_recreateFailures} 次）: {e.GetType().Name}: {e.Message}");
                return false;
            }

            _capSize = contentSize;
            (_region, _captureRect) = GetGameScreenInfo(_hWnd);

            // 单飞闸门保证同一时刻只有一个 Capture 在执行，Recreate 时不存在在途阶段2消费，
            // 可直接销毁旧尺寸资源（ Ensure* 会按新尺寸惰性重建）
            _packUav?.Dispose();
            _packUav = null;
            _packGpuBuf?.Dispose();
            _packGpuBuf = null;
            _packStagingBuf?.Dispose();
            _packStagingBuf = null;
            _stagingTexture?.Dispose();
            _stagingTexture = null;
            _gpuTextureRtv?.Dispose();
            _gpuTextureRtv = null;
            _gpuTexture?.Dispose();
            _gpuTexture = null;
            _cachedBgr?.Dispose();
            _cachedBgr = null;
            InvalidatePublishedFrames();
            _hdrOutputTexture?.Dispose();
            _hdrOutputTexture = null;
            _hdrOutputUav?.Dispose();
            _hdrOutputUav = null;

            // 本帧 surface 仍是 Recreate 前的旧尺寸，与刚按新窗口几何刷新的 _region 不匹配：
            // 变大时 CopySubresourceRegion 源越界（E_INVALIDARG）/ draw 采样 UV 越界。
            // 跳过本帧，待 Recreate 后的新尺寸帧到达再渲染
            return false;
        }

        try
        {
            using var surface = Direct3D11Helper.CreateSharpDXTexture2D(frame.Surface);
            var source = _isHdrEnabled ? ProcessHdrTexture(surface) : surface;
            var d3dDevice = source.Device;
            // A failed GPU write must not leave newer/partial pixels labelled as the old frame.
            // Keep the generation high-water mark, but publish no identity until the draw succeeds.
            _gpuFrameTs = 0;
            _gpuSourceInfo = null;
            EnsureGpuTexture(d3dDevice, contentSize.Width, contentSize.Height, _region);
            var context = d3dDevice.ImmediateContext;

            if (_useDrawWrite)
            {
                // FFmpeg gfxcapture 式 draw 写入：客户区裁剪折进 UV 窗口，一次 draw 渲染进自有纹理
                var drawStage = "EnsureDrawResources";
                try
                {
                    EnsureDrawResources(d3dDevice);

                    var srcW = source.Description.Width;
                    var srcH = source.Description.Height;
                    var region = _region;
                    var uvMinX = region == null ? 0f : region.Value.Left / (float)srcW;
                    var uvMinY = region == null ? 0f : region.Value.Top / (float)srcH;
                    var uvMaxX = region == null ? 1f : region.Value.Right / (float)srcW;
                    var uvMaxY = region == null ? 1f : region.Value.Bottom / (float)srcH;

                    drawStage = "MapConstantBuffer";
                    // 必须 WriteDiscard：cb 仍绑定在上一帧 draw 的 PS 槽上，普通 Write 会 E_INVALIDARG。
                    // 注意 WriteDiscard 不能与 DoNotWait 组合（运行时校验直接 E_INVALIDARG）；
                    // GPU 积压时的阻塞由需求驱动模型收束在消费线程自身，无跨线程冻结
                    var cbMap = context.MapSubresource(_drawCb, 0, MapMode.WriteDiscard, SharpDX.Direct3D11.MapFlags.None);
                    Marshal.WriteInt32(cbMap.DataPointer, 0, BitConverter.SingleToInt32Bits(uvMinX));
                    Marshal.WriteInt32(cbMap.DataPointer, 4, BitConverter.SingleToInt32Bits(uvMinY));
                    Marshal.WriteInt32(cbMap.DataPointer, 8, BitConverter.SingleToInt32Bits(uvMaxX));
                    Marshal.WriteInt32(cbMap.DataPointer, 12, BitConverter.SingleToInt32Bits(uvMaxY));
                    context.UnmapSubresource(_drawCb, 0);

                    drawStage = "CreateSRV";
                    using var srv = new ShaderResourceView(d3dDevice, source);

                    drawStage = "Bind";
                    context.InputAssembler.PrimitiveTopology = SharpDX.Direct3D.PrimitiveTopology.TriangleList;
                    context.VertexShader.Set(_drawVs);
                    // VS 里也读 uvWindow（cb 寄存器），必须同样绑定，否则 uv 恒为 (0,0)、整屏变成单色
                    context.VertexShader.SetConstantBuffer(0, _drawCb);
                    context.PixelShader.Set(_drawPs);
                    context.PixelShader.SetSampler(0, _drawSampler);
                    context.PixelShader.SetConstantBuffer(0, _drawCb);
                    context.PixelShader.SetShaderResource(0, srv);
                    var vpW = region == null ? srcW : region.Value.Right - region.Value.Left;
                    var vpH = region == null ? srcH : region.Value.Bottom - region.Value.Top;
                    context.Rasterizer.SetViewport(0f, 0f, vpW, vpH);
                    context.OutputMerger.SetTargets(_gpuTextureRtv);

                    drawStage = "Draw";
                    context.Draw(3, 0);
                    context.PixelShader.SetShaderResource(0, null);
                    context.OutputMerger.SetTargets((RenderTargetView)null!);
                }
                catch (SharpDXException e)
                {
                    timing?.RecordFailure(e);
                    HandleSharpDxError(e);
                    return false;
                }
                catch (Exception e)
                {
                    timing?.RecordFailure(e);
                    Debug.WriteLine($"[WGC V2][draw] 失败于 {drawStage}: {e.Message}");
                    return false;
                }
            }
            else
            {
                // 旧版拷贝路径（A/B 对比用）
                if (_region != null)
                {
                    context.CopySubresourceRegion(source, 0, _region, _gpuTexture, 0);
                }
                else
                {
                    context.CopyResource(source, _gpuTexture);
                }
            }

            _gpuFrameTs = frameTs;
            _gpuSourceInfo = sourceInfo;
            _diagFrames++;
            return true;
        }
        catch (SharpDXException e)
        {
            timing?.RecordFailure(e);
            HandleSharpDxError(e);
            return false;
        }
        catch (Exception e)
        {
            timing?.RecordFailure(e);
            Debug.WriteLine($"[WGC V2] 渲染新帧失败: {e.Message}");
            return false;
        }
    }

    /// <summary>One native pull from the current generation's pool; called only under the existing state lock.</summary>
    private Direct3D11CaptureFrame? TakeNextFrame() => _captureFramePool?.TryGetNextFrame();

    /// <summary>Ordinary capture avoids diagnostic allocation and extra clock reads.</summary>
    public GameCaptureFrame? Capture() => ReadbackMode == GameCaptureReadbackMode.Blocking
        ? CaptureCore(null) : CapturePolling(null).Frame;

    /// <summary>Capture once with local wall-clock stages, including null and exceptional completion.</summary>
    public GameCaptureFrame? Capture(out GameCaptureCallTiming timing) =>
        ReadbackMode == GameCaptureReadbackMode.Blocking
            ? GameCaptureCallTiming.Run(CaptureCore, out timing)
            : GameCaptureCallTiming.RunAttempt(CapturePolling, out timing).Frame;

    /// <summary>Shared capture path; optional clocks do not change native calls, locks, or ownership.</summary>
    private GameCaptureFrame? CaptureCore(GameCaptureCallTiming? timing)
    {
        // 单飞闸门：并发消费方逐个进入
        var captureGateTaken = false;
        try
        {
            // Preserve the ordinary lock's Enter(ref bool)/finally semantics. Only
            // diagnostics probe contention; a failed probe still waits normally.
            if (timing is null) Monitor.Enter(_captureGate, ref captureGateTaken);
            else
            {
                timing.CaptureGateProbeStartedAtTicks = Stopwatch.GetTimestamp();
                Monitor.TryEnter(_captureGate, 0, ref captureGateTaken);
                timing.CaptureGateContended = !captureGateTaken;
                timing.CaptureGateProbeCompletedAtTicks = Stopwatch.GetTimestamp();
                if (!captureGateTaken) Monitor.Enter(_captureGate, ref captureGateTaken);
            }
            if (timing is not null)
            {
                timing.CaptureGateAcquiredAtTicks = Stopwatch.GetTimestamp();
                timing.LastStage = "state_lock";
            }
            // 阶段1（持 _lock）：状态校验、无新到达判定、GPU 打包 BGR24 + 拷入 staging buffer（同 tick）。
            // 临界区仅命令提交
            SharpDX.Direct3D11.Device? d3dDevice = null;
            RECT? rect;
            long frameTs;
            GameCaptureSourceInfo? sourceInfo;
            int gpuW = 0;
            int gpuH = 0;
            var isCacheHit = false;
            lock (_lock)
            {
                if (timing is not null)
                {
                    timing.StateLockAcquiredAtTicks = Stopwatch.GetTimestamp();
                    timing.LastStage = "state_check";
                    timing.CpuConvert = _useCpuConvert;
                    timing.DrawWrite = _useDrawWrite;
                }
                // A call selected before a concurrent Stop/Start must not execute the wrong readback mode.
                if (ReadbackMode != GameCaptureReadbackMode.Blocking || !IsCapturing || _generation?.IsActive != true)
                {
                    // 按秒级节流输出原因，避免静默返回导致"持续截图失败"无从定位
                    var nowMs = Environment.TickCount64;
                    if (nowMs - _lastNullLogMs >= 1000)
                    {
                        _lastNullLogMs = nowMs;
                        Debug.WriteLine("[WGC V2] Capture 返回空: 会话未启动或已停止");
                    }

                    return null;
                }

                // 阶段0（需求驱动）：消费线程主动取帧并绘制，回调线程只做信号计数。
                // 任何异常都不允许逃出 Capture——触发器线程会因此整个停摆
                try
                {
                    try { TryRenderNewFrameLocked(timing); }
                    finally
                    {
                        if (timing?.RenderStartedAtTicks is not null)
                            timing.RenderCompletedAtTicks = Stopwatch.GetTimestamp();
                    }
                }
                catch (Exception e)
                {
                    timing?.RecordFailure(e);
                    var nowMs = Environment.TickCount64;
                    if (nowMs - _lastNullLogMs >= 1000)
                    {
                        _lastNullLogMs = nowMs;
                        Debug.WriteLine($"[WGC V2] 取帧/绘制异常: {e.GetType().Name}: {e.Message}");
                    }
                }

                if (!IsCapturing || _generation?.IsActive != true)
                {
                    // Do not invert lifecycleGate -> _lock while holding the capture gate.
                    // This frame has already been disposed; queued retirement safely follows
                    // any timed-out native operation before a replacement Start is allowed.
                    var generation = _generation;
                    if (generation != null)
                        ThreadPool.QueueUserWorkItem(_ => StopGeneration(generation));
                    return null;
                }

                if (_gpuTexture == null || _gpuFrameTs == 0)
                {
                    var nowMs = Environment.TickCount64;
                    if (nowMs - _lastNullLogMs >= 1000)
                    {
                        _lastNullLogMs = nowMs;
                        Debug.WriteLine("[WGC V2] Capture 返回空: 尚未收到任何帧（DWM 未推帧，目标窗口可能最小化或尚未渲染）");
                    }

                    return null;
                }

                rect = _captureRect;
                frameTs = _gpuFrameTs;

                // 无新到达（广播纹理时间戳未变）：克隆缓存——零 GPU/PCIe/CvtColor 路径
                isCacheHit = _cachedBgr != null && _cachedFrameTs == frameTs;
                // Snapshot metadata for the chosen pixels before staging/readback leaves _lock.
                sourceInfo = isCacheHit ? _cachedSourceInfo : _gpuSourceInfo;
                if (timing is not null) timing.CacheHit = isCacheHit;
                if (!isCacheHit)
                {
                    if (timing is not null) { timing.LastStage = "submit"; timing.SubmitStartedAtTicks = Stopwatch.GetTimestamp(); }
                    try
                    {
                        d3dDevice = _gpuTexture.Device;
                        gpuW = _gpuTexture.Description.Width;
                        gpuH = _gpuTexture.Description.Height;

                        var context = d3dDevice.ImmediateContext;

                        if (_useCpuConvert)
                        {
                            // CPU 转换回退路径：BGRA 整帧拷入 staging 纹理（阶段2 Map + CvtColor）
                            EnsureStagingTextureLocked(d3dDevice, gpuW, gpuH);
                            var ts1 = Stopwatch.GetTimestamp();
                            context.CopyResource(_gpuTexture, _stagingTexture);
                            _sumStageMs += (Stopwatch.GetTimestamp() - ts1) * 1000.0 / Stopwatch.Frequency;
                        }
                        else
                        {
                            EnsurePackResourcesLocked(d3dDevice, gpuW, gpuH);
                            var total = gpuW * gpuH;

                            // dims 常量（WriteDiscard：cb 可能仍绑定在上一帧 compute 槽上）
                            var ts1 = Stopwatch.GetTimestamp();
                            var cbMap = context.MapSubresource(_packCb, 0, MapMode.WriteDiscard, SharpDX.Direct3D11.MapFlags.None);
                            Marshal.WriteInt32(cbMap.DataPointer, 0, gpuW);
                            Marshal.WriteInt32(cbMap.DataPointer, 4, gpuH);
                            Marshal.WriteInt32(cbMap.DataPointer, 8, total);
                            context.UnmapSubresource(_packCb, 0);

                            // GPU 打包 BGR24 → staging buffer（异步入队，阶段2 Map 等待完成）
                            var ts2 = Stopwatch.GetTimestamp();
                            using var srv = new ShaderResourceView(d3dDevice, _gpuTexture);
                            var pixelGroups = (total + 3) / 4;   // 向上取整，与 EnsurePackResourcesLocked 的缓冲区分配一致
                            var groups = (pixelGroups + 63) / 64;
                            context.ComputeShader.Set(_packCs);
                            context.ComputeShader.SetShaderResource(0, srv);
                            context.ComputeShader.SetUnorderedAccessView(0, _packUav);
                            context.ComputeShader.SetConstantBuffer(0, _packCb);
                            context.Dispatch(groups, 1, 1);
                            context.ComputeShader.SetShaderResource(0, null);
                            context.ComputeShader.SetUnorderedAccessView(0, null);
                            context.ComputeShader.Set(null);
                            _sumPackMs += (Stopwatch.GetTimestamp() - ts2) * 1000.0 / Stopwatch.Frequency;

                            // 拷入 CPU 可读的 staging buffer
                            var ts3 = Stopwatch.GetTimestamp();
                            context.CopyResource(_packGpuBuf, _packStagingBuf);
                            _sumCopyMs += (Stopwatch.GetTimestamp() - ts3) * 1000.0 / Stopwatch.Frequency;
                        }
                    }
                    finally { if (timing is not null) timing.SubmitCompletedAtTicks = Stopwatch.GetTimestamp(); }
                }

                // 两条路径都计为在途：Stop/尺寸变化销毁 staging/_cachedBgr 前必须等其归零
                _activeCaptures++;

                _diagTicks++;
                if (isCacheHit) _diagCacheHits++;
                if (_diagTicks % 100 == 0)
                {
                    Debug.WriteLine(
                        $"[WGC V2][diag] ticks={_diagTicks} frames={_diagFrames} arrivals={_generation?.Arrivals ?? 0} cacheHits={_diagCacheHits} recreates={_diagRecreates} " +
                        $"avgMs: pack={_sumPackMs / 100:0.00} copy={_sumCopyMs / 100:0.00} stage={_sumStageMs / 100:0.00} cvt={_sumCvtMs / 100:0.00} map={_sumMapMs / 100:0.00} clone={_sumCloneMs / 100:0.00}");
                    _sumPackMs = _sumCopyMs = _sumStageMs = _sumCvtMs = _sumMapMs = _sumCloneMs = 0;
                }
            }

            Mat? target = null;
            try
            {
                try
                {
                    if (isCacheHit)
                    {
                        // 无新帧：克隆缓存给消费者私有副本（零 GPU 拷贝、零 PCIe 回读、零 CvtColor）
                        var ts3 = Stopwatch.GetTimestamp();
                        if (timing is not null) { timing.LastStage = "cpu_copy"; timing.CpuCopyStartedAtTicks = ts3; }
                        target = AcquireBgrMat(_cachedBgr!.Rows, _cachedBgr.Cols);
                        _cachedBgr.CopyTo(target);
                        _sumCloneMs += (Stopwatch.GetTimestamp() - ts3) * 1000.0 / Stopwatch.Frequency;
                    }
                    else if (_useCpuConvert)
                    {
                        // 阶段2（锁外，CPU 转换回退路径）：Map BGRA staging 纹理 → CvtColor 写缓存 → 克隆给消费者。
                        // 普通阻塞 MAP_READ（ffmpeg hwcontext 同款）：等的是自己刚提交的按序拷贝，只阻塞消费线程自身
                        var context = d3dDevice!.ImmediateContext;
                        var stagingDesc = _stagingTexture!.Description;
                        var ts2 = Stopwatch.GetTimestamp();
                        if (timing is not null) { timing.LastStage = "readback_map"; timing.ReadbackMapStartedAtTicks = ts2; }
                        DataBox dataBox;
                        try { dataBox = context.MapSubresource(_stagingTexture, 0, MapMode.Read, SharpDX.Direct3D11.MapFlags.None); }
                        finally { if (timing is not null) timing.ReadbackMapCompletedAtTicks = Stopwatch.GetTimestamp(); }
                        _sumMapMs += (Stopwatch.GetTimestamp() - ts2) * 1000.0 / Stopwatch.Frequency;
                        try
                        {
                            var ts3 = Stopwatch.GetTimestamp();
                            if (timing is not null) { timing.LastStage = "cpu_copy"; timing.CpuCopyStartedAtTicks = ts3; }
                            using var bgra = Mat.FromPixelData(stagingDesc.Height, stagingDesc.Width, MatType.CV_8UC4, dataBox.DataPointer, dataBox.RowPitch);
                            EnsureCache(stagingDesc.Width, stagingDesc.Height);
                            Cv2.CvtColor(bgra, _cachedBgr!, ColorConversionCodes.BGRA2BGR);
                            _cachedFrameTs = frameTs;
                            _cachedSourceInfo = sourceInfo;
                            _sumCvtMs += (Stopwatch.GetTimestamp() - ts3) * 1000.0 / Stopwatch.Frequency;

                            var ts4 = Stopwatch.GetTimestamp();
                            target = AcquireBgrMat(stagingDesc.Height, stagingDesc.Width);
                            _cachedBgr!.CopyTo(target);
                            _sumCloneMs += (Stopwatch.GetTimestamp() - ts4) * 1000.0 / Stopwatch.Frequency;
                        }
                        finally
                        {
                            context.UnmapSubresource(_stagingTexture, 0);
                        }
                    }
                    else
                    {
                        // 阶段2（锁外）：Map staging buffer——内容已是 GPU 打包好的 BGR24（= CV_8UC3 内存布局），
                        // 直接包装读取并写入缓存 + 克隆给消费者（CPU 零转换）。
                        // 普通阻塞 MAP_READ（ffmpeg hwcontext 同款）
                        var context = d3dDevice!.ImmediateContext;
                        var ts2 = Stopwatch.GetTimestamp();
                        if (timing is not null) { timing.LastStage = "readback_map"; timing.ReadbackMapStartedAtTicks = ts2; }
                        DataBox dataBox;
                        try { dataBox = context.MapSubresource(_packStagingBuf, 0, MapMode.Read, SharpDX.Direct3D11.MapFlags.None); }
                        finally { if (timing is not null) timing.ReadbackMapCompletedAtTicks = Stopwatch.GetTimestamp(); }
                        _sumMapMs += (Stopwatch.GetTimestamp() - ts2) * 1000.0 / Stopwatch.Frequency;
                        try
                        {
                            if (timing is not null) { timing.LastStage = "cpu_copy"; timing.CpuCopyStartedAtTicks = Stopwatch.GetTimestamp(); }
                            using var bgr = Mat.FromPixelData(gpuH, gpuW, MatType.CV_8UC3, dataBox.DataPointer, gpuW * 3);
                            EnsureCache(gpuW, gpuH);
                            bgr.CopyTo(_cachedBgr!);
                            _cachedFrameTs = frameTs;
                            _cachedSourceInfo = sourceInfo;

                            var ts4 = Stopwatch.GetTimestamp();
                            target = AcquireBgrMat(gpuH, gpuW);
                            _cachedBgr!.CopyTo(target);
                            _sumCloneMs += (Stopwatch.GetTimestamp() - ts4) * 1000.0 / Stopwatch.Frequency;
                        }
                        finally
                        {
                            context.UnmapSubresource(_packStagingBuf, 0);
                        }
                    }

                }
                finally
                {
                    if (timing?.CpuCopyStartedAtTicks is not null)
                        timing.CpuCopyCompletedAtTicks = Stopwatch.GetTimestamp();
                }
                if (timing is not null) timing.LastStage = "publication";
                // A concurrent close/stop must not publish the readback it was waiting to retire.
                if (_generation?.IsActive != true)
                {
                    ReleaseBgrMat(target);
                    target = null;
                    return null;
                }
                return new GameCaptureFrame(WgcBgrMat.CreateFrom(target, ReleaseBgrMat), rect, sourceInfo);
            }
            catch (SharpDXException e)
            {
                timing?.RecordFailure(e);
                if (target != null)
                {
                    ReleaseBgrMat(target);
                }

                HandleSharpDxError(e);
                return null;
            }
            catch (Exception e)
            {
                timing?.RecordFailure(e);
                if (target != null)
                {
                    ReleaseBgrMat(target);
                }

                // CvtColor/CopyTo 等 OpenCvSharp 异常：池化获取的 Mat 已归还（无泄漏）；
                // 缓存时间戳作废，避免下一 tick 误用残缺缓存
                lock (_lock)
                {
                    _cachedFrameTs = 0;
                    _cachedSourceInfo = null;
                }

                Debug.WriteLine($"[WGC V2] Capture 异常: {e.Message}");
                return null;
            }
            finally
            {
                if (timing is not null) timing.LastStage = "cleanup";
                lock (_lock)
                {
                    _activeCaptures--;
                    Monitor.PulseAll(_lock);
                }
            }
        }
        finally
        {
            if (captureGateTaken) Monitor.Exit(_captureGate);
        }
    }

    private void EnsureCache(int width, int height)
    {
        if (_cachedBgr == null || _cachedBgr.Cols != width || _cachedBgr.Rows != height)
        {
            _cachedBgr?.Dispose();
            _cachedBgr = new Mat(height, width, MatType.CV_8UC3);
        }
    }

    private Mat AcquireBgrMat(int height, int width)
    {
        lock (_lock)
        {
            while (_bgrQueue.TryDequeue(out var mat))
            {
                if (_bgrBorrowed.Add(mat))
                {
                    if (mat.IsDisposed)
                    {
                        _bgrBorrowed.Remove(mat);
                        continue;
                    }
                    if (mat.Rows == height && mat.Cols == width && mat.Type() == MatType.CV_8UC3)
                    {
                        return mat;
                    }
                    _bgrBorrowed.Remove(mat);
                    mat.Dispose();
                }
                else
                {
                    // 防御分支：队内 Mat 不应同时存在于借出集合（账本错乱才可达）
                    var fresh = new Mat(height, width, MatType.CV_8UC3);
                    _bgrBorrowed.Add(fresh);
                    return fresh;
                }
            }
            return CreateAndRegisterBgrMat(height, width);
        }
    }

    private Mat CreateAndRegisterBgrMat(int height, int width)
    {
        var fresh = new Mat(height, width, MatType.CV_8UC3);
        _bgrBorrowed.Add(fresh);
        return fresh;
    }

    private void ReleaseBgrMat(Mat mat)
    {
        lock (_lock)
        {
            if (mat == null || !_bgrBorrowed.Remove(mat))
            {
                mat?.Dispose();
                return;
            }
            if (mat.IsDisposed)
            {
                mat.Dispose();
                return;
            }
            if (_bgrPoolClosed)
            {
                mat.Dispose();
                return;
            }
            if (_bgrQueue.Count < MaxPoolSize)
            {
                _bgrQueue.Enqueue(mat);
            }
            else
            {
                if (_bgrQueue.TryDequeue(out var stale))
                {
                    stale.Dispose();
                }
                _bgrQueue.Enqueue(mat);
            }
        }
    }


    public void Stop()
    {
        lock (_lifecycleGate)
        lock (_lock) StopCore();
    }

    /// <summary>
    /// Blocks capture immediately, waits for CPU readback, then queues owner-thread
    /// cleanup behind any running native action. Timeout retains resources and prevents restart.
    /// Caller holds _lock; the cleanup action itself never takes that lock.
    /// </summary>
    private bool StopCore()
    {
        IsCapturing = false;
        _generation?.Deactivate();
        _bgrPoolClosed = true;
        // IsCapturing=false 已挡住新的 Capture；Monitor.Wait 放锁，让在途 Map/CvtColor 的 finally 归零。
        while (_activeCaptures > 0) Monitor.Wait(_lock);
        // An idle pending GPU copy is not an active caller; never Map it during Stop.
        _readbackSlot?.Stop();
        _pendingReadbackResource = null;
        if (_wgcPump is null)
        {
            _generation = null;
            _hWnd = 0;
            return true;
        }

        _pumpRetirement ??= _wgcPump.Retire(DisposeSessionResources);
        try
        {
            if (!WgcCapturePump.WaitWithoutWrapping(_pumpRetirement, WgcDispatchTimeout))
            {
                Debug.WriteLine("[WGC V2] Stop pending: native operation still owns its resources; capture/restart disabled.");
                return false;
            }
        }
        catch (Exception error)
        {
            // A cleanup failure stays observable and prevents this instance from starting another session.
            Debug.WriteLine($"[WGC V2] Stop cleanup failed: {error}");
            return false;
        }

        _pumpRetirement = null;
        _wgcPump = null;
        _generation = null;
        _hWnd = 0;
        return true;
    }

    /// <summary>Clears pixel publication without forgetting already-acquired source identities.</summary>
    private void InvalidatePublishedFrames()
    {
        _cachedCaptureRect = null;
        _cachedFrameTs = 0;
        _cachedSourceInfo = null;
        _gpuFrameTs = 0;
        _gpuSourceInfo = null;
    }

    /// <summary>
    /// Final owner-thread cleanup, after all pump work and CPU readbacks have finished.
    /// Each resource is attempted even if another disposal fails; errors prevent reuse.
    /// </summary>
    private void DisposeSessionResources()
    {
        var errors = new List<Exception>();
        try
        {
            if (_captureItem != null && _captureClosedHandler != null)
                _captureItem.Closed -= _captureClosedHandler;
        }
        catch (Exception error) { errors.Add(error); }
        try
        {
            if (_captureFramePool != null && _frameArrivedHandler != null)
                _captureFramePool.FrameArrived -= _frameArrivedHandler;
        }
        catch (Exception error) { errors.Add(error); }
        _captureClosedHandler = null;
        _frameArrivedHandler = null;
        DisposeOwned(ref _captureSession, errors);
        DisposeOwned(ref _captureFramePool, errors);
        _captureItem = null;
        DisposeOwned(ref _gpuTextureRtv, errors);
        DisposeOwned(ref _gpuTexture, errors);
        DisposeOwned(ref _drawVs, errors);
        DisposeOwned(ref _drawPs, errors);
        DisposeOwned(ref _drawSampler, errors);
        DisposeOwned(ref _drawCb, errors);
        DisposeOwned(ref _packCs, errors);
        DisposeOwned(ref _packCb, errors);
        DisposeOwned(ref _packUav, errors);
        DisposeOwned(ref _packGpuBuf, errors);
        DisposeOwned(ref _packStagingBuf, errors);
        DisposeOwned(ref _stagingTexture, errors);
        DisposeOwned(ref _cachedBgr, errors);
        InvalidatePublishedFrames();
        while (_bgrQueue.TryDequeue(out var pooled)) DisposeOwned(ref pooled, errors);
        DisposeOwned(ref _hdrOutputTexture, errors);
        DisposeOwned(ref _hdrOutputUav, errors);
        DisposeOwned(ref _hdrComputeShader, errors);
        DisposeOwned(ref _d3dDevice, errors);
        if (errors.Count > 0) throw new AggregateException("WGC session cleanup failed.", errors);
    }

    /// <summary>Detaches an owned disposable before disposal, retaining failures for final reporting.</summary>
    private static void DisposeOwned<T>(ref T? resource, List<Exception> errors) where T : class, IDisposable
    {
        var owned = resource;
        resource = null;
        try { owned?.Dispose(); }
        catch (Exception error) { errors.Add(error); }
    }

    /// <summary>Never wait on the caller lock from a WinRT event or the pump thread.</summary>
    private void CaptureItemOnClosed(WgcCaptureGeneration generation)
    {
        if (!generation.Deactivate()) return;
        ThreadPool.QueueUserWorkItem(_ => StopGeneration(generation));
    }

    /// <summary>Checks the captured generation again when an asynchronously queued close is serviced.</summary>
    internal void StopGeneration(WgcCaptureGeneration generation)
    {
        lock (_lifecycleGate)
        lock (_lock)
        {
            if (ReferenceEquals(_generation, generation)) StopCore();
        }
    }

    /// <summary>
    /// FFmpeg gfxcapture 同款：把 WGC 推帧率限到消费需求率（26100+，IGraphicsCaptureSession5）。
    /// C# 投影（TFM 22621）不含该接口，走 QI + vtable 直调；不可用/失败仅告警降级，不影响捕获。
    /// </summary>
    private void TryApplyMinUpdateInterval(GraphicsCaptureSession session)
    {
        if (_minUpdateIntervalHns <= 0)
        {
            Debug.WriteLine("[WGC V2] MinUpdateInterval=0，不启用限流");
            return;
        }

        if (!ApiInformation.IsPropertyPresent("Windows.Graphics.Capture.GraphicsCaptureSession", "MinUpdateInterval"))
        {
            Debug.WriteLine("[WGC V2] MinUpdateInterval 不可用，跳过限流（取帧逻辑不依赖它）");
            return;
        }

        try
        {
            // IGraphicsCaptureSession5 {67C0EA62-1F85-5061-925A-239BE0AC09CB}
            var iid = GraphicsCaptureSession5Iid;
            var unknown = Marshal.GetIUnknownForObject(session);
            try
            {
                if (Marshal.QueryInterface(unknown, ref iid, out var session5) != 0)
                {
                    Debug.WriteLine("[WGC V2] QueryInterface IGraphicsCaptureSession5 失败，跳过限流");
                    return;
                }

                try
                {
                    // vtable 布局：IUnknown 0-2 + IInspectable 3-5 + get_MinUpdateInterval 6 + put_MinUpdateInterval 7
                    var vtbl = Marshal.ReadIntPtr(session5);
                    var putPtr = Marshal.ReadIntPtr(vtbl, PutMinUpdateIntervalVtableSlot * IntPtr.Size);
                    var put = Marshal.GetDelegateForFunctionPointer<PutMinUpdateIntervalDelegate>(putPtr);
                    var hr = put(session5, _minUpdateIntervalHns);
                    if (hr < 0)
                    {
                        Debug.WriteLine($"[WGC V2] put_MinUpdateInterval 失败: 0x{hr:X8}");
                    }
                    else
                    {
                        Debug.WriteLine($"[WGC V2] MinUpdateInterval 已设置: {_minUpdateIntervalHns / 10000.0:0.##}ms");
                    }
                }
                finally
                {
                    Marshal.Release(session5);
                }
            }
            finally
            {
                Marshal.Release(unknown);
            }
        }
        catch (Exception e)
        {
            Debug.WriteLine($"[WGC V2] 应用 MinUpdateInterval 异常: {e.Message}");
        }
    }
}
