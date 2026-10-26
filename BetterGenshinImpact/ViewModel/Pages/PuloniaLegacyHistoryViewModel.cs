using System;
using System.Collections.ObjectModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.ViewModel.Pages.Pulonia;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.ViewModel.Pages;

/// <summary>Read-only legacy evidence browser, independent of task-service initialization and execution types.</summary>
public partial class PuloniaLegacyHistoryViewModel : ViewModel
{
    /// <summary>Shared selected-detail character ceiling; JSON writing stops at this budget rather than serializing the tail.</summary>
    public const int PreviewCharacterLimit = 16 * 1024;
    /// <summary>Aggregate UTF-8 ceiling for selected overview/fact labels and values.</summary>
    public const int PreviewUtf8Limit = 64 * 1024;
    /// <summary>Maximum list-title length, including a visible truncation suffix.</summary>
    public const int ListLabelLimit = 64;
    /// <summary>Only the two existing legacy-read methods are used; no state or writer API is invoked.</summary>
    private readonly PuloniaTaskStore _store;
    /// <summary>Serialize refresh and exact-ID reads without a timer or task-service subscription.</summary>
    private readonly SemaphoreSlim _readGate = new(1, 1);
    /// <summary>Selected immutable evidence row; never a current executable run.</summary>
    [ObservableProperty]
    private LegacyHistoryItem? _selectedRecord;
    /// <summary>Human-readable operation status, translated by the view.</summary>
    [ObservableProperty]
    private string _statusMessage = "旧版记录尚未读取。";
    /// <summary>Distinguish a bounded listing from a single exact-ID result.</summary>
    [ObservableProperty]
    private string _modeMessage = "有界旧版记录列表";
    /// <summary>Whether an owned read is in progress.</summary>
    [ObservableProperty]
    private bool _isRefreshing;
    /// <summary>Whether any selected text was omitted; original source bytes remain intact.</summary>
    [ObservableProperty]
    private bool _isPreviewTruncated;
    /// <summary>Explicit original plan identifier; never interpreted as an arbitrary path.</summary>
    [ObservableProperty]
    private string _exactPlanId = string.Empty;
    /// <summary>Explicit GUID-N history filename alias.</summary>
    [ObservableProperty]
    private string _exactRunId = string.Empty;
    /// <summary>Bounded legacy rows, or one exact-ID row replacing them.</summary>
    public ObservableCollection<LegacyHistoryItem> Records { get; } = [];
    /// <summary>Selected source identity and non-resumption reasons.</summary>
    public ObservableCollection<PuloniaTaskHistoryField> OverviewFields { get; } = [];
    /// <summary>Bounded display-only facts and opaque snapshot text.</summary>
    public ObservableCollection<PuloniaTaskHistoryField> FactFields { get; } = [];
    /// <summary>Bounded per-file/limit diagnostics; no source is deleted or repaired.</summary>
    public ObservableCollection<PuloniaTaskHistoryField> Failures { get; } = [];
    /// <summary>Selected detail visibility.</summary>
    public bool HasSelectedRecord => SelectedRecord is not null;
    /// <summary>Number displayed, never a claim of a complete historical census.</summary>
    public int RecordCount => Records.Count;
    /// <summary>Number of visible read/limit diagnostics.</summary>
    public int FailureCount => Failures.Count;
    /// <summary>Bounded location label only; no file-opening or browsing command is supplied.</summary>
    public string StorageDirectory { get; }
    /// <summary>Actual selected preview size, excluding fixed view labels.</summary>
    public int PreviewUtf8ByteCount => OverviewFields.Concat(FactFields)
        .Sum(entry => Encoding.UTF8.GetByteCount(entry.Label) + Encoding.UTF8.GetByteCount(entry.Value));

    /// <summary>Inject storage only. Construction performs no I/O, scheduling, game or account operation.</summary>
    public PuloniaLegacyHistoryViewModel(PuloniaTaskStore store)
    {
        _store = store;
        StorageDirectory = ClipText(Path.Combine(store.RootDirectory, "history"), 256).Text;
    }

    /// <summary>Read the existing bounded list, retaining selection by original plan/run identity when still present.</summary>
    [RelayCommand]
    public async Task RefreshAsync(CancellationToken ct = default)
    {
        await _readGate.WaitAsync(ct);
        var planId = SelectedRecord?.Record.PlanId;
        var runId = SelectedRecord?.Record.RunId;
        try
        {
            BeginRead("有界旧版记录列表");
            var result = await _store.ListLegacyHistoryWithFailuresAsync(ct);
            foreach (var record in result.Items) Records.Add(new LegacyHistoryItem(record));
            foreach (var failure in result.Failures) AddFailure(Path.GetFileName(failure.Path), failure.Message);
            SelectedRecord = Records.FirstOrDefault(row => row.Record.PlanId == planId && row.Record.RunId == runId);
            StatusMessage = Failures.Count == 0 ? "旧版记录已读取。" : "部分旧版记录未显示；请查看读取提示。";
        }
        catch (OperationCanceledException) { StatusMessage = "旧版记录读取已取消。"; throw; }
        catch (Exception ex) { AddFailure("读取失败", ex.Message); StatusMessage = "旧版记录读取失败。"; }
        finally { EndRead(); _readGate.Release(); }
    }

    /// <summary>Replace the list with one exact-ID read, including records outside the listing budget.</summary>
    [RelayCommand]
    public async Task LoadExactAsync(CancellationToken ct = default)
    {
        var planId = ExactPlanId;
        var runId = ExactRunId;
        await _readGate.WaitAsync(ct);
        try
        {
            BeginRead("按标识读取的单条旧版记录");
            // Bound edit inputs before validation; do not normalize or infer an identity.
            if (planId.Length is < 1 or > 96 || runId.Length != 32)
                throw new ArgumentException("Enter a plan ID with 1 to 96 characters and a 32-character run file alias.");
            var record = await _store.LoadLegacyHistoryRecordAsync(planId, runId, ct);
            if (record is null) { StatusMessage = "未找到指定旧版记录。"; return; }
            var row = new LegacyHistoryItem(record);
            Records.Add(row);
            SelectedRecord = row;
            StatusMessage = "已读取单条记录；刷新可返回有界列表。";
        }
        catch (OperationCanceledException) { StatusMessage = "旧版记录读取已取消。"; throw; }
        catch (Exception ex) { AddFailure("读取失败", ex.Message); StatusMessage = "旧版记录读取失败。"; }
        finally { EndRead(); _readGate.Release(); }
    }

    /// <summary>Release old preview/list references before reading another bounded result.</summary>
    private void BeginRead(string mode)
    {
        IsRefreshing = true;
        SelectedRecord = null;
        Records.Clear();
        Failures.Clear();
        ModeMessage = mode;
        StatusMessage = "正在读取旧版记录。";
    }

    /// <summary>Publish counts after every success, missing result, cancellation or error.</summary>
    private void EndRead()
    {
        IsRefreshing = false;
        OnPropertyChanged(nameof(RecordCount));
        OnPropertyChanged(nameof(FailureCount));
    }

    /// <summary>Keep file names and exception text bounded even for malformed local paths/documents.</summary>
    private void AddFailure(string label, string message)
        => Failures.Add(new PuloniaTaskHistoryField(ClipText(label, 96).Text, ClipText(message, 1024).Text));

    /// <summary>Build one bounded display projection; source bytes and source hash are never rewritten.</summary>
    partial void OnSelectedRecordChanged(LegacyHistoryItem? value)
    {
        OverviewFields.Clear();
        FactFields.Clear();
        IsPreviewTruncated = false;
        OnPropertyChanged(nameof(HasSelectedRecord));
        if (value is null) { OnPropertyChanged(nameof(PreviewUtf8ByteCount)); return; }
        var record = value.Record;
        var characters = PreviewCharacterLimit;
        var bytes = PreviewUtf8Limit;
        // JSON labels are fixed source strings. Charge every label/value to the same preview budget.
        void Add(ObservableCollection<PuloniaTaskHistoryField> target, string label,
            Func<int, (string Text, bool Truncated)> render)
        {
            var labelBytes = Encoding.UTF8.GetByteCount(label);
            if (labelBytes > bytes) { IsPreviewTruncated = true; return; }
            var allowance = Math.Min(characters, (bytes - labelBytes) / 3);
            var result = render(allowance); // Every UTF-16 code unit requires at most three UTF-8 bytes.
            characters -= result.Text.Length;
            bytes -= labelBytes + Encoding.UTF8.GetByteCount(result.Text);
            IsPreviewTruncated |= result.Truncated;
            target.Add(new PuloniaTaskHistoryField(label, result.Text));
        }
        void Identity(string label, string text) => Add(OverviewFields, label, limit => ClipText(text, Math.Min(limit, 512)));
        Identity("原始计划标识", record.PlanId);
        Identity("原始计划名称", record.PlanName);
        Identity("原始请求标识", record.RequestIdOriginal);
        Identity("请求文件别名", record.RequestId);
        Identity("原始运行标识", record.RunIdOriginal);
        Identity("运行文件别名", record.RunId);
        Identity("原始字节数", record.OriginalByteCount.ToString(CultureInfo.InvariantCulture));
        Identity("原始字节 SHA-256", record.OriginalSha256);
        Identity("记录时间", record.SubmittedAt.ToString("O", CultureInfo.InvariantCulture));
        Identity("记录状态", record.Status.ToString());
        Identity("只读原因", string.Join("\n", record.ResumeBlockReasons));
        // One detached JSON tree, never a current model/snapshot parser. Only bounded strings reach the view.
        var document = record.OriginalDocument;
        void Fact(string label, string key)
        {
            var property = document.Property(key);
            Add(FactFields, label, limit => property is null
                ? ClipText("[absent]", limit) : PreviewJson(property.Value, limit));
        }
        Fact("原始父运行标识", "resumed_from_run_id");
        Fact("原始请求与作用域", "request");
        Fact("未解决操作意图", "operation_intent");
        Fact("原始确认效果", "confirmed_effects");
        Fact("原始节点尝试", "node_results");
        Fact("原始完成地址", "completed_task_addresses");
        // Snapshot is already an opaque string. Clip its prefix directly; never pretty-print or parse its body.
        Add(FactFields, "原始快照文本（不执行）", limit => ClipText(record.SnapshotJson, limit));
        OnPropertyChanged(nameof(PreviewUtf8ByteCount));
    }

    /// <summary>Return only a bounded prefix, avoiding a split surrogate pair and marking every omission.</summary>
    private static (string Text, bool Truncated) ClipText(string text, int limit)
    {
        if (text.Length <= limit) return (text, false);
        if (limit <= 0) return (string.Empty, true);
        var count = limit - 1;
        if (count > 0 && char.IsHighSurrogate(text[count - 1])) count--;
        return (text[..count] + "…", true);
    }

    /// <summary>Serialize at most the supplied prefix, stopping traversal immediately when it cannot fit.</summary>
    private static (string Text, bool Truncated) PreviewJson(JToken value, int limit)
    {
        using var output = new PreviewWriter(limit);
        var truncated = false;
        using var writer = new JsonTextWriter(output) { Formatting = Formatting.None, AutoCompleteOnClose = false, CloseOutput = false };
        try { value.WriteTo(writer); }
        catch (PreviewLimitException) { truncated = true; }
        return (output.Prefix, truncated);
    }

    /// <summary>Small immutable list row with bounded labels; its retained evidence cannot be scheduled.</summary>
    public sealed class LegacyHistoryItem
    {
        /// <summary>Original detached legacy evidence, not a current run.</summary>
        public PuloniaLegacyHistoryRecord Record { get; }
        /// <summary>Bounded plan label; never a whole snapshot or arbitrary JSON.</summary>
        public string PlanLabel { get; }
        /// <summary>Original filename alias for visible selection identity.</summary>
        public string RunLabel => Record.RunId;
        /// <summary>Historical local time, not a live execution clock.</summary>
        public string TimeLabel => Record.SubmittedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
        /// <summary>Recorded enum value only, not a newly adjudicated outcome.</summary>
        public string StatusLabel => Record.Status.ToString();
        /// <summary>Whether the historical evidence retains unsettled facts.</summary>
        public bool HasUnresolvedFacts => Record.HasUnresolvedFacts;
        /// <summary>Wrap one immutable record for safe list display.</summary>
        public LegacyHistoryItem(PuloniaLegacyHistoryRecord record)
        {
            Record = record;
            PlanLabel = ClipText(record.PlanName, ListLabelLimit).Text;
        }
    }

    /// <summary>Private early-stop signal; it never escapes a JSON preview.</summary>
    private sealed class PreviewLimitException : Exception { }

    /// <summary>Bounded writer: no oversized serialized document is created before trimming.</summary>
    private sealed class PreviewWriter(int limit) : TextWriter
    {
        /// <summary>Only the bounded output prefix is retained.</summary>
        private readonly StringBuilder _text = new();
        /// <inheritdoc />
        public override Encoding Encoding => Encoding.UTF8;
        /// <summary>Return a prefix without a dangling high surrogate at its end.</summary>
        public string Prefix => _text.Length > 0 && char.IsHighSurrogate(_text[^1])
            ? _text.ToString(0, _text.Length - 1) : _text.ToString();
        /// <inheritdoc />
        public override void Write(char value)
        {
            if (_text.Length >= limit) throw new PreviewLimitException();
            _text.Append(value);
        }
        /// <inheritdoc />
        public override void Write(string? value)
        {
            if (value is null) return;
            var count = Math.Min(value.Length, Math.Max(0, limit - _text.Length));
            _text.Append(value.AsSpan(0, count));
            if (count != value.Length) throw new PreviewLimitException();
        }
        /// <inheritdoc />
        public override void Write(char[] buffer, int index, int count)
        {
            var take = Math.Min(count, Math.Max(0, limit - _text.Length));
            _text.Append(buffer, index, take);
            if (take != count) throw new PreviewLimitException();
        }
    }
}
