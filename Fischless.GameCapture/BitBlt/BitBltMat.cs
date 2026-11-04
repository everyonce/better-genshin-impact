using OpenCvSharp;

namespace Fischless.GameCapture.BitBlt;

public class BitBltMat : Mat
{
    private readonly BitBltSession _session;
    private readonly IntPtr _data;

    /// <summary>Copies the borrowed-data header without allocating and overwriting an empty native Mat.</summary>
    private BitBltMat(Mat owner, BitBltSession session, IntPtr data) : base(owner)
    {
        _session = session;
        _data = data;
    }

    public static Mat FromPixelData(BitBltSession session, int rows, int cols, MatType type, IntPtr data, long step = 0)
    {
        // Mat(IntPtr) is internal to OpenCvSharp; its supported factory and protected copy constructor
        // provide two owned headers, and the temporary one is disposed before returning the wrapper.
        using var owner = Mat.FromPixelData(rows, cols, type, data, step);
        return new BitBltMat(owner, session, data);
    }

    protected override void DisposeUnmanaged()
    {
        base.DisposeUnmanaged();
        _session.ReleaseBuffer(_data);
    }
}
