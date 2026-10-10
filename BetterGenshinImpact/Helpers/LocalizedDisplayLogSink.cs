using System;
using System.Collections.Generic;
using System.Linq;
using BetterGenshinImpact.Service.I18n;
using Serilog.Core;
using Serilog.Events;

namespace BetterGenshinImpact.Helpers;

/// <summary>
/// Localizes exact string property values for a display sink without changing the source event.
/// Templates, property names, dictionary keys, exceptions, and unrecognized text remain intact.
/// </summary>
public sealed class LocalizedDisplayLogSink : ILogEventSink, IDisposable
{
    private readonly ILogEventSink _innerSink;
    private readonly Func<string, string> _translate;

    public LocalizedDisplayLogSink(ILogEventSink innerSink, Func<string, string>? translate = null)
    {
        _innerSink = innerSink ?? throw new ArgumentNullException(nameof(innerSink));
        _translate = translate ?? I18nService.Instance.Translate;
    }

    public void Emit(LogEvent logEvent)
    {
        ArgumentNullException.ThrowIfNull(logEvent);
        var properties = logEvent.Properties.Select(property =>
            new LogEventProperty(property.Key, LocalizeValue(property.Value)));
        var displayEvent = new LogEvent(
            logEvent.Timestamp,
            logEvent.Level,
            logEvent.Exception,
            logEvent.MessageTemplate,
            properties,
            logEvent.TraceId ?? default,
            logEvent.SpanId ?? default);
        _innerSink.Emit(displayEvent);
    }

    private LogEventPropertyValue LocalizeValue(LogEventPropertyValue value) => value switch
    {
        ScalarValue { Value: string text } => new ScalarValue(_translate(text)),
        SequenceValue sequence => new SequenceValue(sequence.Elements.Select(LocalizeValue)),
        StructureValue structure => new StructureValue(
            structure.Properties.Select(property =>
                new LogEventProperty(property.Name, LocalizeValue(property.Value))),
            structure.TypeTag),
        DictionaryValue dictionary => new DictionaryValue(dictionary.Elements.Select(pair =>
            new KeyValuePair<ScalarValue, LogEventPropertyValue>(pair.Key, LocalizeValue(pair.Value)))),
        _ => value
    };

    public void Dispose() => (_innerSink as IDisposable)?.Dispose();
}
