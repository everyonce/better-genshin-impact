namespace Fischless.GameCapture.DwmSharedSurface;

/// <summary>Owns one device and its dependent staging resource; callers serialize use with the capture lifecycle lock.</summary>
internal sealed class SharedSurfaceResources<TDevice, TStaging>(Func<TDevice> createDevice) : IDisposable
    where TDevice : class, IDisposable
    where TStaging : class, IDisposable
{
    /// <summary>The current device, absent after stop or failed replacement.</summary>
    internal TDevice? Device { get; private set; }

    /// <summary>The staging resource belongs exclusively to the current device.</summary>
    internal TStaging? Staging { get; private set; }

    /// <summary>Retires both old resources before creating a replacement; failure cannot retain disposed references.</summary>
    internal void ResetDevice()
    {
        Dispose();
        Device = createDevice();
    }

    /// <summary>Creates staging lazily against the current device, including when dimensions did not change after reset.</summary>
    internal TStaging GetOrCreateStaging(Func<TDevice, TStaging> createStaging)
    {
        var device = Device ?? throw new InvalidOperationException("The shared-surface device is unavailable.");
        return Staging ??= createStaging(device);
    }

    /// <summary>Detaches the old staging reference before a resize can dispose or recreate it.</summary>
    internal void ClearStaging()
    {
        var staging = Staging;
        Staging = null;
        staging?.Dispose();
    }

    /// <summary>Attempts both releases exactly once, even if staging disposal fails; ResetDevice may start a new lifetime.</summary>
    public void Dispose()
    {
        var device = Device;
        var staging = Staging;
        Device = null;
        Staging = null;
        try { staging?.Dispose(); }
        finally { device?.Dispose(); }
    }
}
