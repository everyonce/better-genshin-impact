using BetterGenshinImpact.GameTask.AutoFight.Script;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;

namespace BetterGenshinImpact.UnitTest.GameTaskTests.AutoFightTests;

/// <summary>Pure parser calls and injected logging must not resolve App or TaskControl services.</summary>
public sealed class CombatParserLoggingTests
{
    /// <summary>Small valid strategy; it exercises the success log without game or asset access.</summary>
    private const string ValidJson = """{"info":{"name":"synthetic","author":"test"},"actions":[{"action":"wait(0.2)"}]}""";

    /// <summary>The metadata/default route parses success and preserves the wrapped JSON error.</summary>
    [Fact]
    public void JsonDefault_ParsesAndPreservesErrorsWithoutApplicationLogger()
    {
        var strategy = JsonCombatStrategyParser.Parse(ValidJson);
        Assert.Equal("synthetic", strategy.Info.Name);
        Assert.Equal("wait(0.2)", Assert.Single(strategy.Actions).Action);
        var error = Assert.Throws<InvalidOperationException>(() => JsonCombatStrategyParser.Parse("{"));
        Assert.IsAssignableFrom<JsonException>(error.InnerException);
        Assert.StartsWith("Invalid JSON combat strategy format:", error.Message);
        Assert.Equal("No actions are defined in the JSON combat strategy",
            Assert.Throws<InvalidOperationException>(() => JsonCombatStrategyParser.Parse("{}")).Message);
    }

    /// <summary>Supplying a runtime logger changes only emitted diagnostics, not the parsed values.</summary>
    [Fact]
    public void JsonInjectedLogger_RecordsSuccessWithoutChangingParsedValues()
    {
        var logger = new RecordingLogger();
        var expected = JsonCombatStrategyParser.Parse(ValidJson);
        var actual = JsonCombatStrategyParser.Parse(ValidJson, logger);
        Assert.Equal(JsonConvert.SerializeObject(expected), JsonConvert.SerializeObject(actual));
        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Information, entry.Level);
        Assert.Contains("synthetic", entry.Message);
        Assert.Contains("1 actions", entry.Message);
    }

    /// <summary>Nested action-name validation receives the injected logger and preserves the failure.</summary>
    [Fact]
    public void JsonInjectedLogger_RecordsTheOriginalValidationFailure()
    {
        const string json = """{"actions":[{"name":"true","action":"wait(1)"}]}""";
        var logger = new RecordingLogger();
        var expected = Assert.Throws<InvalidOperationException>(() => JsonCombatStrategyParser.Parse(json));
        var actual = Assert.Throws<InvalidOperationException>(() => JsonCombatStrategyParser.Parse(json, logger));
        Assert.Equal(expected.Message, actual.Message);
        Assert.Equal(LogLevel.Error, Assert.Single(logger.Entries).Level);
    }

    /// <summary>File overloads carry the supplied logger through nested parsing and keep pure defaults.</summary>
    [Fact]
    public void FileOverloads_ForwardOnlyTheSuppliedLogger()
    {
        WithTemporaryDirectory(directory =>
        {
            var logger = new RecordingLogger();
            var jsonPath = Path.Combine(directory, "strategy.json");
            File.WriteAllText(jsonPath, ValidJson);
            Assert.Equal("synthetic", JsonCombatStrategyParser.ParseFile(jsonPath).Info.Name);
            Assert.Equal("synthetic", JsonCombatStrategyParser.ParseFile(jsonPath, logger).Info.Name);
            Assert.Equal(LogLevel.Information, Assert.Single(logger.Entries).Level);
            logger.Entries.Clear();
            var textPath = Path.Combine(directory, "invalid.txt");
            File.WriteAllText(textPath, "wait(1)");
            var expected = Assert.Throws<Exception>(() => CombatScriptParser.Parse(textPath));
            var actual = Assert.Throws<Exception>(() => CombatScriptParser.Parse(textPath, logger));
            Assert.Equal(expected.Message, actual.Message);
            Assert.Equal(LogLevel.Error, Assert.Single(logger.Entries).Level);
            Assert.Throws<FileNotFoundException>(() => JsonCombatStrategyParser.ParseFile(Path.Combine(directory, "missing.json")));
            Assert.Equal("Combat script file not found",
                Assert.Throws<Exception>(() => CombatScriptParser.ReadAndParse(Path.Combine(directory, "missing.txt"))).Message);
        });
    }

    /// <summary>Default text entry points preserve command/round grammar and validation without logging services.</summary>
    [Fact]
    public void TextDefaults_PreserveGrammarAndValidationWithoutApplicationLogger()
    {
        var script = CombatScriptParser.ParseContext("round(1,3-4),wait(0.2)|wait(0.3)", validate: false);
        Assert.Equal(2, script.CombatCommands.Count);
        Assert.Equal(new[] { 1, 3, 4 }, script.CombatCommands[0].ActivatingRound);
        Assert.Equal("0.2", Assert.Single(script.CombatCommands[0].Args!));
        Assert.Equal(CombatScriptParser.CurrentAvatarName, script.CombatCommands[0].Name);
        Assert.Single(CombatScriptParser.ParseLinePart("wait(1)", "synthetic"));
        Assert.Single(CombatScriptParser.ParseLineCommands("wait(1)", "synthetic"));
        Assert.Equal(new[] { 2, 3 }, CombatScriptParser.ParseRoundCommand(new CombatCommand("synthetic", "round(2-3)")));
        Assert.Equal("Invalid combat script format: separate the character and command with a space",
            Assert.Throws<Exception>(() => CombatScriptParser.ParseContext("wait(1)")).Message);
        Assert.Throws<ArgumentException>(() => CombatScriptParser.ParseRoundCommand(new CombatCommand("synthetic", "round")));
    }

    /// <summary>Every nested text error uses the injected logger, including round and parenthesis branches.</summary>
    [Theory]
    [InlineData("round,wait(1)", "round requires arguments")]
    [InlineData("round(0),wait(1)", "round number must be greater than 0")]
    [InlineData("wait(1", "incomplete parentheses")]
    [InlineData("wait(1,wait(2)", "unmatched parentheses")]
    public void TextInjectedLogger_ForwardsNestedFailures(string script, string expectedMessage)
    {
        var logger = new RecordingLogger();
        var expected = Assert.ThrowsAny<Exception>(() => CombatScriptParser.ParseContext(script, validate: false));
        var actual = Assert.ThrowsAny<Exception>(() => CombatScriptParser.ParseContext(script, logger, validate: false));
        Assert.Equal(expected.GetType(), actual.GetType());
        Assert.Equal(expected.Message, actual.Message);
        Assert.Contains(expectedMessage, actual.Message);
        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Error, entry.Level);
        Assert.Contains(expectedMessage, entry.Message);
    }

    /// <summary>Directory parsing still skips malformed files, retaining both the error and warning.</summary>
    [Fact]
    public void TextDirectory_ReportsNestedErrorAndContinuesWithWarning()
    {
        WithTemporaryDirectory(directory =>
        {
            File.WriteAllText(Path.Combine(directory, "valid.txt"), "// synthetic empty script");
            File.WriteAllText(Path.Combine(directory, "invalid.txt"), "wait(1)");
            var logger = new RecordingLogger();
            Assert.NotNull(CombatScriptParser.ReadAndParse(directory, logger));
            Assert.Equal(new[] { LogLevel.Error, LogLevel.Warning }, logger.Entries.Select(entry => entry.Level));
            Assert.Contains("invalid.txt", logger.Entries[1].Message);
            Assert.NotNull(CombatScriptParser.ReadAndParse(directory));
        });
    }

    /// <summary>An explicit null logger is rejected instead of silently resolving an application logger.</summary>
    [Fact]
    public void ExplicitNullLogger_IsRejectedLocally()
    {
        Assert.Throws<ArgumentNullException>(() => JsonCombatStrategyParser.Parse(ValidJson, null!));
        Assert.Throws<ArgumentNullException>(() => CombatScriptParser.ParseContext("wait(1)", null!, validate: false));
    }

    /// <summary>Both unknown-command forms stay pure and carry the injected logger through construction.</summary>
    [Theory]
    [InlineData("not_a_command")]
    [InlineData("not_a_command(1)")]
    public void UnknownCommand_DefaultAndInjectedPathsPreserveTheFailure(string command)
    {
        const string message = "Unknown method in combat strategy script: not_a_command";
        Assert.Equal(message, Assert.Throws<ArgumentException>(() => Method.GetEnumByCode("not_a_command")).Message);
        Assert.Equal(message, Assert.Throws<ArgumentException>(() => new CombatCommand("synthetic", command)).Message);
        Assert.Equal(message, Assert.Throws<ArgumentException>(() => CombatScriptParser.ParseContext(command, validate: false)).Message);
        var logger = new RecordingLogger();
        Assert.Equal(message, Assert.Throws<ArgumentException>(() => CombatScriptParser.ParseContext(command, logger, validate: false)).Message);
        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Error, entry.Level);
        Assert.Equal(message, entry.Message);
    }

    /// <summary>Each file case owns only its uniquely named temporary directory.</summary>
    private static void WithTemporaryDirectory(Action<string> action)
    {
        var directory = Path.Combine(Path.GetTempPath(), "combat-parser-logging-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try { action(directory); }
        finally { Directory.Delete(directory, recursive: true); }
    }

    /// <summary>In-memory logger; it has no provider, application, native or service dependencies.</summary>
    private sealed class RecordingLogger : ILogger
    {
        /// <summary>Actual level and formatted message observed by the supplied logger.</summary>
        public List<(LogLevel Level, string Message)> Entries { get; } = [];

        /// <summary>Parser tests need no scope ownership.</summary>
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        /// <summary>Retain every diagnostic emitted by the parser.</summary>
        public bool IsEnabled(LogLevel logLevel) => true;

        /// <summary>Capture the actual formatting performed by the logging extension.</summary>
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter) => Entries.Add((logLevel, formatter(state, exception)));
    }
}
