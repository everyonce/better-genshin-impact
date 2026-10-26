using BetterGenshinImpact.GameTask.Common.Resin;
using BetterGenshinImpact.ViewModel.Resin;

namespace BetterGenshinImpact.UnitTest.ViewModelTests.ResinTests;

/// <summary>草稿、隐藏值、能力限制与异步确认测试，不创建 WPF 窗口。</summary>
public sealed class ResinEditorViewModelTests
{
    /// <summary>四种能力与三种方式的输入，包括不支持和隐藏字段，打开后均保持原值且不提示。</summary>
    [Fact]
    public void Open_PreservesAllValuesAndDoesNotConfirm()
    {
        foreach (var capability in new[] { ResinCapabilities.Domain, ResinCapabilities.StygianOnslaught, ResinCapabilities.LeyLineOutcrop, ResinCapabilities.Boss })
        foreach (var mode in Enum.GetValues<ResinUsageMode>())
        {
            var usage = capability.Defaults;
            usage.Mode = mode;
            usage.RunCount = 17;
            usage.Counts = new() { Condensed = 2, Original = 4, Transient = 3, Fragile = 1 };
            usage.Allowed.Transient = true;
            var calls = 0;
            var vm = new ResinUsageEditorViewModel("测试任务", capability, usage, _ => { calls++; return Task.FromResult(true); });
            Assert.Equal(usage, vm.BuildValue());
            Assert.Equal(0, calls);
            Assert.Equal("Resin use · 测试任务", vm.Title);
            Assert.Equal(ResinKinds.InOrder, vm.Kinds.Select(row => row.Kind));
            vm.Kinds[0].Count++;
            Assert.Equal(2, usage.Counts.Condensed);
        }
    }

    /// <summary>模式切换仅改变可见性与说明，开关、总次数、分类次数和档位均保留。</summary>
    [Fact]
    public void Modes_PreserveHiddenValuesAndUpdateDescriptions()
    {
        var usage = new ResinUsage { Mode = ResinUsageMode.RunCount, RunCount = 7, Counts = new() { Condensed = 2, Original = 4 } };
        var vm = Create(usage);
        Assert.True(vm.ShowRunCount);
        vm.IsPerTypeMode = true;
        Assert.False(vm.ShowRunCount);
        Assert.Equal("Reward claims by Resin type", vm.KindsHeader);
        Assert.Equal("0 disables this Resin type; move to the next type when one runs short", vm.KindsDescription);
        Assert.All(vm.Kinds, row => { Assert.True(row.ShowCount); Assert.False(row.ShowToggle); });
        Assert.Equal("Use after the Condensed Resin claims are complete", vm.Kinds[1].Description);
        vm.Kinds[0].Count = 3;
        vm.SelectedTier = vm.TierChoices.Single(choice => choice.Tier == OriginalResinTier.Only20);
        vm.IsExhaustMode = true;
        Assert.All(vm.Kinds, row => { Assert.False(row.ShowCount); Assert.True(row.ShowToggle); });
        Assert.EndsWith(", until exhausted", vm.Kinds[2].Description);
        Assert.Equal("Allowed Resin", vm.KindsHeader);
        Assert.Equal("Use in order from top to bottom", vm.KindsDescription);
        vm.IsRunCountMode = true;
        Assert.Equal(7, vm.RunCount);
        Assert.Equal(3, vm.BuildValue().Counts.Condensed);
        Assert.Equal(OriginalResinTier.Only20, vm.BuildValue().OriginalTier);
        Assert.True(vm.BuildValue().Allowed.Original);
    }

    /// <summary>Assert explicit English presentation of task validation; unrelated hidden fields do not participate.</summary>
    [Theory]
    [InlineData(ResinUsageMode.PerType, "No count has been entered")]
    [InlineData(ResinUsageMode.Exhaust, "No Resin type has been selected")]
    [InlineData(ResinUsageMode.RunCount, "No count has been entered")]
    public void Validation_DisablesConfirmAndShowsSharedMessage(ResinUsageMode mode, string expected)
    {
        var usage = new ResinUsage { Mode = mode, RunCount = 0 };
        if (mode == ResinUsageMode.Exhaust) usage.Allowed = new();
        var vm = Create(usage);
        Assert.False(vm.CanConfirm);
        Assert.Equal(expected, vm.ValidationMessage);
        Assert.Equal(expected, vm.Summary);
    }

    /// <summary>首领只显示一个不可编辑档位，原粹锁定，浓缩和分别指定显示专属原因。</summary>
    [Fact]
    public void Boss_LocksOriginalAndDisablesUnsupportedOptions()
    {
        var vm = new ResinUsageEditorViewModel("自动首领讨伐", ResinCapabilities.Boss, ResinCapabilities.Boss.Defaults, _ => Task.FromResult(true));
        Assert.True(vm.CanConfirm);
        Assert.False(vm.IsPerTypeModeEnabled);
        Assert.Equal("Boss challenges support reward claim counts only", vm.PerTypeModeDescription);
        Assert.False(vm.IsTierEditable);
        Assert.Single(vm.TierChoices);
        Assert.Equal("Boss rewards always use 40 Original Resin", vm.TierDescription);
        Assert.False(vm.Kinds[0].IsEditable);
        Assert.Equal("Boss challenges do not currently support Condensed Resin", vm.Kinds[0].Description);
        Assert.True(vm.Kinds[1].IsAllowed);
        Assert.False(vm.Kinds[1].IsEditable);
        vm.Kinds[1].IsAllowed = false;
        Assert.True(vm.Kinds[1].IsAllowed);
        Assert.Equal("Boss rewards always consume 40 Original Resin", vm.Kinds[1].Description);
        Assert.Equal("Replenish Original Resin before combat when it is below 40", vm.Kinds[2].Description);
    }

    /// <summary>耗尽开启补充树脂先显示开启，异步否决后回退一次；直接与战前补充正文不同。</summary>
    [Theory]
    [InlineData(false, ResinKind.Transient)]
    [InlineData(false, ResinKind.Fragile)]
    [InlineData(true, ResinKind.Transient)]
    [InlineData(true, ResinKind.Fragile)]
    public async Task Exhaust_EnableSupplement_ConfirmsAndRestoresOnNo(bool boss, ResinKind kind)
    {
        var capability = boss ? ResinCapabilities.Boss : ResinCapabilities.Domain;
        var response = new TaskCompletionSource<bool>();
        var requests = new List<ResinConfirmation>();
        var vm = new ResinUsageEditorViewModel("测试", capability, capability.Defaults, request => { requests.Add(request); return response.Task; });
        var row = vm.Kinds.Single(row => row.Kind == kind);
        row.IsAllowed = true;
        Assert.True(row.IsAllowed);
        Assert.False(vm.CanConfirm);
        var name = kind == ResinKind.Transient ? "Transient Resin" : "Fragile Resin";
        var request = Assert.Single(requests);
        Assert.Equal("Use " + name, request.Title);
        Assert.Equal(boss ? $"When running until Resin is exhausted, {name} will be used to replenish Original Resin whenever it falls below 40, until none remains.\nEnable this?"
            : $"When running until Resin is exhausted, {name} will be used after Condensed and Original Resin run short, until none remains.\nEnable this?", request.Message);
        response.SetResult(false);
        await vm.PendingConfirmation;
        Assert.False(row.IsAllowed);
        Assert.True(vm.CanConfirm);
        Assert.Single(requests);
    }

    /// <summary>切入耗尽只确认一次，否决关闭补充开关但保留耗尽方式。</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SwitchToExhaust_ConfirmsBothEnabledKinds(bool accepted)
    {
        var usage = new ResinUsage { Mode = ResinUsageMode.RunCount, Allowed = new() { Original = true, Transient = true, Fragile = true } };
        var requests = new List<ResinConfirmation>();
        var vm = new ResinUsageEditorViewModel("测试", ResinCapabilities.Domain, usage, request => { requests.Add(request); return Task.FromResult(accepted); });
        Assert.Empty(requests);
        vm.Mode = ResinUsageMode.Exhaust;
        await vm.PendingConfirmation;
        var request = Assert.Single(requests);
        Assert.Equal("Run until Resin is exhausted", request.Title);
        Assert.Equal("Transient Resin, Fragile Resin is enabled. Running until Resin is exhausted will keep using it until none remains.\nContinue?", request.Message);
        Assert.Equal(ResinUsageMode.Exhaust, vm.Mode);
        Assert.Equal(accepted, vm.Kinds[2].IsAllowed);
        Assert.Equal(accepted, vm.Kinds[3].IsAllowed);
    }

    /// <summary>其他方式不提示，初始化已有的开启状态也不提示。</summary>
    [Theory]
    [InlineData(ResinUsageMode.RunCount)]
    [InlineData(ResinUsageMode.PerType)]
    [InlineData(ResinUsageMode.Exhaust)]
    public async Task Confirmations_DoNotRunDuringInitializationOrBoundedModes(ResinUsageMode mode)
    {
        var usage = new ResinUsage { Mode = mode };
        usage.Allowed.Transient = true;
        var calls = 0;
        var vm = new ResinUsageEditorViewModel("测试", ResinCapabilities.Domain, usage, _ => { calls++; return Task.FromResult(true); });
        Assert.Equal(0, calls);
        if (mode != ResinUsageMode.Exhaust) vm.Kinds[3].IsAllowed = true;
        await vm.PendingConfirmation;
        Assert.Equal(0, calls);
    }

    /// <summary>旧确认不会覆盖用户后续切换，新确认串行显示，否决恢复不会触发第三次确认。</summary>
    [Fact]
    public async Task Confirmation_RejectsStaleResultAndSuppressesReentry()
    {
        var firstResponse = new TaskCompletionSource<bool>();
        var secondResponse = new TaskCompletionSource<bool>();
        var calls = 0;
        var vm = new ResinUsageEditorViewModel("测试", ResinCapabilities.Domain, new(), _ => ++calls == 1 ? firstResponse.Task : secondResponse.Task);
        vm.Kinds[2].IsAllowed = true;
        var first = vm.PendingConfirmation;
        vm.Mode = ResinUsageMode.RunCount;
        vm.Mode = ResinUsageMode.Exhaust;
        Assert.Equal(1, calls);
        firstResponse.SetResult(false);
        await first;
        Assert.True(vm.Kinds[2].IsAllowed);
        secondResponse.SetResult(false);
        await vm.PendingConfirmation;
        Assert.False(vm.Kinds[2].IsAllowed);
        Assert.Equal(2, calls);
    }

    /// <summary>合成旧值归一化为默认，首次保留预填 40，隐藏数量与边界校验保持。</summary>
    [Theory]
    [InlineData(-1)]
    [InlineData(0)]
    public void Craft_DefaultPrefills40AndRetainsHiddenAmount(int legacy)
    {
        var vm = new CraftResinEditorViewModel(legacy);
        Assert.True(vm.IsDefaultMode);
        Assert.Equal(0, vm.BuildValue());
        Assert.Equal("Craft the default quantity", vm.Summary);
        vm.KeepResin = true;
        Assert.Equal(40, vm.KeepAmount);
        Assert.Equal("Keep 40 Original Resin after crafting", vm.Summary);
        vm.KeepAmount = 73;
        vm.IsDefaultMode = true;
        Assert.Equal(0, vm.BuildValue());
        vm.KeepResin = true;
        Assert.Equal(73, vm.BuildValue());
        vm.KeepAmount = 1000;
        Assert.False(vm.CanConfirm);
        Assert.Equal("The amount to keep must be between 1 and 999.", vm.ValidationMessage);
        vm.KeepAmount = 999;
        Assert.True(vm.CanConfirm);
    }

    /// <summary>创建无需交互确认的秘境编辑器。</summary>
    private static ResinUsageEditorViewModel Create(ResinUsage usage)
        => new("自动秘境", ResinCapabilities.Domain, usage, _ => Task.FromResult(true));
}
