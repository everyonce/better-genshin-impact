using BetterGenshinImpact.Core.Script.Dependence;
using System.Text;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

/// <summary>Receipts must remain finalizable when historical evidence reaches a storage boundary.</summary>
public sealed class PilotReceiptBudgetTests
{
    /// <summary>A started receipt can become terminal without admitting another file.</summary>
    [Fact]
    public void ExistingReceiptCanBeFinalizedAtFileBudgetBoundary()
    {
        using var sandbox = new EvidenceSandbox("receipts", "mission.json", "started");
        sandbox.FillToFileBoundary();
        var file = new LimitedFile(sandbox.Root);

        Assert.True(file.WriteTextSync("receipts/mission.json", "completed"));
        Assert.Equal("completed", File.ReadAllText(sandbox.Target));
        Assert.False(file.WriteTextSync("receipts/next.json", "started"));
        Assert.False(File.Exists(Path.Combine(sandbox.Tree, "next.json")));
        Assert.Equal(4095, Directory.EnumerateFiles(sandbox.Tree).Count());
    }

    /// <summary>Appending keeps historical report content and consumes no new file slot.</summary>
    [Fact]
    public void ExistingReportCanAppendAtFileBoundaryWithoutAdmittingAnotherFile()
    {
        using var sandbox = new EvidenceSandbox("reports", "session.jsonl", "started\n");
        sandbox.FillToFileBoundary();
        var file = new LimitedFile(sandbox.Root);

        Assert.True(file.WriteTextSync("reports/session.jsonl", "completed\n", append: true));
        Assert.Equal("started\ncompleted\n", File.ReadAllText(sandbox.Target));
        Assert.False(file.WriteTextSync("reports/next.jsonl", "started\n", append: true));
        Assert.False(File.Exists(Path.Combine(sandbox.Tree, "next.jsonl")));
    }

    /// <summary>Replacement and append account different projected byte usage.</summary>
    [Fact]
    public void OverwriteReplacesOldBytesButAppendStillConsumesByteBudget()
    {
        using var sandbox = new EvidenceSandbox("reports", "session.jsonl", "started\n");
        // Leave exactly the existing destination's bytes below the established metadata reserve.
        using (var filler = File.Create(Path.Combine(sandbox.Tree, "historical.json")))
            filler.SetLength(64L * 1024 * 1024 - 128 * 1024 - Encoding.UTF8.GetByteCount("started\n"));
        var file = new LimitedFile(sandbox.Root);

        Assert.True(file.WriteTextSync("reports/session.jsonl", "stopped\n"));
        Assert.Equal("stopped\n", File.ReadAllText(sandbox.Target));
        Assert.False(file.WriteTextSync("reports/session.jsonl", "more\n", append: true));
        Assert.Equal("stopped\n", File.ReadAllText(sandbox.Target));
        Assert.False(file.WriteTextSync("reports/next.jsonl", "new"));
    }

    /// <summary>Owns one isolated temporary script root; never reads or changes live game evidence.</summary>
    private sealed class EvidenceSandbox : IDisposable
    {
        private readonly string _parent = Path.Combine(Path.GetTempPath(), "BetterGI-receipt-budget-" + Guid.NewGuid().ToString("N"));
        /// <summary>Isolated script root that activates the production evidence budget.</summary>
        public string Root { get; }
        /// <summary>Receipt or report tree covered by the production admission check.</summary>
        public string Tree { get; }
        /// <summary>Existing text destination rewritten or appended by each test.</summary>
        public string Target { get; }

        /// <summary>Creates an owned temporary tree and its initial destination.</summary>
        public EvidenceSandbox(string tree, string file, string initial)
        {
            Root = Path.Combine(_parent, "ActOnePilot");
            Tree = Path.Combine(Root, tree);
            Target = Path.Combine(Tree, file);
            Directory.CreateDirectory(Tree);
            File.WriteAllText(Target, initial);
        }

        /// <summary>Reproduces 4,095 existing receipt files, the observed failure boundary.</summary>
        public void FillToFileBoundary()
        {
            for (var i = 0; i < 4094; i++)
                File.WriteAllText(Path.Combine(Tree, $"historical-{i}.json"), "{}");
        }

        /// <summary>Removes only this fixture's owned temporary tree.</summary>
        public void Dispose()
        {
            // Only remove the uniquely named directory created by this fixture.
            Directory.Delete(_parent, recursive: true);
        }
    }
}
