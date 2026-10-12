# R15 Windrise validation

## Runner and OCR changes

`rootDirected` rejects GPS movement while the map is unrevealed and uses bounded native W/S holds, camera look, or Statue interaction with a fresh-image, same-session, one-use witness. Walk and retreat permits allow up to 24 half-second moves under a 35-second local deadline. Each move is followed by fresh frame, HP, enemy, UI, and focus checks; unchanged observations stop movement. The intended reduction in root submissions versus the former six-move cap is not a measured speedup. Strict pause and per-move guards remain.

The reveal cleanup requires three fresh no-input captures 200 ms apart and permits B only in a fresh, known field. Control OCR requests a same-capture crop at `(1520,985,390,80)` for the exact Lisa objective when E/Q controls are missing. Two look turns of −250 and −150 completed without HP loss and with an inventory pause (3,036 ms and 3,012 ms). A prior full-frame capture saw only R while the terminal reported Q and grounded=true, supporting missing OCR controls rather than a proven stagger or terrain cause.

The red-bar geometry filter accepts width >=16 and aspect ratio >=3.5, or a same-frame level anchor. A five-move batch detected an actual Lv3 Hydro Slime with a 71×4 red bar, took no HP loss, and verified pause in 7,503 ms. The earlier four-by-three leaf false stop was fixed. Amber party-label OCR uses a narrower same-capture crop to avoid `Amber4`.

An earlier unsafe-look guard refused input but left the field unpaused; HP fell to 331/1186 during root idle delay. The pause-only fallback passed tests but remains unverified against a live threat and is disabled. Earlier recovery took 31,478 ms and verified 1186/1186 HP. Script sources were hotloaded over RDP without native build or restart.

## Live batches and combat attempts

The first 24-move batch completed in 24,884 ms end-to-end and 24,122 ms local time. Measured key-input time was 13,909 ms, including pause and overhead. Lisa objective distance changed from 531 m to 481 m; HP fell from 1186 to 1166 (20 HP, cause unknown). This does not establish reduced end-to-end latency. Later, a 12-move batch ended `ground=false` with an unverified pause despite a terminal `ground=true` reading and 1146 HP. A subsequent five-move batch lost 39 HP and also ended `ground=false`, unpaused, while the terminal read `ground=true`; root paused at the journal. A later five-move slime batch paused safely, but safe arrival and autonomous progress remain unproven.

The first live combat request did not reach combat. Its local routine ran 3.402 seconds and returned `pause=false`. The game was unpaused at 20:09:52.579 UTC; diagnosis and root pause followed at 20:10:17.635, about 25 seconds later. HP was 1067/1186 at the first failed frame, 1050 locally, then 928 before the root pause: 139 HP lost overall.

The second attempt selected VK_3 once but never fought or returned to Amber. Full-frame OCR missed the active grey slot-3 indicator, producing false `world=false`; cleanup ended with `pause=false`. Kaeya was 1057/1057 at the initial reading, 1039 locally, and 934 before the root pause, a total loss of 123 HP over about 26 seconds. The root paused at the journal.

A third attempt ran the existing native starter auto-fight once with cooperative 15-second timeout; total mission time was 22,040 ms. Kaeya HP changed 916→899→844 and Amber returned at 876 HP. Post-fight evidence showed +10 Character EXP and Slime Condensate with no enemy bars, proving at least one slime was killed but not proving the area was clear. Food interaction and pause were verified at frames 647/648.

A later noncombat probe succeeded while the game remained paused between combat attempts. It took 12,177 ms end-to-end and ended at field frame 650 with Amber at 876/1186 HP, exact Lisa objective at 406 m, no enemy bars, and compass value 96. The only inputs were Escape and B: no character selection or native fight occurred. Fresh immutable Food proof was captured at frame 654 and final idle confirmed at 655; HP remained 876/1186. For the field-650 capture, capture took 4 ms, OCR primitive 838 ms, PNG writing 166 ms, and total observation 1,034 ms. This single probe does not establish enemy clearance, arrival, Act I completion, or an aggregate speed improvement.

## Pause guardian and combat path

The user requires every failure path after unpause to verify pause before any next combat action. A local-pause guardian wrapper owns cleanup and blocks stop-bypass cleanup with same-session and focus guards. The key-up old-state overwrite defect was fixed by releasing before starting the next key. Focused tests passed: 10 local-pause, 14 Lion pure-module, and 15 Lion adapter tests, including 13 fault cases and deterministic pending tests.

The combat path gates on safe food closure, exact Lisa objective, owned Kaeya in slot 3, no Trial state, grounded status, HP >=60%, and a fresh enemy bar. It permits one VK_3 attempt and reuses the existing native starter auto-fight for at most 15 seconds with cooperative cancellation and disposal; it has no hard cutoff or HP monitor. Returning to Amber permits one VK_2 attempt. One live attempt proved at least one slime could be killed, but no all-clear or completed-quest evidence exists.

The JavaScript suite passed **979/979 tests across 119 matching test files**, 0 failures. Node duration was 34,592.9141 ms; wall time was 34,752 ms. It ran all matching `Test/**/*.test.js`, `.test.cjs`, and `.test.mjs` files except the unintegrated `Test/ActOnePilot/lion-domain.test.cjs`. Full output is saved at `artifacts/r15-local-pause-all-tests.log`.

While paused at frame 648, `bgi`, `mission`, `lion-field-combat`, `local-pause`, and `windrise` sources were hotloaded without a native build or script restart. The later noncombat probe occurred after hotload. No further live combat was performed.

Earlier validated changes were pushed to `main` and `english-interface` at `7d71f15`; subsequent reveal/OCR, combat, and guardian changes remain unpublished. Prologue Act I is incomplete, the Lion entrance has not been live-validated, and the area-clear state is unproven.
