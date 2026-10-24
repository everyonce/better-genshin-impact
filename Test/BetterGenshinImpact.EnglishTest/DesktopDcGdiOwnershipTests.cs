using Fischless.GameCapture.DesktopDc;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Executes the actual GDI owner with managed native fakes; these tests open no DC, window or desktop.</summary>
public sealed class DesktopDcGdiOwnershipTests
{
    /// <summary>A successful copy exposes pixels only after flush and restores selection before deleting resources.</summary>
    [Fact]
    public void SuccessHasOneThreadOwnedTransactionAndIdempotentCleanup()
    {
        var native = new FakeGdi();
        var owner = new DesktopDcGdiOwner(native);
        Assert.Throws<InvalidOperationException>(() => owner.Bits);
        owner.Initialize();
        Assert.Throws<InvalidOperationException>(() => owner.Bits);
        owner.Copy(-1920, 40);
        Assert.Equal((nint)40, owner.Bits);
        Assert.Equal((-1920, 40, 1920, 1080), native.CopyRect);
        owner.Dispose();
        Assert.True(owner.CleanupSucceeded);
        Assert.Equal(new[] { "screen", "device", "memory", "bitmap", "layout", "select", "copy", "flush",
            "flush", "restore", "delete_bitmap", "delete_dc", "release_screen" }, native.Calls);
        var count = native.Calls.Count;
        owner.Dispose();
        Assert.Equal(count, native.Calls.Count);
        Assert.All(native.Threads, thread => Assert.Equal(Environment.CurrentManagedThreadId, thread));
        Assert.Throws<InvalidOperationException>(() => owner.Bits);
    }

    /// <summary>Every initialization failure still releases independently acquired resources once.</summary>
    [Theory]
    [InlineData("screen")]
    [InlineData("device")]
    [InlineData("memory")]
    [InlineData("bitmap")]
    [InlineData("layout")]
    [InlineData("select")]
    public void PartialInitializationIsOwnedBeforeFailure(string stage)
    {
        var native = new FakeGdi();
        native.Throws.Add(stage);
        var owner = new DesktopDcGdiOwner(native);
        Assert.Throws<InvalidOperationException>(owner.Initialize);
        owner.Dispose();
        Assert.True(owner.CleanupSucceeded);
        Assert.Equal(stage == "screen" ? 0 : 1, native.Calls.Count(item => item == "release_screen"));
        if (stage == "select")
        {
            Assert.True(native.Calls.IndexOf("delete_dc") < native.Calls.IndexOf("delete_bitmap"));
            Assert.DoesNotContain("restore", native.Calls);
        }
        var count = native.Calls.Count;
        owner.Dispose();
        Assert.Equal(count, native.Calls.Count);
    }

    /// <summary>Copy and flush failures never expose a readable borrowed pointer.</summary>
    [Theory]
    [InlineData("copy")]
    [InlineData("flush")]
    public void FailedCopyNeverPublishesPixels(string stage)
    {
        var native = new FakeGdi();
        var owner = new DesktopDcGdiOwner(native);
        owner.Initialize();
        native.Failures.Add(stage);
        Assert.Throws<InvalidOperationException>(() => owner.Copy(0, 0));
        Assert.Throws<InvalidOperationException>(() => owner.Bits);
        native.Failures.Clear();
        owner.Dispose();
        Assert.True(owner.CleanupSucceeded);
        Assert.Equal(1, native.Calls.Count(item => item == "copy"));
    }

    /// <summary>A failed initial selection is treated as uncertain until its private DC is destroyed.</summary>
    [Fact]
    public void FailedSelectionDeletesDcBeforeBitmap()
    {
        var native = new FakeGdi();
        native.Failures.Add("select");
        var owner = new DesktopDcGdiOwner(native);
        Assert.Throws<InvalidOperationException>(owner.Initialize);
        owner.Dispose();
        Assert.True(owner.CleanupSucceeded);
        Assert.True(native.Calls.IndexOf("delete_dc") < native.Calls.IndexOf("delete_bitmap"));
    }

    /// <summary>Restoration failure remains recorded even if deleting the private DC safely deselects the bitmap.</summary>
    [Fact]
    public void FailedRestoreRetiresDcBeforeBitmapWithoutClaimingCleanSuccess()
    {
        var native = new FakeGdi();
        var owner = new DesktopDcGdiOwner(native);
        owner.Initialize();
        native.Failures.Add("restore");
        owner.Dispose();
        Assert.False(owner.CleanupSucceeded);
        Assert.True(native.Calls.IndexOf("delete_dc") < native.Calls.IndexOf("delete_bitmap"));
        Assert.Single(native.CleanupAttempts("delete_dc"));
        Assert.Contains(owner.CleanupFailures, item => item.StartsWith("restore_bitmap:"));
    }

    /// <summary>When both deselection and private-DC deletion fail, the selected bitmap is not deleted or retried.</summary>
    [Fact]
    public void UncertainSelectionNeverDeletesTheBitmap()
    {
        var native = new FakeGdi();
        var owner = new DesktopDcGdiOwner(native);
        owner.Initialize();
        native.Throws.Add("restore");
        native.Failures.Add("delete_dc");
        owner.Dispose();
        Assert.False(owner.CleanupSucceeded);
        Assert.DoesNotContain("delete_bitmap", native.Calls);
        Assert.Contains("release_screen", native.Calls);
        Assert.Contains(owner.CleanupFailures, item => item.Contains("selection remains uncertain"));
        var count = native.Calls.Count;
        owner.Dispose();
        Assert.Equal(count, native.Calls.Count);
    }

    /// <summary>Independent cleanup failures do not hide subsequent resource-release attempts.</summary>
    [Theory]
    [InlineData("flush")]
    [InlineData("delete_bitmap")]
    [InlineData("delete_dc")]
    [InlineData("release_screen")]
    public void CleanupFailureIsExplicitAndNeverReplayed(string stage)
    {
        var native = new FakeGdi();
        var owner = new DesktopDcGdiOwner(native);
        owner.Initialize();
        native.Throws.Add(stage);
        owner.Dispose();
        Assert.False(owner.CleanupSucceeded);
        Assert.Contains("release_screen", native.Calls);
        Assert.Single(owner.CleanupFailures);
        var count = native.Calls.Count;
        owner.Dispose();
        Assert.Equal(count, native.Calls.Count);
    }

    /// <summary>A nonzero allocation address without its owning bitmap handle cannot be called fully cleaned.</summary>
    [Fact]
    public void MissingBitmapHandleRetainsCleanupUncertainty()
    {
        var native = new FakeGdi { OrphanAddress = true };
        var owner = new DesktopDcGdiOwner(native);
        Assert.Throws<InvalidOperationException>(owner.Initialize);
        owner.Dispose();
        Assert.False(owner.CleanupSucceeded);
        Assert.Contains(owner.CleanupFailures, item => item.StartsWith("bitmap_address:"));
        Assert.DoesNotContain("delete_bitmap", native.Calls);
    }

    /// <summary>The same GDI owner never transfers its acquired DC to a second thread.</summary>
    [Fact]
    public void CrossThreadDisposalIsRejectedBeforeNativeCleanup()
    {
        var native = new FakeGdi();
        var owner = new DesktopDcGdiOwner(native);
        owner.Initialize();
        Exception? observed = null;
        var thread = new Thread(() => { try { owner.Dispose(); } catch (Exception error) { observed = error; } });
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(5)));
        Assert.IsType<InvalidOperationException>(observed);
        Assert.DoesNotContain("release_screen", native.Calls);
        owner.Dispose();
        Assert.True(owner.CleanupSucceeded);
    }

    /// <summary>Bad device or actual allocation metadata is checked before any copy.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    [InlineData(6)]
    [InlineData(7)]
    [InlineData(8)]
    public void UnsupportedDeviceOrDibIsRejected(int kind)
    {
        var native = new FakeGdi();
        native.Device = kind switch
        {
            0 => native.Device with { RasterCaps = 0 },
            1 => native.Device with { Planes = 2 },
            2 => native.Device with { BitsPerPixel = 16 },
            3 => native.Device with { MapMode = 2 },
            4 => native.Device with { WindowX = 1 },
            5 => native.Device with { WindowY = 1 },
            6 => native.Device with { ViewportX = 1 },
            7 => native.Device with { ViewportY = 1 },
            _ => native.Device
        };
        if (kind == 8) native.BitmapLayout = native.BitmapLayout with { Stride = 5759 };
        var owner = new DesktopDcGdiOwner(native);
        Assert.Throws<InvalidOperationException>(owner.Initialize);
        owner.Dispose();
        Assert.True(owner.CleanupSucceeded);
        Assert.DoesNotContain("copy", native.Calls);
    }

    /// <summary>Managed fake tracks actual ownership/ordering, including a selection that may change before throwing.</summary>
    internal sealed class FakeGdi : IDesktopDcGdi
    {
        /// <summary>Ordered invocations and owning managed thread identities.</summary>
        internal readonly List<string> Calls = new();
        /// <summary>Thread for each recorded invocation.</summary>
        internal readonly List<int> Threads = new();
        /// <summary>Configured false-return paths.</summary>
        internal readonly HashSet<string> Failures = new();
        /// <summary>Configured exception paths.</summary>
        internal readonly HashSet<string> Throws = new();
        /// <summary>Injected synchronization/reentrant behavior at the one copy boundary.</summary>
        internal Action? OnCopy;
        /// <summary>Simulates an invalid nonzero address without its corresponding owner handle.</summary>
        internal bool OrphanAddress;
        /// <summary>Actual selected-object state detects unsafe bitmap deletion.</summary>
        private bool _selected;
        /// <summary>Exact signed crop passed to the native copy.</summary>
        internal (int Left, int Top, int Width, int Height) CopyRect;
        /// <summary>Device and DIB metadata default to the admitted layout.</summary>
        internal DesktopDcDeviceInfo Device = new(1, 1, 32, 1, 0, 0, 0, 0);
        /// <summary>Fake allocation's actual metadata.</summary>
        internal DesktopDcBitmapInfo BitmapLayout = new(1920, 1080, 5760, 1, 24, 40);
        /// <summary>Inspect a named cleanup operation without changing the fake.</summary>
        internal IEnumerable<string> CleanupAttempts(string operation) => Calls.Where(item => item == operation);
        /// <summary>Record once, then return or throw the configured result.</summary>
        private bool Hit(string stage)
        {
            Calls.Add(stage); Threads.Add(Environment.CurrentManagedThreadId);
            if (Throws.Contains(stage)) throw new InvalidOperationException(stage + " failed");
            return !Failures.Contains(stage);
        }
        /// <inheritdoc />
        public nint GetScreenDc() => Hit("screen") ? 10 : 0;
        /// <inheritdoc />
        public DesktopDcDeviceInfo ReadDeviceInfo(nint screen) { Hit("device"); return Device; }
        /// <inheritdoc />
        public nint CreateMemoryDc(nint screen) => Hit("memory") ? 20 : 0;
        /// <inheritdoc />
        public nint CreateBitmap(nint screen, int width, int height, int stride, out nint bits)
        {
            bits = 0;
            if (!Hit("bitmap")) return 0;
            Assert.Equal((1920, 1080, 5760), (width, height, stride));
            bits = 40;
            return OrphanAddress ? 0 : 30;
        }
        /// <inheritdoc />
        public DesktopDcBitmapInfo ReadBitmapInfo(nint bitmap) { Hit("layout"); return BitmapLayout; }
        /// <inheritdoc />
        public nint SelectBitmap(nint memory, nint bitmap)
        {
            if (bitmap == 30) { _selected = true; return Hit("select") ? 50 : 0; }
            if (!Hit("restore")) return 0;
            _selected = false; return 30;
        }
        /// <inheritdoc />
        public bool Copy(nint memory, nint screen, int left, int top, int width, int height)
        { CopyRect = (left, top, width, height); var success = Hit("copy"); OnCopy?.Invoke(); return success; }
        /// <inheritdoc />
        public bool Flush() => Hit("flush");
        /// <inheritdoc />
        public bool DeleteMemoryDc(nint memory)
        { if (!Hit("delete_dc")) return false; _selected = false; return true; }
        /// <inheritdoc />
        public bool DeleteBitmap(nint bitmap)
        {
            if (_selected) throw new InvalidOperationException("Deleting a still-selected bitmap");
            return Hit("delete_bitmap");
        }
        /// <inheritdoc />
        public bool ReleaseScreenDc(nint screen) => Hit("release_screen");
    }
}
