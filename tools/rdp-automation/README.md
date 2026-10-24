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

Warm launches minimize an existing connected/connecting RDP window by default.
To retain a window you explicitly showed, invoke `start-approved.ps1 -Mode Game
-PreserveWindow` (or `-Mode Host -PreserveWindow`). The direct `start-host.ps1`
also accepts `-PreserveWindow`, and the Python `start` command accepts
`--preserve-window`. These options suppress the extra minimize during reuse;
a new or recovered connection still uses BetterGI's minimized automation startup.
The `show` command continues to leave the window visible until a later minimize
or default start request.

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

`rootReady:true` and `readinessScope:primary_control_endpoint` mean the primary control endpoint is verified. `rdpConnected` reports the observed RDP connection, without claiming that a child or game is ready. Use `start` and `start-game` below to await those stages; the Game wrapper reports `readinessScope:game_runtime` only after `game_ready` and `runtimeRunning:true`. After replacing only the child, select the primary's existing release explicitly when reusing that older primary.

The Python `start` command first checks the pinned primary and discovers its
authenticated child. It joins `connecting`/`launching_child` without replaying
that operation. A prior `child_launch_dispatched` state is a completed dispatch;
if its child is now missing, a new explicit invocation may send one recovery
request through the existing serialized server start. An unavailable, ambiguous,
or foreign child endpoint prevents that request. A lost acknowledgement is never
retried; only fresh active-start evidence or a verified appeared child permits
continued waiting. The result separates `childReady` (verified child endpoint)
from `gameReady` (completed game attachment), and records `childStartDispatched`.

Recovery keeps the primary and RDP session. It does not upgrade a warm host or
silently select a different child executable: the primary's existing launcher
uses its own package. In particular, an old r1 primary may start an r1 child that
lacks the corrected `rootProcessId` backlink. Such a child is reported as a legacy
identity limitation, not accepted as ready. Use the explicitly verified child
replacement workflow or a later planned primary upgrade; do not weaken the
identity check or close a live host automatically.

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

The required full solution verification always uses Debug. For an optimized runtime, pass `-PublishConfiguration Release`; omitting it preserves Debug publishing. The build manifest records both configurations, the runtime target, and binary hashes so latency results identify the actual package:

```powershell
& tools/rdp-automation/build-runtime.ps1 -PublishConfiguration Release
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

`start-agent` keeps `legacy-area-640x360-v1` as its default observation profile.
For an explicitly compatible P2P client, select the native-image Hamming profile:

```powershell
& $py tools/rdp-automation/rdp_control.py start-agent `
  --process-id 5678 --windows-session-id 3 `
  --observation-profile p2p-native-hamming-192-v1
```

This command remains observation-only unless `--enable-input` is also supplied.
Status exposes `agentObservationProfile` for the active or most recent run;
the CLI verifies the requested profile before reporting a listening stream.
Reusing a running stream requires both its input permission and profile to match.
Stop it explicitly before changing either option. Older servers that omit this
status field can confirm only the legacy profile, never the native Hamming path.

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

## Reset the fixed navigation start

`reset-navigation` runs the server's fixed `mondstadt-city-10` reset profile and
sets the requested camera yaw. It performs game input only in the authenticated
automated RDP child. Stop the model client and agent stream first; the runtime
must be ready and all automation tasks idle.

```powershell
& $py tools/rdp-automation/rdp_control.py reset-navigation `
  --process-id 5678 --windows-session-id 3 --yaw-degrees 0 --timeout 120
```

Yaw defaults to 0 degrees and must be finite, at least 0 and below 360. The client
submits one `startNavigationReset` request and pins its returned run ID as well
as the child PID, session and nonce. It returns the full server status only when
`navigationReset.state` is `completed`, task cleanup has finished, and the three
server-validated final position/yaw observations are present. The server owns
the fixed profile and numerical acceptance criteria; the CLI does not accept
arbitrary coordinates or paths. Failure, cancellation or a replaced run is an
error. A timeout does not restart the reset or imply that it was cancelled:
inspect `status` before another mutation. The existing `stopAutomationTasks`
control operation cancels owned automation work, including this reset.

Capable runtimes advertise `verificationDiagnosticsVersion: 1`. After a terminal
run and task cleanup, the client makes one read-only `navigationResetDiagnostics`
request pinned to that run ID and process identity. It returns up to 15 measured
verification poses with exact rejection reasons and spread/spacing metrics.
These are separate from `samples`, which remains exactly three verified poses
on success and empty on failure. Ordinary status omits the larger diagnostic
array and retains its 8 KiB response limit; only the explicit evidence response
may use 32 KiB. All requests remain limited to 8 KiB.

Failed or cancelled resets raise `NavigationResetError` in Python with the
authenticated terminal result in `.status`; CLI failure JSON includes the same
`status` object. If evidence retrieval fails or its run/instance changes, the
original terminal result is retained and the operation still reports an error.
Neither failure restarts the reset. Older runtimes without the capability keep
their existing behavior.

The fixed profile distinguishes waypoint ID 10's map icon
`(-876.1047, 2277.604)` from its expected spawn `(-867.6852, 2281.4954)`.
Verification requires the `City_102` local template at rank 0 with confidence
at least 0.99, and yaw confidence at least 0.2. The final three observations
must use distinct native capture sources, each within 3 map units and 3 degrees
of the target, with at most 1.5 map units of positional spread and 2 degrees of
yaw spread. WGC source metadata is required; the conservative freshness anchor
is the earlier of the reported source time and immutable first-acquisition time,
and its age must not exceed 500 ms. This does not establish actual game-render
age. The operation has a 75-second cooperative deadline; synchronous native work
and cleanup may finish after that deadline. Verified 2D position and yaw do not
establish camera pitch, elevation, an identical scene, HP, time of day, weather,
or encounter state.

## Run the fixed native navigation baseline

`run-navigation-baseline` runs `mondstadt-city-leg-1-v1` in the authenticated,
opted-in RDP child. Stop the policy client and agent stream and wait for all
tasks to finish first. Prepare the start separately with `reset-navigation`;
the baseline command never resets, teleports, retries movement, or accepts a
route file, coordinates, yaw target, or arbitrary inputs.

```powershell
& $py tools/rdp-automation/rdp_control.py run-navigation-baseline `
  --process-id 5678 --windows-session-id 3 --timeout 45
```

The fixed leg follows the first two coordinates of the shipped Mondstadt
crafting-bench route, from `(-867.7041015625, 2281.378173828125)` to
`(-874.3662109375, 2274.179931640625)`, about 9.808 map units. Its separately
named `native-fixed-leg-feedback-v1` controller uses unsprinted forward input
and horizontal camera corrections. It does not invoke the general path
executor's revive, popup handling, party switching, skills or escape routines.

The server requires a start within 1.5 map units, local `City_102` rank-0 map
matching with confidence at least 0.99, yaw confidence at least 0.2, and fresh
native WGC source metadata. Input authority expires at 150 ms using the earlier
of reported source time and immutable first-acquisition time; this is not proof
of actual game-render age. Forward input has a 100 ms renewable lease and a
nominal 25 ms release watchdog. Source/target loss, non-normal motion, corridor
violations, lease expiry or evidence failure ends the run. Scheduling and
blocking native calls prevent a hard real-time release guarantee. A normal
key-tip classification is negative hint evidence, not proof of ground contact.

Movement stops within 1.5 map units of the endpoint. After release, success
requires three distinct source observations within 2 map units of the endpoint,
at most 1.5 units of positional spread and 2 degrees of yaw spread, with adjacent
acquisitions at least 80 ms apart. The task has a 30-second cooperative deadline;
native work and cleanup can finish later. Position/yaw do not establish altitude,
camera pitch, an identical scene or encounter state.

The client requires `navigationBaseline.resultVersion: 1`, sends exactly one
`startNavigationBaseline`, and pins its new run ID, child PID/session/nonce and
game PID. After terminal state and task cleanup, it makes one read-only
`navigationBaselineResult` query using `navigationBaselineRunId`. Only that
response may use 32 KiB; requests and ordinary status retain their 8 KiB limits,
including compatibility with older primary hosts. An older child without this
capability is rejected before any start request.

The returned `navigationBaseline.result` contains the measured initial/final
poses, verification attempts, release outcome and evidence references/hashes.
Bulk evidence stays in the server-selected `User/NavigationBaselines/<runId>/`
directory: a bounded journal and at most two native images. It is labeled
`controller-intent-and-pose`, with `humanDemonstration`, `trainingEligible` and
`completeLowLevelDispatchTrace` all false. It does not establish physical game
acceptance or a complete native dispatch trace.

Failed/cancelled owner states remain failures even when a measured result says
`verified: true`, because cleanup can fail afterward. Python raises
`NavigationBaselineError` with the last verified status in `.status`, including
the full terminal result when retrieval succeeds; CLI error JSON retains the
same object under `status`. A failed result query retains the compact terminal
status. A timeout neither cancels nor restarts work: inspect status before any
new mutation. The existing `stopAutomationTasks` operation can explicitly cancel
owned work. A lost start acknowledgement has an unknown outcome and is never
replayed or inferred from a different run.

## Validation

```powershell
& $py -m unittest discover -s tools/rdp-automation -p 'test_*.py' -v
```

Tests cover framed protocol/peer identity, nonce changes, bounded output, single-use jobs, RDP/elevation rejection, native suspended-process Job Object handling, configuration staging and hash/lifecycle replacement readiness. They use harmless Python processes and synthetic files; they do not send game input or interact with GUI windows. Native Windows security/file primitives may require running the test command outside a restrictive sandbox. Live RDP authentication, game attachment and replacement remain separate end-to-end checks.
