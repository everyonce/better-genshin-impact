using System.Net;
using System.Net.Sockets;
using BetterGenshinImpact.GameTask.AutoCombo.ComboBuild;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public class AutoComboEndpointTests
{
    [Theory]
    [InlineData("http://10.0.10.2:8000/v1")]
    [InlineData("http://172.16.0.1/v1")]
    [InlineData("http://172.31.255.254/v1")]
    [InlineData("http://192.168.1.1/v1")]
    [InlineData("http://127.0.0.1/v1")]
    [InlineData("http://localhost:8000/v1")]
    [InlineData("http://[::1]:8000/v1")]
    [InlineData("http://[fd12::1]:8000/v1")]
    [InlineData("http://[::ffff:10.0.10.2]:8000/v1")]
    public void LocalHttpAllowsAnOptionalKey(string url)
    {
        Assert.Null(AutoComboEndpointValidator.GetValidationError(new Uri(url), out var local,
            _ => throw new Exception("Literal/localhost should not require DNS")));
        Assert.True(local);
    }

    [Theory]
    [InlineData("http://8.8.8.8/v1")]
    [InlineData("http://172.15.255.255/v1")]
    [InlineData("http://172.32.0.0/v1")]
    [InlineData("http://192.169.0.1/v1")]
    [InlineData("http://[2606:4700::1111]/v1")]
    [InlineData("http://[::ffff:8.8.8.8]/v1")]
    [InlineData("ftp://127.0.0.1/v1")]
    [InlineData("http://user:password@10.0.10.2/v1")]
    public void PublicHttpAndUnsupportedUrlsAreRejected(string url)
    {
        Assert.NotNull(AutoComboEndpointValidator.GetValidationError(new Uri(url), out _));
    }

    [Fact]
    public void CthulhuHostnameResolvesToPrivateLan()
    {
        Assert.Null(AutoComboEndpointValidator.GetValidationError(new Uri("http://cthulhu:8000/v1"), out var local,
            host => { Assert.Equal("cthulhu", host); return [IPAddress.Parse("10.0.10.2")]; }));
        Assert.True(local);
    }

    [Fact]
    public void MixedPrivateAndPublicDnsIsRejected()
    {
        Assert.NotNull(AutoComboEndpointValidator.GetValidationError(new Uri("http://mixed.example/v1"), out var local,
            _ => [IPAddress.Parse("10.0.10.2"), IPAddress.Parse("8.8.8.8")]));
        Assert.False(local);
    }

    [Fact]
    public void UnresolvedHttpHostReturnsAnActionableError()
    {
        var error = AutoComboEndpointValidator.GetValidationError(new Uri("http://missing.example/v1"), out _,
            _ => throw new SocketException((int)SocketError.HostNotFound));
        Assert.Contains("could not resolve host", error);
        Assert.NotNull(AutoComboEndpointValidator.GetValidationError(new Uri("http://empty.example/v1"), out _, _ => []));
    }

    [Fact]
    public void PublicHttpsDoesNotRequireDnsButStillRequiresAKey()
    {
        Assert.Null(AutoComboEndpointValidator.GetValidationError(new Uri("https://provider.example/v1"), out var local,
            _ => throw new Exception("HTTPS should not require DNS")));
        Assert.False(local);
    }

    [Fact]
    public void RelativeEndpointReturnsValidationError()
    {
        Assert.NotNull(AutoComboEndpointValidator.GetValidationError(new Uri("v1", UriKind.Relative), out _));
    }
}
