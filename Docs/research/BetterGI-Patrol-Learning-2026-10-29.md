# Learning from a live Mondstadt patrol

On SIREN, the R57 child and Genshin share the minimized BetterGI RDP desktop. A resident Open P2P model reads the native 192 × 192 game images on the RTX 2080 SUPER. BetterGI uses the map pose to steer along the current segment. A compatible movement proposed by Open P2P can execute directly. This route covers three surveyed stations and two different approaches to the junction. Its objective is to visit and identify the stations in order.

## Route and evidence

Each circuit runs from the stair front to the sidewalk junction, to the west lamp, back to the junction and back to the stairs. At each arrival the controller releases input and waits for stable native measurements in the new input epoch. The independent audit joins source frames, intermediate positions, applied steps, release receipts and station order. The image exporter joins each station to an original frame by capture epoch, frame ID and video presentation time.

The first complete circuit took 14.34 seconds, with 295 recorded frames and 120 applied actions. The next run completed six circuits in 90.97 seconds, with 1,899 recorded frames and 784 applied actions. Median Open P2P inference was 30.93 ms. Capture to input dispatch was 82.43 ms at the median and 149.41 ms at the maximum. The GPU reached 60 °C during that six-circuit run.

A longer attempt stopped after ten legs when Windows briefly denied access to the frequently replaced status file. The resident honored the addressed stop. The supervisor now pins the run identity once and monitors its private control file. Only initial sharing violations receive brief retries. Invalid control data still stops the attempt. The interrupted recording remains in its own evidence directory.

The retry completed all **24 circuits and 96 verified legs in 369.22 seconds**. One CUDA model load served 7,995 source frames. The bridge confirmed first software dispatch for all 3,167 accepted actions. Open P2P supplied 683 route-compatible actions. Native navigation supplied the other 2,484. Median policy evaluation was 30.67 ms. Capture to first software dispatch was 81.31 ms at the median and 146.61 ms at the maximum. Whole-GPU utilization had a median of 38%, and the thermal monitor observed a peak of 65 °C. The run ended on its requested leg count with input released.

Consecutive software dispatches were 99.92 ms apart at the median and 108.16 ms at the 95th percentile. All 95 gaps above half a second included a planned station release and its three confirmation samples. The longest gap was 819.42 ms at the west lamp, where a stale pose briefly delayed the release. Away from these station checks the longest gap was 302.28 ms. The run had zero gaps of one second or longer.

## What the models learned

**Steering.** A small CPU head learned three actions from 500 receipt-backed interventions in three earlier gameplay runs. Its eight input features include the native bearing and range as well as the original Open P2P action. On a separate stair-post lease, generation one matched 1,642 of 1,679 native decisions. Adding the first street circuit to the training set reduced that result to 1,641. On the six unseen street circuits the generations scored 597 and 596 out of 612. Generation one remained the live observer. The deterministic native rule is the teacher and still owns steering when the visual proposal is incompatible.

**Camera response.** Sixteen isolated training turns and six fresh holdout turns measured how much yaw followed a short horizontal mouse pulse. The fitted gain was 0.09383 degrees per count. All six held-out signs were correct. Mean absolute error was 0.545 degrees against 0.500 for a fixed 0.100 gain. The candidate missed its adoption threshold and the checkpoint loader refuses it for control.

**Station appearance.** A separate CPU classifier compares a small color grid taken from the center of each image. Native position supplies the training label. The classifier receives only the image at inference. Generation one learned from the first circuit and generation two also learned from the six-circuit lease. Both checkpoints were frozen before the long run. To prevent repeated station visits from inflating the sample, the primary comparison counts each source image once. Each generation also receives a score for each station and approach.

On the 24-circuit run, generation two predicted the junction for every live frame. It identified all 48 junction arrivals and missed all 25 stair views and all 24 lamp views. Median live classification took 0.413 ms. Independently decoding the 97 arrival frames from video reproduced every class prediction. For steering, generation one matched 2,351 of 2,410 eligible native labels and its 3,176 online predictions reproduced offline. The patrol completed using the native verification and hybrid controller.

The paired held-out comparison showed that landmark generations one and two both scored 48/97. The selection gate retained generation one. The long run's center-image color means were darker and bluer than either training run. Generation three uses the same feature and distance rule, with 127 unique training views from the three completed leases. Its checkpoint was frozen before collecting the next evaluation lease.

The next ten circuits completed 40 legs in 153.68 seconds, with one model load, 3,253 source frames, 1,325 applied actions and a 62 °C peak. Generation three recognized 40/41 distinct live station images at a median of 0.449 ms per image. The decoded video reproduced all 41 predictions. On those same images, generation one scored 20/41. Generation three recognized 11/11 stair views, 10/10 lamp views and 19/20 junction views. The predeclared gate retained the incumbent because its junction recall had been 20/20. That result prompted one additional generation using the newly verified views and another independent lease.

**Generation four qualified as the station observer.** It learned from 168 unique views and scored 40/41 on a further ten-circuit holdout. Per-station scores were 20/20 at the junction, 11/11 at the stairs and 9/10 at the lamp. Generation one scored 20/41, with zero correct at the stairs and lamp. Every station therefore met the gate. Frozen generation three produced the same class scores as generation four on this particular lease. Independent decoding reproduced all 41 live G4 predictions. This run took 154.58 seconds, dispatched all 1,336 accepted actions and peaked at 62 °C. Its median image-to-dispatch time was 80.55 ms.

## A task the recognizer can perform

The photo collector accepts named stations on this route. When the character arrives, it compares the independent image prediction with the native station and saves the original RGB image only on agreement. Before collection, the runtime recomputes the observer's promotion from the hash-bound paired evaluation. After the task, another verifier joins the photo to the original native event, checks the decoded PNG pixels against the RGB hash and runs the frozen recognizer on those pixels again.

The first live task collected the stair front on frame 24, the junction on frame 103, and the west lamp on frame 218. All three matched at the first opportunity. The patrol finished three full circuits in 44.69 seconds with 384 applied actions. The source photos and journal are under `photo-task/20261029T153050Z-e1db23ae3523/station-photos`.

## Continuing on SIREN

The [series command](../../tools/bettergi-agent/README.md#repeat-a-qualified-photo-task) repeats this named task under the existing controller limits. Each batch must finish, release input and pass both audits before the next can start. A stop file cancels the current resident and all future batches. The supervisor checks the original host and child process, Windows session and instance identity, and stops on a lost identity check. The upper limit is three batches within 30 minutes, and each batch keeps its original circuit, wall-clock and temperature limits.

In the first two-batch attempt, batch one verified four circuits and three photos. Batch two finished its route, but its encoder dropped five frames in the final segment. The supervisor refused credit for that batch and stopped. The original dispatch receipts and an independent reconstruction from capture timestamps measured a 25.81-second gap between batches, including a 20.34-second model load. Within-batch timing and between-batch startup are reported separately.

The segmented recorder now admits up to 32 verified RGB192 frames while the encoder catches up, approximately 3.4 MiB or 1.6 seconds at 20 Hz. The live controller continues to consume the newest frame. A delayed-writer regression filled all 32 slots and drained them without loss. The repaired series at `continuation/series-20261029T153926Z-a830841ef303` completed both four-circuit batches and verified six original station photos across 32 legs. Both batches recorded zero dropped frames and reached a maximum observed queue depth of two. Their GPU temperature peaks were 63 °C and 62 °C. The original host remained minimized and the child reported game-ready with input released.

The two repaired batches applied 1,063 actions in total. Their measured last-to-first dispatch interval was 24.84 seconds across the batch boundary, including 18.47 seconds of model loading. The lease-adjusted Windows clock and the independent capture clock gave the same result.

The follow-up experiment carried the loaded model across independently graded photo requests in one bounded lease. It measured each handoff against the earlier one-second limit and audited request ownership, source age and the separate photo journals. See the [warm request results](BetterGI-Warm-Requests-2026-10-29.md). For a different neighborhood, first survey its positions and collect a separate held-out lease before using its photos as task evidence.

## Reproduce on SIREN

The [launcher guide](../../tools/bettergi-agent/README.md) gives the thermal-limited command. The [training guide](../../tools/bettergi-agent/STEERING-HEAD.md) covers independent training and evaluation leases. Model files live under `artifacts/agent/steering` and `artifacts/agent/landmarks`. Recordings, source-indexed station sheets, receipts and the failed attempt live under `artifacts/live/2026-10-29-patrol`. Large local recordings and downloaded model weights stay outside Git.

The sealed 24-circuit run is `sustained/20261029T151132Z-532c7f82221a` within that evidence directory. Its `audit-checkpoints.json` joins both shadow models to the actual gameplay. Its `dispatch-continuity.json` measures input cadence, and `station-landmarks/station-views.png` shows the final circuit. The paired comparison and selection record are `paired-sustained-24.json` and `qualify-sustained-24.json` in the landmark model directory.
