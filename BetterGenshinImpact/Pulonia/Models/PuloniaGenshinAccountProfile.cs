using Newtonsoft.Json;

namespace BetterGenshinImpact.Pulonia.Models;

/// <summary>原神账号的切换资料；登录密码只保存在 Windows 凭据管理器。</summary>
public sealed class PuloniaGenshinAccountProfile
{
    /// <summary>当前登录账号的固定别名，不代表某个已核验的 UID。</summary>
    public const string DefaultId = "default";
    /// <summary>供计划引用的稳定身份，形如 <c>acc_</c> + 16 位短 ID；默认账号固定为 <see cref="DefaultId"/>。</summary>
    public string Id { get; set; } = PuloniaId.NewAccountId();
    /// <summary>用户可读名称。</summary>
    public string Name { get; set; } = "新账号";
    /// <summary>目标完整 UID；默认账号不指定目标。</summary>
    public string? Uid { get; set; }
    /// <summary>优先使用的登录方式。</summary>
    public PuloniaGenshinAccountLoginMode LoginMode { get; set; }
    /// <summary>
    /// 账号图片相对于 User/Pulonia 的路径。图片文件每次采集或导入都新建、不覆盖，
    /// 新图片的运行快照记录此路径；旧图片仍保留 ImageVersion 内容校验，旧图片暂不清理。
    /// </summary>
    public string? ImagePath { get; set; }
    /// <summary>Optional legacy SHA-256 pin. Metadata edits retain it; newly created replacement images use the immutable-path policy.</summary>
    public string? ImageVersion { get; set; }
    /// <summary>登录列表显示的完整脱敏账号文字。</summary>
    public string ListText { get; set; } = "";
    /// <summary>
    /// Windows 凭据的引用，不包含用户名或密码；目标名按账号固定，保存时覆盖同名凭据。
    /// 由账号存储确定：账号目录保存成功后才写入凭据，账号被移除或改用不使用密码的登录方式时清除引用并删除凭据。
    /// </summary>
    public string? CredentialReference { get; set; }
    /// <summary>是否表示当前登录账号。</summary>
    [JsonIgnore] public bool IsDefault => Id == DefaultId;
    /// <summary>建立免配置的当前账号。</summary>
    public static PuloniaGenshinAccountProfile CreateDefault() => new() { Id = DefaultId, Name = "默认账号（当前登录账号）" };
}
