using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Pulonia.Models;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>Lossless removal of legacy task presentation fields, under the existing store and writer gates.</summary>
public sealed partial class PuloniaTaskStore
{
    /// <summary>
    /// Reread the owned plan under both gates. Preserve original primary/backup bytes, commit presentation
    /// first, then replace only the projected plan. A failed second write is safe to retry without reseeding.
    /// </summary>
    private async Task<PuloniaTaskPlan?> MigratePlanPresentationAsync(string path, string id, CancellationToken ct)
    {
        if (!File.Exists(path)) return null;
        var original = await File.ReadAllBytesAsync(path, ct).ConfigureAwait(false);
        using var input = new MemoryStream(original, writable: false);
        using var reader = new StreamReader(input, Utf8WithoutBom, detectEncodingFromByteOrderMarks: true);
        var json = await reader.ReadToEndAsync(ct).ConfigureAwait(false);
        var plan = PuloniaTaskJson.ReadPlan(json, out var collapsed, out var projected);
        if (plan.Id != id)
            throw new PuloniaTaskValidationException(path, "File name and plan ID differ.");
        if (collapsed is null) return plan;

        // An existing empty list is initialized state and wins over every legacy false value.
        var state = await ReadPlanViewStateFileAsync(ct).ConfigureAwait(false);
        var initialize = !state.CollapsedTaskIds.ContainsKey(id);
        if (initialize) state.CollapsedTaskIds.Add(id, collapsed);
        ValidatePlanViewState(state);
        var stateJson = PuloniaTaskJson.Write(state);
        var backup = File.Exists(path + ".bak")
            ? await File.ReadAllBytesAsync(path + ".bak", ct).ConfigureAwait(false) : null;

        // Both immutable originals must be durable before either live document changes.
        await PreservePlanPresentationOriginalAsync(path, original, ct).ConfigureAwait(false);
        if (backup is not null)
            await PreservePlanPresentationOriginalAsync(path + ".bak", backup, ct).ConfigureAwait(false);
        if (initialize)
            await WriteAtomicallyAsync(Path.Combine(RootDirectory, PlanViewStateFileName), stateJson, ct).ConfigureAwait(false);
        // Do not replace a pre-existing backup, increment Revision, or signal an executable plan change.
        await WriteAtomicallyAsync(path, projected!, ct, preserveExistingBackup: true).ConfigureAwait(false);
        return plan;
    }

    /// <summary>Keep byte-exact immutable originals; a partial or different prior archive stops migration.</summary>
    private static async Task PreservePlanPresentationOriginalAsync(string path, byte[] bytes, CancellationToken ct)
    {
        var archive = path + ".presentation.original";
        if (File.Exists(archive))
        {
            // A prior attempt may have written every byte but failed before its durable flush.
            // Verify and flush the same retained handle before publishing either live document.
            await using var retained = new FileStream(archive, FileMode.Open, FileAccess.ReadWrite, FileShare.Read);
            if (retained.Length != bytes.Length)
                throw new PuloniaTaskValidationException(path, "Presentation original differs; no live document was changed.");
            var preserved = new byte[bytes.Length];
            await retained.ReadExactlyAsync(preserved, ct).ConfigureAwait(false);
            if (!preserved.SequenceEqual(bytes))
                throw new PuloniaTaskValidationException(path, "Presentation original differs; no live document was changed.");
            retained.Flush(flushToDisk: true);
            return;
        }
        // CreateNew never overwrites evidence. A failed partial archive stays visible and blocks a retry.
        await using var stream = new FileStream(archive, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
        await stream.WriteAsync(bytes, ct).ConfigureAwait(false);
        stream.Flush(flushToDisk: true);
    }
}
