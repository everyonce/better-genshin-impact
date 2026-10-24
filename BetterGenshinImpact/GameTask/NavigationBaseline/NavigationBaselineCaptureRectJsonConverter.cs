using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Vanara.PInvoke;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Keep exact pending geometry within the existing journal budget without repeated derived RECT aliases.</summary>
internal sealed class NavigationBaselineCaptureRectJsonConverter : JsonConverter<RECT>
{
    /// <summary>This journal writer never reconstructs native capture resources from serialized geometry.</summary>
    public override RECT Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        throw new NotSupportedException("Navigation capture geometry is written only.");

    /// <summary>Write all four original signed edges; width, height and other aliases are redundant.</summary>
    public override void Write(Utf8JsonWriter writer, RECT value, JsonSerializerOptions options)
    {
        writer.WriteStartObject();
        writer.WriteNumber("left", value.Left);
        writer.WriteNumber("top", value.Top);
        writer.WriteNumber("right", value.Right);
        writer.WriteNumber("bottom", value.Bottom);
        writer.WriteEndObject();
    }
}
