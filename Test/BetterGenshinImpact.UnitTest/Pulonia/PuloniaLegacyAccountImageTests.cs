using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Pulonia.Models;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.ViewModel.Windows.Pulonia;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Xunit;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>Synthetic bytes and account/editor metadata only; every credential/switcher operation fails the test.</summary>
public sealed class PuloniaLegacyAccountImageTests : IDisposable
{
    /// <summary>Only this test-owned temporary directory is accessed.</summary>
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pulonia-legacy-image-" + Guid.NewGuid().ToString("N"));
    /// <summary>Ordinary generated legacy account identity, kept exact through every roundtrip.</summary>
    private const string LegacyId = "account_0123456789abcdef0123456789abcdef";
    /// <summary>Known SHA-256 of the synthetic ASCII bytes abc.</summary>
    private const string Pin = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    /// <summary>Real external services must never be reached by these fixtures.</summary>
    private readonly RefusingVault _vault = new();
    /// <summary>Image/login runtime operations must never be reached by editor metadata tests.</summary>
    private readonly RefusingSwitcher _switcher = new();

    /// <summary>Known bytes match without any decoder or filesystem involvement, and caller mutation is detected.</summary>
    [Fact]
    public void PinChecksTheExactGivenBytes()
    {
        var bytes = Encoding.ASCII.GetBytes("abc");
        PuloniaGenshinAccountImageProvenance.Verify(bytes, Pin);
        bytes[0] ^= 1;
        Assert.Throws<InvalidOperationException>(() => PuloniaGenshinAccountImageProvenance.Verify(bytes, Pin));
    }

    /// <summary>A null legacy pin preserves the upstream immutable-path policy without inventing a content claim.</summary>
    [Fact]
    public void NullPinDoesNotInventFingerprint()
    {
        PuloniaGenshinAccountImageProvenance.Verify([1, 2, 3], null);
        PuloniaGenshinAccountImageProvenance.Verify([], null);
        var account = Profile(); account.ImageVersion = null;
        Assert.Equal(JTokenType.Null, JObject.Parse(PuloniaTaskJson.Write(account))["image_version"]!.Type);
    }

    /// <summary>Malformed or uppercase legacy versions cannot weaken the old exact lowercase comparison.</summary>
    [Theory]
    [InlineData("")]
    [InlineData("abc")]
    [InlineData("BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD")]
    [InlineData("ga7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")]
    [InlineData("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad\n")]
    public void MalformedPinIsRejected(string value)
        => Assert.Throws<InvalidOperationException>(() => PuloniaGenshinAccountImageProvenance.Verify([1], value));

    /// <summary>Both old explicit-null and omitted optional fields remain readable without regenerating account IDs.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void NullAndOmittedLegacyFieldsRoundTrip(bool omitted)
    {
        var doc = JObject.Parse(PuloniaTaskJson.Write(Profile()));
        if (omitted) doc.Remove("image_version"); else doc["image_version"] = JValue.CreateNull();
        var account = PuloniaTaskJson.Read<PuloniaGenshinAccountProfile>(doc.ToString());
        Assert.Equal(LegacyId, account.Id); Assert.Null(account.ImageVersion);
        Assert.Null(PuloniaTaskJson.Read<PuloniaGenshinAccountProfile>(PuloniaTaskJson.Write(account)).ImageVersion);
    }

    /// <summary>The restored field does not relax the shared strict unknown-member or duplicate-key readers.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void OtherUnknownAndDuplicateMembersStayRejected(bool duplicate)
    {
        var json = PuloniaTaskJson.Write(Profile());
        json = duplicate ? json.Insert(json.IndexOf('{') + 1, "\"image_version\":null,")
            : json.Insert(json.IndexOf('{') + 1, "\"image_version_typo\":null,");
        Assert.ThrowsAny<JsonException>(() => PuloniaTaskJson.Read<PuloniaGenshinAccountProfile>(json));
    }

    /// <summary>Serialized account snapshots retain their pin independently of later mutable account edits.</summary>
    [Fact]
    public void SerializedProfileSnapshotRetainsPin()
    {
        var profile = Profile(); var snapshot = PuloniaTaskJson.Write(profile);
        profile.Name = "Changed"; profile.ImagePath = "account-images/new.png"; profile.ImageVersion = null;
        var retained = PuloniaTaskJson.Read<PuloniaGenshinAccountProfile>(snapshot);
        Assert.Equal(LegacyId, retained.Id); Assert.Equal(Pin, retained.ImageVersion);
        Assert.Equal("account-images/legacy.png", retained.ImagePath);
        PuloniaGenshinAccountImageProvenance.Verify(Encoding.ASCII.GetBytes("abc"), retained.ImageVersion);
    }

    /// <summary>Store load/save preserves exact references and the pin while changing ordinary metadata only.</summary>
    [Fact]
    public async Task MetadataRoundtripKeepsIdentityAndPin()
    {
        await SeedAsync(); using var store = Store();
        var settings = await store.LoadAccountSettingsAsync(); var account = settings.Accounts.Single(a => a.Id == LegacyId);
        account.Name = "Edited name"; account.ListText = "masked@example";
        var saved = await store.SaveAccountSettingsAsync(settings);
        var retained = saved.Accounts.Single(a => a.Id == LegacyId);
        Assert.Equal(Pin, retained.ImageVersion); Assert.Equal(account.ImagePath, retained.ImagePath);
        Assert.Equal("100000001", retained.Uid); Assert.Equal(LegacyId, retained.Id);
        Assert.Equal(5, saved.Revision); Assert.Equal(4, settings.Revision);
        Assert.Equal("abc", await File.ReadAllTextAsync(Path.Combine(_root, "account-images", "legacy.png")));
    }

    /// <summary>An older editor cannot remove provenance by omitting it, including equivalent Windows path spellings.</summary>
    [Theory]
    [InlineData("account-images/legacy.png")]
    [InlineData("account-images/./legacy.png")]
    [InlineData("ACCOUNT-IMAGES/LEGACY.PNG")]
    public async Task SameImageOmittedPinIsRestored(string path)
    {
        await SeedAsync(); using var store = Store();
        var settings = await store.LoadAccountSettingsAsync(); var account = settings.Accounts.Single(a => a.Id == LegacyId);
        account.ImageVersion = null; account.ImagePath = path; account.Name = "Older editor";
        var saved = await store.SaveAccountSettingsAsync(settings);
        Assert.Null(account.ImageVersion);
        Assert.Equal(Pin, saved.Accounts.Single(a => a.Id == LegacyId).ImageVersion);
        Assert.Equal(Pin, (await store.LoadAccountSettingsAsync()).Accounts.Single(a => a.Id == LegacyId).ImageVersion);
    }

    /// <summary>A metadata save cannot silently repin the same file; the account JSON stays byte-exact on rejection.</summary>
    [Fact]
    public async Task SameImageChangedPinFailsBeforePublication()
    {
        await SeedAsync(); var before = await File.ReadAllBytesAsync(AccountFile);
        using var store = Store(); var settings = await store.LoadAccountSettingsAsync();
        settings.Accounts.Single(a => a.Id == LegacyId).ImageVersion = new string('0', 64);
        await Assert.ThrowsAsync<InvalidOperationException>(() => store.SaveAccountSettingsAsync(settings));
        Assert.Equal(before, await File.ReadAllBytesAsync(AccountFile));
    }

    /// <summary>Removing a pin without a replacement file does not make a broken draft durable.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingReplacementCannotDropPin(bool removed)
    {
        await SeedAsync(); var before = await File.ReadAllBytesAsync(AccountFile);
        using var store = Store(); var settings = await store.LoadAccountSettingsAsync();
        var account = settings.Accounts.Single(a => a.Id == LegacyId);
        account.ImageVersion = null; account.ImagePath = removed ? null : "account-images/not-created.png";
        await Assert.ThrowsAsync<InvalidOperationException>(() => store.SaveAccountSettingsAsync(settings));
        Assert.Equal(before, await File.ReadAllBytesAsync(AccountFile));
    }

    /// <summary>A new immutable replacement may follow the null-pin policy while the prior image bytes remain intact.</summary>
    [Fact]
    public async Task SuccessfulReplacementDoesNotOverwriteLegacyImage()
    {
        await SeedAsync(); using var store = Store(); var settings = await store.LoadAccountSettingsAsync();
        var account = settings.Accounts.Single(a => a.Id == LegacyId);
        account.ImagePath = await store.CreateAccountImageAsync(LegacyId, [4, 5, 6]); account.ImageVersion = null;
        var saved = await store.SaveAccountSettingsAsync(settings);
        Assert.Null(saved.Accounts.Single(a => a.Id == LegacyId).ImageVersion);
        Assert.Equal(new byte[] { 4, 5, 6 }, await File.ReadAllBytesAsync(store.GetAccountImagePath(account.ImagePath)));
        Assert.Equal("abc", await File.ReadAllTextAsync(Path.Combine(_root, "account-images", "legacy.png")));
    }

    /// <summary>Catalog admission rejects orphan pins and pins attached to the default account.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void InvalidAccountPinBindingIsRejected(bool defaultAccount)
    {
        var profile = defaultAccount ? PuloniaGenshinAccountProfile.CreateDefault() : Profile();
        profile.ImageVersion = Pin; profile.ImagePath = defaultAccount ? "account-images/legacy.png" : null;
        var settings = new PuloniaGenshinAccountSettings();
        if (defaultAccount) settings.Accounts[0] = profile; else settings.Accounts.Add(profile);
        Assert.Throws<InvalidOperationException>(() => PuloniaTaskStore.ValidateAccountSettings(settings));
    }

    /// <summary>Real editor selection and save commands retain a legacy pin without invoking image/runtime services.</summary>
    [Fact]
    public async Task EditorMetadataAndSelectionKeepPin()
    {
        await SeedAsync(); using var store = Store(); using var editor = Editor(store); await editor.LoadAsync();
        var account = editor.Accounts.Single(a => a.Id == LegacyId); editor.SelectedAccount = account;
        editor.AccountName = "Editor name"; editor.ListText = "full masked text";
        editor.SelectedAccount = editor.Accounts.Single(a => a.IsDefault); editor.SelectedAccount = account;
        Assert.Equal(Pin, account.ImageVersion); Assert.Equal("Editor name", editor.AccountName);
        await editor.SaveCommand.ExecuteAsync(null);
        Assert.Equal(Pin, account.ImageVersion);
        var saved = (await store.LoadAccountSettingsAsync()).Accounts.Single(a => a.Id == LegacyId);
        Assert.Equal("Editor name", saved.Name); Assert.Equal(Pin, saved.ImageVersion);
    }

    /// <summary>The editor's success-only replacement transition clears only the new draft's pin.</summary>
    [Fact]
    public async Task EditorCreatedImageTransitionAdoptsNewPolicy()
    {
        await SeedAsync(); using var store = Store(); using var editor = Editor(store); await editor.LoadAsync();
        var account = editor.Accounts.Single(a => a.Id == LegacyId); editor.SelectedAccount = account;
        var created = await store.CreateAccountImageAsync(LegacyId, [8, 9]);
        editor.ApplyCreatedImagePath(created);
        Assert.Equal(Pin, account.ImageVersion); // Editing the draft does not rewrite the retained profile before save/selection.
        await editor.SaveCommand.ExecuteAsync(null);
        Assert.Null(account.ImageVersion); Assert.Equal(created, account.ImagePath);
        var saved = (await store.LoadAccountSettingsAsync()).Accounts.Single(a => a.Id == LegacyId);
        Assert.Null(saved.ImageVersion); Assert.Equal(created, saved.ImagePath);
        editor.AccountName = "Second metadata edit"; await editor.SaveCommand.ExecuteAsync(null);
        Assert.Null((await store.LoadAccountSettingsAsync()).Accounts.Single(a => a.Id == LegacyId).ImageVersion);
        Assert.Equal("abc", await File.ReadAllTextAsync(Path.Combine(_root, "account-images", "legacy.png")));
    }

    /// <summary>A failed creation cannot reach the draft transition or discard the pin during a later metadata save.</summary>
    [Fact]
    public async Task FailedCreationLeavesEditorPinUntouched()
    {
        await SeedAsync(); using var store = Store(); using var editor = Editor(store); await editor.LoadAsync();
        editor.SelectedAccount = editor.Accounts.Single(a => a.Id == LegacyId);
        using var canceled = new CancellationTokenSource(); canceled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => store.CreateAccountImageAsync(LegacyId, [8], canceled.Token));
        editor.AccountName = "After failed creation"; await editor.SaveCommand.ExecuteAsync(null);
        Assert.Equal(Pin, (await store.LoadAccountSettingsAsync()).Accounts.Single(a => a.Id == LegacyId).ImageVersion);
        Assert.Single(Directory.GetFiles(Path.Combine(_root, "account-images")));
    }

    /// <summary>The catalog path is always inside this test's private temporary root.</summary>
    private string AccountFile => Path.Combine(_root, "accounts.json");
    /// <summary>Construct a store with a fail-fast fake vault; the native credential implementation is never called.</summary>
    private PuloniaTaskStore Store() => new(_root) { CredentialVault = _vault };
    /// <summary>No runtime coordinator is supplied, and the substitute switcher refuses every operation.</summary>
    private PuloniaGenshinAccountsViewModel Editor(PuloniaTaskStore store) => new(store, null!, _switcher);
    /// <summary>Create the legacy profile with an exact 40-character identity and synthetic image pin.</summary>
    private static PuloniaGenshinAccountProfile Profile() => new()
    {
        Id = LegacyId, Name = "Synthetic legacy account", Uid = "100000001", LoginMode = PuloniaGenshinAccountLoginMode.Image,
        ImagePath = "account-images/legacy.png", ImageVersion = Pin
    };
    /// <summary>Seed only owned synthetic metadata and three bytes; no image is decoded.</summary>
    private async Task SeedAsync()
    {
        Directory.CreateDirectory(Path.Combine(_root, "account-images"));
        await File.WriteAllBytesAsync(Path.Combine(_root, "account-images", "legacy.png"), Encoding.ASCII.GetBytes("abc"));
        var settings = new PuloniaGenshinAccountSettings { Revision = 4 }; settings.Accounts.Add(Profile());
        await File.WriteAllTextAsync(AccountFile, PuloniaTaskJson.Write(settings), new UTF8Encoding(false));
    }

    /// <summary>Even swallowed external-service failures are visible through counters at test cleanup.</summary>
    public void Dispose()
    {
        try { Assert.Equal(0, _vault.Calls); Assert.Equal(0, _switcher.Calls); }
        finally { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
    }

    /// <summary>Credential operations are forbidden, including a normally swallowed failure.</summary>
    private sealed class RefusingVault : IPuloniaCredentialVault
    {
        /// <summary>Count every forbidden invocation.</summary>
        public int Calls { get; private set; }
        /// <inheritdoc />
        public void Write(string target, string userName, string password) { Calls++; throw new InvalidOperationException("Forbidden credential write."); }
        /// <inheritdoc />
        public void Delete(string target) { Calls++; throw new InvalidOperationException("Forbidden credential delete."); }
    }

    /// <summary>Any attempted runtime login/capture is a fixture failure, never a native operation.</summary>
    private sealed class RefusingSwitcher : IPuloniaGenshinAccountSwitcher
    {
        /// <summary>Count every forbidden invocation.</summary>
        public int Calls { get; private set; }
        /// <inheritdoc />
        public Task<string> PrepareAsync(GameRuntime runtime, PuloniaGenshinAccountProfile account, CancellationToken ct)
        { Calls++; throw new InvalidOperationException("Forbidden runtime preparation."); }
        /// <inheritdoc />
        public Task VerifyAsync(GameRuntime runtime, string expectedUid, CancellationToken ct)
        { Calls++; throw new InvalidOperationException("Forbidden runtime verification."); }
        /// <inheritdoc />
        public Task<(string Uid, string ImagePath)> CaptureCurrentAccountAsync(GameRuntime runtime, string accountId, CancellationToken ct)
        { Calls++; throw new InvalidOperationException("Forbidden image capture."); }
    }
}
