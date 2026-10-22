using Compunet.YoloSharp;
using System.IO;
using Microsoft.ML.OnnxRuntime;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise image decoding and real YOLO preprocessing after the decoder dependency upgrade.</summary>
public sealed class ImageDecoderCompatibilityTests
{
    [Fact]
    public void PatchedDecoderWorksWithBundledTreeDetector()
    {
        var model = Path.Combine(AppContext.BaseDirectory, "Assets", "Model", "Domain", "bgi_tree.onnx");
        Assert.True(File.Exists(model), "The packaged detection model is required for compatibility validation.");
        using var original = new Image<Rgb24>(640, 640);
        using var png = new MemoryStream();
        original.SaveAsPng(png);
        png.Position = 0;
        using var decoded = Image.Load<Rgb24>(png);
        using var options = new SessionOptions { IntraOpNumThreads = 1 };
        using var predictor = new YoloPredictor(model, new YoloPredictorOptions { SessionOptions = options });
        var result = predictor.Detect(decoded);
        Assert.NotNull(result);
    }
}
