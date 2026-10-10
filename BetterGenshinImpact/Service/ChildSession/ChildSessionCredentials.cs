using System;
using System.ComponentModel;
using System.Threading;
using BetterGenshinImpact.Helpers.Win32;
using Meziantou.Framework.Win32;

namespace BetterGenshinImpact.Service.ChildSession;

/// <summary>Opt-in credentials for the local Desktop Clone connection only.</summary>
public static class ChildSessionCredentials
{
    public const string TargetName = "BetterGenshinImpact.DesktopClone";
    private static int _revision;
    public static int Revision => Volatile.Read(ref _revision);

    /// <summary>Read only when connecting; do not retain the result in configuration or UI state.</summary>
    public static ChildSessionCredential? Read()
    {
        var credential = CredentialManagerHelper.ReadCredential(TargetName);
        return credential == null || string.IsNullOrWhiteSpace(credential.UserName) || string.IsNullOrEmpty(credential.Password)
            ? null
            : new ChildSessionCredential(credential.UserName, credential.Password);
    }

    /// <summary>Call only after the user explicitly chooses to save their Windows sign-in.</summary>
    public static void Save(string userName, string password)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(userName);
        ArgumentException.ThrowIfNullOrEmpty(password);
        CredentialManagerHelper.SaveCredential(TargetName, userName.Trim(), password,
            "Windows sign-in for BetterGI Desktop Clone", CredentialPersistence.LocalMachine);
        Interlocked.Increment(ref _revision);
    }

    public static void Forget()
    {
        try
        {
            // The shared helper swallows errors and logs exception messages. Let the caller
            // display a safe error instead, without potentially sensitive native details.
            CredentialManager.DeleteCredential(TargetName);
        }
        catch (Win32Exception exception) when (exception.NativeErrorCode == 1168)
        {
            // ERROR_NOT_FOUND: forgetting an already missing credential is successful.
        }
        Interlocked.Increment(ref _revision);
    }
}

// Intentionally not a record: generated record ToString() would disclose the password.
public sealed class ChildSessionCredential
{
    public string UserName { get; }
    [System.Text.Json.Serialization.JsonIgnore]
    [Newtonsoft.Json.JsonIgnore]
    public string Password { get; }

    internal ChildSessionCredential(string userName, string password)
    {
        UserName = userName;
        Password = password;
    }
}
