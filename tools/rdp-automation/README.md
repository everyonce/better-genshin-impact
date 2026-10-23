# BetterGI RDP automation

This local Python 3.11 CLI controls explicitly enabled BetterGI instances. The primary instance hosts the separate RDP window; capture, game automation and ordinary commands run in the child session. It uses the existing same-user named pipe, verifies its Windows PID/session/owner, and pins mutations to a fresh instance nonce. It contains no credential handling or installer.

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

It then stops child automation, waits for idle, writes the hash-pinned restart manifest and requests one replacement. Success requires a new child PID and nonce in the same RDP session, the same registered root, the selected directory and assembly hash, and a running game runtime with no active automation task. A failed reattachment is reported as failure. The primary RDP host and existing game are retained; the replacement starts with `--automation start` to reattach. Automation tasks are left stopped until explicitly restarted.

An I/O timeout can leave a mutation's outcome unknown. Query `discover`/`status` and inspect the existing job/result before sending another mutation; the client does not replay uncertain requests.

## Validation

```powershell
& $py -m unittest discover -s tools/rdp-automation -p 'test_*.py' -v
```

Tests cover framed protocol/peer identity, nonce changes, bounded output, single-use jobs, RDP/elevation rejection, native suspended-process Job Object handling, configuration staging and hash/lifecycle replacement readiness. They use harmless Python processes and synthetic files; they do not send game input or interact with GUI windows. Native Windows security/file primitives may require running the test command outside a restrictive sandbox. Live RDP authentication, game attachment and replacement remain separate end-to-end checks.
