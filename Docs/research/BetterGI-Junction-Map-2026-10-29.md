# Inspecting the world map during a BetterGI navigation lease

The test starts at the surveyed Mondstadt sidewalk junction, opens the world map, recognizes the map and its close control on the same image, closes it, verifies the junction again, then walks to the west lamp. The normal world-HUD gate stays active throughout. During the UI operation the controller fences all ordinary proposals. It retains the GPU model for the subsequent walk.

## Starting position and replacement

The input-disabled R57 probe `r57-passive-final` recorded 58 world-ready images. Qualified G4 labeled every image as the junction. The independent native location put the character 6.17 units from that station and within 0.2 units of the stairs. The two-unit junction guard refused that view. R57 then completed a separate three-leg route, photographing the west lamp and junction, before consuming a graceful finish at the junction. Its GPU peak was 63 °C. The original route is in `approach/batches-20261029T175853Z-beceb160b8fb`.

The source-pinned `ensure-child` operation admits only the expected idle child under the authenticated, minimized R56 host. It verifies the requested package and the clean target capture settings. The protected settings handle remains held through restart acknowledgement. The R57→R58 receipt in `lineage` retained host PID 10124 and RDP session 3 and verified the new child PID 38028. The first five-second R58 probe contained one recorded frame and no valid pose. A twenty-second input-disabled check subsequently produced 230 valid G4 junction poses out of 232 frames, with a maximum position error of 0.154 units. The passive reader also reports its own capture/terminal outcome independently of the route runner.

## First map attempt

`live/warm-20261029T180711Z-9e347a5c89dc` retained the released junction photo and the native open-map software receipt. M was pressed at 656.308 ms and released at 727.682 ms on the lease clock. The next WGC image was generated at 700.207 ms, during the key hold, but acquired at 899.846 ms. Its age exceeded the 150 ms gate. The resident stopped at 913.463 ms with zero Escape presses and zero walking inputs. The synchronous 2.54 MB PNG capture on this code path ran before the next frame could be processed.

`r58-after-attempt` then observed the open map with input disabled. The original 1920×1080 PNG matched the close button at 0.9956, scale control at 0.9772 and settings control at 0.9668. Its SHA-256 is `7ae2747095e498400b96dd9ad2f31fa98b6d01b30b53a9cc2b0c3a07ffc2f164`. This independent capture establishes that the game opened the map. The first attempt retains its failure result.

All run paths above are under `artifacts/live/2026-10-29-map-inspection` in the SIREN checkout.

## R59 repair and deployment gate

R59 copies the original native pixels at the decision and compresses the PNG after releasing input. A stale observation clears the current recognition streak. Sending a key still requires a source at most 150 ms old. The native operation has a 12-second deadline. The Python resident keeps the same loaded GPU policy across the UI transition and requires a released world-ready junction and three fresh G4 matches before walking.

For an interrupted opening, the separate recovery command requires the audited R58 opening and input-disabled map capture. It waits for the new navigation recognizer to publish twice, then requires two fresh, positively matched native map images before its single Escape. The returned native poses must also match the original position. The canonical R58 origin digest is `e2519a01119be325ad714200d95a7fa7316bcd0fd0071343ed77d8ae0b0ac23e`.

The .NET 10 Debug solution build and self-contained Windows x64 Release publish passed. The package is `artifacts/release-r59/BetterGI-English-win-x64`, with DLL SHA-256 `6165c8b7e3bc25a3490c8a1042740f05587fa1762616870bd5109cd4530c25cf`. The native suite passed 100 tests, the Python agent suite passed 474, and the RDP control suite passed 95. Release retention kept R1, R55, R56, R58 and R59.

The first R59 deployment preflight stopped before replacement. Windows denied `SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION` on Genshin PID 26240 in RDP session 3. The capture settings were staged and the idle discovery saved under `lineage59`. The R56 host and R58 child remained connected. At that preflight the last verified screen was the open map, and a completed map-to-lamp run was still unverified.

## Measured cost of retaining evidence

An offline SIREN replay used the same R58 OpenCvSharp binary and the original junction pixels. It reproduced the saved PNG byte for byte. Encoding took 154.7 ms at the median and 156.4 ms at p95. All 12 warm encodes exceeded the 150 ms source-age limit. Allocating and copying the same 6.22 MB of pixels took 1.04 ms at the median and 1.96 ms at p95. On the original map image the corresponding medians were 114.4 ms and 1.00 ms.

The independent Python verifier classified both saved images correctly. Warm median times were 17.8 ms for the junction and 17.6 ms for the map. The raw samples are in `offline-map-microbench-20261029T182302Z.json` under the experiment directory, SHA-256 `6cece3324e84b937573a9b360dfd522c1024ccd0382507bcb6fc71437866703f`.

## Live R59 results on SIREN

The one-time Windows elevation succeeded. The helper held a read-only handle to Genshin PID 26240 during replacement, preserved the R56 host PID 10124 in session 1, and sealed the new R59 child PID 5520 in RDP session 3. Independent replay verified the receipt under `lineage59-admin`. The three subsequent runs all used the original game window handle 197360 and one GPU model load per run.

| Run | Second map source after M release | First world source after Escape release | Released G4 junction after Escape | First applied camera turn after Escape | First applied W after Escape | GPU policy median | Peak GPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Recovery of R58 opening | — | 1.658 s | 2.376 s | 3.160 s | 4.223 s | 27.76 ms | 63 °C |
| Fresh visit | 0.645 s | 0.740 s | 1.709 s | 2.342 s | 3.430 s | 29.78 ms | 61 °C |
| Fresh repeat | 0.653 s | 0.727 s | 1.633 s | 2.373 s | 3.416 s | 29.74 ms | 65 °C |

Recovery first verified two new native map frames, sent one Escape and matched the returned junction to the R58 position. Each fresh visit sent one M and one Escape. All three captured a qualified G4 junction on return, photographed the west lamp, and returned to the junction on the same controller lease. The timing uses the source-image timestamp for game response and the native applied-input receipt for the camera and W. The GPU metric includes preprocessing and action decoding. World position and photographs independently verify arrival.

Original runs are `recovery/warm-20261029T191651Z-9d5b3c8f7c36`, `r59-live/warm-20261029T191756Z-b633a0566524`, and `r59-repeat/warm-20261029T191916Z-189862af5a80`. Each has a `map-audit.json`, original images and transaction evidence under `map-inspection`, and a separate `handoff-audit.json` with two verified legs. The interrupted R58 attempt retains its original failure result.

## Sustained queue and delayed receipts

The first extended run, `r59-sustained/batches-20261029T192439Z-3683a8b411d9`, completed the map operation and 14 photographed goals over 18 legs before the controller stopped. Replay matched all 14 original images to the qualified G4 model and their native endpoints. The span from first to last applied route input was 75.46 seconds. The attempt finished short of the 210-second target.

Batch four's last input ran at 78,090.207 ms on the native lease clock. Its endpoint release followed 340.79 ms later. The third settled endpoint source arrived at +692.31 ms. The first action in batch five, a camera turn on frame 2150, ran at +880.77 ms. The controller considered a second proposal while the first turn's terminal receipt was in flight. It rejected the proposal locally because its full 150 ms start window extended beyond the one-second handoff deadline. The outer report incorrectly described that local refusal as a lost acknowledgment. All 613 acknowledged actions had terminal receipts. The final native state reported no held keys or active action.

The revised controller waits for the first accepted successor's original receipt before considering another input. Capture, world readiness, operator STOP and the thermal monitor remain active. An empty receipt keeps the original dispatch deadline in force. A positive receipt must prove the first action ran within that deadline. A missing receipt has a bounded grace period in which no further input is issued. The controller records an outstanding acknowledgment only as it enters the wire call. All 483 offline regression tests passed. A new input-disabled lease then confirmed the junction on 57 of 57 world-ready frames, within 0.24 units of its surveyed position.

The first corrected trial, `r59-receipt-sustained/batches-20261029T193111Z-1aeeb9d58499`, completed its map visit and 12 walking batches on one GPU load and one RDP connection. The walking audit verified 46 photographed destinations and 62 legs in 249.80 seconds. Of 2,157 applied actions, 1,735 came from BetterGI's navigation controller and 422 from Open P2P. The GPU policy median was 30.63 ms, median image-to-input time was 75.06 ms, and the longest interval between consecutive applied inputs was 794.69 ms. Peak GPU temperature was 65 °C.

At all 11 later batch starts the first action reached a completed terminal before the next admission. Median acceptance-to-terminal time was 105.61 ms and median terminal-to-next-admission time was 97.14 ms. The original combined launcher classified this trial as stopped after its successful walking audit. It had expected `operator-finished`, the manual queue ending. The automatic producer and consumer recorded `gameplayTargetReached` and `runtime-target-achieved`, respectively. The original launcher and all native receipts are retained.

The corrected independent verifier replayed the original map pixels, M and Escape software receipts, returned junction, and complete route. The producer's finish witness spanned 223.9123 seconds of native input against the declared 210 seconds. All 45 goal handoffs were below one second. The separate `map-replay.json` records this result and binds the unchanged original launcher and route audit by SHA-256. Its own SHA-256 is `7254f1413a7c73d309a8716c2fd1808688b8c86b2d70f2256344cc5a8090e702`.

The next live trial, `r59-final/batches-20261029T193934Z-55977fbd722e`, reached its 90-second target and photographed 22 destinations over 30 legs. Its original walking audit stopped at leg 19. The prior junction endpoint was verified on frame 1988, and the next batch arrived on frame 1990, 93.75 ms later. The original images and input journal confirm a stationary wait at the same junction pose. The west lamp was verified on frame 2127. The runtime measured 5,055.1297 ms from admission, while the audit measured 5,148.8797 ms from the settled junction. All 22 original photos rematched G4 and all 1,014 terminal receipts matched the event journal. The trial retains its timing failure.

## Final validation

The runtime now keeps the earlier verified endpoint timestamp across batch admission. The existing independent 35-second leg test stays in force, including time spent waiting at the station. All 485 offline regression tests passed. The repeat `r59-qualified/batches-20261029T194421Z-e109630019a4` exited successfully, with both its original `map-audit.json` and `handoff-audit.json` marked passed.

The model loaded once. The map was verified on frame 38 and the first west-lamp photograph on frame 225. The queue reached its 90-second target with 93.003 seconds between positively identified native dispatches. After finishing the accepted batch, the route totaled 116.406 seconds, six batches, 22 photographed goals, 30 legs and 997 applied actions. BetterGI supplied 804 actions and Open P2P supplied 193. Median GPU policy time was 30.54 ms and median source-image-to-input time was 75.55 ms. The largest consecutive input gap was 708.30 ms and GPU temperature peaked at 62 °C.

The final station was the sidewalk junction. Read-only discovery after the run confirmed the original R56 host was minimized, its R59 child was game-ready, and both task and stream were idle. These trials cover the world map and the three surveyed street stations. A naturally occurring stair-photo miss, broader exploration, quests and combat still require live qualification.
