using BetterGenshinImpact.Core.Agent;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Portable actual-Rust goldens plus native buffer ownership and bounds checks.</summary>
public sealed class AgentHamming192Tests
{
    /// <summary>Load saved byte/coefficient results from the unchanged pinned Rust oracle.</summary>
    private static JsonDocument Goldens() => JsonDocument.Parse(File.ReadAllText(
        Path.Combine(AppContext.BaseDirectory, "Fixtures", "AgentHamming192Golden.json")));

    /// <summary>Analytical images are reproducible without importing NumPy's seeded random generator.</summary>
    public static IEnumerable<object[]> Cases()
    {
        using var goldens = Goldens();
        foreach (var sample in goldens.RootElement.GetProperty("cases").EnumerateArray())
            yield return [sample.GetProperty("width").GetInt32(), sample.GetProperty("height").GetInt32(),
                sample.GetProperty("pattern").GetString()!, sample.GetProperty("sha256").GetString()!];
    }

    /// <summary>Check every actual-Rust image hash in all four native channel/stride layouts.</summary>
    [Theory]
    [MemberData(nameof(Cases))]
    public void NativeLayoutsMatchRustBytes(int width, int height, string pattern, string expected)
    {
        var rgb = Image(width, height, pattern);
        var plan = new AgentHamming192Plan(width, height);
        foreach (var (channels, blueFirst, padding) in new[] { (3, false, 0), (3, true, 7), (4, false, 7), (4, true, 7) })
        {
            int stride = (width + padding) * channels;
            // No final-row padding is required by the borrowing contract.
            var source = new byte[(height - 1) * stride + width * channels];
            Array.Fill(source, (byte)211);
            for (int y = 0; y < height; y++)
                for (int x = 0; x < width; x++)
                {
                    for (int c = 0; c < 3; c++)
                        source[y * stride + x * channels + (blueFirst ? 2 - c : c)] = rgb[(y * width + x) * 3 + c];
                    if (channels == 4) source[y * stride + x * channels + 3] = (byte)((x + 17 * y) % 256);
                }
            var inputHash = SHA256.HashData(source);
            var destination = Enumerable.Repeat((byte)173, AgentHamming192Plan.OutputBytes + 17).ToArray();
            plan.ResizeInto(source, stride, channels, blueFirst, destination);
            Assert.Equal(expected, Convert.ToHexString(SHA256.HashData(destination.AsSpan(0, AgentHamming192Plan.OutputBytes))).ToLowerInvariant());
            Assert.Equal(inputHash, SHA256.HashData(source));
            Assert.All(destination.Skip(AgentHamming192Plan.OutputBytes), value => Assert.Equal((byte)173, value));
        }
    }

    /// <summary>Quantized weights must agree before pixel rounding can be considered equivalent.</summary>
    [Fact]
    public void AllSavedRustCoefficientAxesMatch()
    {
        using var goldens = Goldens();
        foreach (var axis in goldens.RootElement.GetProperty("axes").EnumerateArray())
        {
            var expected = axis.GetProperty("coefficients").EnumerateArray().Select(value => value.GetInt32()).ToArray();
            int length = axis.GetProperty("length").GetInt32();
            var plan = new AgentHamming192Plan(length, length);
            Assert.Equal(expected, plan.ExportAxisForValidation(true));
            Assert.Equal(expected, plan.ExportAxisForValidation(false));
        }
    }

    /// <summary>Invalid geometry and row access must fail before touching source/destination memory.</summary>
    [Fact]
    public void InvalidDimensionsStrideAndBuffersAreRejected()
    {
        foreach (int invalid in new[] { 0, -1, 8193, int.MaxValue })
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new AgentHamming192Plan(invalid, 1));
            Assert.Throws<ArgumentOutOfRangeException>(() => new AgentHamming192Plan(1, invalid));
        }
        var plan = new AgentHamming192Plan(2, 2);
        var source = new byte[12];
        var target = new byte[AgentHamming192Plan.OutputBytes];
        Assert.Throws<ArgumentOutOfRangeException>(() => plan.ResizeInto(source, 6, 1, false, target));
        Assert.Throws<ArgumentOutOfRangeException>(() => plan.ResizeInto(source, 5, 3, false, target));
        Assert.Throws<ArgumentOutOfRangeException>(() => plan.ResizeInto(source, int.MaxValue, 3, false, target));
        Assert.Throws<ArgumentException>(() => plan.ResizeInto(source.AsSpan(0, 11), 6, 3, false, target));
        Assert.Throws<ArgumentException>(() => plan.ResizeInto(source, 6, 3, false, target.AsSpan(0, target.Length - 1)));
        Assert.Throws<ArgumentException>(() => plan.ResizeInto(target.AsSpan(0, 12), 6, 3, false, target));
    }

    /// <summary>A cached plan retains neither caller buffer nor mutable frame-specific scratch state.</summary>
    [Fact]
    public void ConcurrentCallersOwnIndependentOutputs()
    {
        var plan = new AgentHamming192Plan(1, 1);
        var outputs = new byte[8][];
        Parallel.For(0, outputs.Length, index =>
        {
            outputs[index] = new byte[AgentHamming192Plan.OutputBytes];
            plan.ResizeInto(new byte[] { (byte)index, 21, 43 }, 3, 3, false, outputs[index]);
        });
        for (int index = 0; index < outputs.Length; index++)
            for (int pixel = 0; pixel < 192 * 192; pixel++)
                Assert.Equal(new byte[] { (byte)index, 21, 43 }, outputs[index].AsSpan(pixel * 3, 3).ToArray());
    }

    /// <summary>Reproduce the exact analytical fixture assignment order, including overlapping corners.</summary>
    private static byte[] Image(int width, int height, string pattern)
    {
        var pixels = new byte[width * height * 3];
        for (int y = 0; y < height; y++)
            for (int x = 0; x < width; x++)
                for (int c = 0; c < 3; c++)
                    pixels[(y * width + x) * 3 + c] = pattern switch
                    {
                        "black" or "edges" => 0,
                        "white" => 255,
                        "ramp" => (byte)((c == 0 ? x : c == 1 ? y : x + y) % 256),
                        "checker" => (byte)(((x + y) % 2) * 255),
                        _ => throw new ArgumentException("Unknown fixture pattern")
                    };
        if (pattern == "edges")
        {
            new byte[] { 255, 0, 0 }.CopyTo(pixels, 0);
            new byte[] { 0, 0, 255 }.CopyTo(pixels, pixels.Length - 3);
            new byte[] { 0, 255, 0 }.CopyTo(pixels, (width - 1) * 3);
            new byte[] { 255, 255, 255 }.CopyTo(pixels, (height - 1) * width * 3);
        }
        return pixels;
    }
}
