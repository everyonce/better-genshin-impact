using System.Diagnostics;
using BetterGenshinImpact.Helpers;
using Serilog.Core;
using Serilog.Events;
using Serilog.Parsing;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class DisplayLogLocalizationTests
{
    private static string Translate(string value) => value switch
    {
        "自动秘境" => "Auto Domain",
        "开启" => "On",
        _ => value
    };

    [Fact]
    public void DisplayCopyTranslatesKnownValuesAndPreservesSourceEventAndMetadata()
    {
        var output = new CollectingSink();
        using var sink = new LocalizedDisplayLogSink(output, Translate);
        var timestamp = new DateTimeOffset(2026, 10, 10, 12, 30, 0, TimeSpan.FromHours(-5));
        var exception = new InvalidOperationException("Original exception");
        var template = new MessageTemplateParser().Parse("{Task}: {State}; {CustomPath}");
        const string customPath = @"C:\Users\custom\自动秘境\开启.json";
        var traceId = ActivityTraceId.CreateRandom();
        var spanId = ActivitySpanId.CreateRandom();
        var source = new LogEvent(timestamp, LogEventLevel.Warning, exception, template,
        [
            new LogEventProperty("Task", new ScalarValue("自动秘境")),
            new LogEventProperty("State", new ScalarValue("开启")),
            new LogEventProperty("CustomPath", new ScalarValue(customPath)),
            new LogEventProperty("CustomName", new ScalarValue("My custom task 开启")),
            new LogEventProperty("Count", new ScalarValue(7))
        ], traceId, spanId);
        var originalMessage = source.RenderMessage();

        sink.Emit(source);

        var display = Assert.Single(output.Events);
        Assert.NotSame(source, display);
        Assert.Equal("Auto Domain", Assert.IsType<ScalarValue>(display.Properties["Task"]).Value);
        Assert.Equal("On", Assert.IsType<ScalarValue>(display.Properties["State"]).Value);
        Assert.Equal(customPath, Assert.IsType<ScalarValue>(display.Properties["CustomPath"]).Value);
        Assert.Equal("My custom task 开启", Assert.IsType<ScalarValue>(display.Properties["CustomName"]).Value);
        Assert.Equal(7, Assert.IsType<ScalarValue>(display.Properties["Count"]).Value);
        Assert.Equal("自动秘境", Assert.IsType<ScalarValue>(source.Properties["Task"]).Value);
        Assert.Equal("开启", Assert.IsType<ScalarValue>(source.Properties["State"]).Value);
        Assert.Equal(originalMessage, source.RenderMessage());
        Assert.Same(template, display.MessageTemplate);
        Assert.Same(exception, display.Exception);
        Assert.Equal(timestamp, display.Timestamp);
        Assert.Equal(source.Level, display.Level);
        Assert.Equal(traceId, display.TraceId);
        Assert.Equal(spanId, display.SpanId);
        Assert.Equal(source.Properties.Keys.Order(), display.Properties.Keys.Order());
    }

    [Fact]
    public void NestedValuesTranslateWithoutChangingPropertyNamesDictionaryKeysOrOriginals()
    {
        var output = new CollectingSink();
        using var sink = new LocalizedDisplayLogSink(output, Translate);
        var originalStructure = new StructureValue(
            [new LogEventProperty("开启", new ScalarValue("开启"))], "OriginalType");
        var originalDictionary = new DictionaryValue(
        [
            new KeyValuePair<ScalarValue, LogEventPropertyValue>(
                new ScalarValue("自动秘境"), new ScalarValue("自动秘境"))
        ]);
        var originalSequence = new SequenceValue(
            [new ScalarValue("自动秘境"), originalStructure, originalDictionary, new ScalarValue(null)]);
        var source = new LogEvent(DateTimeOffset.UtcNow, LogEventLevel.Information, null,
            new MessageTemplateParser().Parse("{@Details}"),
            [new LogEventProperty("Details", originalSequence)]);

        sink.Emit(source);

        var display = Assert.Single(output.Events);
        var sequence = Assert.IsType<SequenceValue>(display.Properties["Details"]);
        Assert.Equal("Auto Domain", Assert.IsType<ScalarValue>(sequence.Elements[0]).Value);
        var structure = Assert.IsType<StructureValue>(sequence.Elements[1]);
        Assert.Equal("OriginalType", structure.TypeTag);
        var property = Assert.Single(structure.Properties);
        Assert.Equal("开启", property.Name);
        Assert.Equal("On", Assert.IsType<ScalarValue>(property.Value).Value);
        var dictionary = Assert.IsType<DictionaryValue>(sequence.Elements[2]);
        var entry = Assert.Single(dictionary.Elements);
        Assert.Equal("自动秘境", entry.Key.Value);
        Assert.Equal("Auto Domain", Assert.IsType<ScalarValue>(entry.Value).Value);
        Assert.Null(Assert.IsType<ScalarValue>(sequence.Elements[3]).Value);
        Assert.Same(originalSequence, source.Properties["Details"]);
        Assert.Equal("自动秘境", Assert.IsType<ScalarValue>(originalSequence.Elements[0]).Value);
        Assert.Equal("开启", Assert.IsType<ScalarValue>(Assert.Single(originalStructure.Properties).Value).Value);
        Assert.Equal("自动秘境", Assert.IsType<ScalarValue>(Assert.Single(originalDictionary.Elements).Value).Value);
        Assert.Null(display.TraceId);
        Assert.Null(display.SpanId);
    }

    private sealed class CollectingSink : ILogEventSink
    {
        public List<LogEvent> Events { get; } = [];
        public void Emit(LogEvent logEvent) => Events.Add(logEvent);
    }
}
