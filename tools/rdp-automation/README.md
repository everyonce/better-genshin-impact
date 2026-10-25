# BetterGI RDP automation

See the [current agent status](../../Docs/research/BetterGI-Agent-Status.md) for the deployed build, pending repair and measured model latency.

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

- **Start BetterGI.lnk** preserves a verified running primary (including an older host), or requests one through the approved task, then ensures the separately selected latest verified BetterGI child in RDP.
- **Start Genshin in RDP.lnk** ensures that same selected child, then awaits its game runtime. An already-ready matching child is reused without a game-start mutation, including while its automation is active. Game startup uses BetterGI's configured path in RDP and preserves an already running game.

Both links pin the selected directory and executable/assembly hashes for the whole
invocation. A missing child can be started once through a compatible existing primary. An
old child is replaced only when explicit task/lifecycle evidence says it is idle
and it advertises a supported `idleRestartVersion`. Both versions nonblockingly reserve
the task semaphore and runtime-start admission through shutdown, and binds the
manifest to the request's selected directory and both hashes. A competing manifest
cannot redirect the request to another release. The shortcut never stops its tasks.
After one acknowledged replacement, temporary unavailable endpoints or degraded
replacement UI status remain unready within the original deadline. Every unavailable
endpoint must clear, the retiring child must disappear, and the unique new child
must retain its authenticated process epoch, root/session, selected directory and
assembly hash before success. Known conflicting identities remain errors. A lost
restart acknowledgement still fails with an unknown outcome; it is never replayed.
`replacementEvidence` records the phase, request attempt/acknowledgement, bounded
poll count and latest pending reason on success or failure. Hidden shortcut failures
retain separate stdout/stderr, exit code, timeout and parsed control error under
`controlFailure`; successful control calls retain their streams in `controlEvidence`.
The ordinary-token helper uses no shell, preserves Windows argv quoting, and avoids
Windows PowerShell 5's terminating native-stderr behavior. A helper timeout stops
only its own CLI process and does not cancel or retry the server-side operation.
The child restart retains the primary, RDP
session and game. Busy children, unavailable/ambiguous identities, changed hashes
or uncertain responses fail visibly without replaying start/restart requests.
Existing target settings are retained; a target without settings uses the bounded
configuration-staging path before restart. Newly shipped scripts are preserved.

**Host-mode behavior changed:** the approved BetterGI link now reports
`readinessScope:selected_child_control_endpoint`, with separate `gameReady`,
rather than stopping at primary-only readiness. This makes the stable link select
the usable current child even when the retained old host bootstraps its own old
package. The lower-level `start-host.ps1` remains primary-only. The approved Game
link reports `game_runtime` only after `game_ready` and `runtimeRunning:true`.
Host replacement requires capability **2** and sends version-two
`startupMode:controlEndpoint`: the new child retains `--automation` but receives
no `start` action. It can therefore report its verified control endpoint with
`runtimeRunning:false` and `gameReady:false`, without launching or requiring a
game. Game replacement uses explicit `startupMode:gameRuntime` on capability 2;
capability 1 retains its original game-start contract. Startup intent is part of
the authenticated request and its replay fingerprint, alongside the target pins.
An r19/capability-1 child cannot honor endpoint-only replacement, so Host refuses
that upgrade before staging settings or a manifest. It never silently downgrades
to Game behavior; use an intentional Game upgrade or controlled direct
`hot-replace` first. Direct `hot-replace` keeps its existing stop/drain/game-start
default.

A current automated primary advertises `childStartupIntentVersion:1`. Its cold
`--automation --desktopClone` activation has no start action and bootstraps only
the child's control endpoint; an explicit `start` action selects the game runtime.
The authenticated `startChildSession` command optionally accepts exactly
`childStartupMode:controlEndpoint` or `gameRuntime`. Intent is fingerprinted and
captured for both the direct continuation and the login callback. They share one
launch outcome, recheck generation/cancellation under the launch semaphore, and
do not replay an uncertain dispatch. Omitted requests and manual UI startup retain
their legacy behavior.

Host refuses a missing-child mutation on an older primary before dispatch. It
also refuses to join an active game/unknown startup intent. Game may join an
active endpoint bootstrap, verify the selected child, and explicitly start its
game afterward. Both links may reuse an existing matching child under the retained
r1 primary. A missing child is not recreated from an older primary package unless
that package advertises the atomic replacement contract needed to reach the pinned
selection. A newer verified primary/child is never downgraded to an older selection.
The live r1 primary is never replaced or logged off by this flow.

Cold endpoint-only behavior requires the new primary binary; older binaries
retain their previous automatic game-start behavior. The protected task still
selects the newest verified installed package and needs no new registration.
Cold Windows login/ActiveX behavior has not been live-validated while the current
game session remains active; synthetic tests cover intent and callback boundaries.

Results include `selectedChild`, its pinned package/identities, `childReplaced`
and `childStartDispatched`. The ordinary-token `ensure-child` CLI carries these
checks; no new elevated task/helper or registration is needed.

Only the exact audited r1 binary may omit `uiStatus` and its child root backlink.
Its package and assembly are verified first, and an independently authenticated
connected primary must match the pinned root PID/session/nonce. Such a child is
an upgrade candidate only, never ready; missing task/lifecycle fields are not
treated as idle. r1 through r18 lack the atomic restart capability: the shortcut
refuses automatic replacement before staging configuration or a restart manifest.
They require one controlled explicit `hot-replace` with active work stopped; that
existing direct command deliberately keeps its legacy stop/drain contract. A
matching current child can still be reused without this capability. Unknown legacy
packages require explicit investigation.
If a legacy/manual startup under the retained r1 primary creates another r1 child,
that child needs the same controlled upgrade. Approved missing-child reconciliation
now refuses that unupgradeable bootstrap before mutation; it never replaces a live host.
Replacement success requires a new child PID/nonce, exact selected hash/directory,
same root/session, the requested endpoint/game lifecycle and no active task.

An old host's manual/legacy bootstrap still passes `--automation start`; the
wrapper does not relabel that behavior as endpoint-only. It verifies the selected
child before success or an explicit game-start request, preserving the existing game.

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

The ordinary `start` command keeps the primary and RDP session. It does not upgrade a warm host or
silently select a different child executable: the primary's existing launcher
uses its own package. In particular, an old r1 primary may start an r1 child that
lacks the corrected `rootProcessId` backlink. Such a child is reported as a legacy
identity limitation, not accepted as ready. The approved shortcuts add the
verified idle-only reconciliation described above; direct callers may use the
explicit child replacement workflow. Do not weaken the
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

Development builds also support an explicit queued-step startup option:

```powershell
& $py tools/rdp-automation/rdp_control.py start-agent `
  --process-id 5678 --windows-session-id 3 --enable-input `
  --experimental-queued-step-applications
```

This option requires input permission and a fresh stream. The server blocks action
submission until the client completes the separate queued-v2 handshake for that
connection and the reviewed producer build. A listening status does not establish
that handshake. Omitting the option preserves the ordinary request and session
behavior; this option alone does not install or start a learned policy.

The 19 startup regression checks use in-memory transports and need only Python:

```powershell
python -B -X utf8 -m unittest discover -s tools/rdp-automation -p "test_queued_step_application_start.py" -v
```

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

WindowsGraphicsCaptureV2 also supports an explicit GPU readback experiment:

```powershell
& $py tools/rdp-automation/rdp_control.py set-capture-mode `
  --process-id 5678 --windows-session-id 3 --mode WindowsGraphicsCaptureV2 `
  --readback-mode poll_single_v1
```

The child must advertise `readbackVersion: 1` and the requested value in
`readbackModes`. Both `blocking` and `poll_single_v1` require V2 when explicitly
supplied. Omitting the option selects `blocking` and preserves the legacy request
shape. Switching requires an idle child and reattaches capture once; the client
checks both `configuredReadbackMode` and the attached `effectiveReadbackMode`.
To return to blocking readback, use the same command with `--readback-mode blocking`.

An additional WGC V2 experiment selects source retention and the existing conversion
path explicitly through the same idle, one-reattachment command:

```powershell
& $py tools/rdp-automation/rdp_control.py set-capture-mode `
  --process-id 5678 --windows-session-id 3 --mode WindowsGraphicsCaptureV2 `
  --readback-mode poll_single_v1 --source-retention hold-until-readback-v1 `
  --conversion cpu
```

The child must advertise `captureOptionsVersion: 1`, `sourceRetentions` containing
the exact retention selector, and `conversionModes` containing the exact conversion
selector. Retention values are `disabled` and `hold-until-readback-v1`; conversion
values are `gpu` and `cpu`. Explicit fields are rejected for every other backend.
Missing fields preserve the saved retention/conversion settings; the existing omitted
readback option still selects `blocking`. New configurations default to disabled
retention and GPU conversion. There is no UI toggle or automatic backend fallback.

`configuredSourceRetention` / `configuredConversion` describe saved configuration;
`effectiveSourceRetention` / `effectiveConversion` describe the active V2 attachment
and are absent for stopped or other-backend captures. These are managed startup
metadata reads, with no native capture or capture-lock wait. They establish neither
usable pixels, GPU completion, freshness nor input permission. The selected source
is retained until successful readback copy and Unmap, before refill; there is still
one pending slot and the same two-buffer selection bound. Source/cancellation/input
and all navigation age/deadline limits remain unchanged. Use `--source-retention disabled`
and/or `--conversion gpu` explicitly to change the saved choices back.

When reset teleport runs on the already-selected polling backend, its map and
loading-screen captures now wait through typed Pending outcomes. Each acquisition
has a two-second/200-call bound with cancellation and target/mode checks. Actual
Unavailable outcomes retain the existing four-attempt limit; malformed metadata
and expired acquisition windows stop teleport. This opt-in does not change the
ordinary capture helper or navigation's 150 ms source-age limit.

Polling keeps one submitted GPU copy and checks it without waiting inside Map.
A pending copy supplies no new pixels or source identity and cannot renew an
input lease. The stream may retain its last completed frame while its source
ages normally; the current `readback` snapshot (`mode`, `pendingCount`,
`lastOutcome`) describes capture progress separately from that frame. Native
navigation retains its existing freshness, cancellation and bounded wait rules.
Other capture/driver calls can still block, so verify image freshness and measured
latency before choosing this mode for sustained gameplay.

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

Reset capture defaults to `shared`. The explicit `--capture-policy task_owned_timer`
requires `navigationReset.capturePolicies` support before mutation, and the
selected `capturePolicy` is pinned through admission, polling and the terminal
diagnostics query. Older children keep the omitted shared wire shape. This
experiment leaves teleport capture shared: TaskRunner activates and drains the
runtime-bound timer pause **after the awaited teleport completes and before
orientation**, then retains it through input cleanup. Other hotkey/background
capture callers are not claimed to be excluded. Trigger cleanup/drain failure
ends the reset; it does not retry teleport or reuse an earlier reset result.

The isolated pose path checks chat on its same admitted native pixels before
world recognition, updates the existing chat guard and rejects directly detected
open chat. It supports native frames no larger than 1920×1080; shared keeps its
existing geometry support. Task-cancel and runtime-stop hotkeys remain usable
while the task owns this pause. Pose/source thresholds, response barriers and
the whole reset deadline are unchanged. Request this reset experiment separately
from the baseline's independent capture and timing choices.

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
the baseline command never resets, teleports, replays uncertain input, or accepts a
route file, coordinates, yaw target, or arbitrary inputs.

```powershell
& $py tools/rdp-automation/rdp_control.py run-navigation-baseline `
  --process-id 5678 --windows-session-id 3 --timeout 45
```

The explicit `mondstadt-city-two-legs-v1` profile continues through the first
three pinned points of the shipped route. It requires advertised route version 1,
the exact profile, timing v4 and task-owned timer capture:

```powershell
& $py tools/rdp-automation/rdp_control.py run-navigation-baseline `
  --process-id 5678 --windows-session-id 3 --timeout 45 `
  --timing-contract v4 --capture-policy task_owned_timer `
  --route-profile mondstadt-city-two-legs-v1
```

Both legs share one owner, input lease, watchdog, source history, recovery budget
and 30-second deadline. At the midpoint the controller releases movement, verifies
three fresh stable poses, then requires a fourth distinct anchor before the next
ordinary decision. The read-only handoff has at most two seconds and 32 captures/
reads; it cannot renew input or start movement recovery. Final input closure and
endpoint verification happen at the second endpoint. A completed first leg is
retained as partial evidence when the rest fails; it is never route success.
Omitting `--route-profile` preserves the original single-leg wire request.

`--timing-contract v2` and `--timing-contract v3` are explicit opt-ins and require advertised
`navigationBaseline.timingContracts` support before dispatch. The default `v1`
omits the selector for legacy hosts. Compact status and the pinned result retain
both `timingContract` and `controllerMethod` (`native-fixed-leg-feedback-v1`,
`native-fixed-leg-feedback-v2` or `native-fixed-leg-feedback-v3`). Version two permits a first W attempt of at most
150 ms and subsequent attempts of 100 ms; each expiry is also capped by the
conservative source freshness anchor plus 250 ms. These are host dispatch/lease
bounds, not proof of physical game input receipt, release timing or ground truth.
The first-attempt allowance is used once per run; releasing W for camera
realignment does not restore it.

Version three permits up to 150 ms on **each new W keydown attempt**, including
after a normal release and camera realignment. Renewing an existing W hold still
grants only 100 ms and does not send another keydown. Every v3 expiry is the
earlier of the final dispatch-gate clock plus its grant and the conservative
source anchor plus 250 ms, so older accepted sources can shorten the grant.
`firstForwardAttempt` continues to identify only the first attempt in the run;
later v3 starts retain `false` even when they receive 150 ms. Old expiry is checked
before renewal, expiry remains terminal, and native-call time consumes the grant.
Neither v3 nor the capture-policy selector changes the 150 ms source-age limit,
60/80 ms response barriers, route gates or 30-second whole-task deadline. The
watchdog's actual release can run late; the recorded clocks do not claim a hard
OS scheduling bound. For an explicitly selected v3 run, add `--timing-contract v3`
to the baseline command. The omitted/default contract remains v1.

`--capture-policy task_owned_timer` is a separate opt-in experiment. The default
`shared` keeps the existing timer/task capture behavior and omits the selector
for older children. The opt-in requires `navigationBaseline.capturePolicies`
support before dispatch; `capturePolicy` is pinned in compact status, the full
result and journal independently of `timingContract`. For example, to compare
capture sharing while retaining timing v2:

```powershell
& $py tools/rdp-automation/rdp_control.py run-navigation-baseline `
  --process-id 5678 --windows-session-id 3 --timeout 45 `
  --timing-contract v2 --capture-policy task_owned_timer
```

TaskRunner drains the bound runtime's timer capture after acquiring task
ownership, then keeps that timer capture paused through input cleanup. Timer
housekeeping continues; unrelated hotkey or background capture callers are not
claimed to be excluded. Drain or trigger-disable failure ends the run before
baseline input. A current trigger's cleanup failure clears only after that same
trigger later disables successfully. An unresolved retired trigger's failure
blocks this opt-in until the dispatcher or process is recreated; starting another
task does not erase it. Failure evidence is bounded, and shared-mode callbacks
keep their existing behavior. The opted-in baseline checks chat on the same
admitted native frame before world
recognition, updates the existing chat guard, and rejects directly detected open
chat without waiting for its two-frame debounce. Its added recognition cost is
measured. This experiment rejects native frames wider than 1920 or taller than
1080 before chat recognition, because its existing chat template geometry cannot
directly interpret larger raw pixels. Shared capture retains its previous
geometry support. No source, response-barrier or input-lease limit is widened. Configured
task-cancel and runtime-stop hotkeys remain exempt from chat suppression while
the task owns this pause. Other hotkey behavior remains unchanged.

The fixed leg follows the first two coordinates of the shipped Mondstadt
crafting-bench route, from `(-867.7041015625, 2281.378173828125)` to
`(-874.3662109375, 2274.179931640625)`, about 9.808 map units. Its separately
versioned `native-fixed-leg-feedback-*` controller uses unsprinted forward input
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

The file journal retains up to 63 selected slow/failed capture-call traces plus
the final invocation's trace when available, within a total of 64. Keeping the
last invocation also covers a successful read followed by an input-gate failure.
Already-retained traces are not duplicated; omitted optional detail is counted
explicitly. `captureTimingSelection` labels this selection, and
`completeCaptureTimingTrace` remains false. Required poll rows remain separate;
the post-release journal keeps its 6 MiB limit and wire limits are unchanged.

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


### Opt-in v4 native timing recovery

`run-navigation-baseline --timing-contract v4` requires the selected child to advertise `v4` in `navigationBaseline.timingContracts`. It never silently falls back to an older contract. The default remains v1; v1–v3 behavior is unchanged, and `--capture-policy` remains independent.

V4 retains v3's at-most-150 ms physical W starts, 100 ms renewals and conservative source-anchor-plus-250 ms cap. It may recover at most twice from a typed age-only source overrun or known lease expiry during the travel phase. Each recovery first releases W, keeps the same release watchdog running, and waits without input for at most 2 seconds and 32 capture polls inside the original 30-second task budget. Successful rearm requires the exact pause ticket and target, no cancellation or release error, unchanged source epoch/geometry, increasing source clocks beyond the completed release plus 80 ms, and fresh same-frame closed-chat, world, normal-motion and route-corridor evidence. Rearm itself sends no input.

The initial anchor and all endpoint acceptance gates remain strict. Invalid/missing/regressing source metadata, changed target/epoch/geometry, world/chat/motion/corridor rejection, uncertain key release, exhausted recovery/evidence limits and cancellation remain terminal. Synchronous native calls and OS scheduling can outlast the cooperative deadline; this does not extend input authority or establish physical release latency. Normal motion evidence does not prove safe footing.

After permanent input closure, current v4 builds allow one separate final-evidence window: at most 2 seconds from the completed close, clipped to the original 30-second task deadline, with at most 32 native reads and 32 capture admissions. Only a typed source-age overrun may be discarded; the 150 ms freshness limit, fixed 80 ms close barrier and all known hard source/pose gates remain unchanged. Three accepted poses are still required, with 120 ms between accepted reads and 20 ms after an age discard. A rejected candidate image never replaces the accepted final image. This window cannot reopen input or consume another movement recovery ticket. Its bounded file-only evidence is identified by `finalVerificationReadinessVersion:1` and `finalVerificationWindow`; partial accepted samples remain visible on failure. Older v4 builds lack this separate policy, so retain the package hash with each result.

The file journal adds `recoverySchemaVersion`, `recoveryPauses` and `recoveryAttempts`. Attempts retain fixed deadlines, trigger sources and half-open ranges into the original observation/capture-poll arrays, with rearm or failure outcomes. These remain controller-intent/recognized-pose records with `trainingEligible:false`, not human demonstrations or game acknowledgment. The existing 6 MiB journal and other global evidence limits remain unchanged. The CLI retains failed terminal results and never resets or retries the route automatically.

### Optional native capture-only archive

`run-navigation-baseline ... --timing-contract v4 --capture-policy task_owned_timer --shadow-capture rgb192-capture-only-v1` requests a separate passive RGB192 archive. The pinned child must advertise `navigationBaseline.shadowCaptureVersion: 1` and the exact mode before the single start request. Omission preserves the existing baseline. There is no model, second capture loop, input authority, live action transport or mode switch.

The existing native Ready path copies only fresh, hard-validated source pixels, including those preceding its response barrier. These copies are not world/pose admission. A worker applies the existing exact P2P Hamming transform and writes lossless packed `.rgb` frames plus a manifest linked to the completed native journal SHA-256/run ID. The journal remains the source of native controller intent; it is not a complete low-level dispatch trace or game acknowledgment. Sampling is irregular, and every archive remains `trainingEligible: false`.

Two preallocated raw buffers (at most 3840x2160x4 each), 1,024 unique frames, an 8 MiB sidecar and one process-wide writer bound storage/ownership. RGB files total at most 108 MiB. Copy/IO loss stops shadow admission, is reported explicitly, and does not renew input or extend any native deadline. Terminal worker retirement has one 2 s budget; an unresolved writer retains the process-wide reservation so another shadow cannot accumulate behind it.

A selected archive must be complete and positively retired for the CLI to return success. A native route can be verified while the archive failed; the dedicated `NavigationBaselineError.status` and CLI error JSON retain that native result and the archive counters separately. Failure before journal publication may leave only partial files with no complete manifest; those cannot establish usable archive evidence. Ordinary status carries only capability/selection, and the dedicated result carries the compact archive summary.

### Fixed reverse continuation with optional archive

The proposed `mondstadt-city-reverse-two-legs-v1` profile requires `--continuation-from-run-id` naming the same child's latest fully cleaned-up, verified forward two-leg owner. Use v4 and task_owned_timer. The client fetches the exact predecessor result, then sends one start; it performs no reset, teleport, mode change, or uncertain-request replay. The server atomically checks the retained predecessor and runtime/game/capture/input binding, then requires a fresh same-epoch source at the reversed start. Process IDs or an old result file alone do not authorize continuation.

`--shadow-capture rgb192-capture-only-v1` may accompany that reverse selector. Both capabilities and both selections must remain exact. A predecessor that selected shadow capture must retain matching complete, retired archive evidence before this CLI will start a reverse run, whether or not the new run selects shadow. Missing, incomplete, or contradictory summaries fail before mutation. The server's native verification remains independent of archive completeness; a direct server reverse without shadow does not certify a prior writer's retirement. A selected new archive also acquires its exclusive writer slot before any navigation input. An incomplete requested archive produces a CLI failure while retaining the full native result and continuation proof.

This proposal still requires a fresh same-build forward two-leg acceptance and integrated validation before live reverse/shadow use. The capture-only archive is irregular source evidence and grants no model or input authority.
### Explicit fixed courtyard continuation

After a fresh verified `mondstadt-city-leg-1-v1` run on the same child with `v4` and `task_owned_timer`, `mondstadt-city-courtyard-return-v1` follows only point2→point1. `mondstadt-city-courtyard-forward-v1` then follows point1→point2. Both use `--continuation-from-run-id` with the exact latest completed predecessor and require the exact profile in the child's advertised `routeProfiles`. Return accepts an ordinary short or courtyard-forward; courtyard-forward accepts only courtyard-return. Each request is separate, with no automatic loop or reset fallback.

These profiles retain the existing runtime/game/capture binding, cleanup, source-floor, start-anchor, world/motion/chat and input-lease checks. Their result has `routeVersion: 1`, one fixed leg, no waypoint, and the existing three final endpoint samples. Ordinary short result framing stays unchanged. Selected predecessor shadow archives must be complete and worker-retired before the client issues continuation. Controller intent and archived pixels do not attest physical input delivery. The older three-point reverse remains a separate profile; these courtyard selections do not traverse its elevation edge.


Endpoint continuation status contract2 advertises `endpointContinuationVersion: 2` and publishes only
`continuation: {version: 2, predecessorRunId, predecessorProfileId}` in ordinary status. The enclosing
authenticated child and owner still bind the current run. The dedicated result and file journal retain
the complete version1 continuation proof, including runtime, source floor, cleanup and predecessor
artifact evidence. The CLI supports exact legacy1/new2 status forms, pins the compact reference through
polling, and verifies the complete proof after terminal retrieval. It never substitutes a later owner or
replays an uncertain start. Old clients reject capability2 before a continuation mutation. The ordinary
8KiB and dedicated-result32KiB frame limits are unchanged; a compact reference is not independent
evidence of runtime continuity, physical input acknowledgment, or full artifact verification.

### Verified courtyard use inside minimized RDP

R45 completed a fresh short forward route and the fixed return/forward pair, then four consecutive supervised legs, inside the existing minimized RDP session. Its selected capture mode was `DesktopDc` with `--desktop-dc-source-policy host-acquisition-v1`. That policy supports only the ordinary short route and the advertised fixed courtyard return/forward profiles, using `v4` and `task_owned_timer`; the older two-leg profiles and shadow archive are not accepted with this policy. Acquisition timestamps describe host capture work and do not certify rendered-frame age.

#### Preview and run a bounded sequence

`courtyard_sequence.py` derives the next return/forward direction from an independently accepted latest predecessor proof. Its default checks the proof, deployment, binaries and snapshot files and prints a JSON plan without importing the pipe client or querying processes. Use a fresh output directory:

```powershell
& $py tools/rdp-automation/courtyard_sequence.py `
  --predecessor '<absolute-path-to-latest-predecessor-proof.json>' `
  --predecessor-sha256 '<exact-proof-sha256>' `
  --output-dir '<fresh-absolute-batch-directory>' `
  --max-legs 4 --seconds 180
```

Add `--execute` to the same command after reviewing the plan. The existing hidden RDP broker owns one worker; no visible-console fallback is used. The bound is four legs and 180 seconds for admitting new legs, with the existing 45-second native-client limit and a 270-second worker limit. Each immediate native terminal and artifact envelope gates the next leg. Full route audits remain retrospective, and another invocation requires a newly accepted proof from the separate route auditor.

The initial adapter accepts the reviewed R45-compatible deployment, predecessor and audit schemas. A future incompatible build needs an updated adapter. Timeouts, unknown outcomes and failed native owners stop the batch; the command never resets, refocuses, replaces the child or replays a start. After child replacement, establish a fresh seed and accepted proof. The first live trial completed one return and stopped on a native endpoint lease expiry during the next forward; the failure and its diagnosis are retained in the measured results linked below.

The parent summary retains bounded broker facts and the validated worker error, attempted/successful leg counts and last reported native result. A native failure such as `forward_lease_expired` is reported distinctly from a broker timeout. Reported terminal state does not prove OS process retirement or replace the full route audit; malformed or contradictory results remain failures. The combined command cohort passed 78 CPU/mock tests covering evidence validation, sequence control and parent reporting.

The endpoint-expiry repair is compiled and deployed in R46; its source12 producer passed 1,860 selected C# cases and Debug/Release validation. The primary envelope checker now recognizes the conditional top-level schema3 closure with exact source and release joins; the existing recovery schema3 remains a separate field. This envelope check does not replace the full route audit or admit a predecessor by itself. The latest R46 reset succeeded, but its short seed exhausted two movement recoveries, so it cannot authorize continuation.

Explicit native timing v5 is a separate opt-in producer change. It passed the required primary Debug build and all 1,890 selected C# tests; matching CLI support passed 279 Python tests. R47 is deployed inside the same minimized RDP session. Its fresh reset and short v5 route completed, the latter in 3.82 seconds with zero movement recoveries. The full R47 audit and continuation binding remain pending. Existing single-baseline and courtyard defaults remain v1 and v4 respectively. Never substitute an older accepted predecessor for a failed latest owner or reuse it across child replacement.

#### Request an individual leg

Use the current child process and Windows session IDs from `discover`/`status`, and the exact latest verified forward run ID. The following requests one return leg; the IDs below are placeholders to replace with that current state:

```powershell
$childProcessId = 5678
$rdpSessionId = 3
$previousForwardRunId = '<latest-verified-forward-run-id>'
& $py tools/rdp-automation/rdp_control.py run-navigation-baseline `
  --process-id $childProcessId --windows-session-id $rdpSessionId --timeout 45 `
  --timing-contract v4 --capture-policy task_owned_timer `
  --route-profile mondstadt-city-courtyard-return-v1 `
  --continuation-from-run-id $previousForwardRunId
```

After that request returns verified completion and clean input closure, use its returned run ID for the next forward leg:

```powershell
$previousReturnRunId = '<just-completed-verified-return-run-id>'
& $py tools/rdp-automation/rdp_control.py run-navigation-baseline `
  --process-id $childProcessId --windows-session-id $rdpSessionId --timeout 45 `
  --timing-contract v4 --capture-policy task_owned_timer `
  --route-profile mondstadt-city-courtyard-forward-v1 `
  --continuation-from-run-id $previousReturnRunId
```

The client retains the same authenticated child, capture epoch, build, game and immediate predecessor. A timeout or missing reply is not permission to replay a start. After replacing the child, establish a new ordinary short-route seed; an old child's run ID cannot resume the new child. Host-policy continuation additionally advertises `hostEndpointContinuationVersion: 1` and retains its typed host-acquisition floor and application build binding.

The accepted four-leg experiment demonstrates automatic continuation across this fixed corridor. Movement still pauses for endpoint verification, turnarounds and some camera corrections. See the [measured sprint results](../../Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md) for the actual key-release-to-next-key-down gaps and limits of the model experiments.
