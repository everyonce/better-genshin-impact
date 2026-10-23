using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Fischless.GameCapture;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Accept only exact existing capture backend names, never numeric, composite, or arbitrary config values.</summary>
internal sealed class CaptureModeJsonConverter : JsonConverter<CaptureModes>
{
    /// <summary>Decode a named backend without permissive enum-number or case coercion.</summary>
    public override CaptureModes Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String)
            throw new JsonException("Capture mode must be an existing named backend.");
        var name = reader.GetString();
        if (!Enum.TryParse<CaptureModes>(name, false, out var mode) || !Enum.IsDefined(mode)
            || !string.Equals(name, mode.ToString(), StringComparison.Ordinal))
            throw new JsonException("Capture mode must be an existing named backend.");
        return mode;
    }

    /// <summary>Keep request fingerprints and responses in the same strict named wire representation.</summary>
    public override void Write(Utf8JsonWriter writer, CaptureModes value, JsonSerializerOptions options)
    {
        if (!Enum.IsDefined(value)) throw new JsonException("Unknown capture backend.");
        writer.WriteStringValue(value.ToString());
    }
}
