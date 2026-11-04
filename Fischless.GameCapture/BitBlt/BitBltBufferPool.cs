using System.Runtime.InteropServices;

namespace Fischless.GameCapture.BitBlt;

/// <summary>Reuses native frame buffers until retirement; outstanding frames retain their own allocations.</summary>
internal sealed class BitBltBufferPool : IDisposable
{
    /// <summary>Serializes buffer return with retirement so no pointer can enter a closed pool.</summary>
    private readonly object _gate = new();
    /// <summary>Only idle allocations belong to the pool; borrowed buffers remain with their Mats.</summary>
    private readonly Stack<nint> _buffers = new();
    /// <summary>Allocation callbacks allow ownership tests without GDI or native memory.</summary>
    private readonly Func<int, nint> _allocate;
    /// <summary>Releases allocations after retirement; tests count each release instead.</summary>
    private readonly Action<nint> _free;
    /// <summary>Retirement is terminal and idempotent.</summary>
    private bool _closed;

    /// <summary>Uses unmanaged allocations in production and accounting callbacks in tests.</summary>
    internal BitBltBufferPool(Func<int, nint>? allocate = null, Action<nint>? free = null)
    {
        _allocate = allocate ?? Marshal.AllocHGlobal;
        _free = free ?? Marshal.FreeHGlobal;
    }

    /// <summary>Transfers one reusable buffer to its caller; a retired pool cannot rent again.</summary>
    internal nint Rent(int bytes)
    {
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_closed, this);
            return _buffers.TryPop(out var buffer) ? buffer : _allocate(bytes);
        }
    }

    /// <summary>Returns a borrowed buffer once, freeing it immediately if its session has retired.</summary>
    internal void Return(nint buffer)
    {
        lock (_gate)
        {
            if (_closed) _free(buffer);
            else _buffers.Push(buffer);
        }
    }

    /// <summary>Closes admission and drains idle buffers exactly once; borrowed buffers are freed on return.</summary>
    public void Dispose()
    {
        lock (_gate)
        {
            if (_closed) return;
            _closed = true;
            while (_buffers.TryPop(out var buffer)) _free(buffer);
        }
    }
}
