# R15 Windrise validation

## Changes and live evidence

The finite `rootDirected` runner keeps actions bounded to W/S holds, camera look, and Statue interaction. It rejects GPS movement while the map is unrevealed and requires a fresh-image, same-session, one-use witness for the action. The walk/retreat cap is now 24 holds under a 35-second local deadline. Each 500 ms hold is followed by fresh frame, HP, enemy, UI, and focus checks; unchanged observations stop the walk. Up to 12 seconds of walking per permit is intended to reduce root submissions compared with the former six-hold cap; this is a design intent, not a measured speedup. Strict pause and per-hold guards remain. Root reset `interactions=0` and `pauseOnly=false` for this run.

Two live-observation misses were repaired: enemies with unknown level OCR remain eligible for the conservative red-bar scan (a visible Lv3 Hydro Slime had been missed by the prior level-4 detector), and Amber party-label OCR now uses a narrower crop from the same capture to avoid the spurious `Amber4` result.

The initial unsafe-look guard refused input but left the field unpaused. During the root’s idle delay, HP fell to 331/1186. A pause-only fallback was added and passed its tests, but was not validated against a live threat; it is disabled for the current run. The root retreated to the Statue and recovered at Starfell; healing took 31,478 ms and full HP (1186/1186) was confirmed. The root then returned to the unlocked Falcon waypoint. Source changes were loaded by the RDP script without a native build or restart.

The first 24-hold live batch was active when this report was updated; no result was available yet.

## Validation and remaining evidence

The repository JavaScript suite passed: **940 tests across 117 matching test files**, 0 failures, exit code 0. Node reported 13,207 ms; wall time was 13.3 seconds. All matching `Test/**/*.test.js`, `.test.cjs`, and `.test.mjs` files ran except `Test/ActOnePilot/lion-domain.test.cjs`, whose module remains prepared but unintegrated. Full output was saved locally at `artifacts/r15-windrise-all-tests.log`.

This validates JavaScript behavior only. Prologue Act I is not complete, and the Lion entrance has not been live-validated.
