# Recognizing the Mondstadt stairs across changes in lighting

**G4 remains the qualified photo observer.** G6 avoided one real stair error on a fresh lease and introduced another on an independent historical original. G7 and G8 each tied G4 at 41/41 in separate prospective comparisons. In actual goal-directed gameplay, G4 completed all eight requested stair returns on arrival.

G4 sometimes mistakes the stairs for the sidewalk junction even when BetterGI’s map pose is stable. The original failure occurred on the fifth goal of a live destination run. Four original images spanning 905.5 ms, including all three stationary retries, were classified as the junction. The native position remained 0.43 map units from the stair anchor at 105°. Those four images belong to one arrival. The [earlier run report](BetterGI-Continuous-Batches-2026-10-29.md) records the failed request and its input release.

## Frozen color comparison

G6 retained G4’s 168 templates and center-image sampling grid. For each template it subtracts the mean difference in each RGB channel before comparing the remaining spatial pattern. This makes it less sensitive to an overall color shift while preserving the location of color boundaries. The original 34 development images include the four correlated stair misses. G6 corrected those four and retained the other 30 labels. Its checkpoint was fixed before the comparison, at SHA-256 `4c347fc40796ccd33248982e5979273d10e6dd2afed45e8f2d5be7b8f1f7e446`. A regression verifies that giving the photo-task launcher G6 with G4’s valid qualification fails before the GPU adapter starts.

## Older leases outside G6 development

The evaluator fixed the whole-lease list before scoring. Nine historical leases contained 233 native station observations. One had five dropped recording frames and failed the source-integrity audit. All its data remains retained, with zero scored images from that lease. Eight eligible leases remained, disjoint from 23 recorded training, promotion and development source windows. These are retrospective comparisons. The old photo collector preferentially saved successful photos, so the exact-PNG panel does not estimate the natural miss rate.

| Historical source | Station | G4 | G6 |
| --- | --- | ---: | ---: |
| Lossless original | Junction | 7/7 | 7/7 |
| Lossless original | Stairs | 9/9 | 8/9 |
| Lossless original | Lamp | 9/9 | 9/9 |
| Independently decoded H.264 | Junction | 104/104 | 104/104 |
| Independently decoded H.264 | Stairs | 57/60 | 57/60 |
| Independently decoded H.264 | Lamp | 50/52 | 52/52 |

The overall decoded score increased from 211/216 to 213/216. G6 fixed two decoded stair errors and introduced two others. The number of entirely correct decoded leases fell from seven to five. On the original pixels, frame 10 of the `b254d2f5` lease was a new stair-to-junction error. Five natural live G4 misses occurred in a single historical lease. Their video survives, but there are no exact PNGs for those five images. Keep the two evidence domains separate.

## Prospective source collection

`run_patrol_series.py --retain-station-rgb` records a lossless original at each verified native start and arrival on an explicitly requested fixed patrol. The flag requires a shadow recognizer and a run without photo objectives. The post-run audit joins each image to its source timestamp, frame, native station, readiness and controller epochs, pipe identity and exact live prediction. The original and a wrong prediction are retained together. The collector uses the existing recorder and byte limit. Its evidence gives the observer no additional input or photo authority. `--owner-from` checks the original RDP session IDs, process IDs and nonces before admission.

The fresh G6 lease recorded all 41 native station views over 40 legs in 152.22 seconds. All 41 exact G6 labels and distances reproduced the live observer. G4 scored 39/41 and G6 scored 40/41 on the same original images. Their respective predictions also matched on the decoded recording. Both recognized the junction 20/20 and lamp 10/10. At the stairs G4 scored 9/11 and G6 scored 10/11. Both called the start view the junction. At frame 1733 the player returned from the junction to the stairs. G6 recognized this arrival and G4 missed it. This was a fixed patrol, so the shadow prediction did not repair a goal. GPU temperature peaked at 63 °C. Median and maximum capture-to-first-dispatch ages were 82.61 and 144.71 ms.

The fresh lease passed the usual comparison criteria for G6 on both source domains, but the separate historical lossless stair regression remains. A single-lease comparison cannot grant an experimental metric family photo authority. A real photo launcher regression exercises matching, valid single-lease qualification data and confirms that experimental G6 and G7 are still confined to observing.

On a separate synthetic diagnostic, each of the 41 original images was also brightened, darkened, warmed, cooled or shifted in green by 12 byte levels with clipping. G4 remained correct under all six shifts on 37 original images. G6 did so on 40. The synthetic changes count toward neither live performance nor qualification. Evidence for these comparisons is in `artifacts/live/2026-10-29-stairs`, including `retrospective-corpus.json`, `retrospective-scores.json`, `g6-paired-prospective/episode-audit.json` and `g6-synthetic-lighting.json`.

## Retaining part of the color signal

One color weight fits both known failure patterns on the development examples. With 0 meaning full channel centering and 1 the original G4 metric, every true station was strictly closer than every competing class for weights between 0.30644 and 0.61050. The calculation takes the nearest template in each class into account. G7 uses the simple weight 0.5 and the same 168 templates. It correctly classified the 35 exposed originals, with a smallest distance to a competing class of 0.02853 above the winning distance. The source of the new historical counterexample and the original failure leases are all excluded from G7 evaluation.

G7 checkpoint SHA-256 is `99531706a59ce3e53156f0ad1a4532292e375d1ed783ba49bc82653ebce1e3c6`. It was frozen after G6’s prospective lease began. That entire lease is excluded from G7 qualification. Its standalone scorer preserves the frozen G4 and G6 code.

On seven development-disjoint, admissible historical leases, G7 and G4 each scored 22/22 on the available originals. G7 improved the decoded total from 194/199 to 196/199. It introduced one decoded stair error in a previously perfect episode for which the original pixels are unavailable. In G7’s separate prospective ten-circuit lease, G4 and G7 each scored 41/41 on originals and video. All 41 original predictions and distances reproduced G7’s live results. This lease began 382.39 seconds after freeze, covered 154.28 seconds of verified navigation and peaked at 63 °C. The strict improvement requirement retained G4.

## Actual directed stair-photo test

The first launch stopped before loading a model or sending input because a worker loaded incompatible photo-validator caller and callee versions during a code update. The failure remains at `directed/batches-20261029T171027Z-5d8964d21b18`. The corrected launcher recomputed G4’s original qualification before acquiring a new lease. Source files for the next launch were held fixed. The final compatibility fix also accepts the old call form for exactly the canonical G4 digest and recomputes its original qualification. Tests verify that an altered qualification, near-match digest or experimental metric fails closed.

Qualified G4 completed 16 requests over 24 legs in 85.16 seconds. Four independently supplied batches alternated the junction or lamp with returns to the stairs. Every one of the eight requested stair images matched on arrival. The three cross-batch input gaps were 604, 608 and 609 ms. Open P2P supplied 141 of 724 software input requests, median evaluation took 30.79 ms, and the median capture-to-dispatch age was 74.04 ms. Peak GPU temperature was 62 °C. There were no stationary retries in this trial. The prospective G6 shadow correction and the earlier scheduled two-view confirmation remain distinct from rescuing a naturally failed live goal. Raw requests, original PNGs and independent timings are at `directed/batches-20261029T171152Z-c690c1063691`.

## Testing one additional stair reference

G8 retains G5’s v1 metric, labels and ordered bank of 177 templates. G5 recognized 40/41 original images in the G6 episode. Its only error was the initial stair view at frame 24. G8 added that one native-verified original, bringing the bank to 178 and the training score to 41/41. The entire G6 episode became G8 training data. G7’s prospective episode was excluded. G8 was frozen at SHA-256 `02dd82f1146861f683c74da963e5717aba65bf5a90149437a30e57145631a0fc`.

G8 and G4 each scored 22/22 on the fixed historical original panel. On the 199 decoded images G8 scored 197, versus G4’s 194, with four corrections and one new error. The new error was a lamp classified as stairs in an already imperfect episode. No original was available to check that frame. All six previously perfect decoded episodes stayed perfect. The predeclared historical screen allowed one independent fresh trial.

G8’s single prospective lease began 116.91 seconds after freeze. It excluded 33 prior source windows, including the full G6 and G7 leases. On all 41 original images G8 and G4 tied, with 20/20 junction, 11/11 stair and 10/10 lamp views. All 41 live G8 predictions and distances reproduced from their original pixels, and both observers also scored 41/41 on the decoded recording. There were no wrong-station predictions in this episode. Both independent qualification results retained G4 for lack of a strict gain. The patrol verified 151.61 seconds of navigation over 40 legs, 1,297 applied software input requests and a peak GPU temperature of 64 °C. The median capture-to-first-dispatch age was 81.81 ms and the maximum was 147.60 ms. The earlier decoded lamp error remains unresolved.

The three prospective leases were separately admitted after each candidate’s freeze. The original R56 host and R57 game child remained in minimized RDP for all live trials. The C# release change from the preceding sprint was not installed in either process. Final read-only discovery reported a minimized host, `game_ready`, no running task and no controller stream.

## Recognizing a real recovery in a future goal run

`report_stationary_photo_recovery.py` replays each original PNG and the native release, pose, no-input and successor dispatch evidence. It distinguishes an initial classification miss followed by a qualified stationary image and a subsecond handoff from a deliberately requested second view, exhausted retries, or a correct later image without a verified handoff. Replaying the actual planned confirmation gave a 285.27 ms stationary interval and 905.32 ms handoff. Replaying the failed stairs arrival produced four original misses over 905.55 ms. Neither earned natural-recovery credit. A synthetic genuine miss followed by a correct image and a 986 ms handoff exercised the positive branch. An independently recorded real miss and recovery is still needed.

The final Windows regression run passed 434 tests. The full .NET 10 Debug solution build completed successfully. Both logs, all three sealed prospective leases, the directed trial and the read-only final RDP discovery remain under `artifacts/live/2026-10-29-stairs`.
