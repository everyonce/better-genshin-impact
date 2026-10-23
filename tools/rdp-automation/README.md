# BetterGI RDP automation

This local Python 3.11 CLI controls explicitly enabled BetterGI instances. The primary instance hosts the separate RDP window; capture, game automation and ordinary commands run in the child session. It uses the existing same-user named pipe, verifies its Windows PID/session/owner, and pins mutations to a fresh instance nonce. It contains no credential handling or game/dependency installation.

## Approve stable launch shortcuts once

The optional approved launcher uses one fixed Windows scheduled task, `\BetterGI Automation\StartHost`. Its action is an administrator-owned helper in `C:\Program Files\BetterGI Automation`, running with the current user's `InteractiveToken` and highest available privilege. It accepts no caller arguments, stores no password, and launches only the newest verified numbered BetterGI package from this workspace with `--automation --desktopClone`. It never invokes workspace PowerShell/Python scripts while elevated. Protected helper/config/task ownership belongs to Administrators; the ordinary user receives read/execute permission.

Approving this workflow means trusting future BetterGI builds in this workspace to run elevated. Local binary hashes detect mismatched or damaged files; they do not independently authenticate the author of a future build. Changes to the protected helper itself require another explicit administrator installation. This is intended for this trusted development checkout.

Prepare/review the exact plan and generate the two local shortcuts without registering a task or launching an application:

```powershell
& tools/rdp-automation/register-approved-launchers.ps1
& tools/rdp-automation/register-approved-launchers.ps1 -PrepareShortcuts
```

Only after reviewing that plan, run the following from an elevated **64-bit Windows PowerShell** under the same account:

```powershell
& 'D:/work/genshin-auto/tools/rdp-automation/register-approved-launchers.ps1' -Install
```

This one-time operation copies the protected helpers, applies administrator ownership, and registers the fixed task. It does not run the task or launch BetterGI/Genshin. Windows' normal administrator approval is required for registration. No UAC settings, authentication settings, or passwords are changed. Registration and standard-token task invocation require separate live verification after approval; the automated tests validate plans and target selection without registering anything.

`-Install` records bounded success/failure details in `artifacts/rdp-automation/registration-result.json`, including when launched with a hidden window. The default review plan remains read-only. Close the registration administrator shell afterward: ordinary launchers explicitly reject elevated/high-integrity tokens before importing workspace helpers. Task invocation is pinned to the verified local console session using Windows [RunEx session binding](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-iregisteredtask-runex), so a simultaneous RDP logon cannot redirect the host launch.

The generated files in `tools/rdp-automation/shortcuts` are stable across release numbers:

- **Start BetterGI.lnk** reuses a currently running, verified numbered automation host, or requests the newest verified package through the approved task.
- **Start Genshin in RDP.lnk** first ensures that host exists, connects/awaits its RDP child, then calls `start-game` for that exact child. It never launches a game executable in the local desktop session. It uses BetterGI's configured game path and preserves an already running game.

The shortcuts run an ordinary-token wrapper. Existing standard-token child command execution is unchanged. Missing Windows sign-in, a legacy incompatible host, unavailable RDP, or a game-launch failure is reported; the scripts do not terminate unrelated instances. Hidden shortcut results are saved to `artifacts/rdp-automation/last-shortcut-result.json`; the protected task's dispatch result is `C:\Program Files\BetterGI Automation\last-host-result.json`. For immediate JSON output, run `start-approved.ps1 -Mode Host` or `start-approved.ps1 -Mode Game` directly. `start-host.ps1 -UseApprovedTask` also exposes the fixed task path.

## Start the verified primary host

Run `start-host.ps1` from the local desktop session. By default it selects the highest numbered `artifacts/release-rN/BetterGI-English-win-x64` package that passes validation. It checks the build manifest's exact target directory and both BetterGI binary SHA256 hashes, the portable .NET10 win-x64 runtime, and rejects redirected paths. Its JSON result lists any incomplete or invalid newer packages it skipped. An explicitly selected invalid package fails without falling back.

```powershell
# File validation only: no process discovery, application launch, or session changes.
& tools/rdp-automation/start-host.ps1 -ValidateOnly

# Launch or reuse this exact verified release.
& tools/rdp-automation/start-host.ps1 `
  -TargetDirectory 'D:/work/genshin-auto/artifacts/release-r1/BetterGI-English-win-x64' `
  -PythonExe 'C:/Programs/Python/Python311/python.exe'
```

The launcher requests hidden startup with `--automation --desktopClone`; BetterGI keeps its RDP window minimized. Its readiness deadline is `-TimeoutSeconds` (45 by default, plus a final bounded CLI request). It discovers the unique new primary with the matching Windows session, automation opt-in, nonce, package directory and assembly hash through the existing verified control CLI. BetterGI may elevate itself into a different process; an exited loader is not treated as a failed host, and the returned `root.processId` is the verified active PID. A matching running primary is reused. Existing legacy, incompatible, ambiguous or unavailable hosts are reported instead of terminated. Windows elevation/sign-in remain normal user-managed steps; the script does not install components or alter credentials.

`rootReady:true` means the primary control endpoint is verified. RDP connection and game readiness are separate states in the returned `root` status; use `start` and `start-game` below to await them. Reusing a host does not replay a pending connection. After replacing only the child, select the primary's existing release explicitly when reusing that older primary.

Start the packaged primary BetterGI with `--automation`. This enables the lifecycle endpoint. The root `start` command connects the RDP child and waits for that child's endpoint. Authentication and any first-run consent remain in the RDP UI; a timed-out request is not replayed automatically.

Starting the primary with `BetterGI.exe --automation --desktopClone` also requests the connection automatically, minimizes its RDP window, and launches the child with `--automation start`. Automation mode suppresses informational welcome/update/feed/banner UI and primary OCR preheating; game-start failures are exposed through structured status. Windows sign-in and authentication remain user-managed.

Automation sets the persistent per-user value `HKCU\Software\Microsoft\Terminal Server Client\RemoteDesktop_SuppressWhenMinimized` to `2` to keep RDP rendering while minimized. Actual ActiveX capture while minimized still needs live validation. `show` disables automatic minimization until a subsequent `minimize` or `start` request.

```powershell
$py = 'C:/Programs/Python/Python311/python.exe'
& $py tools/rdp-automation/rdp_control.py discover
& $py tools/rdp-automation/rdp_control.py status --process-id 1234 --windows-session-id 2
& $py tools/rdp-automation/rdp_control.py start --process-id 1234 --windows-session-id 2 --timeout 120
& $py tools/rdp-automation/rdp_control.py minimize --process-id 1234 --windows-session-id 2
& $py tools/rdp-automation/rdp_control.py show --process-id 1234 --windows-session-id 2
```

Use the IDs returned by `discover`; the numbers above are placeholders. Omitting both IDs selects the single enabled primary, or the single enabled child for child-only commands. Ambiguity requires explicit IDs. A numeric session ID never substitutes for the actual RDP checks.

`cancel-start` cancels the primary's pending child connection. `start-game` targets the discovered child and waits for its guarded game runtime to attach or start:

```powershell
& $py tools/rdp-automation/rdp_control.py start-game --process-id 5678 --windows-session-id 3 --timeout 90
```

Root status reports `childConnectedState` as 0 (disconnected), 1 (connected), or 2 (connecting). `automationState` and `automationError` describe lifecycle progress. `runtimeRunning` reports the child game runtime; `taskRunning` reports active automation work. `start` verifies the RDP connection and child endpoint, while `start-game` verifies the game runtime.

## Run an ordinary command in the RDP session

`exec` asks the primary to launch the fixed `child_runner.py` through an interactive-session scheduled task at the lowest run level. The helper uses the selected interpreter's `pythonw.exe`, preventing its initial console from stealing game focus; a missing windowless interpreter is an error. Before executing the requested command, the runner checks its actual process session, WTS RDP protocol, token elevation and integrity. Console, wrong-session and elevated execution are rejected. Arguments are literal strings; commands require an absolute `.exe` path and are passed with `shell=False`.

```powershell
& $py tools/rdp-automation/rdp_control.py exec `
  --process-id 1234 --windows-session-id 2 `
  --work-dir 'D:/work/genshin-auto' --timeout 30 -- `
  'C:/Programs/Python/Python311/python.exe' -c 'import os; print(os.getpid())'
```

The runner creates the command suspended, assigns it to a Windows Job Object, then resumes it. Closing that job ends its remaining descendants. Timeout, failure and normal completion therefore apply to the owned command tree. It does not terminate BetterGI, the RDP host, or an existing game process.

Each invocation has a unique, single-use job file under `artifacts/rdp-automation/jobs`, an exclusive `.claimed` record, and an atomically published result. Results include the observed Windows session, token properties, exit status, elapsed time, and bounded stdout/stderr. Output retention defaults to 256 KiB per stream; excess output is drained and counted. `--output-limit` allows 1 KiB–1 MiB. `--timeout` allows 1–3600 seconds. Job/result files remain available for diagnosis. Terminal interruption does not cancel an already dispatched command; its finite runner timeout still applies.

Use `--python` to select the Python installation that runs the helper; the client selects its windowless sibling. The executable after `--` may be a different interpreter, such as the installed CUDA environment:

```powershell
& $py tools/rdp-automation/rdp_control.py exec --timeout 30 -- `
  'D:/work/genshin-auto/artifacts/agent/envs/gamescaling/Scripts/python.exe' `
  -c 'import torch; print(torch.cuda.is_available())'
```

## Build, stage configuration, and replace the child

`build-runtime.ps1` builds and publishes a self-contained .NET10 Windows x64 package in a new numbered release directory and records its hashes. It leaves existing installations intact. Run it from the repository root; see its parameter help for available settings:

```powershell
Get-Help tools/rdp-automation/build-runtime.ps1 -Detailed
& tools/rdp-automation/build-runtime.ps1
```

Copy the current local settings separately into the new package:

```powershell
& $py tools/rdp-automation/rdp_control.py stage-config `
  --source-directory 'D:/work/genshin-auto/artifacts/release-r1/BetterGI-English-win-x64' `
  --target-directory 'D:/work/genshin-auto/artifacts/release-r2/BetterGI-English-win-x64'
```

This copies `User/config.json`, the existing external-control marker, and missing custom definitions in ScriptGroup, AutoFight, AutoGeniusInvokation and AutoPathing. It preserves files already shipped at those profile paths, skips JS/I18n/default assets and recorded data, and reports copied paths without printing settings. A different main config or marker already in the target causes a failure so an existing installation is not silently overwritten. `configuration-staging.json` records the result.

```powershell
& $py tools/rdp-automation/rdp_control.py hot-replace `
  --process-id 5678 --windows-session-id 3 --timeout 120 `
  --target-directory 'D:/work/genshin-auto/artifacts/release-r2/BetterGI-English-win-x64'
```

Hot replacement requires a different sibling `release-rN/BetterGI-English-win-x64` directory. It first validates the portable .NET10 package, including the .NETCore, WindowsDesktop and AspNetCore frameworks, and hashes BetterGI.exe/BetterGI.dll. This explicit command provisions `enabled:true` and `allowAppRestart:true` in both installations' `User/ExternalControl/enable-quest-control.json`, preserving unrelated marker fields. `--automation` alone does not grant the older restart capability.

Preflight also requires exactly one authenticated automated primary connected to the child session and pins its PID/nonce. An advertised old root PID must match; only a missing legacy root field uses this verified fallback. Missing, ambiguous or disconnected roots fail before any tasks are stopped.

It then stops child automation, waits for idle, writes the hash-pinned restart manifest and requests one replacement. Success requires a new child PID and nonce in the same RDP session, the same connected registered root, the selected directory and assembly hash, and a running game runtime with no active automation task. The replacement must advertise the pinned positive root PID. A failed reattachment is reported as failure. The primary RDP host and existing game are retained; the replacement starts with `--automation start` to reattach. Automation tasks are left stopped until explicitly restarted.

Once the game runtime is ready, the [headless agent bridge commands](../../Docs/design/agent-stream.md#headless-launch) start or stop the capture/model connection without replacing the game. Input remains opt-in on both ends.

To change an unusable capture backend without closing Genshin, stop any active agent
task and select an existing backend explicitly:

```powershell
& $py tools/rdp-automation/rdp_control.py stop-agent --process-id 5678 --windows-session-id 3
& $py tools/rdp-automation/rdp_control.py set-capture-mode `
  --process-id 5678 --windows-session-id 3 --mode WindowsGraphicsCapture
```

The command requires an idle automated RDP child, reserves its task ownership,
detaches capture, saves the selected mode, and reattaches the same game. It waits
for `game_ready` and verifies `captureMode` in status. Capture readiness still
requires inspecting the resulting images; an attached runtime alone does not
establish usable game pixels. `WindowsGraphicsCaptureV2` is an explicit fallback
if the original Windows Graphics Capture backend cannot supply frames.

An I/O timeout can leave a mutation's outcome unknown. Query `discover`/`status` and inspect the existing job/result before sending another mutation; the client does not replay uncertain requests.

## Validation

```powershell
& $py -m unittest discover -s tools/rdp-automation -p 'test_*.py' -v
```

Tests cover framed protocol/peer identity, nonce changes, bounded output, single-use jobs, RDP/elevation rejection, native suspended-process Job Object handling, configuration staging and hash/lifecycle replacement readiness. They use harmless Python processes and synthetic files; they do not send game input or interact with GUI windows. Native Windows security/file primitives may require running the test command outside a restrictive sandbox. Live RDP authentication, game attachment and replacement remain separate end-to-end checks.
