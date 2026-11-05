# Run routes in BetterGI RDP

Connect and minimize the BetterGI RDP window, with Genshin running inside it. From the repository root, run the following command with your game UID and a route that starts near your current position. This example starts at the rock on the Mondstadt inland scouting route.

```powershell
python -B tools/quest-pilot/run-rdp-route.py `
  --route tools/quest-pilot/routes/mondstadt-scout-inland-detour.json `
  --progress artifacts/route-run-01.json `
  --expected-uid YOUR_GAME_UID `
  --allow-field-combat
```

An optional `teleportTo` field in a route JSON selects `temple-of-the-lion`, `mondstadt-gate`, or `starfell-lake`. BetterGI opens the map when needed and verifies arrival before walking the waypoints. Travel uses the same route deadline. A route with `startNear` checks its starting position after teleporting.

The launcher discovers the connected child and verifies the running game against BetterGI’s configured executable, Windows session, window, and process start time. Use `--process-id PID` to select a child when several are connected. It uses Node from the console PATH. Use `--node PATH` to select an installed `node.exe`.

- Repeat `--route PATH` to run up to 20 routes on one pilot. Each route starts after the previous route verifies arrival. A verified inventory handoff lets the next route skip an extra menu transition.
- Use `--allow-field-combat` to engage measured enemies during exploration. Use `--allow-dialogue` for routes that support dialogue and `--continue-objective TEXT` for each subsequent quest objective you want to follow.
- Use `--stop-file PATH` to choose a stop signal. Creating that file during the run requests a stop. Choose a fresh progress filename for each run.

For a single route, `--progress` contains its native requests and results. For a sequence, it contains the chain summary, and the adjacent `.rdp` directory contains the individual progress files. Exit code 0 means every route verified arrival and the pilot retired. For an interrupted run, the worker result identifies the last leg and records whether the pilot retired.

Other Python callers can retain the exact root and child identities between operations.

```python
args = launcher.parse_args([
    '--route', str(route), '--progress', str(progress), '--expected-uid', uid,
])
result = launcher.run(args, expected_owner={'root': original_root, 'child': original_child})
```

Run `python -B tools/quest-pilot/test_run_rdp_route.py -v` for the launcher regression tests.

To talk to an NPC at the final waypoint, add `"talkTo": "Amber"` (or the NPC's exact English name) to an exploration or quest route. For quest routes, the controller checks the visible objective and prepares the starting screen required by the installed navigation routine. This authorizes that named arrival, while `--allow-dialogue` separately enables dialogue encountered on the way. Place the last waypoint within interaction range. BetterGI matches the selected F prompt, confirms the speaker after opening the conversation, advances recognized lines and choices, and verifies a return to the world before parking in inventory. A missed prompt or a tutorial handoff leaves the waypoint cursor available for inspection. The recorded conversation establishes that the NPC spoke, while quest completion still needs separate objective or reward evidence.
