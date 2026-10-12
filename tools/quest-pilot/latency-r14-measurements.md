# r14 observation latency benchmark

## Matched paused-state trials

Three interleaved pairs compared four separate observation requests with one local burst containing four observations. Every trial used the same paused scene, sent no game input, performed no restart, and captured exactly four frames. Measured shell wall time includes client startup, requests, polling, status checks, heartbeat, and quiescence. Model deliberation time was excluded.

| Pair | Mode | Requests | Wall time | Observation pipeline sum | Wall minus observation sum |
|---:|---|---:|---:|---:|---:|
| 1 | Separate | 4 | 4,945.0 ms | 765 ms | 4,180.0 ms |
| 1 | Burst | 1 | 2,005.4 ms | 909 ms | 1,096.4 ms |
| 2 | Separate | 4 | 4,735.3 ms | 873 ms | 3,862.3 ms |
| 2 | Burst | 1 | 1,964.9 ms | 846 ms | 1,118.9 ms |
| 3 | Separate | 4 | 5,040.3 ms | 969 ms | 4,071.3 ms |
| 3 | Burst | 1 | 1,986.5 ms | 911 ms | 1,075.5 ms |
| **Mean** | **Separate** | **4** | **4,906.9 ms** | **869.0 ms** | **4,037.9 ms** |
| **Mean** | **Burst** | **1** | **1,985.6 ms** | **888.7 ms** | **1,096.9 ms** |

In this protocol, burst mode reduced measured shell wall time by **59.5%** and request count by **75%**. The observation pipeline sum was 19.7 ms (2.3%) higher in burst mode, so the wall-time gain did not come from faster capture/OCR. The wall-minus-observation remainder fell by 2,940.9 ms, combining client and protocol handling; the available measurements cannot divide that remainder among startup, polling, status checks, heartbeat, and quiescence.

These are three trials per mode on one host and release. The initial separate-first then burst run was excluded because order effects were observed. This is a paused-state observation benchmark, not a gameplay or quest-completion speedup. Model time is excluded.

## Saved frame timings

| Frames | Count | Capture mean | Legacy OCR window mean | PNG write mean | Total mean | Total p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| 1–291 | 291 | 2.9 ms | 279.7 ms | 57.4 ms | 400.7 ms | 366 / 778 ms |
| 292–350 | 59 | 2.9 ms | 293.9 ms | 59.5 ms | 428.8 ms | 363 / 945 ms |
| All saved frames | 397 | 2.9 ms | 284.3 ms | 57.7 ms | 399.5 ms | 355 / 778 ms |

The 59-frame window does not establish a capture/OCR speedup. These adjacent windows are not a controlled comparison. Proposed OCR cropping remains unmeasured.

The legacy `ocrMs` timer is a cumulative window. When fallback crops run after PNG writing and map lookup, that window includes those intervening operations. Its stage fields overlap and cannot be added as exclusive costs. For example, frame 449 reported `ocrMs` 363 ms and PNG 76 ms within a 376 ms total. The matched benchmark above uses shell wall time and the complete `totalMs` pipeline, so this timer defect does not invalidate the 59.5% result. Future OCR comparisons must use a separately timed recognition-call metric.

The corrected instrumentation was hotloaded at idle frame 461 without restarting the script or application. `ocrFindMultiMs` now accumulates only the native OCR `findMulti` call duration; `ocrReadCount` counts those calls and resets with each observation. Image preparation, row extraction, disposal, PNG writing, and map lookup are outside this timer. A fake-clock regression verifies that a 100 ms PNG write is excluded and counters reset between observations. After two additional proof regressions, the complete published test selection passed 614/614 in 3,505.6 ms.

Live frames 462–469 populated the new fields. For example, frame 467 recorded four OCR calls taking 339 ms, a legacy OCR window of 429 ms, PNG writing of 79 ms, and 441 ms total. Frame 468 recorded three OCR calls taking 259 ms and 360 ms total. These are instrumentation checks in different game states, not an OCR speedup comparison.

## Live grouped-action validation

Two bounded glide requests used four and then one observed W400 holds, taking 5,837 ms and 2,344 ms by receipt. The second reported a fresh grounded landing at frame 460. Both ended with verified automatic pause, and Kaeya's health stayed at 1063/1427. An earlier wind-ride request visually took off but its receipt did not verify takeoff because overlapping OCR duplicated the Space label; the source fix and explicit pause recovery were root interventions.

The subsequent door-console request took 1,838 ms, sent one Continue and one F press, and ended paused. Its receipt correctly left `doorOpenVerified=false`; root visually saw the activated console and later the gate lifting. A later bounded W200 request took 913 ms and showed the fully open gate at frame 472, with health unchanged and automatic pause at 473. Door opening is root visual evidence, not a console-receipt claim. No traversal, quest completion, or Act I completion is inferred. These live outcomes validate bounded local actions, but there is no matched old-versus-new gameplay trial from which to calculate a quest speedup.

## Combat observation comparison

The prechange combat source from commit `5b707c8` and the updated loop were executed side by side with the same static healthy HUD, constant enemy bar, eight inputs (character selection, E, six normal attacks), no-progress stop, and verified pause. This is a deterministic fake-clock workload, not a live fight or quest benchmark.

Reproduce with `node tools/quest-pilot/benchmark-combat-observations.cjs <prechange-combat.js>`, passing the `combat.js` source from commit `5b707c8` as that file. The benchmark does not connect to BetterGI or send game input.

| Simulated observation cost | Old observations | New observations | Old elapsed | New elapsed | Saved |
|---:|---:|---:|---:|---:|---:|
| 20 ms | 17 | 11 | 3,190 ms | 3,070 ms | 120 ms |
| 300 ms | 17 | 11 | 7,950 ms | 6,150 ms | 1,800 ms |

The revised loop reuses the checked post-action observation for its next decision. A frame older than one second is recaptured before another input; health/UI checks, the four-second enemy-bar reacquisition window, input release, and operation caps are preserved. Regression coverage verifies frame reuse, stopping after unsafe post-hit health, and recapture when processing ages a cached frame.

In the first live attempt, the controller stopped before combat input because no enemy bar was recognized. After one bounded approach, the next live request issued character selection, E, and two normal attacks. The starts of E and the two attacks were 731 ms and 709 ms apart. Health stayed at 1063/1427, but an unrecognized English Hydro Amber tutorial interrupted the request, which stopped after 12,340 ms with pause verification false. Root added recognition for that exact tutorial, then a separate recovery request dismissed it once and verified canonical pause. This exercises the revised combat path but does not establish a matched live speedup or a completed fight.

The subsequent guarded approach initially sent Continue but no movement because Lv.5 appeared only in cropped OCR. Root corrected the full-frame/local-crop evidence mismatch and the receipt-metadata handling, then hotloaded the fix without restarting. The next approach sent one W500 hold (516 ms measured input), took 2,740 ms by receipt, preserved 1063/1427 health, and ended with verified automatic pause. Its receipt still reported `approachVerified=false`; distance and arrival were not verified.

The following live fight took 8,963 ms by receipt (8,891 ms inside the combat routine), issued eight inputs totaling 620 ms, and stopped after six normal attacks with no recognized damage progress. Health stayed at 1063/1427 and pause was verified. The combat routine made 11 observations, frames 527–537, in addition to two wrapper observations. Those 11 pipelines totaled 4,839 ms: native capture 29 ms, exclusive OCR calls 3,755 ms across 48 calls, and PNG writes 783 ms. These fields do not explain every part of combat elapsed time. There is no matched prechange live fight; this validates the revised observation count and safe stop, not enemy defeat or a live speedup percentage. The published test selection passed 624/624 in 3,555.6 ms, excluding the unintegrated Lion-preparation tests.

Later review found that a partially obscured 19 px bar became the old loop's permanent minimum. The recorded no-progress reason does not prove that every attack missed. The updated tracker resets on restored bars or multiple targets and tolerates the observed 128–130 px contour jitter using a 3 px threshold. After two attacks without recognized progress, an optional guarded local approach can send up to four released W250 pulses and two camera corrections capped at 32 px. Inputs use fresh same-session Trial Kaeya evidence and count against the existing action/time limits; no range, damage, or completion claim is inferred from bar width alone.

The update was hotloaded at pause frame 537 without a script or native restart. Published tests passed 641/641 in 3,295.5 ms, excluding the unintegrated Lion-preparation test. Repeating the simulated comparison above still produced 17 versus 11 observations with identical inputs and outcomes when the optional approach API was absent.

The first live approach-enabled fight took 22,400 ms by receipt (22,318 ms inside the routine), issued 21 actions including two W250 pulses and no camera correction, and reported 1,975 ms input. The routine made 24 observations, frames 540–563, in addition to wrapper frames 538–539. Routine pipeline sums were 12,987 ms: capture 66 ms, exclusive OCR 10,549 ms across 131 calls, and PNG writing 1,767 ms. These are cumulative measured costs in this attempt, not a matched speedup. Root visually saw depleted enemy bars and additional slimes; defeat and quest completion remained unverified. HP fell from 1063 to 873/1427 at frame 562, and canonical pause was verified at frame 563.

A second request stopped before any combat action because HP was below 60%. Its 1,098 ms receipt and zero routine presses omit the wrapper's Continue and subsequent automatic Escape: resuming exposed Kaeya to attacks, with 775/1427 HP observed at frame 566 and canonical pause verified at 567. This exposes a resume/recovery limitation, not successful autonomous combat. No user UI action or process/script/game/RDP restart occurred in these two requests; root mission choices and the source hotload were interventions. The encounter, Wolf quest, and Act I remain incomplete.

## Mission-log timing context

The append-only mission log contains 234 matched started-to-terminal intervals. Their first-start to latest-terminal window is 2 h 9 m 3.6 s. The union of mission intervals is 5 m 7.4 s; the remaining 2 h 3 m 56.2 s is unassigned wall time outside those intervals. This is paused/orchestration time in the log window. The records do not attribute it to model deliberation or user time, and the window is not the full session lifetime.

A grouped four-pulse movement mission took 4,301 ms by receipt, with 2,060 ms reported input. The timestamp interval between its started and terminal records was 4,241 ms. Four earlier single-action receipts totaled 5,334 ms but differed in direction and total input duration, so they do not support a speedup percentage. The grouped movement outcome did not verify its target; no quest completion is implied.

## One-shot burst recovery measurement

After the low-HP stop at frame 567, source for a bounded one-shot Q burst recovery was hotloaded at canonical pause from `artifacts/hotloads/wolf-one-shot-burst-recovery-20261012-004354/manifest.json`, updating `bgi.js` and `mission.js` without a native, game, script, or RDP restart. The published test selection passed 654/654 in 4,058.0091 ms (`artifacts/wolf-burst-recovery-published-tests.log`).

Live mission `mission-cc6af44a93f34f34be888df18858e2f7` stopped after the bounded sequence in 3,911 ms by receipt (3,014 ms in the routine), including 294 ms reported input: one Continue, one Q60, and one Escape60, with no retries. HP was 731/1427 before and after the Q interval, but it had dropped from 775/1427 at frame 566 to 731 before Q during the resume interval. Therefore the evidence supports no observed HP loss during Q, not no loss during the entire recovery. Root observed a blue burst animation at frame 570, but its effect remains unverified. Canonical pause verified at frame 571 and the controller returned idle. A per-session `wolfBurstRecoveryQAttempt.json` marker was written before Q to prevent replay after report rolloff. The receipt does not verify burst effect, combat completion, or quest completion; normal combat still uses its 60% HP guard. This is one bounded live recovery, not a matched latency comparison or evidence of combat/quest success. Root-directed code changes, hotload, and mission selection remain interventions; no user UI action or process/session restart occurred.

A subsequent root-directed defensive Cryo E request, `mission-83d5c14cac5044a09c6d9c16b3c337b4`, took 1,233 ms and issued one guarded E. HP remained 731/1427 at frame 574; canonical pause was verified at 575. Root visual showed four living Pyro Slimes with partly red bars and damage labels. This defensive step did not invoke the enemy-bar detector, so its `enemyBars=[]` output is unmeasured, not a detector miss or evidence of defeat. A prior instrumented read at frame 573 found no anchored bar; the available evidence does not identify why. No repeated combat followed. This adds no matched performance result and does not verify burst effect, combat completion, or quest completion.
