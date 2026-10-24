using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Newtonsoft.Json.Linq;
using OpenCvSharp;
using System.Buffers;
using System.Reflection;
using System.Runtime.InteropServices;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise profile declaration and real Mat-to-pooled-RGB conversion without a live runtime.</summary>
public sealed class AgentObservationProfileTests
{
    /// <summary>The default remains legacy; only an explicit supported profile changes geometry.</summary>
    [Theory]
    [InlineData(AgentObservationProfile.Legacy, 640, 360, true)]
    [InlineData(AgentObservationProfile.P2PNativeHamming192, 192, 192, false)]
    public void HelloDeclaresFixedProfile(string profile, int width, int height, bool preserveAspect)
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var session = new AgentStreamSession(runtime, profile);
        var helloMethod = typeof(AgentStreamSession).GetMethod("CreateHello", BindingFlags.NonPublic | BindingFlags.Instance)!;
        var hello = JObject.FromObject(helloMethod.Invoke(session, [false])!);
        Assert.Equal(profile, hello["observationProfile"]!.Value<string>());
        Assert.Equal(width, hello["widthLimit"]!.Value<int>());
        Assert.Equal(height, hello["heightLimit"]!.Value<int>());
        Assert.Equal(preserveAspect, hello["observationPreprocessing"]!["preserveAspectRatio"]!.Value<bool>());
        Assert.Equal("rgb24", hello["observationPreprocessing"]!["pixelFormat"]!.Value<string>());
        Assert.Equal("native_capture", hello["observationPreprocessing"]!["source"]!.Value<string>());
        Assert.Equal(AgentObservationProfile.Legacy, AgentObservationProfile.Normalize(null));
        Assert.Throws<ArgumentException>(() => new AgentStreamSession(runtime, "unknown"));
    }

    /// <summary>Real non-contiguous native Mats use their row stride and ignore alpha; leases stay independent.</summary>
    [Theory]
    [InlineData(3)]
    [InlineData(4)]
    public void NativePaddedMatProducesIndependentExactPayload(int channels)
    {
        const int width = 193, height = 197, padding = 7;
        var rgb = new byte[width * height * 3];
        var storage = new byte[(width + padding) * (height + 2) * channels];
        int stride = (width + padding) * channels;
        for (int y = 0; y < height; y++)
            for (int x = 0; x < width; x++)
                for (int c = 0; c < 3; c++)
                {
                    byte value = (byte)((c == 0 ? x : c == 1 ? y : x + y) % 256);
                    rgb[(y * width + x) * 3 + c] = value;
                    storage[(y + 1) * stride + (x + 2) * channels + 2 - c] = value;
                }
        using var owner = new Mat(height + 2, width + padding, channels == 3 ? MatType.CV_8UC3 : MatType.CV_8UC4);
        Marshal.Copy(storage, 0, owner.Data, storage.Length);
        using var source = new Mat(owner, new Rect(2, 1, width, height));
        Assert.False(source.IsContinuous());
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, width, height), 1));
        var session = new AgentStreamSession(runtime, AgentObservationProfile.P2PNativeHamming192);
        var pool = new TrackingPool();
        var first = session.EncodeObservation(source, out int encodedWidth, out int encodedHeight, out int length, pool);
        var second = session.EncodeObservation(source, out _, out _, out _, pool);
        Assert.Equal(192, encodedWidth);
        Assert.Equal(192, encodedHeight);
        Assert.Equal(AgentHamming192Plan.OutputBytes, length);
        var expected = new byte[length];
        new AgentHamming192Plan(width, height).ResizeInto(rgb, width * 3, 3, false, expected);
        Assert.Equal(expected, first.Take(length).ToArray());
        Assert.Equal(expected, second.Take(length).ToArray());
        Assert.NotSame(first, second);
        Array.Fill(first, (byte)9);
        Assert.Equal(expected, second.Take(length).ToArray());
        Assert.All(second.Skip(length), value => Assert.Equal((byte)171, value));
        Assert.Equal(0, pool.Returns); // Only the publication/transport owner may release successful leases.
        pool.Return(first);
        pool.Return(second);
        Assert.Equal(2, pool.Returns);
    }

    /// <summary>A failed conversion returns its rented lease rather than leaking a pooled frame.</summary>
    [Fact]
    public void ConversionFailureReturnsLease()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 2, 2), 1));
        var session = new AgentStreamSession(runtime, AgentObservationProfile.P2PNativeHamming192);
        using var source = new Mat(2, 2, MatType.CV_8UC3, new Scalar(1, 2, 3));
        var pool = new TrackingPool { TooShort = true };
        Assert.Throws<ArgumentOutOfRangeException>(() => session.EncodeObservation(source, out _, out _, out _, pool));
        Assert.Equal(1, pool.Returns);
        using var invalid = new Mat(2, 2, MatType.CV_32FC3);
        Assert.Throws<ArgumentException>(() => session.EncodeObservation(invalid, out _, out _, out _, pool));
        Assert.Equal(1, pool.Returns);
    }

    /// <summary>Legacy output still uses the original area resize and BGR conversion operation order.</summary>
    [Fact]
    public void DefaultProfilePreservesLegacyBytes()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1280, 720), 1));
        var session = new AgentStreamSession(runtime);
        using var source = new Mat(720, 1280, MatType.CV_8UC3, new Scalar(11, 23, 37));
        Cv2.Line(source, new Point(0, 0), new Point(1279, 719), new Scalar(255, 7, 1), 3);
        using var small = new Mat();
        using var rgb = new Mat();
        Cv2.Resize(source, small, new Size(640, 360), interpolation: InterpolationFlags.Area);
        Cv2.CvtColor(small, rgb, ColorConversionCodes.BGR2RGB);
        var expected = new byte[640 * 360 * 3];
        Marshal.Copy(rgb.Data, expected, 0, expected.Length);
        var pool = new TrackingPool();
        var result = session.EncodeObservation(source, out int width, out int height, out int length, pool);
        Assert.Equal(640, width);
        Assert.Equal(360, height);
        Assert.Equal(expected.Length, length);
        Assert.Equal(expected, result.Take(length).ToArray());
        Assert.All(result.Skip(length), value => Assert.Equal((byte)171, value));
        pool.Return(result);
    }

    /// <summary>Observe allocation/return ownership without relying on shared-pool implementation details.</summary>
    private sealed class TrackingPool : ArrayPool<byte>
    {
        /// <summary>Inject a broken lease to exercise conversion cleanup after a successful rent.</summary>
        public bool TooShort { get; init; }
        /// <summary>Number of explicitly released leases.</summary>
        public int Returns { get; private set; }
        /// <summary>Use a canary suffix to detect writing pool capacity instead of payload length.</summary>
        public override byte[] Rent(int minimumLength) => Enumerable.Repeat((byte)171,
            TooShort ? minimumLength - 1 : minimumLength + 17).ToArray();
        /// <summary>Record release without recycling during a test.</summary>
        public override void Return(byte[] array, bool clearArray = false) => Returns++;
    }
}
