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

## Mission-log timing context

The append-only mission log contains 234 matched started-to-terminal intervals. Their first-start to latest-terminal window is 2 h 9 m 3.6 s. The union of mission intervals is 5 m 7.4 s; the remaining 2 h 3 m 56.2 s is unassigned wall time outside those intervals. This is paused/orchestration time in the log window. The records do not attribute it to model deliberation or user time, and the window is not the full session lifetime.

A grouped four-pulse movement mission took 4,301 ms by receipt, with 2,060 ms reported input. The timestamp interval between its started and terminal records was 4,241 ms. Four earlier single-action receipts totaled 5,334 ms but differed in direction and total input duration, so they do not support a speedup percentage. The grouped movement outcome did not verify its target; no quest completion is implied.
