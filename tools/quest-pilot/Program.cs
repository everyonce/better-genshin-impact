using System.Text.Json;
using BetterGenshinImpact.GameTask.Common.Map.MiniMap;
using OpenCvSharp;

var result = new List<object>();
using var predictor = new MiniMapPreprocessor();
foreach (var path in args)
{
    try
    {
        using var image = Cv2.ImRead(path, ImreadModes.Color);
        if (image.Empty() || image.Width < 274 || image.Height < 231)
        {
            result.Add(new { path, angle = (float?)null, confidence = 0f, error = "image empty or too small" });
            continue;
        }
        using var roi = new Mat(image, new Rect(62, 19, 212, 212));
        var (angle, confidence) = predictor.PredictRotationWithConfidence(roi);
        var markers = FindWorldMarkers(image);
        result.Add(new { path, angle = (float?)angle, confidence, world_marker_candidates = markers, error = (string?)null });
    }
    catch (Exception e)
    {
        result.Add(new { path, angle = (float?)null, confidence = 0f, error = e.GetType().Name + ": " + e.Message });
    }
}
Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));

static object[] FindWorldMarkers(Mat image)
{
    // Search only the gameplay view: exclude HUD and minimap. Genshin's active
    // quest marker is a compact gold diamond with a dark border, unlike foliage.
    var searchRect = new Rect(320, 150, Math.Min(1440, image.Width - 320), Math.Min(630, image.Height - 150));
    using var view = new Mat(image, searchRect);
    using var hsv = new Mat();
    using var mask = new Mat();
    Cv2.CvtColor(view, hsv, ColorConversionCodes.BGR2HSV);
    Cv2.InRange(hsv, new Scalar(12, 125, 135), new Scalar(38, 255, 255), mask);
    Cv2.FindContours(mask, out Point[][] contours, out _, RetrievalModes.External, ContourApproximationModes.ApproxSimple);
    var candidates = new List<object>();
    foreach (var contour in contours)
    {
        var bounds = Cv2.BoundingRect(contour);
        if (bounds.Width < 20 || bounds.Width > 65 || bounds.Height < 20 || bounds.Height > 65)
            continue;
        var ratio = bounds.Width / (double)bounds.Height;
        if (ratio < 0.72 || ratio > 1.38)
            continue;
        var area = Cv2.ContourArea(contour);
        var fill = area / (bounds.Width * (double)bounds.Height);
        if (area < 250 || fill < 0.30 || fill > 0.88)
            continue;
        var perimeter = Cv2.ArcLength(contour, true);
        var polygon = Cv2.ApproxPolyDP(contour, 0.035 * perimeter, true);
        if (polygon.Length is < 4 or > 8 || !Cv2.IsContourConvex(polygon))
            continue;
        // Require gold pixels across the compact shape, preventing narrow
        // bright grass blades from passing the square/diamond geometry filter.
        candidates.Add(new
        {
            center = new { x = searchRect.X + bounds.X + bounds.Width / 2.0, y = searchRect.Y + bounds.Y + bounds.Height / 2.0 },
            bbox = new { x = searchRect.X + bounds.X, y = searchRect.Y + bounds.Y, width = bounds.Width, height = bounds.Height },
            contour_area = Math.Round(area, 1),
            polygon_vertices = polygon.Length,
            fill_ratio = Math.Round(fill, 3)
        });
    }
    return candidates.ToArray();
}
