namespace Fischless.GameCapture.DesktopDc;

/// <summary>Marks cleanup uncertainty that permanently prevents this capture object from publishing another frame.</summary>
internal sealed class DesktopDcCleanupException : InvalidOperationException
{
    /// <summary>Preserve the cleanup stage and any underlying failure without replaying the operation.</summary>
    internal DesktopDcCleanupException(string message, Exception? innerException = null)
        : base(message, innerException)
    {
    }

    /// <summary>Find a cleanup failure even when a primary capture failure was retained alongside it.</summary>
    internal static bool IsPresent(Exception error) => error is DesktopDcCleanupException
        || error is AggregateException aggregate && aggregate.InnerExceptions.Any(IsPresent)
        || error.InnerException is not null && IsPresent(error.InnerException);

    /// <summary>Keep an existing failure first while recording a later independent cleanup failure.</summary>
    internal static Exception Combine(Exception? primary, Exception additional) =>
        primary is null ? additional : new AggregateException(primary, additional);
}
