using System.Collections.Concurrent;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Fischless.GameCapture.BitBlt;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercises actual buffer ownership with fake pointer IDs, without GDI, game input or native capture.</summary>
public sealed class BitBltBufferPoolTests
{
    /// <summary>A returned allocation is reused and repeated disposal frees it only once.</summary>
    [Fact]
    public void ReusesBuffersAndDisposesExactlyOnce()
    {
        var memory = new AllocationLedger();
        using var pool = memory.CreatePool();
        var first = pool.Rent(64);
        pool.Return(first);
        Assert.Equal(first, pool.Rent(64));
        pool.Return(first);
        pool.Dispose();
        pool.Dispose();
        Assert.Single(memory.Allocated);
        memory.AssertAllFreedOnce();
        Assert.Throws<ObjectDisposedException>(() => pool.Rent(64));
    }

    /// <summary>Stop never frees a still-borrowed frame, but its eventual return cannot leak.</summary>
    [Fact]
    public void LateReturnFreesBorrowedBufferAfterRetirement()
    {
        var memory = new AllocationLedger();
        using var pool = memory.CreatePool();
        var idle = pool.Rent(64);
        var borrowed = pool.Rent(64);
        pool.Return(idle);
        pool.Dispose();
        Assert.True(memory.Freed.ContainsKey(idle));
        Assert.False(memory.Freed.ContainsKey(borrowed));
        pool.Return(borrowed);
        pool.Dispose();
        memory.AssertAllFreedOnce();
    }

    /// <summary>Either ordering of a frame return and session retirement frees every allocation exactly once.</summary>
    [Fact]
    public async Task ConcurrentReturnsAndRetirementDoNotLoseOrDoubleFreeBuffers()
    {
        for (var round = 0; round < 25; round++)
        {
            var memory = new AllocationLedger();
            using var pool = memory.CreatePool();
            var buffers = Enumerable.Range(0, 64).Select(_ => pool.Rent(64)).ToArray();
            var start = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var returns = buffers.Select(buffer => Task.Run(async () =>
            {
                await start.Task;
                pool.Return(buffer);
            })).ToArray();
            var close = Task.Run(async () => { await start.Task; pool.Dispose(); });
            start.SetResult();
            await Task.WhenAll(returns.Append(close)).WaitAsync(TimeSpan.FromSeconds(10));
            pool.Dispose();
            memory.AssertAllFreedOnce();
        }
    }

    /// <summary>Allocator failure leaves no phantom ownership and permits subsequent rents.</summary>
    [Fact]
    public void AllocationFailureLeavesPoolUsable()
    {
        var memory = new AllocationLedger();
        var attempts = 0;
        using var pool = new BitBltBufferPool(bytes =>
            ++attempts == 1 ? throw new OutOfMemoryException() : memory.Allocate(bytes), memory.Free);
        Assert.Throws<OutOfMemoryException>(() => pool.Rent(64));
        var buffer = pool.Rent(64);
        pool.Return(buffer);
        pool.Dispose();
        memory.AssertAllFreedOnce();
    }

    /// <summary>Actual CPU Mat headers retain pixels and return their buffer once, even after the pool retires.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void MatWrapperPreservesPixelsAndReturnsBufferExactlyOnce(bool retireBeforeReturn)
    {
        var freeCount = 0;
        using var pool = new BitBltBufferPool(Marshal.AllocHGlobal, pointer =>
        {
            Interlocked.Increment(ref freeCount);
            Marshal.FreeHGlobal(pointer);
        });
        // Bypass the native GDI constructor; ReleaseBuffer only uses this injected managed pool.
        // This fixture must never call BitBltSession.Dispose, GetImage or any capture lifecycle method.
        var session = (BitBltSession)RuntimeHelpers.GetUninitializedObject(typeof(BitBltSession));
        typeof(BitBltSession).GetField("_bufferPool", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(session, pool);
        var buffer = pool.Rent(12);
        Marshal.Copy(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 }, 0, buffer, 12);
        using var wrapper = BitBltMat.FromPixelData(session, 2, 2, MatType.CV_8UC3, buffer, 6);
        Assert.Equal(buffer, wrapper.Data);
        Assert.Equal(new Vec3b(1, 2, 3), wrapper.At<Vec3b>(0, 0));
        Assert.Equal(new Vec3b(10, 11, 12), wrapper.At<Vec3b>(1, 1));
        if (retireBeforeReturn) pool.Dispose();
        Assert.Equal(0, freeCount);
        wrapper.Dispose();
        wrapper.Dispose();
        Assert.True(wrapper.IsDisposed);
        if (!retireBeforeReturn)
        {
            Assert.Equal(0, freeCount);
            var reused = pool.Rent(12);
            Assert.Equal(buffer, reused);
            pool.Return(reused);
        }
        pool.Dispose();
        Assert.Equal(1, freeCount);
    }

    /// <summary>Tracks unique fake addresses and release counts, so a regression cannot corrupt the test process heap.</summary>
    private sealed class AllocationLedger
    {
        /// <summary>Monotonically assigns fake pointer IDs without allocating unmanaged memory.</summary>
        private int _next;
        /// <summary>Records byte counts for every allocated address.</summary>
        internal ConcurrentDictionary<nint, int> Allocated { get; } = new();
        /// <summary>Records every free attempt, including duplicates.</summary>
        internal ConcurrentDictionary<nint, int> Freed { get; } = new();

        /// <summary>Creates a pool wired to this accounting ledger.</summary>
        internal BitBltBufferPool CreatePool() => new(Allocate, Free);

        /// <summary>Returns a unique nonzero address and remembers its requested size.</summary>
        internal nint Allocate(int bytes)
        {
            nint pointer = Interlocked.Increment(ref _next);
            Assert.True(Allocated.TryAdd(pointer, bytes));
            return pointer;
        }

        /// <summary>Counts release attempts; no native pointer is dereferenced.</summary>
        internal void Free(nint pointer) => Freed.AddOrUpdate(pointer, 1, (_, count) => count + 1);

        /// <summary>Requires every allocated pointer, and no foreign pointer, to be released once.</summary>
        internal void AssertAllFreedOnce()
        {
            Assert.Equal(Allocated.Count, Freed.Count);
            Assert.All(Allocated.Keys, pointer => Assert.Equal(1, Freed[pointer]));
        }
    }
}
