using BetterGenshinImpact.Core.Script.Dependence;
using Xunit;
using System.IO;

namespace BetterGenshinImpact.EnglishTest;

public sealed class CaptureStorageTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "BetterGI-retention-" + Guid.NewGuid().ToString("N"), "ActOnePilot");
    public CaptureStorageTests() => Directory.CreateDirectory(Path.Combine(_root, "observations", "session"));
    private string Frame(int number) => Path.Combine(_root, "observations", "session", $"frame-{number:0000}.png");
    private static long Plenty() => 8L * 1024 * 1024 * 1024;

    [Fact]
    public void LowDiskRefusesWriteAndPreservesExistingEvidence()
    {
        File.WriteAllText(Frame(1), "original");
        Assert.Throws<IOException>(() => new CaptureImageWriter().Write(_root, Frame(2), [1, 2, 3],
            () => CaptureStorageBudget.MinimumFreeBytes));
        Assert.Equal("original", File.ReadAllText(Frame(1)));
        Assert.False(File.Exists(Frame(2)));
    }

    [Fact]
    public void UnchangedImagesRetainEveryFramePathAndTransitionsRemainDistinct()
    {
        var writer = new CaptureImageWriter();
        writer.Write(_root, Frame(1), [1, 2, 3], Plenty);
        writer.Write(_root, Frame(2), [1, 2, 3], Plenty);
        writer.Write(_root, Frame(3), [4, 5, 6], Plenty);
        Assert.Equal(File.ReadAllBytes(Frame(1)), File.ReadAllBytes(Frame(2)));
        Assert.Equal(new byte[] { 4, 5, 6 }, File.ReadAllBytes(Frame(3)));
        Assert.Throws<IOException>(() => writer.Write(_root, Frame(1), [9], Plenty));
        Assert.Equal(new byte[] { 1, 2, 3 }, File.ReadAllBytes(Frame(1)));
    }

    [Fact]
    public void QuotaSurvivesWriterRestartAndDoesNotDeleteAnyFile()
    {
        for (var i = 1; i <= CaptureStorageBudget.MaxFiles; i++) File.WriteAllText(Frame(i), "x");
        Assert.Throws<IOException>(() => new CaptureImageWriter().Write(_root, Frame(5000), [1], Plenty));
        Assert.Equal(CaptureStorageBudget.MaxFiles, Directory.GetFiles(Path.GetDirectoryName(Frame(1))!).Length);
    }

    [Fact]
    public void ByteQuotaAndOversizedFrameAreRejectedWithoutWriting()
    {
        Assert.Throws<IOException>(() => CaptureStorageBudget.CheckUsage(CaptureStorageBudget.MaxBytes, 1, 1, Plenty()));
        Assert.Throws<IOException>(() => CaptureStorageBudget.Check(_root, CaptureStorageBudget.FrameReserveBytes + 1, Plenty));
        Assert.False(File.Exists(Frame(2)));
    }

    [Theory]
    [InlineData("../outside.png")]
    [InlineData("User/config.json")]
    [InlineData("observations/../frame-1.png")]
    public void UnsafeDestinationsAreRejected(string relative)
    {
        Assert.Throws<IOException>(() => new CaptureImageWriter().Write(_root, Path.Combine(_root, relative), [1], Plenty));
        Assert.Empty(Directory.GetFiles(_root, "*.png", SearchOption.AllDirectories));
    }

    [Fact]
    public void RotationPreservesPinsLockedChangedAndHistoricalFiles()
    {
        var retention = new CaptureRetention(_root);
        for (var i = 1; i <= 300; i++)
        {
            var bytes = System.Text.Encoding.UTF8.GetBytes("image-" + i);
            File.WriteAllBytes(Frame(i), bytes);
            retention.Register(Frame(i), bytes.Length, Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)));
            var metadata = Path.ChangeExtension(Frame(i), ".json");
            File.WriteAllText(metadata, "{}");
            retention.RegisterMetadata(metadata, Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes("{}"))));
        }
        retention.Pin("session", 1);
        File.WriteAllText(Frame(4), "changed externally");
        File.WriteAllText(Frame(9999), "historical unregistered evidence");
        using (var locked = new FileStream(Frame(3), FileMode.Open, FileAccess.Read, FileShare.None))
        {
            retention.Sweep(DateTime.UtcNow);
            Assert.True(File.Exists(Frame(1)));
            Assert.True(File.Exists(Frame(3)));
            Assert.True(File.Exists(Frame(4)));
            Assert.True(File.Exists(Frame(9999)));
            Assert.False(File.Exists(Frame(2)));
            Assert.False(File.Exists(Path.ChangeExtension(Frame(2), ".json")));
            Assert.True(File.Exists(Frame(300)));
        }
        retention.Sweep(DateTime.UtcNow.AddDays(2));
        Assert.False(File.Exists(Frame(3)));
        Assert.True(File.Exists(Frame(299)));
        Assert.True(File.Exists(Frame(300)));
        Assert.True(File.Exists(Frame(1)));
        Assert.True(File.Exists(Frame(4)));
        Assert.True(File.Exists(Frame(9999)));
    }

    [Theory]
    [InlineData(1, 32)]
    [InlineData(16 * 1024 * 1024, 4)]
    public void ContinuousEvidencePinsStayBoundedAndOldEvidenceExpires(long recordedBytes, int expectedPins)
    {
        var retention = new CaptureRetention(_root);
        for (var i = 1; i <= 400; i++)
        {
            var bytes = System.Text.Encoding.UTF8.GetBytes("evidence-" + i);
            File.WriteAllBytes(Frame(i), bytes);
            retention.Register(Frame(i), recordedBytes, Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)));
            retention.Pin("session", i);
        }
        var pinned = File.ReadAllLines(Path.Combine(_root, "capture-retention.tsv"))
            .Select(line => line.Split('\t')).Where(fields => fields[4] == "1").ToArray();
        Assert.Equal(expectedPins, pinned.Length);
        Assert.True(pinned.Sum(fields => long.Parse(fields[1])) <= CaptureRetention.PinnedBytes);
        new CaptureRetention(_root).Sweep(DateTime.UtcNow.AddDays(2));
        Assert.False(File.Exists(Frame(1)));
        Assert.True(File.Exists(Frame(400)));
        Assert.Equal(expectedPins + 2, Directory.GetFiles(Path.GetDirectoryName(Frame(1))!, "*.png").Length);
    }

    [Fact]
    public void CaptureAdmissionNeverExceedsTheFrameCapBetweenSweeps()
    {
        var writer = new CaptureImageWriter();
        var retention = new CaptureRetention(_root);
        for (var frame = 1; frame <= 320; frame++)
        {
            writer.Write(_root, Frame(frame), BitConverter.GetBytes(frame), Plenty);
            if (frame <= CaptureRetention.PinnedFrames) retention.Pin("session", frame);
            Assert.True(Directory.GetFiles(Path.GetDirectoryName(Frame(1))!, "*.png").Length <= CaptureRetention.LatestFrames + CaptureRetention.PinnedFrames);
        }
        Assert.True(File.Exists(Frame(1)));
        Assert.False(File.Exists(Frame(33)));
        Assert.True(File.Exists(Frame(320)));
    }

    [Fact]
    public void UnregisteredEvidenceCannotExpandTheImageByteCap()
    {
        using (var image = File.Create(Frame(9999))) image.SetLength(CaptureRetention.RecentBytes + CaptureRetention.PinnedBytes);
        Assert.Throws<IOException>(() => new CaptureImageWriter().Write(_root, Frame(1), [1], Plenty));
        Assert.True(File.Exists(Frame(9999)));
        Assert.False(File.Exists(Frame(1)));
    }

    [Fact]
    public async Task LedgerReplacementToleratesTransientDeleteSharingLock()
    {
        var destination = Path.Combine(_root, "ledger");
        var temporary = destination + ".tmp";
        File.WriteAllText(destination, "old");
        File.WriteAllText(temporary, "new");
        var reader = new FileStream(destination, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var release = Task.Run(() => { Thread.Sleep(100); reader.Dispose(); });
        try { CaptureRetention.ReplaceLedger(temporary, destination); }
        finally { await release; }
        Assert.Equal("new", File.ReadAllText(destination));
        Assert.False(File.Exists(temporary));
    }

    [Fact]
    public void LedgerReplacementDoesNotOverridePersistentDenial()
    {
        var destination = Path.Combine(_root, "ledger");
        var temporary = destination + ".tmp";
        File.WriteAllText(destination, "old");
        File.WriteAllText(temporary, "new");
        using var reader = new FileStream(destination, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var error = Record.Exception(() => CaptureRetention.ReplaceLedger(temporary, destination));
        Assert.True(error is IOException or UnauthorizedAccessException);
        Assert.Equal("old", File.ReadAllText(destination));
        Assert.True(File.Exists(temporary));
    }

    public void Dispose() => Directory.Delete(Path.GetDirectoryName(_root)!, true);
}
