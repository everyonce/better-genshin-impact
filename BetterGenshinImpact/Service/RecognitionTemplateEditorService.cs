using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.Interface;
using BetterGenshinImpact.View.Windows;
using BetterGenshinImpact.ViewModel.Windows;
using Microsoft.Extensions.Logging;
using Microsoft.Win32;
using OpenCvSharp;
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;

namespace BetterGenshinImpact.Service;

/// <summary>
/// 协调游戏截图、本地图片与 Recognition 模板编辑窗口的生命周期。
/// </summary>
public sealed class RecognitionTemplateEditorService
{
    private sealed record EditorSource(Mat Image, string InitialTemplateName);

    private readonly RecognitionTemplateAssetService _assetService;
    private readonly IConfigService _configService;
    private readonly ILogger<RecognitionTemplateEditorService> _logger;

    /// <summary>
    /// 游戏运行环境服务，截取当前画面时读取 <see cref="GameRuntimeService.Current"/>
    /// </summary>
    private readonly GameRuntimeService _runtimeService;

    private RecognitionTemplateEditorWindow? _window;
    private int _isOpening;

    public RecognitionTemplateEditorService(
        RecognitionTemplateAssetService assetService,
        IConfigService configService,
        ILogger<RecognitionTemplateEditorService> logger,
        GameRuntimeService runtimeService)
    {
        _assetService = assetService;
        _configService = configService;
        _logger = logger;
        _runtimeService = runtimeService;
    }

    public Task OpenAsync()
    {
        return OpenCoreAsync(
            () => Task.Run<EditorSource?>(() => new EditorSource(CaptureRecognitionCanvas(), "")),
            "Cannot capture the current game screen and open the template editor.",
            "Start screen capture on the Start page and make sure the game window is not minimized.");
    }

    public Task OpenFromImageAsync()
    {
        return OpenCoreAsync(
            SelectLocalImageAsync,
            "Cannot read the selected image and open the template editor.",
            "Select a valid PNG, JPEG, BMP, or WebP image.");
    }

    private async Task OpenCoreAsync(
        Func<Task<EditorSource?>> sourceFactory,
        string failureMessage,
        string guidance)
    {
        if (Interlocked.Exchange(ref _isOpening, 1) != 0)
        {
            return;
        }

        Mat? sourceImage = null;
        try
        {
            var dispatcher = Application.Current?.Dispatcher
                             ?? throw new InvalidOperationException("The WPF Dispatcher has not been initialized.");
            var activatedExistingWindow = await dispatcher.InvokeAsync(() =>
            {
                if (_window is not { IsVisible: true })
                {
                    return false;
                }

                if (_window.WindowState == WindowState.Minimized)
                {
                    _window.WindowState = WindowState.Normal;
                }

                _window.Activate();
                return true;
            });
            if (activatedExistingWindow)
            {
                return;
            }

            var source = await sourceFactory();
            if (source == null)
            {
                return;
            }

            var editorImage = source.Image;
            sourceImage = editorImage;
            if (editorImage.Empty())
            {
                throw new InvalidOperationException("No valid image was obtained.");
            }

            await dispatcher.InvokeAsync(() =>
            {
                var viewModel = new RecognitionTemplateEditorViewModel(
                    editorImage,
                    _assetService,
                    _configService,
                    source.InitialTemplateName);
                sourceImage = null; // 所有权已经转移给 ViewModel。
                RecognitionTemplateEditorWindow? window = null;
                try
                {
                    window = new RecognitionTemplateEditorWindow(viewModel);
                    if (Application.Current.MainWindow is { IsVisible: true, WindowState: not WindowState.Minimized } owner)
                    {
                        window.Owner = owner;
                    }
                    else
                    {
                        window.WindowStartupLocation = WindowStartupLocation.CenterScreen;
                    }

                    window.Closed += OnWindowClosed;
                    _window = window;
                    window.Show();
                    window.Activate();
                }
                catch
                {
                    if (window != null)
                    {
                        window.Closed -= OnWindowClosed;
                    }

                    _window = null;
                    viewModel.Dispose();
                    throw;
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to open the Recognition template editor");
            await ShowOpenErrorAsync(failureMessage, ex.Message, guidance);
        }
        finally
        {
            sourceImage?.Dispose();
            Interlocked.Exchange(ref _isOpening, 0);
        }
    }

    private static async Task<EditorSource?> SelectLocalImageAsync()
    {
        var dispatcher = Application.Current?.Dispatcher
                         ?? throw new InvalidOperationException("The WPF Dispatcher has not been initialized.");
        var imagePath = await dispatcher.InvokeAsync(() =>
        {
            var dialog = new OpenFileDialog
            {
                Title = I18nService.Instance.Translate("选择模板制作参考图片"),
                Filter = I18nService.Instance.Translate("图片文件|*.png;*.jpg;*.jpeg;*.bmp;*.webp|PNG 图片|*.png|所有文件|*.*"),
                CheckFileExists = true
            };
            return dialog.ShowDialog(Application.Current.MainWindow) == true
                ? dialog.FileName
                : null;
        });
        if (string.IsNullOrWhiteSpace(imagePath))
        {
            return null;
        }

        var image = await Task.Run(() => LoadLocalImage(imagePath));
        return new EditorSource(image, Path.GetFileNameWithoutExtension(imagePath));
    }

    private static Mat LoadLocalImage(string imagePath)
    {
        using var stream = File.OpenRead(imagePath);
        var image = Mat.FromStream(stream, ImreadModes.Color);
        if (image.Empty())
        {
            image.Dispose();
            throw new InvalidOperationException("The selected file is not a readable image.");
        }

        return image;
    }

    /// <summary>
    /// 截取当前运行环境的画面作为模板制作画布
    /// </summary>
    /// <exception cref="InvalidOperationException">截图器未启动</exception>
    private Mat CaptureRecognitionCanvas()
    {
        var runtime = _runtimeService.Current ?? throw new InvalidOperationException("截图器未启动");
        using var captureRegion = runtime.CaptureToRectArea();
        if (captureRegion.SrcMat.Empty())
        {
            throw new InvalidOperationException("No valid game screenshot was obtained.");
        }

        return captureRegion.SrcMat.Clone();
    }

    private void OnWindowClosed(object? sender, EventArgs e)
    {
        if (sender is RecognitionTemplateEditorWindow window)
        {
            window.Closed -= OnWindowClosed;
            if (ReferenceEquals(_window, window))
            {
                _window = null;
            }
        }
    }

    private static async Task ShowOpenErrorAsync(string failureMessage, string detail, string guidance)
    {
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher == null)
        {
            return;
        }

        await dispatcher.InvokeAsync(() =>
        {
            ThemedMessageBox.Show(
                $"{failureMessage}{Environment.NewLine}{Environment.NewLine}{detail}{Environment.NewLine}{Environment.NewLine}{guidance}",
                I18nService.Instance.Translate("模板素材制作"),
                MessageBoxButton.OK,
                ThemedMessageBox.MessageBoxIcon.Warning,
                MessageBoxResult.OK,
                Application.Current.MainWindow);
        });
    }
}
