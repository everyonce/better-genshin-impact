using BetterGenshinImpact.Core.Config;
using Microsoft.ML.OnnxRuntime;
using System;
using System.IO;
using System.Text.Json;

namespace BetterGenshinImpact.Core.Recognition.ONNX.YOLO;

[Obsolete]
public class Predictor
{
    private readonly InferenceSession _session;
    private readonly string[] labels;

    public Predictor()
    {
        var options = new SessionOptions();
        var modelPath = Global.Absolute(@"Assets\Model\Fish\bgi_fish.onnx");
        if (!File.Exists(modelPath)) throw new FileNotFoundException("Auto-fishing model file was not found", modelPath);

        _session = new InferenceSession(modelPath, options);

        var wordJsonPath = Global.Absolute(@"Assets\Model\Fish\label.json");
        if (!File.Exists(wordJsonPath)) throw new FileNotFoundException("Auto-fishing model classification file was not found", wordJsonPath);

        var json = File.ReadAllText(wordJsonPath);
        labels = JsonSerializer.Deserialize<string[]>(json) ?? throw new Exception("label.json deserialize failed");
    }
}
