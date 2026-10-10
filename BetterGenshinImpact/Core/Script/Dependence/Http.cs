using BetterGenshinImpact.Core.Script.Utils;
using System;
using System.IO;
using System.Threading.Tasks;
using OpenCvSharp;
using System.Linq;
using System.Text.Json;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using BetterGenshinImpact.GameTask;
using Microsoft.Extensions.Logging;

namespace BetterGenshinImpact.Core.Script.Dependence;

public class Http
{
    private readonly ILogger<Http> _logger = App.GetLogger<Http>();

    private void CheckHttpPermission(string url)
    {
        var currentProject = RunnerContext.Instance.CurrentScriptProject;
        if (!currentProject?.AllowJsHTTP ?? false)
        {
            throw new UnauthorizedAccessException("This JavaScript script is not allowed to make HTTP requests. Enable 'JavaScript HTTP permission' in the scheduler's general settings.");
        }
        var allowedUrls = currentProject?.Project?.Manifest.HttpAllowedUrls ?? [];
        if (allowedUrls.Length == 0)
        {
            throw new UnauthorizedAccessException("No allowed request URLs are configured for this JavaScript script. Configure http_allowed_urls in the script's manifest.json.");
        }
        if (allowedUrls.Any(allowedUrl =>
        {
            // fuzzy match
            var pattern = "^" + System.Text.RegularExpressions.Regex.Escape(allowedUrl).Replace("\\*", ".*") + "$";
            _logger.LogDebug($"[HTTP] Checking whether URL {url} matches: {pattern}");
            var regex = new System.Text.RegularExpressions.Regex(pattern);
            return regex.IsMatch(url);
        }))
        {
            return;
        }
        throw new UnauthorizedAccessException($"This JavaScript script is not allowed to request this URL: {url}. Configure http_allowed_urls in the script's manifest.json. Currently allowed URLs: [{string.Join(", ", allowedUrls)}]");
    }

    public class HttpReponse
    {
        public int status_code { get; set; }
        public Dictionary<string, string> headers { get; set; } = new();
        public string body { get; set; } = "";
    }


    /// <summary>
    /// 执行HTTP请求
    /// </summary>
    /// <param name="method">HTTP方法</param>
    /// <param name="url">请求URL</param>
    /// <param name="body">请求体</param>
    /// <param name="headersJson">请求头，JSON格式</param>
    /// <returns></returns>
    public async Task<HttpReponse> Request(string method, string url, string? body = null, string? headersJson = null)
    {
        _logger.LogDebug($"[HTTP] Sending HTTP request: {method} {url} Body: {(body != null ? body : "null")} Headers: {(headersJson != null ? headersJson : "null")}");
        CheckHttpPermission(url);

        var dictHeaders = new Dictionary<string, string>();
        if (!string.IsNullOrWhiteSpace(headersJson))
        {
            try
            {
                var headers = JsonSerializer.Deserialize<Dictionary<string, string>>(headersJson);
                if (headers != null)
                {
                    dictHeaders = headers;
                }
            }
            catch (JsonException)
            {
                throw new ArgumentException("The headers JSON is invalid.");
            }
        }

        // header全部小写
        dictHeaders = dictHeaders.ToDictionary(kvp => kvp.Key.ToLowerInvariant(), kvp => kvp.Value);

        // 提前取出来Content-Type，防止被覆盖
        string contentType = "application/json";
        if (dictHeaders.TryGetValue("content-type", out var ct))
        {
            contentType = ct;
            dictHeaders.Remove("content-type");
        }

        // 使用HttpClient发送请求
        using var httpClient = new HttpClient();
        httpClient.DefaultRequestHeaders.Clear();
        foreach (var header in dictHeaders)
        {
            httpClient.DefaultRequestHeaders.Add(header.Key, header.Value);
        }

        var content = body == null ? null : new StringContent(body, Encoding.UTF8, contentType);
        var response = await httpClient.SendAsync(new HttpRequestMessage(new HttpMethod(method), url) { Content = content });

        var responseCode = (int)response.StatusCode;
        var responseHeaders = response.Headers.ToDictionary(h => h.Key, h => h.Value.First()); // 只取第一个值
        var responseBody = await response.Content.ReadAsStringAsync();
        return new HttpReponse
        {
            status_code = responseCode,
            headers = responseHeaders,
            body = responseBody,
        };
    }
}
