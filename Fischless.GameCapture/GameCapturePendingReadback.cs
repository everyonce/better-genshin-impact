using Vanara.PInvoke;

namespace Fischless.GameCapture;

/// <summary>Immutable metadata for one unpublished copy; contains no native resource or mutable capture reference.</summary>
/// <param name="SubmissionId">Positive counter local to SourceInfo.CaptureEpoch.</param>
/// <param name="SourceInfo">Original source identity and first acquisition, never renewed by polling.</param>
/// <param name="SubmittedAtStopwatchTicks">QPC sampled immediately before submitting the staging copy.</param>
/// <param name="Width">Width of the submitted native pixels.</param>
/// <param name="Height">Height of the submitted native pixels.</param>
/// <param name="CaptureRect">RECT belonging to those pixels, not a later window geometry.</param>
public sealed record GameCapturePendingReadback(long SubmissionId, GameCaptureSourceInfo SourceInfo,
    long SubmittedAtStopwatchTicks, int Width, int Height, RECT? CaptureRect);
