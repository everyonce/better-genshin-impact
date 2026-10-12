# R15 Windrise validation

## Current travel safety

The shared pause guardian now owns every Windrise failure path after unpause. Paused-field witnesses are checked against saved image/JSON evidence and require the same camera within 5 degrees.

The first travel attempt made no look or movement input: the inventory was fading and field health was unavailable. The captured-only retry now waits for a strict fresh field observation rather than treating inventory disappearance as field proof. That attempt returned with pause verified in 6,249 ms; Amber remained at 876/1186 HP, and no root pause was needed.

A stale-witness rejection (witness more than 120 seconds old) sent no input and left the game paused in inventory. This is a correct safety rejection, not a combat failure.

Two paused camera turns completed without movement or HP loss. The first took 14,811 ms end-to-end, changed compass 96→72 with one −250 look, and returned inventory proof. The second took 16,441 ms, changed compass 72→52 with one −200 look, and returned inventory proof. Two 500 ms forward holds then took 14,057 ms end-to-end, moved the Lisa objective from 406 m to 401 m, retained Amber at 876 HP, saw no red bars, and verified pause. A later paused look took 15,414 ms and changed compass 52→34.5 with Amber still at 876 HP and pause verified.

A later 12-hold plan stopped before hold six when its next readiness check failed. Five 500 ms holds had completed in 32,489 ms end-to-end; Lisa objective distance moved from 401 m to 391 m, HP stayed at 876/1186, no red bars were seen, mandatory inventory proof was obtained, and no root pause was needed. The receipt does not record per-check age, so the precise cause is unproven; code and observation review suggest the 1,000 ms freshness limit expired between the post-hold and next pre-hold checks amid repeated file reads and evaluation. A subsequent request lost game foreground before any scripted input. Native focus recovery took 4,468 ms; a fresh read-only probe then verified pause in 11,864 ms, with no user action.

These end-to-end times include startup, captures, and verification, not just keypress duration. The bounded travel evidence shows progress over a short distance; it does not establish overall speed improvement or arrival. One human Space advance after handoff caused a transient map animation; the game later returned to the field automatically. The animation and charted marker at frames 1220/1221 prove map reveal only, not a durable pause, Statue unlock, or completed interaction. No Leave choice was recorded. The earlier total elapsed time was 637,086 ms, with about 3 seconds in the internal runner; this is not evidence of a latency gain. Health after the unobserved transition was not checked, so no unchanged-HP claim is supported.

A prior Lion probe took 11,057 ms, started in the field at 876/1186 HP with Lisa at 319 m, then refused Food before sending input. Its old wrapper returned without verified pause. Root immediately ran a guarded Windrise recovery in 11,252 ms without an unused permit, movement, look, or F: the guardian sent one B, Food was verified, and idle was confirmed.

The latest guarded Food probe completed in 8,141 ms. Escape was sent once; the transition frame had no HP evidence, then a fresh field observation showed Amber at 876/1186 HP, Lisa at 319 m, no enemy bars, and compass 95. One local GPS-anchor query took 112 ms and was accepted near Windrise, about 1.65 m from the anchor. The next field observation again showed 876/1186 HP; one B produced durable Food proof, idle, and verified final pause. Cleanup took another capture, so the field probe frame and result field frame differ. This validates the guarded Food and anchor checks in this case; it does not establish travel, arrival, healing, or quest completion.

The Statue F guardian now rejects map-only proof and waits for normal field then Food evidence; the Lion wrapper owns initial known-field refusal. Recorded Statue Space fixtures and transient-map regressions passed, but the updated Space/Leave handler has not been executed live since that change; the human had already advanced the dialogue. No new live combat has occurred.

A scoped cleanup removed 203 redundant unchanged Statue PNGs (468,681,471 bytes, about 447 MiB). All JSON was retained, along with reviewed samples and action/final proof images. No app, game, RDP, or script restart occurred.

## Validation

The shared bounded-key and Alt-click/Wolf-jump loops now compute remaining time once and break when it is <=0. Clock-jump regressions confirm there is no negative sleep, matching-key release still occurs, and pause is verified.

Module caching now caches code definitions only. Every readiness check still reads fresh `Date.now()`, focus, session, and current-frame evidence and enforces the 1,000 ms age limit. A three-hold regression used one Windrise module read; after a successful post-guard observation, the deterministic capture age advanced to 1,001 ms. The next W hold was blocked with `currentFrameValid=true` and `fieldReady=false`, and pause was verified. This confirms the cache does not weaken readiness checks; it does not show a measured live speed gain.

Before the cache update, three live eight-hold batches took 30,096 ms (Lisa 391→375 m), 26,937 ms (375→358 m), and 39,110 ms (358→337 m). HP stayed at 876, no enemy bars were seen, and each batch verified pause. Later cache-enabled travel took 22,413 ms for four holds (Lisa 337→326 m) and 19,311 ms for two holds (326→324 m); both retained 876 HP and verified pause. A subsequent timer failure took 16,874 ms: two W down/up events occurred, but only the first await succeeded, so the receipt reports one movement (Lisa 324→320 m), HP 876, and verified pause. Do not treat this as one input. These timings are not a speedup comparison. The cache source was hotloaded while paused.

The current JavaScript suite passed **1,017/1,017 tests across 120 matching files**, with 0 failures. Node duration was 28,219.3542 ms; wall time was 28,331 ms. It excluded only the unintegrated `Test/ActOnePilot/lion-domain.test.cjs`. Focused recorded-fixture and regression suites passed: 45 Windrise, 22 Lion, and 20 pure guardian tests.

Earlier live combat attempts had unsafe pause failures and HP loss; the shared guardian now covers those post-unpause failure paths. A prior native starter-fight attempt killed at least one slime, but did not establish that the area was clear. The Lion entrance has not been validated, Prologue Act I is incomplete, and the Lisa objective remains in progress.
