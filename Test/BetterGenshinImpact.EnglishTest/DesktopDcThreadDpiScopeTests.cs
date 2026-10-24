using System.ComponentModel;
using Fischless.GameCapture.DesktopDc;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Test the actual scope with managed context functions; no Windows DPI call runs.</summary>
public sealed class DesktopDcThreadDpiScopeTests
{
    /// <summary>Successful entry and restoration use semantic context equality and restore only once.</summary>
    [Fact]
    public void RestoresExactPriorContextOnce()
    {
        var fake = new Context();
        using var scope = fake.Enter();
        Assert.Equal((nint)(-4), fake.Current);
        scope.Dispose();
        scope.Dispose();
        Assert.Equal((nint)17, fake.Current);
        Assert.Equal(new nint[] { -4, 17 }, fake.Calls);
    }

    /// <summary>Opaque aliases are compared with the supplied semantic function, never raw handle equality.</summary>
    [Fact]
    public void SemanticEqualityAcceptsOpaqueAliases()
    {
        var fake = new Context();
        using var scope = new DesktopDcThreadDpiScope(fake.Set, () => fake.Current * 10,
            (actual, expected) => actual == expected * 10, () => fake.Thread);
        scope.Dispose();
        Assert.Equal((nint)17, fake.Current);
    }

    /// <summary>A rejected setter has no valid prior context and never attempts an invented restoration.</summary>
    [Fact]
    public void EntryFailureDoesNotRestoreAnUnknownContext()
    {
        var fake = new Context { RejectEntry = true };
        Assert.Throws<Win32Exception>(() => fake.Enter());
        Assert.Equal(new nint[] { -4 }, fake.Calls);
        Assert.Equal((nint)17, fake.Current);
    }

    /// <summary>A failed post-set verification still owns and restores the context before throwing.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void FailedEntryVerificationRestoresBeforeThrow(bool queryThrows)
    {
        var fake = new Context { RejectEntryEquality = !queryThrows, ThrowEntryQuery = queryThrows };
        Assert.Throws<InvalidOperationException>(() => fake.Enter());
        Assert.Equal(new nint[] { -4, 17 }, fake.Calls);
        Assert.Equal((nint)17, fake.Current);
    }

    /// <summary>Original admission failure survives together with uncertain restoration.</summary>
    [Fact]
    public void EntryVerificationAndRestorationFailuresAreBothRetained()
    {
        var fake = new Context { RejectEntryEquality = true, RejectRestore = true };
        var error = Assert.Throws<AggregateException>(() => fake.Enter());
        Assert.Contains("admission was not verified", error.InnerExceptions[0].Message);
        Assert.True(DesktopDcCleanupException.IsPresent(error));
        Assert.Equal(new nint[] { -4, 17 }, fake.Calls);
    }

    /// <summary>An exceptional setter cannot establish a known unchanged context.</summary>
    [Fact]
    public void ExceptionalEntryIsCleanupUncertainty()
    {
        Assert.Throws<DesktopDcCleanupException>(() => new DesktopDcThreadDpiScope(
            _ => throw new InvalidOperationException("setter"), () => 17, (a, b) => a == b, () => 2));
    }

    /// <summary>Zero, exceptional and mismatched restoration all remain terminal, with no retry on Dispose.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void RestoreFailureIsTypedAndNotRetried(int kind)
    {
        var fake = new Context();
        var scope = fake.Enter();
        fake.RejectRestore = kind == 0;
        fake.ThrowRestore = kind == 1;
        fake.RejectRestoreEquality = kind == 2;
        Assert.Throws<DesktopDcCleanupException>(scope.Dispose);
        scope.Dispose();
        Assert.Equal(new nint[] { -4, 17 }, fake.Calls);
    }

    /// <summary>Misuse on another thread fails before calling the context setter.</summary>
    [Fact]
    public void WrongThreadCannotRestoreAnotherThread()
    {
        var fake = new Context();
        var scope = fake.Enter();
        fake.Thread = 3;
        Assert.Throws<DesktopDcCleanupException>(scope.Dispose);
        fake.Thread = 2;
        scope.Dispose();
        Assert.Equal(new nint[] { -4 }, fake.Calls);
    }

    /// <summary>Managed fake DPI context with separate admission and restoration faults.</summary>
    private sealed class Context
    {
        /// <summary>Current opaque context, original context 17, and native thread identity.</summary>
        internal nint Current = 17;
        /// <summary>Controlled native thread without creating or querying a Windows thread.</summary>
        internal uint Thread = 2;
        /// <summary>Every attempted context change.</summary>
        internal readonly List<nint> Calls = new();
        /// <summary>Individual native/query failure seams.</summary>
        internal bool RejectEntry, RejectEntryEquality, ThrowEntryQuery, RejectRestore, ThrowRestore, RejectRestoreEquality;
        /// <summary>Use the production scope with only fake delegates.</summary>
        internal DesktopDcThreadDpiScope Enter() => new(Set, Get, Equal, () => Thread);
        /// <summary>Return the actual previous context on successful changes.</summary>
        internal nint Set(nint value)
        {
            Calls.Add(value);
            if (value == -4 && RejectEntry || value == 17 && RejectRestore) return 0;
            if (value == 17 && ThrowRestore) throw new InvalidOperationException("restore setter");
            var previous = Current;
            Current = value;
            return previous;
        }
        /// <summary>Fail only the initial verification when requested.</summary>
        private nint Get()
        {
            if (Current == -4 && ThrowEntryQuery) throw new InvalidOperationException("entry query");
            return Current;
        }
        /// <summary>Separate semantic equality faults from setter return values.</summary>
        private bool Equal(nint actual, nint expected) => actual == expected
            && !(expected == -4 && RejectEntryEquality) && !(expected == 17 && RejectRestoreEquality);
    }

    /// <summary>Explicit fake-only scope used by existing capture fixtures; never calls the native factory.</summary>
    internal sealed class CallbackScope(Action close) : IDisposable
    {
        /// <summary>Dispose once even when the callback fails.</summary>
        private bool _closed;
        /// <summary>Invoke the controlled restoration action at the real transaction boundary.</summary>
        public void Dispose()
        {
            if (_closed) return;
            _closed = true;
            close();
        }
    }
}
