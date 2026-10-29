# Continuing destination batches on SIREN

A separate process can submit goals to the GPU model that is already walking in BetterGI's minimized RDP session. The resident initially receives just the first two to four requests, the maximum number of batches and the total leg budget. Each later batch has its own names, request IDs, starting station and destination order. It can only follow a real, applied action from the previous batch on this lease. The next batch starts at the previous batch's verified final destination.

## What the recording verifies

The sender freezes its intent and publishes a complete file without replacing an existing submission. The file names the resident, bridge session, owner epoch, preceding batch digest and its first-applied input witness. A second record brackets publication on the Windows performance counter. The resident checks the records and the exact submitted bytes before accepting the new requests at the released endpoint. Each request starts its own policy history and collects its own source image.

Independent replay reconstructs each batch from the sender's intent, joins it to the original action receipt and brackets the handoff on the native input and Windows Graphics Capture clocks. It reconstructs the actual surveyed legs, decodes the saved PNGs, checks the immutable visual checkpoints, and enforces the existing thermal, image-freshness, recording, input-release and stop checks. Input can resume only on a fresh observation. A missing batch leaves input released and times out after one second. All local evidence is under `artifacts/live/2026-10-29-batches` on SIREN.

## Separate sender and missing successor

The manual pilot began at the stairs with junction and lamp as its only two goals. After an input from the first batch had been applied, a separate process submitted junction and stairs. The publication witness traces to input on original frame 26. The resident accepted the submission at the lamp on frame 226. The last old input and first new input were 604.90 ms apart. The return to the stairs finished four goals and four legs in 15.41 seconds of navigation, with 135 applied actions, a single GPU load and a peak of 60 °C. Evidence is in `manual-repeat/batches-20261029T163444Z-22b249cd07bf`.

The first manual pilot failed because the sender expected the live status file to contain the Windows session ID. The running manifest supplies that field and the live status supplies the active child PID. The corrected sender cross-checks both against the pinned broker job and current RDP connection. In the failed pilot, the first batch finished at the lamp and the released resident sent zero further input proposals. Its original outcome is retained in `manual/batches-20261029T163221Z-5eb1b92b5b34`.

A separate negative test deliberately withheld batch two. The first two goals finished at the stairs. All 62 accepted inputs had retired by the final endpoint release. There were zero later proposals, and the terminal software release returned 1,051.57 ms after the final verified frame. The timeout and empty held-key state are in `withheld/batches-20261029T163338Z-a6f28bea2a5a`.

## Retained release race

The first sustained run stopped at the lamp during batch one. Frame 222 showed a native pose 0.83 units from the lamp with a ready world in epoch 2. The `released` reply reported epoch 3 and `world_observation_invalidated`. The controller requires a specific `client_release` acknowledgement, so it issued zero further proposals and did not credit the lamp. The terminal input state had no held keys. The original evidence is in `sustained/batches-20261029T163541Z-67844b21aba2`.

The bridge released input and obtained its readiness snapshot in separate critical sections. A delayed capture could change the readiness reason between them. The updated C# bridge takes the snapshot under the same lock as the release. The live trials continued to use the original R57 process. Its Python controller requires a fresh stationary observation and a new acknowledged release before it can credit an arrival after this race.

The R57 recovery is limited to this specific invalidated observation after native `releaseAll` returned. It requires an inactive input controller with empty tracked keys, the same capture and owner, two newer stationary source poses at least 80 ms apart, a second genuine `client_release` acknowledgement, and the usual three settled arrival frames. The retry window is 650 ms. The new C# bridge passed 17 readiness and wire tests plus the full Debug build. Neither live RDP process was replaced.

## Natural visual disagreement

The next attempt started at a freshly verified lamp and admitted a second batch. On its fifth request the character arrived 0.43 world units from the stair anchor, facing 105°. G4 called the original arrival and all three stationary retries the junction. The character held the same position and heading through frames 925, 934, 943 and 952, spanning 905.5 ms. The resident stopped and the fifth request remains incomplete. A decoded video frame would have called frame 943 the stairs. Independent scoring of the exact lossless PNGs reproduces all four misses. This genuine disagreement differs from the earlier [planned two-view confirmation](BetterGI-Destination-Requests-2026-10-29.md#continuation-and-repeat-visits). Evidence is in `sustained-repeat/batches-20261029T164113Z-82ec37606820`.

## Frozen observer comparison

G5 inherited G4’s 168 templates and feature rule. Nine original arrival images added three junction, four stair and two lamp references from two previous leases. The source verifier checks the saved PNG digest, the decoded RGB digest logged during the lease, the native release and settled pose. Only the original arrival from the four correlated misses entered the template bank. Its three retries belong to the same training lease and cannot count as independent evaluations.

The SHA-256 of the frozen G5 checkpoint is `02d386d0f085dc3facbf0613cf6a0d4a187a07044a6c1a462f9f580720d7a732`. The freeze record at `artifacts/agent/landmarks/g5-freeze/freeze.json` predates the holdout job. The promotion rule requires a fresh ten-circuit lease, at least ten unique source frames per station, no per-station regression versus G4 and strictly more correct predictions in total.

The holdout finished 40 legs in 154.70 seconds. All 41 unique station captures were distinct from training. On the same decoded frames G4 and G5 each scored 20/20 at the junction, 11/11 at the stairs and 10/10 at the lamp. G5 also agreed on all 41 live original predictions. Its median live evaluation took 0.463 ms. The strict comparison retained G4, which remained the photo observer for the following destination test. Artifacts include `g5-holdout/20261029T164557Z-5036ddea8321/audit.json` and `artifacts/agent/landmarks/g5-freeze/independent-holdout-audit.json`.

## Sustained changing goals

One resident completed 36 requested station photos over 63 walking legs in **242.31 seconds** from its verified start to its final verified photo at the junction. The sender supplied nine batches of four named goals. Each successor was published after an actual applied action in its predecessor. The original controller session and ownership epoch continued across all nine recording segments. The single GPU model load took 15.61 seconds before gameplay. The 28 unrequested station visits earned no request credit. The 36 requested photos passed on the first arrival observation.

| Measured on the original source and software input receipts | Result |
| --- | ---: |
| Eight cross-batch intervals between software input dispatches | 600.00–702.98 ms |
| Median consecutive dispatch interval | 99.89 ms |
| Longest consecutive dispatch interval | 911.67 ms |
| Median Open P2P evaluation | 30.84 ms |
| Median / maximum capture-to-first-dispatch age | 76.19 / 147.50 ms |
| Recorded source frames | 5,262 |
| Applied BetterGI / Open P2P input requests | 1,659 / 424 |
| Peak GPU temperature | 64 °C |

The benchmark exercised three surveyed Mondstadt stations. Each batch provided new destinations while BetterGI and the GPU model continued playing. The safe boundary still requires an explicit successor within the one-second deadline. A batch limit, input permissions and a wall-clock deadline are set before starting. Evidence is in `sustained-qualified/batches-20261029T164933Z-b286c0bfb0b3`, including `audit.json`, `handoff-audit.json`, `station-photos`, `batches` and `independent-timing.json`.

## Stop during the second batch

The stop drill started a fresh resident at the verified junction. It completed the first four requests over seven legs. Batch two was admitted and its first request received 17 applied actions before shutdown. The incomplete fifth request earned no photo or completion. The supervisor picked up its stop marker and published the addressed command 1,359 ms later. Windows performance-counter samples bound the interval from that write to native input release at 182.63–183.97 ms. One final W dispatch started 11.83 ms after publication, before the resident observed the command. The next proposal was suppressed when the control epoch changed. The terminal state had no active input and no held keys. `stopVerified` was true and the full-route `passed` flag was false.

Final read-only discovery confirmed the original R56 primary in session 1 (PID 10124) and R57 child in session 3 (PID 21240), the RDP window minimized, the game ready, and no active task or stream. The resident stayed stopped. Evidence is in `stop/batches-20261029T165425Z-6741984f8e38` and `final-discovery.json`.

The 398 focused Python regressions passed under Windows with native NTFS hard links enabled. The sandbox-only run denied the sender test’s temporary hard-link operation. Both test logs were retained. The .NET 10 Debug solution build and all 17 C# readiness and wire tests passed.
