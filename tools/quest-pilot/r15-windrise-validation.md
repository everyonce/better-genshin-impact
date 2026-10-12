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
## Bounded navigation evidence

`bgi.js` and `mission.js` were hotloaded while quiescent without native, script, game, or RDP restart. A live field probe took 7,561 ms and showed 876/1186 HP, Lisa at 319 m, empty enemy bars, a nearby GPS observation, and Food proof.

The first protected navigation run lasted 22,886 ms. It requested nine W holds (six 800 ms and three 250 ms; 5,550 ms total requested movement) and three camera turns. The resulting displacement was about 19.9 m; Lisa distance changed 319→298 m, HP stayed 876/1186, enemy bars remained empty, and Food plus idle proof were recorded. The runner correctly returned `destinationReached=false` and `questComplete=false`: its next OCR observations rendered Kaeya with accented variants rejected by the strict owned-character check. Five focused pure OCR tests for removing combining accents passed; the predicate still requires unique geometry and slot 3. This is partial measured progress, not destination arrival or quest completion.

A later 10,287 ms probe showed 876 HP, Lisa at 298 m, and Food proof, but queried GPS while the field HUD was fading. The deferred-query fix has now passed live: a 12,568 ms probe waited for a complete returned-field observation with world and grounded true, 876/1186 HP, Lisa at 298 m, no enemy bars, and compass 55.5 before issuing the native GPS query. Food and idle proof followed. No coordinates are included. The 12,568 ms and 10,287 ms runs differ in readiness path and are not a latency comparison. No human intervention occurred during these navigation runs.

The next protected leg completed in 21,387 ms end-to-end and arrived within 5 m of the local waypoint. It used seven W holds (five 800 ms and two 250 ms; 4,500 ms requested movement) plus two horizontal mouse offsets (−202 and −81); measured runner input time for movement and turn awaits was 4,925 ms. Lisa distance changed 298→280 m, HP stayed 876/1186, enemy bars remained empty, and Food plus idle proof were verified. The navigation status was `arrived` and `destinationReached=true`, while `questComplete=false` because Lisa had not been met. There was no travel restart or human input. This establishes waypoint arrival for this leg, not quest completion or a comparative speed gain.

The climb-release JavaScript suite passed **1,057/1,057 tests across 125 matching files**, with 0 failures; Node duration was 20,857.3746 ms and wall time 20,934 ms. It excluded the unintegrated `lion-domain` and `lion-combat` tests. Full output is in the local run log `artifacts/r15-lisa-climb-full-tests.log`.

A separate API regression corrected a misleading mock: native `GetPositionFromMap` returns `Point2f` x/y without a map label (`Genshin.cs` line 417). The test failed before the mock was corrected and passes in the full suite.

## Paused-position refresh and storage cleanup

A paused-position refresh took 6,963 ms and used Escape+B only. It returned a fresh field at Lisa 181 m, HP 876/1186, camera 55.5, no enemies, with Food proof and idle confirmed. A 32 ms native GPS query (667 ms total observation time) used a seed from an earlier paused navigation receipt only to search for an anchor within 25 m; the seed was not used for movement. HP was unchanged. There was no combat, human input, root desktop input, or restart; `bgi.js` and `paused-navigation-anchor.js` were hotloaded once.

The next two protected legs arrived within 5 m of their local waypoints in 16,773 ms and 19,826 ms. They used nine and eleven bounded forward holds, respectively, and one camera turn each. Lisa distance changed 181→165→143 m. Both recorded unchanged 876/1186 HP, no jump or climb recovery, `questComplete=false`, and fresh Food proof before returning idle. These show live navigation with the added party OCR crops and refreshed GPS seed; they do not establish a measured speedup or quest completion.

Five stale build copies were retired after user data had been copied and hash-verified, reclaiming 4,913,213,473 gross bytes. The original r8 copy remains because the user copy still needs 17 GB; its partial copy was removed. Available space is 4.75 GiB. This reports completed cleanup evidence only.
## Cliff approach and climb release

The live seven-hold navigation leg plus one look took 16,666 ms and stopped when climbing was detected. Lisa distance changed 143→126 m, HP remained 876, and Food/idle proof was obtained. The scoped climb-release mission took 6,653 ms and issued Escape, X, then B only; it sent no W, Space, party selection, or combat input. Evidence showed a fresh cliff position within 3 m, grounded and not climbing, HP 876/1186, Lisa 125 m, followed by Food and idle proof. A later −250 camera look took 6,719 ms with no movement or HP loss; Food and idle were verified. The cliff was ahead and enemies were above, with no red bars detected and no combat. The cliff approach remains unresolved.

The climb release is narrowly gated by a paused navigation receipt whose reason is exactly climbing, saved climb-scene/HP/GPS evidence within 5 m, and a fresh live GPS check within 3 m. It sends one X only after consuming the attempt and reading it back, then requires a fresh grounded fix within 25 m. All errors after close go through the shared mandatory-pause guardian. Focused coverage passed: 30 adapter tests and 10 pure climb tests.

Sources `bgi.js`, `lion-field-combat.js`, and `lisa-climb-release.js` were hotloaded once without a script, native, game, or RDP restart. A local script-library rescan found nearby mining points but no continuous road path; teleport routing splits the near-matching path. Prologue Act I is incomplete, the cliff route remains unresolved, and the Lion has not been entered.

A five-hold retreat to the grassy base arrived within 5 m in 15,218 ms, retaining 876/1186 HP and verified Food pause. The next leg stopped after one turn and before any W because an enemy bar appeared. Amber was hit during the transition (820 HP at the last qualified field, then 805); Food pause was verified in 6,685 ms. Empty bars in the later screenshot were not interpreted as enemy clearance because an enemy was close enough for its head bar to be clipped.

The subsequent bounded native fight took 24,095 ms end-to-end and 15,218 ms in the native routine. Its 15,000 ms cooperative timeout was followed locally by verified Food pause and idle. The reward overlay supports at least one enemy kill, while the reviewed screenshot still showed two living enemies. Cleanup unnecessarily returned from Kaeya (821/1057 HP) to Amber (685/1186 HP, below the 60% threshold); this is a recovery defect to fix before another attempt. No healing food was available, only seven revival eggs. This validates the timeout-to-pause path in a live fight, not encounter clearance or quest completion.

## Lisa Statue retreat

Cleanup now pauses the current character without an automatic Amber switch. A new bounded Lisa recovery uses the native teleport to the already-unlocked Starfell Lake Statue. It permits a living low-health character and nearby enemies only while retreating to the map; Statue arrival and passive healing require a fresh grounded Lisa HUD, a native GPS fix within 20 m, and no detected enemies. It sends no movement, F, party, or combat input. Every error after inventory close or adoption of the paused map is owned by the shared guardian until fresh pause proof exists.

The first live request took 8,588 ms and refused teleport because the map had no Mondstadt title. It returned with verified map pause. The revised gate uses the canonical Starfell/Galesong regional labels and exploration anchors; a sanitized regression from that real map covers starting recovery directly from pause.

The next request took 25,779 ms end-to-end, including 7,031 ms in native teleport. It verified a Starfell GPS position about 6.6 m from the Statue, Lisa at 908 m, Amber still 685/1186 HP, and no enemies. The bounded passive-healing wait did not reach 95%; Food pause and idle were verified before diagnosis. Teleport is live-validated, while full healing and subsequent travel remain pending. Two source hotloads were used; there was no script, native, game, or RDP restart and no human input.

The final suite for this wave passed **1,081/1,081 tests across 127 files**, with 0 failures, Node duration 23,539.3922 ms and wall time 23,616 ms. It includes 16 recovery adapter tests and 8 pure runner tests. It excludes the two unintegrated Lion drafts. Output is preserved locally at `artifacts/r15-lisa-statue-full-tests.log`.
## Validation

The shared bounded-key and Alt-click/Wolf-jump loops now compute remaining time once and break when it is <=0. Clock-jump regressions confirm there is no negative sleep, matching-key release still occurs, and pause is verified.

Module caching now caches code definitions only. Every readiness check still reads fresh `Date.now()`, focus, session, and current-frame evidence and enforces the 1,000 ms age limit. A three-hold regression used one Windrise module read; after a successful post-guard observation, the deterministic capture age advanced to 1,001 ms. The next W hold was blocked with `currentFrameValid=true` and `fieldReady=false`, and pause was verified. This confirms the cache does not weaken readiness checks; it does not show a measured live speed gain.

Before the cache update, three live eight-hold batches took 30,096 ms (Lisa 391→375 m), 26,937 ms (375→358 m), and 39,110 ms (358→337 m). HP stayed at 876, no enemy bars were seen, and each batch verified pause. Later cache-enabled travel took 22,413 ms for four holds (Lisa 337→326 m) and 19,311 ms for two holds (326→324 m); both retained 876 HP and verified pause. A subsequent timer failure took 16,874 ms: two W down/up events occurred, but only the first await succeeded, so the receipt reports one movement (Lisa 324→320 m), HP 876, and verified pause. Do not treat this as one input. These timings are not a speedup comparison. The cache source was hotloaded while paused.

Earlier focused recorded-fixture and regression suites passed: 45 Windrise, 22 Lion, and 20 pure guardian tests. The latest full-suite result appears above.

Earlier live combat attempts had unsafe pause failures and HP loss; the shared guardian now covers those post-unpause failure paths. A prior native starter-fight attempt killed at least one slime, but did not establish that the area was clear. The Lion has not been entered, Prologue Act I is incomplete, and the Lisa objective remains in progress. The pause guardian holds indefinitely until fresh proof is available.
