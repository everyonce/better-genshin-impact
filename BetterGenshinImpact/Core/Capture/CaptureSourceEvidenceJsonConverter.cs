using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace BetterGenshinImpact.Core.Capture;

/// <summary>Preserve legacy WGC record bytes while giving host evidence an explicit separate tagged representation.</summary>
internal sealed class CaptureSourceEvidenceJsonConverter : JsonConverter<CaptureSourceEvidence>
{
    /// <summary>Allow the serializer to activate this internal native-evidence converter.</summary>
    public CaptureSourceEvidenceJsonConverter() { }

    /// <summary>Native evidence is produced locally, never accepted as command input.</summary>
    public override CaptureSourceEvidence Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        throw new NotSupportedException("Capture evidence cannot be supplied through a command.");

    /// <summary>No host clock is serialized into a WGC source timestamp field.</summary>
    public override void Write(Utf8JsonWriter writer, CaptureSourceEvidence value, JsonSerializerOptions options)
    {
        if (value.WgcSource is { } wgc) { JsonSerializer.Serialize(writer, wgc, options); return; }
        writer.WriteStartObject();
        writer.WriteString("kind", DesktopCapturePolicy.HostAcquisitionV1);
        writer.WritePropertyName("hostSnapshot");
        JsonSerializer.Serialize(writer, value.HostSnapshot, options);
        writer.WriteEndObject();
    }
}
