# BetterGI quest pilot helpers

## Reconnecting a closed desktop host

Builds with `--desktopClone` can open and connect the RDP desktop directly without starting capture or a quest on the main desktop. Stage a `Host-Launcher.json` containing `version:1`, `desktopClone:true`, and a `sha256` object with the exact `BetterGI.exe` and `BetterGI.dll` hashes. Then run `powershell -File tools/quest-pilot/resume-rdp-host.ps1 -AppDirectory artifacts/release-r11/BetterGI-English-win-x64` from Windows session 1. The launcher verifies the staged workspace path and hashes, refuses a second main-desktop host, and starts that exact executable. Windows elevation or an RDP authentication prompt may still require the user; the launcher does not enter credentials.

Stage the external-control opt-in marker, the pinned `ActOneRun` group and the current `ActOnePilot` package before launching the host. The launcher checks these before Desktop Clone can create its child; a child started without the marker cannot enable its endpoint until it restarts.

Closing the outer host can disconnect RDP while its BetterGI child and Genshin process remain alive. Check their PIDs, Windows session and controller status before restarting either. Windows can assign a new session number after logoff: discover the replacement child and explicitly pin that actual session in both clients. After reconnection, use the pilot's explicit `questStep` named `focusGame`, capture a fresh observation and verify the current state before continuing. A failed focus attempt sends no scripted game input.

## Persistent Act One controller (r9)

The ActOnePilot listener has no idle or total-runtime cutoff. It waits for explicit commands until stopped or the BetterGI host exits. Bounded mission deadlines and fresh-screen checks still apply. A stopped mission is not automatically retried, and an explicitly stopped listener does not automatically restart.

The r9 application includes an opt-in local named-pipe service for `status`, `startPilot`, `stopPilot`, and separately enabled `restartApp`. It remains available while the pilot script is stopped. It starts only `ActOneRun`, which must contain exactly one enabled JavaScript project named `ActOnePilot`; it stops only a verified task it owns. No arbitrary code, groups, keys, or shell commands are accepted by this endpoint. The pipe is restricted to the current Windows user and runs only in an RDP child instance. A new process nonce prevents commands targeting an old app instance from controlling a replacement.

1. Install the r9 application and current ActOnePilot package in a separate directory. Preserve the script-group settings and game configuration. Inside its directory, create `User/ExternalControl/enable-quest-control.json` containing `{"version":1,"enabled":true}`. Removing or disabling this marker prevents subsequent start/stop commands; restart the application to remove the endpoint itself.
2. Launch that application inside RDP with `--instance childsession`. Leave the outer Desktop Clone host running. Do not use `--startGroups`: the control service should start and own the pilot. The controller requires a session ID above 1 that BetterGI itself identifies as a remote-desktop child and 1920x1080 normalized game capture.
3. Use the exact child PID and explicitly pinned session for each command. For example, `python tools/quest-pilot/controller-control.py status --process-id <PID> --windows-session-id 6`. Substitute `startPilot` or `stopPilot` for `status` when intended. Start acknowledgment means dispatch accepted; poll status until a fresh `idle` heartbeat confirms readiness. Stop acknowledgment means cancellation requested; verify that ownership ends before starting again.
4. Set `BETTERGI_PILOT_APP_DIR` to the new application directory before using `act-one-command.py`, and pass `--expected-windows-session-id 6` using the currently verified session ID. The client checks the live process, RDP-child proof, fresh heartbeat, idle state, session and frame. A timeout never resends the request.

`controller-status.json` distinguishes starting, idle, running, stopped and faulted states; stale owned heartbeats are reported as unresponsive. Reports retain full history as JSONL while the frequently rewritten JSON index stays bounded. No timer renews or replaces the listener session.

The service remains available while the script is stopped. The on-demand recovery task below can launch the host when the application itself is absent. Neither the listener nor the task has a two-hour lifetime. Individual game missions and recovery requests remain bounded.

### On-demand RDP recovery

The tested portable build provides `installRecoveryLauncher`, `restartHost`, and `shutdownApp` through the same exact-PID/session/nonce endpoint. These require `allowAppRestart:true` and no active BetterGI task. They accept no executable, process target, paths, arguments, or script payloads.

1. Stop the owned pilot and verify that `serviceOwnsPilot` is false. Stage `Host-Launcher.json` in the app root with `version:1`, `desktopClone:true`, and `sha256` containing exactly the hashes of `BetterGI.exe` and `BetterGI.dll`. Invoke `controller-control.py installRecoveryLauncher --process-id <CHILD_PID> --windows-session-id <RDP_SESSION>`. The elevated child installs and reads back the fixed same-user task `BetterGI-Quest-RDP-Host`.
2. From the console session, run `powershell -NoProfile -File tools/quest-pilot/recover-rdp-host.ps1`. It validates the task, build and controller package, then dispatches its fixed `--desktopClone` action in session 1. This launches an absent host or activates the existing host; the host connects the desktop clone and launches BetterGI if its child is missing. A dispatch acknowledgment is not proof of readiness. Verify the live child endpoint before starting the pilot.
3. After staging a newer tested child and installing its recovery task, `controller-control.py restartHost --process-id <CHILD_PID> --windows-session-id <RDP_SESSION>` replaces the connected root with that task's build. It verifies the actual connected root's pipe identity, creation time, session and release path, terminates only the root, then dispatches the task. Graceful root disposal logs off the whole clone, so this explicit host handoff preserves the child and game by avoiding that disposal path. Verify all three processes and the new root connection before resuming.
4. `shutdownApp` exits only the pinned idle child after the response attempt. It leaves the host and game running and permits a missing-child recovery test. It is not a gameplay command.

The task is demand-only, runs as the current user with the highest interactive token, has no triggers and no execution time limit. Parallel activation lets an already-running host receive a new `--desktopClone` request. This is recovery on command, not a background crash watchdog. Authentication prompts, a locked desktop, a signed-out Windows account or disabled opt-in still require attention. No helper enters passwords or operates elevation prompts.

The development task deliberately trusts same-user writable local code, as `restartApp` does. Co-located hashes detect stale or mismatched releases; they do not authenticate a publisher. A same-user process that replaces the executable and its manifest can change the code subsequently run by this elevated task. This is not an isolation boundary against that user. To revoke it, delete the fixed task and disable the external-control marker.

### Switching application builds

`restartApp` requires `allowAppRestart:true` in the opt-in marker of both installations. It refuses to restart while a task is active; explicitly stop the pilot and verify completion first. Stage the tested application in a sibling `release-rN/BetterGI-English-win-x64` directory, including its config and pilot group. Write `User/ExternalControl/pending-restart.json` in the current app directory with `version:1`, the absolute `targetDirectory`, and the SHA256 values `exeSha256` and `dllSha256` for the new BetterGI.exe and BetterGI.dll. The CLI accepts no path or executable argument.

Invoke `controller-control.py restartApp --process-id <OLD_PID> --windows-session-id 5`. The existing elevated child launches the exact checked executable directly, with `--instance childsession --restart-from-pid <OLD_PID>`, then exits. The replacement waits for the old process before initializing; the outer Desktop Clone host stays running. A successful response confirms only that launch was dispatched. Discover the replacement PID, verify its pipe status, and explicitly start the pilot; no gameplay mission resumes automatically. If the response is lost, inspect both processes instead of replaying the command.

This opt-in trusts locally built code writable by the same Windows user. Hashes catch stale or mismatched binaries; they do not authenticate a publisher or protect against a malicious process running as that user. `allowAppRestart` is off by default. This is a local development deployment mechanism, not a signed software updater.

## Historical Bird's Eye View helpers

These files preserve source helpers from the supervised Bird's Eye View pilot. They are research artifacts for a narrowly controlled experiment, not a reusable or unattended automation package. They have input-capable entry points: `birds-eye-steer.py`, `birds-eye-follow.py`, `birds-eye-dialogue.py`, and `birds-eye-command.py` can send game input when explicitly run. `birds-eye-vision.py` is read-only. `VisionProbe` analyzes screenshots using BetterGI's existing assemblies.

Bird's Eye View was completed during a supervised run on 2026-10-10. The journal confirmed the transition to Unexpected Power, and the pilot stopped before its combat tutorial. The route was not recorded as a general route, and these scripts do not know how to safely handle arbitrary scenes, loading, combat, choices, or unexpected UI. A person must supervise the game and inspect each state.

## Existing pilot installation

By default, the helpers expect the existing local pilot installation at `artifacts/release-r8/BetterGI-English-win-x64`, including its `User/JsScript/OpeningQuestPilot` bridge, DLLs, and `VisionProbe.dll`. Install the live-tested `OpeningQuestPilot` source package into that r8 installation first; its RDP/session guards and `navigation.json` setup are part of the pilot. Pin the current Windows RDP child session ID explicitly on each helper invocation. These files do not recreate the bridge or guard package and are not turnkey on another machine.

Override the installation path with `BETTERGI_PILOT_APP_DIR`. The steering/follow helpers use `DOTNET_HOST_PATH` to locate the .NET host; absent that variable, they use the existing user-local .NET 8 path. The vision helper imports sibling Python files from this directory. `birds-eye-vision.py` requires NumPy and Pillow.

`VisionProbe.csproj` references `BetterGI.dll` and `OpenCvSharp.dll` from the default r8 installation. If using another installation, update those references for the build; `BETTERGI_PILOT_APP_DIR` does not change MSBuild reference paths.

## Safety and scope

Do not run input-capable helpers without the original supervised setup, an active operator, and a fresh visual check. Do not run them unattended or infer safety from a successful prior pilot. The bounded route and scene assumptions are specific to the completed Bird's Eye View pilot. Stop before Unexpected Power.
