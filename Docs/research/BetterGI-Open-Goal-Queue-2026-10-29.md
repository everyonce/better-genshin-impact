# Choosing new goals during gameplay on SIREN

The destination controller can start with an initial batch, a gameplay-time target and hard ceilings. It does not require the final number of goals or batches. The approved map remains the Mondstadt stairs, sidewalk junction and west lamp. G4 checks photos, BetterGI verifies position and release, and the resident GPU Open P2P model supplies route-compatible input. A live RDP pair is admitted only if its process IDs, Windows sessions, roles and nonces match the previously sealed owner manifest.

## How the selector uses gameplay

After a native action actually executes during the active batch, the producer can publish **one** next decision. It considers legal sequences of four, three or two goals that fit the remaining physical legs. It first balances the cumulative requested station counts, then verified station counts and approach directions. It favors more traversed legs on a tie, with station order rotated by the witness frame. It stores its input counts, witness, clock, selected destinations and reason separately from the request payload. An independent implementation recomputes the decision from the original input receipts and admitted plans.

Gameplay time is the span from the first applied input’s native dispatch to the current applied witness’s dispatch on the same Windows performance-counter clock. Loading the model contributes no time. The time target asks the producer to finish the batch that is already under way. The wall deadline, 78 °C cutoff, lost telemetry, lost owner, operator stop and input-freshness limits still interrupt the resident. Exhausting the batch or leg budget has a different outcome from achieving the time target.

## Finishing without granting another input

A finish packet occupies the same immutable next slot as a successor plan. It is joined to the previous slot, original run and owner epoch, real applied input, decision bytes and publication clock. It has no destination and grants no movement. The resident can consume it only after verifying the final requested photograph, endpoint release, settled source observations and all earlier receipts. A stale, invalid or missing slot cannot complete the job. The terminal audit checks that the finish carries the original endpoint evidence and that there are no later proposals or applied actions. A pause or operator stop before this boundary interrupts the job even when the producer already published a finish.

The supervisor checks operator cancellation every 50 ms. A separate worker samples GPU telemetry at the existing two-second cadence. A failed GPU query, temperature at or above 78 °C, or six seconds without a completed fresh sample triggers a stop. The supervisor joins its last sample before awarding completion. Slower telemetry cannot hold up delivery of an operator stop to the resident.

## Live RDP evidence

All folders below are under `artifacts/live/2026-10-29-open-queue`. The launcher's `handoff-audit.json` and separate row-by-row replay use native receipts, observation and policy traces, compact run summaries and exact retained photos. Wall time includes cold start. Verified route time is measured between native in-game observations.

**20-second pilot.** `pilot/batches-20261029T173426Z-7161c9ac1062` completed eight requested and G4-verified station photos across eleven physical legs on one model load and controller lease. The second batch was selected in flight. A real dispatch 27.001 seconds after the first earned the target, and finish was consumed at settled frame 1203 after 42.6 seconds of verified navigation. All 371 applied inputs belonged to the admitted run and none followed finish. The cross-batch input gap was 603 ms. Median model evaluation was 30.69 ms, median capture-to-input dispatch was 76.42 ms, and the hottest sample was 64 °C.

**Missing decision.** `withheld/batches-20261029T173827Z-5f1fc1d14451` started at the sidewalk junction and received only the two initial orders. It photographed the west lamp and stairs across three physical legs and 110 applied inputs. The exact stairs photo was frame 367. After the one-second deadline the resident reported `warmQueueStarved`, emitted zero further proposals and finished the native stream with zero pending inputs, an empty tracked input state and a release receipt. The GPU peaked at 61 °C. The launcher returned exit 1 and the independent failure replay retained `passed=false`.

**Handoff timing.** On the pilot’s seven transitions between goals, the final settled photo’s Windows Graphics Capture timestamp to the next native input dispatch had a 186.83 ms median and a 204.98 ms maximum. Measured from the previous native release acknowledgement, the corresponding intervals were 536.40 and 538.36 ms. Between those two starting timestamps BetterGI collected the required fresh pose observations. Both intervals end at native software dispatch.

**Sustained 210-second target.** `sustained/batches-20261029T173956Z-841251b33a44` reached its target on an applied dispatch after 211.405 s. It consumed the explicit finish after the sidewalk junction photo at frame 6391. Native replay verified 227.105 s of navigation, 44 of 44 requested photos and 59 physical legs. One load and one controller lease served eleven walking batches. Ten successors used four distinct ordered sequences. The stairs and junction each received fifteen requested photos, and the lamp received fourteen. All were verified without a photo retry or another release command. The 18.52 s model cold start preceded the first dispatch.

| Sustained measurement | Result |
| --- | ---: |
| Original model evaluations | 1,952 |
| Applied actions | 1,946 (390 Open P2P, 1,556 native navigation) |
| Median model evaluation | 30.54 ms |
| Capture to applied dispatch, median / maximum | 75.33 / 149.89 ms |
| Consecutive applied dispatch gaps, median / maximum | 99.84 / 809.71 ms |
| Ten cross-batch input gaps, minimum / maximum | 596.54 / 809.71 ms |
| GPU peak | 65 °C |

There were 43 transitions between completed and subsequent goals. From native release acknowledgement to the next applied dispatch they consumed 24.417 s total, with a 537.42 ms median and a 738.52 ms maximum. Of that total, 16.818 s elapsed before the qualifying photographs were captured. From the settled photo capture to the next native dispatch the total was 7.599 s, median 177.32 ms, 95th percentile 199.71 ms and maximum 216.18 ms. No consecutive dispatch gap anywhere exceeded one second. `independent-open-queue-replay.json`, `independent-timing.json` and `independent-request-timing.json` retain the separate clocks and denominators.

**Operator cancellation.** `operator-stop/batches-20261029T174459Z-c45ab5031a1c` applied the first actions for goal five in batch two, then the external operator drill wrote the lease's STOP file. The file-to-addressed-control interval was 31 ms on the launcher monotonic clock. Windows performance-counter samples around the addressed write put native software release 86.366–87.796 ms later, giving an estimated 117–119 ms end to end. The previous fixed-batch drill took 1,359 ms to address and another 183–184 ms to release. During propagation the game controller accepted one camera-only proposal 12.124 ms after the write and began its dispatch at 12.203 ms. It was cancelled. All receipts resolved and final release reported zero pending or held inputs. Four photos and seven legs had completed. Goal five was interrupted and the verifier recorded `stopVerified=true` and `passed=false`.

Final read-only discovery found the same R56 host (PID 10124) and R57 RDP child (PID 21240). The RDP window was minimized, the game was ready, and the task and agent stream were idle. The final GPU sample was 56 °C. The local .NET 10 Debug solution build succeeded and all 447 distinct regression tests in the selected navigation, model, release and audit suites passed.

## Next gameplay transition

The next bounded task is to open the world map at the verified junction, recognize its close control, close it, reverify the world HUD and junction, and continue to the west lamp. BetterGI already has map-opening and native map-recognition code in `TpTask.cs` and `NavigationResetMapRecovery.cs`. It needs a lease-owned command that preserves the original UI images and input receipts across the transition. Natural recovery from the previously observed stairs photo miss still requires its own live evidence. The current runs continued using qualified G4.
