using SharpDX.Direct3D11;
using System.Diagnostics;
using OpenCvSharp;

namespace Fischless.GameCapture.Graphics.Helpers;

public static class Texture2DExtensions
{
    /// <summary>Preserves the existing null-on-failure API for callers without device recovery.</summary>
    public static Mat? CreateMat(this Texture2D staging, Device d3dDevice, Texture2D surfaceTexture, ResourceRegion? region = null) =>
        CreateMat(staging, d3dDevice, surfaceTexture, region, propagateSharpDxErrors: false);

    /// <summary>Copies a texture to owned CPU pixels; callers owning device recovery may opt into SharpDX failures.</summary>
    internal static Mat? CreateMat(this Texture2D staging, Device d3dDevice, Texture2D surfaceTexture, ResourceRegion? region,
        bool propagateSharpDxErrors)
    {
        try
        {
            // Copy data
            if (region != null)
            {
                d3dDevice.ImmediateContext.CopySubresourceRegion(surfaceTexture, 0, region, staging, 0);
            }
            else
            {
                d3dDevice.ImmediateContext.CopyResource(surfaceTexture, staging);
            }

            // 映射纹理以便CPU读取
            var dataBox = d3dDevice.ImmediateContext.MapSubresource(
                staging,
                0,
                MapMode.Read,
                MapFlags.None);

            try
            {
                using var mat = Mat.FromPixelData(staging.Description.Height, staging.Description.Width,
                    MatType.CV_8UC4, dataBox.DataPointer, dataBox.RowPitch);
                return mat.CvtColor(ColorConversionCodes.BGRA2BGR);
            }
            finally
            {
                d3dDevice.ImmediateContext.UnmapSubresource(staging, 0);
            }
        }
        catch (Exception e) when (ShouldSuppressFailure(e, propagateSharpDxErrors))
        {
            Debug.WriteLine("Failed to copy texture to mat.");
            Debug.WriteLine(e.StackTrace);
            return null;
        }
    }

    /// <summary>Preserves legacy null-on-failure callers while letting device owners recover from GPU errors.</summary>
    internal static bool ShouldSuppressFailure(Exception error, bool propagateSharpDxErrors) =>
        !propagateSharpDxErrors || error is not SharpDX.SharpDXException;
}
