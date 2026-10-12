# R15 Windrise validation

## Current travel safety

The shared pause guardian now owns every Windrise failure path after unpause. Paused-field witnesses are checked against saved image/JSON evidence and require the same camera within 5 degrees.

The first travel attempt made no look or movement input: the inventory was fading and field health was unavailable. The captured-only retry now waits for a strict fresh field observation rather than treating inventory disappearance as field proof. That attempt returned with pause verified in 6,249 ms; Amber remained at 876 HP, and no root pause was needed.

A stale-witness rejection (witness more than 120 seconds old) sent no input and left the game paused in inventory. This is a correct safety rejection, not a combat failure.

Two paused camera turns completed without movement or HP loss. The first took 14,811 ms end-to-end, changed compass 96→72 with one −250 look, and returned inventory proof. The second took 16,441 ms, changed compass 72→52 with one −200 look, and returned inventory proof. Two 500 ms forward holds then took 14,057 ms end-to-end, moved the Lisa objective from 406 m to 401 m, retained Amber at 876 HP, saw no red bars, and verified pause. A later paused look took 15,414 ms and changed compass 52→34.5 with Amber still at 876 HP and pause verified.

A later 12-hold plan stopped before hold six when its next readiness check failed. Five 500 ms holds had completed in 32,489 ms end-to-end; Lisa objective distance moved from 401 m to 391 m, HP stayed at 876/876, no red bars were seen, mandatory inventory proof was obtained, and no root pause was needed. The receipt does not record per-check age, so the precise cause is unproven; code and observation review suggest the 1,000 ms freshness limit expired between the post-hold and next pre-hold checks amid repeated file reads and evaluation. A subsequent request lost game foreground before any scripted input. Native focus recovery took 4,468 ms; a fresh read-only probe then verified pause in 11,864 ms, with no user action.

These end-to-end times include startup, captures, and verification, not just keypress duration. The bounded travel evidence shows progress over a short distance; it does not establish overall speed improvement or arrival. The game remains outdoors at “Meet Lisa.” No live combat has occurred since the user’s pause instruction.

## Validation

The current JavaScript suite passed **986/986 tests across 119 matching files**, with 0 failures. Node duration was 55,790.4609 ms; wall time was 55,965 ms. The run excluded only the unintegrated `Test/ActOnePilot/lion-domain.test.cjs`. Focused suites passed: Windrise adapter **32/32**, Lion adapter **15/15**.

Earlier live combat attempts had unsafe pause failures and HP loss; the shared guardian now covers those post-unpause failure paths. A prior native starter-fight attempt killed at least one slime, but did not establish that the area was clear. The Lion entrance has not been validated, Prologue Act I is incomplete, and the Lisa objective remains in progress.
