using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Music.Model;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;
using System;
using System.IO;
using System.Text;

namespace BetterGenshinImpact.GameTask.Music.Service;

public sealed class MusicStateStore : IMusicStateStore
{
    private static readonly Encoding Utf8WithoutBom = new UTF8Encoding(false);
    private readonly ILogger<MusicStateStore> _logger = App.GetLogger<MusicStateStore>();
    private readonly object _syncRoot = new();
    private readonly string _statePath = Global.Absolute(@"User\Music\music-state.json");

    public MusicStateStore()
    {
        State = Load();
    }

    public MusicLibraryState State { get; }

    public void Save()
    {
        lock (_syncRoot)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(_statePath)!);
                var json = JsonConvert.SerializeObject(State, Formatting.Indented);
                File.WriteAllText(_statePath, json, Utf8WithoutBom);
            }
            catch (Exception e)
            {
                _logger.LogWarning(e, "Failed to save the playback queue state");
            }
        }
    }

    private MusicLibraryState Load()
    {
        try
        {
            if (!File.Exists(_statePath))
            {
                return new MusicLibraryState();
            }

            var json = File.ReadAllText(_statePath, Utf8WithoutBom);
            var state = JsonConvert.DeserializeObject<MusicLibraryState>(json) ?? new MusicLibraryState();
            state.MusicFolderHistory ??= [];
            state.Items = new System.Collections.Generic.Dictionary<string, MusicItemPreference>(
                state.Items ?? [],
                StringComparer.OrdinalIgnoreCase);
            return state;
        }
        catch (Exception e)
        {
            _logger.LogWarning(e, "Failed to load the playback queue state; using the default state");
            return new MusicLibraryState();
        }
    }
}
