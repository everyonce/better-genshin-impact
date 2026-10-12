# R15 Windrise validation

## Current travel safety

The shared pause guardian now owns every Windrise failure path after unpause. Paused-field witnesses are checked against saved image/JSON evidence and require the same camera within 5 degrees.

The first travel attempt made no look or movement input: the inventory was fading and field health was unavailable. The captured-only retry now waits for a strict fresh field observation rather than treating inventory disappearance as field proof. That attempt returned with pause verified in 6,249 ms; Amber remained at 876 HP, and no root pause was needed.

A stale-witness rejection (witness more than 120 seconds old) sent no input and left the game paused in inventory. This is a correct safety rejection, not a combat failure.

Two paused camera turns completed without movement or HP loss. The first took 14,811 ms end-to-end, changed compass 96→72 with one −250 look, and returned inventory proof. The second took 16,441 ms, changed compass 72→52 with one −200 look, and returned inventory proof. Two 500 ms forward holds then took 14,057 ms end-to-end, moved the Lisa objective from 406 m to 401 m, retained Amber at 876 HP, saw no red bars, and verified pause. A later paused look took 15,414 ms and changed compass 52→34.5 with Amber still at 876 HP and pause verified.

A later 12-hold plan stopped before hold six when its next readiness check failed. Five 500 ms holds had completed in 32,489 ms end-to-end; Lisa objective distance moved from 401 m to 391 m, HP stayed at 876/876, no red bars were seen, mandatory inventory proof was obtained, and no root pause was needed. The receipt does not record per-check age, so the precise cause is unproven; code and observation review suggest the 1,000 ms freshness limit expired between the post-hold and next pre-hold checks amid repeated file reads and evaluation. A subsequent request lost game foreground before any scripted input. Native focus recovery took 4,468 ms; a fresh read-only probe then verified pause in 11,864 ms, with no user action.

These end-to-end times include startup, captures, and verification, not just keypress duration. The bounded travel evidence shows progress over a short distance; it does not establish overall speed improvement or arrival. The game remains outdoors at “Meet Lisa.” A later Statue interaction opened the exact known English dialogue, “world opens... noble hearts.” Its mandatory guardian cleanup is still pending: it sent zero cleanup keys, has not returned, and has produced no final pause proof. The outer client timed out waiting for idle; this is neither a completed nor a failed cleanup result. Statue unlock is unconfirmed. A fresh capture still shows the dialogue.

## Validation

The shared bounded-key and Alt-click/Wolf-jump loops now compute remaining time once and break when it is <=0. Clock-jump regressions confirm there is no negative sleep, matching-key release still occurs, and pause is verified.

Module caching now caches code definitions only. Every readiness check still reads fresh `Date.now()`, focus, session, and current-frame evidence and enforces the 1,000 ms age limit. A three-hold regression used one Windrise module read; after a successful post-guard observation, the deterministic capture age advanced to 1,001 ms. The next W hold was blocked with `currentFrameValid=true` and `fieldReady=false`, and pause was verified. This confirms the cache does not weaken readiness checks; it does not show a measured live speed gain.

Before the cache update, three live eight-hold batches took 30,096 ms (Lisa 391→375 m), 26,937 ms (375→358 m), and 39,110 ms (358→337 m). HP stayed at 876, no enemy bars were seen, and each batch verified pause. Later cache-enabled travel took 22,413 ms for four holds (Lisa 337→326 m) and 19,311 ms for two holds (326→324 m); both retained 876 HP and verified pause. A subsequent timer failure took 16,874 ms: two W down/up events occurred, but only the first await succeeded, so the receipt reports one movement (Lisa 324→320 m), HP 876, and verified pause. Do not treat this as one input. These timings are not a speedup comparison. The cache source was hotloaded while paused.

The current JavaScript suite passed **990/990 tests across 119 matching files**, with 0 failures. Node duration was 46,119.6944 ms; wall time was 46,331 ms. The run excluded only the unintegrated `Test/ActOnePilot/lion-domain.test.cjs`. Focused suites passed: Windrise adapter **35/35** (included in the full suite), track-quest tutorial **6/6**, and Lion adapter **15/15**.

Earlier live combat attempts had unsafe pause failures and HP loss; the shared guardian now covers those post-unpause failure paths. A prior native starter-fight attempt killed at least one slime, but did not establish that the area was clear. The Lion entrance has not been validated, Prologue Act I is incomplete, the Lisa objective remains in progress, and Statue unlock is unconfirmed.
