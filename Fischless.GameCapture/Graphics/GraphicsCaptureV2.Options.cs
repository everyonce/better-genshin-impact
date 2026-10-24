namespace Fischless.GameCapture.Graphics;

/// <summary>Start-selected managed metadata only; queries never acquire a capture lock or perform native work.</summary>
public partial class GraphicsCaptureV2
{
    /// <summary>Source lifetime chosen for this attachment; callers separately check IsCapturing, as for ReadbackMode.</summary>
    public string SourceRetentionMode => _sourceRetentionEnabled ? "hold-until-readback-v1" : "disabled";

    /// <summary>Existing conversion path chosen at startup; this does not report device health or readback readiness.</summary>
    public string ConversionMode => _useCpuConvert ? "cpu" : "gpu";
}
