using System;
using System.Diagnostics;
using System.Threading;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Model.Area;
using Fischless.GameCapture;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>One positively recognized map close inside the existing preparation window; never a generic UI recovery.</summary>
internal sealed class NavigationResetMapRecovery
{
    /// <summary>Consumed before native dispatch, including an ambiguous or partially failed press.</summary>
    internal bool Attempted { get; private set; }
    /// <summary>Exact source authorizing the sole Escape attempt; not a new capture or game acknowledgment.</summary>
    internal GameCaptureSourceInfo? TriggerSource { get; private set; }
    /// <summary>Final pre-dispatch host clock; release still runs if dispatch fails or cancellation arrives.</summary>
    internal long? RequestedAtTicks { get; private set; }
    /// <summary>Only a successful explicit key-up establishes the post-input response cutoff.</summary>
    internal long? ReleasedAtTicks { get; private set; }
    /// <summary>Bounded original failure detail, retained independently of release failure.</summary>
    internal string? Error { get; private set; }
    /// <summary>Explicit cleanup failure is not hidden by a prior native dispatch failure.</summary>
    internal string? ReleaseError { get; private set; }

    /// <summary>Map markers and a close button are required together; missing HUD alone authorizes nothing.</summary>
    internal static bool RecognizeKnownMap(Mat source) => RecognizeKnownMap(source,
        Bv.IsInBigMapUi, region => Matches(region, "QuickTeleport", "MapCloseButton"), Bv.DetectChatUi,
        HasBlockingModal, ChatUiHotkeyGuard.UpdateVisualState);

    /// <summary>Borrow the same source pixels; supported unscaled geometry and every negative guard stay explicit.</summary>
    internal static bool RecognizeKnownMap(Mat source, Func<ImageRegion, bool> isMap,
        Func<ImageRegion, bool> hasClose, Func<ImageRegion, ChatUiDetectionResult> chat,
        Func<ImageRegion, bool> hasModal, Action<ChatUiDetectionResult> updateChat)
    {
        if (source.Empty() || source.Channels() is not (3 or 4) || source.Width > 1920 || source.Height > 1080)
            throw new InvalidOperationException("unsupported_map_recovery_geometry");
        using var region = new ImageRegion(new Mat(source, new Rect(0, 0, source.Width, source.Height)), 0, 0);
        if (!isMap(region) || !hasClose(region)) return false;
        var evidence = chat(region);
        updateChat(evidence);
        if (evidence.State != ChatUiState.Closed) throw new InvalidOperationException($"chat_not_closed: {evidence.State}");
        // AgentWorldRecognizer returns HudMissing before checking modals, so inspect modal assets independently here.
        if (hasModal(region)) throw new InvalidOperationException("map_recovery_blocking_ui");
        return true;
    }

    /// <summary>HUD-absent settling frames still reject real modal evidence instead of retrying a hidden hard blocker.</summary>
    internal static void ValidateSettlingWorld(Mat source, AgentWorldEvidence world) =>
        ValidateSettlingWorld(source, world, HasBlockingModal);

    /// <summary>Test the missing-HUD branch without an application asset loader or a second capture.</summary>
    internal static void ValidateSettlingWorld(Mat source, AgentWorldEvidence world, Func<ImageRegion, bool> hasModal)
    {
        if (world != AgentWorldEvidence.HudMissing) return;
        using var region = new ImageRegion(new Mat(source, new Rect(0, 0, source.Width, source.Height)), 0, 0);
        if (hasModal(region)) throw new InvalidOperationException("map_recovery_blocking_ui");
    }

    /// <summary>Reuse the native modal appearance and Confirm assets independently of the world-HUD early return.</summary>
    private static bool HasBlockingModal(ImageRegion region) => AgentWorldRecognizer.MatchesModalAppearance(region,
        RecognitionAssets.Get(@"Common\Element", "PromptDialogLeftBottomStar", region)) || Matches(region, "AutoFight", "Confirm");

    /// <summary>Use the existing asset matcher without retaining an owned region or changing template thresholds.</summary>
    private static bool Matches(ImageRegion region, string task, string name)
    {
        using var match = region.Find(RecognitionAssets.Get(task, name, region));
        return match.IsExist();
    }

    /// <summary>Validate at the final boundary, then attempt one press and always explicitly release its key.</summary>
    internal void CloseOnce(GameCaptureSourceInfo source, long windowStartedAtTicks, Action validateTarget,
        Action pressEscape, Action releaseEscape, CancellationToken ct, Func<long>? timestamp = null)
    {
        timestamp ??= Stopwatch.GetTimestamp;
        if (Attempted) throw new InvalidOperationException("map_close_already_attempted");
        var first = timestamp();
        Check(first);
        validateTarget();
        if (Attempted) throw new InvalidOperationException("map_close_already_attempted");
        var now = timestamp();
        if (now < first) throw new InvalidOperationException("preparation_clock_regressed");
        Check(now);
        // A cancellation or failed target/source/deadline check before here sends no key and consumes no attempt.
        Attempted = true;
        TriggerSource = source;
        RequestedAtTicks = now;
        Exception? dispatchError = null;
        try
        {
            try { ct.ThrowIfCancellationRequested(); pressEscape(); }
            catch (Exception error) { dispatchError = error; throw; }
            finally
            {
                try { releaseEscape(); ReleasedAtTicks = timestamp(); }
                catch (Exception error)
                {
                    ReleaseError = Describe(error);
                    if (dispatchError is null) throw;
                }
            }
            // A completed late call never becomes permission to teleport; cleanup was already attempted.
            var completed = timestamp();
            if (completed < now || ReleasedAtTicks is not { } released || released < now || completed < released) throw new InvalidOperationException("preparation_clock_regressed");
            Check(completed);
        }
        catch (Exception error) { Error = Describe(error); throw; }

        void Check(long clock)
        {
            ct.ThrowIfCancellationRequested();
            if (clock < windowStartedAtTicks) throw new InvalidOperationException("preparation_clock_regressed");
            if (Stopwatch.GetElapsedTime(windowStartedAtTicks, clock) >= NavigationResetPreparationReadiness.Timeout)
                throw new InvalidOperationException("map_recovery_preparation_deadline");
            if (NativeNavigationResetOperations.SourceRejectionReason(source, clock, source.CaptureEpoch) is { } reason)
                throw new InvalidOperationException("map_recovery_source_rejected: " + reason);
        }
    }

    /// <summary>Neither a cached copy nor a single newer clock can verify the effect of Escape.</summary>
    internal bool SourcePassedRelease(GameCaptureSourceInfo source) => Attempted && ReleasedAtTicks is { } released
        && TriggerSource is { } trigger && source.CaptureEpoch == trigger.CaptureEpoch
        && source.SourceTimestamp100ns > trigger.SourceTimestamp100ns
        && source.AcquiredAtStopwatchTicks > trigger.AcquiredAtStopwatchTicks
        && NativeNavigationResetOperations.SourceIsAfterBarrier(source, released);

    /// <summary>Keep this at-most-one diagnostic record bounded even for unusual native exception messages.</summary>
    private static string Describe(Exception error)
    {
        var value = error.GetBaseException().Message;
        return value.Length <= 512 ? value : value[..512];
    }
}
