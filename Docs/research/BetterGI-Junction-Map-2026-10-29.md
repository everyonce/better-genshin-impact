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

The independent Python verifier classified both saved images correctly. Warm median times were 17.8 ms for the junction and 17.6 ms for the map. The R59 change moves PNG encoding after release. Its live recognition and input latency still require measurement. The raw samples are in `offline-map-microbench-20261029T182302Z.json` under the experiment directory, SHA-256 `6cece3324e84b937573a9b360dfd522c1024ccd0382507bcb6fc71437866703f`.
