# Mondstadt stair-post gameplay, October 29, 2026

BetterGI and Open P2P completed **24 consecutive crossings in 210.98 seconds** around a stone post at the foot of the Mondstadt stairs. The character climbed the post on the first approach, dropped, backed away and stepped sideways. After reaching the far endpoint it reused three measured detour points on all 23 subsequent crossings. The run finished through four stale-frame interruptions. A separate five-decisions-per-second trial verified four consecutive ground-stall escapes.

## Live tests on this machine

BetterGI R57 captured the running game in minimized RDP session 3. A resident Open P2P 150M model on the RTX 2080 SUPER evaluated Hamming RGB192 images, using history 41, a CUDA graph, the existing street-walking instruction and a 150 ms first-input deadline. The R56 host stayed on the primary desktop. The Python controller and audit run from the checkout. The R57 executable is unchanged.

| Run | Route and result |
|---|---|
| `lamp-hybrid-12` | Eight streetlamp crossings in 39.10 s at 10 Hz. All 350 accepted actions had applied receipts. The character continued moving past the lamp without invoking recovery. |
| `planter-21` | Two flower-box crossings in 6.52 s at 10 Hz. No sustained stall occurred. |
| `stair-post-27` | At 10 Hz the character climbed the stone post. Two X inputs were applied, the helper observed a normal exit, and forward input took the character back into the same post. The controller stopped at its retry limit with zero completed legs. |
| `post-walk-31` | Four verified stair-post legs in 62.00 s at 5 Hz, with four verified ground-stall passages. The audit joined all 279 accepted actions to applied receipts. Median source-to-first-dispatch time was 84.92 ms, with a 147.16 ms maximum. Peak GPU temperature was 68°C. |
| `post-fullrate-32` | The first full-rate escape taught three detour points. Nine subsequent legs reused them. On leg 11 one stale observation erased the path, and the next climb exhausted the two-drop budget. The resident run failed. Its recorded prefix shows the escape and replays, and is excluded from sustained completion results. |
| `post-rebind-37` | The controller finished 18 legs. The stale-frame release occurred while the camera was turning. Position changed by 0.001 map units and yaw changed by 63°. The controller interpreted the rotation as a departure, discarded the detour, then stopped at its climb limit. |
| `post-interrupt-42` | A deliberately delayed walking frame expired at the controller. Input stayed held during reconfirmation and the character finished the replay. A second delayed frame caught a stationary turn. Its completion receipt arrived in the asynchronous reader before release, but the planner had not seen it. It discarded the path and the trial stopped after two legs. |
| `post-interrupt-47` | Completed all 24 legs with one model load and one controller lease. The independent audit joined 4,541 source frames, all 1,931 accepted navigation actions and both applied climb-drop commands. It verified one climb passage, 23 detour replays and four resumptions after expired observations. Peak GPU temperature was 63°C. |

On the completed 10 Hz trial, model evaluation took 30.38 ms at the median and 33.85 ms at the 95th percentile. Median time from captured image to first navigation input dispatch was 81.14 ms. The maximum was 149.52 ms against a 150 ms deadline. Initial model loading took 18.34 s before gameplay. Of the 1,931 accepted navigation commands, 224 used the model's forward proposal, 549 used native forward guidance, 1,148 corrected the heading and 10 retreated or stepped sideways. The climb escape cleared the post sideways by 2.77 map units and reached the endpoint 7.24 units beyond the contact plane.

During the ground-stall trial each blocked approach accumulated 1.05–1.09 s of applied forward input within a two-second window. After backing up, the character moved sideways by 2.25–2.97 map units and finished 4.41–6.47 units beyond the contact plane. The native screenshot shows the character against the square end post. The learned-route counter was zero on this trial. The controller discarded its first candidate during the readiness transition caused by its own endpoint release.

In the failed full-rate trial, normal localization remained available. A 64.81 ms model call on frame 2418 left the image 165.89 ms old, beyond the 150 ms dispatch deadline. The prior forward input ended at 86,479.49 ms. The next applied action, a camera turn from fresh frame 2425, began at 86,770.94 ms. The controller correctly withheld input for that 291 ms gap but lost the static detour as a side effect.

The final interruption experiment delayed two real images in the consumer after capture, preserving their original source timestamps. Frame 278 was held for 170.33 ms during walking. The controller released input and recovered on frames 290, 293 and 298, 446.82 ms after release. Frame 518 was held for 170.22 ms during a camera turn. Fresh frames 529, 532 and 536 confirmed that yaw had settled from 286° to 333.5° while position remained stable. Reconfirmation took 365.54 ms. The exact completed mouse request was already in the reader's inbox when the synchronous release reply returned. Two further stale frames occurred naturally, on legs nine and seventeen. The leg-nine interruption recovered in 335.9 ms. Leg seventeen exercised the camera-turn allowance again. All four interrupted legs reached the endpoint.

## What the controller does

The original courtyard remains the default route. The fixed street routes use the same WGC image for learned proposals and BetterGI localization. The client cross-checks its map orientation against the native bearings. It keeps commands within the reviewed corridor and sends all movement through one controller lease.

* Ground stalls require distinct source frames, clustered position and yaw over two seconds, and at least 600 ms of receipt-confirmed forward movement. Retreat and sidestep advance on applied input and measured lateral clearance.
* A confirmed climb-drop exit binds the applied X request, release, normal observations and capture identity. During an admitted leg the next qualified position starts retreat. Both climb and ground recovery keep finite budgets.
* With `--remember-hybrid-bypass`, a successful passage teaches three positions measured after retreat, at sideways clearance and past the obstruction. The planner saves the path only after verifying the endpoint. On later legs it can use the same waypoints in either direction for the life of that stream. The expected release at an endpoint is tied to the returned readiness epoch. A new blockage or unqualified motion evidence can invalidate the path.
* On a stale image during a learned detour, the controller releases input and freezes the waypoint. It needs three fresh, stable positions in the returned world-readiness epoch within 1.5 s. For a large camera turn the body must stay within 0.35 map units and yaw must settle toward the waypoint in the commanded direction. The controller joins the exact applied rotation to the last accepted native turn. It checks receipts already delivered to the frame reader as well as the release reply, leaving the original records available for model feedback and auditing.

The RDP job broker also retires an expired command that no ordinary-token runner has claimed. Retirement competes atomically with the runner's claim, so a caller can distinguish a command that never started from one whose result is still unknown.

## Reproduction and local evidence

Start at either stair-post endpoint with the game world open. The two map coordinates are `(-844.93, 2255.29)` and `(-844.30, 2245.50)`. Use the existing RDP runner and GPU settings from the [R57 qualification](BetterGI-Hybrid-Gameplay-2026-10-27.md). Select the following options for the new route.

```text
--hybrid-navigation --hybrid-route mondstadt-stair-post-v1 --hybrid-legs 24
--navigation-climb-recovery --remember-hybrid-bypass
--goal-intent ground-navigation --fps 20 --decision-hz 10
--action-hold-ms 100 --max-observation-age-ms 150
```

The local evidence directory is `artifacts/live/2026-10-29-obstacle`. It contains the original game captures, recordings with source-frame indices, proposal and terminal-receipt journals, thermal logs, failed-trial reports and independent audits. `stone-post-contact-survey.png` is a native game capture. `post-walk-31-passage.png` shows four actual model-view frames from the third leg. The timestamps measure software dispatch from the captured observation. Video playback uses synthetic presentation times.

To verify the complete result against the local recordings, run this command from the checkout.

```powershell
$evidence = 'artifacts/live/2026-10-29-obstacle/post-interrupt-47'
python -B tools/bettergi-agent/audit_hybrid_run.py `
  --run "$evidence.json" --recordings "$evidence-recording" `
  --minimum-legs 24 --minimum-climb-passages 1 `
  --minimum-bypass-replays 23 --minimum-bypass-rebinds 4 `
  --output "$evidence-recheck.json"
```

The required Debug build passed. The updated auditor also passed the original 60-leg courtyard recording. Final discovery reported the game ready, the RDP window minimized on the main desktop, and both the child input stream and BetterGI tasks idle.
