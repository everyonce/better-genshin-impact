using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Simulator.Extensions;
using Vanara.PInvoke;

namespace BetterGenshinImpact.UnitTest.GameTaskTests.AutoFishingTests
{
    /// <summary>
    /// 不产生任何实际输入的通道，所有操作直接返回自身
    /// </summary>
    internal class FakeInputChannel : IInputBackend, IInputChannel, IKeyboardInput, IMouseInput
    {
        /// <summary>Report the expected channel kind without constructing a Win32 dispatcher.</summary>
        public InputBackendKind Kind => InputBackendKind.Win32;

        /// <summary>DesktopRegion obtains its foreground mouse here during screenshot tests.</summary>
        public IInputChannel Foreground => this;

        /// <summary>Background commands also stay inside the test double.</summary>
        public IInputChannel Background => this;

        /// <summary>Counts simulated region clicks without sending input.</summary>
        public int LeftButtonDownCount { get; private set; }

        /// <summary>The fake backend owns no device resources.</summary>
        public void Dispose() { }

        public IKeyboardInput Keyboard => this;

        public IMouseInput Mouse => this;

        public IInputChannel SimulateAction(GIActions action, KeyType type = KeyType.KeyPress) => this;

        public bool IsKeyDown(User32.VK key) => false;

        IInputChannel IInputChannel.Sleep(int ms) => this;

        public void ReleaseAll()
        {
        }

        public IKeyboardInput KeyDown(User32.VK key) => this;

        public IKeyboardInput KeyUp(User32.VK key) => this;

        public IKeyboardInput KeyPress(User32.VK key) => this;

        IKeyboardInput IKeyboardInput.Sleep(int ms) => this;

        public IMouseInput MoveMouseBy(int dx, int dy) => this;

        public IMouseInput MoveMouseTo(double absX, double absY) => this;

        public IMouseInput LeftButtonDown()
        {
            LeftButtonDownCount++;
            return this;
        }

        public IMouseInput LeftButtonUp() => this;

        public IMouseInput LeftButtonClick() => this;

        public IMouseInput RightButtonDown() => this;

        public IMouseInput RightButtonUp() => this;

        public IMouseInput RightButtonClick() => this;

        public IMouseInput MiddleButtonDown() => this;

        public IMouseInput MiddleButtonUp() => this;

        public IMouseInput MiddleButtonClick() => this;

        public IMouseInput XButtonDown(int buttonId) => this;

        public IMouseInput XButtonUp(int buttonId) => this;

        public IMouseInput XButtonClick(int buttonId) => this;

        public IMouseInput VerticalScroll(int scrollAmountInClicks) => this;

        IMouseInput IMouseInput.Sleep(int ms) => this;
    }
}
