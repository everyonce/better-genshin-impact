using System;
using Serilog;

namespace BetterGenshinImpact.Service;

internal static class RuntimeLogRetention
{
    internal const long FileBytes = 8L * 1024 * 1024;
    internal const int FileCount = 8;
    internal static LoggerConfiguration Configure(LoggerConfiguration configuration, string path,
        long fileBytes = FileBytes, int fileCount = FileCount) => configuration.WriteTo.File(path,
        outputTemplate: "[{Timestamp:HH:mm:ss.fff}] [{Level:u3}] [{BgiInstance}] {SourceContext}{NewLine}{Message}{NewLine}{Exception}{NewLine}",
        rollingInterval: RollingInterval.Day, shared: true, fileSizeLimitBytes: fileBytes,
        rollOnFileSizeLimit: true, retainedFileCountLimit: fileCount, retainedFileTimeLimit: TimeSpan.FromDays(7));
}
