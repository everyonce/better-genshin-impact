using System;
using System.Linq;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Bounded representation fixtures, not simulated route acceptance or universal string-size proofs.</summary>
public sealed class NavigationBaselineContinuationWireBoundsTests(ITestOutputHelper output)
{
    /// <summary>Keep both transport envelopes and deepest retained motion/source fields observable.</summary>
    [Theory]
    [InlineData("blocking", false, false)]
    [InlineData("blocking", false, true)]
    [InlineData("blocking", true, false)]
    [InlineData("blocking", true, true)]
    [InlineData("poll_single_v1", false, false)]
    [InlineData("poll_single_v1", false, true)]
    [InlineData("poll_single_v1", true, false)]
    [InlineData("poll_single_v1", true, true)]
    public void ReverseContinuationFitsCompactAndDedicatedResultEnvelopes(string mode, bool failed, bool shadow)
    {
        var samples = Enumerable.Range(1, 3).Select(Sample).ToArray();
        var predecessor = Evidence(mode, 'p', shadow);
        var link = new NavigationBaselineContinuationLink
        {
            PredecessorRunId = new string('a', 32), PredecessorEvidence = predecessor,
            PredecessorFinalSource = samples[^1].Source, PredecessorCleanupReturnedAtTicks = 123456789012345,
            RuntimeIdentity = Guid.Parse("01234567-89ab-cdef-0123-456789abcdef"),
            ChildProcessId = 12345, ChildNonce = new string('b', 32), WindowsSessionId = 3,
            GameProcessId = 23456, GameStartedAtUtcTicks = 638982123456789012,
            CaptureType = "Fischless.GameCapture.Graphics.GraphicsCaptureV2", ReadbackMode = mode
        };
        var error = failed ? new string('e', 512) : null;
        var result = new NavigationBaselineRunResult
        {
            ProfileId = NavigationBaselineRouteProfile.ReverseId, Continuation = link,
            TimingContract = NavigationBaselineTiming.V4, CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer,
            Verified = !failed, Phase = "verify", Error = error, InitialSample = Sample(0),
            Samples = failed ? [] : samples, VerificationSamples = samples, ObservationCount = 1024,
            Evidence = Evidence(mode, 'r', shadow), ElapsedMs = 29999.123456789, InputReleaseError = error,
            Legs = [new(1, 3, 2, 12345678.123456, 12355678.123456, 0, 512, "completed"),
                new(2, 2, 1, 12355678.123456, 12365678.123456, 512, 1024, failed ? "failed" : "completed")],
            Waypoint = new()
            {
                Release = new("w_up", 12345678.123456, 12345679.123456), DeadlineAtMs = 12347679.123456,
                EndedAtMs = 12347678.123456, ObservationStart = 500, ObservationEnd = 532,
                PollStart = 2000, PollEnd = 2032, ReadCount = 32, CaptureCount = 32, SourceAgeDiscards = 28,
                Samples = samples, Anchor = Sample(4), Outcome = "completed"
            }
        };
        var status = new NavigationBaselineStatus
        {
            ShadowCapture = shadow ? NavigationBaselineShadowMode.Rgb192 : null,
            RunId = new string('c', 32), State = failed ? "failed" : "completed", Phase = "verify", Error = error,
            ProfileId = NavigationBaselineRouteProfile.ReverseId, Continuation = link,
            TimingContract = NavigationBaselineTiming.V4, CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer,
            GameProcessId = 23456, WindowsSessionId = 3, ReadbackMode = mode,
            ObservationCount = 1024, EvidenceComplete = true
        };
        var compact = ExternalControlProtocol.SerializeResponse(new ExternalControlResponse
        { Status = new() { NavigationBaseline = status } });
        var full = ExternalControlProtocol.SerializeResponse(new ExternalControlResponse
        { Status = new() { NavigationBaseline = status with { Result = result } } });
        output.WriteLine($"Reverse wire representation ({mode}, failed={failed}, shadow={shadow}): compact={compact.Length}; result={full.Length} bytes.");
        Assert.InRange(compact.Length, 1, 8191);
        Assert.InRange(full.Length, 1, 32767);
        using var compactJson = JsonDocument.Parse(compact);
        using var fullJson = JsonDocument.Parse(full);
        var compactOperation = compactJson.RootElement.GetProperty("status").GetProperty("navigationBaseline");
        var fullOperation = fullJson.RootElement.GetProperty("status").GetProperty("navigationBaseline");
        var measured = fullOperation.GetProperty("result");
        Assert.Equal(2, compactOperation.GetProperty("endpointContinuationVersion").GetInt32());
        var reference = compactOperation.GetProperty("continuation");
        Assert.Equal(3, reference.EnumerateObject().Count());
        Assert.Equal(2, reference.GetProperty("version").GetInt32());
        Assert.Equal(link.PredecessorRunId, reference.GetProperty("predecessorRunId").GetString());
        Assert.Equal(link.PredecessorProfileId, reference.GetProperty("predecessorProfileId").GetString());
        Assert.Equal(reference.GetRawText(), fullOperation.GetProperty("continuation").GetRawText());
        Assert.Equal(1, measured.GetProperty("continuation").GetProperty("version").GetInt32());
        Assert.Equal(1024, measured.GetProperty("continuation").GetProperty("predecessorEvidence")
            .GetProperty("journalPath").GetString()!.Length);
        Assert.Equal(predecessor.JournalSha256, measured.GetProperty("continuation").GetProperty("predecessorEvidence")
            .GetProperty("journalSha256").GetString());
        Assert.False(measured.GetProperty("continuation").GetProperty("physicalInputAcknowledged").GetBoolean());
        if (shadow)
        {
            Assert.Equal(NavigationBaselineShadowMode.Rgb192, fullOperation.GetProperty("shadowCapture").GetString());
            Assert.True(measured.GetProperty("evidence").GetProperty("shadowCapture").GetProperty("workerRetired").GetBoolean());
            Assert.Equal(1024, measured.GetProperty("continuation").GetProperty("predecessorEvidence")
                .GetProperty("shadowCapture").GetProperty("framesWritten").GetInt32());
        }
        Assert.Equal(samples[^1].SourceEpoch, measured.GetProperty("continuation").GetProperty("predecessorFinalSource")
            .GetProperty("CaptureEpoch").GetGuid());
        Assert.Equal("normal", measured.GetProperty("waypoint").GetProperty("samples")[0]
            .GetProperty("motion").GetProperty("status").GetString());
        Assert.Equal(3, measured.GetProperty("legs")[0].GetProperty("startPointId").GetInt32());
        Assert.Equal(1, measured.GetProperty("legs")[1].GetProperty("endPointId").GetInt32());
    }

    /// <summary>Long bounded artifact references remain complete in the dedicated result only.</summary>
    private static NavigationBaselineEvidence Evidence(string mode, char prefix, bool shadow) =>
        new(true, prefix + new string('j', 1023), new string('a', 64), prefix + new string('i', 1023),
            new string('b', 64), prefix + new string('f', 1023), new string('c', 64)) { ReadbackMode = mode,
            ShadowCapture = shadow ? new(NavigationBaselineShadowMode.Rgb192, true, true, null,
                4096, 1024, 1024, 3072, 0, 0, 0, prefix + new string('s', 1023), new('d', 64), new('a', 64)) : null };

    /// <summary>All additive same-frame fields are retained, with stable high-digit finite values.</summary>
    private static NavigationBaselineSample Sample(int index) => new(-886.1494140625, 2263.282958984375,
        359.123456789, DateTimeOffset.Parse("2026-10-24T09:00:00.1234567+00:00"),
        Guid.Parse("fedcba98-7654-3210-fedc-ba9876543210"), 123456789012345 + index, 123456789012345 + index,
        .999999123456, .987654321, "City_102", new("normal", "native_key_tip_templates_v1", false, false, 9.123456789),
        149.123456789, 359.123456789, 1.23456789, 12.3456789, .123456789,
        new(12345678.123456, 12345679.123456, 12345680.123456, 12345681.123456)) { LegIndex = index < 4 ? 1 : 2 };
}
