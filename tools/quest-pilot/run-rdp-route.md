# Run a canonical route inside the existing RDP session

From the repository root, with BetterGI's RDP child already connected, minimized, and running the game:

```powershell
python -B tools/quest-pilot/run-rdp-route.py `
  --route tools/quest-pilot/routes/mondstadt-scout-inland-detour.json `
  --progress artifacts/route-run-01.json `
  --expected-uid YOUR_GAME_UID `
  --allow-field-combat --allow-dialogue
```

Use a route appropriate to the current location and the exact numeric game UID. The example is a specific inland detour, not a route from arbitrary world positions. Both gameplay permissions are opt-in and are passed unchanged to `act-one-route.py --controller`. Add `--continue-objective TEXT` only for each explicitly authorized subsequent objective. The launcher does not invent a route, alter route JSON, start an application, reconnect RDP, or focus the main desktop.

An installed `node.exe` must be on the console PATH, or supplied with `--node PATH`. `--process-id PID` selects one existing child when discovery is ambiguous. Inside RDP, the foreground process must match the installed `User/config.json` game's executable and current Windows session. Its actual process creation time and HWND are retained and rechecked before each route. The launcher does not require a nonexistent game PID field in discovery. Existing unavailable endpoints, active work, unresolved controller leases, or a mismatched `ActOneRun` group cause refusal. The fixed native group is reused only when it contains the single input-enabled pilot, automatic game entry is disabled, and automatic pathing/combat/food options are explicitly disabled. If absent, the launcher exclusively creates this group and removes only its own file after verified retirement.

Repeat `--route PATH` for up to20 ordered routes. Each is still one canonical bounded controller call, with the original JSON retained byte-for-byte. Only verified arrival advances to the next route. Later legs pass their preceding successful progress to the canonical `--continue-from-progress` verifier; invalid shortcut evidence follows that controller's normal bootstrap. A pending, failed, or uncertain leg never advances or retries.

The default canonical deadline is90,000ms per route and the maximum segment count is3; `--deadline-ms` and `--max-segments` may reduce these within their existing limits. All legs use one owned pilot session. Add `--stop-file PATH` for caller cancellation. The launch also honors its progress directory's `STOP`, `<progress>.STOP`, evidence directory's `STOP`, and the pilot's native `STOP`.

For one route, `--progress` is exactly the canonical progress document. For multiple routes it is an aggregate with `legs[].progress`; each original canonical document stays under `leg-001`, `leg-002`, etc. Other evidence is in the adjacent `<progress-stem>.rdp` directory: original route snapshots, one launch document, broker result, worker result, route stdout/stderr, group before/after, and launcher result. Existing progress or evidence directories are never overwritten or reused.

Exit0 means every route verified arrival and the exact owned pilot retired. Exit2 means execution or retirement failed. Admission errors exit nonzero before dispatch. Native request/receipt files are retained. An unresolved canonical request retains its controller/launcher leases for inspection. Uncertain start or broker delivery is recorded and never replayed; cleanup does not adopt or stop another session.

Other Python callers may import this module and use:

```python
args = launcher.parse_args([
    '--route', str(route), '--progress', str(progress), '--expected-uid', uid,
])
result = launcher.run(args, expected_owner={'root': original_root, 'child': original_child})
```

`expected_owner` compares each record's exact `processId`, `windowsSessionId`, and `instanceNonce` before broker dispatch and again inside the worker. The returned report contains `status`, `exitCode`, `progress`, `workerResult`, `launcherResult`, `pilotRetired`, and `owner`. Pre-dispatch validation errors raise; runtime failure reports remain separate from any caller's original failed run. Arrival or retirement alone does not grant unrelated encounter, quest, or healing success.

Run the inert regression tests from the repository root:

```powershell
python -B tools/quest-pilot/test_run_rdp_route.py -v
```

These tests use the real canonical parser and files, with broker/native/process operations replaced by explicit fixtures. They do not start BetterGI or issue game input.
