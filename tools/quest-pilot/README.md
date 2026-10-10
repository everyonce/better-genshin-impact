# BetterGI quest pilot helpers

These files preserve source helpers from the supervised Bird's Eye View pilot. They are research artifacts for a narrowly controlled experiment, not a reusable or unattended automation package. They have input-capable entry points: `birds-eye-steer.py`, `birds-eye-follow.py`, `birds-eye-dialogue.py`, and `birds-eye-command.py` can send game input when explicitly run. `birds-eye-vision.py` is read-only. `VisionProbe` analyzes screenshots using BetterGI's existing assemblies.

Bird's Eye View was completed during a supervised run on 2026-10-10. The journal confirmed the transition to Unexpected Power, and the pilot stopped before its combat tutorial. The route was not recorded as a general route, and these scripts do not know how to safely handle arbitrary scenes, loading, combat, choices, or unexpected UI. A person must supervise the game and inspect each state.

## Existing pilot installation

By default, the helpers expect the existing local pilot installation at `artifacts/release-r8/BetterGI-English-win-x64`, including its `User/JsScript/OpeningQuestPilot` bridge, DLLs, and `VisionProbe.dll`. Install the live-tested `OpeningQuestPilot` source package into that r8 installation first; its RDP/session guards and `navigation.json` setup are part of the pilot. The helper also requires the active Windows RDP session ID 5. These files do not recreate the bridge or guard package and are not turnkey on another machine.

Override the installation path with `BETTERGI_PILOT_APP_DIR`. The steering/follow helpers use `DOTNET_HOST_PATH` to locate the .NET host; absent that variable, they use the existing user-local .NET 8 path. The vision helper imports sibling Python files from this directory. `birds-eye-vision.py` requires NumPy and Pillow.

`VisionProbe.csproj` references `BetterGI.dll` and `OpenCvSharp.dll` from the default r8 installation. If using another installation, update those references for the build; `BETTERGI_PILOT_APP_DIR` does not change MSBuild reference paths.

## Safety and scope

Do not run input-capable helpers without the original supervised setup, an active operator, and a fresh visual check. Do not run them unattended or infer safety from a successful prior pilot. The bounded route and scene assumptions are specific to the completed Bird's Eye View pilot. Stop before Unexpected Power.
